"""Characterization pins for autodev's second-pass ladder (ENH-3606, plan item 1C).

Each scenario runs the REAL ``autodev.yaml`` -> ``prepare-issue.yaml`` chain under
``PersistentExecutor`` with a stub ``refine-to-ready-issue`` and scripted slash
commands (``tests.autodev_harness``), and pins TODAY's artifacts: the autodev
state path, ``autodev-skipped.txt`` rows, queue, staged/passed/unverified, the
``prepare-issue`` run-record token per issue, issue status/deferred_reason,
``summary.json``, the slash-command sequence and the repair-cycle counter.

These are characterization pins, not a spec: where today's behavior looks wrong
the scenario says so in a ``# BUG-LIKE:`` comment instead of asserting the
"right" answer. ENH-3606 (or the preparation-policy spike that may replace it)
re-runs the same ``SCENARIOS`` table against a relocated ladder; the only diffs
it may show are its enumerated accepted behavior changes.

One scenario per ENH-3606 "Terminal table" row, plus the prepare-issue wrapper's
own terminals, a resume characterization, and a harness smoke test.
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
REFINE_OK = ("count_repair_cycle_refine", "copy_broke_down", "route_refine_success")
IMPLEMENT = (
    "check_proof_defer_or_implement",
    "implement_current",
    "verify_impl_closed",
    "route_quality_gate",
)
TO_SIZE_REVIEW = (
    "check_passed",
    "select_obligation_post_refine",
    "check_missing_artifacts",
    "detect_children",
    "size_review_snap",
    "check_broke_down",
    "check_parent_resolved",
    "recheck_scores",
    "run_size_review",
    "count_repair_cycle_size_review",
    "enqueue_or_skip",
)
POST_SIZE_REVIEW = (
    "check_parent_resolved_post_size_review",
    "select_obligation_post_size_review",
    "check_reconcile_needed",
)
RESCORE = ("clear_scores", "rerun_confidence", "check_scores_present", "route_after_rescore")
RECONCILE_TO_RECHECK = (
    "reconcile_current",
    "count_repair_cycle_reconcile",
    *RESCORE,
    "recheck_after_size_review",
    "check_pre_deferral_remedy",
)
GUARD2_TO_GO_NO_GO = (
    "check_size_review_ran_this_pass",
    "check_guard2_verdict",
    "check_readiness_for_atomic_remediation",
    "remediate_oversized_atomic",
    "mark_rescore_origin_atomic",
    *RESCORE,
    "regate_after_atomic_remediation",
    "check_atomic_design_remedy",
    "check_go_no_go_eligible",
    "run_go_no_go",
    "check_go_no_go_waiver",
)
END = ("dequeue_next", "finalize_done")
LADDER_RECONCILE_PATH = (
    *PREFIX,
    *REFINE_OK,
    *TO_SIZE_REVIEW,
    *POST_SIZE_REVIEW,
    *RECONCILE_TO_RECHECK,
    *END,
)
WRAPPER_DONE = ("clear_record", "run_refine_to_ready", "forward_done")
WRAPPER_STOP = ("clear_record", "run_refine_to_ready", "forward_stop")

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
# The table. Phase 2 re-runs every Scenario here against a replacement
# prepare-issue (run_autodev(..., prepare_issue_yaml=..., autodev_transform=...)).
# ---------------------------------------------------------------------------

SCENARIOS: list[tuple[Scenario, Expected]] = [
    # -- ladder complete, gates pass (ENH-3606 row: mark_ready) -------------------
    (
        Scenario(name="ready_implement_closed", frontmatter=READY, inner_runs={ID: (done(),)}),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "check_passed",
                "select_obligation_pre_implement",
                *IMPLEMENT,
                *END,
            ),
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
                "refine-issue": (NOOP,),  # refine_for_design does not fix the section
            },
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                *TO_SIZE_REVIEW,
                *POST_SIZE_REVIEW,
                *RECONCILE_TO_RECHECK,
                "dispatch_design_remedy",
                "refine_for_design",
                "count_repair_cycle_refine_for_design",
                *RESCORE,
                "recheck_after_size_review",
                "check_pre_deferral_remedy",
                *END,
            ),
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
    # -- ENH-3625: first gate (check_passed) hard-ANDs check-design --------------
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
            path=(
                *PREFIX,
                *REFINE_OK,
                *TO_SIZE_REVIEW,
                *POST_SIZE_REVIEW,
                *RECONCILE_TO_RECHECK,
                "dispatch_design_remedy",
                "refine_for_design",
                "count_repair_cycle_refine_for_design",
                *RESCORE,
                "recheck_after_size_review",
                "check_pre_deferral_remedy",
                *END,
            ),
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
            path=(
                *PREFIX,
                *REFINE_OK,
                *TO_SIZE_REVIEW,
                *POST_SIZE_REVIEW,
                *GUARD2_TO_GO_NO_GO,
                *END,
            ),
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
    # -- oversized_atomic, GO -> reopen_waived -> implement ----------------------
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
            path=(
                *PREFIX,
                *REFINE_OK,
                *TO_SIZE_REVIEW,
                *POST_SIZE_REVIEW,
                *GUARD2_TO_GO_NO_GO,
                "reopen_waived",
                "select_obligation_pre_implement",
                *IMPLEMENT,
                *END,
            ),
            staged=(ID,),
            passed=(ID,),
            # BUG-LIKE: reopen_waived clears the oversized_atomic record and nothing
            # writes a success record, so an implemented issue ends with no
            # prepare-issue record (MISSING); set-status open also leaves
            # deferred_reason: oversized_atomic on the now-done issue.
            records={ID: "MISSING"},
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
            path=LADDER_RECONCILE_PATH,
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
            path=LADDER_RECONCILE_PATH,
            skipped=(f"{ID}  low_readiness",),
            records={ID: "DEFERRED:gate_unmet"},
            issues={ID: ("deferred", "low_readiness")},
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- decision_unresolved from recheck_after_size_review (ENH-2936 branch) -----
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
            path=LADDER_RECONCILE_PATH,
            skipped=(f"{ID}  decision_unresolved",),
            records={ID: "BLOCKED:decision_unresolved"},
            issues={ID: ("deferred", "decision_unresolved")},
            # BUG-LIKE: finalize_done's decision_unresolved bucket counts only the
            # child's autodev-decision-unresolved.txt ledger, so autodev's own
            # decision_unresolved row lands in the generic `skipped` count (1) and
            # `decision_unresolved` stays 0.
            summary=summary(skipped=1),
            slash=(f"issue-size-review {ID}", f"reconcile-issue {ID}", f"confidence-check {ID}"),
            repair_cycle="3",
        ),
    ),
    # -- decision_unresolved from record_reentry_exhausted (selector re-entry cap) --
    (
        Scenario(
            name="decision_reentry_exhausted",
            frontmatter={**READY, "decision_needed": True},
            inner_runs={ID: (done(), done())},
        ),
        Expected(
            path=(
                *PREFIX,
                *REFINE_OK,
                "check_passed",
                "select_obligation_pre_implement",
                "refine_current",
                *REFINE_OK,
                "check_passed",
                "select_obligation_pre_implement",
                "record_reentry_exhausted",
                *END,
            ),
            wrapper_path=WRAPPER_DONE * 2,
            skipped=(f"{ID}  decision_unresolved",),
            records={ID: "BLOCKED:decision_unresolved"},
            issues={ID: ("deferred", "decision_unresolved")},
            # BUG-LIKE: same bucket mismatch as decision_unresolved_at_recheck.
            summary=summary(skipped=1),
            repair_cycle="2",
        ),
    ),
    # -- size-review decomposition (children enqueued by enqueue_or_skip) ----------
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
                *TO_SIZE_REVIEW,
                *DEQUEUE,
                *REFINE_OK,
                "check_passed",
                "select_obligation_pre_implement",
                *IMPLEMENT,
                *DEQUEUE,
                "route_refine_outcome",
                "ledger_child_stop",
                *END,
            ),
            wrapper_path=(*WRAPPER_DONE, *WRAPPER_DONE, *WRAPPER_STOP),
            skipped=(f"{ID}  decomposed", "ENH-9003  refine_failed"),
            staged=("ENH-9002",),
            passed=("ENH-9002",),
            dequeued=(ID, "ENH-9002", "ENH-9003"),
            # BUG-LIKE: the decomposed parent keeps the inner run's forwarded BLOCKED
            # record; nothing on the size-review path records DECOMPOSED.
            records={ID: "BLOCKED", "ENH-9002": "READY", "ENH-9003": "BLOCKED:quality"},
            issues={ID: ("done", None), "ENH-9002": ("done", None), "ENH-9003": ("open", None)},
            summary=summary(verdict="success", closed=1, skipped=2, closed_implemented=1),
            slash=(f"issue-size-review {ID}",),
            repair_cycle="0",  # reset by the last dequeue (ENH-9003 never re-entered)
            ll_auto=("ENH-9002",),
            ledgers={"autodev-new-children.txt": ["ENH-9002", "ENH-9003"]},
        ),
    ),
    # -- resolved parent: recheck_after_size_review's done-issue branch ------------
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
            path=LADDER_RECONCILE_PATH,
            skipped=(f"{ID}  resolved_by_subloop",),
            # BUG-LIKE: no record is written on this branch; the inner run's forwarded
            # BLOCKED record is what a record reader sees.
            records={ID: "BLOCKED"},
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
                "size_review_snap",
                "check_broke_down",
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
            path=(
                *PREFIX,
                *REFINE_OK,
                "check_passed",
                "select_obligation_post_refine",
                "check_missing_artifacts",
                "run_wire",
                "count_repair_cycle_wire",
                "run_refine",
                "clear_scores",
                "rerun_confidence",
                "check_scores_present",
                "rerun_confidence",
                "check_scores_present",
                "mark_scores_absent_infra",
                *END,
            ),
            # ENH-3606 accepted change 1: today a scores-absent stop writes no
            # autodev-skipped row and is invisible in summary.json (verdict no-op).
            records={ID: "BLOCKED"},
            issues={ID: ("open", None)},
            summary=summary(),
            slash=(
                f"wire-issue {ID}",
                f"refine-issue {ID}",
                f"confidence-check {ID}",
                f"confidence-check {ID}",
            ),
            repair_cycle="2",
            ledgers={"autodev-scores-absent.txt": [ID]},
        ),
    ),
    # -- an on_error -> dequeue_next drop (enqueue_or_skip harness fault, exit 2) ----
    (
        Scenario(
            name="on_error_drop",
            frontmatter=LOW_READINESS,
            inner_runs={ID: (done(),)},
            slash={"issue-size-review": (SIZE_REVIEW_LEAF,)},
            faults={"enqueue_or_skip": 2},
        ),
        Expected(
            path=(*PREFIX, *REFINE_OK, *TO_SIZE_REVIEW, *END),
            # BUG-LIKE: the drop leaves autodev-inflight set, so finalize_done files
            # the never-staged issue as `inflight_at_finalize` and the run ends
            # `phantom` in the `failed` terminal.
            unverified=(f"{ID}  inflight_at_finalize",),
            records={ID: "BLOCKED"},
            issues={ID: ("open", None)},
            summary=summary(verdict="phantom", not_closed=1, inflight_unresolved=1, abandoned=1),
            slash=(f"issue-size-review {ID}",),
            repair_cycle="2",
            final_state="failed",
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
            # BUG-3622 (fixed): `next:`-routed ladder slash states now run the 429
            # classifier, and in-place rate-limit retries no longer count toward the
            # throttle hard_max, so the with_rate_limit_handling ladder runs to its
            # 21600 s budget (12 attempts, 12 instant waits) and halts the queue
            # through on_rate_limit_exhausted -> finalize_rate_limited.
            # Still BUG-LIKE: the issue stays in flight (inflight_at_finalize) with the
            # inner run's forwarded BLOCKED record; ENH-3606's mark_rate_limited
            # terminal records RETRYABLE_ERROR:rate_limited instead.
            path=(
                *LADDER_RECONCILE_PATH[: LADDER_RECONCILE_PATH.index("run_size_review")],
                *("run_size_review",) * 12,
                "finalize_rate_limited",
                "finalize_done",
            ),
            unverified=(f"{ID}  inflight_at_finalize",),
            records={ID: "BLOCKED"},
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
            wrapper_path=(*WRAPPER_DONE, *WRAPPER_STOP, *WRAPPER_STOP),
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
            path=(*PREFIX, "route_refine_outcome", "ledger_child_stop", *END),
            wrapper_path=WRAPPER_STOP,
            skipped=(f"{ID}  refine_failed",),  # written by prepare-issue's forward_stop
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
            path=(*PREFIX, "route_refine_outcome", "skip_inflight_infra", *END),
            wrapper_path=("clear_record", "run_refine_to_ready", "mark_inner_error"),
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
            path=(*PREFIX, "route_refine_outcome", "finalize_rate_limited", "finalize_done"),
            wrapper_path=WRAPPER_STOP,
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
            Crash(state="count_repair_cycle_reconcile", when="after"),
            _replayed("count_repair_cycle_reconcile", LADDER_RECONCILE_PATH),
            WRAPPER_DONE,
            # BUG-LIKE: state is persisted at state_enter, so a kill after the
            # increment re-runs count_repair_cycle_reconcile on resume and the
            # repair-cycle counter double-counts one reconcile pass (4, not 3).
            "4",
            id="after_counter_increment_double_counts",
        ),
        pytest.param(
            Crash(state="reconcile_current", when="before"),
            _replayed("reconcile_current", LADDER_RECONCILE_PATH),
            WRAPPER_DONE,
            "3",  # the slash never ran before the kill: one call, clean count
            id="before_ladder_slash_is_clean",
        ),
        pytest.param(
            Crash(state="scripted_run", when="after"),
            _replayed("refine_current", LADDER_RECONCILE_PATH),
            # the parent persisted refine_current, so the whole wrapper re-runs
            ("clear_record", "run_refine_to_ready", *WRAPPER_DONE),
            "3",
            id="inside_inner_loop_reruns_wrapper",
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
