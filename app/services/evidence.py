from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from app.schemas.evidence import (
    EvidenceBundleStatus,
    EvidenceFailure,
    EvidenceItem,
    EvidenceRequest,
    EvidenceRequestMetadata,
    EvidenceSources,
    EvidenceState,
    EvidenceSummary,
    MarineEvidenceResponse,
)
from app.schemas.marine import RefreshAcceptedResponse
from app.services.chlorophyll import chlorophyll_error_code
from app.services.sst import sst_error_code
from app.services.waves import wave_error_code
from app.services.wind import wind_error_code
from app.services.wind_forecast import ecmwf_wind_error_code


SOURCE_NAMES = ("pfz", "sst", "chlorophyll", "waves", "wind", "currents", "sea_level")
NOTICE = "Decision-support information; not certified navigation advice."


class EvidenceSourceNotConfiguredError(RuntimeError):
    def __init__(self, code: str):
        super().__init__("Evidence source is not configured")
        self.code = code


ERROR_CODES_BY_TYPE = {
    # PFZ
    "NoValidPFZError": "NO_VALID_PFZ",
    "NoSectorsDiscoveredError": "NO_SECTORS_DISCOVERED",
    "PFZSourceUnavailableError": "PFZ_SOURCE_UNAVAILABLE",
    "PFZParseError": "INVALID_PFZ_RESPONSE",
    # Currents
    "InvalidCurrentTimeError": "INVALID_CURRENT_TIME",
    "CurrentDataUnavailableError": "CURRENT_DATA_UNAVAILABLE",
    "NoValidCurrentCellError": "NO_VALID_CURRENT_CELL",
    "CurrentForecastOutOfHorizonError": "CURRENT_FORECAST_OUT_OF_HORIZON",
    "CurrentTimeUnavailableError": "CURRENT_TIME_UNAVAILABLE",
    "InvalidCurrentResponseError": "INVALID_CURRENT_RESPONSE",
    "CurrentDependencyMissingError": "CURRENT_DEPENDENCY_MISSING",
    "CurrentAuthenticationError": "CURRENT_AUTHENTICATION_FAILED",
    "CurrentSourceNotConfiguredError": "CURRENT_SOURCE_NOT_CONFIGURED",
    "CurrentSourceUnavailableError": "CURRENT_SOURCE_UNAVAILABLE",
    # Sea level
    "InvalidTideTimeError": "INVALID_TIDE_TIME",
    "TideDataUnavailableError": "TIDE_DATA_UNAVAILABLE",
    "TideForecastOutOfHorizonError": "TIDE_FORECAST_OUT_OF_HORIZON",
    "TideTimeUnavailableError": "TIDE_TIME_UNAVAILABLE",
    "NoValidTideCellError": "NO_VALID_TIDE_CELL",
    "StaticGridAlignmentError": "STATIC_GRID_ALIGNMENT_FAILED",
    "InvalidTideResponseError": "INVALID_TIDE_RESPONSE",
    "TideDependencyMissingError": "TIDE_DEPENDENCY_MISSING",
    "TideAuthenticationError": "TIDE_AUTHENTICATION_FAILED",
    "TideSourceNotConfiguredError": "TIDE_SOURCE_NOT_CONFIGURED",
    "StaticMaskUnavailableError": "STATIC_MASK_UNAVAILABLE",
    "TideSourceUnavailableError": "TIDE_SOURCE_UNAVAILABLE",
}

NOT_CONFIGURED_CODES = {
    "pfz": "PFZ_SOURCE_NOT_CONFIGURED",
    "sst": "SST_SOURCE_NOT_CONFIGURED",
    "chlorophyll": "CHLOROPHYLL_SOURCE_NOT_CONFIGURED",
    "waves": "WAVE_SOURCE_NOT_CONFIGURED",
    "wind_recent": "WIND_SOURCE_NOT_CONFIGURED",
    "wind_forecast": "ECMWF_FORECAST_NOT_CONFIGURED",
    "currents": "CURRENT_SOURCE_NOT_CONFIGURED",
    "sea_level": "TIDE_SOURCE_NOT_CONFIGURED",
}

