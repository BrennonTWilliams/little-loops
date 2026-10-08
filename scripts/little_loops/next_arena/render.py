"""Human, JSON and explain rendering plus the generated output schema for ``ll-next``.

Pure functions over already-assessed data (FEAT-3561 phase E). Nothing here reads the
clock, cwd, environment, files (other than the packaged schema asset), git or the history
DB. The JSON envelope is::

    {schema_version, project_root, as_of, selection_policy, recording,
     recommendations, explanation, diagnostics}

* ``recording`` is ``{status, reason}`` on every envelope (``recorded``/``disabled``/
  ``unavailable``); each recommendation carries a nullable ``rec_id``, present only after the
  whole shown batch committed. ``as_of`` is microsecond-precision UTC (FEAT-3711);
* recommendation mode: ``explanation`` is ``null`` and ``recommendations`` holds complete,
  runnable candidates (action identity is never null);
* explain mode: ``recommendations`` is ``[]`` and ``explanation`` is
  ``{assessment, alternates}`` -- the named verb's assessment plus the other registered
  verbs' assessments of the same target (nullable action identity); an absent target gives
  ``explanation = null`` plus a ``target_not_found`` diagnostic.

Axis objects keep canonical per-verb order (``sort_keys`` is never used for payloads) and
``allow_nan=False`` guarantees no NaN/Infinity ever reaches the output.

The checked-in ``output-schema.json`` and ``feedback-schema.json`` (the ``ll-next feedback
--json`` document) are generated from this module::

    python -m little_loops.next_arena.render --write-schema
"""

from __future__ import annotations

import importlib.resources
import json
import shlex
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.next_arena.actions import (
    ACTION_KEY_TABLE,
    ACTION_KEYS,
    FINGERPRINT_SCOPE_V1,
    SCAN_TARGET,
    render_action,
    spec_from_dict,
)
from little_loops.next_arena.candidates import (
    FAIL,
    MISSING,
    PASS,
    Candidate,
    CandidateAssessment,
)
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics
from little_loops.next_arena.registry import (
    ACTION_VARIANTS,
    DOMAIN_LOOP,
    DOMAIN_SCAN,
    DOMAIN_SPRINT,
    REGISTRY,
    SCHEMA_VERSION,
    registered_verbs,
)

if TYPE_CHECKING:
    from little_loops.next_arena.recording import FeedbackResult, FeedbackUnavailable

__all__ = [
    "DIAGNOSTIC_LIMIT_TEXT",
    "FEEDBACK_SCHEMA_ASSET",
    "FEEDBACK_SCHEMA_FILENAME",
    "FEEDBACK_SCHEMA_VERSION",
    "RECORDING_DISABLED_REASONS",
    "RECORDING_UNAVAILABLE_REASONS",
    "SCHEMA_ASSET",
    "SCHEMA_FILENAME",
    "build_envelope",
    "build_feedback_document",
    "build_feedback_schema",
    "feedback_schema_text",
    "load_feedback_schema",
    "render_accept_text",
    "render_feedback_text",
    "write_feedback_schema",
    "build_explanation",
    "build_output_schema",
    "bucket_diagnostics",
    "collect_diagnostics",
    "format_as_of",
    "format_instant",
    "load_output_schema",
    "output_schema_text",
    "render_explain_text",
    "render_json",
    "render_text",
    "scope_subject",
    "target_not_found",
    "write_output_schema",
]

SCHEMA_FILENAME = "output-schema.json"
SCHEMA_ASSET = ("next_arena", SCHEMA_FILENAME)
FEEDBACK_SCHEMA_FILENAME = "feedback-schema.json"
FEEDBACK_SCHEMA_ASSET = ("next_arena", FEEDBACK_SCHEMA_FILENAME)
#: Version of the ``ll-next feedback --json`` document (independent of the envelope's).
#: 2 (FEAT-3713): the closed ``offer.action_spec`` union grows the ``sprint`` and ``scan`` variants.
FEEDBACK_SCHEMA_VERSION = 2
#: Closed ``recording.reason`` vocabularies (FEAT-3711); status ``recorded`` carries no reason.
RECORDING_DISABLED_REASONS: tuple[str, ...] = (
    "no_record",
    "explain",
    "config_disabled",
    "env_kill_switch",
    "analytics_disabled",
    "command_not_captured",
    "nothing_to_record",
)
RECORDING_UNAVAILABLE_REASONS: tuple[str, ...] = (
    "remote_unsupported_v1",
    "schema_not_ready",
    "write_failed",
)
#: Maximum diagnostics listed in human output (JSON always carries all of them).
DIAGNOSTIC_LIMIT_TEXT = 12

_SCHEMA_ID = "https://little-loops.dev/schemas/ll-next-output.json"
_FEEDBACK_SCHEMA_ID = "https://little-loops.dev/schemas/ll-next-feedback.json"
_ISO_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_INSTANT_PATTERN = "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}Z$"


# ------------------------------------------------------------------------------ envelope


def format_as_of(as_of: datetime) -> str:
    """Render the captured clock as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, second precision)."""
    return as_of.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_instant(instant: datetime) -> str:
    """Render an instant as ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC, always microseconds).

    The recommendation-event storage and v3 envelope/feedback contract: fractional instants
    are retained and a whole second renders as an explicit ``.000000Z``. ``format_as_of`` keeps
    its second precision for its other callers.
    """
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json_default(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def render_json(envelope: Mapping[str, Any]) -> str:
    """Serialize *envelope* deterministically (insertion order kept, NaN/Infinity rejected)."""
    return json.dumps(
        envelope, indent=2, ensure_ascii=False, allow_nan=False, default=_json_default
    )


def build_explanation(
    named: CandidateAssessment | None, alternates: Sequence[CandidateAssessment]
) -> dict[str, Any] | None:
    """The ``explanation`` object, or ``None`` when the named target does not exist."""
    if named is None:
        return None
    return {
        "assessment": named.to_dict(),
        "alternates": [a.to_dict() for a in alternates],
    }


def build_envelope(
    *,
    project_root: Path | str,
    as_of: datetime,
    selection_policy: Mapping[str, Any],
    recording: Mapping[str, Any],
    recommendations: Sequence[Candidate] = (),
    rec_ids: Sequence[str | None] = (),
    explanation: Mapping[str, Any] | None = None,
    diagnostics: Iterable[Diagnostic] = (),
) -> dict[str, Any]:
    """Assemble the output envelope (key order is part of the contract).

    *recording* is the required ``{status, reason}`` object; *rec_ids* parallels
    *recommendations* (``None`` entries, or an empty sequence, mean no usable ID).
    """
    ids = list(rec_ids) + [None] * (len(recommendations) - len(rec_ids))
    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(project_root),
        "as_of": format_instant(as_of),
        "selection_policy": dict(selection_policy),
        "recording": {"status": recording["status"], "reason": recording["reason"]},
        "recommendations": [
            {"rec_id": rec_id, **c.to_dict()}
            for c, rec_id in zip(recommendations, ids, strict=False)
        ],
        "explanation": None if explanation is None else dict(explanation),
        "diagnostics": [d.to_dict() for d in sort_diagnostics(diagnostics)],
    }


