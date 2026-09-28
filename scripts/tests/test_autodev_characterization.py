"""Characterization pins for autodev's preparation ladder (ENH-3618, remapped by ENH-3623).

Each scenario runs the REAL ``autodev.yaml`` -> ``prepare-issue.yaml`` chain under
``PersistentExecutor`` with a stub ``refine-to-ready-issue`` and scripted slash
commands (``tests.autodev_harness``), and pins the artifacts: the autodev state
path, the prepare-issue dispatch-loop path, ``autodev-skipped.txt`` rows, queue,
staged/passed/unverified, the ``prepare-issue`` run-record token per issue, issue
status/deferred_reason, ``summary.json``, the slash-command sequence and the
repair-cycle counter.

These are characterization pins, not a spec: where the behavior looks wrong the
scenario says so in a ``# BUG-LIKE:`` comment instead of asserting the "right"
answer. ENH-3623 moved the second-pass ladder from autodev into the prepare-issue
dispatch loop; it remapped every path and changed only the enumerated accepted
behavior changes (``# ENH-3623`` comments; the replaced values live in
``test_preparation_policy_parity.PRE_CUTOVER_PINS``).

One scenario per terminal-table row, plus the wrapper's own terminals, a resume
characterization, and a harness smoke test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.autodev_harness import (
    PREPARE_ISSUE_YAML,
    AutodevResult,
    ChildSpec,
    Crash,
    Effects,
    InnerRun,
    Scenario,
    SlashResponse,
    run_autodev,
)

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Scenario building blocks
# ---------------------------------------------------------------------------

ID = "ENH-9001"
READY = {"confidence_score": 90, "outcome_confidence": 80}
LOW_READINESS = {"confidence_score": 70, "outcome_confidence": 80}
#: Readiness passes, outcome fails. reconcile_attempted keeps check_reconcile_needed
#: from firing on the readiness plateau, so the guard-2 branch is reached directly.
LOW_OUTCOME = {"confidence_score": 90, "outcome_confidence": 50, "reconcile_attempted": True}
#: Arms the Program Design gate: an issue with no ``## Program Design`` fails check-design.
DESIGN_GATE_ARMED = {".ll/program-design-cutover.json": '{"date": "2000-01-01"}'}

NOOP = SlashResponse()
SIZE_REVIEW_LEAF = SlashResponse(output="[{id}] skipped: structural score 3 (Small) - leaf-sized")
SIZE_REVIEW_GUARD2 = SlashResponse(output="[{id}] skipped: score 9 (Very Large) - atomic")
RECONCILE = SlashResponse(effects=Effects(frontmatter={"reconcile_attempted": True}))
GO = SlashResponse(output="GO", effects=Effects(frontmatter={"outcome_gate_waived": True}))
NO_GO = SlashResponse(output="NO-GO")


def confidence(readiness: int, outcome: int, **frontmatter: Any) -> SlashResponse:
    """A /ll:confidence-check that writes these scores (and optional flags)."""
    return SlashResponse(effects=Effects(scores=(readiness, outcome), frontmatter=frontmatter))


def done() -> InnerRun:
    return InnerRun()


def stop(legacy_class: str, **kw: Any) -> InnerRun:
    return InnerRun(terminal="failed", legacy_class=legacy_class, **kw)


LADDER_TO_RECONCILE = {
    "issue-size-review": (SIZE_REVIEW_LEAF,),
    "reconcile-issue": (RECONCILE,),
}

# ---------------------------------------------------------------------------
# Expected-path segments (autodev, depth 0)
# ---------------------------------------------------------------------------

DEQUEUE = (
    "dequeue_next",
    "check_status_at_dequeue",
    "check_blockers_at_dequeue",
    "check_gate_at_dequeue",
    "refine_current",
)
PREFIX = ("init", *DEQUEUE)
REFINE_OK = ("copy_broke_down", "route_refine_success")
IMPLEMENT = (
    "check_proof_defer_or_implement",
    "implement_current",
    "verify_impl_closed",
    "route_quality_gate",
)
END = ("dequeue_next", "finalize_done")
#: ENH-3623: autodev has no second-pass state; every ladder outcome is one wrapper
#: terminal, so the autodev paths collapse to these four shapes.
READY_PATH = (*PREFIX, *REFINE_OK, "check_passed", *IMPLEMENT, *END)
STOP_PATH = (*PREFIX, "route_refine_outcome", "ledger_child_stop", *END)
INFRA_PATH = (*PREFIX, "route_refine_outcome", "skip_inflight_infra", *END)
RATE_LIMITED_PATH = (*PREFIX, "route_refine_outcome", "finalize_rate_limited", "finalize_done")

# ---------------------------------------------------------------------------
# Expected-path segments (prepare-issue dispatch loop, depth 1)
# ---------------------------------------------------------------------------


def step(kind: str) -> tuple[str, ...]:
    """One dispatched command step: ``select_step -> run_<kind> -> record_step``."""
    return ("select_step", f"run_{kind}", "record_step")


CHILD = step("child")
SIZE_REVIEW = ("select_step", "run_size_review", "classify_guard2", "record_step")
SIZE_REVIEW_G2 = ("select_step", "run_size_review", "classify_guard2", "record_guard2")
APPLY = ("select_step", "apply_outcome")
WRAPPER_DONE = (*CHILD, *APPLY)
#: size review -> reconcile -> rescore -> terminal (the readiness-plateau ladder).
WRAPPER_RECONCILE = (*CHILD, *SIZE_REVIEW, *step("reconcile"), *step("rescore"), *APPLY)
#: ...then the design remedy (refine gap + rescore) before design_gate_failed.
WRAPPER_DESIGN_REMEDY = (
    *CHILD,
    *SIZE_REVIEW,
    *step("reconcile"),
    *step("rescore"),
    *step("refine_gap"),
    *step("rescore"),
    *APPLY,
)
#: guard-2 (atomic) -> wire remediation -> rescore -> go/no-go.
WRAPPER_GO_NO_GO = (
    *CHILD,
    *SIZE_REVIEW_G2,
    *step("wire"),
    *step("rescore"),
    *step("go_no_go"),
    *APPLY,
)
#: missing-artifacts repair: wire -> refine gap -> rescore -> rescore retry.
WRAPPER_RESCORE_RETRY = (
    *CHILD,
    *step("wire"),
    *step("refine_gap"),
    *step("rescore"),
    *step("rescore"),
    *APPLY,
)

SUMMARY_BASE: dict[str, Any] = {
    "verdict": "no-op",
    "closed": 0,
    "not_closed": 0,
    "skipped": 0,
    "gate_blocked": 0,
    "decision_unresolved": 0,
    "not_started": 0,
    "inflight_unresolved": 0,
    "abandoned": 0,
    "stop_reason": "completed",
    "pending": 0,
    "proof_gate_infra": 0,
    "closed_implemented": 0,
    "closed_cancelled": 0,
    "quality_failed": 0,
    "quality_gate_infra": 0,
    "record_absent": 0,
    "record_ledger_mismatch": 0,
}


def summary(**overrides: Any) -> dict[str, Any]:
    return {**SUMMARY_BASE, **overrides}


@dataclass(frozen=True)
class Expected:
    """Today's pinned artifacts for one scenario (see :func:`observed`)."""

    path: tuple[str, ...]
    records: dict[str, str]
    issues: dict[str, tuple[str | None, str | None]]
    summary: dict[str, Any]
    wrapper_path: tuple[str, ...] = WRAPPER_DONE
    skipped: tuple[str, ...] = ()
    queue: tuple[str, ...] = ()
    staged: tuple[str, ...] = ()
    passed: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()
    dequeued: tuple[str, ...] = (ID,)
    slash: tuple[str, ...] = ()
    repair_cycle: str | None = "1"
    ll_auto: tuple[str, ...] = ()
    ledgers: dict[str, list[str]] = field(default_factory=dict)
    terminated_by: str = "terminal"
    final_state: str = "done"
    # Number of rate-limit/backoff waits the scenario is expected to request
    # (instant under the harness). 0 means any wait is a hermeticity failure.
    rate_limit_waits: int = 0


