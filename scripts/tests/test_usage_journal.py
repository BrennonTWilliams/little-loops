"""Tests for per-state token usage journaling in usage.jsonl."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import PersistentExecutor
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.subprocess_utils import TokenUsage


class MockActionRunner:
    """Action runner that returns pre-configured results."""

    def __init__(self, results: list[ActionResult] | None = None) -> None:
        self.calls: list[str] = []
        self.results = results or []
        self._index = 0

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Any = None,
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: Any = None,
        on_usage_detailed: Any = None,
    ) -> ActionResult:
        del timeout, is_slash_command, on_output_line, agent, tools, on_usage, on_usage_detailed
        self.calls.append(action)
        if self._index < len(self.results):
            result = self.results[self._index]
            self._index += 1
            return result
        return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)


@pytest.fixture
def tmp_loops_dir(tmp_path: Path) -> Path:
    return tmp_path / ".loops"


@pytest.fixture
def simple_fsm(tmp_path: Path) -> FSMLoop:
    run_dir = str(tmp_path / "run_dir") + "/"
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    return FSMLoop(
        name="test-loop",
        initial="check",
        states={
            "check": StateConfig(action="echo hi", on_yes="done", on_no="done"),
            "done": StateConfig(terminal=True),
        },
        context={"run_dir": run_dir},
    )


class TestUsageJournaling:
    def test_usage_jsonl_written_when_action_complete_has_tokens(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """usage.jsonl is created when action_complete carries token fields."""
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=200,
            cache_read_tokens=300,
            cache_creation_tokens=50,
            model="claude-sonnet-4-6",
        )
        result_with_usage = ActionResult(
            output="yes", stderr="", exit_code=0, duration_ms=100, usage_events=[usage]
        )
        runner = MockActionRunner(results=[result_with_usage])
        executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor.run()

        run_dir = Path(simple_fsm.context["run_dir"])
        usage_path = run_dir / "usage.jsonl"
        assert usage_path.exists(), "usage.jsonl should be created"
        lines = usage_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 1
        row = json.loads(lines[0])
        assert row["input_tokens"] == 1000
        assert row["output_tokens"] == 200
        assert row["cache_read_tokens"] == 300
        assert row["cache_creation_tokens"] == 50
        assert row["model"] == "claude-sonnet-4-6"
        assert "state" in row
        assert "iteration" in row
        assert "timestamp" in row

    def test_usage_jsonl_not_written_when_no_tokens(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """usage.jsonl is not created for shell actions with no token data."""
        runner = MockActionRunner()  # returns ActionResult with empty usage_events
        executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor.run()

        run_dir = Path(simple_fsm.context["run_dir"])
        usage_path = run_dir / "usage.jsonl"
        # Either doesn't exist or has no lines
        if usage_path.exists():
            assert usage_path.read_text(encoding="utf-8").strip() == ""

    def test_shell_action_skipped_from_journal(
        self, tmp_path: Path, tmp_loops_dir: Path
    ) -> None:
        """Shell action_type invocations produce no row in usage.jsonl."""
        run_dir = str(tmp_path / "run2") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        fsm = FSMLoop(
            name="shell-loop",
            initial="run",
            states={
                "run": StateConfig(action="echo hello", action_type="shell", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        # Shell runner returns no usage_events
        runner = MockActionRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor.run()

        usage_path = Path(run_dir) / "usage.jsonl"
        if usage_path.exists():
            lines = [l for l in usage_path.read_text().splitlines() if l.strip()]
            assert len(lines) == 0, "Shell actions must not produce usage.jsonl rows"

    def test_usage_jsonl_appends_across_iterations(
        self, tmp_path: Path, tmp_loops_dir: Path
    ) -> None:
        """Multiple iterations each append a row to usage.jsonl."""
        run_dir = str(tmp_path / "run3") + "/"
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        usage1 = TokenUsage(100, 20, 0, 0, "claude-sonnet-4-6")
        usage2 = TokenUsage(200, 40, 0, 0, "claude-sonnet-4-6")
        fsm = FSMLoop(
            name="multi-iter",
            initial="step1",
            states={
                "step1": StateConfig(action="echo a", on_yes="step2", on_no="step2"),
                "step2": StateConfig(action="echo b", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
            context={"run_dir": run_dir},
        )
        runner = MockActionRunner(
            results=[
                ActionResult(output="yes", stderr="", exit_code=0, duration_ms=10, usage_events=[usage1]),
                ActionResult(output="yes", stderr="", exit_code=0, duration_ms=10, usage_events=[usage2]),
            ]
        )
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor.run()

        usage_path = Path(run_dir) / "usage.jsonl"
        assert usage_path.exists()
        lines = usage_path.read_text().splitlines()
        assert len(lines) == 2
        row1 = json.loads(lines[0])
        row2 = json.loads(lines[1])
        assert row1["input_tokens"] == 100
        assert row2["input_tokens"] == 200

    def test_usage_jsonl_not_archived_to_history(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """usage.jsonl must NOT be copied to .loops/.history/ — it lives permanently at run_dir."""
        usage = TokenUsage(100, 20, 0, 0, "claude-sonnet-4-6")
        runner = MockActionRunner(
            results=[ActionResult(output="yes", stderr="", exit_code=0, duration_ms=10, usage_events=[usage])]
        )
        executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor.run()

        # Verify .history does not contain usage.jsonl
        history_dir = tmp_loops_dir / ".history"
        if history_dir.exists():
            for run_subdir in history_dir.iterdir():
                assert not (run_subdir / "usage.jsonl").exists(), (
                    "usage.jsonl must not be archived to .history/"
                )