# ---------------------------------------------------------------------------- diagnostics


def scope_subject(verb: str, target: str) -> str:
    """The diagnostic subject an ``--explain VERB TARGET`` scopes to (domain-aware).

    Issue diagnostics are subjected to the bare issue ID; loop diagnostics to ``loop:NAME``,
    sprint diagnostics to ``sprint:NAME`` and the single scan to ``scan:project``, so a loop,
    sprint and issue spelled alike never receive each other's diagnostics.
    """
    domain = REGISTRY[verb].domain
    if domain == DOMAIN_LOOP:
        return f"loop:{target}"
    if domain == DOMAIN_SPRINT:
        return f"sprint:{target}"
    if domain == DOMAIN_SCAN:
        return f"scan:{target}"
    return target


def target_not_found(target: str, verb: str) -> Diagnostic:
    """Diagnostic for ``--explain VERB TARGET`` naming a target absent from the inventory."""
    domain = REGISTRY[verb].domain
    if domain == DOMAIN_LOOP:
        return Diagnostic(
            "target_not_found",
            f"{target!r} is not a discovered loop definition; --explain matches the exact "
            f"command operand as printed (e.g. a name from `ll-loop list`) for {verb}",
            (),
            f"loop:{target}",
        )
    if domain == DOMAIN_SPRINT:
        return Diagnostic(
            "target_not_found",
            f"{target!r} is not a discovered sprint definition; --explain matches the exact "
            f"sprint name (the file stem of NAME.yaml in the configured sprints directory) "
            f"for {verb}",
            (),
            f"sprint:{target}",
        )
    if domain == DOMAIN_SCAN:
        return Diagnostic(
            "target_not_found",
            f"{target!r} is not the scan target; the {verb} candidate is the whole configured "
            f"scan scope, so use `--explain {verb} {SCAN_TARGET}`",
            (),
            f"scan:{target}",
        )
    return Diagnostic(
        "target_not_found",
        f"{target!r} is not a known issue ID; --explain matches the full issue ID exactly "
        f"as spelled (e.g. FEAT-0123) for {verb}",
        (),
        target,
    )


#: Per-domain first (source-validity) gate and the "nothing to assess" noun used in
#: ``empty_source`` diagnostics; the issue domain's defaults are ``lifecycle`` / leaf issue.
_FIRST_GATE = {DOMAIN_LOOP: "definition", DOMAIN_SPRINT: "definition", DOMAIN_SCAN: "scope"}
_EMPTY_SOURCE_NOUN = {
    DOMAIN_LOOP: "valid loop definition",
    DOMAIN_SPRINT: "valid sprint definition",
    DOMAIN_SCAN: "configured scan scope",
}
#: ``target_key`` namespaces whose per-definition validation noise stays out of a full pass.
_QUIET_TARGET_PREFIXES = ("loop:", "sprint:", "scan:")


def bucket_diagnostics(
    assessments: Sequence[CandidateAssessment], bucket_order: Sequence[str]
) -> list[Diagnostic]:
    """Explain why a requested bucket yielded no runnable candidate.

    Emits one diagnostic per empty requested bucket with a distinct code:

    * ``empty_source`` -- no actionable (open/blocked, non-EPIC) target exists for the verb;
    * ``gate_missing`` -- actionable targets have a required gate that lacked its input
      (e.g. an absent readiness or outcome score);
    * ``gate_failed`` -- actionable targets have a failed gate or veto.

    Both gate codes are emitted when a bucket has both kinds of rejection.
    """
    out: list[Diagnostic] = []
    for verb in bucket_order:
        items = [a for a in assessments if a.action_type == verb]
        if any(a.fully_resolved for a in items):
            continue
        domain = REGISTRY[verb].domain
        first_gate = _FIRST_GATE.get(domain, "lifecycle")
        actionable = [
            a for a in items if first_gate in a.gates and a.gates[first_gate].status == PASS
        ]
        if not actionable:
            what = _EMPTY_SOURCE_NOUN.get(domain, "open or blocked leaf issue")
            out.append(
                Diagnostic(
                    "empty_source",
                    f"{verb}: no {what} was found to assess "
                    f"({len(items)} inventory target(s), none actionable)",
                    (),
                    verb,
                )
            )
            continue
        for status, code in ((FAIL, "gate_failed"), (MISSING, "gate_missing")):
            reasons: Counter[str] = Counter()
            affected = 0
            for a in actionable:
                codes = [
                    g.code
                    for name, g in a.gates.items()
                    if name != first_gate and g.status == status
                ]
                if codes:
                    affected += 1
                    reasons.update(set(codes))
            if not affected:
                continue
            top = ", ".join(f"{name} x{count}" for name, count in sorted(reasons.items()))
            what = "a failed gate" if status == FAIL else "a missing gate input"
            out.append(
                Diagnostic(
                    code,
                    f"{verb}: {affected} of {len(actionable)} actionable target(s) have "
                    f"{what} ({top})",
                    (),
                    verb,
                )
            )
    return out


def collect_diagnostics(
    state_diagnostics: Iterable[Diagnostic],
    assessments: Sequence[CandidateAssessment],
    bucket_order: Sequence[str],
    *,
    extra: Iterable[Diagnostic] = (),
    scope_to: str | None = None,
) -> list[Diagnostic]:
    """Union of source diagnostics, assessment diagnostics (refine caps ...) and bucket notes.

    With *scope_to* (the explain subject: an issue ID, ``loop:NAME``, ``sprint:NAME`` or
    ``scan:project``) only diagnostics about that subject are kept.
    """
    found: list[Diagnostic] = list(state_diagnostics)
    for item in assessments:
        if scope_to is None and item.target_key.startswith(_QUIET_TARGET_PREFIXES):
            # A full pass does not list every definition's validation warnings (dozens across
            # the built-ins); they stay on the assessment and appear under --explain.
            found.extend(
                d
                for d in item.diagnostics
                if item.eligible and not d.code.endswith("_validation_warning")
            )
            continue
        found.extend(item.diagnostics)
    if scope_to is not None:
        found = [d for d in found if d.subject == scope_to]
    else:
        found.extend(bucket_diagnostics(assessments, bucket_order))
    found.extend(extra)
    return list(sort_diagnostics(found))