def observed(r: AutodevResult) -> dict[str, Any]:
    """Project a harness result onto the pinned fields."""
    return {
        "terminated_by": r.terminated_by,
        "final_state": r.final_state,
        "path": tuple(r.path),
        "wrapper_path": tuple(r.wrapper_path),
        "skipped": tuple(r.skipped),
        "queue": tuple(r.queue),
        "staged": tuple(r.staged),
        "passed": tuple(r.passed),
        "unverified": tuple(r.unverified),
        "dequeued": tuple(r.dequeued),
        "records": r.records,
        "issues": r.issues,
        "summary": r.summary,
        "slash": tuple(r.slash_commands),
        "repair_cycle": r.repair_cycle_count,
        "ll_auto": tuple(r.ll_auto_calls),
        "ledgers": r.ledgers,
    }


def expected_view(e: Expected) -> dict[str, Any]:
    return {
        "terminated_by": e.terminated_by,
        "final_state": e.final_state,
        "path": e.path,
        "wrapper_path": e.wrapper_path,
        "skipped": e.skipped,
        "queue": e.queue,
        "staged": e.staged,
        "passed": e.passed,
        "unverified": e.unverified,
        "dequeued": e.dequeued,
        "records": e.records,
        "issues": e.issues,
        "summary": e.summary,
        "slash": e.slash,
        "repair_cycle": e.repair_cycle,
        "ll_auto": e.ll_auto,
        "ledgers": e.ledgers,
    }


