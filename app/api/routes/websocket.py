import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/ingestion")
async def ingestion_progress(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        for progress, stage in (
            (10, "starting"),
            (35, "fetching_sources"),
            (65, "validating"),
            (90, "saving"),
            (100, "completed"),
        ):
            await websocket.send_json(
                {"progress": progress, "stage": stage}
            )
            await asyncio.sleep(0.2)

        await websocket.close()
    except WebSocketDisconnect:
        return