# ---------------------------------------------------------------------------- text output


def _root_hint(project_root: str) -> list[str]:
    return [
        f"Project root: {project_root}",
        "Run copied actions from the project root "
        f"(cd {shlex.quote(project_root)}); ll-next never runs them.",
    ]


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _axes_line(item: Candidate | CandidateAssessment) -> str:
    parts = []
    for name, axis in item.axes.items():
        if axis.score is None:
            continue
        parts.append(f"{name} {axis.score:.2f}")
    return ", ".join(parts) if parts else "no resolved axes"


def _diagnostic_lines(diagnostics: Sequence[Diagnostic]) -> list[str]:
    if not diagnostics:
        return []
    lines = ["", "Notes:"]
    for diag in diagnostics[:DIAGNOSTIC_LIMIT_TEXT]:
        lines.append(f"  - [{diag.code}] {diag.message}")
    extra = len(diagnostics) - DIAGNOSTIC_LIMIT_TEXT
    if extra > 0:
        lines.append(f"  - ... {extra} more (use --json for all)")
    return lines


def _blocker_note(blocker: Mapping[str, Any] | None) -> str:
    if not blocker:
        return ""
    reach = blocker["reachable"]
    unlocked = blocker["immediately_unlocked"]
    shown = reach.get("display") or reach.get("count")
    return (
        f" [blocker: {shown} reachable downstream, "
        f"{blocker['direct_dependents']['count']} direct, "
        f"{unlocked['count']} immediately unlocked]"
    )


def _alternate_text(alt: Any) -> str:
    if alt.eligible and alt.display_command:
        return f"{alt.action_type}: {alt.display_command}{_blocker_note(alt.blocker)}"
    return (
        f"{alt.action_type}: not eligible ({', '.join(alt.exclusion_reasons) or 'n/a'})"
        f"{_blocker_note(alt.blocker)}"
    )


def _recording_line(recording: Mapping[str, Any]) -> str | None:
    status, reason = recording["status"], recording["reason"]
    if status == "recorded":
        return "Recording: recorded (accept one with `ll-next accept REC_ID`)"
    if reason == "nothing_to_record":
        return None
    hint = (
        " - run `ll-session migrate` to prepare the history store"
        if reason == "schema_not_ready"
        else ""
    )
    return f"Recording: {status} ({reason}){hint}"


def render_text(
    *,
    project_root: Path | str,
    recommendations: Sequence[Candidate],
    bucket_order: Sequence[str],
    diagnostics: Sequence[Diagnostic] = (),
    recording: Mapping[str, Any] | None = None,
    rec_ids: Sequence[str | None] = (),
) -> str:
    """Human output for recommendation mode (also the empty/exit-1 rendering)."""
    root = str(project_root)
    lines: list[str] = []
    if recommendations:
        noun = "recommendation" if len(recommendations) == 1 else "recommendations"
        lines.append(f"ll-next: {len(recommendations)} {noun}")
    else:
        lines.append("ll-next: no eligible candidate across " + ", ".join(bucket_order) + ".")
    lines.extend(_root_hint(root))
    recording_line = _recording_line(recording) if recording is not None else None
    if recording_line is not None:
        lines.append(recording_line)
    ids = list(rec_ids) + [None] * (len(recommendations) - len(rec_ids))
    for position, (cand, rec_id) in enumerate(zip(recommendations, ids, strict=False), start=1):
        lines.append("")
        lines.append(f"{position}. [{cand.action_type}] {cand.target}")
        lines.append(f"   {cand.display_command}")
        if rec_id is not None:
            lines.append(f"   rec_id: {rec_id}")
        lines.append(f"   {cand.selection_reason}")
        lines.append(f"   axes: {_axes_line(cand)}")
        if cand.alternates:
            alt = "; ".join(_alternate_text(a) for a in cand.alternates)
            lines.append(f"   also: {alt}")
        evidence_line = _evidence_line(cand)
        if evidence_line:
            lines.append(f"   {evidence_line}")
        overlap = cand.evidence.get("selected_overlap")
        if overlap:
            names = "; ".join(f"{o['action_type']} {o['display_command']}" for o in overlap)
            lines.append(
                f"   overlaps (alternative choices, not a bundle to run together): {names}"
            )
    lines.extend(_diagnostic_lines(diagnostics))
    return "\n".join(lines)


def _raw_text(raw: Any, limit: int = 110) -> str:
    """Compact one-line rendering of an axis ``raw`` value for human output."""
    if isinstance(raw, Mapping):
        parts = [f"{k}={v}" for k, v in raw.items() if v is not None and not isinstance(v, list)]
        text = ", ".join(parts) or "{}"
    else:
        text = repr(raw)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _assessment_block(item: Mapping[str, Any], *, heading: str) -> list[str]:
    lines = [heading]
    lines.append(f"  target: {item['target']} ({item['target_key']})")
    if item["eligible"]:
        lines.append(f"  eligible: yes -> {item['display_command']}")
        lines.append(f"  action_key: {item['action_key']}  {item['action_fingerprint']}")
    else:
        lines.append("  eligible: no")
        lines.append(f"  excluded because: {', '.join(item['exclusion_reasons']) or 'n/a'}")
    if item["eligible"]:
        lines.append(f"  {item['selection_reason']}")
    rank = item["bucket_rank"]
    lines.append(
        f"  bucket rank: {rank if rank is not None else 'unranked'}; utility "
        f"{_fmt(item['utility'])}; coverage {item['coverage']}"
    )
    if item["gates"]:
        lines.append("  gates:")
        for name, gate in item["gates"].items():
            lines.append(f"    {name}: {gate['status']} - {gate['reason']}")
    lines.append("  axes:")
    for name, axis in item["axes"].items():
        if axis["score"] is None:
            lines.append(f"    {name}: missing ({axis['missing_reason']})")
        else:
            lines.append(
                f"    {name}: raw {_raw_text(axis['raw'])} -> score {axis['score']:.3f} "
                f"(weight {axis['configured_weight']:.2f}, effective "
                f"{axis['effective_weight']:.3f}; {axis['source']})"
            )
    leverage = item["evidence"].get("leverage")
    if leverage is not None:
        shown = leverage.get("display") or leverage.get("missing_reason") or "unknown"
        lines.append(f"  leverage evidence: downstream {shown} ({leverage.get('status')})")
    lines.extend(_blocker_lines(item["evidence"].get("blocker")))
    lines.extend(_loop_lines(item["evidence"].get("loop")))
    lines.extend(_sprint_lines(item["evidence"].get("sprint")))
    lines.extend(_scan_lines(item["evidence"].get("scan")))
    return lines


