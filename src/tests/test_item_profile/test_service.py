"""Unit tests for ItemProfileService — CSV ingestion (DAB-33), stats engine (DAB-34), pattern/anomaly (DAB-35)."""

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.core.exceptions import PayloadTooLargeError, ValidationError
from src.modules.item_profile.service import (
    FieldStats,
    ItemProfileService,
    _assign_severity,
    _char_class_signature,
    _classify_cardinality,
    _count_rows,
    _detect_anomalies,
    _detect_pattern,
    _infer_column_type,
    _parse_csv,
    compute_all_stats,
    compute_field_stats,
    detect_cross_subsidiary_splits,
    detect_duplicates,
    load_full_csv,
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
    lines = [header] + list(rows)
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
        with pytest.raises(Exception):
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
            patch("src.modules.item_profile.service.ProjectRepository") as MockRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=project_id))
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
            patch("src.modules.item_profile.service.ProjectRepository") as MockRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
            with pytest.raises(ValidationError, match="not found in storage"):
                await service.initiate_run(uuid.uuid4(), "uploads/missing.csv", user)

    @pytest.mark.asyncio
    async def test_oversized_file_raises_413(self):
        store = _make_store(exists=True, size=600 * 1024 * 1024)
        service = _make_service(store=store)
        user = _make_user()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as MockRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
            with pytest.raises(PayloadTooLargeError):
                await service.initiate_run(uuid.uuid4(), "uploads/huge.csv", user)

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self):
        store = _make_store(exists=True, size=1024)
        service = _make_service(store=store)
        user = _make_user()

        with (
            patch("src.modules.item_profile.service.ensure_project_access", new=AsyncMock()),
            patch("src.modules.item_profile.service.ProjectRepository") as MockRepo,
        ):
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
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


# ---------------------------------------------------------------------------
# DAB-34: Field statistics engine
# ---------------------------------------------------------------------------

class TestClassifyCardinality:
    def test_low(self):
        assert _classify_cardinality(5) == "low"

    def test_medium(self):
        assert _classify_cardinality(50) == "medium"

    def test_high(self):
        assert _classify_cardinality(200) == "high"

    def test_boundary_low_medium(self):
        assert _classify_cardinality(9) == "low"
        assert _classify_cardinality(10) == "medium"

    def test_boundary_medium_high(self):
        assert _classify_cardinality(100) == "medium"
        assert _classify_cardinality(101) == "high"


class TestAssignSeverity:
    def test_blocker(self):
        assert _assign_severity(51.0) == "blocker"

    def test_warning(self):
        assert _assign_severity(15.0) == "warning"

    def test_ok(self):
        assert _assign_severity(5.0) == "ok"

    def test_exact_50_is_warning(self):
        assert _assign_severity(50.0) == "warning"

    def test_exact_10_is_ok(self):
        assert _assign_severity(10.0) == "ok"


