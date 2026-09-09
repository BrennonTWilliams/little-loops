"""Cross-repo history.db aggregation over a declared workspace (FEAT-3410).

Given a list of `WorkspaceMember` rows (from FEAT-3409's
`discover_workspace_members()`), opens each member's ``history.db``
read-only and runs `analyze_agent_quality()` once per member, producing a
per-repo breakdown plus a list of skipped members with reasons. Source
databases are never written to, migrated, or locked for writes: each
connection is opened directly via a ``file:...?mode=ro`` URI (modeled on
``issue_history/evolution.py::_open_db()``), never through
``history_reader/_base.py::_connect_readonly()``, which calls ``ensure_db()``
and would migrate a stale member in place before the schema-skew gate below
could see it. Opening a WAL-mode member creates ``-wal``/``-shm`` sidecars on
first read that persist after close -- expected, not a violation; the main
file's bytes are unchanged.

Workspace-wide totals (one `QualityAnalysis` merged across all members) are
out of scope -- see FEAT-3410's Design Notes § "Why totals are deferred" and
the follow-up issue FEAT-3418, which owns the multi-ATTACH union mechanism
and the cross-repo issue-ID discriminator it requires.

Constructing ``BRConfig(member.repo_path)`` for the per-member issues lookup
runs ``load_env_fallback()`` on that member's ``.env``, process-wide,
first-member-wins in manifest order. Nothing downstream here reads those
keys (this module never calls ``resolve_history_db()``), so this is accepted
as a side effect rather than mitigated.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_history.agent_quality import QualityAnalysis, analyze_agent_quality
from little_loops.issue_parser import find_issues
from little_loops.session_store.queries import read_schema_version
from little_loops.session_store.schema import SCHEMA_VERSION
from little_loops.workspace import WorkspaceMember

_ALL_STATUSES = {"open", "in_progress", "blocked", "deferred", "done", "cancelled"}


@dataclass(frozen=True)
class AggregationResult:
    """Per-repo quality breakdown across a workspace, plus skipped members.

    No ``totals`` field -- see the module docstring's "Why totals are
    deferred" pointer.
    """

    per_repo: dict[str, QualityAnalysis]
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON/YAML formatters, mirroring `QualityAnalysis.to_dict()`."""
        return {
            "per_repo": {label: analysis.to_dict() for label, analysis in self.per_repo.items()},
            "skipped": [{"repo": label, "reason": reason} for label, reason in self.skipped],
        }


def _label(member: WorkspaceMember) -> str:
    return f"{member.repo_path.name} ({member.role})"


def _open_member_readonly(db_path: Path) -> sqlite3.Connection:
    """Open *db_path* read-only without running schema migrations.

    Modeled on ``issue_history/evolution.py::_open_db()``. May raise
    ``sqlite3.Error`` -- the caller wraps both this call and the
    `read_schema_version()` read in one try/except, since a non-SQLite or
    corrupt file opens lazily without error and only fails on its first
    query.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def aggregate_history_dbs(
    members: list[WorkspaceMember],
    *,
    min_sample: int,
    sensitivity: float,
    baseline_windows: int,
    latest_only: bool,
) -> AggregationResult:
    """Run `analyze_agent_quality()` once per workspace member, read-only.

    Per member: a missing ``db_path``, a schema-version mismatch (behind,
    ahead, or unreadable meta), or a ``sqlite3.Error`` on open/read skips the
    member and records ``(label, reason)`` in `AggregationResult.skipped`;
    nothing raises. `members` comes from FEAT-3409's
    `discover_workspace_members()`; kwargs are forwarded verbatim to
    `analyze_agent_quality()` for every analyzable member.
    """
    per_repo: dict[str, QualityAnalysis] = {}
    skipped: list[tuple[str, str]] = []

    for member in members:
        label = _label(member)
        if not member.db_path.exists():
            skipped.append((label, f"history.db not found at {member.db_path}"))
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = _open_member_readonly(member.db_path)
            version = read_schema_version(conn)
        except sqlite3.Error as exc:
            if conn is not None:
                conn.close()
            skipped.append((label, f"could not read read-only: {exc}"))
            continue

        try:
            if version is None:
                skipped.append((label, "schema_version missing (no meta row)"))
                continue
            if version != str(SCHEMA_VERSION):
                skipped.append((label, f"schema_version {version} != installed {SCHEMA_VERSION}"))
                continue

            issues = find_issues(BRConfig(member.repo_path), status_filter=_ALL_STATUSES)
            per_repo[label] = analyze_agent_quality(
                issues,
                conn=conn,
                min_sample=min_sample,
                sensitivity=sensitivity,
                baseline_windows=baseline_windows,
                latest_only=latest_only,
            )
        finally:
            conn.close()

    return AggregationResult(per_repo=per_repo, skipped=skipped)