def _blocker_lines(blocker: Mapping[str, Any] | None) -> list[str]:
    if not blocker:
        return []
    reach = blocker["reachable"]
    direct = blocker["direct_dependents"]
    unlocked = blocker["immediately_unlocked"]
    multi = blocker["multi_blocked"]
    shown = reach.get("display") or reach.get("count")
    return [
        f"  blocker: {shown} reachable downstream; {direct['count']} direct dependent(s), "
        f"{unlocked['count']} immediately unlocked ({unlocked['implementable_count']} without "
        f"independent vetoes), {multi['count']} multi-blocked",
    ]


def _loop_lines(loop: Mapping[str, Any] | None) -> list[str]:
    if not loop:
        return []
    hist = loop["history"]
    lines = [
        f"  loop: {loop['kind']} {loop['definition_source'] or '(no source identity)'}; "
        f"{loop['digest_label']} {loop['definition_digest'] or 'n/a'}",
        f"  history: joined on {loop['history_join_key']!r} ({loop['history_attribution']}); "
        f"{hist['qualified_runs']} qualifying run(s), {hist['excluded_runs']} excluded"
        + ("" if hist["available"] else f"; UNAVAILABLE ({hist['unavailable_reason']})"),
    ]
    if loop["shadowed"]:
        lines.append(
            "  shadowed sources: "
            + ", ".join(str(s["source"] or s["path"]) for s in loop["shadowed"])
        )
    inputs = loop.get("inputs")
    if inputs and not inputs["ok"]:
        lines.append(
            "  inputs: unresolved (missing "
            f"{inputs['missing_keys'] or '-'}, empty {inputs['unresolved_inputs'] or '-'}, "
            f"unknown {inputs['unknown_inputs'] or '-'})"
        )
    return lines


_ABSENT_TARGET_NOUN = {
    DOMAIN_LOOP: "loop target",
    DOMAIN_SPRINT: "sprint target",
    DOMAIN_SCAN: "scan target",
}


def _history_summary(history: Mapping[str, Any]) -> str:
    """One compact clause describing sprint-history evidence (always disclosing its limits)."""
    labels = ", ".join(history.get("labels") or ())
    witness = history.get("witness")
    if witness is not None:
        scope = (
            "complete walk" if history.get("complete") else "bounded walk, latest run may be newer"
        )
        return (
            f"newest ended `run NAME` {witness['ended_at']} ({witness['witness_age_days']:.2f} "
            f"day(s) ago, outcome unknown; {scope}) [{labels}]"
        )
    reason = history.get("missing_reason") or "none"
    extra = ""
    if history.get("unfinished_invocations"):
        extra = f"; {history['unfinished_invocations']} unfinished"
    return f"no qualified invocation observed ({reason}{extra}) [{labels}]"


def _sprint_lines(sprint: Mapping[str, Any] | None) -> list[str]:
    if not sprint:
        return []
    lines = [
        f"  sprint: {sprint['definition_source'] or '(no project-relative source)'}; "
        f"{sprint['digest_label']} {sprint['definition_digest'] or 'n/a'}; "
        f"{len(sprint['declared_members'])} distinct declared member(s)"
    ]
    if sprint.get("remaining") or sprint.get("terminal_removed"):
        lines.append(
            f"  members: remaining {', '.join(sprint['remaining']) or '-'}; "
            f"done/cancelled (removed) {', '.join(sprint['terminal_removed']) or '-'}"
        )
    waves = sprint.get("waves") or []
    if waves:
        lines.append("  waves: " + " -> ".join(", ".join(w) for w in waves))
    problems = [m for m in sprint.get("members", ()) if m.get("problem")]
    for member in problems:
        lines.append(f"  member {member['issue_id']}: {member['problem']} - {member['detail']}")
    lines.append(f"  history: {_history_summary(sprint['history'])}")
    if sprint.get("normalized_repeats"):
        lines.append(f"  repeated members counted once: {', '.join(sprint['normalized_repeats'])}")
    lines.append(f"  note: {sprint['command_note']}")
    lines.append(f"  note: {sprint['unmodeled_preflights']}")
    return lines


def _scan_lines(scan: Mapping[str, Any] | None) -> list[str]:
    if not scan:
        return []
    dirs = ", ".join(scan["focus_dirs"]) or "-"
    excludes = ", ".join(scan["exclude_patterns"]) or "-"
    lines = [f"  scan scope: {dirs} (exclude {excludes}); {scan['freshness']}"]
    declared = [d for d in scan["configured_directories"] if d["status"] != "ok"]
    for entry in declared:
        lines.append(f"  directory {entry['configured']!r}: {entry['status']} - {entry['detail']}")
    activity = scan.get("activity")
    if activity is not None:
        if not activity["available"]:
            state = f"UNKNOWN ({activity['unavailable_reason']}: {activity['detail']})"
        elif activity["saturated"]:
            state = f"at least {activity['scoped_commit_count_lower_bound']} (threshold met; exact total unknown)"
        elif activity["complete"]:
            state = f"exactly {activity['scoped_commit_count']}"
        else:
            state = (
                f"at least {activity['scoped_commit_count_lower_bound']} observed, then "
                f"{activity['truncation_reason']} (partial, not a count)"
            )
        shallow = "; shallow clone" if activity.get("shallow") else ""
        lines.append(
            f"  activity: {state} scoped commit(s) in {activity['lookback_days']} day(s) to "
            f"{activity['window_end']} (threshold {activity['threshold']}); "
            f"{activity['records_visited']} record(s), {activity['git_calls']} git call(s){shallow}"
        )
    lines.append(f"  note: {scan['freshness_note']}")
    lines.append(f"  note: {scan['command_note']}")
    return lines