# ---------------------------------------------------------------------------
# The table. ENH-3623 remapped every path onto the dispatch loop and folded in the
# accepted behavior changes; each changed field says so in an ``# ENH-3623`` comment
# and ``test_preparation_policy_parity.PRE_CUTOVER_PINS`` keeps the value it replaced.
# ---------------------------------------------------------------------------

SCENARIOS: list[tuple[Scenario, Expected]] = [
    # -- ladder complete, gates pass (terminal table: ready) ----------------------
    (
        Scenario(name="ready_implement_closed", frontmatter=READY, inner_runs={ID: (done(),)}),
        Expected(
            path=READY_PATH,
            staged=(ID,),
            passed=(ID,),
            records={ID: "READY"},
            issues={ID: ("done", None)},
            summary=summary(verdict="success", closed=1, closed_implemented=1),
            ll_auto=(ID,),
        ),
    ),
    # -- design_gate_failed ----------------------------------------------------
    (
        Scenario(
            name="design_gate_failed",
            frontmatter=LOW_READINESS,
            project_files=DESIGN_GATE_ARMED,
            inner_runs={ID: (done(),)},
            slash={
                **LADDER_TO_RECONCILE,
                "confidence-check": (confidence(70, 80),),
                "refine-issue": (NOOP,),  # the design remedy does not fix the section
            },
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_DESIGN_REMEDY,
            skipped=(f"{ID}  design_gate_failed",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "design_gate_failed")},
            summary=summary(skipped=1),
            slash=(
                f"issue-size-review {ID}",
                f"reconcile-issue {ID}",
                f"confidence-check {ID}",
                f"refine-issue {ID}",
                f"confidence-check {ID}",
            ),
            repair_cycle="4",
        ),
    ),
    # -- ENH-3625: first gate hard-ANDs check-design -----------------------------
    (
        Scenario(
            name="first_gate_design_failure",
            frontmatter=READY,
            project_files=DESIGN_GATE_ARMED,
            inner_runs={ID: (done(),)},
            slash={
                **LADDER_TO_RECONCILE,
                "confidence-check": (confidence(90, 80),),
                "refine-issue": (NOOP,),
            },
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_DESIGN_REMEDY,
            skipped=(f"{ID}  design_gate_failed",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "design_gate_failed")},
            summary=summary(skipped=1),
            slash=(
                f"issue-size-review {ID}",
                f"reconcile-issue {ID}",
                f"confidence-check {ID}",
                f"refine-issue {ID}",
                f"confidence-check {ID}",
            ),
            repair_cycle="4",
        ),
    ),
    # -- oversized_atomic, go/no-go escalation, waiver declined -----------------
    (
        Scenario(
            name="oversized_atomic_no_go",
            frontmatter=LOW_OUTCOME,
            inner_runs={ID: (done(),)},
            slash={
                "issue-size-review": (SIZE_REVIEW_GUARD2,),
                "wire-issue": (NOOP,),
                "confidence-check": (confidence(90, 50),),
                "go-no-go": (NO_GO,),
            },
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_GO_NO_GO,
            skipped=(f"{ID}  oversized_atomic",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "oversized_atomic")},
            summary=summary(skipped=1),
            slash=(
                f"issue-size-review {ID}",
                f"wire-issue {ID}",
                f"confidence-check {ID}",
                f"go-no-go {ID}",
            ),
            repair_cycle="2",
        ),
    ),
    # -- oversized_atomic, GO -> reopen -> implement ------------------------------
    (
        Scenario(
            name="oversized_atomic_go_reopen_implement",
            frontmatter=LOW_OUTCOME,
            inner_runs={ID: (done(),)},
            slash={
                "issue-size-review": (SIZE_REVIEW_GUARD2,),
                "wire-issue": (NOOP,),
                "confidence-check": (confidence(90, 50),),
                "go-no-go": (GO,),
            },
        ),
        Expected(
            path=READY_PATH,
            wrapper_path=WRAPPER_GO_NO_GO,
            staged=(ID,),
            passed=(ID,),
            # ENH-3623 (BUG-LIKE pin fixed, terminal table `ready`): the GO path ends
            # with a READY record (was MISSING). Still BUG-LIKE: the reopen leaves
            # deferred_reason: oversized_atomic on the now-done issue.
            records={ID: "READY"},
            issues={ID: ("done", "oversized_atomic")},
            summary=summary(verdict="success", closed=1, closed_implemented=1),
            slash=(
                f"issue-size-review {ID}",
                f"wire-issue {ID}",
                f"confidence-check {ID}",
                f"go-no-go {ID}",
            ),
            repair_cycle="2",
            ll_auto=(ID,),
        ),
    ),
    # -- readiness_stagnated -------------------------------------------------------
    (
        Scenario(
            name="readiness_stagnated",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={**LADDER_TO_RECONCILE, "confidence-check": (confidence(70, 80),)},
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_RECONCILE,
            skipped=(f"{ID}  readiness_stagnated",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "readiness_stagnated")},
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- low_readiness (rescore improved but still below threshold) ---------------
    (
        Scenario(
            name="low_readiness",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={**LADDER_TO_RECONCILE, "confidence-check": (confidence(80, 80),)},
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_RECONCILE,
            skipped=(f"{ID}  low_readiness",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "low_readiness")},
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- decision_unresolved after the post-size-review rescore -------------------
    (
        Scenario(
            name="decision_unresolved_at_recheck",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={
                **LADDER_TO_RECONCILE,
                "confidence-check": (confidence(70, 80, decision_needed=True),),
            },
        ),
        Expected(
            path=STOP_PATH,
            wrapper_path=WRAPPER_RECONCILE,
            skipped=(f"{ID}  decision_unresolved",),
            records={ID: "BLOCKED:decision_unresolved"},
            issues={ID: ("deferred", "decision_unresolved")},
            # BUG-LIKE: finalize_done's decision_unresolved bucket counts only the
            # child's autodev-decision-unresolved.txt ledger, so the wrapper's own
            # decision_unresolved row lands in the generic `skipped` count (1) and
            # `decision_unresolved` stays 0.
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- decision_unresolved from the selector re-entry cap -----------------------
    (
        Scenario(
            name="decision_reentry_exhausted",
            frontmatter={**READY, "decision_needed": True},
            inner_runs={ID: (done(), done())},
        ),
        Expected(
            path=STOP_PATH,
            # the DECISION re-entry is a second RUN_CHILD step inside one wrapper run
            wrapper_path=(*CHILD, *CHILD, *APPLY),
            skipped=(f"{ID}  decision_unresolved",),
            records={ID: "BLOCKED:decision_unresolved"},
            issues={ID: ("deferred", "decision_unresolved")},
            # BUG-LIKE: same bucket mismatch as decision_unresolved_at_recheck.
            summary=summary(skipped=1),
            repair_cycle="2",
        ),
    ),
    # -- size-review decomposition (children enqueued by autodev) -----------------
    (
        Scenario(
            name="size_review_decomposition",
            frontmatter=LOW_READINESS,
            inner_runs={
                ID: (done(),),
                "ENH-9002": (done(),),
                "ENH-9003": (stop("quality"),),
            },
            slash={
                "issue-size-review": (
                    SlashResponse(
                        output="[{id}] decomposed into ENH-9002, ENH-9003",
                        effects=Effects(
                            children=(
                                ChildSpec("ENH-9002", ID, frontmatter=READY),
                                ChildSpec("ENH-9003", ID),
                            )
                        ),
                    ),
                ),
            },
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "detect_children",
                "enqueue_children",
                *DEQUEUE,
                *REFINE_OK,
                "check_passed",
                *IMPLEMENT,
                *DEQUEUE,
                "route_refine_outcome",
                "ledger_child_stop",
                *END,
            ),
            wrapper_path=(*CHILD, *SIZE_REVIEW, *APPLY, *WRAPPER_DONE, *WRAPPER_DONE),
            skipped=(f"{ID}  decomposed", "ENH-9003  refine_failed"),
            staged=("ENH-9002",),
            passed=("ENH-9002",),
            dequeued=(ID, "ENH-9002", "ENH-9003"),
            # ENH-3623 (BUG-LIKE pin fixed, terminal table `decomposed`): the parent
            # records DECOMPOSED with child_ids (was the inner run's stale BLOCKED).
            records={ID: "DECOMPOSED", "ENH-9002": "READY", "ENH-9003": "BLOCKED:quality"},
            issues={ID: ("done", None), "ENH-9002": ("done", None), "ENH-9003": ("open", None)},
            summary=summary(verdict="success", closed=1, skipped=2, closed_implemented=1),
            slash=(f"issue-size-review {ID}",),
            repair_cycle="0",  # reset by the last dequeue (ENH-9003 never re-entered)
            ll_auto=("ENH-9002",),
            ledgers={"autodev-new-children.txt": ["ENH-9002", "ENH-9003"]},
        ),
    ),
    # -- resolved parent: the reconcile resolves the issue mid-ladder --------------
    (
        Scenario(
            name="resolved_parent_at_recheck",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={
                "issue-size-review": (SIZE_REVIEW_LEAF,),
                # the reconcile pass resolves the issue out from under the ladder
                "reconcile-issue": (
                    SlashResponse(
                        effects=Effects(status="done", frontmatter={"reconcile_attempted": True})
                    ),
                ),
                "confidence-check": (confidence(70, 80),),
            },
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "detect_children",
                "check_parent_resolved",
                "recover_subloop_children",
                *END,
            ),
            wrapper_path=WRAPPER_RECONCILE,
            skipped=(f"{ID}  resolved_by_subloop",),
            # ENH-3623 (BUG-LIKE pin fixed, DECOMPOSED guarantee): a resolved parent
            # records DECOMPOSED (was the inner run's forwarded BLOCKED);
            # recover_subloop_children still writes the resolved_by_subloop row.
            records={ID: "DECOMPOSED"},
            issues={ID: ("done", None)},
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- resolved parent: inner DECOMPOSED, no children, parent done ---------------
    (
        Scenario(
            name="inner_decomposed_parent_resolved",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (InnerRun(broke_down=True, effects=Effects(status="done")),)},
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "detect_children",
                "check_parent_resolved",
                "recover_subloop_children",
                *END,
            ),
            skipped=(f"{ID}  resolved_by_subloop",),
            records={ID: "DECOMPOSED"},
            issues={ID: ("done", None)},
            summary=summary(skipped=1),
        ),
    ),
    # -- scores absent after repair (rescore wrote nothing, twice) ------------------
    (
        Scenario(
            name="scores_absent_after_repair",
            frontmatter={**LOW_READINESS, "missing_artifacts": True},
            inner_runs={ID: (done(),)},
            slash={"wire-issue": (NOOP,), "refine-issue": (NOOP,), "confidence-check": (NOOP,)},
        ),
        Expected(
            path=INFRA_PATH,
            wrapper_path=WRAPPER_RESCORE_RETRY,
            # ENH-3623 accepted change 1: a scores-absent stop ledgers one
            # refine_failed_infra row and records RETRYABLE_ERROR:infra (was no row, a
            # forwarded BLOCKED record and an autodev-scores-absent.txt entry, which
            # lost its only writer with mark_scores_absent_infra).
            skipped=(f"{ID}  refine_failed_infra",),
            records={ID: "RETRYABLE_ERROR:infra"},
            issues={ID: ("open", None)},
            summary=summary(),
            slash=(
                f"wire-issue {ID}",
                f"refine-issue {ID}",
                f"confidence-check {ID}",
                f"confidence-check {ID}",
            ),
            repair_cycle="2",
        ),
    ),
    # -- an on_error drop: prep step exits 2 on the size-review follow-up decision --
    (
        Scenario(
            name="on_error_drop",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={"issue-size-review": (SIZE_REVIEW_LEAF,)},
            # the 3rd select_step is the post-size-review decision (was enqueue_or_skip)
            faults={"select_step#3": 2},
        ),
        Expected(
            path=INFRA_PATH,
            wrapper_path=(*CHILD, *SIZE_REVIEW, *APPLY),
            # ENH-3623 accepted change 1: the drop ledgers refine_failed_infra through
            # the no-terminal-intent fallback and clears autodev-inflight, so the run
            # no longer ends `phantom` in `failed` (was inflight_at_finalize).
            skipped=(f"{ID}  refine_failed_infra",),
            records={ID: "RETRYABLE_ERROR:infra"},
            issues={ID: ("open", None)},
            summary=summary(),
            slash=(f"issue-size-review {ID}",),
            repair_cycle="2",
        ),
    ),
    # -- rate-limit exhaustion on a ladder slash state -----------------------------
    (
        Scenario(
            name="ladder_rate_limit_halts",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={
                "issue-size-review": (
                    SlashResponse(output="API Error: 429 rate limit exceeded", exit_code=1),
                ),
            },
        ),
        Expected(
            # BUG-3622: the with_rate_limit_handling slash state runs to its 21600 s
            # budget (12 attempts, 12 instant waits), then on_rate_limit_exhausted ->
            # mark_rate_limited halts the queue through finalize_rate_limited.
            path=RATE_LIMITED_PATH,
            wrapper_path=(
                *CHILD,
                "select_step",
                *("run_size_review",) * 12,
                "mark_rate_limited",
            ),
            unverified=(f"{ID}  inflight_at_finalize",),
            # ENH-3623 (terminal table `rate_limited`): mark_rate_limited records a
            # fresh RETRYABLE_ERROR:rate_limited (was the inner run's stale BLOCKED).
            records={ID: "RETRYABLE_ERROR:rate_limited"},
            issues={ID: ("open", None)},
            summary=summary(
                verdict="rate_limited",
                not_closed=1,
                inflight_unresolved=1,
                abandoned=1,
                stop_reason="rate_limit",
            ),
            slash=(f"issue-size-review {ID}",) * 12,
            rate_limit_waits=12,
        ),
    ),
    # -- inner DECOMPOSED with children (detect_children -> enqueue_children) ------
    (
        Scenario(
            name="inner_decomposed",
            frontmatter=LOW_READINESS,
            inner_runs={
                ID: (
                    InnerRun(
                        broke_down=True,
                        effects=Effects(
                            children=(ChildSpec("ENH-9002", ID), ChildSpec("ENH-9003", ID))
                        ),
                    ),
                ),
                "ENH-9002": (stop("quality"),),
                "ENH-9003": (stop("quality"),),
            },
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "detect_children",
                "enqueue_children",
                *DEQUEUE,
                "route_refine_outcome",
                "ledger_child_stop",
                *DEQUEUE,
                "route_refine_outcome",
                "ledger_child_stop",
                *END,
            ),
            wrapper_path=WRAPPER_DONE * 3,
            skipped=(f"{ID}  decomposed", "ENH-9002  refine_failed", "ENH-9003  refine_failed"),
            dequeued=(ID, "ENH-9002", "ENH-9003"),
            records={
                ID: "DECOMPOSED",
                "ENH-9002": "BLOCKED:quality",
                "ENH-9003": "BLOCKED:quality",
            },
            issues={ID: ("done", None), "ENH-9002": ("open", None), "ENH-9003": ("open", None)},
            summary=summary(skipped=3),
            repair_cycle="0",
            ledgers={"autodev-new-children.txt": ["ENH-9002", "ENH-9003"]},
        ),
    ),
    # -- inner CANCELLED ------------------------------------------------------------
    (
        Scenario(
            name="inner_cancelled",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (InnerRun(effects=Effects(status="cancelled")),)},
        ),
        Expected(
            path=(*PREFIX, *REFINE_OK, "skip_cancelled", *END),
            skipped=(f"{ID}  cancelled",),
            records={ID: "CANCELLED"},
            issues={ID: ("cancelled", None)},
            summary=summary(skipped=1),
        ),
    ),
    # -- wrapper terminals: inner stop / inner death / inner rate limit -------------
    (
        Scenario(
            name="inner_stop_gate_unmet",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (stop("gate_unmet"),)},
        ),
        Expected(
            path=STOP_PATH,
            skipped=(f"{ID}  refine_failed",),  # written by prepare-issue's `prep apply`
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("open", None)},
            summary=summary(skipped=1),
            repair_cycle="0",
        ),
    ),
    (
        Scenario(
            name="inner_error",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (InnerRun(terminal="error", write_record=False),)},
        ),
        Expected(
            path=INFRA_PATH,
            skipped=(f"{ID}  refine_failed_infra",),
            records={ID: "RETRYABLE_ERROR:infra"},
            issues={ID: ("open", None)},
            summary=summary(),
            repair_cycle="0",
        ),
    ),
    (
        Scenario(
            name="inner_rate_limited",
            frontmatter=LOW_READINESS,
            queue=f"{ID},ENH-9004",
            extra_issues=(ChildSpec("ENH-9004", None),),
            inner_runs={ID: (stop("infra", evidence_refs=("rate_limit_exhausted",)),)},
        ),
        Expected(
            path=RATE_LIMITED_PATH,
            queue=("ENH-9004",),
            unverified=(f"{ID}  inflight_at_finalize",),
            records={ID: "RETRYABLE_ERROR:rate_limited", "ENH-9004": "MISSING"},
            issues={ID: ("open", None), "ENH-9004": ("open", None)},
            summary=summary(
                verdict="rate_limited",
                not_closed=1,
                inflight_unresolved=1,
                abandoned=1,
                stop_reason="rate_limit",
                pending=1,
            ),
            repair_cycle="0",
        ),
    ),
]


