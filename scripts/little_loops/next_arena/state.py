"""Immutable project snapshot for the ``ll-next`` arena (FEAT-3561 phase B).

``collect_project_state`` reads every issue source **once** (all statuses, configured
category directories plus existing legacy directories), resolves identity, lifecycle and
priority from the captured bytes, captures the formatting policy and confidence thresholds,
and builds the dependency graph. Nothing here runs git, spawns a subprocess, touches the
history DB, writes files or allocates issue numbers: identity is derived **only** from
``parse_issue_filename``. Downstream generators, scorers and selectors take the resulting
:class:`ProjectState` and never read the clock, cwd, live files or environment themselves.

Identity rules (see the issue's "Snapshot and axis adapters"):

* A full ID is the anchored ``TYPE-NNN`` of the filename with the exact digit spelling.
* More than one source for a full ID, **or** for an anchored number string, makes every
  affected ID ``ambiguous_issue_id`` with all paths retained; ambiguity never depends on
  enumeration order.
* A source whose name is not anchored (or whose anchored type/number disagrees with what the
  shared parser would infer) keeps its content and lifecycle but is
  ``unsupported_issue_filename`` for actions. Numberless names own no ID, target or node.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from little_loops.frontmatter import parse_frontmatter
from little_loops.issue_parser import (
    FilenameId,
    IssueParser,
    parse_issue_filename,
    resolve_priority,
)
from little_loops.next_arena.graph import (
    DEFAULT_LEVERAGE_CAP,
    TERMINAL_STATUSES,
    IssueGraph,
    Leverage,
    LeverageIndex,
    OpCounter,
    Prerequisite,
    build_issue_graph,
    build_leverage_index,
    downstream_leverage,
)
from little_loops.next_arena.inputs import (
    Diagnostic,
    FormattingPolicy,
    Thresholds,
    capture_formatting_policy,
    capture_thresholds,
    is_formatted_from_state,
    sort_diagnostics,
)
from little_loops.session_log import command_counts_in_body, commands_in_body, session_log_body

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.next_arena.history import HistorySnapshot
    from little_loops.next_arena.loop_state import (
        LoopContextInputs,
        LoopDefinitionRecord,
        LoopDomain,
        LoopHistory,
        LoopSourceInventory,
    )
    from little_loops.next_arena.registry import ArenaSettings
    from little_loops.next_arena.scan_activity import ScanActivity
    from little_loops.next_arena.scan_state import ScanDomain, ScanScope
    from little_loops.next_arena.sprint_state import (
        SprintDefinition,
        SprintDomain,
        SprintStateEvidence,
    )

__all__ = [
    "DEFAULT_LEVERAGE_CAP",
    "TERMINAL_STATUSES",
    "AmbiguousId",
    "Diagnostic",
    "FormattingPolicy",
    "IdentityInventory",
    "IssueGraph",
    "Leverage",
    "LeverageIndex",
    "Lifecycle",
    "OpCounter",
    "Prerequisite",
    "ProjectState",
    "SourceRecord",
    "Thresholds",
    "UnsupportedSource",
    "ambiguous_targets",
    "ambiguous_diagnostic",
    "build_identity_inventory",
    "build_leverage_index",
    "build_project_state",
    "build_source_record",
    "collect_project_state",
    "downstream_leverage",
    "identity_diagnostics",
    "identity_issues_for",
    "infer_parser_id",
    "is_formatted_from_state",
    "resolve_lifecycle",
    "supported_source",
    "unique_source",
    "unsupported_diagnostic",
    "unsupported_sources",
]

#: Lifecycle statuses an explicit frontmatter ``status`` may carry.
LIFECYCLE_STATUSES: frozenset[str] = frozenset(
    {"open", "in_progress", "blocked", "deferred", "done", "cancelled"}
)

# Lifecycle provenance values.
PROV_FRONTMATTER = "frontmatter"
PROV_LEGACY_COMPLETED_AT = "legacy_completed_at"
PROV_DEFAULT = "default"
PROV_INVALID = "invalid"

# unsupported_issue_filename reasons.
UNSUPPORTED_NO_ANCHOR = "no_anchor"
UNSUPPORTED_INFERRED = "inferred_unanchored"
UNSUPPORTED_PARSER_DISAGREES = "parser_id_disagrees"
UNSUPPORTED_INFERRED_COLLISION = "inferred_id_collision"

_UNSUPPORTED_TEXT = {
    UNSUPPORTED_NO_ANCHOR: "filename has no P?-TYPE-NNN- anchor, so it owns no issue ID",
    UNSUPPORTED_INFERRED: "filename is not anchored; its inferred ID is evidence only (normalize it)",
    UNSUPPORTED_PARSER_DISAGREES: (
        "anchored type/number disagrees with the ID the shared parser would infer"
    ),
    UNSUPPORTED_INFERRED_COLLISION: (
        "filename is not anchored and its inferred ID collides with another source"
    ),
}

_PRIORITY_INT_RE = re.compile(r"^P(\d+)$")
_PRIORITY_PREFIX_DIGITS_RE = re.compile(r"^P\d+-(\d+)(?:[-.]|$)")


# ----------------------------------------------------------------------------- seams
# Module-level so tests can count calls (one read / one parse per file) or substitute them.


def _read_text(path: Path) -> str:
    """Read one source file (UTF-8). The single filesystem read of a source."""
    return path.read_text(encoding="utf-8")


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse the frontmatter of captured content. The single parse of a source."""
    return parse_frontmatter(content)