class TestComputeFieldStats:
    def test_null_heavy_field(self):
        s = pd.Series([None] * 60 + ["alice"] * 40)
        stats = compute_field_stats("name", s)
        assert stats.null_count == 60
        assert stats.null_pct == 60.0
        assert stats.severity == "blocker"

    def test_fully_unique_field(self):
        # 101 distinct values → high cardinality (> 100 per spec)
        s = pd.Series([str(i) for i in range(101)])
        stats = compute_field_stats("id", s)
        assert stats.distinct_count == 101
        assert stats.uniqueness_pct == 100.0
        assert stats.cardinality == "high"

    def test_constant_field_all_same_value(self):
        s = pd.Series(["active"] * 100)
        stats = compute_field_stats("status", s)
        assert stats.distinct_count == 1
        assert stats.cardinality == "low"
        assert stats.null_pct == 0.0
        assert stats.severity == "ok"
        assert len(stats.top_values) == 1
        assert stats.top_values[0]["value"] == "active"
        assert stats.top_values[0]["count"] == 100

    def test_numeric_field(self):
        s = pd.Series([1.0, 2.5, 3.0, 4.5, 5.0])
        stats = compute_field_stats("price", s)
        assert stats.detected_type == "decimal"
        assert stats.numeric_min == 1.0
        assert stats.numeric_max == 5.0
        assert stats.numeric_mean is not None
        assert stats.text_len_min is None

    def test_integer_field(self):
        s = pd.Series([10, 20, 30, 40])
        stats = compute_field_stats("qty", s)
        assert stats.detected_type == "integer"
        assert stats.numeric_min == 10.0
        assert stats.numeric_max == 40.0

    def test_string_field_text_lengths(self):
        s = pd.Series(["hi", "hello", "hey there"])
        stats = compute_field_stats("greeting", s)
        assert stats.detected_type == "string"
        assert stats.text_len_min == 2
        assert stats.text_len_max == 9
        assert stats.numeric_min is None

    def test_mixed_null_and_values(self):
        s = pd.Series([1, 2, None, None, 3])
        stats = compute_field_stats("val", s)
        assert stats.total_count == 5
        assert stats.null_count == 2
        assert stats.non_null_count == 3
        assert stats.null_pct == 40.0
        assert stats.severity == "warning"

    def test_top_values_limited_to_20(self):
        # 25 distinct values — top_values should cap at 20
        s = pd.Series([str(i) for i in range(25)])
        stats = compute_field_stats("col", s)
        assert len(stats.top_values) == 20

    def test_top_values_pct_sums_roughly_to_100_for_constant(self):
        s = pd.Series(["x"] * 50)
        stats = compute_field_stats("col", s)
        assert stats.top_values[0]["pct"] == 100.0

    def test_null_pct_against_total_not_non_null(self):
        # 30 nulls out of 100 total → null_pct = 30%, uniqueness based on 70 non-null
        s = pd.Series([None] * 30 + ["a"] * 35 + ["b"] * 35)
        stats = compute_field_stats("col", s)
        assert stats.null_pct == 30.0
        assert stats.non_null_count == 70
        assert stats.uniqueness_pct == round(2 / 70 * 100, 2)


class TestComputeAllStats:
    def test_returns_one_stat_per_column(self):
        df = pd.DataFrame({"name": ["alice", "bob"], "age": [30, 25], "active": [True, False]})
        results = compute_all_stats(df)
        assert len(results) == 3
        assert [r.field_name for r in results] == ["name", "age", "active"]

    def test_empty_dataframe_columns(self):
        df = pd.DataFrame({"col": pd.Series([], dtype=object)})
        results = compute_all_stats(df)
        assert len(results) == 1
        assert results[0].total_count == 0


class TestLoadFullCsv:
    def test_loads_all_rows(self):
        # _parse_csv uses nrows=500; load_full_csv must load everything
        rows = [f"val{i}" for i in range(600)]
        raw = ("name\n" + "\n".join(rows)).encode()
        df = load_full_csv(raw)
        assert len(df) == 600

    def test_latin1_encoding(self):
        raw = "name\nM\xe9xico\n".encode("latin-1")
        df = load_full_csv(raw)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# DAB-35: Pattern detection and anomaly engine
# ---------------------------------------------------------------------------

class TestCharClassSignature:
    def test_alpha_only(self):
        assert _char_class_signature("ABC") == "AAA"

    def test_digit_only(self):
        assert _char_class_signature("1234") == "0000"

    def test_mixed_with_special(self):
        assert _char_class_signature("AB-1234") == "AA-0000"

    def test_empty_string(self):
        assert _char_class_signature("") == ""

    def test_special_chars_retained(self):
        assert _char_class_signature("A1.B2") == "A0.A0"


class TestDetectPattern:
    def test_single_dominant_pattern(self):
        s = pd.Series(["AB-1234", "CD-5678", "EF-9012"])
        result = _detect_pattern(s)
        assert result is not None
        assert result["dominant"] == "AA-0000"
        assert result["dominant_pct"] == 100.0
        assert result["variants"] == []

    def test_mixed_patterns_returns_dominant(self):
        s = pd.Series(["AB-1234"] * 8 + ["1234"] * 2)
        result = _detect_pattern(s)
        assert result["dominant"] == "AA-0000"
        assert result["dominant_pct"] == 80.0
        assert len(result["variants"]) == 1
        assert result["variants"][0]["pattern"] == "0000"

    def test_empty_series_returns_none(self):
        assert _detect_pattern(pd.Series([], dtype=object)) is None


class TestDetectAnomalies:
    def test_no_anomalies(self):
        s = pd.Series(["AB-1234", "CD-5678"])
        count, examples = _detect_anomalies(s, "AA-0000")
        assert count == 0
        assert examples == []

    def test_with_anomalies(self):
        s = pd.Series(["AB-1234", "CD-5678", "999"])
        count, examples = _detect_anomalies(s, "AA-0000")
        assert count == 1
        assert "999" in examples

    def test_all_anomalous(self):
        s = pd.Series(["123", "456", "789"])
        count, examples = _detect_anomalies(s, "AA-0000")
        assert count == 3

    def test_examples_capped_at_10(self):
        s = pd.Series([str(i) for i in range(20)])
        count, examples = _detect_anomalies(s, "AAAA")
        assert count == 20
        assert len(examples) == 10


