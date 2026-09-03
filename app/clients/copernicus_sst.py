import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol

from app.core.performance import performance_span, to_thread_timed


COPERNICUS_SST_PRODUCT_ID = "SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001"


class SSTProviderError(RuntimeError):
    """Base class for safe, typed Copernicus provider failures."""


class SSTSourceNotConfiguredError(SSTProviderError):
    pass


class SSTDependencyMissingError(SSTSourceNotConfiguredError):
    pass


class SSTAuthenticationError(SSTProviderError):
    pass


class SSTSourceUnavailableError(SSTProviderError):
    pass


class SSTRateLimitedError(SSTSourceUnavailableError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class InvalidSSTResponseError(SSTProviderError):
    pass


@dataclass(frozen=True, slots=True)
class SSTProviderCell:
    latitude: float
    longitude: float
    analysis_time: datetime
    value_kelvin: float | None
    mask: int | None = None


@dataclass(frozen=True, slots=True)
class SSTRegionalField:
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    cells: tuple[SSTProviderCell, ...]
    analysis_time: datetime
    warnings: tuple[str, ...] = ()


class SSTProvider(Protocol):
    async def fetch_cells(
        self,
        *,
        dataset_id: str,
        variable: str,
        minimum_latitude: float,
        maximum_latitude: float,
        minimum_longitude: float,
        maximum_longitude: float,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> list[SSTProviderCell]: ...

    async def fetch_region(
        self,
        *,
        dataset_id: str,
        variable: str,
        minimum_latitude: float,
        maximum_latitude: float,
        minimum_longitude: float,
        maximum_longitude: float,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> SSTRegionalField: ...


BlockingSSTLoader = Callable[..., list[SSTProviderCell]]
BlockingSSTRegionLoader = Callable[..., SSTRegionalField]


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        decoded = float(value)
    except (TypeError, ValueError):
        return None
    return decoded if math.isfinite(decoded) else None


def _as_utc_datetime(value: Any, pandas_module: Any) -> datetime:
    timestamp = pandas_module.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime().astimezone(UTC)


def _looks_like_authentication_failure(exc: Exception) -> bool:
    details = f"{type(exc).__name__} {exc}".lower()
    return any(
        token in details
        for token in (
            "auth",
            "credential",
            "forbidden",
            "login",
            "password",
            "unauthorized",
            "username",
        )
    )


def load_copernicus_sst_cells(
    *,
    dataset_id: str,
    variable: str,
    minimum_latitude: float,
    maximum_latitude: float,
    minimum_longitude: float,
    maximum_longitude: float,
    start_datetime: datetime,
    end_datetime: datetime,
) -> list[SSTProviderCell]:
    """Synchronously load a small decoded ARCO subset and close it promptly."""
    try:
        copernicusmarine = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
    except ModuleNotFoundError as exc:
        raise SSTDependencyMissingError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    dataset = None
    try:
        with performance_span("provider.open"):
            dataset = copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            variables=[variable, "mask"],
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            coordinates_selection_method="outside",
        )
        with performance_span("provider.remote_load"):
            dataset.load()

        required_coordinates = ("time", "latitude", "longitude")
        if variable not in dataset or any(
            coordinate not in dataset.coords for coordinate in required_coordinates
        ):
            raise InvalidSSTResponseError(
                "Copernicus SST data did not contain the expected structure"
            )

        values = dataset[variable]
        mask_values = dataset.get("mask")
        cells: list[SSTProviderCell] = []
        for time_value in dataset.coords["time"].values:
            analysis_time = _as_utc_datetime(time_value, pandas_module)
            for latitude_value in dataset.coords["latitude"].values:
                latitude = float(latitude_value)
                for longitude_value in dataset.coords["longitude"].values:
                    longitude = float(longitude_value)
                    selector = {
                        "time": time_value,
                        "latitude": latitude_value,
                        "longitude": longitude_value,
                    }
                    decoded_value = _optional_finite_float(
                        values.sel(**selector).item()
                    )
                    decoded_mask = (
                        _optional_finite_float(mask_values.sel(**selector).item())
                        if mask_values is not None
                        else None
                    )
                    cells.append(
                        SSTProviderCell(
                            latitude=latitude,
                            longitude=longitude,
                            analysis_time=analysis_time,
                            value_kelvin=decoded_value,
                            mask=(
                                int(decoded_mask)
                                if decoded_mask is not None
                                else None
                            ),
                        )
                    )
        if not cells:
            raise InvalidSSTResponseError(
                "Copernicus SST data contained no grid cells"
            )
        return cells
    except SSTProviderError:
        raise
    except Exception as exc:
        if _looks_like_authentication_failure(exc):
            raise SSTAuthenticationError(
                "Copernicus Marine credentials are missing or invalid"
            ) from exc
        raise SSTSourceUnavailableError(
            "Copernicus Marine SST source is unavailable"
        ) from exc
    finally:
        if dataset is not None:
            dataset.close()


def load_copernicus_sst_region(
    *,
    dataset_id: str,
    variable: str,
    minimum_latitude: float,
    maximum_latitude: float,
    minimum_longitude: float,
    maximum_longitude: float,
    start_datetime: datetime,
    end_datetime: datetime,
) -> SSTRegionalField:
    """Load one owned regional field; no lazy Xarray object escapes this call."""
    try:
        copernicusmarine = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
    except ModuleNotFoundError as exc:
        raise SSTDependencyMissingError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    dataset = None
    try:
        with performance_span("provider.open"):
            dataset = copernicusmarine.open_dataset(
                dataset_id=dataset_id,
                variables=[variable],
                minimum_latitude=minimum_latitude,
                maximum_latitude=maximum_latitude,
                minimum_longitude=minimum_longitude,
                maximum_longitude=maximum_longitude,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                coordinates_selection_method="outside",
            )
        with performance_span("provider.remote_load"):
            dataset.load()
        required_coordinates = ("time", "latitude", "longitude")
        if variable not in dataset or any(
            coordinate not in dataset.coords for coordinate in required_coordinates
        ):
            raise InvalidSSTResponseError(
                "Copernicus SST data did not contain the expected regional structure"
            )
        times = [
            (_as_utc_datetime(value, pandas_module), value)
            for value in dataset.coords["time"].values
        ]
        eligible_times = [item for item in times if item[0] <= end_datetime.astimezone(UTC)]
        if not eligible_times:
            raise InvalidSSTResponseError("Copernicus SST region contained no eligible time")
        analysis_time, raw_time = max(eligible_times, key=lambda item: item[0])
        values = dataset[variable]
        attrs = {**getattr(values, "encoding", {}), **getattr(values, "attrs", {})}
        sentinels: list[float] = []
        for name in ("_FillValue", "missing_value"):
            decoded = _optional_finite_float(attrs.get(name))
            if decoded is not None:
                sentinels.append(decoded)
        valid_min = _optional_finite_float(attrs.get("valid_min"))
        valid_max = _optional_finite_float(attrs.get("valid_max"))
        valid_range = attrs.get("valid_range")
        if valid_range is not None:
            try:
                range_values = tuple(valid_range)
            except TypeError:
                range_values = ()
            if len(range_values) == 2:
                valid_min = _optional_finite_float(range_values[0])
                valid_max = _optional_finite_float(range_values[1])
        latitudes = tuple(float(value) for value in dataset.coords["latitude"].values)
        longitudes = tuple(float(value) for value in dataset.coords["longitude"].values)
        cells: list[SSTProviderCell] = []
        for latitude_value in dataset.coords["latitude"].values:
            for longitude_value in dataset.coords["longitude"].values:
                value = _optional_finite_float(values.sel(
                    time=raw_time, latitude=latitude_value, longitude=longitude_value
                ).item())
                if value is not None and any(
                    math.isclose(value, sentinel, rel_tol=1e-6, abs_tol=1e-6)
                    for sentinel in sentinels
                ):
                    value = None
                if value is not None and (
                    (valid_min is not None and value < valid_min)
                    or (valid_max is not None and value > valid_max)
                ):
                    value = None
                cells.append(SSTProviderCell(
                    latitude=float(latitude_value),
                    longitude=float(longitude_value),
                    analysis_time=analysis_time,
                    value_kelvin=value,
                ))
        if not cells:
            raise InvalidSSTResponseError("Copernicus SST region contained no cells")
        return SSTRegionalField(
            latitudes=latitudes,
            longitudes=longitudes,
            cells=tuple(cells),
            analysis_time=analysis_time,
        )
    except SSTProviderError:
        raise
    except Exception as exc:
        if _looks_like_authentication_failure(exc):
            raise SSTAuthenticationError(
                "Copernicus Marine credentials are missing or invalid"
            ) from exc
        raise SSTSourceUnavailableError("Copernicus Marine SST source is unavailable") from exc
    finally:
        if dataset is not None:
            dataset.close()


class CopernicusMarineSSTProvider:
    """Async boundary around the Toolbox's synchronous Python API."""

    def __init__(
        self,
        loader: BlockingSSTLoader = load_copernicus_sst_cells,
        region_loader: BlockingSSTRegionLoader = load_copernicus_sst_region,
    ):
        self._loader = loader
        self._region_loader = region_loader

    async def fetch_cells(self, **kwargs: Any) -> list[SSTProviderCell]:
        return await to_thread_timed(self._loader, **kwargs)

    async def fetch_region(self, **kwargs: Any) -> SSTRegionalField:
        return await to_thread_timed(self._region_loader, **kwargs)
