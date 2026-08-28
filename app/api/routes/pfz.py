from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.query_params import LatitudeQuery, LongitudeQuery
from app.clients.incois_pfz import PFZSourceUnavailableError
from app.parsers.pfz_html import NoSectorsDiscoveredError, PFZParseError
from app.schemas.pfz import (
    NearestPFZResponse,
    PFZAdvisory,
    PFZSnapshot,
    TimezoneAwareUTCDateTime,
)
from app.services.pfz import NoValidPFZError


router = APIRouter(prefix="/pfz", tags=["pfz"])


@router.get(
    "/preview",
    response_model=PFZAdvisory,
    responses={
        502: {
            "description": "INCOIS returned a page that could not be parsed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "INVALID_PFZ_RESPONSE",
                            "message": "Forecast date not found",
                        }
                    }
                }
            },
        },
        503: {
            "description": "INCOIS was unavailable after session retry",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "PFZ_SOURCE_UNAVAILABLE",
                            "message": "INCOIS PFZ data unavailable",
                        }
                    }
                }
            },
        },
    },
)
async def preview_pfz_sector(
    request: Request,
    sector_code: str = Query(pattern=r"^SEC\d{3}$"),
) -> PFZAdvisory:
    try:
        return await request.app.state.pfz_service.preview_sector(sector_code)
    except PFZSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PFZ_SOURCE_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except PFZParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "INVALID_PFZ_RESPONSE", "message": str(exc)},
        ) from exc


@router.get(
    "/snapshot",
    response_model=PFZSnapshot,
    responses={
        502: {
            "description": (
                "INCOIS returned no discoverable sectors or invalid PFZ content"
            ),
            "content": {
                "application/json": {
                    "examples": {
                        "no_sectors": {
                            "value": {
                                "detail": {
                                    "code": "NO_SECTORS_DISCOVERED",
                                    "message": (
                                        "INCOIS returned no discoverable PFZ sectors"
                                    ),
                                }
                            }
                        },
                        "invalid_content": {
                            "value": {
                                "detail": {
                                    "code": "INVALID_PFZ_RESPONSE",
                                    "message": "INCOIS PFZ response was invalid",
                                }
                            }
                        },
                    }
                }
            },
        },
        503: {
            "description": "INCOIS was unavailable with no cached fallback",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "SOURCE_UNAVAILABLE",
                            "message": "INCOIS PFZ source unavailable",
                        }
                    }
                }
            },
        },
    },
)
async def get_pfz_snapshot(request: Request) -> PFZSnapshot:
    try:
        return await request.app.state.pfz_snapshot_service.get_snapshot()
    except NoSectorsDiscoveredError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "NO_SECTORS_DISCOVERED",
                "message": "INCOIS returned no discoverable PFZ sectors",
            },
        ) from exc
    except PFZSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SOURCE_UNAVAILABLE",
                "message": "INCOIS PFZ source unavailable",
            },
        ) from exc
    except PFZParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_PFZ_RESPONSE",
                "message": "INCOIS PFZ response was invalid",
            },
        ) from exc


@router.get(
    "/nearest",
    response_model=NearestPFZResponse,
    responses={
        404: {
            "description": "No PFZ advisory is valid for the requested time",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "NO_VALID_PFZ",
                            "message": (
                                "No PFZ advisory is valid for the requested time"
                            ),
                        }
                    }
                }
            },
        },
        502: {
            "description": "INCOIS returned invalid PFZ content",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "INVALID_PFZ_RESPONSE",
                            "message": "INCOIS PFZ response was invalid",
                        }
                    }
                }
            },
        },
        503: {
            "description": "INCOIS was unavailable with no cached fallback",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "SOURCE_UNAVAILABLE",
                            "message": "INCOIS PFZ source unavailable",
                        }
                    }
                }
            },
        },
    },
)
async def get_nearest_pfz(
    request: Request,
    latitude: LatitudeQuery,
    longitude: LongitudeQuery,
    at: Annotated[TimezoneAwareUTCDateTime | None, Query()] = None,
) -> NearestPFZResponse:
    try:
        return await request.app.state.pfz_nearest_service.get_nearest(
            latitude=latitude,
            longitude=longitude,
            at=at,
        )
    except NoValidPFZError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_VALID_PFZ",
                "message": "No PFZ advisory is valid for the requested time",
            },
        ) from exc
    except NoSectorsDiscoveredError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "NO_SECTORS_DISCOVERED",
                "message": "INCOIS returned no discoverable PFZ sectors",
            },
        ) from exc
    except PFZSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SOURCE_UNAVAILABLE",
                "message": "INCOIS PFZ source unavailable",
            },
        ) from exc
    except PFZParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "INVALID_PFZ_RESPONSE",
                "message": "INCOIS PFZ response was invalid",
            },
        ) from exc
