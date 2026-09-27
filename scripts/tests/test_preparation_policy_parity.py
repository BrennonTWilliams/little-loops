"""ENH-3630: characterization parity for the preparation-policy dispatch loop.

Re-runs every ``test_autodev_characterization.SCENARIOS`` entry with
``fixtures/loops/prepare-issue-policy.yaml`` as ``prepare-issue`` and ENH-3606's
boundary retargets applied to ``autodev.yaml``. The comparison covers the parity
fields (ledgers, queue, staging, records, issue status, summary.json, slash
sequence, repair-cycle projection, ll-auto calls); the autodev *path* legitimately
changes (the ladder states are gone) and is checked separately for moved-state
absence.

Every difference from today's pin is listed in ``ALLOWED_DIFFS`` with the reason;
nothing else may differ.

Ported from the ``spike/preparation-policy-a51621302`` tag
(``test_preparation_policy_parity.py``), rewritten rather than ported verbatim for
two scenarios that branched before ENH-3625/BUG-3622 landed on main (see their
comments below): ``h2_first_gate_skips_design`` (ENH-3625 Rule A made *both*
today's ladder and the policy design-aware, so this is no longer a design-gate
differential -- it stays as a plain post-size-review differential) and
``contradiction_masked_by_format_gaps`` (Q1 now reads markers unconditionally, so
the reconcile fires on both sides where the spike-era mask suppressed it). A new
``ladder_rate_limit_halts`` allowance was added: BUG-3622 fixed today's ladder to
run the rate-limit retry loop to exhaustion (matching the policy), but the
*terminal record* still differs -- today forwards the inner run's stale BLOCKED,
while the policy's ``mark_rate_limited`` writes a fresh
``RETRYABLE_ERROR:rate_limited`` (ENH-3606 terminal table).
"""

from __future__ import annotations