FAILURE_MESSAGES = {
    "pfz": "PFZ evidence is unavailable",
    "sst": "SST evidence is unavailable",
    "chlorophyll": "Chlorophyll evidence is unavailable",
    "waves": "Wave evidence is unavailable",
    "wind": "Wind evidence is unavailable",
    "currents": "Current evidence is unavailable",
    "sea_level": "Sea-level evidence is unavailable",
}

NON_RETRYABLE_MARKERS = (
    "NOT_CONFIGURED",
    "DEPENDENCY_MISSING",
    "AUTHENTICATION_FAILED",
    "INVALID_",
    "NO_VALID_",
    "OUT_OF_HORIZON",
    "TIME_UNAVAILABLE",
    "DATA_UNAVAILABLE",
    "DATA_TOO_OLD",
    "STEP_UNAVAILABLE",
)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _is_degraded(source: str, value: Any) -> bool:
    if _enum_value(getattr(value, "cache_status", None)) == "stale":
        return True
    snapshot = getattr(value, "snapshot", None)
    if snapshot is not None and _enum_value(snapshot.status) in {
        "stale", "stale_refreshing"
    }:
        return True
    if source == "pfz":
        return _enum_value(getattr(value, "completeness", None)) == "partial"
    if source == "chlorophyll":
        quality = getattr(value, "quality", None)
        return _enum_value(getattr(quality, "evidence_quality", None)) == "degraded"
    if source == "currents":
        return (
            _enum_value(getattr(value, "evidence_quality", None)) == "degraded"
            or getattr(value, "decomposition_complete", True) is False
        )
    if source == "sea_level":
        return any(
            _enum_value(getattr(value, field, None)) == "degraded"
            for field in (
                "model_evidence_quality",
                "spatial_representativeness",
                "decomposition_evidence_quality",
            )
        )
    if source == "wind":
        return _enum_value(getattr(value, "freshness", None)) == "stale_cycle"
    return False


def _error_code(source: str, exc: Exception, *, future_wind: bool) -> str:
    if isinstance(exc, EvidenceSourceNotConfiguredError):
        return exc.code
    if source == "sst":
        return sst_error_code(exc)
    if source == "chlorophyll":
        return chlorophyll_error_code(exc)
    if source == "waves":
        return wave_error_code(exc)
    if source == "wind":
        return ecmwf_wind_error_code(exc) if future_wind else wind_error_code(exc)
    return ERROR_CODES_BY_TYPE.get(type(exc).__name__, f"{source.upper()}_SOURCE_UNAVAILABLE")


