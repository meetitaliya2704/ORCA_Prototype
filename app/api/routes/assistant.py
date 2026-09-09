from fastapi import APIRouter, HTTPException, Request, status

from app.agents.errors import AssistantExecutionError
from app.schemas.assistant import AssistantRequest, AssistantResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/query",
    response_model=AssistantResponse,
    responses={
        503: {
            "description": "Assistant or one of its required backend services is unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "ASSISTANT_NOT_CONFIGURED",
                            "message": "The ORCA assistant is not enabled",
                        }
                    }
                }
            },
        }
    },
)
async def query_assistant(
    payload: AssistantRequest,
    request: Request,
) -> AssistantResponse:
    service = getattr(request.app.state, "assistant_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ASSISTANT_NOT_CONFIGURED",
                "message": "The ORCA assistant is not enabled",
            },
        )
    try:
        return await service.query(payload)
    except AssistantExecutionError as exc:
        raise HTTPException(
            status_code=(
                exc.http_status
                or (
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if exc.retryable
                    else status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            ),
            detail={"code": exc.code, "message": str(exc)},
        ) from None
