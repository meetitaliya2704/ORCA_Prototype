import asyncio
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol


COPERNICUS_WAVE_PRODUCT_ID = "GLOBAL_ANALYSISFORECAST_WAV_001_027"
COPERNICUS_WAVE_DATASET_VERSION = "202411"
_CYCLE_PATTERN = re.compile(r"_R(?P<date>\d{8})_(?P<hour>\d{2})H\.nc$")


class WaveProviderError(RuntimeError):
    """Base class for safe, typed Copernicus wave failures."""


class WaveSourceNotConfiguredError(WaveProviderError):
    pass


class WaveAuthenticationError(WaveProviderError):
    pass


class WaveSourceUnavailableError(WaveProviderError):
    pass


class InvalidWaveResponseError(WaveProviderError):
    pass


@dataclass(frozen=True, slots=True)
class WaveProviderCell:
    latitude: float
    longitude: float
    valid_time: datetime
    significant_wave_height_m: float | None
    mean_wave_period_s: float | None
    mean_wave_direction_from_deg: float | None


class WaveProvider(Protocol):
    async def fetch_cells(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        height_variable: str,
        period_variable: str,
        direction_variable: str,
        minimum_latitude: float,
        maximum_latitude: float,
        minimum_longitude: float,
        maximum_longitude: float,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> list[WaveProviderCell]: ...


class WaveCycleResolver(Protocol):
    async def resolve_cycle(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        reference_time: datetime,
    ) -> datetime | None: ...


BlockingWaveLoader = Callable[..., list[WaveProviderCell]]
BlockingCycleLoader = Callable[..., datetime | None]


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        decoded = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(decoded) or decoded == -32767.0:
        return None
    return decoded


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


def _wave_error(exc: Exception) -> WaveProviderError:
    if _looks_like_authentication_failure(exc):
        return WaveAuthenticationError(
            "Copernicus Marine credentials are missing or invalid"
        )
    return WaveSourceUnavailableError(
        "Copernicus Marine wave source is unavailable"
    )


def parse_latest_cycle_reference(filenames: Iterable[str]) -> datetime | None:
    references: list[datetime] = []
    for filename in filenames:
        match = _CYCLE_PATTERN.search(filename)
        if match is None:
            continue
        references.append(
            datetime.strptime(
                f"{match.group('date')}{match.group('hour')}",
                "%Y%m%d%H",
            ).replace(tzinfo=UTC)
        )
    return max(references, default=None)


def _response_filenames(response: Any) -> list[str]:
    filenames: list[str] = []
    for item in getattr(response, "files", []) or []:
        if isinstance(item, dict):
            filename = item.get("filename")
        else:
            filename = getattr(item, "filename", None)
        if isinstance(filename, str):
            filenames.append(filename)
    return filenames


def load_latest_wave_cycle(
    *,
    dataset_id: str,
    dataset_version: str,
    reference_time: datetime,
) -> datetime | None:
    """Resolve a cycle from official original-file metadata without downloads."""
    try:
        copernicusmarine = import_module("copernicusmarine")
    except ModuleNotFoundError as exc:
        raise WaveSourceNotConfiguredError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    try:
        response = copernicusmarine.get(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            filter=f"*{reference_time.astimezone(UTC):%Y%m%d}*",
            dry_run=True,
            disable_progress_bar=True,
        )
        return parse_latest_cycle_reference(_response_filenames(response))
    except WaveProviderError:
        raise
    except Exception as exc:
        raise _wave_error(exc) from exc


def load_copernicus_wave_cells(
    *,
    dataset_id: str,
    dataset_version: str,
    height_variable: str,
    period_variable: str,
    direction_variable: str,
    minimum_latitude: float,
    maximum_latitude: float,
    minimum_longitude: float,
    maximum_longitude: float,
    start_datetime: datetime,
    end_datetime: datetime,
) -> list[WaveProviderCell]:
    """Load a small decoded ARCO subset and close it in the worker thread."""
    try:
        copernicusmarine = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
    except ModuleNotFoundError as exc:
        raise WaveSourceNotConfiguredError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    dataset = None
    try:
        variables = [height_variable, period_variable, direction_variable]
        dataset = copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            variables=variables,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            coordinates_selection_method="outside",
        )
        dataset.load()

        required_coordinates = ("time", "latitude", "longitude")
        if any(variable not in dataset for variable in variables) or any(
            coordinate not in dataset.coords for coordinate in required_coordinates
        ):
            raise InvalidWaveResponseError(
                "Copernicus wave data did not contain the expected structure"
            )

        cells: list[WaveProviderCell] = []
        for time_value in dataset.coords["time"].values:
            valid_time = _as_utc_datetime(time_value, pandas_module)
            for latitude_value in dataset.coords["latitude"].values:
                latitude = float(latitude_value)
                for longitude_value in dataset.coords["longitude"].values:
                    longitude = float(longitude_value)
                    selector = {
                        "time": time_value,
                        "latitude": latitude_value,
                        "longitude": longitude_value,
                    }
                    cells.append(
                        WaveProviderCell(
                            latitude=latitude,
                            longitude=longitude,
                            valid_time=valid_time,
                            significant_wave_height_m=_optional_finite_float(
                                dataset[height_variable].sel(**selector).item()
                            ),
                            mean_wave_period_s=_optional_finite_float(
                                dataset[period_variable].sel(**selector).item()
                            ),
                            mean_wave_direction_from_deg=_optional_finite_float(
                                dataset[direction_variable].sel(**selector).item()
                            ),
                        )
                    )
        if not cells:
            raise InvalidWaveResponseError(
                "Copernicus wave data contained no grid cells"
            )
        return cells
    except WaveProviderError:
        raise
    except Exception as exc:
        raise _wave_error(exc) from exc
    finally:
        if dataset is not None:
            dataset.close()


class CopernicusMarineWaveProvider:
    def __init__(self, loader: BlockingWaveLoader = load_copernicus_wave_cells):
        self._loader = loader

    async def fetch_cells(self, **kwargs: Any) -> list[WaveProviderCell]:
        return await asyncio.to_thread(self._loader, **kwargs)


class CopernicusMarineWaveCycleResolver:
    def __init__(self, loader: BlockingCycleLoader = load_latest_wave_cycle):
        self._loader = loader

    async def resolve_cycle(self, **kwargs: Any) -> datetime | None:
        return await asyncio.to_thread(self._loader, **kwargs)
