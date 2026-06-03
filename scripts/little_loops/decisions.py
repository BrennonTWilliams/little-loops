"""Decisions and rules log data layer.

Provides typed dataclasses and CRUD operations for managing architectural
decisions, team-enforced rules, and exceptions stored in `.ll/decisions.yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from little_loops.file_utils import atomic_write

_DEFAULT_LOG_PATH = Path(".ll") / "decisions.yaml"


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path.cwd() / _DEFAULT_LOG_PATH


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleEntry:
        return cls(
            id=data["id"],
            type=data.get("type", "rule"),
            timestamp=data.get("timestamp", ""),
            category=data.get("category", ""),
            labels=data.get("labels", []),
            rationale=data.get("rationale", ""),
            rule=data.get("rule", ""),
            enforcement=data.get("enforcement", "advisory"),
            supersedes=data.get("supersedes"),
            issue=data.get("issue"),
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
        return d


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionEntry:
        outcome_data = data.get("outcome")
        return cls(
            id=data["id"],
            type=data.get("type", "decision"),
            timestamp=data.get("timestamp", ""),
            category=data.get("category", ""),
            labels=data.get("labels", []),
            rationale=data.get("rationale", ""),
            rule=data.get("rule", ""),
            alternatives_rejected=data.get("alternatives_rejected"),
            issue=data.get("issue"),
            scope=data.get("scope", "issue"),
            outcome=DecisionOutcome.from_dict(outcome_data) if outcome_data else None,
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
        return d


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExceptionEntry:
        return cls(
            id=data["id"],
            type=data.get("type", "exception"),
            timestamp=data.get("timestamp", ""),
            category=data.get("category", ""),
            labels=data.get("labels", []),
            rationale=data.get("rationale", ""),
            rule_ref=data.get("rule_ref", ""),
            issue=data.get("issue", ""),
            alternatives_rejected=data.get("alternatives_rejected"),
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
        return d


# Open dispatch registry — add new entry types here without modifying CRUD functions
AnyEntry = RuleEntry | DecisionEntry | ExceptionEntry

_ENTRY_REGISTRY: dict[str, Any] = {
    "rule": RuleEntry,
    "decision": DecisionEntry,
    "exception": ExceptionEntry,
}


def _entry_from_dict(data: dict[str, Any]) -> AnyEntry:
    entry_type = data.get("type", "rule")
    cls = _ENTRY_REGISTRY.get(entry_type)
    if cls is None:
        raise ValueError(f"Unknown entry type: {entry_type!r}")
    return cls.from_dict(data)


def load_decisions(path: Path | None = None) -> list[AnyEntry]:
    """Load all decision log entries from YAML; returns empty list if file absent."""
    resolved = _resolve_path(path)
    if not resolved.exists():
        return []
    raw = resolved.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not data:
        return []
    entries = data if isinstance(data, list) else data.get("entries", [])
    return [_entry_from_dict(e) for e in entries]


def save_decisions(entries: list[AnyEntry], path: Path | None = None) -> None:
    """Atomically persist decision log entries to YAML."""
    resolved = _resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(
        [e.to_dict() for e in entries],
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    atomic_write(resolved, content)


def add_entry(entry: AnyEntry, path: Path | None = None) -> None:
    """Append a new entry to the decisions log."""
    entries = load_decisions(path)
    entries.append(entry)
    save_decisions(entries, path)


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
        getattr(e, "supersedes", None)
        for e in entries
        if getattr(e, "supersedes", None)
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