def _evidence_line(cand: Candidate) -> str | None:
    """A compact per-recommendation evidence line for sprint and scan offers."""
    sprint = cand.evidence.get("sprint")
    if sprint:
        ready = len(sprint.get("ready_now") or ())
        total = len(sprint.get("remaining") or ())
        return (
            f"sprint: {ready} of {total} remaining member(s) ready now; "
            f"last run: {_history_summary(sprint['history'])}"
        )
    scan = cand.evidence.get("scan")
    if scan:
        activity = scan.get("activity") or {}
        count = activity.get("scoped_commit_count_lower_bound") or activity.get(
            "scoped_commit_count"
        )
        shown = f">={count}" if activity.get("saturated") else str(count)
        return (
            f"scan scope: {', '.join(scan['focus_dirs'])}; {shown} scoped commit(s) in "
            f"{scan['activity_lookback_days']} day(s); {scan['freshness']}"
        )
    return None


def render_explain_text(
    *,
    project_root: Path | str,
    explanation: Mapping[str, Any] | None,
    verb: str,
    target: str,
    diagnostics: Sequence[Diagnostic] = (),
) -> str:
    """Human output for ``--explain VERB TARGET`` (an absent target when *explanation* is None)."""
    root = str(project_root)
    lines: list[str] = []
    if explanation is None:
        noun = _ABSENT_TARGET_NOUN.get(REGISTRY[verb].domain, "issue target")
        lines.append(f"ll-next: no {noun} {target!r} for {verb}.")
        lines.extend(_root_hint(root))
    else:
        lines.append(f"ll-next --explain {verb} {target}")
        lines.extend(_root_hint(root))
        lines.append("")
        lines.extend(_assessment_block(explanation["assessment"], heading=f"{verb}:"))
        for alt in explanation["alternates"]:
            lines.append("")
            lines.extend(_assessment_block(alt, heading=f"alternate {alt['action_type']}:"))
    lines.extend(_diagnostic_lines(diagnostics))
    return "\n".join(lines)


# --------------------------------------------------------------------------- JSON Schema


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _nullable(schema: Mapping[str, Any]) -> dict[str, Any]:
    return {"anyOf": [dict(schema), {"type": "null"}]}


def _axis_names() -> list[str]:
    seen: dict[str, None] = {}
    for spec in REGISTRY.values():
        for axis in spec.axes:
            seen.setdefault(axis)
    return list(seen)


def _slash_variant_schema() -> dict[str, Any]:
    commands = sorted({command for command, _ in ACTION_KEY_TABLE.values()})
    return {
        "type": "object",
        "required": ["variant", "command", "args", "working_directory"],
        "additionalProperties": False,
        "properties": {
            "variant": {"const": "slash"},
            "command": {"type": "string", "enum": commands},
            "args": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "working_directory": {"type": "string", "minLength": 1},
        },
    }


def _loop_variant_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "variant",
            "target",
            "definition_source",
            "definition_digest",
            "fingerprint_scope",
            "working_directory",
        ],
        "additionalProperties": False,
        "properties": {
            "variant": {"const": "loop"},
            "target": {"type": "string", "minLength": 1},
            "definition_source": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Project-relative YAML path or `builtin:<relative-YAML-path>` of the "
                    "resolved top-level source."
                ),
            },
            "definition_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "SHA-256 of the captured top-level definition bytes.",
            },
            "fingerprint_scope": {"const": FINGERPRINT_SCOPE_V1},
            "working_directory": {"type": "string", "minLength": 1},
        },
    }


