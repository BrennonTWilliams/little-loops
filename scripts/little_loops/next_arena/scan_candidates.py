"""Scoped-activity scan generator for ``ll-next`` (FEAT-3713).

``assess_capture_scope`` assesses the **single** configured-scope scan candidate for
``capture-issues`` against the captured :class:`~little_loops.next_arena.state.ProjectState`
scan domain. It is pure: the scope, the git-derived activity and the clock-free thresholds are
immutable evidence collected once by :mod:`~little_loops.next_arena.scan_state`.

The recommendation is **evidence-only**: it has no scored axes (``axes={}``, coverage ``0/0``,
``utility=None``) and is offered only when the ``scope`` gate (a usable, existing, symlink-free
directory set) and the ``activity`` gate (enough scoped commits in the lookback window) pass.
Every offer is labelled ``scan-freshness-unknown``: no existing telemetry proves a completed
scan of exactly this scope, so no scan age or freshness is invented.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from little_loops.next_arena.actions import (
    SCAN_ACTION_KEY,
    SCAN_TARGET,
    ActionSpecError,
    ScanActionSpec,
    action_fingerprint,
    render_scan,
)
from little_loops.next_arena.axes import aggregate_axes
from little_loops.next_arena.candidates import (
    FAIL,
    MISSING,
    PASS,
    CandidateAssessment,
    GateResult,
    _gate,
)
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.next_arena.registry import ArenaSettings
from little_loops.next_arena.scan_activity import (
    GIT_UNSUPPORTED,
    MIN_GIT_VERSION,
    TRUNCATED_BYTES,
    TRUNCATED_DEADLINE,
    TRUNCATED_RECORDS,
    ScanActivity,
)
from little_loops.next_arena.scan_state import SCAN_SUBJECT, ScanScope
from little_loops.next_arena.state import ProjectState

__all__ = ["FRESHNESS_LABEL", "VERB", "assess_capture_scope"]

VERB = "capture-issues"
#: Every v1 scan offer carries this label: scan freshness cannot be proven from telemetry.
FRESHNESS_LABEL = "scan-freshness-unknown"

_TRUNCATION_TEXT = {
    TRUNCATED_RECORDS: "the commit-record work cap was reached",
    TRUNCATED_BYTES: "the output byte budget was reached",
    TRUNCATED_DEADLINE: "the shared 2-second time budget expired",
}


def _scope_gate(scope: ScanScope) -> GateResult:
    failure = scope.failure
    if failure is None:
        dirs = ", ".join(scope.focus_dirs)
        return _gate(
            PASS,
            "scope_usable",
            f"eligible director{'y' if len(scope.focus_dirs) == 1 else 'ies'}: {dirs}",
            "scan_config",
        )
    code, detail = failure
    return _gate(FAIL, code, detail, "scan_config")


def _activity_gate(activity: ScanActivity) -> GateResult:
    window = f"{activity.lookback_days} day(s) to {activity.window_end}"
    if not activity.available:
        reason = activity.unavailable_reason or "git_failed"
        detail = activity.detail or "scoped activity could not be read"
        if reason == GIT_UNSUPPORTED:
            detail = (
                f"git rejected the global --no-lazy-fetch option; capture-issues needs Git >= "
                f"{MIN_GIT_VERSION} to read scoped activity without fetching ({detail})"
            )
        return _gate(MISSING, reason, detail, "git_log")
    if activity.saturated:
        return _gate(
            PASS,
            "activity_threshold_met",
            f">={activity.lower_bound} scoped commit(s) observed in {window} "
            f"(threshold {activity.threshold}; exact total unknown)",
            "git_log",
        )
    if activity.complete:
        count = activity.scoped_commit_count or 0
        if activity.shallow:
            return _gate(
                MISSING,
                "partial_shallow_history",
                f"{count} scoped commit(s) in the available history of a shallow clone "
                f"(threshold {activity.threshold}); the lookback window cannot be proven complete",
                "git_log",
            )
        return _gate(
            FAIL,
            "activity_below_threshold",
            f"{count} scoped commit(s) in {window} < threshold {activity.threshold}",
            "git_log",
        )
    why = _TRUNCATION_TEXT.get(activity.truncation_reason or "", "the traversal was truncated")
    return _gate(
        MISSING,
        "activity_partial",
        f"{activity.lower_bound or 0} scoped commit(s) observed below threshold "
        f"{activity.threshold}, but {why}; the count is a lower bound, not an exact value",
        "git_log",
    )


def _spec_for(state: ProjectState, scope: ScanScope) -> ScanActionSpec:
    return ScanActionSpec(
        target=SCAN_TARGET,
        focus_dirs=scope.focus_dirs,
        exclude_patterns=scope.exclude_patterns,
        working_directory=str(state.project_root),
    )


def assess_capture_scope(
    state: ProjectState, *, settings: ArenaSettings
) -> CandidateAssessment | None:
    """Assess the single configured-scope scan for ``capture-issues``.

    Returns ``None`` only when the scan domain was not collected (``scan_scope is None``);
    an existing but unusable or inactive scope is retained as an ineligible assessment with its
    failing/missing gates so ``--explain capture-issues project`` can say why.
    """
    scope = state.scan_scope
    if scope is None:
        return None
    activity = state.scan_activity
    gates: dict[str, GateResult] = {"scope": _scope_gate(scope)}
    if gates["scope"].status == PASS:
        gates["activity"] = (
            _activity_gate(activity)
            if activity is not None
            else _gate(MISSING, "activity_not_collected", "scoped activity was not loaded", None)
        )
    reasons = tuple(dict.fromkeys(g.code for g in gates.values() if g.status != PASS))
    eligible = not reasons and activity is not None

    diagnostics: list[Diagnostic] = [*scope.diagnostics, *state.scan_diagnostics]
    spec: ScanActionSpec | None = None
    fingerprint: str | None = None
    display: str | None = None
    if eligible:
        try:
            spec = _spec_for(state, scope)
            fingerprint = action_fingerprint(spec)
            display = render_scan(spec)
        except ActionSpecError as exc:
            eligible = False
            reasons = (*reasons, "unrepresentable_action")
            diagnostics.append(Diagnostic("unrepresentable_action", str(exc), (), SCAN_SUBJECT))

    aggregate = aggregate_axes(VERB, settings.weights[VERB], {})
    evidence: dict[str, Any] = {
        "scan": {
            "target": SCAN_TARGET,
            "scope_hash": scope.scope_hash,
            **{k: v for k, v in scope.to_dict().items() if k != "scope_hash"},
            "freshness": FRESHNESS_LABEL,
            "freshness_note": (
                "No telemetry proves a completed scan of exactly this scope, so scan age is "
                "unknown; a recurring suggestion means only that the activity gate still holds."
            ),
            "command_note": (
                "/ll:scan-codebase takes no scope argument: it resolves the scan configuration "
                "current when invoked, which may differ from the scope assessed here."
            ),
            "activity_threshold": settings.activity_threshold,
            "activity_lookback_days": settings.activity_lookback_days,
            "activity": activity.to_dict() if activity is not None else None,
        },
        "scoring": {"mode": "evidence_only", "minimum_evidence": None},
    }
    reason = (
        "eligible; awaiting rank"
        if eligible
        else "Excluded: " + (", ".join(reasons) or "no applicable action")
    )
    return CandidateAssessment(
        target=SCAN_TARGET,
        target_key=f"scan:{scope.scope_hash}",
        action_type=VERB,
        action_key=SCAN_ACTION_KEY if eligible else None,
        action_fingerprint=fingerprint if eligible else None,
        action_spec=spec if eligible else None,
        display_command=display if eligible else None,
        eligible=eligible,
        exclusion_reasons=reasons if not eligible else (),
        axes=aggregate.axes,
        gates=MappingProxyType(gates),
        utility=None,
        selection_score=None,
        bucket_rank=None,
        pressure=None,
        selection_reason=reason,
        resolved_axes=aggregate.resolved_axes,
        applicable_axes=aggregate.applicable_axes,
        alternates=(),
        evidence=MappingProxyType(evidence),
        diagnostics=sort_diagnostics(diagnostics),
        priority_int=None,
    )
