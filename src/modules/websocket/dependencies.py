from fastapi import WebSocket

from src.modules.websocket.connection_manager import ConnectionManager


def get_connection_manager(websocket: WebSocket) -> ConnectionManager:
    manager: ConnectionManager = websocket.app.state.connection_manager
    return manager
