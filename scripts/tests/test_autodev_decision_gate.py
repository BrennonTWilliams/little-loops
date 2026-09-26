"""Tests for autodev's decision routing (BUG-2513, reworked by ENH-3610).

ENH-3610: autodev no longer resolves decisions at its own entry points. The
refine-to-ready-issue child owns resolution (``check_decision_before_done``) and
autodev's ``select_obligation_*`` selectors re-enter the child when the flag is
still set. The BUG-2513 history below is kept for the legacy record.


BUG-2513: ``decision_needed`` is only consulted downstream of
``refine_current.on_success``. Four of the five exits out of
``refine_current`` (``on_failure``, ``on_error``, ``on_no``,
``on_rate_limit_exhausted``) advance the queue without consulting the flag,
so a dequeued issue with ``decision_needed: true`` re-enters the queue and
is re-refined indefinitely without ``/ll:decide-issue`` ever running.

The fix adds a ``check_decision_at_dequeue`` state between
``dequeue_next.on_yes`` and ``refine_current`` that short-circuits straight
to ``run_decide`` when ``decision_needed: true`` — making the decision gate
independent of the sub-loop's outcome.

These tests exercise the routing shape with both structural YAML assertions
and a small FSMExecutor-driven run that confirms the gate fires before
``refine_current`` is reached.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


class _StubRunner:
    """Minimal ActionRunner for FSMExecutor routing tests.

    Returns canned results keyed by action-substring so tests can assert
    state ordering without invoking real shell/subprocess actions. Mirrors
    the shape of ``MockActionRunner`` from ``test_fsm_executor.py`` but is
    intentionally local to keep this test file self-contained.
    """

    def __init__(self, results: list[tuple[str, dict[str, Any]]] | None = None) -> None:
        self._results = results or []
        self.calls: list[str] = []

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        **kwargs: Any,
    ) -> Any:
        from little_loops.fsm.executor import ActionResult

        del timeout, is_slash_command, kwargs
        self.calls.append(action)
        for pattern, payload in self._results:
            if pattern in action or pattern == action:
                return ActionResult(
                    output=payload.get("output", ""),
                    stderr=payload.get("stderr", ""),
                    exit_code=payload.get("exit_code", 0),
                    duration_ms=payload.get("duration_ms", 1),
                )
        return ActionResult(output="", stderr="", exit_code=0, duration_ms=1)


def _state(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import StateConfig

    return StateConfig(**kwargs)


def _loop(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import FSMLoop

    return FSMLoop(**kwargs)


def _run_decision_chain(fsm: Any, action_runner: Any) -> tuple[Any, list[str]]:
    """Run a minimal autodev-shaped FSM and return (result, visited path)."""
    from little_loops.fsm.executor import FSMExecutor

    visited: list[str] = []

    def on_event(event: dict[str, Any]) -> None:
        if event.get("event") == "state_enter":
            visited.append(event["state"])

    executor = FSMExecutor(fsm, action_runner=action_runner, event_callback=on_event)
    return executor.run(), visited


_DECISION_STATES_REMOVED = (
    "check_decision_at_dequeue",
    "resolve_decision_at_dequeue",
    "mark_decide_ran_at_dequeue",
    "check_decision_after_refine",
    "decide_current",
    "check_decision_before_size_review",
    "triage_outcome_failure",
    "resolve_decision_direct",
)

#: ENH-3611 (commit 2): the 22 autodev spike/decision states removed; the
#: refine-to-ready-issue child owns spike and decision repair.
_SPIKE_STATES_REMOVED = (
    "check_spike_needed",
    "run_spike",
    "count_repair_cycle_spike",
    "route_spike_verdict",
    "check_spike_budget",
    "record_spike_inconclusive",
    "mark_spike_no_verdict_infra",
    "rerun_confidence_after_spike",
    "clear_scores_before_spike",
    "check_scores_present_spike",
    "check_spike_needed_before_skip",
    "resolve_decision",
    "mark_decide_ran",
    "rerun_confidence_after_decide",
    "clear_scores_before_decide",
    "check_scores_present_decide",
    "recheck_after_decide",
    "check_rearmed_spike_after_decide",
    "check_decide_rate_limited",
    "record_decision_unresolved",
    "snap_and_size_review",
    "check_proof_gate_before_implement",
)

#: ENH-3615: the nine wire / atomic / reconcile rescoring-triplet states, replaced by
#: the shared clear_scores -> rerun_confidence -> check_scores_present ->
#: route_after_rescore chain.
_RESCORE_TRIPLET_STATES_REMOVED = (
    "clear_scores_before_wire",
    "rerun_confidence_after_wire",
    "check_scores_present_wire",
    "clear_scores_before_atomic",
    "rerun_confidence_after_atomic_remediation",
    "check_scores_present_atomic",
    "clear_scores_before_reconcile",
    "rerun_confidence_after_reconcile",
    "check_scores_present_reconcile",
)

_PRE_IMPLEMENT_SITES = (
    ("check_passed", "on_yes"),
    ("recheck_scores", "on_yes"),
    ("recheck_after_size_review", "on_yes"),
    ("regate_after_atomic_remediation", "on_yes"),
    ("reopen_waived", "next"),
)


class TestRemovedDecisionEntryPoints:
    """ENH-3610: autodev's eight decision entry states stay deleted (pattern:
    ``TestAssertDecisionClearedStructural``) and no edge targets them."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.mark.parametrize("state", _DECISION_STATES_REMOVED)
    def test_state_stays_deleted(self, data: dict[str, Any], state: str) -> None:
        assert state not in data["states"], (
            f"{state} was removed by ENH-3610 — autodev never resolves a decision itself; "
            "the refine-to-ready-issue child owns resolution"
        )

    def test_no_edge_targets_a_removed_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _DECISION_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    def test_no_state_calls_the_resolve_decision_oracle(self, data: dict[str, Any]) -> None:
        """ENH-3611: resolve_decision (the last oracle caller) is gone; no autodev
        state runs oracles/resolve-decision or /ll:spike."""
        callers = [
            n for n, s in data["states"].items() if s.get("loop") == "oracles/resolve-decision"
        ]
        assert callers == []
        spikers = [
            n
            for n, s in data["states"].items()
            if s.get("action_type") == "slash_command"
            and (s.get("action") or "").startswith("/ll:spike")
        ]
        assert spikers == []

    def test_spike_states_stay_deleted(self, data: dict[str, Any]) -> None:
        assert len(_SPIKE_STATES_REMOVED) == 22
        assert [n for n in _SPIKE_STATES_REMOVED if n in data["states"]] == []

    def test_no_edge_targets_a_removed_spike_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _SPIKE_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    @pytest.mark.parametrize("state", _RESCORE_TRIPLET_STATES_REMOVED)
    def test_rescore_triplet_state_stays_deleted(self, data: dict[str, Any], state: str) -> None:
        assert state not in data["states"]

    def test_no_edge_targets_a_removed_rescore_triplet_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _RESCORE_TRIPLET_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    def test_run_size_review_rate_limit_halts_through_finalize(self, data: dict[str, Any]) -> None:
        """ENH-3615: exhaustion no longer drops the issue silently via dequeue_next."""
        assert data["states"]["run_size_review"]["on_rate_limit_exhausted"] == (
            "finalize_rate_limited"
        )

    def test_dequeue_routes_through_status_then_blockers(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_status_at_dequeue"]
        assert state["on_no"] == "check_blockers_at_dequeue"
        assert state["on_error"] == "check_blockers_at_dequeue"

    def test_autodev_yaml_loads_and_validates(self) -> None:
        from little_loops.fsm.validation import ValidationSeverity, load_and_validate

        fsm, errors = load_and_validate(AUTODEV_LOOP_PATH)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, [str(e) for e in error_list]
        for state in ("select_obligation_post_refine", "select_obligation_pre_implement"):
            assert state in fsm.states
        assert "record_reentry_exhausted" in fsm.states


class TestObligationSelectorStructural:
    """ENH-3610: both selector route tables and the retarget table."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_post_refine_route_table(self, data: dict[str, Any]) -> None:
        state = data["states"]["select_obligation_post_refine"]
        assert state["evaluate"] == {"type": "classify"}
        assert state["route"] == {
            "DECISION": "refine_current",
            "DECISION_EXHAUSTED": "record_reentry_exhausted",
            "PROOF": "refine_current",
            "_": "check_missing_artifacts",  # ENH-3611: was check_spike_needed
            "_error": "detect_children",
        }

    def test_pre_implement_route_table(self, data: dict[str, Any]) -> None:
        state = data["states"]["select_obligation_pre_implement"]
        assert state["evaluate"] == {"type": "classify"}
        assert state["route"] == {
            "DECISION": "refine_current",
            "DECISION_EXHAUSTED": "record_reentry_exhausted",
            "PROOF": "refine_current",
            "_": "check_proof_defer_or_implement",  # ENH-3611: only proof stage
            "_error": "check_proof_defer_or_implement",
        }

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    def test_selector_probe_order_and_flags(self, data: dict[str, Any], name: str) -> None:
        action = data["states"][name]["action"]
        assert action.index("check-flag") < action.index("next-obligation")
        assert "decision_needed" in action
        for token in (
            "--format token",
            "--readiness-threshold ${context.readiness_threshold:shell}",
            "--outcome-threshold ${context.outcome_threshold:shell}",
            "--honor-waiver",
            "autodev-reentry-DECISION-",
            "grep -vxF",
            "autodev-staged.txt",
        ):
            assert token in action, token

    @pytest.mark.parametrize(("state", "edge"), _PRE_IMPLEMENT_SITES)
    def test_score_pass_sites_route_through_pre_implement_selector(
        self, data: dict[str, Any], state: str, edge: str
    ) -> None:
        assert data["states"][state][edge] == "select_obligation_pre_implement"

    def test_check_passed_failure_edges_route_through_post_refine_selector(
        self, data: dict[str, Any]
    ) -> None:
        state = data["states"]["check_passed"]
        assert state["on_no"] == "select_obligation_post_refine"
        assert state["on_cannot_judge"] == "select_obligation_post_refine"
        assert state["on_error"] == "detect_children"

    def test_recheck_scores_failure_edges_skip_to_size_review(self, data: dict[str, Any]) -> None:
        state = data["states"]["recheck_scores"]
        for edge in ("on_no", "on_error", "on_cannot_judge"):
            assert state[edge] == "run_size_review"

    def test_route_refine_success_fallthroughs_retarget_to_check_passed(
        self, data: dict[str, Any]
    ) -> None:
        route = data["states"]["route_refine_success"]["route"]
        for token in ("READY", "BLOCKED", "MISSING", "_", "_error"):
            assert route[token] == "check_passed"

    def test_dequeue_next_clears_reentry_counters(self, data: dict[str, Any]) -> None:
        assert "autodev-reentry-*-$CURRENT" in data["states"]["dequeue_next"]["action"]

    def test_record_reentry_exhausted_shape(self, data: dict[str, Any]) -> None:
        state = data["states"]["record_reentry_exhausted"]
        action = state["action"]
        assert "decision_unresolved" in action
        assert "autodev-skipped.txt" in action
        assert "rm -f ${context.run_dir}/autodev-inflight" in action
        assert "set-status" in action and "--reason decision_unresolved" in action
        assert "refine_failed" not in action
        assert state["next"] == "dequeue_next"


def _interp(action: str, run_dir: Path, issue_id: str) -> str:
    subs = {
        "context.run_dir": str(run_dir),
        "captured.input.output:shell": issue_id,
        "captured.input.output": issue_id,
        "context.readiness_threshold:shell": "85",
        "context.outcome_threshold:shell": "65",
    }
    return re.sub(r"\$\{([^}]+)\}", lambda m: subs[m.group(1)], action)


class _StubIssues:
    """Bash stub for ``ll-issues`` driven by files in a temp dir.

    ``flag`` holds the decision_needed value (absent file = unset), ``status`` the
    issue status; ``next-obligation`` prints ``obligation`` (default NONE) and exits
    ``next_rc``; ``check-flag`` exits ``flag_rc`` when set (2 simulates an
    unresolvable ID). Every call is appended to ``calls``.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "ll-issues").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> "{root}/calls"\n'
            'case "$1" in\n'
            f'  check-flag) if [ -f "{root}/flag_rc" ]; then exit "$(cat "{root}/flag_rc")"; fi\n'
            f'    [ -f "{root}/flag" ] && exit 0; exit 1;;\n'
            f'  next-obligation) if [ -f "{root}/obligation" ]; then cat "{root}/obligation"; '
            f'else echo NONE; fi; exit "$(cat "{root}/next_rc" 2>/dev/null || echo 0)";;\n'
            f'  show) printf \'{{"status": "%s"}}\' "$(cat "{root}/status" 2>/dev/null || echo open)";;\n'
            f'  refine-status) [ -f "{root}/refine_count" ] && '
            f'printf \'{{"refine_count": %s}}\' "$(cat "{root}/refine_count")"; exit 0;;\n'
            "  *) exit 0;;\n"
            "esac\n"
        )
        (self.bin / "ll-issues").chmod(0o755)

    def set_flag(self, on: bool) -> None:
        (self.root / "flag").write_text("true") if on else (self.root / "flag").unlink(
            missing_ok=True
        )

    def calls(self) -> list[str]:
        f = self.root / "calls"
        return f.read_text().splitlines() if f.exists() else []

    def set_refine_count(self, n: int) -> None:
        (self.root / "refine_count").write_text(str(n))

    def run(self, action: str, run_dir: Path, issue_id: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        # cwd is isolated so the selector never reads the repo's own .ll/ll-config.json
        cwd = self.root / "cwd"
        cwd.mkdir(exist_ok=True)
        return subprocess.run(
            ["bash", "-c", _interp(action, run_dir, issue_id)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=cwd,
        )


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    return d


@pytest.fixture
def stub(tmp_path: Path) -> _StubIssues:
    return _StubIssues(tmp_path)


@pytest.fixture
def states() -> dict[str, Any]:
    return _load_autodev_yaml()["states"]


class TestObligationSelectorBehavior:
    """ENH-3610: run the real selector actions under bash against a stub ll-issues."""

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    @pytest.mark.parametrize("issue_id", ["ENH-3610", "3610"])
    def test_flag_set_prints_decision_then_exhausted(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path, name: str, issue_id: str
    ) -> None:
        stub.set_flag(True)
        (run_dir / "autodev-staged.txt").write_text(f"OTHER-1\n{issue_id}\n")
        action = states[name]["action"]
        first = stub.run(action, run_dir, issue_id)
        assert first.returncode == 0, first.stderr
        assert first.stdout.strip() == "DECISION"
        assert (run_dir / f"autodev-reentry-DECISION-{issue_id}").read_text() == "1"
        # Un-staged before the token is printed; other IDs untouched.
        assert (run_dir / "autodev-staged.txt").read_text().splitlines() == ["OTHER-1"]
        # next-obligation is never consulted when the flag is set.
        assert not any(c.startswith("next-obligation") for c in stub.calls())
        second = stub.run(action, run_dir, issue_id)
        assert second.stdout.strip() == "DECISION_EXHAUSTED"

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    @pytest.mark.parametrize("flag_rc", [None, "2"])
    def test_flag_unset_or_unresolvable_falls_to_next_obligation(
        self,
        states: dict[str, Any],
        stub: _StubIssues,
        run_dir: Path,
        name: str,
        flag_rc: str | None,
    ) -> None:
        if flag_rc is not None:
            (stub.root / "flag_rc").write_text(flag_rc)
        result = stub.run(states[name]["action"], run_dir, "ENH-3610")
        assert result.returncode == 0
        assert result.stdout.strip() == "NONE"
        nxt = [c for c in stub.calls() if c.startswith("next-obligation")]
        expected = (
            "next-obligation ENH-3610 --format token --readiness-threshold 85 "
            "--outcome-threshold 65 --honor-waiver"
        )
        if name == "select_obligation_post_refine":
            # ENH-3611: the low-outcome selector passes the child's six tier-1 skips.
            expected += (
                " --skip FORMAT --skip VERIFY --skip HEDGES --skip PLACEHOLDERS"
                " --skip ACCEPTANCE_CRITERIA --skip DESIGN"
            )
        assert nxt == [expected]
        assert not list(run_dir.glob("autodev-reentry-*"))

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    def test_next_obligation_failure_is_nonzero_for_error_route(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path, name: str
    ) -> None:
        (stub.root / "next_rc").write_text("2")
        result = stub.run(states[name]["action"], run_dir, "ENH-3610")
        assert result.returncode == 2

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    @pytest.mark.parametrize(
        ("count", "expected"), [(3, "DECISION"), (4, "DECISION"), (5, "DECISION_EXHAUSTED")]
    )
    def test_lifetime_cap_boundary_default(
        self,
        states: dict[str, Any],
        stub: _StubIssues,
        run_dir: Path,
        name: str,
        count: int,
        expected: str,
    ) -> None:
        stub.set_flag(True)
        stub.set_refine_count(count)
        result = stub.run(states[name]["action"], run_dir, "BUG-3614")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected
        marker = run_dir / "autodev-reentry-DECISION-BUG-3614"
        if expected == "DECISION_EXHAUSTED":
            # Capped issue never consumes the one-shot marker; diagnostic is stderr-only.
            assert not marker.exists()
            assert f"[DECISION_CAPPED] BUG-3614 refine_count={count} cap=5" in result.stderr
            assert "DECISION_CAPPED" not in result.stdout
        else:
            assert marker.read_text() == "1"
            assert "DECISION_CAPPED" not in result.stderr

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    def test_lifetime_cap_honors_config_override(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path, name: str
    ) -> None:
        stub.set_flag(True)
        (stub.root / "cwd" / ".ll").mkdir(parents=True)
        (stub.root / "cwd" / ".ll" / "ll-config.json").write_text(
            '{"commands": {"max_refine_count": 7}}'
        )
        stub.set_refine_count(6)
        assert stub.run(states[name]["action"], run_dir, "BUG-1").stdout.strip() == "DECISION"
        stub.set_refine_count(7)
        result = stub.run(states[name]["action"], run_dir, "BUG-2")
        assert result.stdout.strip() == "DECISION_EXHAUSTED"
        assert "cap=7" in result.stderr

    @pytest.mark.parametrize(
        "name", ["select_obligation_post_refine", "select_obligation_pre_implement"]
    )
    def test_unreadable_refine_count_is_under_cap(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path, name: str
    ) -> None:
        stub.set_flag(True)  # no refine_count file: stub prints nothing
        result = stub.run(states[name]["action"], run_dir, "BUG-1")
        assert result.stdout.strip() == "DECISION"

    def test_decision_blocks_byte_identical(self, states: dict[str, Any]) -> None:
        def block(name: str) -> str:
            action = states[name]["action"]
            start = action.index('if [ "$RC" -eq 0 ]')
            return action[start : action.index("\nfi\n", start)]

        assert block("select_obligation_post_refine") == block("select_obligation_pre_implement")

    def test_dequeue_next_clears_reentry_counter(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        (run_dir / "autodev-reentry-DECISION-BUG-1").write_text("1")
        (run_dir / "autodev-reentry-DECISION-BUG-2").write_text("1")
        (run_dir / "autodev-queue.txt").write_text("BUG-1\n")
        result = stub.run(states["dequeue_next"]["action"], run_dir, "BUG-1")
        assert result.returncode == 0, result.stderr
        assert not (run_dir / "autodev-reentry-DECISION-BUG-1").exists()
        assert (run_dir / "autodev-reentry-DECISION-BUG-2").exists()


def _drive(
    states: dict[str, Any],
    stub: _StubIssues,
    run_dir: Path,
    start: str,
    child: Any,
    issue_id: str = "ENH-3610",
) -> list[str]:
    """Walk real selector/exhaustion states; every other state is a stub.

    ``child(stub)`` runs when the walk enters ``refine_current`` and models the
    refine-to-ready-issue child (it may clear or leave the decision flag). The
    walk ends at ``implement_current`` or ``dequeue_next``.
    """
    visited: list[str] = []
    node = start
    for _ in range(20):
        visited.append(node)
        if node in ("implement_current", "dequeue_next"):
            return visited
        if node == "refine_current":
            child(stub)
            (run_dir / "autodev-staged.txt").open("a").write(f"{issue_id}\n")  # check_passed
            node = "select_obligation_pre_implement"
            continue
        if node == "check_proof_defer_or_implement":
            node = "implement_current"
            continue
        state = states[node]
        result = stub.run(state["action"], run_dir, issue_id)
        if "route" in state:
            token = result.stdout.strip().splitlines()[-1] if result.returncode == 0 else "_error"
            route = state["route"]
            node = route.get(token, route["_"])
        else:
            node = state["next"]
    raise AssertionError(f"walk did not terminate: {visited}")


class TestDecisionReentryFlow:
    """ENH-3610: real-FSM walks over the selector states."""

    def test_flagged_issue_reenters_child_and_never_implements_with_flag(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        stub.set_flag(True)
        seen_at_implement: list[bool] = []

        def child(s: _StubIssues) -> None:
            s.set_flag(False)  # child resolves the decision before done

        visited = _drive(states, stub, run_dir, "select_obligation_pre_implement", child)
        seen_at_implement.append((stub.root / "flag").exists())
        assert visited[-1] == "implement_current"
        assert "refine_current" in visited
        assert seen_at_implement == [False]

    def test_check_passed_on_yes_catches_child_drift(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        """A drifted child reaches done with the flag set: the selector at
        check_passed.on_yes still catches it."""
        stub.set_flag(True)
        assert states["check_passed"]["on_yes"] == "select_obligation_pre_implement"
        visited = _drive(states, stub, run_dir, "select_obligation_pre_implement", lambda s: None)
        assert visited[0] == "select_obligation_pre_implement"
        assert "refine_current" in visited
        assert "implement_current" not in visited

    def test_child_leaving_flag_set_twice_exhausts_and_defers(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        stub.set_flag(True)
        (run_dir / "autodev-inflight").write_text("ENH-3610")
        visited = _drive(states, stub, run_dir, "select_obligation_pre_implement", lambda s: None)
        assert visited.count("refine_current") == 1
        assert visited[-2:] == ["record_reentry_exhausted", "dequeue_next"]
        assert "implement_current" not in visited
        stub_calls = stub.calls()
        assert (
            "set-status ENH-3610 deferred --by automation --reason decision_unresolved"
            in stub_calls
        )
        assert (run_dir / "autodev-skipped.txt").read_text().splitlines() == [
            "ENH-3610  decision_unresolved"
        ]
        assert "refine_failed" not in (run_dir / "autodev-skipped.txt").read_text()
        assert not (run_dir / "autodev-inflight").exists()
        assert "ENH-3610" not in (run_dir / "autodev-staged.txt").read_text().splitlines()

    def test_reentered_child_deferral_leaves_issue_unstaged(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        """A staged issue re-entered on DECISION whose child then stops
        (BLOCKED:decision_unresolved) must not be left staged, or finalize_done
        lists it in autodev-unverified.txt."""
        stub.set_flag(True)
        (run_dir / "autodev-staged.txt").write_text("ENH-3610\n")
        result = stub.run(states["select_obligation_pre_implement"]["action"], run_dir, "ENH-3610")
        assert result.stdout.strip() == "DECISION"
        assert "ENH-3610" not in (run_dir / "autodev-staged.txt").read_text().splitlines()
        # The finalize_done unverified set is derived from autodev-staged.txt.
        finalize = states["finalize_done"]["action"]
        assert "autodev-staged.txt" in finalize

    def test_flag_clear_takes_next_obligation_path_to_proof_gate(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        visited = _drive(states, stub, run_dir, "select_obligation_pre_implement", lambda s: None)
        assert visited == [
            "select_obligation_pre_implement",
            "check_proof_defer_or_implement",
            "implement_current",
        ]

    def test_exhaustion_does_not_overwrite_resolved_status(
        self, states: dict[str, Any], stub: _StubIssues, run_dir: Path
    ) -> None:
        """BUG-2729 guard: a done/completed/cancelled issue is left unchanged."""
        (stub.root / "status").write_text("done")
        result = stub.run(states["record_reentry_exhausted"]["action"], run_dir, "ENH-3610")
        assert result.returncode == 0, result.stderr
        assert not any(c.startswith("set-status") for c in stub.calls())
        assert (
            run_dir / "autodev-skipped.txt"
        ).read_text().strip() == "ENH-3610  decision_unresolved"


class TestChildDecisionInvariant:
    """ENH-3610: refine-to-ready-issue never reaches ``done`` with decision_needed set,
    except through write_broke_down."""

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_done_edges_pass_through_decision_gate(self, child: dict[str, Any]) -> None:
        assert child["check_missing_artifacts"]["on_yes"] == "check_decision_before_done"
        # ENH-3604: the score gates collapsed into the route_score_obligation dispatch.
        assert child["route_score_obligation"]["route"]["NONE"] == "check_decision_before_done"

    def test_only_gate_write_done_record_and_class_writers_reach_done(
        self, child: dict[str, Any]
    ) -> None:
        inbound = set()
        for name, state in child.items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            if "done" in targets:
                inbound.add(name)
        # write_broke_down is the documented exception; the rest are class-writing stops.
        assert "write_done_record" in inbound
        assert "write_broke_down" in inbound
        for name in ("route_score_obligation", "check_missing_artifacts"):
            assert name not in inbound

    def test_decision_gate_routes(self, child: dict[str, Any]) -> None:
        gate = child["check_decision_before_done"]
        assert "check-flag" in gate["action"] and "decision_needed" in gate["action"]
        assert gate["on_yes"] == "check_decide_attempts"
        # ENH-3611: the proof gate sits between the decision gate and the done record.
        assert gate["on_no"] == "check_proof_before_done"
        assert gate["on_error"] == "check_proof_before_done"
        proof = child["check_proof_before_done"]
        assert proof["on_yes"] == "run_spike"
        assert proof["on_no"] == "write_done_record"
        assert proof["on_error"] == "write_done_record"

    def test_run_record_write_moved_to_write_done_record(self, child: dict[str, Any]) -> None:
        assert "run-record write" in child["write_done_record"]["action"]
        assert child["write_done_record"]["next"] == "done"
        for name in ("route_score_obligation", "check_missing_artifacts"):
            assert "run-record write" not in child[name]["action"], name


class TestSpikeTriageStructural:
    """ENH-2640, moved by ENH-3611: the spike-remediation triad now lives in the
    refine-to-ready-issue child; autodev has none of it (stays-deleted guards)."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_spike_states_removed_from_autodev(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in ("check_spike_needed", "run_spike", "rerun_confidence_after_spike"):
            assert name not in states, f"{name} was removed from autodev by ENH-3611"

    def test_child_owns_spike_states(self, child: dict[str, Any]) -> None:
        for name in ("check_spike_needed", "run_spike", "route_spike_verdict"):
            assert name in child, f"{name} missing from refine-to-ready-issue.yaml"

    def test_child_check_spike_needed_predicate_reads_both_flags(
        self, child: dict[str, Any]
    ) -> None:
        """Predicate must be spike_needed AND NOT spike_attempted (two-field one-shot)."""
        action = child["check_spike_needed"].get("action", "")
        assert "spike_needed" in action
        assert "spike_attempted" in action
        assert child["check_spike_needed"]["on_no"] == "check_missing_artifacts"

    def test_child_run_spike_invokes_spike_skill(self, child: dict[str, Any]) -> None:
        state = child["run_spike"]
        assert "/ll:spike" in state.get("action", "")
        assert "--auto" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"


class TestDecidePathSpikeGate:
    """BUG-2654, reworked by ENH-3611: the post-size-review skip edge is protected by
    select_obligation_post_size_review (PROOF re-entry into the child) instead of
    autodev's own check_spike_needed_before_skip, which is gone."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_old_gate_stays_deleted(self, data: dict[str, Any]) -> None:
        assert "check_spike_needed_before_skip" not in data.get("states", {})

    def test_enqueue_or_skip_routes_to_post_size_review_selector(
        self, data: dict[str, Any]
    ) -> None:
        state = data["states"]["enqueue_or_skip"]
        assert state.get("on_no") == "check_parent_resolved_post_size_review"
        resolved_gate = data["states"]["check_parent_resolved_post_size_review"]
        assert resolved_gate.get("on_no") == "select_obligation_post_size_review"
        assert resolved_gate.get("on_error") == "select_obligation_post_size_review"
        selector = data["states"]["select_obligation_post_size_review"]
        assert selector["route"]["PROOF"] == "refine_current"
        assert selector["route"]["_"] == "check_reconcile_needed"
        assert selector["route"]["_error"] == "recheck_after_size_review"

    def test_selector_guards_a_spikeable_issue_only(self, data: dict[str, Any]) -> None:
        """The selector reads the same two-field predicate the old gate did
        (spike_needed AND NOT spike_attempted) plus the shared budget."""
        action = data["states"]["select_obligation_post_size_review"]["action"]
        assert "spike_needed" in action
        assert "spike_attempted" in action
        assert "spike-runs-" in action


class TestReconcilePlateauStructural:
    """ENH-2689: structural assertions on the post-spike reconcile plateau triad
    (check_reconcile_needed / reconcile_current / rerun_confidence_after_reconcile).

    Mirrors TestDecidePathSpikeGate for the sibling gate that catches a
    "spike ran but Readiness is bit-identical" plateau and routes one
    /ll:reconcile-issue pass before the low_readiness deferral.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_reconcile_states_exist(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in (
            "check_reconcile_needed",
            "reconcile_current",
            "rerun_confidence",
        ):
            assert name in states, f"{name} missing from autodev.yaml (ENH-2689)"

    def test_post_size_review_selector_routes_to_reconcile_gate(self, data: dict[str, Any]) -> None:
        """ENH-3611: select_obligation_post_size_review's `_` (the retired
        check_spike_needed_before_skip's slot) interposes the reconcile gate."""
        state = data["states"]["select_obligation_post_size_review"]
        assert state["route"]["_"] == "check_reconcile_needed"

    def test_reconcile_predicate_reads_snapshot_and_guard(self, data: dict[str, Any]) -> None:
        """Predicate: pre-refine snapshot == current Readiness AND NOT reconcile_attempted."""
        state = data["states"]["check_reconcile_needed"]
        action = state.get("action", "")
        assert state.get("fragment") == "shell_exit"
        assert "autodev-pre-readiness.txt" in action
        assert "autodev-pre-spike-readiness.txt" not in action  # ENH-3611
        assert "confidence" in action
        assert "reconcile_attempted" in action, (
            "reconcile gate must read reconcile_attempted for the one-shot guard (AC 3)"
        )

    def test_reconcile_gate_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_reconcile_needed"]
        assert state.get("on_yes") == "reconcile_current", "plateau must reach reconcile (AC 1)"
        # BUG-2734: non-plateau now routes through check_guard2_verdict (which
        # itself falls through to recheck_after_size_review on no guard-2 match) —
        # this still preserves the BUG-1230 leaf-skip terminus, just one hop later.
        # BUG-2744: interposed check_size_review_ran_this_pass, a runtime marker
        # gate that bypasses check_guard2_verdict when run_size_review didn't
        # execute for the current issue this pass (stale cross-issue captured
        # state otherwise readable by check_guard2_verdict — see
        # TestGuard2VerdictBypass below).
        assert state.get("on_no") == "check_size_review_ran_this_pass"
        assert state.get("on_error") == "recheck_after_size_review"
        gate_state = data["states"]["check_size_review_ran_this_pass"]
        assert gate_state.get("on_yes") == "check_guard2_verdict"
        assert gate_state.get("on_no") == "recheck_after_size_review"
        # BUG-3390: fails CLOSED — unverifiable provenance must never evaluate
        # a possibly-stale prior-issue capture.
        assert gate_state.get("on_error") == "recheck_after_size_review"
        guard2_state = data["states"]["check_guard2_verdict"]
        # BUG-2752: no-match now routes through check_guard2_score_fallback (which
        # itself falls through to recheck_after_size_review) before the terminus.
        assert guard2_state.get("on_no") == "check_guard2_score_fallback"
        assert guard2_state.get("on_error") == "recheck_after_size_review"
        fallback_state = data["states"]["check_guard2_score_fallback"]
        assert fallback_state.get("on_no") == "recheck_after_size_review"
        assert fallback_state.get("on_error") == "recheck_after_size_review"

    def test_reconcile_current_invokes_skill(self, data: dict[str, Any]) -> None:
        state = data["states"]["reconcile_current"]
        assert "/ll:reconcile-issue" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        # FEAT-2751: routes through the repair-cycle counter state before the
        # confidence rerun.
        assert state.get("next") == "count_repair_cycle_reconcile"
        assert state.get("on_error") == "count_repair_cycle_reconcile"
        assert state.get("on_rate_limit_exhausted") == "finalize_rate_limited"
        counter_state = data["states"]["count_repair_cycle_reconcile"]
        assert counter_state.get("next") == "clear_scores"
        assert counter_state.get("on_error") == "clear_scores"

    def test_rerun_confidence_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["rerun_confidence"]
        assert "/ll:confidence-check" in state.get("action", "")
        # BUG-3588/ENH-3615: routes through the presence gate, then route_after_rescore
        # forwards the reconcile origin to recheck_after_size_review
        assert state.get("next") == "check_scores_present"
        assert state.get("on_error") == "check_scores_present"
        assert data["states"]["route_after_rescore"]["route"]["RECONCILE"] == (
            "recheck_after_size_review"
        )


class TestReconcilePlateauRouting:
    """ENH-2689: FSMExecutor-driven assertions on the reconcile gate routing.

    Mirrors TestCheckDecisionAtDequeueRouting's mini-FSM shape: the gate must
    fire reconcile_current on a plateau (exit 0) and fall through to
    recheck_after_size_review when there is no plateau (exit 1) or on error.
    """

    @pytest.fixture
    def reconcile_chain_fsm(self) -> Any:
        return _loop(
            name="autodev-reconcile-gate-mini",
            initial="select_obligation_post_size_review",
            states={
                # ENH-3611: the selector's `_` route (classify token `_`) enters the
                # reconcile gate; modelled here as a shell gate that always falls through.
                "select_obligation_post_size_review": _state(
                    action="false",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="refine_current",
                    on_no="check_reconcile_needed",
                    on_error="recheck_after_size_review",
                ),
                "check_reconcile_needed": _state(
                    action="reconcile-predicate",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="reconcile_current",
                    on_no="recheck_after_size_review",
                    on_error="recheck_after_size_review",
                ),
                "refine_current": _state(action="true", action_type="shell", next="done"),
                "reconcile_current": _state(action="true", action_type="shell", next="done"),
                "recheck_after_size_review": _state(
                    action="true", action_type="shell", next="done"
                ),
                "done": _state(terminal=True),
            },
        )

    def test_plateau_routes_to_reconcile(self, reconcile_chain_fsm: Any) -> None:
        """Snapshot == current AND not attempted (exit 0) → reconcile_current fires
        before any low_readiness deferral."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 0}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "reconcile_current" in visited, f"visited={visited!r}"
        assert "recheck_after_size_review" not in visited, (
            f"reconcile must precede (and here replace) the skip; visited={visited!r}"
        )

    def test_no_plateau_falls_through_to_recheck(self, reconcile_chain_fsm: Any) -> None:
        """No plateau (exit 1) → recheck_after_size_review, reconcile skipped (AC 4)."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 1}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "reconcile_current" not in visited, f"visited={visited!r}"

    def test_predicate_error_falls_through_to_recheck(self, reconcile_chain_fsm: Any) -> None:
        """Predicate error (exit 2) fail-opens to recheck_after_size_review."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 2, "stderr": "boom"}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "reconcile_current" not in visited, f"visited={visited!r}"


class TestDesignGateRefineRemedy:
    """BUG-3002: a Program-Design-only gate failure must route to a dedicated
    refine_for_design remedy — /ll:reconcile-issue's contract explicitly
    excludes ## Program Design, so the pre-fix reconcile_current remedy could
    never touch the section whose failure triggered it."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_refine_for_design_states_exist(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in (
            "refine_for_design",
            "count_repair_cycle_refine_for_design",
            "dispatch_design_remedy",
        ):
            assert name in states, f"{name} missing from autodev.yaml (BUG-3002)"

    def test_refine_for_design_invokes_skill(self, data: dict[str, Any]) -> None:
        """Structural mirror of test_reconcile_current_invokes_skill."""
        state = data["states"]["refine_for_design"]
        action = state.get("action", "")
        assert "/ll:refine-issue" in action
        assert "--auto" in action and "--gap-analysis" in action
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "count_repair_cycle_refine_for_design"
        assert state.get("on_error") == "count_repair_cycle_refine_for_design"
        assert state.get("on_rate_limit_exhausted") == "finalize_rate_limited"
        counter_state = data["states"]["count_repair_cycle_refine_for_design"]
        assert counter_state.get("next") == "clear_scores"
        assert counter_state.get("on_error") == "clear_scores"

    def test_counter_state_writes_design_remedy_attempted_marker(
        self, data: dict[str, Any]
    ) -> None:
        action = data["states"]["count_repair_cycle_refine_for_design"]["action"]
        assert "autodev-repair-cycle-count.txt" in action
        assert "autodev-design-remedy-attempted-$ID" in action

    def test_marker_not_cleared_at_dequeue_next(self, data: dict[str, Any]) -> None:
        """Per-issue-scoped by filename, like autodev-design-gate-failed-$ID —
        clearing it per dequeue would let one issue take two refine passes."""
        action = data["states"]["dequeue_next"]["action"]
        assert "autodev-design-remedy-attempted" not in action

    def test_dispatch_design_remedy_routes_refine_design_token(self, data: dict[str, Any]) -> None:
        state = data["states"]["dispatch_design_remedy"]
        assert "refine_design" in state.get("action", "")
        assert state.get("on_yes") == "refine_for_design"
        assert state.get("on_no") == "dispatch_pre_deferral_remedy"
        assert state.get("on_error") == "dispatch_pre_deferral_remedy"

    def test_check_pre_deferral_remedy_routes_through_design_gate_first(
        self, data: dict[str, Any]
    ) -> None:
        """dispatch_design_remedy must be chained BEFORE
        dispatch_pre_deferral_remedy — that state rm -f's the remedy token
        before routing, so a gate placed downstream would always observe an
        empty token and silently fall back to reconcile_current."""
        assert data["states"]["check_pre_deferral_remedy"].get("on_yes") == "dispatch_design_remedy"

    def test_dispatch_pre_deferral_remedy_plateau_routing_unmodified(
        self, data: dict[str, Any]
    ) -> None:
        """The plateau path (spike/reconcile tokens) still resolves via
        dispatch_pre_deferral_remedy; ENH-3611 retargeted the spike leg from the
        removed run_spike to refine_current (child re-entry, interim until ENH-3606)."""
        state = data["states"]["dispatch_pre_deferral_remedy"]
        assert state.get("on_yes") == "refine_current"
        assert state.get("on_no") == "reconcile_current"
        assert state.get("on_error") == "reconcile_current"


class TestAtomicDesignRemedyRouting:
    """BUG-3002: FSMExecutor-driven mini-FSM mirroring TestReconcilePlateauRouting's
    shape — drives check_atomic_design_remedy → refine_for_design →
    count_repair_cycle_refine_for_design and asserts refine_for_design fires
    (never reconcile_current) for the design-gate-pending case."""

    @pytest.fixture
    def design_remedy_fsm(self) -> Any:
        return _loop(
            name="autodev-design-remedy-mini",
            initial="check_atomic_design_remedy",
            states={
                "check_atomic_design_remedy": _state(
                    action="pending-marker",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="refine_for_design",
                    on_no="dequeue_next",
                    on_error="dequeue_next",
                ),
                "refine_for_design": _state(
                    action="true", action_type="shell", next="count_repair_cycle_refine_for_design"
                ),
                "count_repair_cycle_refine_for_design": _state(
                    action="true", action_type="shell", next="done"
                ),
                "reconcile_current": _state(action="true", action_type="shell", next="done"),
                "dequeue_next": _state(action="true", action_type="shell", next="done"),
                "done": _state(terminal=True),
            },
        )

    def test_design_remedy_pending_routes_to_refine_for_design(
        self, design_remedy_fsm: Any
    ) -> None:
        runner = _StubRunner(results=[("pending-marker", {"exit_code": 0})])
        _result, visited = _run_decision_chain(design_remedy_fsm, runner)
        assert "refine_for_design" in visited, f"visited={visited!r}"
        assert "count_repair_cycle_refine_for_design" in visited, f"visited={visited!r}"
        assert "reconcile_current" not in visited, f"visited={visited!r}"

    def test_no_pending_remedy_falls_through_to_dequeue(self, design_remedy_fsm: Any) -> None:
        runner = _StubRunner(results=[("pending-marker", {"exit_code": 1})])
        _result, visited = _run_decision_chain(design_remedy_fsm, runner)
        assert "dequeue_next" in visited, f"visited={visited!r}"
        assert "refine_for_design" not in visited, f"visited={visited!r}"


class TestGuard2VerdictBypass:
    """BUG-2744 / BUG-3390: FSMExecutor-driven assertions that
    check_size_review_ran_this_pass bypasses check_guard2_verdict unless
    run_size_review executed for the current issue this pass (proven by the
    positive ``autodev-size-review-ran-this-pass`` marker), preventing a stale
    prior-issue ``captured.size_review_output`` from being evaluated.

    Mirrors TestReconcilePlateauRouting's mini-FSM shape, standing in for the
    real check_reconcile_needed → check_size_review_ran_this_pass →
    check_guard2_verdict chain.
    """

    @pytest.fixture
    def guard2_bypass_fsm(self) -> Any:
        return _loop(
            name="autodev-guard2-bypass-mini",
            initial="check_reconcile_needed",
            states={
                "check_reconcile_needed": _state(
                    action="false",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="reconcile_current",
                    on_no="check_size_review_ran_this_pass",
                    on_error="recheck_after_size_review",
                ),
                "check_size_review_ran_this_pass": _state(
                    action="marker-check",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="check_guard2_verdict",
                    on_no="recheck_after_size_review",
                    on_error="recheck_after_size_review",
                ),
                "reconcile_current": _state(action="true", action_type="shell", next="done"),
                "check_guard2_verdict": _state(action="true", action_type="shell", next="done"),
                "recheck_after_size_review": _state(
                    action="true", action_type="shell", next="done"
                ),
                "done": _state(terminal=True),
            },
        )

    def test_shortcut_this_pass_bypasses_guard2(self, guard2_bypass_fsm: Any) -> None:
        """Positive marker absent (run_size_review did not run this pass, exit 1) →
        recheck_after_size_review directly; check_guard2_verdict never visited,
        so it can never evaluate a prior issue's stale captured output."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("marker-check", {"exit_code": 1}),
            ]
        )
        _result, visited = _run_decision_chain(guard2_bypass_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "check_guard2_verdict" not in visited, f"visited={visited!r}"

    def test_normal_pass_reaches_guard2(self, guard2_bypass_fsm: Any) -> None:
        """Positive marker present (run_size_review ran this pass, exit 0) →
        check_guard2_verdict fires as before."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("marker-check", {"exit_code": 0}),
            ]
        )
        _result, visited = _run_decision_chain(guard2_bypass_fsm, runner)
        assert "check_guard2_verdict" in visited, f"visited={visited!r}"

    def test_marker_check_error_fails_closed_to_recheck(self, guard2_bypass_fsm: Any) -> None:
        """BUG-3390: a marker-check error fails CLOSED to recheck_after_size_review —
        unverifiable provenance must never evaluate a possibly-stale capture."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("marker-check", {"exit_code": 2, "stderr": "boom"}),
            ]
        )
        _result, visited = _run_decision_chain(guard2_bypass_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "check_guard2_verdict" not in visited, f"visited={visited!r}"


class TestAssertDecisionClearedStructural:
    """BUG-2595 / ENH-3075 / ENH-3611: the post-decide decision-gate re-check
    (``assert_decision_cleared``) lives in ``oracles/resolve-decision.yaml`` and the
    caller-side chain (``recheck_after_decide``, ``record_decision_unresolved``) was
    removed from ``autodev.yaml`` by ENH-3611 — the refine-to-ready-issue child owns
    decision repair (``check_decision_before_done``) and autodev's selectors re-enter
    it. This class guards the removals and the child-side contract that replaced them.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_recheck_after_decide_stays_deleted(self, data: dict[str, Any]) -> None:
        """ENH-3611: recheck_after_decide (and its ENH-3075 on_yes retarget) is gone;
        the pre-implement selector -> check_proof_defer_or_implement is the only
        route into implement_current."""
        states = data["states"]
        assert "recheck_after_decide" not in states
        assert states["select_obligation_pre_implement"]["route"]["_"] == (
            "check_proof_defer_or_implement"
        )

    def test_assert_decision_cleared_absent_from_autodev_states(self, data: dict[str, Any]) -> None:
        """ENH-3075: assert_decision_cleared moved into
        oracles/resolve-decision.yaml and must leave no dangling reference or
        stale definition behind in autodev.yaml's own states block."""
        states = data.get("states", {})
        assert "assert_decision_cleared" not in states, (
            "assert_decision_cleared must be deleted from autodev.yaml's states "
            "block — it now lives in oracles/resolve-decision.yaml (ENH-3075)"
        )
        for name, state in states.items():
            for edge in ("on_yes", "on_no", "on_error", "on_success", "on_failure", "next"):
                assert state.get(edge) != "assert_decision_cleared", (
                    f"{name}.{edge} still references deleted state "
                    "assert_decision_cleared (ENH-3075)"
                )

    def test_record_decision_unresolved_stays_deleted_from_autodev(
        self, data: dict[str, Any]
    ) -> None:
        """ENH-3611: autodev's record_decision_unresolved is gone; the surviving
        decision deferral is record_reentry_exhausted (ledgers decision_unresolved)."""
        assert "record_decision_unresolved" not in data["states"]
        assert "decision_unresolved" in data["states"]["record_reentry_exhausted"]["action"]

    def test_child_record_decision_unresolved_advances_and_defers(
        self, child: dict[str, Any]
    ) -> None:
        """The child's record_decision_unresolved keeps the old autodev contract:
        ledger to autodev-decision-unresolved.txt (ENH-2666 deferral via set-status)
        and stop, so autodev sees BLOCKED:decision_unresolved."""
        state = child["record_decision_unresolved"]
        action = state["action"]
        assert "autodev-decision-unresolved.txt" in action
        assert "/ll:decide-issue" in action
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason decision_unresolved" in action
        assert state["next"] == "failed"


# ENH-2717's check_decision_after_decide_error is deleted (ENH-3075): its
# short-circuit collapses into oracles/resolve-decision.yaml's
# assert_decision_cleared, which every run_decide exit path (success or
# error) now reaches directly. The 5 routing assertions that used to live in
# TestCheckDecisionAfterDecideErrorStructural are replaced by
# test_run_decide_on_error_routes_to_assert_decision_cleared in
# TestResolveDecisionOracle (test_builtin_loops.py), modeled on
# test_run_decide_and_assert_decision_cleared_routing /
# test_assert_decision_cleared_terminal_contract in that same test class.


class TestAssertDecisionClearedRouting:
    """BUG-2595, re-rooted by ENH-3611: a still-armed decision flag must never reach
    implement_current. The old synthetic recheck_after_decide mini-FSM is replaced by
    real-state walks through the selectors (``TestDecisionReentryFlow`` covers the
    armed/cleared paths); this class pins the invariant on the real routing table."""

    def test_selector_decision_route_never_targets_implement(self) -> None:
        states = _load_autodev_yaml()["states"]
        for name in ("select_obligation_post_refine", "select_obligation_pre_implement"):
            route = states[name]["route"]
            assert route["DECISION"] == "refine_current"
            assert route["DECISION_EXHAUSTED"] == "record_reentry_exhausted"

    def test_implement_current_only_reached_via_proof_defer_state(self) -> None:
        states = _load_autodev_yaml()["states"]
        preds = set()
        for name, state in states.items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            if "implement_current" in targets:
                preds.add(name)
        assert preds == {"check_proof_defer_or_implement"}