class TestComputeFieldStatsPatterns:
    def test_string_field_gets_pattern_summary(self):
        s = pd.Series(["AB-1234", "CD-5678", "EF-9012"])
        stats = compute_field_stats("code", s)
        assert stats.pattern_summary is not None
        assert stats.pattern_summary["dominant"] == "AA-0000"
        assert stats.anomaly_count == 0

    def test_uniform_field_zero_anomalies(self):
        s = pd.Series(["AB-1234"] * 50)
        stats = compute_field_stats("code", s)
        assert stats.anomaly_count == 0
        assert stats.anomaly_examples == []

    def test_mixed_pattern_field_anomaly_detected(self):
        s = pd.Series(["AB-1234"] * 9 + ["999"])
        stats = compute_field_stats("code", s)
        assert stats.anomaly_count == 1
        assert "999" in stats.anomaly_examples

    def test_numeric_field_has_no_pattern(self):
        s = pd.Series([1.0, 2.5, 3.0])
        stats = compute_field_stats("price", s)
        assert stats.pattern_summary is None
        assert stats.anomaly_count == 0


class TestDetectDuplicates:
    def test_no_duplicates(self):
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        result = detect_duplicates(df)
        assert result["group_count"] == 0
        assert result["total_duplicate_rows"] == 0
        assert result["examples"] == []

    def test_all_duplicates(self):
        df = pd.DataFrame({"id": [1, 1, 1], "name": ["a", "a", "a"]})
        result = detect_duplicates(df)
        assert result["group_count"] == 1
        assert result["total_duplicate_rows"] == 3

    def test_partial_duplicates(self):
        df = pd.DataFrame({"id": [1, 1, 2], "name": ["a", "a", "b"]})
        result = detect_duplicates(df)
        assert result["group_count"] == 1
        assert result["total_duplicate_rows"] == 2

    def test_with_explicit_key_fields(self):
        df = pd.DataFrame({"id": [1, 1, 2], "name": ["a", "b", "c"]})
        # Only key on 'id' → rows 0 and 1 are duplicates
        result = detect_duplicates(df, key_fields=["id"])
        assert result["group_count"] == 1
        assert result["total_duplicate_rows"] == 2

    def test_empty_dataframe(self):
        df = pd.DataFrame({"id": pd.Series([], dtype=int)})
        result = detect_duplicates(df)
        assert result["group_count"] == 0


class TestDetectCrossSubsidiarySplits:
    def test_no_subsidiary_column(self):
        df = pd.DataFrame({"account": ["A", "B"], "amount": [100, 200]})
        result = detect_cross_subsidiary_splits(df)
        assert result["has_cross_subsidiary_splits"] is False
        assert result["split_count"] == 0

    def test_no_splits(self):
        df = pd.DataFrame({
            "account": ["A", "B", "C"],
            "subsidiary": ["Sub1", "Sub1", "Sub1"],
        })
        result = detect_cross_subsidiary_splits(df)
        assert result["has_cross_subsidiary_splits"] is False

    def test_with_cross_subsidiary_splits(self):
        df = pd.DataFrame({
            "account": ["A", "A", "B"],
            "subsidiary": ["Sub1", "Sub2", "Sub1"],
        })
        result = detect_cross_subsidiary_splits(df)
        assert result["has_cross_subsidiary_splits"] is True
        assert result["split_count"] == 1
        assert len(result["examples"]) == 1
        assert set(result["examples"][0]["subsidiaries"]) == {"Sub1", "Sub2"}

    def test_company_column_detected(self):
        df = pd.DataFrame({
            "account": ["A", "A"],
            "company": ["C1", "C2"],
        })
        result = detect_cross_subsidiary_splits(df)
        assert result["has_cross_subsidiary_splits"] is True

    def test_branch_column_detected(self):
        df = pd.DataFrame({
            "account": ["X", "X"],
            "branch": ["B1", "B2"],
        })
        result = detect_cross_subsidiary_splits(df)
        assert result["has_cross_subsidiary_splits"] is True