from dataclasses import replace
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
from tests.preparation_policy_harness import DELETED_STATES, run_policy
from tests.test_autodev_characterization import (
    DESIGN_GATE_ARMED,
    GO,
    NO_GO,
    NOOP,
    READY,
    SCENARIOS,
    SIZE_REVIEW_GUARD2,
    SIZE_REVIEW_LEAF,
    Expected,
    _assert_hermetic,
    confidence,
    done,
    expected_view,
    observed,
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

#: Scenario-level fault remaps: today's fault points are states that no longer exist.
FAULT_REMAP: dict[str, dict[str, int]] = {
    # enqueue_or_skip (the EOS decision after size review) == the 3rd select_step.
    "on_error_drop": {"select_step#3": 2},
}

#: ``{scenario: {field: (new_value, justification)}}`` -- the enumerated diff list.
ALLOWED_DIFFS: dict[str, dict[str, tuple[Any, str]]] = {
    "oversized_atomic_go_reopen_implement": {
        "records": (
            {ID: "READY"},
            "BUG-LIKE pin fixed per ENH-3606 terminal table (mark_ready): the GO path "
            "now ends with a READY record instead of MISSING",
        ),
    },
    "size_review_decomposition": {
        "records": (
            {ID: "DECOMPOSED", "ENH-9002": "READY", "ENH-9003": "BLOCKED:quality"},
            "BUG-LIKE pin fixed per ENH-3606 terminal table (size-review decomposition "
            "-> decomposed + child_ids); was the stale forwarded BLOCKED",
        ),
    },
    "resolved_parent_at_recheck": {
        "records": (
            {ID: "DECOMPOSED"},
            "BUG-LIKE pin fixed per ENH-3606 (route_ladder_stop: resolved parent -> "
            "mark_decomposed); autodev's recover_subloop_children still writes the "
            "same resolved_by_subloop row",
        ),
    },
    "scores_absent_after_repair": {
        "skipped": (
            (f"{ID}  refine_failed_infra",),
            "ENH-3606 accepted change 1: scores-absent stop now ledgered refine_failed_infra",
        ),
        "records": ({ID: "RETRYABLE_ERROR:infra"}, "ENH-3606 terminal table: mark_scores_absent"),
        "ledgers": (
            {},
            "ENH-3606 decided: autodev-scores-absent.txt loses its only writer "
            "(mark_scores_absent_infra deleted)",
        ),
    },
    "on_error_drop": {
        "skipped": (
            (f"{ID}  refine_failed_infra",),
            "ENH-3606 accepted change 1: an on_error drop now ledgers refine_failed_infra",
        ),
        "unverified": ((), "same: skip_inflight_infra clears autodev-inflight"),
        "records": ({ID: "RETRYABLE_ERROR:infra"}, "ENH-3606 terminal table: mark_ladder_error"),
        "summary": (
            summary(),
            "same: no phantom inflight; verdict no-op like scores_absent (the "
            "refine_failed_infra bucket is not counted as skipped by autodev_summary)",
        ),
        "final_state": ("done", "same: finalize_done no longer sees a phantom inflight"),
    },
    "ladder_rate_limit_halts": {
        "records": (
            {ID: "RETRYABLE_ERROR:rate_limited"},
            "BUG-3622 fixed the retry loop itself (both sides run it to exhaustion, "
            "same 12 waits), but ENH-3606's mark_rate_limited terminal writes a fresh "
            "RETRYABLE_ERROR:rate_limited record; today's finalize_rate_limited still "
            "leaves the inner run's stale forwarded BLOCKED",
        ),
    },
}


def _scenario(s: Scenario) -> Scenario:
    return replace(s, faults=FAULT_REMAP.get(s.name, dict(s.faults)))


def _expected_parity(s: Scenario, e: Expected) -> dict[str, Any]:
    view = expected_view(e)
    out = {k: view[k] for k in PARITY_FIELDS}
    for fieldname, (value, _why) in ALLOWED_DIFFS.get(s.name, {}).items():
        out[fieldname] = value
    return out


def _observed_parity(r: AutodevResult) -> dict[str, Any]:
    view = observed(r)
    return {k: view[k] for k in PARITY_FIELDS}


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("scenario", "expected"),
    [pytest.param(s, e, id=s.name) for s, e in SCENARIOS],
)
def test_policy_parity(
    scenario: Scenario, expected: Expected, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = run_policy(_scenario(scenario), tmp_path, monkeypatch)
    _assert_hermetic(r, expected.rate_limit_waits)
    assert _observed_parity(r) == _expected_parity(scenario, expected)
    # PASS criterion 2: no autodev event enters a moved (or deleted) state.
    entered = set(r.path) & set(DELETED_STATES)
    assert not entered, f"autodev entered moved states: {sorted(entered)}"


def test_allowed_diffs_are_real_diffs() -> None:
    """Every ALLOWED_DIFFS entry must differ from today's pin (no vacuous allowances)."""
    pinned = {s.name: expected_view(e) for s, e in SCENARIOS}
    for name, fields in ALLOWED_DIFFS.items():
        for fieldname, (value, _why) in fields.items():
            assert pinned[name][fieldname] != value, f"{name}.{fieldname} allowance is a no-op"


# ---------------------------------------------------------------------------
# Differential scenarios: run BOTH today's ladder and the policy on the same
# scenario and compare. These cover the four hardest routing shapes (H1-H4 in
# the spike report) and ladder paths the pinned table does not reach.
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
    # H2 (rewritten, ENH-3625): both today's `check_passed` and the policy's first
    # gate are now design-aware (Rule A), so a design-failing first pass no longer
    # skips straight to FINISH on either side -- it falls through to SIZE_REVIEW.
    # This stays a differential (not folded into the pinned table) because the
    # *post-size-review* path is where the 39 moved states legitimately diverge.
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
    # Q1 (BUG-3624, fixed on main): the same marker on an issue with blocking format
    # gaps now DOES fire the reconcile (markers are read unconditionally); the
    # spike-era mask this scenario characterized no longer exists on either side, so
    # this is plain parity with contradiction_reconcile's shape, not the masked one.
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

#: Per-scenario diffs vs today in the differential runs (same shape as ALLOWED_DIFFS).
DIFF_ALLOWED: dict[str, dict[str, tuple[Any, str]]] = {
    "h1_guard2_across_epochs_go": {
        "records": ({ID: "READY"}, "as oversized_atomic_go_reopen_implement (mark_ready)"),
    },
    "rescore_retry_recovers": {
        "records": (
            {ID: "READY"},
            "BUG-LIKE today: an issue implemented off the RASR pass keeps the forwarded "
            "BLOCKED inner record; the policy's FINISH(ready) writes READY",
        ),
    },
}


@pytest.mark.timeout(600)
@pytest.mark.parametrize("scenario", [pytest.param(s, id=s.name) for s in DIFF_SCENARIOS])
def test_policy_matches_today_differential(
    scenario: Scenario, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "today").mkdir()
    (tmp_path / "policy").mkdir()
    today = run_autodev(scenario, tmp_path / "today", monkeypatch)
    _assert_hermetic(today)
    policy = run_policy(scenario, tmp_path / "policy", monkeypatch)
    _assert_hermetic(policy)
    want = _observed_parity(today)
    for fieldname, (value, _why) in DIFF_ALLOWED.get(scenario.name, {}).items():
        assert want[fieldname] != value, f"{scenario.name}.{fieldname}: allowed diff is a no-op"
        want[fieldname] = value
    assert _observed_parity(policy) == want, f"today path: {today.path}"
    assert not set(policy.path) & set(DELETED_STATES)
    # The scenario must actually exercise the shape it names (non-vacuous parity).
    slash = tuple(policy.slash_commands)
    inner_runs = sum(1 for p in policy.full_path if p.endswith(":scripted_run"))
    shape = DIFF_SHAPES.get(scenario.name)
    if shape is not None:
        assert shape(slash, inner_runs), (scenario.name, slash, inner_runs)


_W, _R, _C, _S, _G, _RC = (
    f"wire-issue {ID}",
    f"refine-issue {ID}",
    f"confidence-check {ID}",
    f"issue-size-review {ID}",
    f"go-no-go {ID}",
    f"reconcile-issue {ID}",
)
DIFF_SHAPES: dict[str, Any] = {
    "h1_guard2_across_epochs": lambda s, n: s == (_S, _W, _R, _C, _W, _C, _G) and n == 2,
    "h1_guard2_across_epochs_go": lambda s, n: s == (_S, _W, _R, _C, _W, _C, _G) and n == 2,
    "h2_first_gate_honors_design_then_size_review": lambda s, n: (
        s == (_S, _RC, _C, _R, _C) and n == 1
    ),
    "h3_proof_reentry_then_ready": lambda s, n: n == 2,
    "h3_decision_reentry_resolves": lambda s, n: n == 2,
    "pre_deferral_reconcile_remedy": lambda s, n: s == (_S, _RC, _C, _RC, _C),
    "rescore_retry_recovers": lambda s, n: s == (_W, _R, _C, _C),
    "contradiction_reconcile": lambda s, n: s == (_S, _RC, _C),
    "contradiction_not_masked_by_format_gaps_bug3624": lambda s, n: s == (_S, _RC, _C),
}
