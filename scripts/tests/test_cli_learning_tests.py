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

    def test_check_shows_untested_assertions(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_mark_stale_invokes_learning_test_event_mirror(
        self, sample_record: LearnTestRecord
    ) -> None:
        """ENH-2466: mark-stale best-effort mirrors the change into history.db."""
        with patch("sys.argv", ["ll-learning-tests", "mark-stale", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                with patch("little_loops.learning_tests.mark_stale"):
                    with patch(
                        "little_loops.session_store.record_learning_test_event"
                    ) as mock_record:
                        result = main_learning_tests()
        assert result == 0
        mock_record.assert_called_once()
        assert mock_record.call_args[0][1] == "Anthropic SDK streaming"

    def test_mark_stale_swallows_mirror_exceptions(self, sample_record: LearnTestRecord) -> None:
        """A DB failure in the mirror write must not break mark-stale (ENH-2466)."""
        with patch("sys.argv", ["ll-learning-tests", "mark-stale", "Anthropic SDK streaming"]):
            with patch(
                "little_loops.learning_tests.check_learning_test",
                return_value=sample_record,
            ):
                with patch("little_loops.learning_tests.mark_stale"):
                    with patch(
                        "little_loops.session_store.record_learning_test_event",
                        side_effect=RuntimeError("db boom"),
                    ):
                        result = main_learning_tests()
        assert result == 0


class TestStaleAwareCLI:
    """Tests for ll-learning-tests check --stale-aware flag (ENH-2208)."""

    def _make_record(self, *, date: str = "2026-04-25", status: str = "proven") -> LearnTestRecord:
        return LearnTestRecord(
            target="Anthropic SDK streaming",
            date=date,
            status=status,
            assertions=[],
            raw_output_path=None,
        )

    def test_stale_aware_fresh_proven_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--stale-aware exits 0 for a proven record within the stale threshold."""
        import datetime

        fresh_date = datetime.date.today().isoformat()
        record = self._make_record(date=fresh_date)
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "--stale-aware", "Anthropic SDK streaming"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=record):
                with patch("little_loops.config.core.resolve_config_path", return_value=None):
                    result = main_learning_tests()
        assert result == 0

    def test_stale_aware_stale_proven_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--stale-aware exits 1 for a proven record older than stale_after_days."""
        record = self._make_record(date="2020-01-01")
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "--stale-aware", "Anthropic SDK streaming"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=record):
                with patch("little_loops.config.core.resolve_config_path", return_value=None):
                    result = main_learning_tests()
        assert result == 1

    def test_stale_aware_absent_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--stale-aware exits 1 when no record is found."""
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "--stale-aware", "missing target"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=None):
                result = main_learning_tests()
        assert result == 1

    def test_stale_aware_not_proven_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--stale-aware exits 1 for a refuted record even with a fresh date."""
        import datetime

        fresh_date = datetime.date.today().isoformat()
        record = self._make_record(date=fresh_date, status="refuted")
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "--stale-aware", "Anthropic SDK streaming"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=record):
                with patch("little_loops.config.core.resolve_config_path", return_value=None):
                    result = main_learning_tests()
        assert result == 1

    def test_stale_aware_still_prints_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--stale-aware outputs record JSON to stdout even when stale."""
        record = self._make_record(date="2020-01-01")
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "--stale-aware", "Anthropic SDK streaming"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=record):
                with patch("little_loops.config.core.resolve_config_path", return_value=None):
                    main_learning_tests()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["target"] == "Anthropic SDK streaming"

    def test_without_stale_aware_stale_record_still_exits_0(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without --stale-aware, a stale proven record exits 0 (backward compat)."""
        record = self._make_record(date="2020-01-01")
        with patch(
            "sys.argv",
            ["ll-learning-tests", "check", "Anthropic SDK streaming"],
        ):
            with patch("little_loops.learning_tests.check_learning_test", return_value=record):
                result = main_learning_tests()
        assert result == 0


class TestMainLearningTestsProve:
    """Tests for ll-learning-tests prove subcommand (ENH-2430)."""

    def _make_record(self, *, status: str = "proven") -> LearnTestRecord:
        return LearnTestRecord(
            target="requests",
            date="2026-07-01",
            status=status,
            assertions=[Assertion(claim="raises on 4xx", result="pass")],
            raw_output_path=None,
        )

    def test_prove_success_prints_json_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record(status="proven")
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run") as mock_run,
            patch("little_loops.learning_tests.check_learning_test", return_value=record),
        ):
            result = main_learning_tests()
        assert result == 0
        mock_run.assert_called_once()
        data = json.loads(capsys.readouterr().out)
        assert data["target"] == "requests"
        assert data["status"] == "proven"

    def test_prove_shells_to_ready_to_implement_gate(self) -> None:
        record = self._make_record(status="proven")
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run") as mock_run,
            patch("little_loops.learning_tests.check_learning_test", return_value=record),
        ):
            main_learning_tests()
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "ll-loop",
            "run",
            "ready-to-implement-gate",
            "--context",
            "targets=requests",
        ]

    def test_prove_still_refuted_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record(status="refuted")
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run"),
            patch("little_loops.learning_tests.check_learning_test", return_value=record),
        ):
            result = main_learning_tests()
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "refuted"

    def test_prove_invokes_learning_test_event_mirror(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-2466: prove best-effort mirrors the refreshed record into history.db."""
        record = self._make_record(status="proven")
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run"),
            patch("little_loops.learning_tests.check_learning_test", return_value=record),
            patch("little_loops.session_store.record_learning_test_event") as mock_record,
        ):
            result = main_learning_tests()
        assert result == 0
        mock_record.assert_called_once()
        assert mock_record.call_args[0][1] == "requests"

    def test_prove_swallows_mirror_exceptions(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A DB failure in the mirror write must not break prove (ENH-2466)."""
        record = self._make_record(status="proven")
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "requests"]),
            patch("subprocess.run"),
            patch("little_loops.learning_tests.check_learning_test", return_value=record),
            patch(
                "little_loops.session_store.record_learning_test_event",
                side_effect=RuntimeError("db boom"),
            ),
        ):
            result = main_learning_tests()
        assert result == 0

    def test_prove_still_missing_exits_1_with_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("sys.argv", ["ll-learning-tests", "prove", "nonexistent target"]),
            patch("subprocess.run"),
            patch("little_loops.learning_tests.check_learning_test", return_value=None),
        ):
            result = main_learning_tests()
        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error" in captured.err
        assert "nonexistent target" in captured.err