class MarineEvidenceService:
    def __init__(
        self,
        *,
        pfz_service=None,
        sst_service=None,
        sst_snapshot_manager=None,
        chlorophyll_service=None,
        chlorophyll_snapshot_manager=None,
        wave_service=None,
        recent_wind_service=None,
        forecast_wind_service=None,
        current_service=None,
        sea_level_service=None,
        fallback_services: dict[str, Any] | None = None,
        source_timeout_seconds: float = 3.0,
        max_concurrent_sources: int = 7,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.pfz_service = pfz_service
        self.sst_service = sst_service
        self.sst_snapshot_manager = sst_snapshot_manager
        self.chlorophyll_service = chlorophyll_service
        self.chlorophyll_snapshot_manager = chlorophyll_snapshot_manager
        self.wave_service = wave_service
        self.recent_wind_service = recent_wind_service
        self.forecast_wind_service = forecast_wind_service
        self.current_service = current_service
        self.sea_level_service = sea_level_service
        self.fallback_services = fallback_services or {}
        self.source_timeout_seconds = source_timeout_seconds
        self.max_concurrent_sources = max_concurrent_sources
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence time must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _require(service: Any, source: str) -> Any:
        if service is None:
            raise EvidenceSourceNotConfiguredError(NOT_CONFIGURED_CODES[source])
        return service

    async def _call(
        self,
        source: str,
        latitude: float,
        longitude: float,
        at: datetime,
        comparison_now: datetime,
    ) -> Any:
        fallback = self.fallback_services.get(source)

        async def _invoke_primary() -> Any:
            if source == "pfz":
                service = self._require(self.pfz_service, "pfz")
                return await service.get_nearest(latitude=latitude, longitude=longitude, at=at)
            if source == "sst":
                if self.sst_snapshot_manager is not None:
                    res = await self.sst_snapshot_manager.get_sst(
                        latitude=latitude, longitude=longitude, at=at
                    )
                    if isinstance(res, RefreshAcceptedResponse) and fallback is not None:
                        return await _invoke_fallback()
                    return res
                service = self._require(self.sst_service, "sst")
                return await service.get_sst(latitude=latitude, longitude=longitude, at=at)
            if source == "chlorophyll":
                if self.chlorophyll_snapshot_manager is not None:
                    res = await self.chlorophyll_snapshot_manager.get_chlorophyll(
                        latitude=latitude, longitude=longitude, at=at
                    )
                    if isinstance(res, RefreshAcceptedResponse) and fallback is not None:
                        return await _invoke_fallback()
                    return res
                service = self._require(self.chlorophyll_service, "chlorophyll")
                return await service.get_chlorophyll(
                    latitude=latitude, longitude=longitude, at=at
                )
            if source == "waves":
                service = self._require(self.wave_service, "waves")
                return await service.get_waves(latitude=latitude, longitude=longitude, at=at)
            if source == "wind":
                if at > comparison_now:
                    service = self._require(self.forecast_wind_service, "wind_forecast")
                    return await service.get_forecast(
                        latitude=latitude, longitude=longitude, at=at
                    )
                service = self._require(self.recent_wind_service, "wind_recent")
                return await service.get_wind(latitude=latitude, longitude=longitude, at=at)
            if source == "currents":
                service = self._require(self.current_service, "currents")
                return await service.get_current(latitude=latitude, longitude=longitude, at=at)
            service = self._require(self.sea_level_service, "sea_level")
            return await service.get_sea_level(latitude=latitude, longitude=longitude, at=at)

        async def _invoke_fallback() -> Any:
            if fallback is None:
                raise EvidenceSourceNotConfiguredError(NOT_CONFIGURED_CODES.get(source, f"{source.upper()}_SOURCE_NOT_CONFIGURED"))
            if source == "pfz":
                return await fallback.get_nearest(latitude=latitude, longitude=longitude, at=at)
            if source == "sst":
                return await fallback.get_sst(latitude=latitude, longitude=longitude, at=at)
            if source == "chlorophyll":
                return await fallback.get_chlorophyll(latitude=latitude, longitude=longitude, at=at)
            if source == "waves":
                return await fallback.get_waves(latitude=latitude, longitude=longitude, at=at)
            if source == "wind":
                if at > comparison_now and hasattr(fallback, "get_forecast"):
                    return await fallback.get_forecast(latitude=latitude, longitude=longitude, at=at)
                if hasattr(fallback, "get_wind"):
                    return await fallback.get_wind(latitude=latitude, longitude=longitude, at=at)
                return await fallback.get_forecast(latitude=latitude, longitude=longitude, at=at)
            if source == "currents":
                return await fallback.get_current(latitude=latitude, longitude=longitude, at=at)
            if source == "sea_level":
                return await fallback.get_sea_level(latitude=latitude, longitude=longitude, at=at)
            return await fallback.get_sea_level(latitude=latitude, longitude=longitude, at=at)

        if fallback is not None:
            # Check if primary is unconfigured
            if source == "sst" and self.sst_service is None and self.sst_snapshot_manager is None:
                return await _invoke_fallback()
            if source == "chlorophyll" and self.chlorophyll_service is None and self.chlorophyll_snapshot_manager is None:
                return await _invoke_fallback()
            if source == "waves" and self.wave_service is None:
                return await _invoke_fallback()
            if source == "wind" and (self.recent_wind_service is None and self.forecast_wind_service is None):
                return await _invoke_fallback()
            if source == "currents" and self.current_service is None:
                return await _invoke_fallback()
            if source == "sea_level" and self.sea_level_service is None:
                return await _invoke_fallback()

            try:
                async with asyncio.timeout(self.source_timeout_seconds):
                    return await _invoke_primary()
            except Exception:
                return await _invoke_fallback()

        return await _invoke_primary()

    async def aggregate(self, request: EvidenceRequest) -> MarineEvidenceResponse:
        comparison_now = self._utc(self._now())
        request_time = self._utc(request.at) if request.at is not None else comparison_now
        requested = {
            "pfz": request.include_pfz,
            "sst": request.include_sst,
            "chlorophyll": request.include_chlorophyll,
            "waves": request.include_waves,
            "wind": request.include_wind,
            "currents": request.include_currents,
            "sea_level": request.include_sea_level,
        }
        semaphore = asyncio.Semaphore(self.max_concurrent_sources)

        async def bounded(source: str) -> Any:
            async with semaphore:
                return await self._call(
                    source,
                    request.latitude,
                    request.longitude,
                    request_time,
                    comparison_now,
                )

        active_names = [name for name in SOURCE_NAMES if requested[name]]
        raw_results = await asyncio.gather(
            *(bounded(name) for name in active_names), return_exceptions=True
        )
        result_by_name = dict(zip(active_names, raw_results, strict=True))
        items: dict[str, EvidenceItem[Any]] = {}
        failures: list[EvidenceFailure] = []
        future_wind = request_time > comparison_now

        for source in SOURCE_NAMES:
            if not requested[source]:
                items[source] = EvidenceItem(state=EvidenceState.NOT_REQUESTED)
                continue
            result = result_by_name[source]
            if isinstance(result, RefreshAcceptedResponse):
                items[source] = EvidenceItem(state=EvidenceState.PENDING)
                failures.append(EvidenceFailure(
                    source=source,
                    state="pending",
                    code=result.code,
                    message=f"{source.replace('_', ' ').title()} evidence refresh is in progress",
                    retryable=True,
                    retry_after_seconds=result.retry_after_seconds,
                    refresh_job_id=result.job_id,
                ))
                continue
            if isinstance(result, BaseException):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                code = _error_code(source, result, future_wind=future_wind)
                retry_after = getattr(result, "retry_after_seconds", None)
                retryable = not any(marker in code for marker in NON_RETRYABLE_MARKERS)
                failures.append(EvidenceFailure(
                    source=source,
                    state="unavailable",
                    code=code,
                    message=FAILURE_MESSAGES[source],
                    retryable=retryable,
                    retry_after_seconds=(
                        retry_after if isinstance(retry_after, int) and retry_after > 0 else None
                    ),
                ))
                items[source] = EvidenceItem(state=EvidenceState.UNAVAILABLE)
                continue
            state = EvidenceState.DEGRADED if _is_degraded(source, result) else EvidenceState.AVAILABLE
            items[source] = EvidenceItem(state=state, data=result)

        requested_count = len(active_names)
        available_count = sum(item.state == EvidenceState.AVAILABLE for item in items.values())
        degraded_count = sum(item.state == EvidenceState.DEGRADED for item in items.values())
        pending_count = sum(item.state == EvidenceState.PENDING for item in items.values())
        unavailable_count = sum(item.state == EvidenceState.UNAVAILABLE for item in items.values())
        usable_count = available_count + degraded_count
        status = (
            EvidenceBundleStatus.COMPLETE
            if usable_count == requested_count
            else EvidenceBundleStatus.UNAVAILABLE
            if usable_count == 0
            else EvidenceBundleStatus.PARTIAL
        )
        return MarineEvidenceResponse(
            request=EvidenceRequestMetadata(
                latitude=request.latitude,
                longitude=request.longitude,
                at=request_time,
            ),
            generated_at=self._utc(self._now()),
            status=status,
            summary=EvidenceSummary(
                requested_sources=requested_count,
                available_sources=available_count,
                unavailable_sources=unavailable_count,
                degraded_sources=degraded_count,
                pending_sources=pending_count,
            ),
            evidence=EvidenceSources.model_validate(items),
            failures=failures,
            notices=[NOTICE],
        )
