"""ENH-3630: table tests for the pure ``preparation_policy.decide()``.

Ported from the ENH-3621 spike (tag ``spike/preparation-policy-a51621302``), with the
"today" side of every scenario updated for the fixes that landed on ``main`` after the
spike branched (merge base ``9f7c5dc27``): BUG-3624 (Q1), ENH-3625 (Q3), BUG-3620 and
BUG-3622 (see ``preparation_policy``'s module docstring). Three scenarios are rewritten
rather than ported verbatim -- see each test's docstring.

Each case is (snapshot, fact log) -> expected step. The fact logs are written the way
``ll-issues prep step/record`` write them: an ``intent`` then a ``done`` per command,
``obs`` facts for observations, all in pass ``"1"`` unless a case says otherwise.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

import pytest

from little_loops.preparation_policy import (
    DONE_FACT_CAP,
    MAX_DONE_PER_PASS,
    MAX_STEPS,
    Fact,
    Facts,
    IssueSnapshot,
    Step,
    StepKind,
    current_pass,
    decide,
)

ID = "ENH-1"
LOW = IssueSnapshot(issue_id=ID, confidence=70, outcome=80)
READY = IssueSnapshot(issue_id=ID, confidence=90, outcome=80)
LOW_OUTCOME = IssueSnapshot(issue_id=ID, confidence=90, outcome=50)


def start(pre_readiness: str = "70", pre_ids: tuple[str, ...] = (ID,), pass_id: str = "1") -> Fact:
    return Fact(
        pass_id, 0, "obs", "pass_start", {"pre_readiness": pre_readiness, "pre_ids": list(pre_ids)}
    )


def cmd(seq: int, kind: StepKind, pass_id: str = "1", **payload: Any) -> list[Fact]:
    """An intent + done pair for one executed command."""
    return [
        Fact(pass_id, seq, "intent", kind.value, dict(payload)),
        Fact(pass_id, seq, "done", kind.value, dict(payload)),
    ]


def child(
    seq: int,
    token: str = "BLOCKED",
    terminal: str = "done",
    role: str = "first",
    pass_id: str = "1",
    **extra: Any,
) -> list[Fact]:
    return cmd(seq, StepKind.RUN_CHILD, pass_id, role=role, terminal=terminal, token=token, **extra)


def log(*groups: Any, pass_id: str = "1") -> Facts:
    out: list[Fact] = []
    for g in groups:
        out.extend(g if isinstance(g, list) else [g])
    return Facts(pass_id=pass_id, facts=tuple(out))


def check(step: Step, kind: StepKind, **payload: Any) -> None:
    assert step.kind is kind, (step.kind, step.reason, step.evidence)
    for k, v in payload.items():
        assert step.payload.get(k) == v, (k, step.payload, step.reason)


# ---------------------------------------------------------------------------
# Entry, inner-loop outcomes, and the first gate
# ---------------------------------------------------------------------------


def test_pass_start_runs_the_child_after_clearing_records() -> None:
    s = decide(LOW, log(start()))
    check(s, StepKind.RUN_CHILD, role="first", preconditions=["clear_records"])
    assert s.seq == 1


@pytest.mark.parametrize(
    ("terminal", "token", "kind", "outcome"),
    [
        ("failed", "DEFERRED:gate_unmet", StepKind.STOP, "child_stop"),
        ("error", "MISSING", StepKind.STOP, "inner_error"),
        ("done", "CANCELLED", StepKind.FINISH, "cancelled"),
    ],
)
def test_inner_outcomes(terminal: str, token: str, kind: StepKind, outcome: str) -> None:
    check(decide(LOW, log(start(), child(1, token, terminal))), kind, outcome=outcome)


def test_ready_after_child_finishes() -> None:
    check(decide(READY, log(start(), child(1, "READY"))), StepKind.FINISH, outcome="ready")


def test_h2_first_gate_is_design_aware_enh3625() -> None:
    """ENH-3625 (Q3, rewritten from the spike's ``h2_first_gate_skips_design``).

    The spike's first gate ignored the design verdict (quirk H2); ENH-3625 chose
    option A -- the first gate now hard-ANDs check-design like every later gate, so a
    design-failing inner ``done`` no longer finishes ``ready``; it falls through to
    ``post_refine_select`` -> ``detect`` -> ``recheck_scores``, which (still failing
    design) routes to SIZE_REVIEW instead.
    """
    s = decide(replace(READY, design_failed=True), log(start(), child(1, "READY")))
    check(s, StepKind.SIZE_REVIEW)
    # BUG-3620: no sticky observation is ever recorded for a design failure.
    assert s.observations == ()


def test_first_gate_honors_waiver() -> None:
    snap = replace(LOW_OUTCOME, waived=True)
    check(decide(snap, log(start(), child(1))), StepKind.FINISH, outcome="ready")


# ---------------------------------------------------------------------------
# Selectors and re-entry budgets (H3)
# ---------------------------------------------------------------------------


def test_decision_reentry_then_exhausted() -> None:
    snap = replace(LOW, decision_needed=True)
    check(decide(snap, log(start(), child(1))), StepKind.RUN_CHILD, role="decision")
    facts = log(start(), child(1), child(2, role="decision"))
    check(decide(snap, facts), StepKind.STOP, outcome="decision_exhausted")


def test_decision_reentry_capped_by_lifetime_refine_count() -> None:
    snap = replace(LOW, decision_needed=True, refine_count=5, refine_cap=5)
    check(decide(snap, log(start(), child(1))), StepKind.STOP, outcome="decision_exhausted")


def test_decision_reentry_budget_is_per_pass() -> None:
    snap = replace(LOW, decision_needed=True)
    old_pass = [*child(1, pass_id="1"), *child(2, role="decision", pass_id="1")]
    facts = log(start(pass_id="2"), *old_pass, child(1, pass_id="2"), pass_id="2")
    check(decide(snap, facts), StepKind.RUN_CHILD, role="decision")


def test_proof_reentry_post_refine() -> None:
    snap = replace(LOW_OUTCOME, obligation_post="PROOF:absent", spike_needed=True)
    check(decide(snap, log(start(), child(1))), StepKind.RUN_CHILD, role="proof")
    spent = replace(snap, spike_runs=2)
    check(decide(spent, log(start(), child(1))), StepKind.SIZE_REVIEW)
    used = log(start(), child(1), child(2, role="proof"))
    check(decide(snap, used), StepKind.SIZE_REVIEW)


def test_pre_implement_proof_gate_reentry() -> None:
    snap = replace(READY, gate_verdict="structured_proof")
    check(decide(snap, log(start(), child(1, "READY"))), StepKind.RUN_CHILD, role="proof")
    waived = replace(snap, waived=True)
    check(decide(waived, log(start(), child(1, "READY"))), StepKind.FINISH, outcome="ready")


def test_missing_artifacts_wire_chain() -> None:
    snap = replace(LOW, missing_artifacts=True)
    check(decide(snap, log(start(), child(1))), StepKind.WIRE, role="artifacts")
    f = log(start(), child(1), cmd(2, StepKind.WIRE, role="artifacts"))
    check(decide(snap, f), StepKind.REFINE_GAP, role="post_wire")
    f = log(
        start(),
        child(1),
        cmd(2, StepKind.WIRE, role="artifacts"),
        cmd(3, StepKind.REFINE_GAP, role="post_wire"),
    )
    check(
        decide(snap, f), StepKind.RESCORE, origin="wire", attempt=1, preconditions=["clear_scores"]
    )


def test_selector_error_goes_to_detect() -> None:
    snap = replace(LOW, obligation_post="ERROR", missing_artifacts=True)
    check(decide(snap, log(start(), child(1))), StepKind.SIZE_REVIEW)


# ---------------------------------------------------------------------------
# Detection and recheck_scores
# ---------------------------------------------------------------------------


def test_detect_children_against_the_pass_baseline() -> None:
    snap = replace(LOW, child_candidates=frozenset({"ENH-2", "ENH-3"}))
    s = decide(snap, log(start(pre_ids=(ID, "ENH-2")), child(1, "DECOMPOSED")))
    check(s, StepKind.FINISH, outcome="decomposed", child_ids=["ENH-3"])


def test_detect_resolved_parent() -> None:
    snap = replace(LOW, status="done")
    check(decide(snap, log(start(), child(1, "DECOMPOSED"))), StepKind.FINISH, outcome="decomposed")


def test_inner_decomposed_without_children_falls_back_to_size_review() -> None:
    check(decide(LOW, log(start(), child(1, "DECOMPOSED"))), StepKind.SIZE_REVIEW)


def test_recheck_scores_hard_ands_design_bug3620_current_verdict() -> None:
    """BUG-3620: the design condition reads this visit's verdict; no marker recorded."""
    snap = replace(READY, obligation_post="NONE", design_failed=True)
    s = decide(snap, log(start(), child(1, "DECOMPOSED")))
    check(s, StepKind.SIZE_REVIEW)
    assert s.observations == ()


# ---------------------------------------------------------------------------
# Rescoring chain (return address = the done fact before RESCORE)
# ---------------------------------------------------------------------------


def _rescored(origin: str, attempt: int = 1) -> Facts:
    return log(start(), child(1), cmd(2, StepKind.RESCORE, origin=origin, attempt=attempt))


def test_rescore_retry_then_scores_absent() -> None:
    absent = replace(LOW, confidence=None, outcome=None)
    s = decide(absent, _rescored("reconcile"))
    check(s, StepKind.RESCORE, origin="reconcile", attempt=2)
    assert "preconditions" not in s.payload  # no second clear before the retry
    check(decide(absent, _rescored("reconcile", 2)), StepKind.STOP, outcome="scores_absent")


@pytest.mark.parametrize(
    ("origin", "snap", "kind", "payload"),
    [
        ("wire", READY, StepKind.FINISH, {"outcome": "ready"}),  # EOS -> ... -> RASR pass
        ("reconcile", LOW, StepKind.STOP, {"outcome": "low_readiness"}),
        ("atomic", LOW_OUTCOME, StepKind.GO_NO_GO, {"preconditions": ["defer_oversized_atomic"]}),
    ],
)
def test_rescore_dispatch_by_origin(
    origin: str, snap: IssueSnapshot, kind: StepKind, payload: dict[str, Any]
) -> None:
    # fired pre-deferral remedy blocks the RASR remedy arm so reconcile reaches low_readiness
    facts = log(
        start(pre_readiness=""),
        child(1),
        cmd(2, StepKind.RECONCILE, pre_deferral=True, contradiction_only=False),
        cmd(3, StepKind.RESCORE, origin=origin, attempt=1),
    )
    check(decide(snap, facts), kind, **payload)


# ---------------------------------------------------------------------------
# Post-size-review: reconcile check, guard-2 (H1), recheck_after_size_review
# ---------------------------------------------------------------------------


def _after_sr(*extra: Any, guard2: bool = False, pre: str = "70") -> Facts:
    return log(
        start(pre_readiness=pre), child(1), cmd(2, StepKind.SIZE_REVIEW, guard2=guard2), *extra
    )


def test_reconcile_on_plateau() -> None:
    check(decide(LOW, _after_sr()), StepKind.RECONCILE, contradiction_only=False)


def test_fresh_below_backfills_pre_readiness() -> None:
    s = decide(LOW, _after_sr(pre=""))
    check(s, StepKind.RECONCILE)
    assert ("pre_readiness", "70") in s.observations


def test_contradiction_only_reconcile_capped_at_two_per_pass() -> None:
    snap = replace(LOW_OUTCOME, reconcile_attempted=True, superseded_markers=1)
    check(decide(snap, _after_sr(pre="90")), StepKind.RECONCILE, contradiction_only=True)
    two = [
        *cmd(3, StepKind.RECONCILE, contradiction_only=True),
        *cmd(4, StepKind.RECONCILE, contradiction_only=True),
        *cmd(5, StepKind.SIZE_REVIEW, guard2=False),
    ]
    s = decide(snap, _after_sr(*two, pre="90"))
    assert s.kind is not StepKind.RECONCILE


def test_guard2_routes_to_atomic_remediation() -> None:
    snap = replace(LOW_OUTCOME, reconcile_attempted=True)
    check(decide(snap, _after_sr(guard2=True, pre="90")), StepKind.WIRE, role="atomic")


def test_h1_guard2_reads_the_last_size_review_of_the_pass() -> None:
    snap = replace(LOW_OUTCOME, reconcile_attempted=True)
    epoch2 = [
        *child(3, role="spike_remedy"),
        *cmd(4, StepKind.WIRE, role="artifacts"),
        *cmd(5, StepKind.REFINE_GAP, role="post_wire"),
        *cmd(6, StepKind.RESCORE, origin="wire", attempt=1),
    ]
    # epoch-1 size review said guard-2; epoch 2 reached guard-2 through the wire path
    check(decide(snap, _after_sr(*epoch2, guard2=True, pre="90")), StepKind.WIRE, role="atomic")
    # a later size review in the same pass (guard2=false) replaces it
    later = [*epoch2[:-2], *cmd(7, StepKind.SIZE_REVIEW, guard2=False)]
    s = decide(snap, _after_sr(*later, guard2=True, pre="90"))
    assert not (s.kind is StepKind.WIRE and s.payload.get("role") == "atomic")


def test_guard2_is_pass_scoped() -> None:
    snap = replace(LOW_OUTCOME, reconcile_attempted=True)
    old = cmd(2, StepKind.SIZE_REVIEW, pass_id="1", guard2=True)
    facts = log(
        start(pre_readiness="90", pass_id="2"),
        *old,
        child(1),
        cmd(2, StepKind.RESCORE, origin="wire", attempt=1),
        pass_id="2",
    )
    s = decide(snap, facts)
    assert not (s.kind is StepKind.WIRE and s.payload.get("role") == "atomic")


def test_readiness_stagnated() -> None:
    f = _after_sr(
        *cmd(3, StepKind.RECONCILE), *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1)
    )
    check(decide(LOW, f), StepKind.STOP, outcome="readiness_stagnated")


