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


class SSTAuthenticationError(SSTProviderError):
    pass


class SSTSourceUnavailableError(SSTProviderError):
    pass


class InvalidSSTResponseError(SSTProviderError):
    pass


@dataclass(frozen=True, slots=True)
class SSTProviderCell:
    latitude: float
    longitude: float
    analysis_time: datetime
    value_kelvin: float | None
    mask: int | None = None


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


BlockingSSTLoader = Callable[..., list[SSTProviderCell]]


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
        raise SSTSourceNotConfiguredError(
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


class CopernicusMarineSSTProvider:
    """Async boundary around the Toolbox's synchronous Python API."""

    def __init__(self, loader: BlockingSSTLoader = load_copernicus_sst_cells):
        self._loader = loader

    async def fetch_cells(self, **kwargs: Any) -> list[SSTProviderCell]:
        return await to_thread_timed(self._loader, **kwargs)
