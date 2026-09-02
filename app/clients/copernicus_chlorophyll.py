import asyncio
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Protocol

from app.core.performance import performance_span, to_thread_timed


COPERNICUS_CHLOROPHYLL_PRODUCT_ID = "OCEANCOLOUR_GLO_BGC_L4_NRT_009_102"
COPERNICUS_CHLOROPHYLL_SPATIAL_RESOLUTION_KM = 4.638312


class ChlorophyllProviderError(RuntimeError):
    """Base class for safe, typed Copernicus chlorophyll failures."""


class ChlorophyllSourceNotConfiguredError(ChlorophyllProviderError):
    pass


class ChlorophyllDependencyMissingError(ChlorophyllProviderError):
    pass


class ChlorophyllAuthenticationError(ChlorophyllProviderError):
    pass


class ChlorophyllSourceUnavailableError(ChlorophyllProviderError):
    pass


class InvalidChlorophyllResponseError(ChlorophyllProviderError):
    pass


@dataclass(frozen=True, slots=True)
class ChlorophyllFlagMetadata:
    meaning_to_mask: dict[str, int]
    raw_flag_meanings: str | tuple[str, ...]

    @property
    def land_mask(self) -> int:
        return self.meaning_to_mask["LAND"]

    @property
    def interpolated_mask(self) -> int:
        return self.meaning_to_mask["INTERPOLATED"]


@dataclass(frozen=True, slots=True)
class ChlorophyllProviderCell:
    latitude: float
    longitude: float
    analysis_time: datetime
    chlorophyll_mg_m3: float | None
    uncertainty_percent: float | None
    flag_value: int | None


@dataclass(frozen=True, slots=True)
class ChlorophyllProviderResult:
    cells: list[ChlorophyllProviderCell]
    flag_metadata: ChlorophyllFlagMetadata
    chlorophyll_valid_min: float = 0.0
    chlorophyll_valid_max: float = 1000.0
    spatial_resolution_km: float = COPERNICUS_CHLOROPHYLL_SPATIAL_RESOLUTION_KM