def _sprint_variant_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "variant",
            "target",
            "definition_source",
            "definition_digest",
            "fingerprint_scope",
            "working_directory",
            "members",
        ],
        "additionalProperties": False,
        "properties": {
            "variant": {"const": "sprint"},
            "target": {
                "type": "string",
                "minLength": 1,
                "description": "Exact sprint name (the NAME.yaml file stem).",
            },
            "definition_source": {
                "type": "string",
                "minLength": 1,
                "description": "Normalized project-relative POSIX path of the sprint YAML.",
            },
            "definition_digest": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
                "description": "SHA-256 of the sprint definition bytes that were parsed.",
            },
            "fingerprint_scope": {"const": FINGERPRINT_SCOPE_V1},
            "working_directory": {"type": "string", "minLength": 1},
            "members": {
                "type": "array",
                "description": (
                    "Every distinct declared member in first-occurrence file order with its "
                    "lifecycle status as assessed (terminal members included). Offer snapshot; "
                    "not fingerprint material."
                ),
                "items": {
                    "type": "object",
                    "required": ["issue_id", "status"],
                    "additionalProperties": False,
                    "properties": {
                        "issue_id": {"type": "string", "minLength": 1},
                        "status": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


def _scan_variant_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["variant", "target", "focus_dirs", "exclude_patterns", "working_directory"],
        "additionalProperties": False,
        "properties": {
            "variant": {"const": "scan"},
            "target": {"const": SCAN_TARGET},
            "focus_dirs": {
                "type": "array",
                "description": "Normalized, deduplicated, sorted project-relative scan directories.",
                "items": {"type": "string", "minLength": 1},
            },
            "exclude_patterns": {
                "type": "array",
                "description": "Normalized, deduplicated, sorted scan exclusion patterns.",
                "items": {"type": "string", "minLength": 1},
            },
            "working_directory": {"type": "string", "minLength": 1},
        },
    }


#: Per-variant ``action_spec`` branch builders keyed by registered variant name.
_VARIANT_SCHEMAS = {
    "slash": _slash_variant_schema,
    "loop": _loop_variant_schema,
    "sprint": _sprint_variant_schema,
    "scan": _scan_variant_schema,
}

_RECOMMENDATION_ONLY = (
    "rec_id",
    "action_type",
    "action_key",
    "action_fingerprint",
    "action_spec",
    "target",
    "target_key",
    "display_command",
    "axes",
    "gates",
    "utility",
    "selection_score",
    "bucket_rank",
    "pressure",
    "selection_reason",
    "resolved_axes",
    "applicable_axes",
    "coverage",
    "alternates",
    "evidence",
    "diagnostics",
)

_ASSESSMENT_KEYS = (
    "target",
    "target_key",
    "action_type",
    "action_key",
    "action_fingerprint",
    "action_spec",
    "display_command",
    "eligible",
    "exclusion_reasons",
    "axes",
    "gates",
    "utility",
    "selection_score",
    "bucket_rank",
    "pressure",
    "selection_reason",
    "resolved_axes",
    "applicable_axes",
    "coverage",
    "alternates",
    "evidence",
    "diagnostics",
)


def _common_properties() -> dict[str, Any]:
    return {
        "action_type": {"type": "string", "enum": list(registered_verbs())},
        "target": {"type": "string", "minLength": 1},
        "target_key": {"type": "string", "pattern": "^[a-z]+:.+$"},
        "axes": {
            "type": "object",
            "propertyNames": {"enum": _axis_names()},
            "additionalProperties": _ref("axis"),
        },
        "gates": {"type": "object", "additionalProperties": _ref("gate")},
        "utility": _nullable({"type": "number", "minimum": 0, "maximum": 1}),
        "selection_score": _nullable({"type": "number", "minimum": 0, "maximum": 1}),
        "pressure": {"type": "null"},
        "selection_reason": {"type": "string"},
        "resolved_axes": {"type": "integer", "minimum": 0},
        "applicable_axes": {"type": "integer", "minimum": 0},
        "coverage": {"type": "string", "pattern": "^[0-9]+/[0-9]+$"},
        "alternates": {"type": "array", "items": _ref("alternate")},
        "evidence": {"type": "object"},
        "diagnostics": {"type": "array", "items": _ref("diagnostic")},
    }


def build_output_schema() -> dict[str, Any]:
    """Generate the ``ll-next --json`` output JSON Schema from the verb/action registries.

    Enums (verbs, action keys, commands, axes, variants) derive from the registry and the
    action-key table, never from a second list. ``recommendations[]`` items require complete
    action identity; the separate ``assessment`` definition used by ``--explain`` allows null
    action fields, ``bucket_rank`` and utility.
    """
    verbs = list(registered_verbs())
    action_keys = list(ACTION_KEYS)
    variants = list(ACTION_VARIANTS)
    action_spec_branches = [_VARIANT_SCHEMAS[v]() for v in variants]

    common = _common_properties()
    recommendation_props = dict(common)
    recommendation_props.update(
        {
            "rec_id": _nullable({"type": "string", "pattern": _UUID_PATTERN}),
            "action_key": {"type": "string", "enum": action_keys},
            "action_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
            "action_spec": _ref("action_spec"),
            "display_command": {"type": "string", "minLength": 1},
            "bucket_rank": {"type": "integer", "minimum": 1},
        }
    )
    assessment_props = dict(common)
    assessment_props.update(
        {
            "eligible": {"type": "boolean"},
            "exclusion_reasons": {"type": "array", "items": {"type": "string"}},
            "action_key": _nullable({"type": "string", "enum": action_keys}),
            "action_fingerprint": _nullable({"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}),
            "action_spec": _nullable(_ref("action_spec")),
            "display_command": _nullable({"type": "string", "minLength": 1}),
            "bucket_rank": _nullable({"type": "integer", "minimum": 1}),
        }
    )
    ordered_recommendation = {k: recommendation_props[k] for k in _RECOMMENDATION_ONLY}
    ordered_assessment = {k: assessment_props[k] for k in _ASSESSMENT_KEYS}

    return {
        "$schema": _ISO_DRAFT,
        "$id": _SCHEMA_ID,
        "title": "ll-next --json output",
        "description": (
            "Output envelope of `ll-next --json`. Generated by "
            "little_loops.next_arena.render.build_output_schema(); do not edit by hand."
        ),
        "type": "object",
        "required": [
            "schema_version",
            "project_root",
            "as_of",
            "selection_policy",
            "recording",
            "recommendations",
            "explanation",
            "diagnostics",
        ],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "project_root": {"type": "string", "minLength": 1},
            "as_of": {"type": "string", "pattern": _INSTANT_PATTERN},
            "selection_policy": _ref("selection_policy"),
            "recording": _ref("recording"),
            "recommendations": {"type": "array", "items": _ref("recommendation")},
            "explanation": _nullable(_ref("explanation")),
            "diagnostics": {"type": "array", "items": _ref("diagnostic")},
        },
        "$defs": {
            "recording": {
                "description": (
                    "Whether the offered rows were stored. `rec_id` values are present only "
                    "when status is `recorded`. Observational: removing it and the IDs leaves "
                    "identical recommendations."
                ),
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["status", "reason"],
                        "additionalProperties": False,
                        "properties": {"status": {"const": "recorded"}, "reason": {"type": "null"}},
                    },
                    {
                        "type": "object",
                        "required": ["status", "reason"],
                        "additionalProperties": False,
                        "properties": {
                            "status": {"const": "disabled"},
                            "reason": {"enum": list(RECORDING_DISABLED_REASONS)},
                        },
                    },
                    {
                        "type": "object",
                        "required": ["status", "reason"],
                        "additionalProperties": False,
                        "properties": {
                            "status": {"const": "unavailable"},
                            "reason": {"enum": list(RECORDING_UNAVAILABLE_REASONS)},
                        },
                    },
                ],
            },
            "selection_policy": {
                "type": "object",
                "required": [
                    "mode",
                    "top",
                    "bucket_order",
                    "caps",
                    "dedup",
                    "cross_verb_utility_comparison",
                    "pressure",
                ],
                "additionalProperties": False,
                "properties": {
                    "mode": {"enum": ["single_pass", "round_robin"]},
                    "top": _nullable({"type": "integer", "minimum": 1}),
                    "bucket_order": {"type": "array", "items": {"enum": verbs}},
                    "caps": {
                        "type": "object",
                        "propertyNames": {"enum": verbs},
                        "additionalProperties": {"type": "integer", "minimum": 1},
                    },
                    "dedup": {"type": "string"},
                    "cross_verb_utility_comparison": {"const": False},
                    "pressure": {"type": "null"},
                },
            },
            "action_spec": {"oneOf": action_spec_branches},
            "axis": {
                "type": "object",
                "required": [
                    "raw",
                    "curve",
                    "score",
                    "configured_weight",
                    "effective_weight",
                    "source",
                    "missing_reason",
                ],
                "additionalProperties": False,
                "properties": {
                    "raw": {},
                    "curve": {"type": "string"},
                    "score": _nullable({"type": "number", "minimum": 0, "maximum": 1}),
                    "configured_weight": _nullable({"type": "number", "minimum": 0}),
                    "effective_weight": _nullable({"type": "number", "minimum": 0}),
                    "source": _nullable({"type": "string"}),
                    "missing_reason": _nullable({"type": "string"}),
                },
            },
            "gate": {
                "type": "object",
                "required": ["status", "reason", "source"],
                "additionalProperties": False,
                "properties": {
                    "status": {"enum": [PASS, FAIL, MISSING]},
                    "reason": {"type": "string"},
                    "source": _nullable({"type": "string"}),
                },
            },
            "diagnostic": {
                "type": "object",
                "required": ["code", "message", "paths", "subject"],
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "message": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "subject": _nullable({"type": "string"}),
                },
            },
            "alternate": {
                "type": "object",
                "required": [
                    "action_type",
                    "eligible",
                    "action_key",
                    "action_fingerprint",
                    "display_command",
                    "bucket_rank",
                    "utility",
                    "exclusion_reasons",
                    "selection_reason",
                    "blocker",
                ],
                "additionalProperties": False,
                "properties": {
                    "action_type": {"enum": verbs},
                    "eligible": {"type": "boolean"},
                    "action_key": _nullable({"enum": action_keys}),
                    "action_fingerprint": _nullable({"type": "string"}),
                    "display_command": _nullable({"type": "string"}),
                    "bucket_rank": _nullable({"type": "integer", "minimum": 1}),
                    "utility": _nullable({"type": "number", "minimum": 0, "maximum": 1}),
                    "exclusion_reasons": {"type": "array", "items": {"type": "string"}},
                    "selection_reason": {"type": "string"},
                    "blocker": _nullable({"type": "object"}),
                },
            },
            "recommendation": {
                "type": "object",
                "description": "A runnable recommendation: complete, non-null action identity.",
                "required": list(ordered_recommendation),
                "additionalProperties": False,
                "properties": ordered_recommendation,
            },
            "assessment": {
                "type": "object",
                "description": (
                    "A target/verb assessment (--explain). Action identity, bucket_rank and "
                    "utility are null for an excluded or unranked target."
                ),
                "required": list(ordered_assessment),
                "additionalProperties": False,
                "properties": ordered_assessment,
            },
            "explanation": {
                "type": "object",
                "required": ["assessment", "alternates"],
                "additionalProperties": False,
                "properties": {
                    "assessment": _ref("assessment"),
                    "alternates": {"type": "array", "items": _ref("assessment")},
                },
            },
        },
    }