class TestMainLearningTestsOrphans:
    """Tests for ll-learning-tests orphans subcommand (ENH-2216)."""

    def _make_record(self, target: str, status: str = "proven") -> LearnTestRecord:
        return LearnTestRecord(
            target=target,
            date="2026-04-25",
            status=status,
            assertions=[],
            raw_output_path=None,
        )

    def test_no_orphans_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("anthropic")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            result = main_learning_tests()
        assert result == 0

    def test_no_orphans_prints_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("anthropic")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            main_learning_tests()
        assert "No orphaned" in capsys.readouterr().out

    def test_orphaned_record_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("boto3")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            result = main_learning_tests()
        assert result == 1

    def test_orphaned_record_prints_target(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("boto3")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            main_learning_tests()
        assert "boto3" in capsys.readouterr().out

    def test_non_orphaned_record_not_listed(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("anthropic")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            main_learning_tests()
        out = capsys.readouterr().out
        assert "No orphaned" in out

    def test_mark_stale_marks_all_orphans(self) -> None:
        record = self._make_record("boto3")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans", "--mark-stale"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value=set(),
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
            patch("little_loops.learning_tests.mark_stale") as mock_stale,
        ):
            result = main_learning_tests()
        assert result == 0
        mock_stale.assert_called_once()

    def test_mark_stale_invokes_learning_test_event_mirror(self) -> None:
        """ENH-2466: --mark-stale best-effort mirrors each orphan into history.db."""
        record = self._make_record("boto3")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans", "--mark-stale"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value=set(),
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
            patch("little_loops.learning_tests.mark_stale"),
            patch("little_loops.session_store.record_learning_test_event") as mock_record,
        ):
            result = main_learning_tests()
        assert result == 0
        mock_record.assert_called_once()
        assert mock_record.call_args[0][1] == "boto3"

    def test_mark_stale_exits_0(self) -> None:
        record = self._make_record("boto3")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans", "--mark-stale"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value=set(),
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
            patch("little_loops.learning_tests.mark_stale"),
        ):
            result = main_learning_tests()
        assert result == 0

    def test_mark_stale_reports_count(self, capsys: pytest.CaptureFixture[str]) -> None:
        records = [self._make_record("boto3"), self._make_record("requests")]
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans", "--mark-stale"]),
            patch("little_loops.learning_tests.list_records", return_value=records),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value=set(),
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
            patch("little_loops.learning_tests.mark_stale"),
        ):
            main_learning_tests()
        assert "2" in capsys.readouterr().out

    def test_scope_flag_uses_custom_directory(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("import boto3\n")

        record = self._make_record("boto3")
        with (
            patch(
                "sys.argv",
                ["ll-learning-tests", "orphans", "--scope", str(src_dir)],
            ),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            result = main_learning_tests()
        # boto3 is imported in src_dir — not an orphan
        assert result == 0

    def test_multiword_target_uses_first_word(self, capsys: pytest.CaptureFixture[str]) -> None:
        record = self._make_record("Anthropic SDK streaming")
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[record]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value={"anthropic"},
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            result = main_learning_tests()
        assert result == 0

    def test_empty_registry_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("sys.argv", ["ll-learning-tests", "orphans"]),
            patch("little_loops.learning_tests.list_records", return_value=[]),
            patch(
                "little_loops.learning_tests.import_scan.get_imported_packages",
                return_value=set(),
            ),
            patch("little_loops.config.core.resolve_config_path", return_value=None),
        ):
            result = main_learning_tests()
        assert result == 0


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
