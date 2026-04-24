import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.websocket.auth import WSAuthError, authenticate_ws
from src.modules.websocket.connection_manager import ConnectionManager
from src.modules.websocket.dependencies import get_connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])


@router.websocket("/jobs/project/{project_id}")
async def ws_jobs(
    websocket: WebSocket,
    project_id: UUID,
    token: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    try:
        await authenticate_ws(token, project_id, db)
    except WSAuthError as exc:
        await websocket.close(code=exc.code, reason=exc.reason)
        return

    await manager.connect(project_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("WS client sent non-JSON frame on project %s", project_id)
                continue
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS error for project %s", project_id)
    finally:
        await manager.disconnect(project_id, websocket)
