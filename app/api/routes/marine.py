from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.query_params import LatitudeQuery, LongitudeQuery
from app.clients.copernicus_chlorophyll import (
    ChlorophyllAuthenticationError,
    ChlorophyllDependencyMissingError,
    ChlorophyllSourceNotConfiguredError,
    ChlorophyllSourceUnavailableError,
    InvalidChlorophyllResponseError,
)
from app.clients.copernicus_currents import (
    CurrentAuthenticationError,
    CurrentDependencyMissingError,
    CurrentSourceNotConfiguredError,
    CurrentSourceUnavailableError,
    InvalidCurrentResponseError,
)
from app.clients.copernicus_sst import (
    InvalidSSTResponseError,
    SSTAuthenticationError,
    SSTSourceNotConfiguredError,
    SSTSourceUnavailableError,
)
from app.clients.copernicus_waves import (
    InvalidWaveResponseError,
    WaveAuthenticationError,
    WaveSourceNotConfiguredError,
    WaveSourceUnavailableError,
)
from app.clients.copernicus_wind import (
    InvalidWindResponseError,
    WindAuthenticationError,
    WindSourceNotConfiguredError,
    WindSourceUnavailableError,
)
from app.clients.ecmwf_wind import (
    ECMWFWindCycleUnavailableError,
    ECMWFWindDataNotFoundError,
    ECMWFWindDependencyMissingError,
    ECMWFWindDownloadTooLargeError,
    ECMWFWindForecastOutOfRangeError,
    ECMWFWindSourceUnavailableError,
    ECMWFWindStepUnavailableError,
    InvalidECMWFWindResponseError,
)
from app.schemas.marine import (
    ChlorophyllResponse,
    CurrentResponse,
    MarineConditionsResponse,
    ECMWFWindForecastResponse,
    SSTQueryTime,
    SSTResponse,
    WaveResponse,
    WindResponse,
)
from app.services.chlorophyll import (
    ChlorophyllDataUnavailableError,
    InvalidChlorophyllTimeError,
    NoValidChlorophyllCellError,
)
from app.services.currents import (
    CurrentDataUnavailableError,
    CurrentForecastOutOfHorizonError,
    CurrentTimeUnavailableError,
    InvalidCurrentTimeError,
    NoValidCurrentCellError,
)
from app.services.sst import NoValidSSTError
from app.services.waves import NoValidWaveDataError, NoWaveTimeAvailableError
from app.services.wind import (
    NoValidWindDataError,
    NoWindForecastAvailableError,
    WindDataTooOldError,
)
from app.services.wind_forecast import ECMWFWindPastRequestError


router = APIRouter(prefix="/marine", tags=["marine"])


@router.get("/conditions", response_model=MarineConditionsResponse)
async def get_conditions(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> MarineConditionsResponse:
    return await request.app.state.marine_service.get_conditions(
        latitude,
        longitude,
        at,
    )


@router.get(
    "/sst",
    response_model=SSTResponse,
    responses={
        404: {"description": "No valid SST cell exists within the search radius"},
        502: {"description": "Copernicus returned an invalid SST response"},
        503: {"description": "Copernicus SST is unavailable or not configured"},
    },
)
async def get_sst(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> SSTResponse:
    service = request.app.state.sst_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SST_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus SST is not enabled",
            },
        )
    try:
        return await service.get_sst(
            latitude=latitude,
            longitude=longitude,
            at=at,
        )
    except NoValidSSTError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_SST",
                "message": "No valid SST cell exists within the configured radius",
            },
        ) from exc
    except InvalidSSTResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_SST_RESPONSE",
                "message": "Copernicus returned an invalid SST response",
            },
        ) from exc
    except SSTAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SST_AUTHENTICATION_FAILED",
                "message": (
                    "Copernicus Marine credentials are missing or invalid"
                ),
            },
        ) from exc
    except SSTSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SST_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus SST integration is not configured",
            },
        ) from exc
    except SSTSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SST_SOURCE_UNAVAILABLE",
                "message": "Copernicus Marine SST source is unavailable",
            },
        ) from exc


