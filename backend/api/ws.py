# api/ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.events import events

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str):
    await events.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()   # нужно только чтобы поймать disconnect
    except WebSocketDisconnect:
        events.disconnect(job_id, websocket)
