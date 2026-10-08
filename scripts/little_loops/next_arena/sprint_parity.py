"""Executor-parity checks for ``run-sprint`` offers (FEAT-3713).

The offered command is the plain ``ll-sprint run -- NAME``. The arena assesses members through the
core's normalized, captured issue sources; the executor re-reads them through
``IssueParser.parse_file`` and its own terminal-status filter. Where those two views *can*
disagree the arena must not recommend the sprint, and it must not "fix" the executor:

* **terminal removal** -- ``cli/sprint/run.py`` removes a member only when the raw frontmatter
  ``status`` is exactly ``done`` or ``cancelled`` (``fm.get("status", "open") in (...)``). The core
  also resolves a status padded with whitespace, or an absent status plus ``completed_at``, to
  terminal. Removing such a member from the assessment while the command still dispatches it is an
  ``executor_membership_mismatch``;
* **relationship shapes** -- the core normalizes ``blocked_by``/``depends_on``/``blocks`` with
  ``state._split_ids`` (strip, drop blanks, ignore mappings, stringify list entries) while the
  executor keeps the raw entries and merges them with the body sections. Shapes whose
  normalization could hide an ordering edge, an outside prerequisite or a cycle -- or crash the
  runtime graph -- are an ``executor_dependency_mismatch``. The check is purely syntactic over the
  captured frontmatter (and the parser's own body-section helpers); it deliberately does not
  simulate the executor's resolver or waves and may conservatively veto a redundant edge.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from little_loops.next_arena.graph import TERMINAL_STATUSES
from little_loops.next_arena.state import ProjectState, SourceRecord, unique_source

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueParser

__all__ = [
    "MembershipMismatch",
    "OutsideBlocksIndex",
    "ShapeFinding",
    "dependency_shape_findings",
    "membership_mismatch",
    "outside_blocks_index",
    "outside_blocks_findings",
]

#: The executor's exact terminal predicate (``cli/sprint/run.py``).
EXECUTOR_TERMINAL = ("done", "cancelled")
_KINDS = ("blocked_by", "depends_on", "blocks")
_BODY_KINDS = ("blocked_by", "blocks")  # kinds with a body-section fallback
_COLLECTIONS = (list, tuple, set, frozenset, Mapping)


def _shown(raw: Any, limit: int = 200) -> str:
    text = repr(raw)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ------------------------------------------------------------------- terminal removal


@dataclass(frozen=True)
class MembershipMismatch:
    """A member the arena would remove as terminal that the plain command would dispatch."""

    issue_id: str
    path: str
    raw_status: str
    lifecycle_status: str
    provenance: str

    def to_dict(self) -> dict[str, str]:
        """JSON-ready mapping including the canonical-status remedy."""
        return {
            "issue_id": self.issue_id,
            "path": self.path,
            "raw_status": self.raw_status,
            "lifecycle_status": self.lifecycle_status,
            "lifecycle_provenance": self.provenance,
            "remedy": (
                f"set `status: {self.lifecycle_status}` exactly (no surrounding whitespace, "
                f"explicit field) in {self.path}"
            ),
        }

    def message(self) -> str:
        return (
            f"{self.issue_id}: the core resolves status {self.lifecycle_status!r} "
            f"({self.provenance}) from raw {self.raw_status}, but `ll-sprint run` only skips an "
            f"exact `status: done|cancelled` and would still dispatch it; "
            f"set `status: {self.lifecycle_status}` exactly in {self.path}"
        )


def membership_mismatch(record: SourceRecord) -> MembershipMismatch | None:
    """``MembershipMismatch`` when *record* is arena-terminal but not executor-terminal.

    Mirrors the plain command's captured predicate exactly: the raw parsed frontmatter
    ``status`` with the default ``open``; no ``completed_at`` fallback, no whitespace stripping.
    """
    if record.lifecycle_status not in TERMINAL_STATUSES:
        return None
    if record.frontmatter.get("status", "open") in EXECUTOR_TERMINAL:
        return None
    raw = record.frontmatter.get("status", "<absent>")
    return MembershipMismatch(
        issue_id=record.issue_id or record.inferred_id or record.rel_path,
        path=record.rel_path,
        raw_status=_shown(raw) if "status" in record.frontmatter else "<absent>",
        lifecycle_status=record.lifecycle_status,
        provenance=record.status_provenance,
    )


# ------------------------------------------------------------------ relationship shapes


@dataclass(frozen=True)
class ShapeFinding:
    """One relationship shape on which the core and the executor can disagree."""

    source_id: str
    path: str
    kind: str
    problem: str
    target: str | None
    raw: str

    def to_dict(self) -> dict[str, str | None]:
        """JSON-ready mapping (the raw entry/list/mapping as text)."""
        return {
            "source": self.source_id,
            "path": self.path,
            "kind": self.kind,
            "problem": self.problem,
            "target": self.target,
            "raw": self.raw,
        }

    def message(self) -> str:
        what = {
            "padded_entry": "an entry with surrounding whitespace the executor does not strip",
            "blank_entries_hide_body_edge": (
                "only blank entries, which suppress a body-section edge in the executor"
            ),
            "mapping_value": "a mapping value (the core ignores it; the executor reads its keys)",
            "nested_entry": "a nested list/mapping entry (the executor's graph cannot hash it)",
            "scalar_value": "an unsupported scalar value",
            "outside_blocks_mapping": (
                "a mapping-valued `blocks` that the core ignores but whose keys name a member"
            ),
        }[self.problem]
        target = f" naming {self.target}" if self.target else ""
        return f"{self.source_id} `{self.kind}` has {what}{target}: {self.raw} ({self.path})"


def _core_ids(raw: Any) -> list[str]:
    """The core's normalization (``state._split_ids``) of a truthy list/str value."""
    if isinstance(raw, str):
        return [p.strip() for p in raw.strip("\"'").split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _body_ids(parser: IssueParser, record: SourceRecord, kind: str) -> list[str]:
    helper = parser._parse_blocked_by if kind == "blocked_by" else parser._parse_blocks
    return list(helper(record.content))


def dependency_shape_findings(
    record: SourceRecord,
    remaining_ids: Collection[str],
    parser: IssueParser,
) -> list[ShapeFinding]:
    """Findings for one **remaining** member's captured relationship values.

    Exact list IDs, an exact empty ``[]`` and valid scalar CSV/empty-string values are the
    shared valid behavior and produce nothing; empty mappings are falsy in both paths and keep
    the body fallback.
    """
    rid = record.issue_id or ""
    found: list[ShapeFinding] = []

    def add(kind: str, problem: str, raw: Any, target: str | None = None) -> None:
        found.append(ShapeFinding(rid, record.rel_path, kind, problem, target, _shown(raw)))

    for kind in _KINDS:
        raw = record.frontmatter.get(kind)
        if not raw:
            continue
        if isinstance(raw, Mapping):
            add(kind, "mapping_value", raw)
            continue
        if isinstance(raw, (list, tuple)):
            for entry in raw:
                if isinstance(entry, _COLLECTIONS):
                    add(kind, "nested_entry", entry)
                elif isinstance(entry, str):
                    stripped = entry.strip()
                    if entry != stripped and stripped in remaining_ids and stripped != rid:
                        add(kind, "padded_entry", entry, stripped)
        elif not isinstance(raw, str):
            add(kind, "scalar_value", raw)
            continue
        if kind in _BODY_KINDS and not _core_ids(raw):
            hidden = [b for b in _body_ids(parser, record, kind) if b in remaining_ids and b != rid]
            if hidden:
                add(kind, "blank_entries_hide_body_edge", raw, hidden[0])
    return found


# ------------------------------------------------------------- outside blocks mappings


@dataclass(frozen=True)
class OutsideBlocksIndex:
    """Nonempty mapping-valued ``blocks`` across the project, keyed by each exact string key."""

    by_target: Mapping[str, tuple[SourceRecord, ...]]


def outside_blocks_index(state: ProjectState) -> OutsideBlocksIndex:
    """Index every source's nonempty ``blocks`` mapping by its exact keys (built once)."""
    grouped: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in state.records:
        blocks = record.frontmatter.get("blocks")
        if isinstance(blocks, Mapping) and blocks:
            for key in blocks:
                if isinstance(key, str):
                    grouped[key].append(record)
    return OutsideBlocksIndex({k: tuple(v) for k, v in grouped.items()})


def outside_blocks_findings(
    state: ProjectState,
    index: OutsideBlocksIndex,
    remaining_ids: Collection[str],
) -> list[ShapeFinding]:
    """Findings for outside sources whose ``blocks`` mapping names a remaining member.

    A source proven satisfied under the core's rules (a unique, anchored, supported source whose
    lifecycle is terminal) does not veto; ambiguity wins over terminal satisfaction. Unrelated
    mappings and outside ``blocked_by``/``depends_on`` are never inspected.
    """
    found: list[ShapeFinding] = []
    for target in sorted(remaining_ids):
        for source in index.by_target.get(target, ()):
            source_id = source.issue_id
            if source_id in remaining_ids:
                continue  # a remaining member: its own mapping is already a finding
            unique = unique_source(state, source_id) if source_id else None
            supported = unique is not None and unique.rel_path not in state.identity.unsupported
            if unique is source and supported and source.lifecycle_status in TERMINAL_STATUSES:
                continue
            found.append(
                ShapeFinding(
                    source_id or source.rel_path,
                    source.rel_path,
                    "blocks",
                    "outside_blocks_mapping",
                    target,
                    _shown(source.frontmatter.get("blocks")),
                )
            )
    return found
