from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.events import events

router = APIRouter()


# Клиенты, которые ждут появления новых jobs
global_connections: set[WebSocket] = set()


@router.websocket("/ws")
async def global_ws(websocket: WebSocket):
    await websocket.accept()

    global_connections.add(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        global_connections.discard(websocket)


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(
    websocket: WebSocket,
    job_id: str,
):
    await events.connect(
        job_id,
        websocket,
    )

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        events.disconnect(
            job_id,
            websocket,
        )


async def notify_job_started(job_id: str, container_id: str):
    """Сообщает frontend о создании нового job."""

    message = {
            "event": "job_started",
            "job_id": job_id,
            "container_id": container_id,
        }

    dead_connections = []

    for websocket in list(global_connections):
        try:
            await websocket.send_json(message)

        except Exception:
            dead_connections.append(websocket)

    for websocket in dead_connections:
        global_connections.discard(websocket)
