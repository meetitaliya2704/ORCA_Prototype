from fastapi import APIRouter

from app.api.routes import assessment, evidence, health, marine, pfz, websocket


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(assessment.router)
api_router.include_router(evidence.router)
api_router.include_router(marine.router)
api_router.include_router(pfz.router)
api_router.include_router(websocket.router)
