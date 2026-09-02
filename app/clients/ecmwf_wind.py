import asyncio
import hashlib
import logging
import math
import tempfile
import threading
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from app.core.performance import performance_span, to_thread_timed


ECMWF_WIND_PROVIDER = "ECMWF"
ECMWF_WIND_MODEL = "ifs"
ECMWF_WIND_RESOLUTION = "0p25"
ECMWF_WIND_RESOLUTION_DEGREES = 0.25
ECMWF_WIND_U_PARAMETER = "10u"
ECMWF_WIND_V_PARAMETER = "10v"
ECMWF_WIND_STREAM = "oper"
ECMWF_WIND_TYPE = "fc"
ECMWF_ALLOWED_SOURCES = frozenset({"ecmwf", "aws", "azure", "google"})


class ECMWFWindError(RuntimeError):
    """Base class for safe, typed ECMWF forecast failures."""


class ECMWFWindNotConfiguredError(ECMWFWindError):
    pass


class ECMWFWindDependencyMissingError(ECMWFWindError):
    pass


class ECMWFWindCycleUnavailableError(ECMWFWindError):
    pass


class ECMWFWindForecastOutOfRangeError(ECMWFWindError):
    pass


class ECMWFWindStepUnavailableError(ECMWFWindError):
    pass


class ECMWFWindSourceUnavailableError(ECMWFWindError):
    pass


class ECMWFWindDownloadTooLargeError(ECMWFWindError):
    pass


class InvalidECMWFWindResponseError(ECMWFWindError):
    pass


class ECMWFWindCorruptDownloadError(InvalidECMWFWindResponseError):
    """A truncated, corrupt, or structurally invalid forecast response."""


class ECMWFWindDataNotFoundError(ECMWFWindError):
    pass


def _provider_status_code(exc: Exception) -> int | None:
    """Read a safe HTTP status without exposing provider URLs or exceptions."""
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    if value is None:
        value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


@dataclass(frozen=True, slots=True)
class ECMWFCycleAvailability:
    latest_short_cycle: datetime
    latest_long_cycle: datetime | None
    source: str
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class ECMWFWindField:
    forecast_reference_time: datetime
    forecast_step_hours: int
    valid_time: datetime
    ni: int
    nj: int
    latitude_first: float
    longitude_first: float
    latitude_increment: float
    longitude_increment: float
    latitude_scans_positive: bool
    longitude_scans_negative: bool
    u_values: bytes
    v_values: bytes
    source_mirror: str
    retrieved_at: datetime
    checksum_sha256: str

    @property
    def approximate_bytes(self) -> int:
        return len(self.u_values) + len(self.v_values)


class ECMWFWindProvider(Protocol):
    async def discover_cycles(self, source: str) -> ECMWFCycleAvailability: ...

    async def retrieve_field(
        self,
        source: str,
        forecast_reference_time: datetime,
        forecast_step_hours: int,
    ) -> ECMWFWindField: ...


ClientFactory = Callable[[str], Any]
Decoder = Callable[[Path, str, int, datetime], ECMWFWindField]


class _ProviderLogGuard:
    """Prevent client/mirror loggers from emitting full or signed URLs."""

    LOGGER_NAMES = (
        "ecmwf.opendata",
        "ecmwf.opendata.client",
        "ecmwf.opendata.utils",
        "multiurl",
        "multiurl.base",
        "multiurl.downloader",
        "multiurl.file",
        "multiurl.ftp",
        "multiurl.heuristics",
        "multiurl.http",
        "multiurl.multipart",
        "multiurl.multiurl",
        "multiurl.retry",
    )
    _lock = threading.Lock()
    _depth = 0
    _saved_states: list[tuple[logging.Logger, bool]] = []

    def __enter__(self) -> None:
        with self._lock:
            if self._depth == 0:
                self.__class__._saved_states = []
                for name in self.LOGGER_NAMES:
                    logger = logging.getLogger(name)
                    self._saved_states.append((logger, logger.disabled))
                    logger.disabled = True
            self.__class__._depth += 1

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        with self._lock:
            self.__class__._depth -= 1
            if self._depth == 0:
                for logger, disabled in self._saved_states:
                    logger.disabled = disabled
                self.__class__._saved_states = []


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidECMWFWindResponseError("ECMWF returned a naive timestamp")
    return value.astimezone(UTC)


