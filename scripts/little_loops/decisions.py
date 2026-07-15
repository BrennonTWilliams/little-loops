"""Decisions and rules log data layer.

Provides typed dataclasses and CRUD operations for managing architectural
decisions, team-enforced rules, and exceptions stored in `.ll/decisions.yaml`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config.core import BRConfig

import yaml

from little_loops.file_utils import atomic_write, atomic_write_json

_DEFAULT_LOG_PATH = Path(".ll") / "decisions.yaml"


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path.cwd() / _DEFAULT_LOG_PATH


def _fragments_dir(log_path: Path) -> Path:
    """Derive the append-only fragment directory from the flat-file *log_path*.

    ``.ll/decisions.yaml`` → ``.ll/decisions.d`` (sibling directory). Derived
    rather than hardcoded so a custom ``decisions.log_path`` still lands its
    fragments in a matching sibling dir (BUG-2644).
    """
    return log_path.with_suffix(".d")


def _load_fragments(frag_dir: Path) -> list[AnyEntry]:
    """Read every ``*.json`` fragment in *frag_dir*, skipping malformed ones.

    Mirrors ``cli/loop/_helpers.py::read_queue_entries()`` malformed-skip
    semantics: a bad fragment (unparseable JSON, missing ``id``, unknown
    ``type``, or unreadable) is silently skipped rather than propagating an
    uncaught error out of ``load_decisions()``. Entries are returned sorted by
    ``(timestamp, filename)`` for a stable, deterministic union order. Two
    fragments carrying the same ``id`` are both preserved (no dict-keyed
    overwrite) so a colliding id surfaces in the merged result (BUG-2642).
    """
    if not frag_dir.exists():
        return []
    parsed: list[tuple[str, str, AnyEntry]] = []
    for f in frag_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entry = _entry_from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError, OSError):
            continue
        parsed.append((data.get("timestamp", ""), f.name, entry))
    parsed.sort(key=lambda t: (t[0], t[1]))
    return [entry for _, _, entry in parsed]


@dataclass
class DecisionOutcome:
    """Recorded outcome for a decision entry."""

    result: str
    measured_at: str
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionOutcome:
        return cls(
            result=data["result"],
            measured_at=data["measured_at"],
            notes=data.get("notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"result": self.result, "measured_at": self.measured_at}
        if self.notes is not None:
            d["notes"] = self.notes
        return d


@dataclass
class RuleEntry:
    """An enforced rule in the decisions log."""

    id: str
    type: str = "rule"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule: str = ""
    enforcement: str = "advisory"
    supersedes: str | None = None
    issue: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleEntry:
        copy = dict(data)
        return cls(
            id=copy.pop("id"),
            type=copy.pop("type", "rule"),
            timestamp=copy.pop("timestamp", ""),
            category=copy.pop("category", ""),
            labels=copy.pop("labels", []),
            rationale=copy.pop("rationale", ""),
            rule=copy.pop("rule", ""),
            enforcement=copy.pop("enforcement", "advisory"),
            supersedes=copy.pop("supersedes", None),
            issue=copy.pop("issue", None),
            extra=copy,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "category": self.category,
            "labels": self.labels,
            "rationale": self.rationale,
            "rule": self.rule,
            "enforcement": self.enforcement,
        }
        if self.supersedes is not None:
            d["supersedes"] = self.supersedes
        if self.issue is not None:
            d["issue"] = self.issue
        return {**d, **self.extra}


@dataclass
class DecisionEntry:
    """A recorded architectural or process decision."""

    id: str
    type: str = "decision"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule: str = ""
    alternatives_rejected: str | None = None
    issue: str | None = None
    scope: str = "issue"
    outcome: DecisionOutcome | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionEntry:
        copy = dict(data)
        outcome_data = copy.pop("outcome", None)
        return cls(
            id=copy.pop("id"),
            type=copy.pop("type", "decision"),
            timestamp=copy.pop("timestamp", ""),
            category=copy.pop("category", ""),
            labels=copy.pop("labels", []),
            rationale=copy.pop("rationale", ""),
            rule=copy.pop("rule", ""),
            alternatives_rejected=copy.pop("alternatives_rejected", None),
            issue=copy.pop("issue", None),
            scope=copy.pop("scope", "issue"),
            outcome=DecisionOutcome.from_dict(outcome_data) if outcome_data else None,
            extra=copy,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "category": self.category,
            "labels": self.labels,
            "rationale": self.rationale,
            "rule": self.rule,
            "scope": self.scope,
        }
        if self.alternatives_rejected is not None:
            d["alternatives_rejected"] = self.alternatives_rejected
        if self.issue is not None:
            d["issue"] = self.issue
        if self.outcome is not None:
            d["outcome"] = self.outcome.to_dict()
        return {**d, **self.extra}


@dataclass
class ExceptionEntry:
    """A one-time exception to an existing rule."""

    id: str
    type: str = "exception"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    rule_ref: str = ""
    issue: str = ""
    alternatives_rejected: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExceptionEntry:
        copy = dict(data)
        return cls(
            id=copy.pop("id"),
            type=copy.pop("type", "exception"),
            timestamp=copy.pop("timestamp", ""),
            category=copy.pop("category", ""),
            labels=copy.pop("labels", []),
            rationale=copy.pop("rationale", ""),
            rule_ref=copy.pop("rule_ref", ""),
            issue=copy.pop("issue", ""),
            alternatives_rejected=copy.pop("alternatives_rejected", None),
            extra=copy,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "category": self.category,
            "labels": self.labels,
            "rationale": self.rationale,
            "rule_ref": self.rule_ref,
            "issue": self.issue,
        }
        if self.alternatives_rejected is not None:
            d["alternatives_rejected"] = self.alternatives_rejected
        return {**d, **self.extra}


@dataclass
class CouplingEntry:
    """A coupling rule linking changed files to required audit targets in wire-issue."""

    id: str
    type: str = "coupling"
    timestamp: str = ""
    category: str = ""
    labels: list[str] = field(default_factory=list)
    rationale: str = ""
    if_changed: str = ""
    then_check: list[str] = field(default_factory=list)
    tier: str = "soft"  # hard | soft | fyi
    archetype: str | None = None
    enforcement: str = "advisory"
    supersedes: str | None = None
    issue: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CouplingEntry:
        copy = dict(data)
        return cls(
            id=copy.pop("id"),
            type=copy.pop("type", "coupling"),
            timestamp=copy.pop("timestamp", ""),
            category=copy.pop("category", ""),
            labels=copy.pop("labels", []),
            rationale=copy.pop("rationale", ""),
            if_changed=copy.pop("if_changed", ""),
            then_check=copy.pop("then_check", []),
            tier=copy.pop("tier", "soft"),
            archetype=copy.pop("archetype", None),
            enforcement=copy.pop("enforcement", "advisory"),
            supersedes=copy.pop("supersedes", None),
            issue=copy.pop("issue", None),
            extra=copy,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp,
            "category": self.category,
            "labels": self.labels,
            "rationale": self.rationale,
            "if_changed": self.if_changed,
            "then_check": self.then_check,
            "tier": self.tier,
            "enforcement": self.enforcement,
        }
        if self.archetype is not None:
            d["archetype"] = self.archetype
        if self.supersedes is not None:
            d["supersedes"] = self.supersedes
        if self.issue is not None:
            d["issue"] = self.issue
        return {**d, **self.extra}


# Open dispatch registry — add new entry types here without modifying CRUD functions
AnyEntry = RuleEntry | DecisionEntry | ExceptionEntry | CouplingEntry

_ENTRY_REGISTRY: dict[str, Any] = {
    "rule": RuleEntry,
    "decision": DecisionEntry,
    "exception": ExceptionEntry,
    "coupling": CouplingEntry,
}


def _entry_from_dict(data: dict[str, Any]) -> AnyEntry:
    entry_type = data.get("type", "rule")
    cls = _ENTRY_REGISTRY.get(entry_type)
    if cls is None:
        raise ValueError(f"Unknown entry type: {entry_type!r}")
    return cls.from_dict(data)


def load_decisions(path: Path | None = None) -> list[AnyEntry]:
    """Load all decision log entries as one logical log (flat file ∪ fragments).

    Presents the legacy flat ``entries:`` list (or bare top-level list) *plus*
    every ``.ll/decisions.d/*.json`` fragment as a single merged list. The flat
    file is still parsed strictly (malformed YAML / missing ``id`` / unknown
    ``type`` raise, preserving ENH-2589 corruption gating); malformed *fragments*
    are skipped (BUG-2644). Returns an empty list when neither source exists.
    """
    resolved = _resolve_path(path)
    legacy: list[AnyEntry] = []
    if resolved.exists():
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        if data:
            entries = data if isinstance(data, list) else data.get("entries", [])
            legacy = [_entry_from_dict(e) for e in entries]
    return legacy + _load_fragments(_fragments_dir(resolved))


def save_decisions(entries: list[AnyEntry], path: Path | None = None) -> None:
    """Atomically persist entries to the flat YAML file and compact fragments.

    Rewrites the whole flat file (the pre-BUG-2644 behavior). Because ``entries``
    is normally the *union* view (flat ∪ fragments) obtained from
    ``load_decisions()``, any fragments are now folded into the flat file, so the
    fragment directory is cleared afterward to keep a subsequent load from
    double-counting. This makes ``save_decisions()`` the compaction point;
    ordinary appends go through ``add_entry()`` and never rewrite the flat file.
    """
    resolved = _resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(
        [e.to_dict() for e in entries],
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    atomic_write(resolved, content)
    frag_dir = _fragments_dir(resolved)
    if frag_dir.exists():
        for f in frag_dir.glob("*.json"):
            f.unlink(missing_ok=True)


def add_entry(entry: AnyEntry, path: Path | None = None) -> None:
    """Append a new entry as its own fragment file (append-only, no rewrite).

    Writes one ``.ll/decisions.d/<uuid>.json`` fragment rather than rewriting the
    whole flat file, so concurrent appends from divergent branches never touch
    the same file region and merge cleanly (BUG-2642 / BUG-2644).
    """
    resolved = _resolve_path(path)
    frag_dir = _fragments_dir(resolved)
    atomic_write_json(frag_dir / f"{uuid.uuid4()}.json", entry.to_dict())


def list_entries(
    path: Path | None = None,
    *,
    type: str | None = None,
    category: str | None = None,
    label: str | None = None,
) -> list[AnyEntry]:
    """Return entries, optionally filtered by type, category, or label."""
    entries = load_decisions(path)
    if type is not None:
        entries = [e for e in entries if e.type == type]
    if category is not None:
        entries = [e for e in entries if e.category == category]
    if label is not None:
        entries = [e for e in entries if label in e.labels]
    return entries


def resolve_active(entries: list[AnyEntry]) -> list[AnyEntry]:
    """Return entries excluding those superseded by a newer entry.

    An entry is inactive if another entry's `supersedes` field references its ID.
    """
    superseded_ids = {
        getattr(e, "supersedes", None) for e in entries if getattr(e, "supersedes", None)
    }
    return [e for e in entries if e.id not in superseded_ids]


def set_outcome(
    entry_id: str,
    result: str,
    measured_at: str,
    notes: str | None = None,
    path: Path | None = None,
    *,
    force: bool = False,
) -> None:
    """Set the outcome on a decision entry; refuses to overwrite without force=True."""
    entries = load_decisions(path)
    for entry in entries:
        if entry.id == entry_id:
            if not isinstance(entry, DecisionEntry):
                raise TypeError(f"Entry {entry_id!r} is not a DecisionEntry (got {entry.type!r})")
            if entry.outcome is not None and not force:
                raise ValueError(
                    f"Entry {entry_id!r} already has an outcome. Use force=True to overwrite."
                )
            entry.outcome = DecisionOutcome(result=result, measured_at=measured_at, notes=notes)
            save_decisions(entries, path)
            return
    raise KeyError(f"No entry with id {entry_id!r}")


def load_coupling_entries(
    path: Path | None = None,
    *,
    changed_globs: list[str] | None = None,
    archetype: str | None = None,
) -> list[CouplingEntry]:
    """Return coupling entries, optionally filtered by glob match against changed files and archetype.

    Returns an empty list when decisions.yaml is absent (graceful degradation).
    """
    from fnmatch import fnmatch

    entries = [e for e in load_decisions(path) if isinstance(e, CouplingEntry)]

    if archetype is not None:
        entries = [e for e in entries if e.archetype == archetype]

    if changed_globs is not None:
        entries = [e for e in entries if any(fnmatch(f, e.if_changed) for f in changed_globs)]

    return entries


def generate_from_completed(config: BRConfig) -> int:
    """Generate DecisionEntry records from completed issues and persist to the log.

    Prefers the SQLite history DB when present; falls back to filesystem scanning.
    Skips issues that already have an entry in the log. When
    ``config.decisions.auto_generate`` is non-empty, only issues whose type
    prefix appears in the list are processed (e.g. ``["FEAT", "ENH"]`` skips
    BUG entries). Returns the count added.
    """
    from little_loops.issue_history.parsing import (
        scan_completed_issues,
        scan_completed_issues_from_db,
    )

    project_root = Path(config.project_root)
    log_path = project_root / config.decisions.log_path
    db_path = project_root / ".ll" / "history.db"

    if db_path.exists():
        completed = scan_completed_issues_from_db(db_path)
    else:
        completed = scan_completed_issues(project_root / config.issues.base_dir)

    type_filter: set[str] = set(config.decisions.auto_generate)

    existing = load_decisions(log_path)
    existing_issue_ids = {e.issue for e in existing if isinstance(e, DecisionEntry) and e.issue}

    count = 0
    for issue in completed:
        if type_filter and issue.issue_type not in type_filter:
            continue
        if issue.issue_id in existing_issue_ids:
            continue
        ts = ""
        if issue.completed_at:
            ts = issue.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif issue.captured_at:
            ts = issue.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = DecisionEntry(
            id=f"DEC-{issue.issue_id}",
            timestamp=ts,
            category=issue.issue_type.lower(),
            labels=[issue.priority, issue.issue_type.lower()],
            rationale=f"Auto-generated from completed issue {issue.issue_id}",
            issue=issue.issue_id,
            scope="issue",
        )
        add_entry(entry, log_path)
        count += 1

    return count
