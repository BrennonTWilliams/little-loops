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

Workspace-wide totals (FEAT-3418) are computed after the per-member loop by
ATTACHing every gated member's ``history.db`` read-only, as schema ``r{i}``,
to one ``:memory:`` connection, then defining a **TEMP** view per relation
the analysis reads as a ``UNION ALL`` over ``r0.<rel>``, ``r1.<rel>``, ....
SQLite resolves an unqualified table name in search order
``temp -> main -> attached``, so every existing unqualified query in
`agent_quality`/`rework`/`_utils`/`quality_regressions` hits the union view
unchanged -- no query site is rewritten. A ``main``-schema view cannot do
this: SQLite rejects ``CREATE VIEW main.<name>`` outright whenever the view
body references any attached-schema object (`.ll/learning-tests/sqlite3.md`
claim 2).

Cross-repo `issue_num`/`issue_id` collisions (every little-loops repo numbers
issues from 1) are resolved *inside* the union views, per id column present:
``issue_id`` gets a ``#r{i}`` **suffix** (never a prefix -- `rework.py`'s
`_has_follow_up` parses `commit_events.issue_id` with
``startswith("BUG-")``, which a prefix would silently break), and
``issue_num`` gets an ``i * _ISSUE_NUM_STRIDE`` offset. The on-disk side is
handled symmetrically: `_discriminate_issues()` suffixes each member's
`IssueInfo.issue_id`/`supersedes` the same way, so `superseded_by()`'s
set-membership join only matches ids within one member. A workspace member
whose analyzable count exceeds the union connection's
``SQLITE_LIMIT_ATTACHED`` cannot be attached at all; `totals` is `None` and
`totals_skipped` names the count and the limit rather than silently unioning
a truncated subset. Session ids are UUIDs shared verbatim across members
(no dedup); a session id present in more than one member's db double-counts
in `totals` -- accepted, documented, does not affect `per_repo`.

Constructing ``BRConfig(member.repo_path)`` for the per-member issues lookup
runs ``load_env_fallback()`` on that member's ``.env``, process-wide,
first-member-wins in manifest order. Nothing downstream here reads those
keys (this module never calls ``resolve_history_db()``), so this is accepted
as a side effect rather than mitigated.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_history.agent_quality import QualityAnalysis, analyze_agent_quality
from little_loops.issue_parser import IssueInfo, find_issues
from little_loops.session_store.queries import read_schema_version
from little_loops.session_store.schema import SCHEMA_VERSION
from little_loops.workspace import WorkspaceMember

_ALL_STATUSES = {"open", "in_progress", "blocked", "deferred", "done", "cancelled"}

_UNION_RELATIONS: tuple[str, ...] = (
    "issue_events",
    "issue_sessions",
    "correction_retirements",
    "user_corrections",
    "usage_events",
    "loop_runs",
    "commit_events",
    "orchestration_runs",
    "raw_events",
)
_ISSUE_NUM_STRIDE = 1_000_000_000


@dataclass(frozen=True)
class AggregationResult:
    """Per-repo quality breakdown across a workspace, plus skipped members.

    `totals` (FEAT-3418) is one `QualityAnalysis` over the union of every
    gated member's tables -- see the module docstring for the mechanism.
    """

    per_repo: dict[str, QualityAnalysis]
    skipped: list[tuple[str, str]] = field(default_factory=list)
    totals: QualityAnalysis | None = None
    totals_skipped: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the JSON/YAML formatters, mirroring `QualityAnalysis.to_dict()`."""
        return {
            "per_repo": {label: analysis.to_dict() for label, analysis in self.per_repo.items()},
            "skipped": [{"repo": label, "reason": reason} for label, reason in self.skipped],
            "totals": self.totals.to_dict() if self.totals is not None else None,
            "totals_skipped": self.totals_skipped,
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


def _gate_member(
    member: WorkspaceMember,
) -> tuple[sqlite3.Connection, None, None] | tuple[None, str, str]:
    """Open *member*'s history.db read-only and validate its schema version.

    Shared by `aggregate_history_dbs()` (FEAT-3410) and
    `workspace_activity.aggregate_workspace_activity()` (FEAT-3445): a missing
    ``db_path``, a schema-version mismatch, or a ``sqlite3.Error`` on
    open/read are the same skip conditions for both callers.

    Returns ``(conn, None, None)`` on success -- the caller owns closing
    *conn*. Returns ``(None, reason, kind)`` on any skip condition, closing
    any connection it opened itself first; *kind* is one of ``"db_missing"``,
    ``"schema_skew"``, ``"unreadable"`` -- the same string values as
    `workspace_activity.MemberActivityStatus` without this module depending
    on that sibling's enum.
    """
    if not member.db_path.exists():
        return None, f"history.db not found at {member.db_path}", "db_missing"

    conn: sqlite3.Connection | None = None
    try:
        conn = _open_member_readonly(member.db_path)
        version = read_schema_version(conn)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        return None, f"could not read read-only: {exc}", "unreadable"

    if version is None:
        conn.close()
        return None, "schema_version missing (no meta row)", "schema_skew"
    if version != str(SCHEMA_VERSION):
        conn.close()
        return None, f"schema_version {version} != installed {SCHEMA_VERSION}", "schema_skew"

    return conn, None, None


def _discriminator(index: int) -> str:
    return f"#r{index}"


def _attach_limit(conn: sqlite3.Connection) -> int:
    """Return this SQLite build's max ATTACHed-database count (a monkeypatch seam)."""
    return conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED)


