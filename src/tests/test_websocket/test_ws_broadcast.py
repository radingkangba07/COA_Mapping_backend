"""Unit tests for ConnectionManager broadcast / connect / disconnect."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.modules.websocket.connection_manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_registers_socket():
    manager = ConnectionManager()
    project_id = uuid4()
    ws = AsyncMock()

    await manager.connect(project_id, ws)

    ws.accept.assert_awaited_once()
    assert manager.connection_count(project_id) == 1


@pytest.mark.asyncio
async def test_disconnect_removes_socket_and_cleans_empty_set():
    manager = ConnectionManager()
    project_id = uuid4()
    ws = AsyncMock()

    await manager.connect(project_id, ws)
    await manager.disconnect(project_id, ws)

    assert manager.connection_count(project_id) == 0
    assert project_id not in manager._connections


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connected_sockets():
    manager = ConnectionManager()
    project_id = uuid4()
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await manager.connect(project_id, ws1)
    await manager.connect(project_id, ws2)

    payload = {"event": "job.status_changed", "status": "completed"}
    await manager.broadcast(project_id, payload)

    ws1.send_json.assert_awaited_once_with(payload)
    ws2.send_json.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_broadcast_skips_other_projects():
    manager = ConnectionManager()
    project_a = uuid4()
    project_b = uuid4()
    ws_a = AsyncMock()
    ws_b = AsyncMock()

    await manager.connect(project_a, ws_a)
    await manager.connect(project_b, ws_b)

    await manager.broadcast(project_a, {"event": "x"})

    ws_a.send_json.assert_awaited_once()
    ws_b.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_drops_broken_sockets():
    manager = ConnectionManager()
    project_id = uuid4()
    good = AsyncMock()
    broken = AsyncMock()
    broken.send_json.side_effect = RuntimeError("socket closed")

    await manager.connect(project_id, good)
    await manager.connect(project_id, broken)

    await manager.broadcast(project_id, {"event": "x"})

    assert good in manager._connections[project_id]
    assert broken not in manager._connections[project_id]
    assert manager.connection_count(project_id) == 1


@pytest.mark.asyncio
async def test_broadcast_no_sockets_is_noop():
    manager = ConnectionManager()
    project_id = uuid4()
    # should not raise even though no one is connected
    await manager.broadcast(project_id, {"event": "x"})
    assert manager.connection_count(project_id) == 0
