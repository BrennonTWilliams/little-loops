"""Tests for ll-queue CLI (little_loops.cli.queue) - FEAT-2682.

Named distinctly from test_cli_loop_queue.py, which covers the unrelated
FSM PID-liveness queue subsystem (little_loops.cli.loop.queue).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.queue import _classify_action, main_queue
from little_loops.queue_store import list_entries
from little_loops.runner_spec import RunnerType


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run every test in its own project dir so .ll/queue.db is isolated."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestMainQueueNoAction:
    def test_no_subcommand_exits_nonzero(self) -> None:
        with patch("sys.argv", ["ll-queue"]):
            with pytest.raises(SystemExit) as exc:
                main_queue()
        assert exc.value.code != 0

    def test_help_exits_zero(self) -> None:
        with patch("sys.argv", ["ll-queue", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main_queue()
        assert exc.value.code == 0


class TestClassifyAction:
    def test_classifies_loop_name(self, tmp_path: Path) -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text("name: my-loop\n")

        spec = _classify_action("my-loop", runner_override=None, timeout=120, arg_pairs=None)
        assert spec.runner == RunnerType.LOOP
        assert spec.target == "my-loop"

    def test_classifies_skill_name(self) -> None:
        # audit-docs ships as a real skill in this repo's own skills/ dir,
        # resolved via CLAUDE_PLUGIN_ROOT falling back to this file's project.
        spec = _classify_action("audit-docs", runner_override=None, timeout=120, arg_pairs=None)
        assert spec.runner == RunnerType.SKILL
        assert spec.target == "audit-docs"

    def test_classifies_raw_cli_invocation_as_cmd_fallback(self) -> None:
        spec = _classify_action(
            "totally-unknown-target-xyz", runner_override=None, timeout=120, arg_pairs=None
        )
        assert spec.runner == RunnerType.CMD

    def test_runner_override_skips_classification(self) -> None:
        spec = _classify_action("anything", runner_override="mcp", timeout=120, arg_pairs=None)
        assert spec.runner == RunnerType.MCP
        assert spec.target == "anything"

    def test_arg_pairs_parsed(self) -> None:
        spec = _classify_action(
            "anything",
            runner_override="cmd",
            timeout=120,
            arg_pairs=["key=value", "other=1"],
        )
        assert spec.args == {"key": "value", "other": "1"}

    def test_malformed_arg_pair_raises(self) -> None:
        with pytest.raises(ValueError):
            _classify_action(
                "anything", runner_override="cmd", timeout=120, arg_pairs=["no-equals-sign"]
            )

    def test_input_value_stored_verbatim_under_loop_input(self) -> None:
        """FEAT-2906: --input is carried onto args["loop_input"], not re-interpreted."""
        spec = _classify_action(
            "anything",
            runner_override="loop",
            timeout=120,
            arg_pairs=None,
            input_value='{"issue_id": "BUG-1"}',
        )
        assert spec.args == {"loop_input": '{"issue_id": "BUG-1"}'}

    def test_no_input_value_leaves_args_empty(self) -> None:
        spec = _classify_action(
            "anything", runner_override="loop", timeout=120, arg_pairs=None, input_value=None
        )
        assert "loop_input" not in spec.args

    def test_loop_runner_no_explicit_timeout_resolves_to_none(self) -> None:
        """BUG-2928: LOOP entries default to unbounded (no outer subprocess deadline)."""
        spec = _classify_action("anything", runner_override="loop", timeout=None, arg_pairs=None)
        assert spec.runner == RunnerType.LOOP
        assert spec.timeout is None

    def test_non_loop_runner_no_explicit_timeout_resolves_to_120(self) -> None:
        """BUG-2928: non-LOOP runners keep the 120s default."""
        spec = _classify_action("anything", runner_override="skill", timeout=None, arg_pairs=None)
        assert spec.runner == RunnerType.SKILL
        assert spec.timeout == 120

        spec = _classify_action("anything", runner_override="cmd", timeout=None, arg_pairs=None)
        assert spec.runner == RunnerType.CMD
        assert spec.timeout == 120


class TestCmdAdd:
    def test_add_persists_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["action"]["target"] == "audit-docs"
        assert data["priority"] == "P3"
        assert data["status"] == "pending"

        entries = list_entries()
        assert len(entries) == 1

    def test_add_with_explicit_runner_and_priority(self) -> None:
        with patch(
            "sys.argv",
            [
                "ll-queue",
                "add",
                "pytest scripts/tests/",
                "--runner",
                "cmd",
                "--priority",
                "P0",
                "--json",
            ],
        ):
            result = main_queue()
        assert result == 0

        entries = list_entries()
        assert entries[0].priority == "P0"
        assert entries[0].action.runner == RunnerType.CMD

    def test_add_with_input_persists_onto_entry_args(self) -> None:
        with patch(
            "sys.argv",
            [
                "ll-queue",
                "add",
                "some-loop",
                "--runner",
                "loop",
                "--input",
                '{"issue_id": "BUG-1"}',
                "--json",
            ],
        ):
            result = main_queue()
        assert result == 0

        entries = list_entries()
        assert entries[0].action.args["loop_input"] == '{"issue_id": "BUG-1"}'

    def _make_loop(self, tmp_path: Path, name: str = "my-loop") -> None:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir(exist_ok=True)
        (loops_dir / f"{name}.yaml").write_text(f"name: {name}\n")

    def test_add_positional_input_matches_input_flag(self, tmp_path: Path) -> None:
        self._make_loop(tmp_path)
        with patch("sys.argv", ["ll-queue", "add", "my-loop", "BUG-3354", "--priority", "P2"]):
            assert main_queue() == 0
        with patch("sys.argv", ["ll-queue", "add", "my-loop", "--input", "BUG-3354"]):
            assert main_queue() == 0

        positional, flagged = sorted(list_entries(), key=lambda e: e.priority)
        assert positional.action.runner == RunnerType.LOOP
        assert positional.action.args["loop_input"] == "BUG-3354"
        assert positional.action.runner == flagged.action.runner
        assert positional.action.args == flagged.action.args
        assert positional.action.timeout == flagged.action.timeout

    def test_add_positional_input_with_flags_first(self, tmp_path: Path) -> None:
        self._make_loop(tmp_path)
        with patch("sys.argv", ["ll-queue", "add", "--priority", "P2", "my-loop", "X"]):
            assert main_queue() == 0
        assert list_entries()[0].action.args["loop_input"] == "X"

    def test_add_positional_input_with_loop_runner_override(self) -> None:
        with patch("sys.argv", ["ll-queue", "add", "some-loop", "X", "--runner", "loop"]):
            assert main_queue() == 0
        assert list_entries()[0].action.args["loop_input"] == "X"

    def test_add_positional_and_input_flag_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._make_loop(tmp_path)
        with patch("sys.argv", ["ll-queue", "add", "my-loop", "A", "--input", "B"]):
            assert main_queue() == 2
        assert "given both positionally and via --input" in capsys.readouterr().err
        assert list_entries() == []

    def test_add_empty_positional_counts_as_given(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._make_loop(tmp_path)
        with patch("sys.argv", ["ll-queue", "add", "my-loop", "", "--input", "B"]):
            assert main_queue() == 2
        assert "given both positionally and via --input" in capsys.readouterr().err

    def test_add_positional_with_non_loop_runner_exits_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("sys.argv", ["ll-queue", "add", "x", "Y", "--runner", "cmd"]):
            assert main_queue() == 2
        err = capsys.readouterr().err
        assert "only valid for loop targets" in err
        assert "classified as cmd" in err
        assert list_entries() == []

    def test_add_positional_with_unresolved_loop_name_exits_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("sys.argv", ["ll-queue", "add", "no-such-loop-xyz", "Y"]):
            assert main_queue() == 2
        err = capsys.readouterr().err
        assert "only valid for loop targets" in err
        assert "'no-such-loop-xyz' classified as cmd" in err
        assert list_entries() == []

    def test_add_raw_command_with_stray_word_exits_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("sys.argv", ["ll-queue", "add", "pytest tests/", "extra", "--runner", "cmd"]):
            assert main_queue() == 2
        assert "only valid for loop targets" in capsys.readouterr().err
        assert list_entries() == []

    def test_add_input_flag_with_non_loop_runner_unchanged(self) -> None:
        with patch("sys.argv", ["ll-queue", "add", "x", "--runner", "cmd", "--input", "Y"]):
            assert main_queue() == 0
        entries = list_entries()
        assert entries[0].action.runner == RunnerType.CMD
        assert entries[0].action.args["loop_input"] == "Y"

    def test_add_with_bad_arg_pair_exits_2(self) -> None:
        with patch(
            "sys.argv", ["ll-queue", "add", "target", "--arg", "malformed", "--runner", "cmd"]
        ):
            result = main_queue()
        assert result == 2

    def test_add_loop_runner_defaults_to_unbounded_timeout(self) -> None:
        """BUG-2928: no --timeout on a LOOP add stores timeout: null."""
        with patch("sys.argv", ["ll-queue", "add", "some-loop", "--runner", "loop"]):
            result = main_queue()
        assert result == 0

        entries = list_entries()
        assert entries[0].action.timeout is None

    def test_add_loop_runner_explicit_timeout_overrides_default(self) -> None:
        with patch(
            "sys.argv", ["ll-queue", "add", "some-loop", "--runner", "loop", "--timeout", "30"]
        ):
            result = main_queue()
        assert result == 0

        entries = list_entries()
        assert entries[0].action.timeout == 30

    def test_add_skill_runner_still_defaults_to_120(self) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--runner", "skill"]):
            result = main_queue()
        assert result == 0

        entries = list_entries()
        assert entries[0].action.timeout == 120


class TestCmdList:
    def test_list_empty_queue(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "list"]):
            result = main_queue()
        assert result == 0
        assert "empty" in capsys.readouterr().out.lower()

    def test_list_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list", "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["action"]["target"] == "audit-docs"

    def test_list_orders_by_priority(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "low", "--runner", "cmd", "--priority", "P4"]):
            main_queue()
        with patch("sys.argv", ["ll-queue", "add", "high", "--runner", "cmd", "--priority", "P0"]):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list", "--json"]):
            main_queue()
        data = json.loads(capsys.readouterr().out)
        assert [e["action"]["target"] for e in data] == ["high", "low"]

    def test_list_shows_loop_input_and_timeout(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch(
            "sys.argv",
            ["ll-queue", "add", "autodev", "--runner", "loop", "--input", "BUG-1"],
        ):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list"]):
            result = main_queue()
        assert result == 0
        out = capsys.readouterr().out
        assert "input=BUG-1" in out
        assert "timeout=∞" in out

    def test_list_shows_finite_timeout(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--runner", "skill"]):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list"]):
            result = main_queue()
        assert result == 0
        assert "timeout=120" in capsys.readouterr().out

    def test_list_truncates_long_input_by_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        long_input = "x" * 100
        with patch(
            "sys.argv",
            ["ll-queue", "add", "autodev", "--runner", "loop", "--input", long_input],
        ):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list"]):
            main_queue()
        out = capsys.readouterr().out
        assert long_input not in out
        assert "…" in out

    def test_list_wide_bypasses_truncation(self, capsys: pytest.CaptureFixture[str]) -> None:
        long_input = "x" * 100
        with patch(
            "sys.argv",
            ["ll-queue", "add", "autodev", "--runner", "loop", "--input", long_input],
        ):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list", "--wide"]):
            main_queue()
        assert long_input in capsys.readouterr().out

    def test_list_wide_flag_round_trip_through_argparse(self) -> None:
        with patch("sys.argv", ["ll-queue", "list", "--wide"]):
            result = main_queue()
        assert result == 0

    def test_list_running_entry_shows_elapsed_time(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.queue_store import claim_entry

        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]
        claim_entry(entry_id)

        with patch("sys.argv", ["ll-queue", "list"]):
            result = main_queue()
        assert result == 0
        assert "ago" in capsys.readouterr().out

    def test_list_json_unaffected_by_summary_change(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch(
            "sys.argv",
            ["ll-queue", "add", "autodev", "--runner", "loop", "--input", "BUG-1", "--json"],
        ):
            main_queue()
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "list", "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["action"]["args"] == {"loop_input": "BUG-1"}
        assert data[0]["action"]["timeout"] is None
        assert "summary" not in data[0]
        assert data[0]["attempt"] == 0
        assert data[0]["nextAttemptAt"] is None

    def test_list_operational_error_json(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-3432: a locked/unreadable queue.db must not crash with a traceback."""
        import little_loops.queue_store as qs

        def _locked_connect(*_a: object, **_k: object) -> sqlite3.Connection:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(qs, "connect", _locked_connect)

        with patch("sys.argv", ["ll-queue", "list", "--json"]):
            result = main_queue()
        assert result == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        data = json.loads(captured.out)
        assert "database is locked" in data["error"]

    def test_list_operational_error_text(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import little_loops.queue_store as qs

        def _locked_connect(*_a: object, **_k: object) -> sqlite3.Connection:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(qs, "connect", _locked_connect)

        with patch("sys.argv", ["ll-queue", "list"]):
            result = main_queue()
        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "database is locked" in captured.err


class TestCliEventContextHardening:
    """ENH-3426: history-writer failures must never take down a JSON CLI."""

    def test_locked_history_db_still_emits_json_without_warning(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A locked history.db must not block ll-queue list --json's payload.

        This patches only little_loops.session_store.connect (history.db) —
        queue_store.connect is a separate function and stays real, so this
        proves the analytics side-channel cannot swallow the queue payload.
        ENH-3679: a SQLITE_BUSY drop is counted and logged at debug, not warning.
        """
        import sqlite3

        import little_loops.session_store as ss

        def _locked_connect(*_a: object, **_k: object) -> sqlite3.Connection:
            exc = sqlite3.OperationalError("database is locked")
            exc.sqlite_errorcode = sqlite3.SQLITE_BUSY  # type: ignore[attr-defined]
            raise exc

        monkeypatch.setattr(ss, "connect", _locked_connect)

        with caplog.at_level(logging.DEBUG, logger="little_loops.session_store.writers"):
            with patch("sys.argv", ["ll-queue", "list", "--json"]):
                result = main_queue()
        assert result == 0
        assert json.loads(capsys.readouterr().out) == []
        enter = [r for r in caplog.records if "enter failed" in r.getMessage()]
        assert enter
        assert all(r.levelno == logging.DEBUG for r in enter)

    @staticmethod
    def _run_queue_list_with_failing_history(
        tmp_path: Path, errorcode: str
    ) -> subprocess.CompletedProcess[str]:
        (tmp_path / ".ll").mkdir()
        script = (
            "import sqlite3\n"
            "import little_loops.session_store as ss\n"
            "def _failing_connect(*a, **k):\n"
            "    exc = sqlite3.OperationalError('database is locked')\n"
            f"    exc.sqlite_errorcode = sqlite3.{errorcode}\n"
            "    raise exc\n"
            "ss.connect = _failing_connect\n"
            "import sys\n"
            "sys.argv = ['ll-queue', 'list', '--json']\n"
            "from little_loops.cli.queue import main_queue\n"
            "raise SystemExit(main_queue())\n"
        )
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_non_lock_history_error_stderr_is_one_line_no_traceback(self, tmp_path: Path) -> None:
        """Real subprocess check of the logging.lastResort stderr delivery path.

        Only this test exercises the actual stderr handler (no traceback) —
        the in-process caplog test above proves the record was emitted, not
        that stderr received exactly one clean line. ENH-3679: lock errors are
        debug-only now, so the warning path is pinned with a non-lock errorcode.
        """
        proc = self._run_queue_list_with_failing_history(tmp_path, "SQLITE_IOERR")
        assert proc.returncode == 0
        assert json.loads(proc.stdout) == []
        lines = proc.stderr.strip().splitlines()
        assert len(lines) == 1
        assert (
            "cli_event_context: enter failed for 'll-queue' (OperationalError: database is locked)"
            in lines[0]
        )

    def test_lock_history_error_emits_nothing_on_stderr(self, tmp_path: Path) -> None:
        """ENH-3679: a counted lock drop must not print a stderr line on every command."""
        proc = self._run_queue_list_with_failing_history(tmp_path, "SQLITE_BUSY")
        assert proc.returncode == 0
        assert json.loads(proc.stdout) == []
        assert proc.stderr.strip() == ""


class TestCmdStatus:
    def test_status_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]

        with patch("sys.argv", ["ll-queue", "status", entry_id, "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["id"] == entry_id

    def test_status_resolves_short_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]

        with patch("sys.argv", ["ll-queue", "status", entry_id[:8], "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["id"] == entry_id

    def test_status_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "status", "deadbeefdeadbeef", "--json"]):
            result = main_queue()
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert "error" in data

    def test_status_operational_error_json(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-3432: _not_found_or_ambiguous must not let OperationalError propagate."""
        import little_loops.queue_store as qs

        def _locked_connect(*_a: object, **_k: object) -> sqlite3.Connection:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(qs, "connect", _locked_connect)

        with patch("sys.argv", ["ll-queue", "status", "deadbeefdeadbeef", "--json"]):
            result = main_queue()
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert "database is locked" in data["error"]
        assert data["id"] == "deadbeefdeadbeef"


class TestCmdRemove:
    def test_remove_pending_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]

        with patch("sys.argv", ["ll-queue", "remove", entry_id, "--json"]):
            result = main_queue()
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["removed"] == entry_id
        assert list_entries() == []

    def test_remove_non_pending_requires_force(self, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.queue_store import claim_entry

        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]
        claim_entry(entry_id)

        with patch("sys.argv", ["ll-queue", "remove", entry_id, "--json"]):
            result = main_queue()
        assert result == 1
        capsys.readouterr()

        with patch("sys.argv", ["ll-queue", "remove", entry_id, "--force", "--json"]):
            result = main_queue()
        assert result == 0
        assert list_entries() == []

    def test_remove_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("sys.argv", ["ll-queue", "remove", "deadbeefdeadbeef", "--json"]):
            result = main_queue()
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert "error" in data