def test_design_gate_failed_is_not_sticky_across_passes_bug3620_fixed() -> None:
    """BUG-3620, rewritten from the spike's ``design_marker_is_sticky_across_passes``.

    The spike pinned a design failure filed in an earlier pass still deferring
    ``design_gate_failed`` in a later pass even though the current visit's design
    verdict (``design_failed=False``) passes -- the bug. Fixed: since ``decide()``
    reads only the current verdict, the stale obs is inert and this pass falls
    through to the ordinary score-stagnation check (cur == pre == 70, 3 repair
    cycles this pass), which stops ``readiness_stagnated`` instead.
    """
    old = Fact("1", 3, "obs", "design_gate_failed", {"value": True})
    remedy = cmd(5, StepKind.REFINE_GAP, pass_id="1", role="design", pre_deferral=True)
    facts = log(
        old,
        *remedy,
        start(pre_readiness="70", pass_id="2"),
        child(1, pass_id="2"),
        cmd(2, StepKind.SIZE_REVIEW, "2", guard2=False),
        cmd(3, StepKind.RECONCILE, "2"),
        cmd(4, StepKind.RESCORE, "2", origin="reconcile", attempt=1),
        pass_id="2",
    )
    check(
        decide(replace(LOW, design_failed=False), facts),
        StepKind.STOP,
        outcome="readiness_stagnated",
    )


