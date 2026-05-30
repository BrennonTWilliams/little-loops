"""Tests for ll-learning-tests CLI (little_loops.cli.learning_tests)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.learning_tests import main_learning_tests
from little_loops.learning_tests import Assertion, LearnTestRecord

HELP_MD = Path(__file__).parent.parent.parent / "commands" / "help.md"
CLI_REFERENCE = Path(__file__).parent.parent.parent / "docs" / "reference" / "CLI.md"


@pytest.fixture
def sample_record() -> LearnTestRecord:
    return LearnTestRecord(
        target="Anthropic SDK streaming",
        date="2026-04-25",
        status="proven",
        assertions=[
            Assertion(claim="events have a type key", result="pass"),
        ],
        raw_output_path=None,
    )


class TestMainLearningTestsNoAction:
    def test_no_subcommand_exits_nonzero(self) -> None:
        with patch("sys.argv", ["ll-learning-tests"]):
            with pytest.raises(SystemExit) as exc:
                main_learning_tests()
        assert exc.value.code != 0

    def test_help_exits_zero(self) -> None:
        with patch("sys.argv", ["ll-learning-tests", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main_learning_tests()
        assert exc.value.code == 0


class TestMainLearningTestsCheck:
    def test_check_found_prints_json(
        self, capsys: pytest.CaptureFixture[str], sample_record: LearnTestRecord
    ) -> None:
        with patch("sys.argv", ["ll-learning-tests", "check", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                result = main_learning_tests()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["target"] == "Anthropic SDK streaming"
        assert data["status"] == "proven"

    def test_check_not_found_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-learning-tests", "check", "nonexistent target"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=None,
            ):
                result = main_learning_tests()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "nonexistent target" in captured.err

    def test_check_not_found_no_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-learning-tests", "check", "missing"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=None,
            ):
                main_learning_tests()
        assert capsys.readouterr().out == ""

    def test_check_output_is_valid_json(
        self, capsys: pytest.CaptureFixture[str], sample_record: LearnTestRecord
    ) -> None:
        with patch("sys.argv", ["ll-learning-tests", "check", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                main_learning_tests()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "assertions" in data
        assert isinstance(data["assertions"], list)

    def test_check_shows_untested_assertions(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI check output must include assertions with result: untested."""
        record = LearnTestRecord(
            target="Stripe rate limits",
            date="2026-05-30",
            status="proven",
            assertions=[
                Assertion(claim="Rate limit is 100 req/s per endpoint", result="untested"),
            ],
            raw_output_path=None,
        )
        with patch("sys.argv", ["ll-learning-tests", "check", "Stripe rate limits"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=record,
            ):
                result = main_learning_tests()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "proven"
        assertions = data["assertions"]
        assert any(a["result"] == "untested" for a in assertions), (
            f"Expected an assertion with result='untested', got {assertions}"
        )


class TestMainLearningTestsList:
    def test_list_empty_prints_array(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-learning-tests", "list"]):
            with patch("little_loops.learning_tests.list_records", return_value=[]):
                result = main_learning_tests()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_list_returns_all_records(
        self, capsys: pytest.CaptureFixture[str], sample_record: LearnTestRecord
    ) -> None:
        with patch("sys.argv", ["ll-learning-tests", "list"]):
            with patch(
                "little_loops.learning_tests.list_records",
                return_value=[sample_record, sample_record],
            ):
                result = main_learning_tests()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["target"] == "Anthropic SDK streaming"

    def test_list_output_is_json_array(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-learning-tests", "list"]):
            with patch("little_loops.learning_tests.list_records", return_value=[]):
                main_learning_tests()
        captured = capsys.readouterr()
        assert isinstance(json.loads(captured.out), list)


class TestMainLearningTestsMarkStale:
    def test_mark_stale_found_returns_0(self, sample_record: LearnTestRecord) -> None:
        with patch("sys.argv", ["ll-learning-tests", "mark-stale", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                with patch("little_loops.learning_tests.mark_stale") as mock_stale:
                    result = main_learning_tests()
        assert result == 0
        mock_stale.assert_called_once()

    def test_mark_stale_not_found_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-learning-tests", "mark-stale", "missing target"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=None,
            ):
                result = main_learning_tests()
        assert result == 1
        assert "Error" in capsys.readouterr().err

    def test_mark_stale_calls_with_slug(self, sample_record: LearnTestRecord) -> None:
        with patch("sys.argv", ["ll-learning-tests", "mark-stale", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                with patch("little_loops.learning_tests.mark_stale") as mock_stale:
                    main_learning_tests()
        slug = mock_stale.call_args[0][0]
        assert slug == "anthropic-sdk-streaming"


class TestDocWiring:
    """Wiring assertions: ll-learning-tests must appear in help.md and CLI.md."""

    def test_help_md_lists_ll_learning_tests(self) -> None:
        content = HELP_MD.read_text()
        assert "ll-learning-tests" in content, (
            "commands/help.md must list ll-learning-tests in the CLI tools block"
        )

    def test_cli_reference_has_ll_learning_tests_section(self) -> None:
        content = CLI_REFERENCE.read_text()
        assert "ll-learning-tests" in content, (
            "docs/reference/CLI.md must have an ll-learning-tests section"
        )
