"""Tests for the prepare-issue dispatch loop and its autodev boundary (ENH-3623).

Structural pins on ``prepare-issue.yaml`` (the 16-state dispatch loop over
``little_loops.preparation_policy``), the autodev side of the cutover (the 42 removed
states, the boundary retargets, the pass-id write), and real-FSM runs of the step
cap and of rate-limit exhaustion in every wrapper slash state.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.fsm.validation import load_and_validate
from little_loops.preparation_policy import DONE_FACT_CAP, MAX_STEPS
from tests.autodev_harness import SlashResponse, run_autodev
from tests.preparation_policy_harness import DELETED_STATES, MOVED_STATES, state_targets
from tests.test_autodev_characterization import (
    APPLY,
    CHILD,
    INFRA_PATH,
    LOW_READINESS,
    RATE_LIMITED_PATH,
    SCENARIOS,
    _assert_hermetic,
    done,
    step,
)

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
WRAPPER = LOOPS_DIR / "prepare-issue.yaml"
AUTODEV = LOOPS_DIR / "autodev.yaml"
ID = "ENH-9001"

STATES = (
    "select_step",
    "run_child",
    "run_wire",
    "run_refine_gap",
    "run_rescore",
    "run_reconcile",
    "run_size_review",
    "classify_guard2",
    "record_guard2",
    "record_step",
    "run_go_no_go",
    "run_advise_go_no_go",
    "apply_outcome",
    "mark_rate_limited",
    "done",
    "failed",
)
SLASH_STATES = {
    "run_wire": "wire-issue",
    "run_refine_gap": "refine-issue",
    "run_rescore": "confidence-check",
    "run_reconcile": "reconcile-issue",
    "run_size_review": "issue-size-review",
    "run_go_no_go": "go-no-go",
}


@pytest.fixture(scope="module")
def data() -> dict:
    return yaml.safe_load(WRAPPER.read_text())


@pytest.fixture(scope="module")
def autodev() -> dict:
    return yaml.safe_load(AUTODEV.read_text())


def _actions(data: dict) -> dict[str, str]:
    return {n: s["action"] for n, s in data["states"].items() if isinstance(s.get("action"), str)}


class TestStructure:
    def test_validates(self) -> None:
        fsm, errors = load_and_validate(WRAPPER, raise_on_error=False)
        assert errors == []
        assert fsm.initial == "select_step"

    def test_exactly_sixteen_states_stated_and_pinned(self, data: dict) -> None:
        assert tuple(data["states"]) == STATES
        assert "Exactly 16 states" in WRAPPER.read_text()

    def test_max_steps_is_derived_from_the_ladder_budget(self, data: dict) -> None:
        """4 states per SIZE_REVIEW step (3 per command step) plus the 3-state tail."""
        assert MAX_STEPS == 4 * DONE_FACT_CAP + 3
        assert data["max_steps"] == MAX_STEPS
        assert data["on_max_steps"] == "apply_outcome"

    def test_no_rm_anywhere(self, data: dict) -> None:
        for name, action in _actions(data).items():
            assert not re.search(r"(^|[\s;&|(])rm\s", action), name

    def test_never_writes_the_staged_ledger(self, data: dict) -> None:
        for name, action in _actions(data).items():
            assert "autodev-staged" not in action, name

    def test_prep_apply_is_the_only_terminal_writer(self, data: dict) -> None:
        """Every shell action calls `ll-issues prep` — except (ENH-3590)
        run_advise_go_no_go, which calls the shipped `ll-issues advise-consult`
        helper directly — and only apply_outcome / mark_rate_limited call
        `prep apply` (ledger row, status, run record)."""
        writers = set()
        for name, action in _actions(data).items():
            if data["states"][name].get("action_type") == "slash_command":
                continue
            if name == "run_advise_go_no_go":
                assert "ll-issues advise-consult " in action, name
            else:
                assert "ll-issues prep " in action, name
            assert ">" not in action and "set-status" not in action, name
            assert "run-record" not in action, name
            if "ll-issues prep apply" in action:
                writers.add(name)
        assert writers == {"apply_outcome", "mark_rate_limited"}

    def test_record_step_never_reads_the_child_capture(self, data: dict) -> None:
        """prep record classifies from the child's run record, not captured.run_child
        (a stale failure_terminal capture cannot reach it)."""
        assert "captured" not in data["states"]["record_step"]["action"]
        assert "captured" not in data["states"]["record_guard2"]["action"]

    def test_every_slash_state_halts_through_mark_rate_limited(self, data: dict) -> None:
        slash = {n for n, s in data["states"].items() if s.get("action_type") == "slash_command"}
        assert slash == set(SLASH_STATES)
        for name in slash:
            state = data["states"][name]
            assert state["fragment"] == "with_rate_limit_handling", name
            assert state["on_rate_limit_exhausted"] == "mark_rate_limited", name
        assert "--rate-limited" in data["states"]["mark_rate_limited"]["action"]

    def test_run_child_is_a_plain_loop_state(self, data: dict) -> None:
        state = data["states"]["run_child"]
        assert state["loop"] == "refine-to-ready-issue"
        assert state["context_passthrough"] is True
        for key in ("timeout", "fragment", "on_rate_limit_exhausted", "on_no"):
            assert key not in state, key
        assert state["on_yes"] == state["on_failure"] == state["on_error"] == "record_step"

    def test_every_step_kind_routes_and_errors_fall_to_apply(self, data: dict) -> None:
        route = data["states"]["select_step"]["route"]
        assert route["_"] == route["_error"] == route["FINISH"] == route["STOP"] == "apply_outcome"
        for kind in (
            "RUN_CHILD",
            "WIRE",
            "REFINE_GAP",
            "RESCORE",
            "RECONCILE",
            "SIZE_REVIEW",
            "ADVISE_GO_NO_GO",
        ):
            assert route[kind] in data["states"]

    def test_classify_guard2_reads_the_capture_through_evaluate_source(self, data: dict) -> None:
        """BUG-2594: the size-review output is matched via evaluate.source, never
        interpolated into a shell action."""
        state = data["states"]["classify_guard2"]
        assert "action" not in state
        assert state["evaluate"]["type"] == "output_contains"
        assert state["evaluate"]["source"] == "${captured.size_review_output.output}"
        assert (state["on_yes"], state["on_no"], state["on_error"]) == (
            "record_guard2",
            "record_step",
            "record_step",
        )

    @pytest.mark.parametrize(
        ("output", "guard2"),
        [
            ("[ENH-1] skipped: score 9 (Very Large) - atomic", True),
            ("FEAT-021 skipped: score 11 (Very Large) — single atomic change", True),
            ("declined decomposition: score 9", True),
            ("score 8 (Very Large)", True),
            ("score 10", True),
            ("[ENH-1] skipped: structural score 6 (Medium)", False),
            ("score 5", False),
            ("[ENH-1] skipped: structural score 3 (Small) - leaf-sized", False),
            ("score 80 points", False),
        ],
    )
    def test_classify_guard2_pattern(self, data: dict, output: str, guard2: bool) -> None:
        """BUG-2734/BUG-2752: guard-2 = a Very Large (8-11) score, whatever the wording."""
        pattern = data["states"]["classify_guard2"]["evaluate"]["pattern"]
        assert bool(re.search(pattern, output)) is guard2

    def test_terminals(self, data: dict) -> None:
        states = data["states"]
        assert states["done"] == {"terminal": True}
        assert states["failed"] == {"terminal": True, "failure": True}
        assert states["apply_outcome"]["on_yes"] == "done"
        assert states["apply_outcome"]["on_no"] == states["apply_outcome"]["on_error"] == "failed"

    def test_scope_declared_and_no_context_block(self, data: dict) -> None:
        assert data["scope"]
        assert "context" not in data


class TestAutodevBoundary:
    def test_move_set_size(self) -> None:
        assert len(MOVED_STATES) == 39
        assert len(DELETED_STATES) == len(set(DELETED_STATES)) == 42

    @pytest.mark.parametrize("state", DELETED_STATES)
    def test_removed_state_is_absent(self, autodev: dict, state: str) -> None:
        assert state not in autodev["states"]

    def test_no_edge_targets_a_removed_or_missing_state(self, autodev: dict) -> None:
        st = autodev["states"]
        dangling = sorted({(n, t) for n, s in st.items() for t in state_targets(s) if t not in st})
        assert dangling == []

    def test_boundary_retargets(self, autodev: dict) -> None:
        st = autodev["states"]
        assert st["refine_current"]["loop"] == "prepare-issue"
        assert st["refine_current"]["on_success"] == "copy_broke_down"
        assert st["refine_current"]["on_failure"] == "route_refine_outcome"
        assert st["refine_current"]["on_error"] == "skip_inflight_infra"
        assert "on_no" not in st["refine_current"]  # BUG-2611
        cp = st["check_passed"]
        assert cp["on_yes"] == "check_proof_defer_or_implement"
        assert cp["on_no"] == cp["on_cannot_judge"] == "skip_inflight"
        assert cp["on_error"] == "skip_inflight_infra"
        assert "check-design" in cp["action"]  # ENH-3625 Rule A stays
        assert st["detect_children"]["on_no"] == "check_parent_resolved"
        assert st["detect_children"]["on_error"] == "check_parent_resolved"
        assert st["check_parent_resolved"]["on_no"] == "skip_inflight"
        assert st["check_parent_resolved"]["on_error"] == "skip_inflight_infra"

    def test_capture_reachability_ok_dropped_and_step_cap_kept(self, autodev: dict) -> None:
        assert "capture_reachability_ok" not in autodev
        assert autodev["max_steps"] == 500

    def test_dequeue_next_writes_the_pass_id(self, autodev: dict) -> None:
        action = autodev["states"]["dequeue_next"]["action"]
        assert "prep-pass-$CURRENT" in action
        assert action.index("autodev-inflight") < action.index("prep-pass-$CURRENT")

    def test_copy_broke_down_only_resets_the_child_flag(self, autodev: dict) -> None:
        action = autodev["states"]["copy_broke_down"]["action"]
        assert action.strip() == "printf '0' > ${context.run_dir}/refine-broke-down"
        assert "autodev-broke-down" not in AUTODEV.read_text()

    def test_no_autodev_state_runs_a_ladder_command(self, autodev: dict) -> None:
        """No autodev event enters a policy-owned step: the ladder's slash commands
        run only inside prepare-issue."""
        for name, state in autodev["states"].items():
            action = state.get("action") or ""
            for skill in SLASH_STATES.values():
                assert f"/ll:{skill}" not in action, (name, skill)

    def test_every_characterization_path_avoids_removed_states(self) -> None:
        for scenario, expected in SCENARIOS:
            assert not set(expected.path) & set(DELETED_STATES), scenario.name


# ---------------------------------------------------------------------------
# Real-FSM runs (autodev -> prepare-issue -> stub refine-to-ready-issue)
# ---------------------------------------------------------------------------

_RATE_LIMITED = SlashResponse(output="API Error: 429 rate limit exceeded", exit_code=1)
_BASE = next(s for s, _ in SCENARIOS if s.name == "readiness_stagnated")


def _slash_upto(kind: str) -> tuple[dict[str, tuple[SlashResponse, ...]], dict[str, Any], str]:
    """Scripted responses that reach *kind*'s slash command first, then 429 it."""
    from tests.test_autodev_characterization import (
        LADDER_TO_RECONCILE,
        LOW_OUTCOME,
        NOOP,
        SIZE_REVIEW_GUARD2,
        confidence,
    )

    if kind == "run_size_review":
        return {"issue-size-review": (_RATE_LIMITED,)}, LOW_READINESS, "issue-size-review"
    if kind == "run_reconcile":
        return (
            {**LADDER_TO_RECONCILE, "reconcile-issue": (_RATE_LIMITED,)},
            LOW_READINESS,
            "reconcile-issue",
        )
    if kind == "run_rescore":
        return (
            {**LADDER_TO_RECONCILE, "confidence-check": (_RATE_LIMITED,)},
            LOW_READINESS,
            "confidence-check",
        )
    if kind == "run_wire":
        slash = {"issue-size-review": (SIZE_REVIEW_GUARD2,), "wire-issue": (_RATE_LIMITED,)}
        return slash, LOW_OUTCOME, "wire-issue"
    if kind == "run_go_no_go":
        slash = {
            "issue-size-review": (SIZE_REVIEW_GUARD2,),
            "wire-issue": (NOOP,),
            "confidence-check": (confidence(90, 50),),
            "go-no-go": (_RATE_LIMITED,),
        }
        return slash, LOW_OUTCOME, "go-no-go"
    if kind == "run_refine_gap":
        slash = {"wire-issue": (NOOP,), "refine-issue": (_RATE_LIMITED,)}
        return slash, {**LOW_READINESS, "missing_artifacts": True}, "refine-issue"
    raise AssertionError(kind)  # pragma: no cover