def _list_issue_files(directory: Path) -> list[Path]:
    """``*.md`` regular files directly under *directory*, path-sorted."""
    return sorted(p for p in directory.glob("*.md") if p.is_file())


# ------------------------------------------------------------------------ lifecycle


@dataclass(frozen=True)
class Lifecycle:
    """Lifecycle status resolved once from captured frontmatter."""

    status: str
    provenance: str
    raw: Any
    conflicting_completed_at: str | None


def resolve_lifecycle(frontmatter: Mapping[str, Any]) -> Lifecycle:
    """Resolve lifecycle status from captured frontmatter (never ``IssueInfo.status``).

    A present explicit status (after the parser's synonym canonicalization, which
    ``parse_frontmatter`` already applied) is authoritative over ``completed_at``: an
    explicit nonterminal status with a leftover marker stays nonterminal and carries the
    marker in ``conflicting_completed_at``. An absent/blank status with ``completed_at``
    resolves ``done`` (``legacy_completed_at``); absent without a marker is ``open``
    (``default``). An explicit status outside the lifecycle vocabulary is ``invalid`` and
    never falls back to completion.
    """
    raw = frontmatter.get("status")
    completed = frontmatter.get("completed_at")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if completed:
            return Lifecycle("done", PROV_LEGACY_COMPLETED_AT, raw, None)
        return Lifecycle("open", PROV_DEFAULT, raw, None)
    if isinstance(raw, str) and raw.strip() in LIFECYCLE_STATUSES:
        status = raw.strip()
        conflict = str(completed) if completed and status not in TERMINAL_STATUSES else None
        return Lifecycle(status, PROV_FRONTMATTER, raw, conflict)
    return Lifecycle("invalid", PROV_INVALID, raw, None)


# --------------------------------------------------------------------------- records


@dataclass(frozen=True)
class SourceRecord:
    """Everything captured from one issue file (read once, all statuses)."""

    path: Path
    rel_path: str
    category: str | None
    from_category_dir: bool
    in_legacy_dir: bool
    filename_id: FilenameId | None
    issue_id: str | None
    inferred_id: str | None
    filename_issue: str | None
    issue_type: str | None
    title: str
    content: str
    read_error: str | None
    frontmatter: Mapping[str, Any]
    lifecycle_status: str
    status_provenance: str
    status_raw: Any
    conflicting_completed_at: str | None
    blocked_by: tuple[str, ...]
    blocks: tuple[str, ...]
    depends_on: tuple[str, ...]
    confidence_score_raw: Any
    outcome_confidence_raw: Any
    outcome_gate_waived_raw: Any
    outcome_gate_waived: bool
    decision_needed_raw: Any
    decision_needed: bool
    priority: str | None
    priority_int: int | None
    priority_source: str | None
    priority_conflict: tuple[str, str] | None
    captured_at_raw: Any
    discovered_date_raw: Any
    session_log: str | None
    session_commands: tuple[str, ...]
    session_command_counts: Mapping[str, int]
    parent: Any
    diagnostics: tuple[Diagnostic, ...]

    @property
    def is_epic(self) -> bool:
        """True for EPIC containers (never an issue-action target)."""
        return self.issue_type == "EPIC"

    @property
    def is_terminal(self) -> bool:
        """True when the resolved lifecycle is ``done`` or ``cancelled``."""
        return self.lifecycle_status in TERMINAL_STATUSES


