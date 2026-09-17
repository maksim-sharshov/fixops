from collections import defaultdict

from fastapi import WebSocket


class EventManager:

    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.history: dict[str, list[dict]] = defaultdict(list)

    async def connect(
        self,
        job_id: str,
        websocket: WebSocket,
    ):
        await websocket.accept()

        self.connections[job_id].add(websocket)

        # Если какие-то события произошли до подключения frontend,
        # отправляем их сразу.
        for event in self.history.get(job_id, []):
            try:
                await websocket.send_json(event)
            except Exception:
                self.disconnect(job_id, websocket)
                break

    def disconnect(
        self,
        job_id: str,
        websocket: WebSocket,
    ):
        self.connections[job_id].discard(websocket)

        if not self.connections[job_id]:
            self.connections.pop(job_id, None)

    async def emit(
        self,
        job_id: str,
        event: str,
        **data,
    ):
        message = {
            "job_id": job_id,
            "event": event,
            **data,
        }

        # Сохраняем историю, чтобы frontend не потерял
        # первые события из-за race condition.
        self.history[job_id].append(message)

        # Ограничиваем историю.
        self.history[job_id] = self.history[job_id][-100:]

        dead_connections = []

        for websocket in list(
            self.connections.get(job_id, set())
        ):
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.append(websocket)

        for websocket in dead_connections:
            self.disconnect(job_id, websocket)


events = EventManager()