@router.get(
    "/chlorophyll",
    response_model=ChlorophyllResponse,
    responses={
        404: {"description": "No current valid chlorophyll cell is available"},
        422: {"description": "Coordinates or chlorophyll time are invalid"},
        502: {"description": "Copernicus returned invalid chlorophyll data"},
        503: {"description": "Copernicus chlorophyll support is unavailable"},
    },
)
async def get_chlorophyll(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> ChlorophyllResponse:
    service = request.app.state.chlorophyll_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHLOROPHYLL_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus chlorophyll is not enabled",
            },
        )
    try:
        return await service.get_chlorophyll(
            latitude=latitude,
            longitude=longitude,
            at=at,
        )
    except InvalidChlorophyllTimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_CHLOROPHYLL_TIME",
                "message": "Chlorophyll requests cannot use a future time",
            },
        ) from exc
    except ChlorophyllDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CHLOROPHYLL_DATA_UNAVAILABLE",
                "message": "No sufficiently fresh chlorophyll analysis is available",
            },
        ) from exc
    except NoValidChlorophyllCellError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_CHLOROPHYLL_CELL",
                "message": (
                    "No valid chlorophyll water cell exists within the configured radius"
                ),
            },
        ) from exc
    except InvalidChlorophyllResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_CHLOROPHYLL_RESPONSE",
                "message": "Copernicus returned an invalid chlorophyll response",
            },
        ) from exc
    except ChlorophyllDependencyMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHLOROPHYLL_DEPENDENCY_MISSING",
                "message": "Optional Copernicus Marine packages are not installed",
            },
        ) from exc
    except ChlorophyllAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHLOROPHYLL_AUTHENTICATION_FAILED",
                "message": "Copernicus Marine credentials are missing or invalid",
            },
        ) from exc
    except ChlorophyllSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHLOROPHYLL_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus chlorophyll integration is not configured",
            },
        ) from exc
    except ChlorophyllSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CHLOROPHYLL_SOURCE_UNAVAILABLE",
                "message": "Copernicus Marine chlorophyll source is unavailable",
            },
        ) from exc


@router.get(
    "/currents",
    response_model=CurrentResponse,
    responses={
        404: {"description": "No valid current cell or provider time is available"},
        422: {"description": "Coordinates or current time are invalid"},
        502: {"description": "Copernicus returned invalid current data"},
        503: {"description": "Copernicus current support is unavailable"},
    },
)
async def get_currents(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> CurrentResponse:
    service = request.app.state.current_service
    if service is None:
        raise HTTPException(status_code=503, detail={"code":"CURRENT_SOURCE_NOT_CONFIGURED","message":"Copernicus currents are not enabled"})
    try:
        return await service.get_current(latitude=latitude,longitude=longitude,at=at)
    except InvalidCurrentTimeError as exc:
        raise HTTPException(status_code=422,detail={"code":"INVALID_CURRENT_TIME","message":"Current time must include a timezone offset"}) from exc
    except NoValidCurrentCellError as exc:
        raise HTTPException(status_code=404,detail={"code":"NO_VALID_CURRENT_CELL","message":"No valid current water cell exists within the configured radius"}) from exc
    except CurrentTimeUnavailableError as exc:
        raise HTTPException(status_code=404,detail={"code":"CURRENT_TIME_UNAVAILABLE","message":"No provider current timestamp satisfies the request"}) from exc
    except CurrentForecastOutOfHorizonError as exc:
        raise HTTPException(status_code=404,detail={"code":"CURRENT_FORECAST_OUT_OF_HORIZON","message":"Requested time exceeds the current forecast horizon"}) from exc
    except CurrentDataUnavailableError as exc:
        raise HTTPException(status_code=404,detail={"code":"CURRENT_DATA_UNAVAILABLE","message":"Current data is unavailable for the request"}) from exc
    except InvalidCurrentResponseError as exc:
        raise HTTPException(status_code=502,detail={"code":"INVALID_CURRENT_RESPONSE","message":"Copernicus returned an invalid current response"}) from exc
    except CurrentDependencyMissingError as exc:
        raise HTTPException(status_code=503,detail={"code":"CURRENT_DEPENDENCY_MISSING","message":"Optional Copernicus Marine packages are not installed"}) from exc
    except CurrentAuthenticationError as exc:
        raise HTTPException(status_code=503,detail={"code":"CURRENT_AUTHENTICATION_FAILED","message":"Copernicus Marine credentials are missing or invalid"}) from exc
    except CurrentSourceNotConfiguredError as exc:
        raise HTTPException(status_code=503,detail={"code":"CURRENT_SOURCE_NOT_CONFIGURED","message":"Copernicus current integration is not configured"}) from exc
    except CurrentSourceUnavailableError as exc:
        raise HTTPException(status_code=503,detail={"code":"CURRENT_SOURCE_UNAVAILABLE","message":"Copernicus Marine current source is unavailable"}) from exc


@router.get(
    "/waves",
    response_model=WaveResponse,
    responses={
        404: {"description": "No valid wave cell or timestamp is available"},
        502: {"description": "Copernicus returned an invalid wave response"},
        503: {"description": "Copernicus waves are unavailable or not configured"},
    },
)
async def get_waves(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> WaveResponse:
    service = request.app.state.wave_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WAVE_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus waves are not enabled",
            },
        )
    try:
        return await service.get_waves(
            latitude=latitude,
            longitude=longitude,
            at=at,
        )
    except NoValidWaveDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_WAVE_DATA",
                "message": "No valid wave data exists within the configured radius",
            },
        ) from exc
    except NoWaveTimeAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_WAVE_TIME_AVAILABLE",
                "message": "No wave model timestamp satisfies the requested time",
            },
        ) from exc
    except InvalidWaveResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_WAVE_RESPONSE",
                "message": "Copernicus returned an invalid wave response",
            },
        ) from exc
    except WaveAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WAVE_AUTHENTICATION_FAILED",
                "message": "Copernicus Marine credentials are missing or invalid",
            },
        ) from exc
    except WaveSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WAVE_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus wave integration is not configured",
            },
        ) from exc
    except WaveSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WAVE_SOURCE_UNAVAILABLE",
                "message": "Copernicus Marine wave source is unavailable",
            },
        ) from exc


