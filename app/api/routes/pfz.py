from fastapi import APIRouter, HTTPException, Query, Request, status

from app.clients.incois_pfz import PFZSourceUnavailableError
from app.parsers.pfz_html import PFZParseError
from app.schemas.pfz import PFZAdvisory


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