def output_schema_text() -> str:
    """The canonical serialized schema (exactly what the checked-in file contains)."""
    return json.dumps(build_output_schema(), indent=2, ensure_ascii=False) + "\n"


def load_output_schema() -> dict[str, Any]:
    """Load the packaged ``output-schema.json`` via ``importlib.resources``."""
    traversable = importlib.resources.files("little_loops")
    for part in SCHEMA_ASSET:
        traversable = traversable.joinpath(part)
    loaded = json.loads(traversable.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def write_output_schema(path: Path | None = None) -> Path:
    """(Re)generate the checked-in schema file; maintainer helper, never called by ``ll-next``."""
    target = path or Path(__file__).with_name(SCHEMA_FILENAME)
    target.write_text(output_schema_text(), encoding="utf-8")
    return target


# ------------------------------------------------------------------- feedback / accept


def _offer_document(offer: Any) -> dict[str, Any]:
    """The stored offer as the feedback document renders it (``display_command`` derived)."""
    stored = json.loads(offer.action_spec)
    spec = {"variant": stored["variant"], **{k: v for k, v in stored.items() if k != "variant"}}
    return {
        "rec_id": offer.rec_id,
        "as_of": offer.as_of,
        "shown_at": offer.ts,
        "invocation_id": offer.invocation_id,
        "rank": offer.rank,
        "action_type": offer.action_type,
        "action_key": offer.action_key,
        "action_fingerprint": offer.action_fingerprint,
        "target": offer.target,
        "target_key": offer.target_key,
        "display_command": render_action(spec_from_dict(stored)),
        "action_spec": spec,
        "requested_top": offer.requested_top,
        "requested_types": json.loads(offer.requested_types),
    }


def build_feedback_document(
    rec_id: str, result: FeedbackResult | FeedbackUnavailable
) -> dict[str, Any]:
    """The single ``ll-next feedback --json`` document for exits 0, 1 and 2 (key order is contract).

    ``state`` exists only for a found offer (``accepted`` | ``unknown``); an absent or
    foreign-project ID is ``found: false`` / ``state: null`` / ``rec_id_not_found``; a storage
    problem is ``availability: unavailable`` with its reason, never a state.
    """
    observed = result.read_observed_at
    provenance = None if result.provenance is None else dict(result.provenance)
    base: dict[str, Any] = {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "rec_id": rec_id,
    }
    from little_loops.next_arena.recording import FeedbackResult  # lazy: recording imports us

    if isinstance(result, FeedbackResult):
        base.update(
            {
                "found": result.found,
                "state": result.state,
                "availability": "available",
                "reason": result.reason,
                "offer": None if result.offer is None else _offer_document(result.offer),
                "accepted_at": result.accepted_at,
            }
        )
    else:
        base.update(
            {
                "found": False,
                "state": None,
                "availability": "unavailable",
                "reason": result.reason,
                "offer": None,
                "accepted_at": None,
            }
        )
    base["read_observed_at"] = None if observed is None else format_instant(observed)
    base["provenance"] = provenance
    return base


def _offer_line(offer: Mapping[str, Any]) -> str:
    return f"[{offer['action_type']}] {offer['target']}: {offer['display_command']}"


def render_accept_text(rec_id: str, offer: Any, accepted_at: str, *, already: bool) -> str:
    """The one human line ``ll-next accept`` prints (no ``--json`` in v1)."""
    verb = "already accepted" if already else "accepted"
    return (
        f"ll-next: {verb} {rec_id} - offered {_offer_line(_offer_document(offer))} "
        f"(offered as of {offer.as_of}; acknowledged {accepted_at})"
    )


def render_feedback_text(rec_id: str, result: FeedbackResult | FeedbackUnavailable) -> str:
    """Human ``ll-next feedback`` output: the offer, its state and the read provenance."""
    document = build_feedback_document(rec_id, result)
    lines = [f"ll-next feedback {rec_id}"]
    if document["availability"] == "unavailable":
        lines.append(f"unavailable: {document['reason']}")
        if document["reason"] == "schema_not_ready":
            lines.append("Run `ll-session migrate` to prepare the history store.")
        elif document["reason"] == "remote_unsupported_v1":
            lines.append("Recommendation events are local SQLite only in v1.")
    elif not document["found"]:
        lines.append("not found: no recommendation with this ID exists in this project.")
    else:
        offer = document["offer"]
        if document["state"] == "accepted":
            lines.append(f"state: accepted (explicitly acknowledged {document['accepted_at']})")
        else:
            lines.append("state: unknown (offer found, acceptance unknown)")
        lines.append(f"offered: {_offer_line(offer)}")
        lines.append(
            f"  rank {offer['rank']}, offered as of {offer['as_of']}; "
            "the historical offered action, not today's assessment"
        )
    provenance = document["provenance"]
    if provenance is not None:
        lines.append(f"store: {provenance['store']} ({provenance['source']})")
    if document["read_observed_at"] is not None:
        lines.append(f"read observed at {document['read_observed_at']}")
    return "\n".join(lines)


def _feedback_branch(
    *, found: bool, state: str | None, availability: str = "available"
) -> dict[str, Any]:
    """One mutually exclusive outcome shape of the feedback document (state/offer coupling)."""
    properties: dict[str, Any] = {
        "found": {"const": found},
        "state": {"const": state},
        "availability": {"const": availability},
        "offer": {"type": "object"} if found else {"type": "null"},
        "accepted_at": {"type": "string"} if state == "accepted" else {"type": "null"},
        "reason": {"type": "null"} if found else {"type": "string"},
    }
    return {"type": "object", "properties": properties}


def build_feedback_schema() -> dict[str, Any]:
    """Generate the ``ll-next feedback --json`` JSON Schema (offer reuses the action_spec union)."""
    variants = list(ACTION_VARIANTS)
    instant = {"type": "string", "pattern": _INSTANT_PATTERN}
    return {
        "$schema": _ISO_DRAFT,
        "$id": _FEEDBACK_SCHEMA_ID,
        "title": "ll-next feedback --json output",
        "description": (
            "Output document of `ll-next feedback REC_ID --json`. Generated by "
            "little_loops.next_arena.render.build_feedback_schema(); do not edit by hand. "
            "`state` is `accepted` or `unknown` (offer found, acceptance unknown) and exists "
            "only for a found offer; there is no `ignored` state."
        ),
        "type": "object",
        "required": [
            "schema_version",
            "rec_id",
            "found",
            "state",
            "availability",
            "reason",
            "offer",
            "accepted_at",
            "read_observed_at",
            "provenance",
        ],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": FEEDBACK_SCHEMA_VERSION},
            "rec_id": {"type": "string", "pattern": _UUID_PATTERN},
            "found": {"type": "boolean"},
            "state": {"enum": ["accepted", "unknown", None]},
            "availability": {"enum": ["available", "unavailable"]},
            "reason": _nullable({"type": "string", "pattern": "^[a-z0-9_]+$"}),
            "offer": _nullable(_ref("offer")),
            "accepted_at": _nullable(instant),
            "read_observed_at": _nullable(instant),
            "provenance": _nullable(_ref("provenance")),
        },
        "oneOf": [
            _feedback_branch(found=True, state="accepted"),
            _feedback_branch(found=True, state="unknown"),
            _feedback_branch(found=False, state=None, availability="available"),
            _feedback_branch(found=False, state=None, availability="unavailable"),
        ],
        "$defs": {
            "provenance": {
                "type": "object",
                "required": ["store", "source"],
                "additionalProperties": False,
                "properties": {
                    "store": {"type": "string", "minLength": 1},
                    "source": {
                        "enum": ["LL_HISTORY_DB", "history.db_path", "default", "history.backend"]
                    },
                },
            },
            "action_spec": {"oneOf": [_VARIANT_SCHEMAS[v]() for v in variants]},
            "offer": {
                "type": "object",
                "description": (
                    "The immutable stored offer: the historical action as it was recommended, "
                    "not a reassessment against today's gates, files or definitions."
                ),
                "required": [
                    "rec_id",
                    "as_of",
                    "shown_at",
                    "invocation_id",
                    "rank",
                    "action_type",
                    "action_key",
                    "action_fingerprint",
                    "target",
                    "target_key",
                    "display_command",
                    "action_spec",
                    "requested_top",
                    "requested_types",
                ],
                "additionalProperties": False,
                "properties": {
                    "rec_id": {"type": "string", "pattern": _UUID_PATTERN},
                    "as_of": instant,
                    "shown_at": instant,
                    "invocation_id": {"type": "string", "pattern": _UUID_PATTERN},
                    "rank": {"type": "integer", "minimum": 1},
                    "action_type": {"type": "string", "minLength": 1},
                    "action_key": {"type": "string", "minLength": 1},
                    "action_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "target": {"type": "string", "minLength": 1},
                    "target_key": {"type": "string", "minLength": 1},
                    "display_command": {"type": "string", "minLength": 1},
                    "action_spec": _ref("action_spec"),
                    "requested_top": _nullable({"type": "integer", "minimum": 1}),
                    "requested_types": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }


def feedback_schema_text() -> str:
    """The canonical serialized feedback schema (exactly what the checked-in file contains)."""
    return json.dumps(build_feedback_schema(), indent=2, ensure_ascii=False) + "\n"


def load_feedback_schema() -> dict[str, Any]:
    """Load the packaged ``feedback-schema.json`` via ``importlib.resources``."""
    traversable = importlib.resources.files("little_loops")
    for part in FEEDBACK_SCHEMA_ASSET:
        traversable = traversable.joinpath(part)
    loaded = json.loads(traversable.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def write_feedback_schema(path: Path | None = None) -> Path:
    """(Re)generate the checked-in feedback schema; maintainer helper."""
    target = path or Path(__file__).with_name(FEEDBACK_SCHEMA_FILENAME)
    target.write_text(feedback_schema_text(), encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m little_loops.next_arena.render --write-schema`` regenerates both assets."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write-schema"]:
        print(write_output_schema())
        print(write_feedback_schema())
        return 0
    if args == ["--print-schema"]:
        sys.stdout.write(output_schema_text())
        return 0
    if args == ["--print-feedback-schema"]:
        sys.stdout.write(feedback_schema_text())
        return 0
    print(
        "usage: python -m little_loops.next_arena.render "
        "(--write-schema | --print-schema | --print-feedback-schema)"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - maintainer helper
    raise SystemExit(main())