def _load_client_class() -> Any:
    try:
        return import_module("ecmwf.opendata").Client
    except ModuleNotFoundError as exc:
        raise ECMWFWindDependencyMissingError(
            "The optional ECMWF Open Data package is not installed"
        ) from exc


def _load_eccodes() -> Any:
    try:
        return import_module("eccodes")
    except ModuleNotFoundError as exc:
        raise ECMWFWindDependencyMissingError(
            "The optional ecCodes decoder package is not installed"
        ) from exc


def _as_utc_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ECMWFWindCycleUnavailableError(
            "ECMWF did not return a forecast reference time"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date_time(date_value: int, time_value: int) -> datetime:
    return datetime.strptime(
        f"{date_value:08d}{time_value:04d}", "%Y%m%d%H%M"
    ).replace(tzinfo=UTC)


def _key(module: Any, handle: Any, name: str, kind: str) -> Any:
    getter = {
        "long": module.codes_get_long,
        "double": module.codes_get_double,
        "string": module.codes_get_string,
    }[kind]
    try:
        return getter(handle, name)
    except Exception as exc:
        raise ECMWFWindCorruptDownloadError(
            "ECMWF GRIB omitted required metadata"
        ) from exc


def _decoded_bytes(values: Any, missing_value: float) -> bytes:
    decoded = array("d")
    for value in values:
        number = float(value)
        decoded.append(
            math.nan
            if not math.isfinite(number) or number == missing_value
            else number
        )
    return decoded.tobytes()


def decode_ecmwf_wind_grib(
    path: Path,
    source: str,
    expected_step: int,
    retrieved_at: datetime,
) -> ECMWFWindField:
    """Decode exactly one 10u and one 10v GRIB2 message using ecCodes."""
    eccodes = _load_eccodes()
    messages: dict[str, dict[str, Any]] = {}
    try:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open("rb") as stream:
            while True:
                handle = eccodes.codes_grib_new_from_file(stream)
                if handle is None:
                    break
                try:
                    short_name = _key(eccodes, handle, "shortName", "string")
                    if short_name not in {ECMWF_WIND_U_PARAMETER, ECMWF_WIND_V_PARAMETER}:
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF GRIB contained an unexpected parameter"
                        )
                    if short_name in messages:
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF GRIB contained duplicate wind components"
                        )
                    edition = _key(eccodes, handle, "edition", "long")
                    grid_type = _key(eccodes, handle, "gridType", "string")
                    data_type = _key(eccodes, handle, "dataType", "string")
                    units = _key(eccodes, handle, "units", "string")
                    ni = _key(eccodes, handle, "Ni", "long")
                    nj = _key(eccodes, handle, "Nj", "long")
                    step = _key(eccodes, handle, "endStep", "long")
                    reference = _date_time(
                        _key(eccodes, handle, "dataDate", "long"),
                        _key(eccodes, handle, "dataTime", "long"),
                    )
                    valid_time = _date_time(
                        _key(eccodes, handle, "validityDate", "long"),
                        _key(eccodes, handle, "validityTime", "long"),
                    )
                    if (
                        edition != 2
                        or grid_type != "regular_ll"
                        or data_type != ECMWF_WIND_TYPE
                        or units not in {"m s**-1", "m s-1", "m/s"}
                    ):
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field used an unsupported GRIB grid"
                        )
                    if ni < 2 or nj < 2 or step != expected_step:
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field dimensions or step were invalid"
                        )
                    if _key(eccodes, handle, "jPointsAreConsecutive", "long"):
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field used unsupported point ordering"
                        )
                    if _key(eccodes, handle, "alternativeRowScanning", "long"):
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field used alternating row scanning"
                        )
                    missing_value = _key(eccodes, handle, "missingValue", "double")
                    values = eccodes.codes_get_values(handle)
                    if len(values) != ni * nj:
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field value count did not match its grid"
                        )
                    latitude_increment = _key(
                        eccodes, handle, "jDirectionIncrementInDegrees", "double"
                    )
                    longitude_increment = _key(
                        eccodes, handle, "iDirectionIncrementInDegrees", "double"
                    )
                    if not (
                        math.isclose(
                            latitude_increment,
                            ECMWF_WIND_RESOLUTION_DEGREES,
                            abs_tol=1e-9,
                        )
                        and math.isclose(
                            longitude_increment,
                            ECMWF_WIND_RESOLUTION_DEGREES,
                            abs_tol=1e-9,
                        )
                    ):
                        raise ECMWFWindCorruptDownloadError(
                            "ECMWF wind field resolution was not 0.25 degrees"
                        )
                    messages[short_name] = {
                        "reference": reference,
                        "step": step,
                        "valid_time": valid_time,
                        "ni": ni,
                        "nj": nj,
                        "latitude_first": _key(
                            eccodes, handle, "latitudeOfFirstGridPointInDegrees", "double"
                        ),
                        "longitude_first": _key(
                            eccodes, handle, "longitudeOfFirstGridPointInDegrees", "double"
                        ),
                        "latitude_increment": latitude_increment,
                        "longitude_increment": longitude_increment,
                        "latitude_scans_positive": bool(
                            _key(eccodes, handle, "jScansPositively", "long")
                        ),
                        "longitude_scans_negative": bool(
                            _key(eccodes, handle, "iScansNegatively", "long")
                        ),
                        "values": _decoded_bytes(values, missing_value),
                    }
                finally:
                    eccodes.codes_release(handle)
    except ECMWFWindError:
        raise
    except Exception as exc:
        raise ECMWFWindCorruptDownloadError(
            "ECMWF wind GRIB could not be decoded"
        ) from exc

    if set(messages) != {ECMWF_WIND_U_PARAMETER, ECMWF_WIND_V_PARAMETER}:
        raise ECMWFWindCorruptDownloadError(
            "ECMWF GRIB did not contain both wind components"
        )
    u = messages[ECMWF_WIND_U_PARAMETER]
    v = messages[ECMWF_WIND_V_PARAMETER]
    metadata_keys = (
        "reference",
        "step",
        "valid_time",
        "ni",
        "nj",
        "latitude_first",
        "longitude_first",
        "latitude_increment",
        "longitude_increment",
        "latitude_scans_positive",
        "longitude_scans_negative",
    )
    if any(u[key] != v[key] for key in metadata_keys):
        raise ECMWFWindCorruptDownloadError(
            "ECMWF u/v messages described different grids or times"
        )
    if u["valid_time"] != u["reference"] + timedelta(hours=u["step"]):
        raise ECMWFWindCorruptDownloadError(
            "ECMWF GRIB reference, step, and valid time were inconsistent"
        )
    return ECMWFWindField(
        forecast_reference_time=u["reference"],
        forecast_step_hours=u["step"],
        valid_time=u["valid_time"],
        ni=u["ni"],
        nj=u["nj"],
        latitude_first=u["latitude_first"],
        longitude_first=u["longitude_first"],
        latitude_increment=u["latitude_increment"],
        longitude_increment=u["longitude_increment"],
        latitude_scans_positive=u["latitude_scans_positive"],
        longitude_scans_negative=u["longitude_scans_negative"],
        u_values=u["values"],
        v_values=v["values"],
        source_mirror=source,
        retrieved_at=_utc(retrieved_at),
        checksum_sha256=checksum,
    )


