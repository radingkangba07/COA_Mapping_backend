"""Unit tests for DEFAULT_STAGES enum refactor."""

from src.modules.workstreams.repository import (
    DEFAULT_STAGES,
    StageDefinition,
    StageSequence,
    StageWeight,
)


def test_default_stages_has_six_entries():
    assert len(DEFAULT_STAGES) == 6


def test_default_stages_sequences_are_contiguous_one_to_six():
    sequences = [s.sequence for s in DEFAULT_STAGES]
    assert sorted(sequences) == list(range(1, 7))


def test_default_stages_sequences_are_unique():
    sequences = [s.sequence for s in DEFAULT_STAGES]
    assert len(set(sequences)) == len(sequences)


def test_default_stages_weights_sum_to_one_hundred():
    total = sum(s.weight for s in DEFAULT_STAGES)
    assert total == 100


def test_default_stages_first_entry_is_upload_files():
    assert DEFAULT_STAGES[0].name == "Upload Files"


def test_default_stages_are_stage_definitions():
    for stage in DEFAULT_STAGES:
        assert isinstance(stage, StageDefinition)


def test_stage_sequence_enum_values():
    assert StageSequence.UPLOAD_FILES == 1
    assert StageSequence.TYPE_MAPPING == 2
    assert StageSequence.ACCOUNT_MAPPING_1 == 3
    assert StageSequence.ACCOUNT_MAPPING_2 == 4
    assert StageSequence.ACCOUNT_MAPPING_3 == 5
    assert StageSequence.PREVIEW_AND_EXPORT == 6


def test_stage_weight_enum_values():
    assert StageWeight.HIGH == 30
    assert StageWeight.LOW == 10


def test_default_stages_names_match_expected():
    expected_names = [
        "Upload Files",
        "Type Mapping",
        "Account Mapping: 1",
        "Account Mapping: 2",
        "Account Mapping: 3",
        "Preview & Export",
    ]
    assert [s.name for s in DEFAULT_STAGES] == expected_names
