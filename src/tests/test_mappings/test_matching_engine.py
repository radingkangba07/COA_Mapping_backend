"""Unit tests for MatchingEngine — T050."""

import pytest

from src.modules.mappings.matching import MatchingEngine


@pytest.fixture
def engine() -> MatchingEngine:
    return MatchingEngine(erp_service=None)


def test_exact_match_returns_100(engine: MatchingEngine):
    target_fields = [
        {"id": "account_name", "name": "Account Name"},
        {"id": "account_type", "name": "Account Type"},
    ]
    result = engine.fuzzy_match_columns(["Account Name"], target_fields)
    assert len(result) == 1
    assert result[0]["confidence"] == 100
    assert result[0]["method"] == "exact"


def test_fuzzy_match_returns_correct_score(engine: MatchingEngine):
    target_fields = [
        {"id": "account_name", "name": "Account Name"},
        {"id": "account_number", "name": "Account Number"},
    ]
    result = engine.fuzzy_match_columns(["Acct Name"], target_fields)
    assert len(result) == 1
    assert result[0]["confidence"] > 60
    assert result[0]["target_field"] in ("account_name", "account_number")


def test_unmatched_columns_return_zero(engine: MatchingEngine):
    target_fields = [
        {"id": "account_name", "name": "Account Name"},
    ]
    result = engine.fuzzy_match_columns(["zzzzz_totally_unrelated"], target_fields, threshold=90)
    assert len(result) == 1
    assert result[0]["confidence"] == 0
    assert result[0]["method"] == "unmatched"


def test_find_best_target_name_exact(engine: MatchingEngine):
    name, score = engine.find_best_target_name("Revenue", ["Revenue", "Expense", "Asset"])
    assert name == "Revenue"
    assert score == 100


def test_find_best_target_name_fuzzy(engine: MatchingEngine):
    _name, score = engine.find_best_target_name("Rev", ["Revenue", "Expense", "Asset"])
    assert score > 0


def test_find_best_target_name_empty(engine: MatchingEngine):
    name, score = engine.find_best_target_name("Test", [])
    assert name == "Test"
    assert score == 0


def test_multiple_columns_matched(engine: MatchingEngine):
    target_fields = [
        {"id": "name", "name": "Name"},
        {"id": "type", "name": "Type"},
        {"id": "number", "name": "Number"},
    ]
    result = engine.fuzzy_match_columns(["Name", "Type", "Number"], target_fields)
    assert len(result) == 3
    for r in result:
        assert r["confidence"] == 100
        assert r["method"] == "exact"
