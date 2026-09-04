from fastapi import APIRouter, HTTPException, Request, Response, status

from app.schemas.pfz_journey import (
    JourneyStatus,
    PFZJourneyRequest,
    PFZJourneyResponse,
)


router = APIRouter(prefix="/decision-support", tags=["decision-support"])


@router.post(
    "/pfz-journey",
    response_model=PFZJourneyResponse,
    responses={
        202: {
            "model": PFZJourneyResponse,
            "description": "PFZ refresh is genuinely in progress",
        },
        503: {
            "description": "Journey orchestration is not configured",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "PFZ_JOURNEY_NOT_CONFIGURED",
                            "message": "PFZ journey support is not configured",
                        }
                    }
                }
            },
        },
    },
)
async def run_pfz_journey(
    payload: PFZJourneyRequest,
    request: Request,
    response: Response,
) -> PFZJourneyResponse:
    service = getattr(request.app.state, "pfz_journey_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PFZ_JOURNEY_NOT_CONFIGURED",
                "message": "PFZ journey support is not configured",
            },
        )
    result = await service.run(payload)
    if result.journey_status == JourneyStatus.PFZ_REFRESH_PENDING:
        response.status_code = status.HTTP_202_ACCEPTED
    return result