def _union_view_sql(conn: sqlite3.Connection, relation: str, schema_count: int) -> str:
    """Build ``CREATE TEMP VIEW <relation> AS ... UNION ALL ...`` over ``r0..r{schema_count-1}``.

    Column substitution is per column *present* on the relation, not per
    relation: any column named ``issue_id`` gets a ``#r{i}`` suffix, any
    column named ``issue_num`` gets an ``i * _ISSUE_NUM_STRIDE`` offset,
    every other column passes through unchanged. ``main`` cannot host this
    view -- see the module docstring.
    """
    columns = [row["name"] for row in conn.execute(f"PRAGMA r0.table_info({relation})")]

    branches = []
    for i in range(schema_count):
        suffix = _discriminator(i)
        select_cols = []
        for col in columns:
            if col == "issue_id":
                select_cols.append(f"issue_id || '{suffix}' AS issue_id")
            elif col == "issue_num":
                select_cols.append(f"{i} * {_ISSUE_NUM_STRIDE} + issue_num AS issue_num")
            else:
                select_cols.append(col)
        branches.append(f"SELECT {', '.join(select_cols)} FROM r{i}.{relation}")

    union_sql = " UNION ALL ".join(branches)
    return f"CREATE TEMP VIEW {relation} AS {union_sql}"  # noqa: S608


def _open_union(db_paths: list[Path]) -> sqlite3.Connection:
    """ATTACH every path read-only as ``r{i}`` and define the 9 TEMP union views.

    Caller has already checked ``len(db_paths) <= _attach_limit(conn)``. The
    views are created *before* ``PRAGMA query_only = ON`` -- that pragma also
    blocks ``CREATE TEMP VIEW``.
    """
    conn = sqlite3.connect(":memory:", uri=True)
    conn.row_factory = sqlite3.Row
    for i, path in enumerate(db_paths):
        conn.execute(f"ATTACH DATABASE ? AS r{i}", (f"file:{path}?mode=ro",))
    for relation in _UNION_RELATIONS:
        conn.execute(_union_view_sql(conn, relation, len(db_paths)))
    conn.execute("PRAGMA query_only = ON")
    return conn


def _open_memory() -> sqlite3.Connection:
    """A bare ``:memory:`` connection, used only to read `_attach_limit()` before attaching."""
    conn = sqlite3.connect(":memory:", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _discriminate_issues(issues: list[IssueInfo], suffix: str) -> list[IssueInfo]:
    """Suffix ``issue_id``/`supersedes` so a member's issues only join with its own db rows."""
    return [
        replace(
            info,
            issue_id=f"{info.issue_id}{suffix}",
            supersedes=[f"{s}{suffix}" for s in info.supersedes],
        )
        for info in issues
    ]


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
    gated: list[tuple[Path, list[IssueInfo]]] = []

    for member in members:
        label = _label(member)
        conn, reason, _kind = _gate_member(member)
        if reason is not None:
            skipped.append((label, reason))
            continue
        assert conn is not None

        try:
            issues = find_issues(BRConfig(member.repo_path), status_filter=_ALL_STATUSES)
            per_repo[label] = analyze_agent_quality(
                issues,
                conn=conn,
                min_sample=min_sample,
                sensitivity=sensitivity,
                baseline_windows=baseline_windows,
                latest_only=latest_only,
            )
            gated.append((member.db_path, issues))
        finally:
            conn.close()

    totals: QualityAnalysis | None = None
    totals_skipped: str | None = None
    if not gated:
        totals_skipped = "no analyzable members"
    else:
        probe = _open_memory()
        try:
            limit = _attach_limit(probe)
        finally:
            probe.close()

        if len(gated) > limit:
            totals_skipped = (
                f"{len(gated)} analyzable members exceed this SQLite build's "
                f"SQLITE_LIMIT_ATTACHED={limit}; trim the workspace manifest to at most "
                f"{limit} members with a history.db"
            )
        else:
            union_conn = _open_union([path for path, _ in gated])
            try:
                combined_issues = [
                    discriminated
                    for i, (_, issues) in enumerate(gated)
                    for discriminated in _discriminate_issues(issues, _discriminator(i))
                ]
                totals = analyze_agent_quality(
                    combined_issues,
                    conn=union_conn,
                    min_sample=min_sample,
                    sensitivity=sensitivity,
                    baseline_windows=baseline_windows,
                    latest_only=latest_only,
                )
            finally:
                union_conn.close()

    return AggregationResult(
        per_repo=per_repo, skipped=skipped, totals=totals, totals_skipped=totals_skipped
    )
