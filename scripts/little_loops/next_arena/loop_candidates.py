"""Runnable-loop generator for ``ll-next`` (FEAT-3769).

``assess_run_loops`` assesses every discovered loop target against the captured
:class:`~little_loops.next_arena.state.ProjectState` loop domain: validity (runner-equivalent
validation done at collection), effective resolution from the printed project root,
zero-argument preflight, the per-verb cold-start scope, and history axes joined on the
persisted logical ``FSMLoop.name`` (never the displayed command target). It performs no
live I/O: definitions, inventory, steering/config inputs and ``.history`` are immutable
evidence collected once by :mod:`~little_loops.next_arena.loop_state`.

One ``(run-loop, loop:TARGET)`` assessment represents the *effective* resolution of a
target; competing sources with the same canonical target are reported as shadowed evidence
rather than as separate assessments.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from little_loops.next_arena.actions import (
    FINGERPRINT_SCOPE_V1,
    LOOP_ACTION_KEY,
    ActionSpecError,
    LoopActionSpec,
    action_fingerprint,
    render_loop,
)
from little_loops.next_arena.axes import (
    TERMINAL_RUN_STATUSES,
    AxisScore,
    aggregate_axes,
    axis_missing,
    compute_loop_axes,
    loop_minimum_evidence_met,
)
from little_loops.next_arena.candidates import (
    FAIL,
    PASS,
    CandidateAssessment,
    GateResult,
    _gate,
    loop_target_key,
)
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.next_arena.loop_state import (
    KIND_PROJECT,
    LoopDefinitionRecord,
    LoopRunRecord,
    ZeroArgContext,
    loop_subject,
    resolve_target,
    zero_argument_context,
)
from little_loops.next_arena.registry import ArenaSettings
from little_loops.next_arena.state import ProjectState

__all__ = ["VERB", "assess_run_loops"]

VERB = "run-loop"


@dataclass(frozen=True)
class _RunSummary:
    qualified: int
    excluded: int
    latest: datetime | None
    completed: int
    terminal: int


def _summarize(runs: list[LoopRunRecord]) -> _RunSummary:
    """Frequency/recency/success inputs from the qualified runs of one logical name."""
    qualified = [r for r in runs if r.qualified and r.started_at is not None]
    latest = max((r.started_at for r in qualified if r.started_at), default=None)
    terminal = [r for r in qualified if r.status in TERMINAL_RUN_STATUSES]
    return _RunSummary(
        qualified=len(qualified),
        excluded=len(runs) - len(qualified),
        latest=latest,
        completed=sum(1 for r in terminal if r.status == "completed"),
        terminal=len(terminal),
    )


def _unresolved_detail(ctx: ZeroArgContext) -> str:
    parts: list[str] = []
    if ctx.missing_keys:
        parts.append("missing context: " + ", ".join(ctx.missing_keys))
    if ctx.unresolved_inputs:
        parts.append("required inputs without a value: " + ", ".join(ctx.unresolved_inputs))
    if ctx.unknown_inputs:
        parts.append(
            "required inputs depending on unknown loaded values: " + ", ".join(ctx.unknown_inputs)
        )
    return "; ".join(parts) + " (zero-argument run supplies no input or context)"


def _missing_axes(reason: str) -> dict[str, AxisScore]:
    return {
        axis: axis_missing("", reason, source="filesystem_history")
        for axis in ("frequency", "recency", "success")
    }


def assess_run_loops(state: ProjectState, *, settings: ArenaSettings) -> list[CandidateAssessment]:
    """Assess each discovered loop target for ``run-loop`` (``target_key`` order).

    Returns ``[]`` when the loop domain was not collected (``loop_definitions is None``). The
    shared ``assess_candidates`` pass assigns within-verb ranks. Each assessment retains the
    effective source/digest, zero-argument context provenance, history join, gates and
    exclusions (unresolved inputs included).
    """
    definitions = state.loop_definitions
    inventory = state.loop_inventory
    inputs = state.loop_inputs
    history = state.loop_history
    if definitions is None or inventory is None or inputs is None or history is None:
        return []

    runs_by_name: dict[str, list[LoopRunRecord]] = defaultdict(list)
    for run in history.records:
        runs_by_name[run.logical_name].append(run)

    groups: dict[str, list[LoopDefinitionRecord]] = defaultdict(list)
    for record in definitions:
        groups[record.target].append(record)

    chosen: dict[str, tuple[LoopDefinitionRecord, bool, str, str]] = {}
    for target, records in groups.items():
        resolution = resolve_target(inventory, target)
        effective = next((r for r in records if r.path == resolution.path), None)
        primary = effective if effective is not None else records[0]
        chosen[target] = (primary, effective is not None, resolution.kind, str(resolution.path))

    by_logical: dict[str, list[str]] = defaultdict(list)
    for target, (primary, matches, _kind, _path) in chosen.items():
        if primary.valid and matches and primary.logical_name:
            by_logical[primary.logical_name].append(target)

    out: list[CandidateAssessment] = []
    for target in sorted(chosen, key=loop_target_key):
        primary, matches, res_kind, res_path = chosen[target]
        shadowed = [r for r in groups[target] if r is not primary]
        out.append(
            _assess_target(
                state,
                settings,
                primary,
                matches,
                res_kind,
                res_path,
                shadowed,
                runs_by_name,
                by_logical,
            )
        )
    return out


def _assess_target(
    state: ProjectState,
    settings: ArenaSettings,
    record: LoopDefinitionRecord,
    resolves_back: bool,
    res_kind: str,
    res_path: str,
    shadowed: list[LoopDefinitionRecord],
    runs_by_name: Mapping[str, list[LoopRunRecord]],
    by_logical: Mapping[str, list[str]],
) -> CandidateAssessment:
    assert state.loop_inputs is not None and state.loop_history is not None
    target = record.target
    gates: dict[str, GateResult] = {}
    reasons: list[str] = []
    diagnostics: list[Diagnostic] = list(record.diagnostics)
    history = state.loop_history

    if record.valid:
        gates["definition"] = _gate(PASS, "valid_definition", source="loop_definition")
    else:
        gates["definition"] = _gate(
            FAIL,
            record.exclusion or "invalid_definition",
            record.exclusion_detail or "",
            "loop_definition",
        )
    if resolves_back:
        gates["resolution"] = _gate(
            PASS, "resolves_to_source", f"{res_kind} source", "source_inventory"
        )
    else:
        gates["resolution"] = _gate(
            FAIL,
            "shadowed_source",
            f"{target!r} resolves from the project root to a {res_kind} source "
            f"({res_path}), not this definition",
            "source_inventory",
        )

    zero_arg: ZeroArgContext | None = None
    if record.valid:
        zero_arg = zero_argument_context(record, state.loop_inputs)
        gates["inputs"] = (
            _gate(PASS, "inputs_resolved", source="preflight")
            if zero_arg.ok
            else _gate(FAIL, "unresolved_input", _unresolved_detail(zero_arg), "preflight")
        )

    logical = record.logical_name if record.valid else None
    named_runs = list(runs_by_name.get(logical, ())) if logical else []
    summary = _summarize(named_runs)
    if record.valid:
        if summary.qualified > 0:
            gates["cold_start_scope"] = _gate(
                PASS, "has_qualifying_run", f"{summary.qualified} qualifying run(s)", "history"
            )
        elif record.kind == KIND_PROJECT and record.visibility == "public":
            gates["cold_start_scope"] = _gate(
                PASS,
                "local_public_fallback",
                "never-run project-local public definition",
                "loop_definition",
            )
        else:
            what = "draft" if record.is_draft else f"{record.kind} {record.visibility}"
            gates["cold_start_scope"] = _gate(
                FAIL,
                "cold_start_scope",
                f"{what} definition with no qualifying run; only never-run project-local "
                "public definitions are offered before a run exists",
                "loop_definition",
            )

    for gate in gates.values():
        if gate.status != PASS:
            reasons.append(gate.code)
    reasons_unique = tuple(dict.fromkeys(reasons))
    eligible = not reasons_unique and bool(record.valid and record.source and record.digest)

    spec: LoopActionSpec | None = None
    fingerprint: str | None = None
    display: str | None = None
    action_key: str | None = None
    if eligible and record.source and record.digest:
        try:
            spec = LoopActionSpec(
                target=target,
                definition_source=record.source,
                definition_digest=record.digest,
                fingerprint_scope=FINGERPRINT_SCOPE_V1,
                working_directory=str(state.project_root),
            )
            fingerprint = action_fingerprint(spec)
            display = render_loop(spec)
            action_key = LOOP_ACTION_KEY
        except ActionSpecError as exc:
            eligible = False
            reasons_unique = (*reasons_unique, "unrepresentable_action")
            diagnostics.append(
                Diagnostic("unrepresentable_action", f"{target}: {exc}", (), loop_subject(target))
            )

    if not record.valid:
        axes_in = _missing_axes("definition_invalid")
    else:
        axes_in = compute_loop_axes(
            run_count=summary.qualified,
            latest_start=summary.latest,
            completed=summary.completed,
            terminal=summary.terminal,
            as_of=state.as_of,
            history_available=history.available,
        )
    aggregate = aggregate_axes(VERB, settings.weights[VERB], axes_in)
    scoring: dict[str, Any] = {"mode": "unranked", "minimum_evidence": None}
    utility: float | None = None
    if eligible:
        enough = loop_minimum_evidence_met(aggregate.axes)
        scoring = {"mode": "scored" if enough else "cold_start", "minimum_evidence": enough}
        utility = aggregate.utility if enough else None

    sharing = sorted(t for t in by_logical.get(logical or "", ()) if t != target)
    evidence: dict[str, Any] = {
        "loop": {
            "target": target,
            "kind": record.kind,
            "definition_source": record.source,
            "definition_digest": record.digest,
            "fingerprint_scope": FINGERPRINT_SCOPE_V1,
            "definition_path": str(record.path),
            "digest_label": "top-level definition bytes",
            "logical_name": logical,
            "history_join_key": logical,
            "history_join": "persisted FSMLoop.name (not the command target)",
            "history_attribution": "shared_logical_name" if sharing else "logical_name_only",
            "shared_logical_name_targets": sharing,
            "visibility": record.visibility,
            "draft": (
                {"folder": record.draft_folder, "internal_name": record.draft_internal_name}
                if record.is_draft
                else None
            ),
            "resolution": {"kind": res_kind, "path": res_path, "matches_source": resolves_back},
            "shadowed": [
                {"source": r.source, "kind": r.kind, "path": str(r.path)} for r in shadowed
            ],
            "errors": list(record.errors),
            "inputs": zero_arg.to_dict() if zero_arg is not None else None,
            "history": {
                "available": history.available,
                "unavailable_reason": history.unavailable_reason,
                "qualified_runs": summary.qualified,
                "excluded_runs": summary.excluded,
                "latest_start": summary.latest.isoformat() if summary.latest else None,
                "terminal_runs": summary.terminal,
                "completed_runs": summary.completed,
            },
        },
        "scoring": scoring,
    }

    reason = (
        "eligible; awaiting rank"
        if eligible
        else "Excluded: " + (", ".join(reasons_unique) or "no applicable action")
    )
    return CandidateAssessment(
        target=target,
        target_key=loop_target_key(target),
        action_type=VERB,
        action_key=action_key if eligible else None,
        action_fingerprint=fingerprint if eligible else None,
        action_spec=spec if eligible else None,
        display_command=display if eligible else None,
        eligible=eligible,
        exclusion_reasons=reasons_unique if not eligible else (),
        axes=aggregate.axes,
        gates=MappingProxyType(gates),
        utility=utility,
        selection_score=utility,
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
