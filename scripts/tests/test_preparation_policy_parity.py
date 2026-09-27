"""ENH-3623: the preparation-policy cutover's parity record.

ENH-3630 proved parity two ways before the cutover: every
``test_autodev_characterization.SCENARIOS`` entry ran against the dispatch-loop
fixture (with an enumerated diff list), and nine differential scenarios ran BOTH the
old autodev ladder and the policy on the same input and compared. ENH-3623 removed
the old ladder, so neither comparison can run any more. What survives:

- ``PRE_CUTOVER_PINS``: for every accepted behavior change, the value the ENH-3618
  pin held before the cutover. ``test_accepted_changes_are_real_diffs`` asserts the
  current pin differs from it (no vacuous allowance), so each accepted change keeps
  its own pinned scenario in ``SCENARIOS``.
- ``DIFF_SCENARIOS`` / ``DIFF_EXPECTED``: the differential scenarios (the four
  hardest routing shapes, H1-H4, plus ladder paths the table does not reach), pinned
  at the values the cutover-time comparison verified (old ladder + ``DIFF_ALLOWED``).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.autodev_harness import (
    DEFAULT_BODY,
    AutodevResult,
    Effects,
    InnerRun,
    Scenario,
    SlashResponse,
    run_autodev,
)
from tests.preparation_policy_harness import DELETED_STATES
from tests.test_autodev_characterization import (
    APPLY,
    CHILD,
    DESIGN_GATE_ARMED,
    GO,
    NO_GO,
    NOOP,
    READY,
    READY_PATH,
    SCENARIOS,
    SIZE_REVIEW,
    SIZE_REVIEW_G2,
    SIZE_REVIEW_GUARD2,
    SIZE_REVIEW_LEAF,
    STOP_PATH,
    WRAPPER_DESIGN_REMEDY,
    WRAPPER_RECONCILE,
    WRAPPER_RESCORE_RETRY,
    Expected,
    _assert_hermetic,
    confidence,
    done,
    expected_view,
    observed,
    step,
    summary,
)

pytestmark = pytest.mark.slow

ID = "ENH-9001"

PARITY_FIELDS = (
    "terminated_by",
    "final_state",
    "skipped",
    "queue",
    "staged",
    "passed",
    "unverified",
    "dequeued",
    "records",
    "issues",
    "summary",
    "slash",
    "repair_cycle",
    "ll_auto",
    "ledgers",
)

#: ``{scenario: {field: (pre-cutover pin, justification)}}`` -- every accepted
#: behavior change (ENH-3623 § Accepted behavior changes + the record-token fixes).
PRE_CUTOVER_PINS: dict[str, dict[str, tuple[Any, str]]] = {
    "oversized_atomic_go_reopen_implement": {
        "records": (
            {ID: "MISSING"},
            "BUG-LIKE pin fixed per the terminal table (ready): the GO path now ends "
            "with a READY record instead of MISSING",
        ),
    },
    "size_review_decomposition": {
        "records": (
            {ID: "BLOCKED", "ENH-9002": "READY", "ENH-9003": "BLOCKED:quality"},
            "BUG-LIKE pin fixed per the terminal table (size-review decomposition -> "
            "decomposed + child_ids); was the stale forwarded BLOCKED",
        ),
    },
    "resolved_parent_at_recheck": {
        "records": (
            {ID: "BLOCKED"},
            "BUG-LIKE pin fixed per the DECOMPOSED guarantee (resolved parent -> "
            "decomposed); recover_subloop_children still writes resolved_by_subloop",
        ),
    },
    "scores_absent_after_repair": {
        "skipped": ((), "accepted change 1: scores-absent stop ledgered refine_failed_infra"),
        "records": ({ID: "BLOCKED"}, "terminal table: scores absent -> RETRYABLE_ERROR:infra"),
        "ledgers": (
            {"autodev-scores-absent.txt": [ID]},
            "autodev-scores-absent.txt lost its only writer (mark_scores_absent_infra)",
        ),
    },
    "on_error_drop": {
        "skipped": ((), "accepted change 1: an on_error drop ledgers refine_failed_infra"),
        "unverified": (
            (f"{ID}  inflight_at_finalize",),
            "same: prep apply's no-terminal-intent fallback clears autodev-inflight",
        ),
        "records": ({ID: "BLOCKED"}, "terminal table: no-terminal-intent fallback -> infra"),
        "summary": (
            summary(verdict="phantom", not_closed=1, inflight_unresolved=1, abandoned=1),
            "same: no phantom inflight (refine_failed_infra is not counted as skipped)",
        ),
        "final_state": ("failed", "same: finalize_done no longer sees a phantom inflight"),
    },
    "ladder_rate_limit_halts": {
        "records": (
            {ID: "BLOCKED"},
            "terminal table (rate_limited): mark_rate_limited writes a fresh "
            "RETRYABLE_ERROR:rate_limited record instead of the stale forwarded BLOCKED",
        ),
    },
}


def test_accepted_changes_are_real_diffs() -> None:
    """Every accepted change must differ from its pre-cutover pin (no vacuous allowance)."""
    pinned = {s.name: expected_view(e) for s, e in SCENARIOS}
    for name, fields in PRE_CUTOVER_PINS.items():
        assert name in pinned, f"{name}: accepted change has no pinned scenario"
        for fieldname, (old, _why) in fields.items():
            assert fieldname in PARITY_FIELDS, (name, fieldname)
            assert pinned[name][fieldname] != old, f"{name}.{fieldname} is not a change"


def _observed_parity(r: AutodevResult) -> dict[str, Any]:
    view = observed(r)
    return {k: view[k] for k in PARITY_FIELDS}


# ---------------------------------------------------------------------------
# Differential scenarios (H1-H4 in the spike report and ladder paths the pinned
# table does not reach), pinned at their cutover-verified values.
# ---------------------------------------------------------------------------

_SUPERSEDED_BODY = (
    DEFAULT_BODY + "\n## Implementation Steps\n\n1. ⚠ Superseded: the old approach (see findings)\n"
)
_CLEAN_SUPERSEDED_BODY = (
    DEFAULT_BODY
    + "\n## Scope Boundaries\n\n- In scope: the widget\n"
    + "\n## Implementation Steps\n\n1. ⚠ Superseded: the old approach (see findings)\n"
    + "\n## Impact\n\n- **Priority**: P3\n"
    + "\n## Status\n\n**Open**\n"
)
_H1_FRONTMATTER = {
    "confidence_score": 60,
    "outcome_confidence": 80,
    "score_ambiguity": 5,
    "score_complexity": 20,
    "score_test_coverage": 20,
    "score_change_surface": 20,
}
_H1_INNER = {
    ID: (
        InnerRun(effects=Effects(scores=(70, 80))),
        InnerRun(effects=Effects(scores=(90, 50), frontmatter={"missing_artifacts": True})),
    )
}


def _h1_slash(go_no_go: SlashResponse) -> dict[str, tuple[SlashResponse, ...]]:
    return {
        "issue-size-review": (SIZE_REVIEW_GUARD2,),
        "wire-issue": (NOOP,),
        "refine-issue": (NOOP,),
        "confidence-check": (confidence(90, 50),),
        "go-no-go": (go_no_go,),
    }


DIFF_SCENARIOS: list[Scenario] = [
    # H1: guard-2 from epoch 1's size review is read in epoch 2 (after a pre-deferral
    # spike re-entry and a wire-origin rescore), never re-running size review.
    Scenario(
        name="h1_guard2_across_epochs",
        frontmatter=_H1_FRONTMATTER,
        inner_runs=_H1_INNER,
        slash=_h1_slash(NO_GO),
    ),
    # H1 + H4: same, go/no-go GO -> reopen -> implement.
    Scenario(
        name="h1_guard2_across_epochs_go",
        frontmatter=_H1_FRONTMATTER,
        inner_runs=_H1_INNER,
        slash=_h1_slash(GO),
    ),
    # H2 (ENH-3625 Rule A): the policy's first gate is design-aware, so a
    # design-failing first pass does not FINISH -- it falls through to SIZE_REVIEW
    # and the design remedy.
    Scenario(
        name="h2_first_gate_honors_design_then_size_review",
        frontmatter=READY,
        project_files=DESIGN_GATE_ARMED,
        inner_runs={ID: (done(),)},
        slash={
            "issue-size-review": (SIZE_REVIEW_LEAF,),
            "reconcile-issue": (NOOP,),
            "confidence-check": (confidence(90, 80),),
            "wire-issue": (NOOP,),
            "refine-issue": (NOOP,),
        },
    ),
    # H3 PROOF: post-refine PROOF re-entry, second inner run passes.
    Scenario(
        name="h3_proof_reentry_then_ready",
        frontmatter={
            "confidence_score": 90,
            "outcome_confidence": 50,
            "spike_needed": True,
            "learning_tests_required": ["widget-api"],
        },
        inner_runs={
            ID: (
                done(),
                InnerRun(effects=Effects(scores=(90, 80), frontmatter={"spike_attempted": True})),
            )
        },
    ),
    # H3 DECISION: post-refine DECISION re-entry resolves the decision.
    Scenario(
        name="h3_decision_reentry_resolves",
        frontmatter={"confidence_score": 70, "outcome_confidence": 80, "decision_needed": True},
        inner_runs={
            ID: (
                done(),
                InnerRun(effects=Effects(scores=(90, 80), frontmatter={"decision_needed": None})),
            )
        },
    ),
    # Fresh issue: fresh_below reconcile with pre-readiness backfill, then an armed
    # pre-deferral reconcile remedy, then low_readiness.
    Scenario(
        name="pre_deferral_reconcile_remedy",
        frontmatter={},
        inner_runs={ID: (InnerRun(effects=Effects(scores=(70, 80))),)},
        slash={
            "issue-size-review": (SIZE_REVIEW_LEAF,),
            "reconcile-issue": (NOOP,),
            "confidence-check": (confidence(72, 80),),
        },
    ),
    # Rescore presence retry recovers; RASR passes -> implemented.
    Scenario(
        name="rescore_retry_recovers",
        frontmatter={"confidence_score": 70, "outcome_confidence": 80, "missing_artifacts": True},
        inner_runs={ID: (done(),)},
        slash={
            "wire-issue": (NOOP,),
            "refine-issue": (NOOP,),
            "confidence-check": (NOOP, confidence(90, 80)),
        },
    ),
    # Contradiction-only reconcile (superseded marker, no blocking format gaps), then
    # readiness_stagnated.
    Scenario(
        name="contradiction_reconcile",
        frontmatter={"confidence_score": 90, "outcome_confidence": 50, "reconcile_attempted": True},
        body=_CLEAN_SUPERSEDED_BODY,
        inner_runs={ID: (done(),)},
        slash={
            "issue-size-review": (SIZE_REVIEW_LEAF,),
            "reconcile-issue": (NOOP,),
            "confidence-check": (confidence(90, 50),),
        },
    ),
    # Q1 (BUG-3624): the same marker on an issue with blocking format gaps still
    # fires the reconcile (markers are read whatever format-check's exit code).
    Scenario(
        name="contradiction_not_masked_by_format_gaps_bug3624",
        frontmatter={"confidence_score": 90, "outcome_confidence": 50, "reconcile_attempted": True},
        body=_SUPERSEDED_BODY,
        inner_runs={ID: (done(),)},
        slash={
            "issue-size-review": (SIZE_REVIEW_LEAF,),
            "reconcile-issue": (NOOP,),
            "confidence-check": (confidence(90, 50),),
        },
    ),
]


_W, _R, _C, _S, _G, _RC = (
    f"wire-issue {ID}",
    f"refine-issue {ID}",
    f"confidence-check {ID}",
    f"issue-size-review {ID}",
    f"go-no-go {ID}",
    f"reconcile-issue {ID}",
)
_H1_WRAPPER = (
    *CHILD,
    *SIZE_REVIEW_G2,
    *CHILD,
    *step("wire"),
    *step("refine_gap"),
    *step("rescore"),
    *step("wire"),
    *step("rescore"),
    *step("go_no_go"),
    *APPLY,
)
_IMPLEMENTED: dict[str, Any] = {
    "path": READY_PATH,
    "staged": (ID,),
    "passed": (ID,),
    "records": {ID: "READY"},
    "summary": summary(verdict="success", closed=1, closed_implemented=1),
    "ll_auto": (ID,),
}

DIFF_EXPECTED: dict[str, Expected] = {
    "h1_guard2_across_epochs": Expected(
        path=STOP_PATH,
        wrapper_path=_H1_WRAPPER,
        skipped=(f"{ID}  oversized_atomic",),
        records={ID: "DEFERRED:gate_unmet"},
        issues={ID: ("deferred", "oversized_atomic")},
        summary=summary(skipped=1),
        slash=(_S, _W, _R, _C, _W, _C, _G),
        repair_cycle="4",
    ),
    # was a DIFF_ALLOWED record: READY (the old ladder left MISSING), as
    # oversized_atomic_go_reopen_implement
    "h1_guard2_across_epochs_go": Expected(
        **_IMPLEMENTED,
        wrapper_path=_H1_WRAPPER,
        issues={ID: ("done", "oversized_atomic")},
        slash=(_S, _W, _R, _C, _W, _C, _G),
        repair_cycle="4",
    ),
    "h2_first_gate_honors_design_then_size_review": Expected(
        path=STOP_PATH,
        wrapper_path=WRAPPER_DESIGN_REMEDY,
        skipped=(f"{ID}  design_gate_failed",),
        records={ID: "DEFERRED:gate_unmet"},
        issues={ID: ("deferred", "design_gate_failed")},
        summary=summary(skipped=1),
        slash=(_S, _RC, _C, _R, _C),
        repair_cycle="4",
    ),
    "h3_proof_reentry_then_ready": Expected(
        **_IMPLEMENTED,
        wrapper_path=(*CHILD, *CHILD, *APPLY),
        issues={ID: ("done", None)},
        repair_cycle="2",
    ),
    "h3_decision_reentry_resolves": Expected(
        **_IMPLEMENTED,
        wrapper_path=(*CHILD, *CHILD, *APPLY),
        issues={ID: ("done", None)},
        repair_cycle="2",
    ),
    "pre_deferral_reconcile_remedy": Expected(
        path=STOP_PATH,
        wrapper_path=(
            *CHILD,
            *SIZE_REVIEW,
            *step("reconcile"),
            *step("rescore"),
            *step("reconcile"),
            *step("rescore"),
            *APPLY,
        ),
        skipped=(f"{ID}  low_readiness",),
        records={ID: "DEFERRED:gate_unmet"},
        issues={ID: ("deferred", "low_readiness")},
        summary=summary(skipped=1),
        slash=(_S, _RC, _C, _RC, _C),
        repair_cycle="4",
    ),
    # was a DIFF_ALLOWED record: READY (the old ladder kept the forwarded BLOCKED)
    "rescore_retry_recovers": Expected(
        **_IMPLEMENTED,
        wrapper_path=WRAPPER_RESCORE_RETRY,
        issues={ID: ("done", None)},
        slash=(_W, _R, _C, _C),
        repair_cycle="2",
    ),
    "contradiction_reconcile": Expected(
        path=STOP_PATH,
        wrapper_path=WRAPPER_RECONCILE,
        skipped=(f"{ID}  readiness_stagnated",),
        records={ID: "DEFERRED:gate_unmet"},
        issues={ID: ("deferred", "readiness_stagnated")},
        summary=summary(skipped=1),
        slash=(_S, _RC, _C),
        repair_cycle="3",
    ),
    "contradiction_not_masked_by_format_gaps_bug3624": Expected(
        path=STOP_PATH,
        wrapper_path=WRAPPER_RECONCILE,
        skipped=(f"{ID}  readiness_stagnated",),
        records={ID: "DEFERRED:gate_unmet"},
        issues={ID: ("deferred", "readiness_stagnated")},
        summary=summary(skipped=1),
        slash=(_S, _RC, _C),
        repair_cycle="3",
    ),
}


def test_every_differential_scenario_is_pinned() -> None:
    assert sorted(DIFF_EXPECTED) == sorted(s.name for s in DIFF_SCENARIOS)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("scenario", [pytest.param(s, id=s.name) for s in DIFF_SCENARIOS])
def test_differential_scenario(
    scenario: Scenario, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = run_autodev(scenario, tmp_path, monkeypatch)
    _assert_hermetic(r)
    assert observed(r) == expected_view(DIFF_EXPECTED[scenario.name])
    assert not set(r.path) & set(DELETED_STATES)
