import asyncio
import logging
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """In-process WebSocket registry keyed by project_id.

    Single-instance only. Multi-instance deployments would need a Redis
    pub/sub fan-out layer in front of this.
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, project_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(project_id, set()).add(websocket)
        logger.info("WS connected to project %s (total=%d)", project_id, len(self._connections[project_id]))

    async def disconnect(self, project_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(project_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    del self._connections[project_id]
        logger.info("WS disconnected from project %s", project_id)

    async def broadcast(self, project_id: UUID, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(project_id, set()))
        if not sockets:
            return

        broken: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                logger.warning("Failed to send to a WS for project %s, will drop", project_id)
                broken.append(ws)

        if broken:
            async with self._lock:
                sockets_set = self._connections.get(project_id)
                if sockets_set is not None:
                    for ws in broken:
                        sockets_set.discard(ws)
                    if not sockets_set:
                        self._connections.pop(project_id, None)

    def connection_count(self, project_id: UUID) -> int:
        return len(self._connections.get(project_id, set()))
