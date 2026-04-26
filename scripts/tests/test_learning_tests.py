"""Tests for little_loops.learning_tests module."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.learning_tests import (
    Assertion,
    LearnTestRecord,
    check_learning_test,
    list_records,
    mark_stale,
    read_record,
    write_record,
)


@pytest.fixture
def learning_tests_dir(temp_project_dir: Path) -> Path:
    """Create .ll/learning-tests directory and return its path."""
    base = temp_project_dir / ".ll" / "learning-tests"
    base.mkdir(parents=True)
    return base


@pytest.fixture
def sample_record() -> LearnTestRecord:
    """A standard LearnTestRecord for use across tests."""
    return LearnTestRecord(
        target="Anthropic SDK streaming",
        date="2026-04-25",
        status="proven",
        assertions=[
            Assertion(claim="streaming events are dicts with a `type` key", result="pass"),
            Assertion(claim="fork_session=true is required for resumed sessions", result="pass"),
        ],
        raw_output_path=".ll/learning-tests/raw/anthropic-sdk-streaming.txt",
    )


class TestLearnTestRecord:
    """Tests for LearnTestRecord dataclass and serialization."""

    def test_to_dict_basic_fields(self, sample_record: LearnTestRecord) -> None:
        d = sample_record.to_dict()
        assert d["target"] == "Anthropic SDK streaming"
        assert d["date"] == "2026-04-25"
        assert d["status"] == "proven"
        assert d["raw_output_path"] == ".ll/learning-tests/raw/anthropic-sdk-streaming.txt"

    def test_to_dict_assertions_are_list_of_dicts(self, sample_record: LearnTestRecord) -> None:
        d = sample_record.to_dict()
        assert isinstance(d["assertions"], list)
        assert d["assertions"][0] == {
            "claim": "streaming events are dicts with a `type` key",
            "result": "pass",
        }

    def test_from_dict_round_trip(self, sample_record: LearnTestRecord) -> None:
        d = sample_record.to_dict()
        restored = LearnTestRecord.from_dict(d)
        assert restored.target == sample_record.target
        assert restored.date == sample_record.date
        assert restored.status == sample_record.status
        assert restored.raw_output_path == sample_record.raw_output_path
        assert len(restored.assertions) == 2
        assert restored.assertions[0].claim == "streaming events are dicts with a `type` key"
        assert restored.assertions[0].result == "pass"

    def test_from_dict_missing_raw_output_path(self) -> None:
        d = {
            "target": "pytest",
            "date": "2026-04-25",
            "status": "proven",
            "assertions": [],
        }
        record = LearnTestRecord.from_dict(d)
        assert record.raw_output_path is None

    def test_from_dict_empty_assertions(self) -> None:
        d = {
            "target": "pytest",
            "date": "2026-04-25",
            "status": "proven",
            "assertions": [],
        }
        record = LearnTestRecord.from_dict(d)
        assert record.assertions == []


class TestWriteRecord:
    """Tests for write_record function."""

    def test_creates_file_in_base_dir(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        path = write_record(sample_record, base_dir=learning_tests_dir)
        assert path.exists()
        assert path.parent == learning_tests_dir

    def test_file_has_frontmatter(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        path = write_record(sample_record, base_dir=learning_tests_dir)
        content = path.read_text()
        assert content.startswith("---\n")
        assert "\n---" in content

    def test_slug_from_target(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        path = write_record(sample_record, base_dir=learning_tests_dir)
        assert "anthropic-sdk-streaming" in path.name

    def test_returns_path(self, learning_tests_dir: Path, sample_record: LearnTestRecord) -> None:
        result = write_record(sample_record, base_dir=learning_tests_dir)
        assert isinstance(result, Path)

    def test_overwrites_existing(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        updated = LearnTestRecord(
            target=sample_record.target,
            date="2026-04-26",
            status="refuted",
            assertions=[],
            raw_output_path=None,
        )
        path = write_record(updated, base_dir=learning_tests_dir)
        content = path.read_text()
        assert "refuted" in content


class TestReadRecord:
    """Tests for read_record function."""

    def test_returns_none_when_missing(self, learning_tests_dir: Path) -> None:
        result = read_record("nonexistent-slug", base_dir=learning_tests_dir)
        assert result is None

    def test_round_trip_preserves_all_fields(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        slug = "anthropic-sdk-streaming"
        restored = read_record(slug, base_dir=learning_tests_dir)
        assert restored is not None
        assert restored.target == sample_record.target
        assert restored.date == sample_record.date
        assert restored.status == sample_record.status
        assert restored.raw_output_path == sample_record.raw_output_path

    def test_round_trip_preserves_nested_assertions(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        restored = read_record("anthropic-sdk-streaming", base_dir=learning_tests_dir)
        assert restored is not None
        assert len(restored.assertions) == 2
        assert restored.assertions[0].claim == "streaming events are dicts with a `type` key"
        assert restored.assertions[0].result == "pass"


class TestMarkStale:
    """Tests for mark_stale function."""

    def test_updates_status_to_stale(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        mark_stale("anthropic-sdk-streaming", base_dir=learning_tests_dir)
        restored = read_record("anthropic-sdk-streaming", base_dir=learning_tests_dir)
        assert restored is not None
        assert restored.status == "stale"

    def test_preserves_assertions_after_mark_stale(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        mark_stale("anthropic-sdk-streaming", base_dir=learning_tests_dir)
        restored = read_record("anthropic-sdk-streaming", base_dir=learning_tests_dir)
        assert restored is not None
        assert len(restored.assertions) == 2

    def test_noop_on_missing_record(self, learning_tests_dir: Path) -> None:
        mark_stale("does-not-exist", base_dir=learning_tests_dir)


class TestListRecords:
    """Tests for list_records function."""

    def test_returns_empty_list_when_dir_empty(self, learning_tests_dir: Path) -> None:
        result = list_records(base_dir=learning_tests_dir)
        assert result == []

    def test_returns_all_written_records(self, learning_tests_dir: Path) -> None:
        r1 = LearnTestRecord(
            target="pytest fixtures",
            date="2026-04-25",
            status="proven",
            assertions=[],
            raw_output_path=None,
        )
        r2 = LearnTestRecord(
            target="httpx async client",
            date="2026-04-25",
            status="refuted",
            assertions=[],
            raw_output_path=None,
        )
        write_record(r1, base_dir=learning_tests_dir)
        write_record(r2, base_dir=learning_tests_dir)
        records = list_records(base_dir=learning_tests_dir)
        assert len(records) == 2

    def test_returns_empty_when_dir_missing(self, temp_project_dir: Path) -> None:
        missing_dir = temp_project_dir / ".ll" / "learning-tests"
        result = list_records(base_dir=missing_dir)
        assert result == []


class TestCheckLearningTest:
    """Tests for check_learning_test function."""

    def test_returns_none_when_no_record(self, learning_tests_dir: Path) -> None:
        result = check_learning_test("unknown target", base_dir=learning_tests_dir)
        assert result is None

    def test_returns_record_for_known_target(
        self, learning_tests_dir: Path, sample_record: LearnTestRecord
    ) -> None:
        write_record(sample_record, base_dir=learning_tests_dir)
        result = check_learning_test("Anthropic SDK streaming", base_dir=learning_tests_dir)
        assert result is not None
        assert result.target == "Anthropic SDK streaming"