def test_design_pre_deferral_remedy_then_defer() -> None:
    snap = replace(LOW, design_failed=True)
    f = _after_sr(
        *cmd(3, StepKind.RECONCILE), *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1)
    )
    check(decide(snap, f), StepKind.REFINE_GAP, role="design", pre_deferral=True)
    f2 = _after_sr(
        *cmd(3, StepKind.RECONCILE),
        *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1),
        *cmd(5, StepKind.REFINE_GAP, role="design", pre_deferral=True),
        *cmd(6, StepKind.RESCORE, origin="reconcile", attempt=1),
    )
    check(decide(snap, f2), StepKind.STOP, outcome="design_gate_failed")


def test_pre_deferral_remedy_spike_or_reconcile() -> None:
    facts = _after_sr(*cmd(3, StepKind.RESCORE, origin="wire", attempt=1), pre="")
    snap = replace(
        LOW,
        score_ambiguity=5,
        score_complexity=20,
        score_test_coverage=20,
        score_change_surface=20,
        reconcile_attempted=True,
    )
    # reconcile_attempted (not contradiction-sourced) -> no remedy -> low_readiness
    check(decide(snap, facts), StepKind.STOP, outcome="low_readiness")
    fresh = replace(snap, reconcile_attempted=False)
    s = decide(fresh, _after_sr(pre="60", guard2=False))
    # cur 70 > pre 60, not plateau: remedy spike (ambiguity weakest)
    check(s, StepKind.RUN_CHILD, role="spike_remedy", pre_deferral=True)
    check(
        decide(replace(fresh, spike_runs=2), _after_sr(pre="60")),
        StepKind.RECONCILE,
        pre_deferral=True,
    )
    fired = _after_sr(*child(3, role="spike_remedy", pre_deferral=True), pre="60")
    # after the spike re-entry the inner run is epoch 2; a fired remedy never re-arms
    fired_rasr = log(*fired.facts, *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1))
    check(decide(fresh, fired_rasr), StepKind.STOP, outcome="low_readiness")


