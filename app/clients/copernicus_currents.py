import asyncio
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol


COPERNICUS_CURRENT_PRODUCT_ID = "GLOBAL_ANALYSISFORECAST_PHY_001_024"
CURRENT_VARIABLES = (
    "uo", "vo", "utide", "vtide", "vsdx", "vsdy", "utotal", "vtotal"
)
_REFERENCE_PATTERN = re.compile(r"_R(?P<date>\d{8})(?:_|\.|$)")


class CurrentProviderError(RuntimeError):
    """Safe base error for Copernicus current access."""


class CurrentSourceNotConfiguredError(CurrentProviderError): pass
class CurrentDependencyMissingError(CurrentProviderError): pass
class CurrentAuthenticationError(CurrentProviderError): pass
class CurrentSourceUnavailableError(CurrentProviderError): pass
class InvalidCurrentResponseError(CurrentProviderError): pass


@dataclass(frozen=True, slots=True)
class CurrentCycleMetadata:
    reference_time: datetime


@dataclass(frozen=True, slots=True)
class CurrentProviderCell:
    latitude: float
    longitude: float
    depth_m: float
    valid_time: datetime
    sea_mask: int | None
    bathymetry_m: float | None
    uo: float | None
    vo: float | None
    utide: float | None
    vtide: float | None
    vsdx: float | None
    vsdy: float | None
    utotal: float | None
    vtotal: float | None


class CurrentProvider(Protocol):
    async def available_times(self, **kwargs: Any) -> list[datetime]: ...
    async def fetch_cells(self, **kwargs: Any) -> list[CurrentProviderCell]: ...


class CurrentMetadataResolver(Protocol):
    async def resolve(self, **kwargs: Any) -> CurrentCycleMetadata | None: ...


