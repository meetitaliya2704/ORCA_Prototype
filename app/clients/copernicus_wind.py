import asyncio
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol


COPERNICUS_WIND_PRODUCT_ID = "WIND_GLO_PHY_L4_NRT_012_004"
COPERNICUS_WIND_DATASET_VERSION = "202207"


class WindProviderError(RuntimeError):
    """Base class for safe, typed Copernicus wind failures."""


class WindSourceNotConfiguredError(WindProviderError):
    pass


class WindAuthenticationError(WindProviderError):
    pass


class WindSourceUnavailableError(WindProviderError):
    pass


class InvalidWindResponseError(WindProviderError):
    pass


@dataclass(frozen=True, slots=True)
class WindProviderCell:
    latitude: float
    longitude: float
    valid_time: datetime
    eastward_wind_mps: float | None
    northward_wind_mps: float | None


@dataclass(frozen=True, slots=True)
class WindProviderResult:
    cells: list[WindProviderCell]
    warnings: tuple[str, ...] = ()


class WindProvider(Protocol):
    async def fetch_cells(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> WindProviderResult: ...


BlockingWindLoader = Callable[..., WindProviderResult]


def extract_catalogue_time_bounds(
    catalogue: Any,
    *,
    dataset_id: str,
    dataset_version: str,
    variable: str,
) -> tuple[datetime, datetime]:
    """Extract official ARCO UTC bounds without accessing data chunks."""
    payload = catalogue.model_dump() if hasattr(catalogue, "model_dump") else catalogue
    for product in payload.get("products", []):
        for dataset in product.get("datasets", []):
            if dataset.get("dataset_id") != dataset_id:
                continue
            for version in dataset.get("versions", []):
                if version.get("label") != dataset_version:
                    continue
                for part in version.get("parts", []):
                    for service in part.get("services", []):
                        if service.get("service_short_name") != "timeseries":
                            continue
                        for item in service.get("variables", []):
                            if item.get("short_name") != variable:
                                continue
                            for coordinate in item.get("coordinates", []):
                                if coordinate.get("coordinate_id") != "time":
                                    continue
                                minimum = coordinate.get("minimum_value")
                                maximum = coordinate.get("maximum_value")
                                if minimum is None or maximum is None:
                                    break
                                return (
                                    datetime.fromtimestamp(float(minimum) / 1000, tz=UTC),
                                    datetime.fromtimestamp(float(maximum) / 1000, tz=UTC),
                                )
    raise InvalidWindResponseError(
        "Copernicus wind catalogue omitted official time bounds"
    )


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


class _UpdatingWarningHandler(logging.Handler):
    """Capture only a known, non-sensitive Toolbox updating warning."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.detected = False

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage().lower()
        if "currently being updated" in message or "may not be up to date" in message:
            self.detected = True


def load_copernicus_wind_cells(
    *,
    dataset_id: str,
    dataset_version: str,
    eastward_variable: str,
    northward_variable: str,
    minimum_latitude: float,
    maximum_latitude: float,
    minimum_longitude: float,
    maximum_longitude: float,
    start_datetime: datetime,
    end_datetime: datetime,
) -> WindProviderResult:
    """Load one small decoded Toolbox subset and close it in this worker."""
    try:
        copernicusmarine = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
    except ModuleNotFoundError as exc:
        raise WindSourceNotConfiguredError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    dataset = None
    warning_handler = _UpdatingWarningHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(warning_handler)
    try:
        variables = [eastward_variable, northward_variable]
        catalogue = copernicusmarine.describe(
            dataset_id=dataset_id,
            disable_progress_bar=True,
        )
        minimum_time, maximum_time = extract_catalogue_time_bounds(
            catalogue,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            variable=eastward_variable,
        )
        requested_hour = end_datetime.astimezone(UTC).replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        selected_time = min(requested_hour, maximum_time)
        if selected_time < minimum_time:
            return WindProviderResult(cells=[])

        dataset = copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            variables=variables,
            minimum_latitude=minimum_latitude,
            maximum_latitude=maximum_latitude,
            minimum_longitude=minimum_longitude,
            maximum_longitude=maximum_longitude,
            start_datetime=selected_time,
            end_datetime=selected_time,
            coordinates_selection_method="outside",
        )
        dataset.load()

        required_coordinates = ("time", "latitude", "longitude")
        if any(variable not in dataset for variable in variables) or any(
            coordinate not in dataset.coords for coordinate in required_coordinates
        ):
            raise InvalidWindResponseError(
                "Copernicus wind data did not contain the expected structure"
            )

        cells: list[WindProviderCell] = []
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
                        WindProviderCell(
                            latitude=latitude,
                            longitude=longitude,
                            valid_time=valid_time,
                            eastward_wind_mps=_optional_finite_float(
                                dataset[eastward_variable].sel(**selector).item()
                            ),
                            northward_wind_mps=_optional_finite_float(
                                dataset[northward_variable].sel(**selector).item()
                            ),
                        )
                    )
        if not cells:
            raise InvalidWindResponseError(
                "Copernicus wind data contained no grid cells"
            )
        warnings: tuple[str, ...] = ()
        if warning_handler.detected or maximum_time < requested_hour:
            warnings = (
                "Copernicus wind dataset may be actively updating; latest "
                "available data precedes the requested time",
            )
        return WindProviderResult(cells=cells, warnings=warnings)
    except WindProviderError:
        raise
    except Exception as exc:
        if _looks_like_authentication_failure(exc):
            raise WindAuthenticationError(
                "Copernicus Marine credentials are missing or invalid"
            ) from exc
        raise WindSourceUnavailableError(
            "Copernicus Marine wind source is unavailable"
        ) from exc
    finally:
        root_logger.removeHandler(warning_handler)
        if dataset is not None:
            dataset.close()


class CopernicusMarineWindProvider:
    def __init__(self, loader: BlockingWindLoader = load_copernicus_wind_cells):
        self._loader = loader

    async def fetch_cells(self, **kwargs: Any) -> WindProviderResult:
        return await asyncio.to_thread(self._loader, **kwargs)
