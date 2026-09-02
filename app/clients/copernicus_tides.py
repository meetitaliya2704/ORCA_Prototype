from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from app.core.performance import performance_span, to_thread_timed


COPERNICUS_TIDE_PRODUCT_ID = "GLOBAL_ANALYSISFORECAST_PHY_001_024"
TIDE_VARIABLES = (
    "total_sea_level",
    "ocean_tide",
    "tide_loading",
    "invert_barometer",
    "sea_surface_height",
    "global_mean_steric_variation",
    "global_mean_mass_volume_variation",
)
STATIC_TIDE_VARIABLES = ("mask", "deptho")
STATIC_SURFACE_LEVEL_COORDINATE_M = 0.49402499198913574


class TideProviderError(Exception):
    pass


class TideSourceNotConfiguredError(TideProviderError):
    pass


class TideDependencyMissingError(TideProviderError):
    pass


class TideAuthenticationError(TideProviderError):
    pass


class TideSourceUnavailableError(TideProviderError):
    pass


class InvalidTideResponseError(TideProviderError):
    pass


class StaticMaskUnavailableError(TideProviderError):
    pass


class StaticGridAlignmentError(TideProviderError):
    pass


@dataclass(frozen=True)
class TideTimeMetadata:
    classification: str
    reference_time: datetime | None = None
    lead_hours: float | None = None


@dataclass(frozen=True)
class TideCell:
    latitude: float
    longitude: float
    depth_m: float
    valid_time: datetime
    total_sea_level: float | None
    ocean_tide: float | None
    tide_loading: float | None
    invert_barometer: float | None
    sea_surface_height: float | None
    global_mean_steric_variation: float | None
    global_mean_mass_volume_variation: float | None


@dataclass(frozen=True)
class TideStaticCell:
    latitude: float
    longitude: float
    mask: int | None
    bathymetry_m: float | None
    mask_depth_m: float | None = None


class TideProvider(Protocol):
    async def available_times(self, **kwargs: Any) -> list[datetime]: ...
    async def fetch_dynamic(self, **kwargs: Any) -> list[TideCell]: ...
    async def fetch_static(self, **kwargs: Any) -> list[TideStaticCell]: ...


class TideMetadataResolver(Protocol):
    async def resolve(self, **kwargs: Any) -> TideTimeMetadata | None: ...


def validate_tide_metadata(metadata: Any) -> None:
    names = set(metadata.data_vars) if hasattr(metadata, "data_vars") else set(metadata)
    missing = set(TIDE_VARIABLES) - names
    if missing:
        raise InvalidTideResponseError(
            "Copernicus sea-level metadata is missing required variables"
        )
    if "load_tide" in names and "tide_loading" not in names:
        raise InvalidTideResponseError("Legacy load_tide cannot replace tide_loading")


def decode_tide_value(value: Any, variable: Any | None = None) -> float | None:
    try:
        import numpy as np
        if np.ma.is_masked(value):
            return None
    except ModuleNotFoundError:
        pass
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    attrs = getattr(variable, "attrs", {}) if variable is not None else {}
    encoding = getattr(variable, "encoding", {}) if variable is not None else {}
    sentinels: list[float] = [-9999.0, 9.96921e36]
    for source in (attrs, encoding):
        for key in ("_FillValue", "missing_value"):
            raw = source.get(key)
            values = raw if isinstance(raw, (list, tuple)) else [raw]
            for item in values:
                try:
                    if item is not None:
                        sentinels.append(float(item))
                except (TypeError, ValueError):
                    continue
    if any(math.isclose(result, item, rel_tol=1e-6, abs_tol=1e-12) for item in sentinels):
        return None
    valid_range = attrs.get("valid_range")
    if valid_range is not None and len(valid_range) == 2:
        if result < float(valid_range[0]) or result > float(valid_range[1]):
            return None
    if "valid_min" in attrs and result < float(attrs["valid_min"]):
        return None
    if "valid_max" in attrs and result > float(attrs["valid_max"]):
        return None
    return result


def _utc(value: Any) -> datetime:
    stamp = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if not isinstance(stamp, datetime):
        stamp = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def select_surface_coordinate(
    values: Any,
    intended_m: float,
    *,
    tolerance_m: float = 0.01,
) -> float:
    candidates = sorted({float(value) for value in values if math.isfinite(float(value))})
    if not candidates:
        raise InvalidTideResponseError("Sea-level response omitted its surface coordinate")
    selected = min(candidates, key=lambda value: (abs(value - intended_m), value))
    if abs(selected - intended_m) > tolerance_m:
        raise InvalidTideResponseError("Sea-level response did not contain the intended surface coordinate")
    return selected


