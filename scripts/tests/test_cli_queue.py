"""Tests for ll-queue CLI (little_loops.cli.queue) - FEAT-2682.

Named distinctly from test_cli_loop_queue.py, which covers the unrelated
FSM PID-liveness queue subsystem (little_loops.cli.loop.queue).
"""

from __future__ import annotations

import json
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

    def test_add_with_bad_arg_pair_exits_2(self) -> None:
        with patch(
            "sys.argv", ["ll-queue", "add", "target", "--arg", "malformed", "--runner", "cmd"]
        ):
            result = main_queue()
        assert result == 2


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
        from little_loops.queue_store import update_entry_result

        with patch("sys.argv", ["ll-queue", "add", "audit-docs", "--json"]):
            main_queue()
        entry_id = json.loads(capsys.readouterr().out)["id"]
        update_entry_result(entry_id, "running", None)

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