def _looks_like_authentication_failure(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(word in text for word in (
        "auth", "credential", "forbidden", "login", "password",
        "unauthorized", "username",
    ))


def _safe_error(exc: Exception) -> CurrentProviderError:
    if isinstance(exc, ModuleNotFoundError):
        return CurrentDependencyMissingError(
            "The optional Copernicus Marine package is not installed"
        )
    if _looks_like_authentication_failure(exc):
        return CurrentAuthenticationError(
            "Copernicus Marine credentials are missing or invalid"
        )
    return CurrentSourceUnavailableError(
        "Copernicus Marine current source is unavailable"
    )


def _as_utc(value: Any, pandas_module: Any) -> datetime:
    timestamp = pandas_module.Timestamp(value)
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime().astimezone(UTC)


def _metadata_values(variable: Any, name: str) -> list[float]:
    values: list[float] = []
    for source in (getattr(variable, "attrs", {}), getattr(variable, "encoding", {})):
        raw = source.get(name)
        if raw is None:
            continue
        raw_values = raw if isinstance(raw, (list, tuple)) else [raw]
        for item in raw_values:
            try:
                number = float(item)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                values.append(number)
    return values


def decode_current_value(value: Any, variable: Any | None = None) -> float | None:
    """Accept a Toolbox-decoded scalar while honoring masks and source metadata."""
    if value is None or bool(getattr(value, "mask", False)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    fills = [9.96921e36, 1.0e20]
    if variable is not None:
        fills += _metadata_values(variable, "_FillValue")
        fills += _metadata_values(variable, "missing_value")
    if any(math.isclose(number, fill, rel_tol=1e-6, abs_tol=0.0) for fill in fills):
        return None
    if variable is not None:
        minimums = _metadata_values(variable, "valid_min")
        maximums = _metadata_values(variable, "valid_max")
        ranges = getattr(variable, "attrs", {}).get("valid_range")
        if ranges is not None:
            try:
                minimums.append(float(ranges[0])); maximums.append(float(ranges[1]))
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
        if minimums and number < max(minimums):
            return None
        if maximums and number > min(maximums):
            return None
    return number


def parse_current_reference(filenames: Iterable[str]) -> CurrentCycleMetadata | None:
    references = []
    for filename in filenames:
        match = _REFERENCE_PATTERN.search(filename)
        if match:
            references.append(datetime.strptime(match.group("date"), "%Y%m%d").replace(tzinfo=UTC))
    return CurrentCycleMetadata(max(references)) if references else None


def _response_filenames(response: Any) -> list[str]:
    result = []
    for item in getattr(response, "files", []) or []:
        value = item.get("filename") if isinstance(item, dict) else getattr(item, "filename", None)
        if isinstance(value, str):
            result.append(value)
    return result


def load_current_reference(*, dataset_id: str, dataset_version: str, selected_time: datetime) -> CurrentCycleMetadata | None:
    try:
        module = import_module("copernicusmarine")
        response = module.get(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            filter=f"*{selected_time.astimezone(UTC):%Y%m%d}*",
            dry_run=True,
            disable_progress_bar=True,
        )
        return parse_current_reference(_response_filenames(response))
    except CurrentProviderError:
        raise
    except Exception as exc:
        raise _safe_error(exc) from exc


def load_current_times(**kwargs: Any) -> list[datetime]:
    try:
        module = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
        dataset = None
        dataset = module.open_dataset(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            variables=["utotal"], minimum_latitude=kwargs["minimum_latitude"],
            maximum_latitude=kwargs["maximum_latitude"], minimum_longitude=kwargs["minimum_longitude"],
            maximum_longitude=kwargs["maximum_longitude"], start_datetime=kwargs["start_datetime"],
            end_datetime=kwargs["end_datetime"], minimum_depth=kwargs["surface_depth_m"],
            maximum_depth=kwargs["surface_depth_m"], coordinates_selection_method="outside",
        )
        dataset.coords["time"].load()
        return sorted({_as_utc(value, pandas_module) for value in dataset.coords["time"].values})
    except CurrentProviderError:
        raise
    except Exception as exc:
        raise _safe_error(exc) from exc
    finally:
        if "dataset" in locals() and dataset is not None:
            dataset.close()


def load_current_cells(**kwargs: Any) -> list[CurrentProviderCell]:
    dynamic = static = None
    try:
        module = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
        bounds = dict(
            minimum_latitude=kwargs["minimum_latitude"], maximum_latitude=kwargs["maximum_latitude"],
            minimum_longitude=kwargs["minimum_longitude"], maximum_longitude=kwargs["maximum_longitude"],
            coordinates_selection_method="outside",
        )
        dynamic = module.open_dataset(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            variables=list(CURRENT_VARIABLES), start_datetime=kwargs["selected_time"],
            end_datetime=kwargs["selected_time"], minimum_depth=kwargs["surface_depth_m"],
            maximum_depth=kwargs["surface_depth_m"], **bounds,
        )
        static = module.open_dataset(
            dataset_id=kwargs["static_dataset_id"], dataset_version=kwargs["static_dataset_version"],
            dataset_part="bathy", variables=["mask", "deptho"],
            minimum_depth=kwargs["surface_depth_m"], maximum_depth=kwargs["surface_depth_m"], **bounds,
        )
        dynamic.load(); static.load()
        if any(name not in dynamic for name in CURRENT_VARIABLES) or any(name not in static for name in ("mask", "deptho")):
            raise InvalidCurrentResponseError("Copernicus current response has an invalid structure")
        for coordinate in ("time", "depth", "latitude", "longitude"):
            if coordinate not in dynamic.coords:
                raise InvalidCurrentResponseError("Copernicus current coordinates are incomplete")
        if static["mask"].attrs.get("standard_name") != "sea_binary_mask" or "1 = sea" not in str(static["mask"].attrs.get("long_name", "")):
            raise InvalidCurrentResponseError("Copernicus land/sea mask metadata is invalid")
        time_value=dynamic.time.values[0]; depth_value=dynamic.depth.values[0]
        valid_time=_as_utc(time_value,pandas_module); cells=[]
        for lat_value in dynamic.latitude.values:
            for lon_value in dynamic.longitude.values:
                selector={"time":time_value,"depth":depth_value,"latitude":lat_value,"longitude":lon_value}
                values={name:decode_current_value(dynamic[name].sel(**selector).item(),dynamic[name]) for name in CURRENT_VARIABLES}
                # Static and SMOC coordinates differ by a few microdegrees in
                # the live catalogue. Nearest is used only to associate the
                # co-registered static mask; final user-cell selection remains
                # deterministic Haversine ranking below the provider boundary.
                mask=decode_current_value(
                    static["mask"].sel(
                        depth=static.depth.values[0], latitude=lat_value,
                        longitude=lon_value, method="nearest"
                    ).item(), static["mask"]
                )
                deptho=decode_current_value(
                    static["deptho"].sel(
                        latitude=lat_value, longitude=lon_value, method="nearest"
                    ).item(), static["deptho"]
                )
                cells.append(CurrentProviderCell(
                    latitude=float(lat_value), longitude=float(lon_value), depth_m=float(depth_value),
                    valid_time=valid_time, sea_mask=int(mask) if mask is not None else None,
                    bathymetry_m=deptho, **values,
                ))
        if not cells:
            raise InvalidCurrentResponseError("Copernicus current response contained no cells")
        return cells
    except CurrentProviderError:
        raise
    except ModuleNotFoundError as exc:
        raise CurrentDependencyMissingError("The optional Copernicus Marine package is not installed") from exc
    except Exception as exc:
        raise _safe_error(exc) from exc
    finally:
        if dynamic is not None: dynamic.close()
        if static is not None: static.close()


class CopernicusMarineCurrentProvider:
    def __init__(self, time_loader: Callable[..., list[datetime]] = load_current_times, cell_loader: Callable[..., list[CurrentProviderCell]] = load_current_cells):
        self._time_loader=time_loader; self._cell_loader=cell_loader
    async def available_times(self, **kwargs: Any) -> list[datetime]:
        return await asyncio.to_thread(self._time_loader, **kwargs)
    async def fetch_cells(self, **kwargs: Any) -> list[CurrentProviderCell]:
        return await asyncio.to_thread(self._cell_loader, **kwargs)


class CopernicusCurrentMetadataResolver:
    def __init__(self, loader: Callable[..., CurrentCycleMetadata | None] = load_current_reference):
        self._loader=loader
    async def resolve(self, **kwargs: Any) -> CurrentCycleMetadata | None:
        return await asyncio.to_thread(self._loader, **kwargs)