@pytest.mark.slow
@pytest.mark.timeout(300)
@pytest.mark.parametrize("kind", sorted(SLASH_STATES))
def test_rate_limit_exhaustion_halts_autodev_per_step_kind(
    kind: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rate-limit exhaustion in any wrapper slash state halts autodev through
    mark_rate_limited -> finalize_rate_limited (BUG-3622 + terminal table)."""
    slash, frontmatter, skill = _slash_upto(kind)
    scenario = replace(_BASE, name=f"rate_limit_{kind}", frontmatter=frontmatter, slash=slash)
    r = run_autodev(scenario, tmp_path, monkeypatch)
    assert r.unscripted == []
    assert r.cli_failures == []
    assert tuple(r.path) == RATE_LIMITED_PATH
    assert r.wrapper_path[-1] == "mark_rate_limited"
    assert r.wrapper_path.count(kind) == 12  # the retry loop ran to exhaustion
    assert r.slash_commands.count(f"{skill} {ID}") == 12
    assert r.records == {ID: "RETRYABLE_ERROR:rate_limited"}
    assert r.summary["stop_reason"] == "rate_limit"


@pytest.mark.slow
@pytest.mark.timeout(300)
def test_step_cap_records_infra_and_reaches_skip_inflight_infra(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrapper step-cap cutoff runs apply_outcome once as the on_max_steps handler
    (no open FINISH/STOP intent -> RETRYABLE_ERROR:infra), finishes
    terminated_by=max_steps, and autodev routes on_failure -> route_refine_outcome ->
    skip_inflight_infra (accepted change 5: refine_failed_infra)."""
    wrapper = tmp_path / "prepare-issue-capped.yaml"
    wrapper.write_text(re.sub(r"(?m)^max_steps: \d+$", "max_steps: 4", WRAPPER.read_text()))
    root = tmp_path / "run"
    root.mkdir()
    scenario = replace(_BASE, name="wrapper_step_cap", inner_runs={ID: (done(),)})
    r = run_autodev(scenario, root, monkeypatch, prepare_issue_yaml=wrapper)
    _assert_hermetic(r)
    # select_step -> run_child -> record_step -> select_step hits the cap; the
    # handler runs apply_outcome without taking its done/failed edge.
    assert tuple(r.wrapper_path) == (*CHILD, "select_step", "apply_outcome")
    assert tuple(r.path) == INFRA_PATH
    assert r.records == {ID: "RETRYABLE_ERROR:infra"}
    assert tuple(r.skipped) == (f"{ID}  refine_failed_infra",)
    assert r.slash_commands == []


def test_segment_helpers() -> None:
    assert (*CHILD, *APPLY) == (
        "select_step",
        "run_child",
        "record_step",
        "select_step",
        "apply_outcome",
    )
    assert step("wire") == ("select_step", "run_wire", "record_step")
