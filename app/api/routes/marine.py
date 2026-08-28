from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.query_params import LatitudeQuery, LongitudeQuery
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
from app.schemas.marine import (
    MarineConditionsResponse,
    SSTQueryTime,
    SSTResponse,
    WaveResponse,
)
from app.services.sst import NoValidSSTError
from app.services.waves import NoValidWaveDataError, NoWaveTimeAvailableError


router = APIRouter(prefix="/marine", tags=["marine"])


@router.get("/conditions", response_model=MarineConditionsResponse)
async def get_conditions(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
) -> MarineConditionsResponse:
    return await request.app.state.marine_service.get_conditions(
        latitude,
        longitude,
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