def _assert_hermetic(r: AutodevResult, rate_limit_waits: int = 0) -> None:
    assert r.unscripted == [], f"scenario reached unscripted calls: {r.unscripted}"
    assert len(r.sleeps) == rate_limit_waits, (
        f"expected {rate_limit_waits} rate-limit/backoff waits, got: {r.sleeps}"
    )
    assert r.cli_failures == [], f"ll-issues fork-server calls lost: {r.cli_failures}"


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("scenario", "expected"),
    [pytest.param(s, e, id=s.name) for s, e in SCENARIOS],
)
def test_autodev_characterization(
    scenario: Scenario,
    expected: Expected,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = run_autodev(scenario, tmp_path, monkeypatch)
    _assert_hermetic(r, expected.rate_limit_waits)
    assert observed(r) == expected_view(expected)


# ---------------------------------------------------------------------------
# Resume characterization: kill the process mid-run, resume via PersistentExecutor.
# ---------------------------------------------------------------------------

_STAGNATED = next(s for s, _ in SCENARIOS if s.name == "readiness_stagnated")
_STAGNATED_EXPECTED = next(e for s, e in SCENARIOS if s.name == "readiness_stagnated")


def _with_crash(crash: Crash) -> Scenario:
    return Scenario(
        name=f"{_STAGNATED.name}+crash",
        frontmatter=_STAGNATED.frontmatter,
        inner_runs=_STAGNATED.inner_runs,
        slash=_STAGNATED.slash,
        crash=crash,
    )


def _replayed(state: str, path: tuple[str, ...]) -> tuple[str, ...]:
    """*path* with the first visit to *state* repeated (the resumed re-entry)."""
    i = path.index(state)
    return (*path[: i + 1], state, *path[i + 1 :])


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("crash", "path", "wrapper_path", "repair_cycle"),
    [
        pytest.param(
            # the 3rd record_step records the reconcile's done fact
            Crash(state="record_step", occurrence=3, when="after"),
            _replayed("refine_current", STOP_PATH),
            # autodev persisted refine_current, so the wrapper restarts at select_step,
            # which decides the next step from the fact log (no replayed command)
            (*CHILD, *SIZE_REVIEW, *step("reconcile"), *step("rescore"), *APPLY),
            # ENH-3623: the counter is a projection of done facts, so a kill after
            # the write no longer double-counts (ENH-3618 pinned "4" here).
            "3",
            id="after_counter_increment_counts_once",
        ),
        pytest.param(
            Crash(state="run_reconcile", when="before"),
            _replayed("refine_current", STOP_PATH),
            # the open RECONCILE intent is replayed: one reconcile call in total
            (
                *CHILD,
                *SIZE_REVIEW,
                "select_step",
                "run_reconcile",
                *step("reconcile"),
                *step("rescore"),
                *APPLY,
            ),
            "3",
            id="before_ladder_slash_is_clean",
        ),
        pytest.param(
            Crash(state="scripted_run", when="after"),
            _replayed("refine_current", STOP_PATH),
            # the inner run finished but its done fact was never recorded: the open
            # RUN_CHILD intent is replayed (one replayed command)
            ("select_step", "run_child", *WRAPPER_RECONCILE),
            "3",
            id="inside_inner_loop_replays_one_child_run",
        ),
    ],
)
def test_autodev_resume_characterization(
    crash: Crash,
    path: tuple[str, ...],
    wrapper_path: tuple[str, ...],
    repair_cycle: str,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = run_autodev(_with_crash(crash), tmp_path, monkeypatch)
    _assert_hermetic(r)
    assert r.crashed_at is not None and r.crashed_at["state"] == crash.state
    assert r.resumed_terminated_by == "terminal"
    expected = expected_view(_STAGNATED_EXPECTED)
    expected.update(path=path, wrapper_path=wrapper_path, repair_cycle=repair_cycle)
    assert observed(r) == expected


# ---------------------------------------------------------------------------
# Harness smoke: the Phase 2 parameters are wired and change nothing when inert.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(300)
def test_harness_accepts_replacement_prepare_issue_and_autodev_transform(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario, expected = SCENARIOS[0]
    copy = tmp_path / "prepare-issue-copy.yaml"
    copy.write_text(PREPARE_ISSUE_YAML.read_text())
    seen: list[str] = []

    def identity(data: dict[str, Any]) -> dict[str, Any]:
        seen.append(data["name"])
        return data

    run_root = tmp_path / "run"
    run_root.mkdir()
    # a replacement prepare-issue and an identity transform change nothing
    r = run_autodev(
        scenario,
        run_root,
        monkeypatch,
        prepare_issue_yaml=copy,
        autodev_transform=identity,
    )
    _assert_hermetic(r)
    assert seen == ["autodev"]
    loops_dir = run_root / "harness" / "loops"
    assert r.loop_yaml_paths["autodev"] == [str(loops_dir / "autodev.yaml")]
    assert r.loop_yaml_paths["prepare-issue"] == [str(loops_dir / "prepare-issue.yaml")]
    assert r.loop_yaml_paths["refine-to-ready-issue"] == [
        str(loops_dir / "refine-to-ready-issue.yaml")
    ]
    assert observed(r) == expected_view(expected)
