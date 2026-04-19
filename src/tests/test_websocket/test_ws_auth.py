"""Unit tests for WS auth helper."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.security import InvalidTokenError
from src.modules.websocket.auth import WSAuthError, authenticate_ws


@pytest.mark.asyncio
async def test_reject_without_token():
    with pytest.raises(WSAuthError) as exc_info:
        await authenticate_ws(None, uuid4(), db=MagicMock())
    assert exc_info.value.code == 4401
    assert "Missing token" in exc_info.value.reason


@pytest.mark.asyncio
async def test_reject_invalid_token():
    with (
        patch("src.modules.websocket.auth.decode_token", side_effect=InvalidTokenError("bad sig")),
        pytest.raises(WSAuthError) as exc_info,
    ):
        await authenticate_ws("bogus", uuid4(), db=MagicMock())
    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_reject_wrong_token_type():
    with (
        patch(
            "src.modules.websocket.auth.decode_token",
            return_value={"sub": str(uuid4()), "type": "refresh"},
        ),
        pytest.raises(WSAuthError) as exc_info,
    ):
        await authenticate_ws("refresh-token", uuid4(), db=MagicMock())
    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_reject_when_user_not_found():
    user_id = uuid4()
    with (
        patch(
            "src.modules.websocket.auth.decode_token",
            return_value={"sub": str(user_id), "type": "access"},
        ),
        patch("src.modules.websocket.auth.UserRepository") as user_repo_cls,
    ):
        user_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(WSAuthError) as exc_info:
            await authenticate_ws("tok", uuid4(), db=MagicMock())
    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_reject_no_project_access():
    user_id = uuid4()
    fake_user = MagicMock(id=user_id, is_active=True)
    with (
        patch(
            "src.modules.websocket.auth.decode_token",
            return_value={"sub": str(user_id), "type": "access"},
        ),
        patch("src.modules.websocket.auth.UserRepository") as user_repo_cls,
        patch("src.modules.websocket.auth.ProjectAccessRepository") as access_repo_cls,
    ):
        user_repo_cls.return_value.get_by_id = AsyncMock(return_value=fake_user)
        access_repo_cls.return_value.get_user_permission = AsyncMock(return_value=None)
        with pytest.raises(WSAuthError) as exc_info:
            await authenticate_ws("tok", uuid4(), db=MagicMock())
    assert exc_info.value.code == 4403


@pytest.mark.asyncio
async def test_accept_with_valid_token_and_access():
    user_id = uuid4()
    fake_user = MagicMock(id=user_id, is_active=True)
    fake_access = MagicMock(permission="editor")
    with (
        patch(
            "src.modules.websocket.auth.decode_token",
            return_value={"sub": str(user_id), "type": "access"},
        ),
        patch("src.modules.websocket.auth.UserRepository") as user_repo_cls,
        patch("src.modules.websocket.auth.ProjectAccessRepository") as access_repo_cls,
    ):
        user_repo_cls.return_value.get_by_id = AsyncMock(return_value=fake_user)
        access_repo_cls.return_value.get_user_permission = AsyncMock(return_value=fake_access)
        returned = await authenticate_ws("tok", uuid4(), db=MagicMock())
    assert returned is fake_user
