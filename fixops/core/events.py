from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class EventManager:

    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(
        self,
        job_id: str,
        websocket: WebSocket,
    ):
        await websocket.accept()

        self.connections[job_id].add(websocket)

    def disconnect(
        self,
        job_id: str,
        websocket: WebSocket,
    ):
        if job_id in self.connections:
            self.connections[job_id].discard(websocket)

            if not self.connections[job_id]:
                del self.connections[job_id]

    async def emit(
        self,
        job_id: str,
        event_type: str,
        **data: Any,
    ):
        message = {
            "type": event_type,
            **data,
        }

        connections = self.connections.get(job_id, set())

        dead_connections = []

        for websocket in connections:
            try:
                await websocket.send_json(message)

            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(job_id, websocket)


events = EventManager()