@router.get(
    "/wind",
    response_model=WindResponse,
    responses={
        404: {"description": "No valid wind cell exists or forecasts were requested"},
        502: {"description": "Copernicus returned an invalid wind response"},
        503: {"description": "Copernicus wind is unavailable, stale, or not configured"},
    },
)
async def get_wind(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[SSTQueryTime | None, Query()] = None,
) -> WindResponse:
    service = request.app.state.wind_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WIND_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus wind is not enabled",
            },
        )
    try:
        return await service.get_wind(latitude=latitude, longitude=longitude, at=at)
    except NoValidWindDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_WIND_DATA",
                "message": "No valid wind data exists within the configured radius",
            },
        ) from exc
    except NoWindForecastAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_WIND_FORECAST_AVAILABLE",
                "message": "The near-real-time wind source does not provide forecasts",
            },
        ) from exc
    except InvalidWindResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_WIND_RESPONSE",
                "message": "Copernicus returned an invalid wind response",
            },
        ) from exc
    except WindAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WIND_AUTHENTICATION_FAILED",
                "message": "Copernicus Marine credentials are missing or invalid",
            },
        ) from exc
    except WindSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WIND_SOURCE_NOT_CONFIGURED",
                "message": "Copernicus wind integration is not configured",
            },
        ) from exc
    except WindDataTooOldError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WIND_DATA_TOO_OLD",
                "message": "Latest wind data exceeds ORCA's maximum age policy",
            },
        ) from exc
    except WindSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WIND_SOURCE_UNAVAILABLE",
                "message": "Copernicus Marine wind source is unavailable",
            },
        ) from exc


@router.get(
    "/wind/forecast",
    response_model=ECMWFWindForecastResponse,
    responses={
        404: {"description": "No compatible ECMWF forecast is available"},
        422: {"description": "Coordinates or forecast time are invalid"},
        502: {"description": "ECMWF returned an invalid forecast response"},
        503: {"description": "ECMWF forecast support is unavailable"},
    },
)
async def get_wind_forecast(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[
        SSTQueryTime,
        Query(description="Required future forecast time with timezone offset"),
    ],
) -> ECMWFWindForecastResponse:
    service = request.app.state.ecmwf_wind_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ECMWF_FORECAST_NOT_CONFIGURED",
                "message": "ECMWF wind forecast integration is not enabled",
            },
        )
    try:
        return await service.get_forecast(
            latitude=latitude,
            longitude=longitude,
            at=at,
        )
    except ECMWFWindPastRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_FORECAST_TIME",
                "message": "The ECMWF endpoint accepts future forecast times only",
            },
        ) from exc
    except ECMWFWindForecastOutOfRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "FORECAST_OUT_OF_HORIZON",
                "message": "Requested time exceeds the available IFS horizon",
            },
        ) from exc
    except ECMWFWindStepUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "FORECAST_STEP_UNAVAILABLE",
                "message": "No ECMWF forecast step satisfies the requested time",
            },
        ) from exc
    except ECMWFWindDataNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_WIND_CELL",
                "message": "No valid ECMWF wind component pair was found",
            },
        ) from exc
    except ECMWFWindDownloadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "ECMWF_WIND_DOWNLOAD_TOO_LARGE",
                "message": "ECMWF wind response exceeded the configured size limit",
            },
        ) from exc
    except InvalidECMWFWindResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_ECMWF_RESPONSE",
                "message": "ECMWF returned an invalid wind forecast response",
            },
        ) from exc
    except ECMWFWindDependencyMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ECMWF_DEPENDENCY_MISSING",
                "message": "Optional ECMWF wind forecast packages are not installed",
            },
        ) from exc
    except ECMWFWindCycleUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ECMWF_SOURCE_UNAVAILABLE",
                "message": "No completed ECMWF forecast cycle could be resolved",
            },
        ) from exc
    except ECMWFWindSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ECMWF_SOURCE_UNAVAILABLE",
                "message": "ECMWF wind forecast source is unavailable",
            },
        ) from exc
