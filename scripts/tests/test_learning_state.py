"""Tests for FSM `type: learning` state dispatch (FEAT-1283).

The learning state queries the learning-tests registry for each declared target;
if all targets are proven, it advances via on_yes; if any target is missing or
stale, it invokes `/ll:explore-api <target>` (up to max_retries times) and
re-checks the registry; if any target is refuted or retries exhaust, it
transitions to on_no / on_blocked.

Uses MockActionRunner (from test_fsm_executor) to assert /ll:explore-api was
invoked, and a per-test learning-tests directory to control registry state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import FSMLoop, LearningConfig, StateConfig
from little_loops.fsm.types import ActionResult
from little_loops.learning_tests import (
    Assertion,
    LearnTestRecord,
    write_record,
)


@dataclass
class _MockRunner:
    """Action runner that simulates `/ll:explore-api` writing a proven record.

    Each call appends to ``calls``. If ``write_records`` is set, the runner
    extracts the target from the action (everything after the skill name) and
    writes a proven LearnTestRecord into ``base_dir`` so the next registry
    lookup succeeds. ``exit_code`` controls success/failure.
    """

    base_dir: Path | None = None
    write_records: bool = False
    write_status: str = "proven"
    exit_code: int = 0
    calls: list[str] = field(default_factory=list)

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
        if self.write_records and self.base_dir is not None:
            target = action.removeprefix("/ll:explore-api ").strip()
            write_record(
                LearnTestRecord(
                    target=target,
                    date="2026-05-11",
                    status=self.write_status,  # type: ignore[arg-type]
                    assertions=[Assertion(claim="x", result="pass")],
                    raw_output_path=None,
                ),
                base_dir=self.base_dir,
            )
        return ActionResult(output="", stderr="", exit_code=self.exit_code, duration_ms=10)


def _learning_fsm(
    targets: list[str],
    *,
    on_yes: str = "planning",
    on_no: str | None = "blocked",
    on_blocked: str | None = None,
    max_retries: int = 2,
) -> FSMLoop:
    """Build a minimal FSM with one learning state and two terminal states."""
    states: dict[str, StateConfig] = {
        "learning": StateConfig(
            type="learning",
            learning=LearningConfig(targets=targets, max_retries=max_retries),
            on_yes=on_yes,
            on_no=on_no,
            on_blocked=on_blocked,
        ),
        "planning": StateConfig(terminal=True),
        "blocked": StateConfig(terminal=True),
    }
    return FSMLoop(name="learning-test", initial="learning", states=states)


class TestLearningStateAllProven:
    """All declared targets already have proven records → fast-path to on_yes."""

    def test_advances_without_invoking_explore_api(
        self, temp_project_dir: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        write_record(
            LearnTestRecord(
                target="Anthropic SDK streaming",
                date="2026-05-11",
                status="proven",
                assertions=[Assertion(claim="claim", result="pass")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        fsm = _learning_fsm(["Anthropic SDK streaming"])
        runner = _MockRunner()
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "planning"
        assert runner.calls == []  # explore-api never invoked
        proven_events = [e for e in events if e.get("event") == "learning_target_proven"]
        complete_events = [e for e in events if e.get("event") == "learning_complete"]
        assert len(proven_events) == 1
        assert proven_events[0]["target"] == "Anthropic SDK streaming"
        assert len(complete_events) == 1


class TestLearningStateMissingRecord:
    """Missing record → invoke /ll:explore-api → re-check → advance."""

    def test_invokes_explore_api_then_advances(
        self, temp_project_dir: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)

        fsm = _learning_fsm(["GitHub API rate limits"])
        runner = _MockRunner(base_dir=base, write_records=True, write_status="proven")
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "planning"
        assert any("/ll:explore-api" in call for call in runner.calls)
        assert any("GitHub API rate limits" in call for call in runner.calls)
        invoked = [e for e in events if e.get("event") == "learning_explore_invoked"]
        proven = [e for e in events if e.get("event") == "learning_target_proven"]
        assert len(invoked) == 1
        assert len(proven) == 1


class TestLearningStateStaleRecord:
    """Existing record with status=stale → invoke /ll:explore-api → advance."""

    def test_stale_triggers_explore_api(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        write_record(
            LearnTestRecord(
                target="stale-target",
                date="2025-01-01",
                status="stale",
                assertions=[Assertion(claim="claim", result="pass")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        fsm = _learning_fsm(["stale-target"])
        runner = _MockRunner(base_dir=base, write_records=True, write_status="proven")
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "planning"
        stale_events = [e for e in events if e.get("event") == "learning_target_stale"]
        assert len(stale_events) == 1
        assert stale_events[0]["target"] == "stale-target"


class TestLearningStateRefuted:
    """Refuted record → transition to on_no / on_blocked, emit refuted event."""

    def test_refuted_routes_to_blocked(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        write_record(
            LearnTestRecord(
                target="refuted-target",
                date="2026-05-11",
                status="refuted",
                assertions=[Assertion(claim="claim", result="fail")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        fsm = _learning_fsm(["refuted-target"], on_no="blocked")
        runner = _MockRunner()
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "blocked"
        assert runner.calls == []  # refuted skips explore-api
        refuted = [e for e in events if e.get("event") == "learning_target_refuted"]
        blocked = [e for e in events if e.get("event") == "learning_blocked"]
        assert len(refuted) == 1
        assert refuted[0]["target"] == "refuted-target"
        assert len(blocked) == 1
        assert blocked[0]["reason"] == "refuted"

    def test_refuted_prefers_on_blocked_when_set(
        self, temp_project_dir: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        write_record(
            LearnTestRecord(
                target="refuted-target",
                date="2026-05-11",
                status="refuted",
                assertions=[Assertion(claim="claim", result="fail")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        fsm = _learning_fsm(["refuted-target"], on_no=None, on_blocked="blocked")
        runner = _MockRunner()
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()
        assert result.final_state == "blocked"


class TestLearningStateMaxRetriesExhausted:
    """After max_retries explore-api invocations, transition to blocked."""

    def test_retries_exhausted_routes_to_blocked(
        self, temp_project_dir: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)

        # Runner does NOT write records → check_learning_test keeps returning None.
        fsm = _learning_fsm(["never-proven"], on_no="blocked", max_retries=2)
        runner = _MockRunner(base_dir=base, write_records=False)
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "blocked"
        # explore-api was invoked exactly max_retries times
        explore_calls = [c for c in runner.calls if "/ll:explore-api" in c]
        assert len(explore_calls) == 2
        blocked = [e for e in events if e.get("event") == "learning_blocked"]
        assert len(blocked) == 1
        assert blocked[0]["reason"] == "retries_exhausted"
        assert blocked[0]["target"] == "never-proven"


class TestLearningStateMultipleTargets:
    """All targets must be proven before the state advances."""

    def test_iterates_all_targets_in_order(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        # First target already proven; second target requires exploration.
        write_record(
            LearnTestRecord(
                target="target-a",
                date="2026-05-11",
                status="proven",
                assertions=[Assertion(claim="claim", result="pass")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        fsm = _learning_fsm(["target-a", "target-b"])
        runner = _MockRunner(base_dir=base, write_records=True, write_status="proven")
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "planning"
        # Only target-b should have been explored
        assert len(runner.calls) == 1
        assert "target-b" in runner.calls[0]
        proven = [e for e in events if e.get("event") == "learning_target_proven"]
        assert [e["target"] for e in proven] == ["target-a", "target-b"]
        complete = [e for e in events if e.get("event") == "learning_complete"]
        assert complete[0]["targets"] == ["target-a", "target-b"]


class TestLearningStateExemptFromThrottle:
    """Pre-existing FEAT-1283 hook: type='learning' is exempt from throttle hard_max.

    Regression for the wiring-pass concern in test_fsm_executor.py:
    ``test_learning_state_exempt_from_hard_max`` sets ``state_type="learning"`` on
    a state that has ``action=...`` (not a learning sub-config). The dispatch
    branch added by FEAT-1283 must NOT swallow that state — it only fires when
    ``state.learning`` is also set.
    """

    def test_dispatch_guard_requires_learning_config(
        self, temp_project_dir: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.chdir(temp_project_dir)
        # No learning config, type="learning" — should fall through to normal
        # shell execution, NOT enter the learning dispatch path.
        fsm = FSMLoop(
            name="legacy-learning",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="echo hi",
                    type="learning",  # marker only — no LearningConfig
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = _MockRunner()
        # The shell action falls back to the default action runner since our mock
        # only intercepts via injection; route to terminal regardless.
        # Patch _run_action to skip actual shell exec.
        with patch.object(FSMExecutor, "_run_action") as mock_run:
            mock_run.return_value = ActionResult(output="", stderr="", exit_code=0, duration_ms=1)
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()
        assert result.final_state == "done"


class TestLearningConfigSerialization:
    """LearningConfig dataclass round-trips via to_dict / from_dict."""

    def test_round_trip_with_defaults(self) -> None:
        cfg = LearningConfig(targets=["x", "y"])
        restored = LearningConfig.from_dict(cfg.to_dict())
        assert restored.targets == ["x", "y"]
        assert restored.max_retries == 2

    def test_round_trip_with_explicit_max_retries(self) -> None:
        cfg = LearningConfig(targets=["x"], max_retries=5)
        d = cfg.to_dict()
        assert d == {"targets": ["x"], "max_retries": 5}
        restored = LearningConfig.from_dict(d)
        assert restored.max_retries == 5

    def test_state_config_round_trip_with_learning(self) -> None:
        state = StateConfig(
            type="learning",
            learning=LearningConfig(targets=["a", "b"], max_retries=3),
            on_yes="planning",
            on_no="blocked",
        )
        d = state.to_dict()
        assert d["type"] == "learning"
        assert d["learning"] == {"targets": ["a", "b"], "max_retries": 3}
        restored = StateConfig.from_dict(d)
        assert restored.learning is not None
        assert restored.learning.targets == ["a", "b"]
        assert restored.learning.max_retries == 3

    def test_targets_csv_round_trip(self) -> None:
        """targets_csv is preserved through to_dict/from_dict (ENH-1741)."""
        cfg = LearningConfig(targets_csv="${context.targets}")
        d = cfg.to_dict()
        assert d["targets_csv"] == "${context.targets}"
        restored = LearningConfig.from_dict(d)
        assert restored.targets_csv == "${context.targets}"
        assert restored.targets == []

    def test_targets_csv_and_max_retries_expr_round_trip(self) -> None:
        """Both targets_csv and max_retries_expr survive serialization (ENH-1741)."""
        cfg = LearningConfig(targets_csv="${context.targets}", max_retries_expr="${context.max_retries}")
        d = cfg.to_dict()
        assert d["targets_csv"] == "${context.targets}"
        assert d["max_retries_expr"] == "${context.max_retries}"
        restored = LearningConfig.from_dict(d)
        assert restored.targets_csv == "${context.targets}"
        assert restored.max_retries_expr == "${context.max_retries}"

    def test_targets_csv_absent_means_none(self) -> None:
        """When targets_csv is not in dict, restored value is None (ENH-1741)."""
        cfg = LearningConfig.from_dict({"targets": ["a"]})
        assert cfg.targets_csv is None
        assert cfg.max_retries_expr is None


class TestLearningStateCsvTargets:
    """ENH-1741: targets_csv resolved at runtime and split into individual targets."""

    def _csv_fsm(
        self,
        targets_csv: str,
        max_retries_expr: str | None = None,
        on_blocked: str | None = "blocked",
    ) -> FSMLoop:
        """Build a minimal FSM with a targets_csv learning state."""
        states: dict[str, StateConfig] = {
            "prove": StateConfig(
                type="learning",
                learning=LearningConfig(
                    targets_csv=targets_csv,
                    max_retries_expr=max_retries_expr,
                ),
                on_yes="planning",
                on_blocked=on_blocked,
                on_no="blocked",
            ),
            "planning": StateConfig(terminal=True),
            "blocked": StateConfig(terminal=True),
        }
        return FSMLoop(name="csv-test", initial="prove", states=states)

    def test_csv_targets_all_proven(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        """Both targets from a CSV string are iterated and proven."""
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        for target in ["target-a", "target-b"]:
            write_record(
                LearnTestRecord(
                    target=target,
                    date="2026-05-11",
                    status="proven",
                    assertions=[Assertion(claim="c", result="pass")],
                    raw_output_path=None,
                ),
                base_dir=base,
            )

        fsm = self._csv_fsm("target-a, target-b")
        runner = _MockRunner()
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "planning"
        assert runner.calls == []
        complete = [e for e in events if e.get("event") == "learning_complete"]
        assert complete[0]["targets"] == ["target-a", "target-b"]

    def test_csv_whitespace_stripped(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        """Whitespace around CSV items is stripped when resolving targets_csv."""
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)
        write_record(
            LearnTestRecord(
                target="target-a",
                date="2026-05-11",
                status="proven",
                assertions=[Assertion(claim="c", result="pass")],
                raw_output_path=None,
            ),
            base_dir=base,
        )

        # "  target-a  " should strip to "target-a"
        fsm = self._csv_fsm("  target-a  ")
        runner = _MockRunner()
        result = FSMExecutor(fsm, action_runner=runner).run()
        assert result.final_state == "planning"

    def test_max_retries_expr_respected(self, temp_project_dir: Path, monkeypatch: Any) -> None:
        """max_retries_expr is resolved to int and used as the retry limit."""
        monkeypatch.chdir(temp_project_dir)
        base = temp_project_dir / ".ll" / "learning-tests"
        base.mkdir(parents=True)

        # No record for target-x: explore-api will be called up to max_retries times.
        # Set max_retries_expr to "1" → only 1 explore attempt before blocking.
        fsm = FSMLoop(
            name="expr-test",
            initial="prove",
            states={
                "prove": StateConfig(
                    type="learning",
                    learning=LearningConfig(
                        targets_csv="target-x",
                        max_retries_expr="1",
                    ),
                    on_yes="planning",
                    on_blocked="blocked",
                    on_no="blocked",
                ),
                "planning": StateConfig(terminal=True),
                "blocked": StateConfig(terminal=True),
            },
        )
        runner = _MockRunner(base_dir=base, write_records=False)
        result = FSMExecutor(fsm, action_runner=runner).run()

        assert result.final_state == "blocked"
        # Only 1 explore attempt (not the default 2)
        assert len(runner.calls) == 1

