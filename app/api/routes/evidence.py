from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.evidence import EvidenceRequest, MarineEvidenceResponse


router = APIRouter(prefix="/decision-support", tags=["decision-support"])


@router.post(
    "/evidence",
    response_model=MarineEvidenceResponse,
    responses={
        503: {
            "description": "Evidence aggregation is disabled",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "EVIDENCE_AGGREGATION_NOT_CONFIGURED",
                            "message": "Marine evidence aggregation is not enabled",
                        }
                    }
                }
            },
        }
    },
)
async def aggregate_marine_evidence(
    payload: EvidenceRequest,
    request: Request,
) -> MarineEvidenceResponse:
    service = getattr(request.app.state, "evidence_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EVIDENCE_AGGREGATION_NOT_CONFIGURED",
                "message": "Marine evidence aggregation is not enabled",
            },
        )
    return await service.aggregate(payload)