def infer_parser_id(filename: str, parent_dir_name: str, config: BRConfig) -> str | None:
    """The ID the shared parser would infer for *filename*, without allocation.

    Mirrors ``IssueParser._parse_type_and_id`` for numbered names (prefix search, then
    directory-category inference) and returns ``None`` where the parser would allocate a
    number or fall back to the filename stem -- those paths are deliberately bypassed.
    A parity test pins this against the real parser for numbered names.
    """
    categories = config.issues.categories
    for category in categories.values():
        match = re.search(rf"({re.escape(category.prefix)})-(\d+)", filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    for category in categories.values():
        if parent_dir_name != category.dir:
            continue
        priority_match = _PRIORITY_PREFIX_DIGITS_RE.match(filename)
        if priority_match:
            return f"{category.prefix}-{priority_match.group(1)}"
        numbers = re.findall(r"\d+", re.sub(r"^P\d+-", "", filename))
        return f"{category.prefix}-{numbers[0]}" if numbers else None
    return None


def _split_ids(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.strip("\"'").split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _merge_edge_ids(frontmatter_value: Any, body_ids: Sequence[str]) -> tuple[str, ...]:
    """Frontmatter wins over the body section (the parser's merge rule), deduplicated."""
    ids = _split_ids(frontmatter_value) or list(body_ids)
    return tuple(dict.fromkeys(ids))


def _flag_true(raw: Any) -> bool:
    """Boolean ``True`` or a case-insensitive ``"true"`` string; nothing else is truthy."""
    if isinstance(raw, bool):
        return raw
    return isinstance(raw, str) and raw.lower() == "true"


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def build_source_record(
    path: Path,
    content: str | None,
    *,
    project_root: Path,
    config: BRConfig,
    parser: IssueParser | None = None,
    read_error: str | None = None,
    category: str | None = None,
    in_legacy_dir: bool = False,
) -> SourceRecord:
    """Build a :class:`SourceRecord` from already-captured *content* (no file access).

    This is the single place a source is parsed; ``collect_project_state`` feeds it the one
    read, and in-memory fixtures (phase F) call it directly with synthetic content.
    ``content=None`` (or a *read_error*) marks the source unreadable: lifecycle ``invalid``.
    """
    text = content or ""
    unreadable = content is None or read_error is not None
    if unreadable and read_error is None:
        read_error = "unreadable source"
    rel_path = _rel_posix(path, project_root)
    diagnostics: list[Diagnostic] = []

    frontmatter: dict[str, Any] = {}
    if not unreadable:
        try:
            frontmatter = _parse_frontmatter(text)
        except Exception as exc:  # fail closed rather than guess a lifecycle
            read_error = f"frontmatter parse failed: {exc}"
            unreadable = True
    if unreadable:
        diagnostics.append(
            Diagnostic("unreadable_source", f"{rel_path}: {read_error}", (rel_path,), None)
        )

    # Identity: the anchored filename is the only authority.
    fid = parse_issue_filename(path.name)
    issue_id = f"{fid.type_prefix}-{fid.number}" if fid is not None else None
    parser_id = infer_parser_id(path.name, path.parent.name, config)
    if fid is not None:
        inferred_id = None
        filename_issue = None if parser_id == issue_id else UNSUPPORTED_PARSER_DISAGREES
    else:
        inferred_id = parser_id
        filename_issue = UNSUPPORTED_INFERRED if parser_id else UNSUPPORTED_NO_ANCHOR
    evidence_id = issue_id or inferred_id
    issue_type = evidence_id.split("-", 1)[0] if evidence_id else None

    # Lifecycle (resolved once; invalid when the source itself is unreadable).
    if unreadable:
        life = Lifecycle("invalid", PROV_INVALID, None, None)
    else:
        life = resolve_lifecycle(frontmatter)
        if life.provenance == PROV_INVALID:
            diagnostics.append(
                Diagnostic(
                    "invalid_status",
                    f"{rel_path}: status {life.raw!r} is not a lifecycle status",
                    (rel_path,),
                    evidence_id,
                )
            )
        if life.conflicting_completed_at is not None:
            diagnostics.append(
                Diagnostic(
                    "conflicting_completed_at",
                    f"{rel_path}: status {life.status!r} is authoritative over "
                    f"completed_at={life.conflicting_completed_at!r}",
                    (rel_path,),
                    evidence_id,
                )
            )

    # Priority: filename prefix wins, frontmatter fallback, no P5 default.
    priority = resolve_priority(path.name, frontmatter, config, default=None)
    priority_source: str | None = None
    priority_conflict: tuple[str, str] | None = None
    if priority is not None:
        if any(path.name.startswith(f"{p}-") for p in config.issue_priorities):
            priority_source = "filename"
            fm_raw = frontmatter.get("priority")
            fm_priority = fm_raw.upper() if isinstance(fm_raw, str) else None
            if fm_priority in config.issue_priorities and fm_priority != priority:
                priority_conflict = (priority, str(fm_priority))
                diagnostics.append(
                    Diagnostic(
                        "priority_disagreement",
                        f"{rel_path}: filename priority {priority} overrides "
                        f"frontmatter priority {fm_priority}",
                        (rel_path,),
                        evidence_id,
                    )
                )
        else:
            priority_source = "frontmatter"
    priority_match = _PRIORITY_INT_RE.match(priority) if priority else None
    priority_int = int(priority_match.group(1)) if priority_match else None

    # Edges and title reuse the parser's own section helpers.
    helper = parser or IssueParser(config)
    blocked_by = _merge_edge_ids(frontmatter.get("blocked_by"), helper._parse_blocked_by(text))
    blocks = _merge_edge_ids(frontmatter.get("blocks"), helper._parse_blocks(text))
    depends_on = _merge_edge_ids(frontmatter.get("depends_on"), ())
    title = str(frontmatter.get("title") or helper._parse_title_from_content(text, path))

    waived_raw = frontmatter.get("outcome_gate_waived")
    decision_raw = frontmatter.get("decision_needed")
    log_body = session_log_body(text)  # one fence scan; the command views derive from it

    return SourceRecord(
        path=path,
        rel_path=rel_path,
        category=category,
        from_category_dir=category is not None,
        in_legacy_dir=in_legacy_dir,
        filename_id=fid,
        issue_id=issue_id,
        inferred_id=inferred_id,
        filename_issue=filename_issue,
        issue_type=issue_type,
        title=title,
        content=text,
        read_error=read_error if unreadable else None,
        frontmatter=MappingProxyType(frontmatter),
        lifecycle_status=life.status,
        status_provenance=life.provenance,
        status_raw=life.raw,
        conflicting_completed_at=life.conflicting_completed_at,
        blocked_by=blocked_by,
        blocks=blocks,
        depends_on=depends_on,
        confidence_score_raw=frontmatter.get("confidence_score"),
        outcome_confidence_raw=frontmatter.get("outcome_confidence"),
        outcome_gate_waived_raw=waived_raw,
        outcome_gate_waived=_flag_true(waived_raw),
        decision_needed_raw=decision_raw,
        decision_needed=_flag_true(decision_raw),
        priority=priority,
        priority_int=priority_int,
        priority_source=priority_source,
        priority_conflict=priority_conflict,
        captured_at_raw=frontmatter.get("captured_at"),
        discovered_date_raw=frontmatter.get("discovered_date"),
        session_log=log_body,
        session_commands=tuple(commands_in_body(log_body)),
        session_command_counts=MappingProxyType(command_counts_in_body(log_body)),
        parent=frontmatter.get("parent"),
        diagnostics=tuple(diagnostics),
    )


# -------------------------------------------------------------------- identity inventory


@dataclass(frozen=True)
class AmbiguousId:
    """An ID with more than one affecting source (duplicate full ID and/or shared number)."""

    issue_id: str
    paths: tuple[str, ...]
    numbers: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class UnsupportedSource:
    """A source that cannot back an action (``unsupported_issue_filename``)."""

    rel_path: str
    reason: str
    issue_id: str | None


@dataclass(frozen=True)
class IdentityInventory:
    """All-status source inventory keyed by anchored full ID and anchored number string.

    ``node_ids`` maps ``rel_path -> graph node ID`` for sources that own a node (anchored
    names, plus uniquely inferred unanchored names kept as graph evidence); sources missing
    from it are anonymous. ``node_paths`` maps a node ID to all of its (sorted) sources.
    """

    by_id: Mapping[str, tuple[str, ...]]
    by_number: Mapping[str, tuple[str, ...]]
    ambiguous: Mapping[str, AmbiguousId]
    node_ids: Mapping[str, str]
    node_paths: Mapping[str, tuple[str, ...]]
    unsupported: Mapping[str, UnsupportedSource]
    diagnostics: tuple[Diagnostic, ...]


def ambiguous_diagnostic(amb: AmbiguousId) -> Diagnostic:
    """The ``ambiguous_issue_id`` diagnostic for *amb* (all conflicting paths retained)."""
    detail = ", ".join(amb.reasons)
    if amb.numbers:
        detail += f"; number {', '.join(amb.numbers)}"
    return Diagnostic(
        "ambiguous_issue_id",
        f"{amb.issue_id} is ambiguous ({detail}): " + ", ".join(amb.paths),
        amb.paths,
        amb.issue_id,
    )


def unsupported_diagnostic(src: UnsupportedSource) -> Diagnostic:
    """The ``unsupported_issue_filename`` diagnostic for *src*."""
    text = _UNSUPPORTED_TEXT.get(src.reason, src.reason)
    return Diagnostic(
        "unsupported_issue_filename",
        f"{src.rel_path}: {src.reason}: {text}",
        (src.rel_path,),
        src.issue_id,
    )


def build_identity_inventory(records: Iterable[SourceRecord]) -> IdentityInventory:
    """Build the identity inventory; the result is independent of *records* order."""
    ordered = sorted(records, key=lambda r: r.rel_path)

    by_id: dict[str, list[str]] = defaultdict(list)
    by_number: dict[str, list[str]] = defaultdict(list)
    number_ids: dict[str, set[str]] = defaultdict(set)
    for rec in ordered:
        if rec.issue_id is not None and rec.filename_id is not None:
            by_id[rec.issue_id].append(rec.rel_path)
            by_number[rec.filename_id.number].append(rec.rel_path)
            number_ids[rec.filename_id.number].add(rec.issue_id)

    ambiguous: dict[str, AmbiguousId] = {}
    for issue_id in sorted(by_id):
        reasons: set[str] = set()
        numbers: set[str] = set()
        paths: set[str] = set()
        if len(by_id[issue_id]) > 1:
            reasons.add("duplicate_full_id")
            paths.update(by_id[issue_id])
        number = issue_id.split("-", 1)[1]
        if len(by_number[number]) > 1:
            numbers.add(number)
            paths.update(by_number[number])
            if len(number_ids[number]) > 1:
                reasons.add("shared_number")
        if len(paths) > 1:
            ambiguous[issue_id] = AmbiguousId(
                issue_id, tuple(sorted(paths)), tuple(sorted(numbers)), tuple(sorted(reasons))
            )

    anchored_ids = set(by_id)
    inferred_groups: dict[str, list[str]] = defaultdict(list)
    for rec in ordered:
        if rec.issue_id is None and rec.inferred_id is not None:
            inferred_groups[rec.inferred_id].append(rec.rel_path)

    node_ids: dict[str, str] = {}
    unsupported: dict[str, UnsupportedSource] = {}
    for rec in ordered:
        if rec.issue_id is not None:
            node_ids[rec.rel_path] = rec.issue_id
            if rec.filename_issue is not None:
                unsupported[rec.rel_path] = UnsupportedSource(
                    rec.rel_path, rec.filename_issue, rec.issue_id
                )
        elif rec.inferred_id is not None:
            collides = rec.inferred_id in anchored_ids or len(inferred_groups[rec.inferred_id]) > 1
            if collides:
                reason = UNSUPPORTED_INFERRED_COLLISION
            else:
                reason = rec.filename_issue or UNSUPPORTED_INFERRED
                node_ids[rec.rel_path] = rec.inferred_id
            unsupported[rec.rel_path] = UnsupportedSource(rec.rel_path, reason, rec.inferred_id)
        else:
            unsupported[rec.rel_path] = UnsupportedSource(
                rec.rel_path, rec.filename_issue or UNSUPPORTED_NO_ANCHOR, None
            )

    node_paths: dict[str, list[str]] = defaultdict(list)
    for rel, node in node_ids.items():
        node_paths[node].append(rel)

    diagnostics = [ambiguous_diagnostic(a) for a in ambiguous.values()]
    diagnostics.extend(unsupported_diagnostic(u) for u in unsupported.values())

    return IdentityInventory(
        by_id=MappingProxyType({k: tuple(sorted(v)) for k, v in sorted(by_id.items())}),
        by_number=MappingProxyType({k: tuple(sorted(v)) for k, v in sorted(by_number.items())}),
        ambiguous=MappingProxyType(ambiguous),
        node_ids=MappingProxyType(dict(sorted(node_ids.items()))),
        node_paths=MappingProxyType({k: tuple(sorted(v)) for k, v in sorted(node_paths.items())}),
        unsupported=MappingProxyType(dict(sorted(unsupported.items()))),
        diagnostics=sort_diagnostics(diagnostics),
    )


# ------------------------------------------------------------------------- project state


@dataclass(frozen=True)
class ProjectState:
    """Immutable snapshot consumed by generators, scorers and selectors.

    ``records`` are path-sorted; ``identity`` is the all-status inventory; ``graph`` holds
    the dependency structure and fail-closed prerequisite evidence; ``thresholds`` and
    ``config_errors`` carry the validated confidence gate (a nonempty ``config_errors`` is a
    CLI configuration error, exit 2); ``diagnostics`` aggregates every deterministic finding.
    """

    project_root: Path
    as_of: datetime
    config: BRConfig = field(repr=False, compare=False)
    records: tuple[SourceRecord, ...]
    identity: IdentityInventory
    graph: IssueGraph
    formatting_policy: FormattingPolicy
    thresholds: Thresholds
    config_errors: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
    #: Loop domain (FEAT-3769). ``None`` means "not collected" (no loop verb in scope), which
    #: is distinct from an empty tuple ("collected, none found").
    loop_definitions: tuple[LoopDefinitionRecord, ...] | None = None
    loop_history: LoopHistory | None = None
    loop_inventory: LoopSourceInventory | None = None
    loop_inputs: LoopContextInputs | None = None
    loop_diagnostics: tuple[Diagnostic, ...] = ()
    #: Scan domain (FEAT-3713). ``None`` means "not collected" (no scan verb in scope); the
    #: activity is ``None`` too when the scope is unusable (no git is run then).
    scan_scope: ScanScope | None = None
    scan_activity: ScanActivity | None = None
    scan_diagnostics: tuple[Diagnostic, ...] = ()
    #: Sprint domain (FEAT-3713). ``None`` means "not collected"; ``sprint_history`` is filled by
    #: the CLI (``dataclasses.replace``) once sprint discovery supplies the candidate names.
    sprint_definitions: tuple[SprintDefinition, ...] | None = None
    sprint_state: SprintStateEvidence | None = None
    sprint_history: HistorySnapshot | None = None
    sprint_diagnostics: tuple[Diagnostic, ...] = ()
    _by_path: Mapping[str, SourceRecord] = field(repr=False, compare=False, default_factory=dict)

    def record_for_path(self, rel_path: str) -> SourceRecord | None:
        """The record at a project-root-relative POSIX path, if collected."""
        return self._by_path.get(rel_path)

    def sources_for(self, issue_id: str) -> tuple[SourceRecord, ...]:
        """Every source owning node *issue_id* (empty for unknown IDs)."""
        return tuple(self._by_path[p] for p in self.identity.node_paths.get(issue_id, ()))


def build_project_state(
    records: Iterable[SourceRecord],
    *,
    project_root: Path,
    as_of: datetime,
    config: BRConfig,
    formatting_policy: FormattingPolicy,
    thresholds: Thresholds,
    config_errors: Iterable[str] = (),
    counter: OpCounter | None = None,
    loop_domain: LoopDomain | None = None,
    scan_domain: ScanDomain | None = None,
    sprint_domain: SprintDomain | None = None,
) -> ProjectState:
    """Assemble a :class:`ProjectState` from captured records and evidence (pure).

    ``collect_project_state`` uses this after its single read pass; phase F builds
    in-memory 10k-issue states through it without creating files.
    """
    ordered = tuple(sorted(records, key=lambda r: r.rel_path))
    inventory = build_identity_inventory(ordered)
    graph = build_issue_graph(ordered, inventory.node_ids, inventory.ambiguous, counter=counter)
    diagnostics = sort_diagnostics(
        [d for rec in ordered for d in rec.diagnostics]
        + list(inventory.diagnostics)
        + list(graph.diagnostics)
    )
    return ProjectState(
        project_root=project_root,
        as_of=as_of,
        config=config,
        records=ordered,
        identity=inventory,
        graph=graph,
        formatting_policy=formatting_policy,
        thresholds=thresholds,
        config_errors=tuple(config_errors),
        diagnostics=diagnostics,
        loop_definitions=loop_domain.definitions if loop_domain is not None else None,
        loop_history=loop_domain.history if loop_domain is not None else None,
        loop_inventory=loop_domain.inventory if loop_domain is not None else None,
        loop_inputs=loop_domain.inputs if loop_domain is not None else None,
        loop_diagnostics=loop_domain.diagnostics if loop_domain is not None else (),
        scan_scope=scan_domain.scope if scan_domain is not None else None,
        scan_activity=scan_domain.activity if scan_domain is not None else None,
        scan_diagnostics=scan_domain.diagnostics if scan_domain is not None else (),
        sprint_definitions=sprint_domain.definitions if sprint_domain is not None else None,
        sprint_state=sprint_domain.state if sprint_domain is not None else None,
        sprint_diagnostics=sprint_domain.diagnostics if sprint_domain is not None else (),
        _by_path=MappingProxyType({r.rel_path: r for r in ordered}),
    )


def _normalize_as_of(as_of: datetime | None) -> datetime:
    if as_of is None:
        return datetime.now(UTC)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware (naive datetimes are rejected)")
    return as_of.astimezone(UTC)


def collect_project_state(
    project_root: Path,
    *,
    as_of: datetime | None = None,
    config: BRConfig | None = None,
    include_loops: bool = False,
    include_scan: bool = False,
    include_sprints: bool = False,
    settings: ArenaSettings | None = None,
) -> ProjectState:
    """Capture a :class:`ProjectState` for an already-resolved *project_root*.

    One read of each ``*.md`` file in every configured category directory plus existing
    ``config.legacy_issue_dirs()``, all statuses, in deterministic path order. ``as_of`` is
    captured once as timezone-aware UTC (naive input raises ``ValueError``). No git,
    subprocess, database, writes or number allocation.

    With *include_loops* the loop domain is collected as well (definitions, inventory,
    steering/config inputs, ``.history``); callers pass it only when a loop verb is in scope,
    so issue-only scopes perform zero loop source reads, validations or history reads.

    With *include_scan* the ``capture-issues`` scan domain is collected too (configured scope
    plus, when the scope is usable, at most two git subprocesses); callers pass it only when
    that verb is in scope, so every other mode performs zero git calls. *settings* supplies the
    activity threshold/lookback and defaults to the config's resolved arena settings.

    With *include_sprints* the sprint definitions (parsed read-only from the effective sprints
    directory, never creating it) and the executor state file are captured; the sprint history
    snapshot is attached separately by the CLI so this function never touches the history store.
    """
    as_of_utc = _normalize_as_of(as_of)
    root = project_root.resolve()
    if config is None:
        from little_loops.config import BRConfig

        config = BRConfig(root)

    directories: list[tuple[Path, str | None, bool]] = []
    seen_dirs: set[Path] = set()
    for cat_name in config.issue_categories:
        directory = config.get_issue_dir(cat_name)
        if directory.is_dir() and directory.resolve() not in seen_dirs:
            seen_dirs.add(directory.resolve())
            directories.append((directory, cat_name, False))
    for directory in config.legacy_issue_dirs():
        if directory.is_dir() and directory.resolve() not in seen_dirs:
            seen_dirs.add(directory.resolve())
            directories.append((directory, None, True))

    parser = IssueParser(config)
    records: list[SourceRecord] = []
    for directory, category, legacy in directories:
        for path in _list_issue_files(directory):
            content: str | None
            error: str | None = None
            try:
                content = _read_text(path)
            except Exception as exc:  # unreadable source: retained, lifecycle invalid
                content = None
                error = f"{type(exc).__name__}: {exc}"
            records.append(
                build_source_record(
                    path,
                    content,
                    project_root=root,
                    config=config,
                    parser=parser,
                    read_error=error,
                    category=category,
                    in_legacy_dir=legacy,
                )
            )

    thresholds, config_errors = capture_thresholds(config)
    loop_domain: LoopDomain | None = None
    if include_loops:
        from little_loops.next_arena.loop_state import collect_loop_domain

        loop_domain = collect_loop_domain(root, config=config, as_of=as_of_utc)
    scan_domain: ScanDomain | None = None
    if include_scan:
        from little_loops.next_arena.scan_state import collect_scan_domain

        scan_domain = collect_scan_domain(
            root,
            config=config,
            as_of=as_of_utc,
            settings=settings if settings is not None else config.next.resolve_arena_settings(),
        )
    sprint_domain: SprintDomain | None = None
    if include_sprints:
        from little_loops.next_arena.sprint_state import collect_sprint_domain

        sprint_domain = collect_sprint_domain(root, config=config)
    return build_project_state(
        records,
        project_root=root,
        as_of=as_of_utc,
        config=config,
        formatting_policy=capture_formatting_policy(root),
        thresholds=thresholds,
        config_errors=config_errors,
        loop_domain=loop_domain,
        scan_domain=scan_domain,
        sprint_domain=sprint_domain,
    )


# ------------------------------------------------------- reusable identity-check functions


def ambiguous_targets(state: ProjectState) -> Mapping[str, AmbiguousId]:
    """IDs that are ambiguous (duplicate full ID or shared anchored number), with all paths.

    The one reusable identity check: every issue action, root-blocker action and declared
    sprint member fails ``ambiguous_issue_id`` for IDs in this mapping.
    """
    return state.identity.ambiguous


def unsupported_sources(state: ProjectState) -> Mapping[str, UnsupportedSource]:
    """Sources (by ``rel_path``) that cannot back an action: ``unsupported_issue_filename``."""
    return state.identity.unsupported


def identity_diagnostics(state: ProjectState) -> tuple[Diagnostic, ...]:
    """Deterministic ``ambiguous_issue_id`` and ``unsupported_issue_filename`` diagnostics."""
    return state.identity.diagnostics


def identity_issues_for(state: ProjectState, issue_id: str) -> tuple[Diagnostic, ...]:
    """Identity diagnostics that disqualify *issue_id* as an action target (empty when clean)."""
    found: list[Diagnostic] = []
    amb = state.identity.ambiguous.get(issue_id)
    if amb is not None:
        found.append(ambiguous_diagnostic(amb))
    for rel in state.identity.node_paths.get(issue_id, ()):
        src = state.identity.unsupported.get(rel)
        if src is not None:
            found.append(unsupported_diagnostic(src))
    return sort_diagnostics(found)


def unique_source(state: ProjectState, issue_id: str) -> SourceRecord | None:
    """The single source of *issue_id*, or ``None`` when unknown or ambiguous."""
    if issue_id in state.identity.ambiguous:
        return None
    paths = state.identity.node_paths.get(issue_id, ())
    return state.record_for_path(paths[0]) if len(paths) == 1 else None


def supported_source(state: ProjectState, issue_id: str) -> SourceRecord | None:
    """The unique source of *issue_id* iff it may back an action (anchored, parser-agreeing)."""
    record = unique_source(state, issue_id)
    if record is None or record.rel_path in state.identity.unsupported:
        return None
    return record
