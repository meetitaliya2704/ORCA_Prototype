from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.assessment import AssessmentRequest, MarineAssessmentResponse


router = APIRouter(prefix="/decision-support", tags=["decision-support"])


@router.post(
    "/assessment",
    response_model=MarineAssessmentResponse,
    responses={
        503: {
            "description": "Assessment service is not configured",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "ASSESSMENT_NOT_CONFIGURED",
                            "message": "Marine assessment is not configured",
                        }
                    }
                }
            },
        }
    },
)
async def assess_marine_conditions(
    payload: AssessmentRequest,
    request: Request,
) -> MarineAssessmentResponse:
    service = getattr(request.app.state, "assessment_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ASSESSMENT_NOT_CONFIGURED",
                "message": "Marine assessment is not configured",
            },
        )
    return await service.assess(payload)
