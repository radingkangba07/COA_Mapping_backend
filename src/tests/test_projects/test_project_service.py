"""Unit tests for ProjectService.create_project_full savepoint behaviour."""

import logging
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.projects.service import ProjectService

_ERP_SERVICE_PATH = "src.modules.erp.dependencies.get_erp_service"
_NEXT_SEQ_PATH = (
    "src.modules.workstreams.repository.WorkstreamRepository.next_display_seq"
)
_CREATE_STAGES_PATH = (
    "src.modules.workstreams.repository.WorkstreamRepository.create_with_stages"
)


def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    return user


def _make_project(org_id=None):
    project = MagicMock()
    project.id = uuid.uuid4()
    project.name = "Test Project"
    project.org_id = org_id or uuid.uuid4()
    return project


def _make_category(slug: str, display_code_prefix: str = "MD"):
    cat = MagicMock()
    cat.id = uuid.uuid4()
    cat.slug = slug
    cat.display_code_prefix = display_code_prefix
    return cat


def _make_session(categories=None):
    """Build an AsyncMock session that yields the given categories on execute()."""
    session = AsyncMock()

    @asynccontextmanager
    async def _begin_nested():
        yield

    session.begin_nested = _begin_nested

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = categories or []
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    return session


def _make_data(org_id):
    """Minimal ProjectCreateFull-like object with chart-of-accounts selected."""
    data = MagicMock()
    data.org_id = org_id
    data.name = "Test Project"
    data.description = None
    data.source_product_id = None
    data.target_product_id = None
    data.source_connection_method_id = None
    data.target_connection_method_id = None
    data.source_vendor_id = None
    data.target_vendor_id = None
    data.mcp_connection_config = None
    data.action = "create"
    data.members = []

    sel = MagicMock()
    sel.data_type = "chart-of-accounts"
    sel.selected = True
    data.master_data_selections = [sel]
    data.opening_balance_selections = []

    return data


def _null_erp_service():
    return MagicMock(
        get_system=lambda _: None,
        get_connection_method=lambda _: None,
    )


@pytest.mark.asyncio
async def test_create_project_full_returns_project_when_workstream_fails():
    """Outer transaction is preserved even if create_with_stages raises."""
    org_id = uuid.uuid4()
    project = _make_project(org_id)
    category = _make_category("master_data")
    session = _make_session(categories=[category])

    project_repo = AsyncMock()
    project_repo.create_project = AsyncMock(return_value=project)
    access_repo = AsyncMock()
    access_repo.grant = AsyncMock()

    service = ProjectService(
        project_repo=project_repo,
        access_repo=access_repo,
        session=session,
    )

    with (
        patch(_ERP_SERVICE_PATH, return_value=_null_erp_service()),
        patch(_NEXT_SEQ_PATH, new_callable=AsyncMock, return_value=1),
        patch(
            _CREATE_STAGES_PATH,
            new_callable=AsyncMock,
            side_effect=RuntimeError("schema mismatch"),
        ),
    ):
        result = await service.create_project_full(_make_data(org_id), _make_user())

    assert result is project


@pytest.mark.asyncio
async def test_create_project_full_logs_error_with_exception_type_on_failure(caplog):
    """Exception is logged at ERROR level and includes the exception class name."""
    org_id = uuid.uuid4()
    project = _make_project(org_id)
    category = _make_category("master_data")
    session = _make_session(categories=[category])

    project_repo = AsyncMock()
    project_repo.create_project = AsyncMock(return_value=project)
    access_repo = AsyncMock()
    access_repo.grant = AsyncMock()

    service = ProjectService(
        project_repo=project_repo,
        access_repo=access_repo,
        session=session,
    )

    with (
        caplog.at_level(logging.ERROR, logger="src.modules.projects.service"),
        patch(_ERP_SERVICE_PATH, return_value=_null_erp_service()),
        patch(_NEXT_SEQ_PATH, new_callable=AsyncMock, return_value=1),
        patch(
            _CREATE_STAGES_PATH,
            new_callable=AsyncMock,
            side_effect=ValueError("bad weight"),
        ),
    ):
        await service.create_project_full(_make_data(org_id), _make_user())

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1
    assert "ValueError" in error_records[0].message


@pytest.mark.asyncio
async def test_create_project_full_does_not_create_workstream_when_category_missing():
    """When the category slug is absent from the DB, no workstream is attempted."""
    org_id = uuid.uuid4()
    project = _make_project(org_id)
    session = _make_session(categories=[])  # no categories returned

    project_repo = AsyncMock()
    project_repo.create_project = AsyncMock(return_value=project)
    access_repo = AsyncMock()
    access_repo.grant = AsyncMock()

    service = ProjectService(
        project_repo=project_repo,
        access_repo=access_repo,
        session=session,
    )

    with (
        patch(_ERP_SERVICE_PATH, return_value=_null_erp_service()),
        patch(_CREATE_STAGES_PATH, new_callable=AsyncMock) as mock_create,
    ):
        result = await service.create_project_full(_make_data(org_id), _make_user())

    assert result is project
    mock_create.assert_not_called()
