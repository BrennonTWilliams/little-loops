"""ENH-3623: the preparation-policy cutover's removed-state register.

ENH-3630 ran the characterization scenarios against a dispatch-loop fixture plus an
in-memory ``autodev.yaml`` transform; ENH-3623 landed both as the built-in
``prepare-issue.yaml`` and ``autodev.yaml``, so :func:`tests.autodev_harness.run_autodev`
now runs the policy directly and this module only keeps what the cutover removed:
the verified 39-state move set (``MOVED_STATES``) plus ``size_review_snap`` /
``check_broke_down`` / ``mark_scores_absent_infra`` (``DELETED_STATES``), and
:func:`state_targets` for edge checks.
"""

from __future__ import annotations

from typing import Any

#: ENH-3606 "Verified move set (39 states)".
MOVED_STATES: tuple[str, ...] = (
    "select_obligation_post_refine",
    "select_obligation_pre_implement",
    "select_obligation_post_size_review",
    "record_reentry_exhausted",
    "run_wire",
    "count_repair_cycle_wire",
    "run_refine",
    "clear_scores",
    "rerun_confidence",
    "check_scores_present",
    "route_after_rescore",
    "count_repair_cycle_refine",
    "recheck_scores",
    "check_missing_artifacts",
    "run_size_review",
    "count_repair_cycle_size_review",
    "enqueue_or_skip",
    "check_parent_resolved_post_size_review",
    "check_reconcile_needed",
    "check_size_review_ran_this_pass",
    "check_guard2_verdict",
    "check_guard2_score_fallback",
    "check_readiness_for_atomic_remediation",
    "remediate_oversized_atomic",
    "mark_rescore_origin_atomic",
    "regate_after_atomic_remediation",
    "check_atomic_design_remedy",
    "check_go_no_go_eligible",
    "run_go_no_go",
    "check_go_no_go_waiver",
    "reopen_waived",
    "refine_for_design",
    "count_repair_cycle_refine_for_design",
    "reconcile_current",
    "count_repair_cycle_reconcile",
    "recheck_after_size_review",
    "check_pre_deferral_remedy",
    "dispatch_design_remedy",
    "dispatch_pre_deferral_remedy",
)
DELETED_STATES: tuple[str, ...] = (
    *MOVED_STATES,
    "size_review_snap",
    "check_broke_down",
    "mark_scores_absent_infra",
)

_EDGE_KEYS = (
    "next",
    "on_yes",
    "on_no",
    "on_error",
    "on_success",
    "on_failure",
    "on_cannot_judge",
    "on_rate_limit_exhausted",
    "on_partial",
    "on_blocked",
)


def state_targets(state: dict[str, Any]) -> list[str]:
    """Every static edge target of a parsed state (fragments excluded)."""
    out = [state[k] for k in _EDGE_KEYS if isinstance(state.get(k), str)]
    route = state.get("route")
    if isinstance(route, dict):
        out.extend(v for v in route.values() if isinstance(v, str))
    return out