class ECMWFOpenDataWindProvider:
    def __init__(
        self,
        *,
        model: str,
        resolution: str,
        u_parameter: str,
        v_parameter: str,
        maximum_retries: int,
        retry_initial_seconds: float,
        retry_max_seconds: float,
        total_timeout_seconds: float,
        max_download_bytes: int,
        client_factory: ClientFactory | None = None,
        decoder: Decoder = decode_ecmwf_wind_grib,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.model = model
        self.resolution = resolution
        self.parameters = [u_parameter, v_parameter]
        self.maximum_retries = maximum_retries
        self.retry_initial_seconds = retry_initial_seconds
        self.retry_max_seconds = retry_max_seconds
        self.total_timeout_seconds = total_timeout_seconds
        self.max_download_bytes = max_download_bytes
        self._client_factory = client_factory or self._make_client
        self._decoder = decoder
        self._now = now or (lambda: datetime.now(UTC))

    def _make_client(self, source: str) -> Any:
        client_class = _load_client_class()
        return client_class(
            source=source,
            model=self.model,
            resol=self.resolution,
            infer_stream_keyword=True,
            maximum_retries=self.maximum_retries,
            retry_after=(
                self.retry_initial_seconds,
                self.retry_max_seconds,
                2,
            ),
            use_server_retry_after=False,
        )

    def _discover_blocking(self, source: str) -> ECMWFCycleAvailability:
        with _ProviderLogGuard():
            client = self._client_factory(source)
            common = {
                "type": ECMWF_WIND_TYPE,
                "stream": ECMWF_WIND_STREAM,
                "param": self.parameters,
            }
            try:
                with performance_span("provider.latest_cycle"):
                    short = _as_utc_datetime(client.latest(step=0, **common))
                    long = _as_utc_datetime(client.latest(step=150, **common))
            except ECMWFWindError:
                raise
            except Exception as exc:
                raise ECMWFWindSourceUnavailableError(
                    "ECMWF cycle discovery is unavailable"
                ) from exc
        return ECMWFCycleAvailability(
            latest_short_cycle=short,
            latest_long_cycle=long,
            source=source,
            discovered_at=_utc(self._now()),
        )

    async def discover_cycles(self, source: str) -> ECMWFCycleAvailability:
        try:
            return await asyncio.wait_for(
                to_thread_timed(self._discover_blocking, source),
                timeout=self.total_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ECMWFWindSourceUnavailableError(
                "ECMWF cycle discovery timed out"
            ) from exc

    def _retrieve_blocking(
        self,
        source: str,
        forecast_reference_time: datetime,
        forecast_step_hours: int,
    ) -> ECMWFWindField:
        with _ProviderLogGuard():
            client = self._client_factory(source)
            with tempfile.TemporaryDirectory(prefix="orca-ecmwf-wind-") as directory:
                target = Path(directory) / "wind.grib2"
                try:
                    with performance_span("provider.grib_download"):
                        client.retrieve(
                            type=ECMWF_WIND_TYPE,
                            stream=ECMWF_WIND_STREAM,
                            param=self.parameters,
                            step=forecast_step_hours,
                            date=forecast_reference_time.strftime("%Y%m%d"),
                            time=forecast_reference_time.hour,
                            target=str(target),
                        )
                except Exception as exc:
                    if _provider_status_code(exc) in {400, 404}:
                        raise ECMWFWindStepUnavailableError(
                            "The requested ECMWF forecast step is unavailable"
                        ) from exc
                    raise ECMWFWindSourceUnavailableError(
                        "ECMWF wind source is unavailable"
                    ) from exc
                if not target.is_file() or target.stat().st_size == 0:
                    raise ECMWFWindCorruptDownloadError(
                        "ECMWF returned an empty wind forecast"
                    )
                if target.stat().st_size > self.max_download_bytes:
                    raise ECMWFWindDownloadTooLargeError(
                        "ECMWF wind response exceeded the configured size limit"
                    )
                with performance_span("provider.decode"):
                    field = self._decoder(target, source, forecast_step_hours, self._now())
                if field.forecast_reference_time != forecast_reference_time:
                    raise ECMWFWindCorruptDownloadError(
                        "ECMWF returned a different forecast cycle"
                    )
                return field

    async def retrieve_field(
        self,
        source: str,
        forecast_reference_time: datetime,
        forecast_step_hours: int,
    ) -> ECMWFWindField:
        try:
            return await asyncio.wait_for(
                to_thread_timed(
                    self._retrieve_blocking,
                    source,
                    forecast_reference_time,
                    forecast_step_hours,
                ),
                timeout=self.total_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ECMWFWindSourceUnavailableError(
                "ECMWF wind retrieval timed out"
            ) from exc
