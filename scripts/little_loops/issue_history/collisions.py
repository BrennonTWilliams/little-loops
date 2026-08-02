"""Read-only audit of ``(issue_num, transition)`` dedup collisions (BUG-3006).

``idx_issue_events_dedup`` / ``idx_issue_snapshots_dedup`` are unique on the
type-blind ``(issue_num, transition)`` pair (ENH-2771), so an ``issue_num``
held by more than one ``issue_id`` is either a legitimate retype (one issue,
re-typed mid-life — e.g. ENH-1234 -> FEAT-1234) or a genuine number-reuse
collision (two unrelated issues that happen to share a bare number). Both
shapes leave exactly one on-disk file surviving under the shared number, so
"is there an on-disk file" alone can't tell them apart — the confirmed
BUG-1978/EPIC-1978 collision and the confirmed 2576/2689/2705 retypes both
have exactly one on-disk survivor.

The signal that *does* distinguish them: whether that survivor's on-disk
``status`` frontmatter is present among its *own* recorded transitions in
this table. A retype's surviving id was written under its current type the
whole time its current status was recorded, so the two agree. A number-reuse
victim's most recent transition (e.g. `EPIC-1978`'s `done`) was silently
discarded by the dedup index — its on-disk status was never recorded under
its own id, so the two disagree. Performs no writes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.history_reader import _connect_readonly

_AUDITED_TABLES = ("issue_events", "issue_snapshots")


@dataclass
class CollisionEntry:
    """One issue id's share of a colliding ``issue_num``."""

    issue_id: str
    transitions: list[str] = field(default_factory=list)
    on_disk: bool = False
    on_disk_status: str | None = None


@dataclass
class CollisionGroup:
    """All ids sharing one ``issue_num`` in one table, plus a classification."""

    table: str
    issue_num: int
    entries: list[CollisionEntry] = field(default_factory=list)

    @property
    def classification(self) -> str:
        """``"retype"`` when the lone on-disk survivor's status matches one of
        its own recorded transitions; ``"number_reuse"`` otherwise (including
        when zero or more than one entry is on-disk — an ambiguous shape that
        never occurs in a clean retype)."""
        on_disk_entries = [e for e in self.entries if e.on_disk]
        if len(on_disk_entries) != 1:
            return "number_reuse"
        survivor = on_disk_entries[0]
        if survivor.on_disk_status is not None and survivor.on_disk_status in survivor.transitions:
            return "retype"
        return "number_reuse"


def _scan_on_disk_statuses(issues_dir: Path) -> dict[str, str]:
    """Map each on-disk issue's exact canonical ``id`` to its current ``status``.

    Deliberately does **not** reuse ``ll-issues path``'s ``_resolve_issue_id()``:
    that resolver treats the type prefix as advisory and falls back to a
    numeric-only match (BUG-2003 tolerance for stale prefixes), so it would
    report both colliding ids as "on disk" whenever either one shares the
    file's number — exactly the ambiguity this audit exists to resolve. This
    scan instead requires each id to match a file's own canonicalized
    frontmatter/filename id exactly.
    """
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.session_store.writers import canonicalize_issue_id

    statuses: dict[str, str] = {}
    if not issues_dir.is_dir():
        return statuses
    for issue_file in issues_dir.rglob("*.md"):
        try:
            content = issue_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(content)
        issue_id = canonicalize_issue_id(fm.get("id"), issue_file)
        if issue_id:
            statuses[str(issue_id).upper()] = str(fm.get("status", "open"))
    return statuses


def audit_issue_collisions(
    db: Path | str,
    issues_dir: Path | str,
) -> list[CollisionGroup]:
    """Return every ``issue_num`` held by more than one ``issue_id``, classified.

    Groups ``issue_events`` and ``issue_snapshots`` independently by
    ``issue_num`` where ``COUNT(DISTINCT issue_id) > 1``. For each id in a
    group, checks whether an on-disk file under *issues_dir* carries that
    *exact* canonicalized id and, if so, its current frontmatter ``status``
    (see ``_scan_on_disk_statuses``), then classifies the group per
    ``CollisionGroup.classification``. Read-only: opens the db connection
    read-only and performs no writes.
    """
    conn = _connect_readonly(Path(db))
    if conn is None:
        return []

    on_disk_statuses = _scan_on_disk_statuses(Path(issues_dir))
    groups: list[CollisionGroup] = []
    try:
        for table in _AUDITED_TABLES:
            rows = conn.execute(
                f"SELECT issue_num, issue_id, transition FROM {table} "  # noqa: S608
                "WHERE issue_num IN ("
                f"  SELECT issue_num FROM {table}"  # noqa: S608
                "   WHERE issue_num IS NOT NULL"
                "   GROUP BY issue_num"
                "   HAVING COUNT(DISTINCT issue_id) > 1"
                ") ORDER BY issue_num, issue_id, transition"
            ).fetchall()

            by_num: dict[int, dict[str, CollisionEntry]] = {}
            for issue_num, issue_id, transition in rows:
                entries = by_num.setdefault(int(issue_num), {})
                entry = entries.setdefault(issue_id, CollisionEntry(issue_id=issue_id))
                if transition not in entry.transitions:
                    entry.transitions.append(transition)

            for issue_num, entries_by_id in sorted(by_num.items()):
                for issue_id, entry in entries_by_id.items():
                    status = on_disk_statuses.get(issue_id.upper())
                    entry.on_disk = status is not None
                    entry.on_disk_status = status
                groups.append(
                    CollisionGroup(
                        table=table,
                        issue_num=issue_num,
                        entries=list(entries_by_id.values()),
                    )
                )
    except sqlite3.Error:
        return groups
    finally:
        conn.close()

    return groups


def format_collision_audit_text(groups: list[CollisionGroup]) -> str:
    """Render collision groups as a human-readable text report."""
    if not groups:
        return "No (issue_num, transition) dedup collisions found."

    lines: list[str] = []
    for group in groups:
        lines.append(f"{group.table}: issue_num={group.issue_num} [{group.classification}]")
        for entry in group.entries:
            disk = f"on-disk, status={entry.on_disk_status}" if entry.on_disk else "not on-disk"
            transitions = ", ".join(entry.transitions)
            lines.append(f"  {entry.issue_id}: {transitions} ({disk})")
    return "\n".join(lines)