def test_resolved_parent_at_recheck_finishes_decomposed() -> None:
    f = _after_sr(
        *cmd(3, StepKind.RECONCILE), *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1)
    )
    check(decide(replace(LOW, status="done"), f), StepKind.FINISH, outcome="decomposed")


def test_decision_needed_at_recheck() -> None:
    f = _after_sr(
        *cmd(3, StepKind.RECONCILE), *cmd(4, StepKind.RESCORE, origin="reconcile", attempt=1)
    )
    check(
        decide(replace(LOW, decision_needed=True), f), StepKind.STOP, outcome="decision_unresolved"
    )


# ---------------------------------------------------------------------------
# Regate after atomic remediation and go/no-go (H4)
# ---------------------------------------------------------------------------


def _after_atomic(*extra: Any) -> Facts:
    return _after_sr(
        *cmd(3, StepKind.WIRE, role="atomic"),
        *cmd(4, StepKind.RESCORE, origin="atomic", attempt=1),
        *extra,
        guard2=True,
        pre="90",
    )


def test_h4_go_no_go_requires_prior_deferral_precondition() -> None:
    s = decide(LOW_OUTCOME, _after_atomic())
    check(s, StepKind.GO_NO_GO, preconditions=["defer_oversized_atomic"])


def test_h4_go_no_go_is_once_per_run() -> None:
    old = cmd(9, StepKind.GO_NO_GO, pass_id="0")
    facts = Facts("1", (*old, *_after_atomic().facts))
    check(decide(LOW_OUTCOME, facts), StepKind.STOP, outcome="oversized_atomic")