def _safe_provider_error(exc: Exception, *, static: bool = False) -> TideProviderError:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "auth" in name or "credential" in text or "unauthorized" in text:
        return TideAuthenticationError("Copernicus Marine authentication failed")
    if isinstance(exc, ModuleNotFoundError):
        return TideDependencyMissingError("Optional Copernicus Marine packages are not installed")
    if static:
        return StaticMaskUnavailableError("Copernicus static mask is unavailable")
    return TideSourceUnavailableError("Copernicus sea-level source is unavailable")


def _open_dataset(**kwargs: Any) -> Any:
    try:
        import copernicusmarine
    except ModuleNotFoundError as exc:
        raise TideDependencyMissingError(
            "Optional Copernicus Marine packages are not installed"
        ) from exc
    with performance_span("provider.open"):
        return copernicusmarine.open_dataset(**kwargs)


def load_tide_times(**kwargs: Any) -> list[datetime]:
    dataset = None
    try:
        dataset = _open_dataset(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            variables=["total_sea_level"],
            minimum_longitude=kwargs["minimum_longitude"], maximum_longitude=kwargs["maximum_longitude"],
            minimum_latitude=kwargs["minimum_latitude"], maximum_latitude=kwargs["maximum_latitude"],
            minimum_depth=kwargs["surface_depth_m"], maximum_depth=kwargs["surface_depth_m"],
            start_datetime=kwargs["start_datetime"], end_datetime=kwargs["end_datetime"],
        )
        return [_utc(item) for item in dataset.time.values]
    except TideProviderError:
        raise
    except Exception as exc:
        raise _safe_provider_error(exc) from exc
    finally:
        if dataset is not None:
            dataset.close()


def load_tide_dynamic(**kwargs: Any) -> list[TideCell]:
    dataset = None
    try:
        dataset = _open_dataset(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            variables=list(TIDE_VARIABLES),
            minimum_longitude=kwargs["minimum_longitude"], maximum_longitude=kwargs["maximum_longitude"],
            minimum_latitude=kwargs["minimum_latitude"], maximum_latitude=kwargs["maximum_latitude"],
            minimum_depth=kwargs["surface_depth_m"], maximum_depth=kwargs["surface_depth_m"],
            start_datetime=kwargs["start_datetime"], end_datetime=kwargs["end_datetime"],
        )
        with performance_span("provider.remote_load"):
            dataset.load()
        validate_tide_metadata(dataset)
        if "depth" not in dataset.coords:
            raise InvalidTideResponseError("Sea-level response omitted the surface coordinate")
        depth = select_surface_coordinate(dataset.depth.values, kwargs["surface_depth_m"])
        cells: list[TideCell] = []
        for time_value in dataset.time.values:
            valid_time = _utc(time_value)
            for latitude in dataset.latitude.values:
                for longitude in dataset.longitude.values:
                    values: dict[str, float | None] = {}
                    for name in TIDE_VARIABLES:
                        item = dataset[name]
                        selectors = {}
                        if "time" in item.dims: selectors["time"] = time_value
                        if "latitude" in item.dims: selectors["latitude"] = latitude
                        if "longitude" in item.dims: selectors["longitude"] = longitude
                        item = item.sel(**selectors)
                        if "depth" in item.dims:
                            item = item.sel(depth=depth, method="nearest")
                        values[name] = decode_tide_value(item.item(), dataset[name])
                    cells.append(TideCell(float(latitude), float(longitude), depth, valid_time, **values))
        if not cells:
            raise InvalidTideResponseError("Copernicus sea-level response contained no cells")
        return cells
    except TideProviderError:
        raise
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTideResponseError("Copernicus returned malformed sea-level data") from exc
    except Exception as exc:
        raise _safe_provider_error(exc) from exc
    finally:
        if dataset is not None:
            dataset.close()


