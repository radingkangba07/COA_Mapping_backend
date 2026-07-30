"""Unit tests for ItemProfileService — CSV ingestion pathway (DAB-33)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.core.exceptions import PayloadTooLargeError, ValidationError
from src.modules.item_profile.service import (
    ItemProfileService,
    _count_rows,
    _infer_column_type,
    _parse_csv,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**overrides) -> SimpleNamespace:
    defaults = {"id": uuid.uuid4(), "email": "test@example.com"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_service(*, store=None, publisher=None, run_repo=None):
    if run_repo is None:
        run_repo = AsyncMock()
        run_repo.create_run.return_value = SimpleNamespace(
            id=uuid.uuid4(), status="ingesting"
        )
    session = AsyncMock()
    return ItemProfileService(
        run_repo=run_repo,
        store=store,
        publisher=publisher,
        session=session,
    )


def _make_store(*, exists=True, size=100, data: bytes = b""):
    store = MagicMock()
    store.object_exists.return_value = exists
    store.get_object_size.return_value = size
    store.get_object.return_value = (data, "text/csv")
    return store


def _csv_bytes(*rows: str, header: str = "name,age,active") -> bytes:
    lines = [header, *list(rows)]
    return "\n".join(lines).encode()


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestInferColumnType:
    def test_string(self):
        s = pd.Series(["alice", "bob", "charlie"])
        assert _infer_column_type(s) == "string"

    def test_integer(self):
        s = pd.Series([1, 2, 3, None])
        assert _infer_column_type(s) == "integer"

    def test_decimal(self):
        s = pd.Series([1.5, 2.3, 3.7])
        assert _infer_column_type(s) == "decimal"

    def test_boolean(self):
        s = pd.Series(["true", "false", "True", "False"])
        assert _infer_column_type(s) == "boolean"

    def test_date(self):
        s = pd.Series(["2024-01-01", "2024-06-15", "2023-12-31"])
        assert _infer_column_type(s) == "date"

    def test_all_null(self):
        s = pd.Series([None, None])
        assert _infer_column_type(s) == "string"


class TestCountRows:
    def test_basic(self):
        raw = b"name,age\nalice,30\nbob,25\n"
        assert _count_rows(raw) == 2

    def test_no_trailing_newline(self):
        # header + 2 data rows, last row has no trailing newline
        raw = b"name,age\nalice,30\nbob,25"
        assert _count_rows(raw) == 2

    def test_empty(self):
        raw = b""
        assert _count_rows(raw) == 0


class TestParseCsv:
    def test_valid_utf8(self):
        raw = b"name,age\nalice,30\nbob,25\n"
        df = _parse_csv(raw)
        assert list(df.columns) == ["name", "age"]
        assert len(df) == 2

    def test_utf8_bom(self):
        raw = "﻿name,age\nalice,30\n".encode("utf-8-sig")
        df = _parse_csv(raw)
        assert "name" in df.columns

    def test_latin1_fallback(self):
        raw = "name,city\nalice,M\xe9xico\n".encode("latin-1")
        df = _parse_csv(raw)
        assert list(df.columns) == ["name", "city"]

    def test_empty_file_raises(self):
        with pytest.raises(ValidationError):
            _parse_csv(b"")

    def test_header_only_no_data_rows(self):
        # A CSV with only a header and no data rows is valid but empty
        df = _parse_csv(b"name,age\n")
        assert list(df.columns) == ["name", "age"]
        assert len(df) == 0


# ---------------------------------------------------------------------------
# Service: initiate_run
# ---------------------------------------------------------------------------

class TestInitiateRun:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        store = _make_store(exists=True, size=1024)
        service = _make_service(store=store)
        user = _make_user()
        project_id = uuid.uuid4()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as mock_repo,
        ):
            mock_repo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=project_id))
            result = await service.initiate_run(project_id, "uploads/test.csv", user)

        assert result["status"] == "ingesting"
        assert "run_id" in result

    @pytest.mark.asyncio
    async def test_file_not_found_raises_422(self):
        store = _make_store(exists=False)
        service = _make_service(store=store)
        user = _make_user()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as mock_repo,
        ):
            mock_repo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
            with pytest.raises(ValidationError, match="not found in storage"):
                await service.initiate_run(uuid.uuid4(), "uploads/missing.csv", user)

    @pytest.mark.asyncio
    async def test_oversized_file_raises_413(self):
        store = _make_store(exists=True, size=600 * 1024 * 1024)
        service = _make_service(store=store)
        user = _make_user()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as mock_repo,
        ):
            mock_repo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
            with pytest.raises(PayloadTooLargeError):
                await service.initiate_run(uuid.uuid4(), "uploads/huge.csv", user)

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self):
        store = _make_store(exists=True, size=1024)
        service = _make_service(store=store)
        user = _make_user()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as mock_repo,
        ):
            mock_repo.return_value.get_by_id = AsyncMock(return_value=None)
            from src.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                await service.initiate_run(uuid.uuid4(), "uploads/test.csv", user)


# ---------------------------------------------------------------------------
# Service: process_run
# ---------------------------------------------------------------------------

class TestProcessRun:
    @pytest.mark.asyncio
    async def test_valid_csv_transitions_to_profiling_pending(self):
        raw = _csv_bytes("alice,30,true", "bob,25,false")
        store = _make_store(data=raw)
        publisher = AsyncMock()
        run_repo = AsyncMock()
        service = _make_service(store=store, publisher=publisher, run_repo=run_repo)
        run_id = uuid.uuid4()
        project_id = uuid.uuid4()

        await service.process_run(run_id, project_id, "uploads/test.csv")

        call_kwargs = run_repo.update_run.call_args.kwargs
        assert call_kwargs["status"] == "profiling_pending"
        assert call_kwargs["field_count"] == 3
        assert call_kwargs["source_row_count"] == 2
        publisher.publish_run_created.assert_awaited_once_with(run_id, project_id)

    @pytest.mark.asyncio
    async def test_empty_file_transitions_to_failed(self):
        store = _make_store(data=b"")
        run_repo = AsyncMock()
        service = _make_service(store=store, run_repo=run_repo)
        run_id = uuid.uuid4()

        await service.process_run(run_id, uuid.uuid4(), "uploads/empty.csv")

        call_kwargs = run_repo.update_run.call_args.kwargs
        assert call_kwargs["status"] == "failed"
        assert "empty" in call_kwargs["error_detail"].lower()

    @pytest.mark.asyncio
    async def test_binary_file_transitions_to_failed(self):
        raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10" * 10
        store = _make_store(data=raw)
        run_repo = AsyncMock()
        service = _make_service(store=store, run_repo=run_repo)
        run_id = uuid.uuid4()

        await service.process_run(run_id, uuid.uuid4(), "uploads/image.png")

        call_kwargs = run_repo.update_run.call_args.kwargs
        assert call_kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_oversized_download_transitions_to_failed(self):
        # Simulate a file that passes head_object check but body exceeds limit
        raw = b"a,b\n" + b"x,y\n" * 10
        store = _make_store(data=raw)
        run_repo = AsyncMock()
        service = _make_service(store=store, run_repo=run_repo)
        run_id = uuid.uuid4()

        # Patch _MAX_FILE_BYTES to a tiny value to trigger the post-download check
        with patch("src.modules.item_profile.service._MAX_FILE_BYTES", 5):
            await service.process_run(run_id, uuid.uuid4(), "uploads/test.csv")

        call_kwargs = run_repo.update_run.call_args.kwargs
        assert call_kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_nats_not_published_when_publisher_is_none(self):
        raw = _csv_bytes("alice,30,true")
        store = _make_store(data=raw)
        run_repo = AsyncMock()
        service = _make_service(store=store, publisher=None, run_repo=run_repo)

        await service.process_run(uuid.uuid4(), uuid.uuid4(), "uploads/test.csv")

        call_kwargs = run_repo.update_run.call_args.kwargs
        assert call_kwargs["status"] == "profiling_pending"
