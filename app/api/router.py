from fastapi import APIRouter

from app.api.routes import (
    assistant,
    assessment,
    evidence,
    health,
    marine,
    pfz,
    pfz_journey,
    speech,
    websocket,
)


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(assistant.router)
api_router.include_router(speech.router)
api_router.include_router(assessment.router)
api_router.include_router(evidence.router)
api_router.include_router(marine.router)
api_router.include_router(pfz.router)
api_router.include_router(pfz_journey.router)
api_router.include_router(websocket.router)