def load_tide_static(**kwargs: Any) -> list[TideStaticCell]:
    dataset = None
    try:
        dataset = _open_dataset(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            dataset_part=kwargs.get("dataset_part", "bathy"), variables=list(STATIC_TIDE_VARIABLES),
            minimum_longitude=kwargs["minimum_longitude"], maximum_longitude=kwargs["maximum_longitude"],
            minimum_latitude=kwargs["minimum_latitude"], maximum_latitude=kwargs["maximum_latitude"],
            minimum_depth=kwargs.get("static_surface_depth_m", STATIC_SURFACE_LEVEL_COORDINATE_M),
            maximum_depth=kwargs.get("static_surface_depth_m", STATIC_SURFACE_LEVEL_COORDINATE_M),
        )
        with performance_span("provider.remote_load"):
            dataset.load()
        if not set(STATIC_TIDE_VARIABLES).issubset(dataset.data_vars):
            raise StaticMaskUnavailableError("Static response omitted mask or bathymetry")
        cells: list[TideStaticCell] = []
        depth_value = None
        if "depth" in dataset["mask"].dims:
            depth_value = float(min(dataset.depth.values))
        for latitude in dataset.latitude.values:
            for longitude in dataset.longitude.values:
                mask_item = dataset["mask"].sel(latitude=latitude, longitude=longitude)
                if "depth" in mask_item.dims:
                    mask_item = mask_item.sel(depth=depth_value)
                bathy_item = dataset["deptho"].sel(latitude=latitude, longitude=longitude)
                mask = decode_tide_value(mask_item.item(), dataset["mask"])
                bathy = decode_tide_value(bathy_item.item(), dataset["deptho"])
                cells.append(TideStaticCell(float(latitude), float(longitude), int(mask) if mask is not None else None, bathy, depth_value))
        if not cells:
            raise StaticMaskUnavailableError("Static response contained no cells")
        return cells
    except TideProviderError:
        raise
    except Exception as exc:
        raise _safe_provider_error(exc, static=True) from exc
    finally:
        if dataset is not None:
            dataset.close()


_REFERENCE_RE = re.compile(r"_R(?P<date>\d{8})")


def load_tide_metadata(**kwargs: Any) -> TideTimeMetadata | None:
    try:
        import copernicusmarine
    except ModuleNotFoundError as exc:
        raise TideDependencyMissingError("Optional Copernicus Marine packages are not installed") from exc
    try:
        result = copernicusmarine.get(
            dataset_id=kwargs["dataset_id"], dataset_version=kwargs["dataset_version"],
            filter=f"*{kwargs['selected_time']:%Y%m%d}*", dry_run=True,
        )
        names = [str(getattr(item, "file_path", item)) for item in getattr(result, "files", result or [])]
        references = []
        for name in names:
            match = _REFERENCE_RE.search(name)
            if match:
                references.append(datetime.strptime(match.group("date"), "%Y%m%d").replace(tzinfo=UTC))
        if not references:
            return None
        reference = max(references)
        selected = kwargs["selected_time"].astimezone(UTC)
        if selected >= reference:
            return TideTimeMetadata("forecast", reference, (selected-reference).total_seconds()/3600)
        if selected <= reference.replace(hour=0) - __import__("datetime").timedelta(hours=24):
            return TideTimeMetadata("analysis", reference, None)
        return None
    except TideProviderError:
        raise
    except Exception:
        return None


class CopernicusMarineTideProvider:
    def __init__(self, time_loader: Callable[..., list[datetime]] = load_tide_times,
                 dynamic_loader: Callable[..., list[TideCell]] = load_tide_dynamic,
                 static_loader: Callable[..., list[TideStaticCell]] = load_tide_static):
        self._time_loader = time_loader
        self._dynamic_loader = dynamic_loader
        self._static_loader = static_loader

    async def available_times(self, **kwargs: Any) -> list[datetime]:
        return await to_thread_timed(self._time_loader, **kwargs)

    async def fetch_dynamic(self, **kwargs: Any) -> list[TideCell]:
        return await to_thread_timed(self._dynamic_loader, **kwargs)

    async def fetch_static(self, **kwargs: Any) -> list[TideStaticCell]:
        return await to_thread_timed(self._static_loader, **kwargs)


class CopernicusTideMetadataResolver:
    def __init__(self, loader: Callable[..., TideTimeMetadata | None] = load_tide_metadata):
        self._loader = loader

    async def resolve(self, **kwargs: Any) -> TideTimeMetadata | None:
        return await to_thread_timed(self._loader, **kwargs)
