from fastapi import APIRouter, Query, Request

from app.schemas.marine import MarineConditionsResponse


router = APIRouter(prefix="/marine", tags=["marine"])


@router.get("/conditions", response_model=MarineConditionsResponse)
async def get_conditions(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> MarineConditionsResponse:
    return await request.app.state.marine_service.get_conditions(
        latitude,
        longitude,
    )