@pytest.mark.parametrize(
    ("snap", "kind", "payload"),
    [
        (
            replace(LOW_OUTCOME, waived=True),
            StepKind.FINISH,
            {"outcome": "ready", "preconditions": ["reopen"]},
        ),
        (replace(LOW_OUTCOME, waived=False), StepKind.STOP, {"outcome": "oversized_atomic"}),
        # ENH-3606 accepted change 4: waiver covers only the outcome gate
        (
            replace(LOW_OUTCOME, waived=True, confidence=80),
            StepKind.STOP,
            {"outcome": "low_readiness"},
        ),
    ],
)
def test_h4_after_go_no_go(snap: IssueSnapshot, kind: StepKind, payload: dict[str, Any]) -> None:
    check(decide(snap, _after_atomic(*cmd(5, StepKind.GO_NO_GO))), kind, **payload)


def test_h4_reopen_rides_on_a_decision_reentry_too() -> None:
    snap = replace(LOW_OUTCOME, waived=True, decision_needed=True)
    s = decide(snap, _after_atomic(*cmd(5, StepKind.GO_NO_GO)))
    check(s, StepKind.RUN_CHILD, role="decision", preconditions=["reopen", "clear_records"])


def test_atomic_design_remedy_is_not_a_pre_deferral_remedy() -> None:
    snap = replace(LOW_OUTCOME, design_failed=True)
    check(decide(snap, _after_atomic()), StepKind.REFINE_GAP, role="design")
    assert "pre_deferral" not in decide(snap, _after_atomic()).payload


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def test_runaway_pass_stops_infra() -> None:
    many = [
        cmd(i, StepKind.RESCORE, origin="wire", attempt=1) for i in range(1, MAX_DONE_PER_PASS + 2)
    ]
    check(decide(LOW, log(start(), *many)), StepKind.STOP, outcome="ladder_error")


