"""ENH-3630: run the characterization scenarios against the policy wrapper.

``policy_transform`` applies ENH-3606's boundary-edge retargets to a parsed
``autodev.yaml``, deletes the verified 39-state move set plus
``size_review_snap`` / ``check_broke_down`` / ``mark_scores_absent_infra``, and adds
the ``prep-pass-<ID>`` write to ``dequeue_next``. ``run_policy`` runs a scenario
through :func:`tests.autodev_harness.run_autodev` with
``fixtures/loops/prepare-issue-policy.yaml`` as ``prepare-issue``.

Ported from the ``spike/preparation-policy-a51621302`` tag
(``preparation_policy_harness.py``); this module targets the fixture path (not
``BUILTIN_LOOPS_DIR``, ENH-3630 § Dispatch-loop fixture) and no longer needs the
``mark_rate_limited`` "wired for when BUG-3622 lands" caveat -- BUG-3622 is
fixed on main.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.autodev_harness import AutodevResult, Scenario, run_autodev

POLICY_YAML = Path(__file__).parent / "fixtures" / "loops" / "prepare-issue-policy.yaml"

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

_INFLIGHT_LINE = "printf '%s' \"$CURRENT\" > ${context.run_dir}/autodev-inflight\n"
_PASS_WRITE = (
    "# ENH-3630: per-issue pass id for the preparation fact log\n"
    "P=$(cat ${context.run_dir}/prep-pass-$CURRENT 2>/dev/null || echo 0)\n"
    "printf '%s' \"$((P + 1))\" > ${context.run_dir}/prep-pass-$CURRENT\n"
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


def policy_transform(data: dict[str, Any]) -> dict[str, Any]:
    """ENH-3606 boundary retargets + deletions + the dequeue_next pass-id write."""
    st = data["states"]
    for name in DELETED_STATES:
        del st[name]
    st["refine_current"]["on_success"] = "copy_broke_down"
    cp = st["check_passed"]
    cp["on_yes"] = "check_proof_defer_or_implement"
    cp["on_no"] = "skip_inflight"
    cp["on_cannot_judge"] = "skip_inflight"
    cp["on_error"] = "skip_inflight_infra"
    st["detect_children"]["on_no"] = "check_parent_resolved"
    st["detect_children"]["on_error"] = "check_parent_resolved"
    st["check_parent_resolved"]["on_no"] = "skip_inflight"
    st["check_parent_resolved"]["on_error"] = "skip_inflight_infra"
    data.pop("capture_reachability_ok", None)
    action = st["dequeue_next"]["action"]
    assert _INFLIGHT_LINE in action, "dequeue_next inflight write moved; update the transform"
    st["dequeue_next"]["action"] = action.replace(_INFLIGHT_LINE, _INFLIGHT_LINE + _PASS_WRITE)
    dangling = sorted({(n, t) for n, s in st.items() for t in state_targets(s) if t not in st})
    assert not dangling, f"autodev edges into removed states: {dangling}"
    return data


def run_policy(scenario: Scenario, tmp_path: Path, monkeypatch: Any) -> AutodevResult:
    return run_autodev(
        scenario,
        tmp_path,
        monkeypatch,
        prepare_issue_yaml=POLICY_YAML,
        autodev_transform=policy_transform,
    )