class ChlorophyllProvider(Protocol):
    async def fetch_cells(
        self,
        *,
        dataset_id: str,
        chlorophyll_variable: str,
        uncertainty_variable: str,
        flags_variable: str,
        minimum_latitude: float,
        maximum_latitude: float,
        minimum_longitude: float,
        maximum_longitude: float,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> ChlorophyllProviderResult: ...


BlockingChlorophyllLoader = Callable[..., ChlorophyllProviderResult]


def _metadata_sequence(value: Any, *, field_name: str) -> list[Any]:
    if isinstance(value, str):
        if field_name == "flag_meanings":
            return value.split()
        raise InvalidChlorophyllResponseError(f"{field_name} is malformed")
    if isinstance(value, Sequence):
        return list(value)
    if isinstance(value, Iterable):
        return list(value)
    raise InvalidChlorophyllResponseError(f"{field_name} is malformed")


def parse_chlorophyll_flag_metadata(
    flag_masks: Any,
    flag_meanings: Any,
) -> ChlorophyllFlagMetadata:
    """Validate the provider's mask/meaning pairing without positional assumptions."""
    masks_raw = _metadata_sequence(flag_masks, field_name="flag_masks")
    meanings_raw = _metadata_sequence(flag_meanings, field_name="flag_meanings")
    if not masks_raw or len(masks_raw) != len(meanings_raw):
        raise InvalidChlorophyllResponseError(
            "flag_masks and flag_meanings must have matching non-zero lengths"
        )

    mapping: dict[str, int] = {}
    used_masks: set[int] = set()
    for raw_mask, raw_meaning in zip(masks_raw, meanings_raw, strict=True):
        try:
            numeric_mask = float(raw_mask)
            mask = int(numeric_mask)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidChlorophyllResponseError("flag mask is malformed") from exc
        meaning = str(raw_meaning).strip().upper()
        if (
            not math.isfinite(numeric_mask)
            or numeric_mask != mask
            or mask <= 0
            or mask & (mask - 1) != 0
            or not meaning
            or meaning in mapping
            or mask in used_masks
        ):
            raise InvalidChlorophyllResponseError(
                "flag metadata contains duplicate or invalid mappings"
            )
        mapping[meaning] = mask
        used_masks.add(mask)

    if "LAND" not in mapping or "INTERPOLATED" not in mapping:
        raise InvalidChlorophyllResponseError(
            "flag metadata must define LAND and INTERPOLATED"
        )
    if mapping["LAND"] & mapping["INTERPOLATED"]:
        raise InvalidChlorophyllResponseError(
            "LAND and INTERPOLATED masks must not overlap"
        )
    raw = flag_meanings if isinstance(flag_meanings, str) else tuple(
        str(value) for value in meanings_raw
    )
    return ChlorophyllFlagMetadata(mapping, raw)


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        decoded = float(value)
    except (TypeError, ValueError):
        return None
    return decoded if math.isfinite(decoded) else None


def _optional_flag(value: Any) -> int | None:
    decoded = _optional_finite_float(value)
    if decoded is None or decoded < 0 or decoded != int(decoded):
        return None
    return int(decoded)


def _as_utc_datetime(value: Any, pandas_module: Any) -> datetime:
    timestamp = pandas_module.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime().astimezone(UTC)


def _scalar_at(variable: Any, selector: dict[str, Any]) -> Any:
    selected = variable.sel(**selector).squeeze(drop=True)
    if getattr(selected, "size", 1) != 1:
        raise InvalidChlorophyllResponseError(
            "Copernicus chlorophyll variable did not resolve to one value"
        )
    return selected.item()


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


def load_copernicus_chlorophyll_cells(
    *,
    dataset_id: str,
    chlorophyll_variable: str,
    uncertainty_variable: str,
    flags_variable: str,
    minimum_latitude: float,
    maximum_latitude: float,
    minimum_longitude: float,
    maximum_longitude: float,
    start_datetime: datetime,
    end_datetime: datetime,
) -> ChlorophyllProviderResult:
    """Load a bounded, decoded ARCO subset and close it in the worker thread."""
    try:
        copernicusmarine = import_module("copernicusmarine")
        pandas_module = import_module("pandas")
    except ModuleNotFoundError as exc:
        raise ChlorophyllDependencyMissingError(
            "The optional Copernicus Marine package is not installed"
        ) from exc

    dataset = None
    try:
        with performance_span("provider.open"):
            dataset = copernicusmarine.open_dataset(
            dataset_id=dataset_id,
            variables=[
                chlorophyll_variable,
                uncertainty_variable,
                flags_variable,
            ],
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

        required_variables = (
            chlorophyll_variable,
            uncertainty_variable,
            flags_variable,
        )
        required_coordinates = ("time", "latitude", "longitude")
        if any(name not in dataset for name in required_variables) or any(
            coordinate not in dataset.coords for coordinate in required_coordinates
        ):
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll data did not contain the expected structure"
            )

        chlorophyll = dataset[chlorophyll_variable]
        uncertainty = dataset[uncertainty_variable]
        flags = dataset[flags_variable]
        flag_metadata = parse_chlorophyll_flag_metadata(
            flags.attrs.get("flag_masks"),
            flags.attrs.get("flag_meanings"),
        )
        valid_min = _optional_finite_float(chlorophyll.attrs.get("valid_min"))
        valid_max = _optional_finite_float(chlorophyll.attrs.get("valid_max"))
        if valid_min is None or valid_max is None or valid_min >= valid_max:
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll valid-range metadata is malformed"
            )

        cells: list[ChlorophyllProviderCell] = []
        for time_value in dataset.coords["time"].values:
            analysis_time = _as_utc_datetime(time_value, pandas_module)
            for latitude_value in dataset.coords["latitude"].values:
                latitude = float(latitude_value)
                for longitude_value in dataset.coords["longitude"].values:
                    selector = {
                        "time": time_value,
                        "latitude": latitude_value,
                        "longitude": longitude_value,
                    }
                    cells.append(
                        ChlorophyllProviderCell(
                            latitude=latitude,
                            longitude=float(longitude_value),
                            analysis_time=analysis_time,
                            chlorophyll_mg_m3=_optional_finite_float(
                                _scalar_at(chlorophyll, selector)
                            ),
                            uncertainty_percent=_optional_finite_float(
                                _scalar_at(uncertainty, selector)
                            ),
                            flag_value=_optional_flag(_scalar_at(flags, selector)),
                        )
                    )
        if not cells:
            raise InvalidChlorophyllResponseError(
                "Copernicus chlorophyll data contained no grid cells"
            )
        return ChlorophyllProviderResult(
            cells=cells,
            flag_metadata=flag_metadata,
            chlorophyll_valid_min=valid_min,
            chlorophyll_valid_max=valid_max,
        )
    except ChlorophyllProviderError:
        raise
    except Exception as exc:
        if _looks_like_authentication_failure(exc):
            raise ChlorophyllAuthenticationError(
                "Copernicus Marine credentials are missing or invalid"
            ) from exc
        raise ChlorophyllSourceUnavailableError(
            "Copernicus Marine chlorophyll source is unavailable"
        ) from exc
    finally:
        if dataset is not None:
            dataset.close()


class CopernicusMarineChlorophyllProvider:
    """Async boundary around the Toolbox's synchronous Python API."""

    def __init__(
        self,
        loader: BlockingChlorophyllLoader = load_copernicus_chlorophyll_cells,
    ) -> None:
        self._loader = loader

    async def fetch_cells(self, **kwargs: Any) -> ChlorophyllProviderResult:
        return await to_thread_timed(self._loader, **kwargs)