def test_applied_pass_replays_its_terminal() -> None:
    facts = log(start(), child(1, "READY"), cmd(2, StepKind.FINISH, outcome="ready"))
    check(decide(READY, facts), StepKind.FINISH, outcome="ready")


def test_decide_is_pure() -> None:
    facts = _after_sr(pre="")
    a, b = decide(LOW, facts), decide(LOW, facts)
    assert a == b
    assert facts == _after_sr(pre="")


# ---------------------------------------------------------------------------
# ENH-3630: budget arithmetic, pass-id default, import boundary
# ---------------------------------------------------------------------------


def test_max_steps_arithmetic() -> None:
    """AC: cap and max_steps = 4 * cap + 3 are exported with the arithmetic pinned."""
    assert DONE_FACT_CAP == MAX_DONE_PER_PASS
    assert MAX_STEPS == 4 * DONE_FACT_CAP + 3
    # Must exceed the spike's empirical (not derived) MAX_DONE_PER_PASS = 15 --
    # the legal worst case is bigger than anything the spike's scenarios observed.
    assert DONE_FACT_CAP > 15


def test_absent_pass_file_reads_as_pass_zero(tmp_path) -> None:
    assert current_pass(tmp_path, ID) == "0"
    (tmp_path / f"prep-pass-{ID}").write_text("")
    assert current_pass(tmp_path, ID) == "0"


def test_pure_layer_imports_no_cli_module() -> None:
    """AC: importing the pure layer imports no ``little_loops.cli`` module.

    Run in a fresh interpreter (subprocess) so an already-imported
    ``little_loops.cli.*`` module elsewhere in the test session's ``sys.modules``
    can't hide a real boundary violation.
    """
    import subprocess

    code = (
        "import sys\n"
        "from little_loops.preparation_policy import (\n"
        "    decide, Step, StepKind, Facts, IssueSnapshot,\n"
        ")\n"
        "leaked = [\n"
        "    m for m in sys.modules\n"
        "    if m == 'little_loops.cli' or m.startswith('little_loops.cli.')\n"
        "]\n"
        "assert not leaked, leaked\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
