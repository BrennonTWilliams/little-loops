"""Cross-repo activity counts over a declared workspace (FEAT-3445).

Sibling to `workspace_quality.aggregate_history_dbs()`: given a list of
`WorkspaceMember` rows, opens each member's ``history.db`` read-only via the
shared `workspace_quality._gate_member()` gate -- never
``history_reader/_base.py::_connect_readonly()``, which calls ``ensure_db()``
and would migrate a stale member in place before the gate could see it -- and
counts loop and issue-lifecycle activity over a ``since``/``until`` window.

Unlike quality's ATTACH/union machinery, every metric here is
per-(repo, issue) sum-decomposable: ``loop_runs.run_id`` is ``UNIQUE`` within
one member db, and ``idx_issue_events_dedup`` is a per-member partial-unique
on ``(issue_num, transition)``, so workspace totals are a plain Python sum
over ``ok`` members -- no ATTACH, no cross-repo id discriminator. An issue
counts once per repo it appears in; same-ID issues in different repos are
distinct logical issues (every little-loops repo numbers issues from 1).

Timestamps are compared in Python, not SQL: ``loop_runs.started_at`` /
``issue_events.ts`` are written in mixed ``+00:00``-with-microseconds and
``Z``-suffixed forms depending on writer, and raw lexicographic comparison of
those forms does not sort the way the timestamps' actual instants do. `_parse_ts()`
normalizes each row value (and the ``since``/``until`` bounds) via
``datetime.fromisoformat()``, treating naive values (no offset) as UTC. NULL,
empty-string, and unparseable timestamps are excluded from windowed counts
and included in unbounded counts -- an unbounded count is a row count; a
windowed one requires a comparable timestamp.

Known limitations (accepted, not solved here):
- FSM signals (stalls, cycles, rate-limits) are webhook-only and never land
  in history.db, so no read here can cover them.
- ``_ISSUE_TRANSITION_MAP`` maps ``issue.closed`` -> ``'done'`` but
  ``issue.skipped`` -> ``'cancelled'`` (and backfill writes ``cancelled``
  verbatim), so live-closed issues count as ``issues_completed`` while
  live-skipped/backfilled-cancelled issues count nowhere -- ``issues_closed``
  stays a reserved always-``None`` field rather than a count.
- Backfilled ``done`` issues with no ``completed_at`` frontmatter get
  ``ts = captured_at`` (or ``discovered_date``), so they count as completed
  at capture time, not completion time. Live ``record_issue_event`` rows are
  unaffected.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from little_loops.issue_history.workspace_quality import _gate_member, _label
from little_loops.workspace import WorkspaceMember


class MemberActivityStatus(Enum):
    """Machine-readable outcome of gating + counting one workspace member."""

    OK = "ok"  # counts present (possibly zero)
    DB_MISSING = "db_missing"  # no history.db -> instrumented: False
    SCHEMA_SKEW = "schema_skew"  # version mismatch -> instrumented: True, counts unreadable
    UNREADABLE = "unreadable"  # sqlite3.Error on open, version read, or the count SQL


@dataclass(frozen=True)
class RepoActivity:
    """One member's activity counts (or skip reason) -- frozen, crosses a boundary."""

    repo_path: str
    role: str
    label: str
    status: MemberActivityStatus
    instrumented: bool
    reason: str | None = None
    loops_run: int | None = None
    loops_completed: int | None = None
    issues_completed: int | None = None
    issues_deferred: int | None = None
    issues_closed: None = None  # reserved: always None, see module docstring

    def to_dict(self) -> dict[str, Any]:
        """Canonical serialization: `ok`/`error` are the consumer-facing fields."""
        return {
            "repo_path": self.repo_path,
            "role": self.role,
            "label": self.label,
            "status": self.status.value,
            "ok": self.status is MemberActivityStatus.OK,
            "error": self.reason,
            "instrumented": self.instrumented,
            "loops_run": self.loops_run,
            "loops_completed": self.loops_completed,
            "issues_completed": self.issues_completed,
            "issues_deferred": self.issues_deferred,
            "issues_closed": self.issues_closed,
        }


@dataclass(frozen=True)
class WorkspaceTotals:
    """Workspace-wide sums over `ok` members, plus membership/instrumentation counts."""

    members: int
    instrumented_members: int
    instrumented: bool
    ok_members: int
    loops_run: int | None
    loops_completed: int | None
    issues_completed: int | None
    issues_deferred: int | None
    issues_closed: None = None  # reserved: always None, same rule as RepoActivity

    def to_dict(self) -> dict[str, Any]:
        """Keys in declaration order above (stable order: FEAT-3446 AC 1)."""
        return {
            "members": self.members,
            "instrumented_members": self.instrumented_members,
            "instrumented": self.instrumented,
            "ok_members": self.ok_members,
            "loops_run": self.loops_run,
            "loops_completed": self.loops_completed,
            "issues_completed": self.issues_completed,
            "issues_deferred": self.issues_deferred,
            "issues_closed": self.issues_closed,
        }


@dataclass(frozen=True)
class WorkspaceActivityResult:
    """`aggregate_workspace_activity()`'s return value: per-repo rows plus totals."""

    since: str | None
    until: str | None
    per_repo: dict[str, RepoActivity]
    totals: WorkspaceTotals

    def to_dict(self) -> dict[str, Any]:
        return {
            "since": self.since,
            "until": self.until,
            "per_repo": [activity.to_dict() for activity in self.per_repo.values()],
            "totals": self.totals.to_dict(),
        }


def _parse_ts(value: str | None) -> datetime | None:
    """Parse a possibly-mixed-format, possibly-naive, possibly-empty timestamp.

    Returns ``None`` for ``None``, ``""``, or any string `datetime.fromisoformat()`
    rejects after normalizing a trailing ``Z`` to ``+00:00`` (NULL/empty/
    unparseable rule). A naive result (no offset -- including date-only input)
    is treated as UTC.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _in_window(ts: datetime, since_dt: datetime | None, until_dt: datetime | None) -> bool:
    if since_dt is not None and ts < since_dt:
        return False
    return not (until_dt is not None and ts > until_dt)


def _count_loops_run(
    conn: sqlite3.Connection, since_dt: datetime | None, until_dt: datetime | None
) -> int:
    if since_dt is None and until_dt is None:
        return conn.execute("SELECT COUNT(*) FROM loop_runs").fetchone()[0]
    count = 0
    for (started_at,) in conn.execute("SELECT started_at FROM loop_runs"):
        ts = _parse_ts(started_at)
        if ts is not None and _in_window(ts, since_dt, until_dt):
            count += 1
    return count


def _count_loops_completed(
    conn: sqlite3.Connection, since_dt: datetime | None, until_dt: datetime | None
) -> int:
    if since_dt is None and until_dt is None:
        row = conn.execute("SELECT COUNT(*) FROM loop_runs WHERE ended_at IS NOT NULL").fetchone()
        return row[0]
    count = 0
    rows = conn.execute("SELECT ended_at FROM loop_runs WHERE ended_at IS NOT NULL")
    for (ended_at,) in rows:
        ts = _parse_ts(ended_at)
        if ts is not None and _in_window(ts, since_dt, until_dt):
            count += 1
    return count


def _count_issue_transition(
    conn: sqlite3.Connection,
    transition: str,
    since_dt: datetime | None,
    until_dt: datetime | None,
) -> int:
    if since_dt is None and until_dt is None:
        return conn.execute(
            "SELECT COUNT(*) FROM issue_events WHERE transition = ?", (transition,)
        ).fetchone()[0]
    count = 0
    rows = conn.execute("SELECT ts FROM issue_events WHERE transition = ?", (transition,))
    for (ts_str,) in rows:
        ts = _parse_ts(ts_str)
        if ts is not None and _in_window(ts, since_dt, until_dt):
            count += 1
    return count


def _count_member_activity(
    conn: sqlite3.Connection, since_dt: datetime | None, until_dt: datetime | None
) -> tuple[int, int, int, int]:
    return (
        _count_loops_run(conn, since_dt, until_dt),
        _count_loops_completed(conn, since_dt, until_dt),
        _count_issue_transition(conn, "done", since_dt, until_dt),
        _count_issue_transition(conn, "deferred", since_dt, until_dt),
    )


def _totals(per_repo: dict[str, RepoActivity]) -> WorkspaceTotals:
    ok_rows = [r for r in per_repo.values() if r.status is MemberActivityStatus.OK]
    ok_members = len(ok_rows)

    def _sum(attr: str) -> int | None:
        if ok_members == 0:
            return None
        return sum(getattr(r, attr) for r in ok_rows)

    return WorkspaceTotals(
        members=len(per_repo),
        instrumented_members=sum(1 for r in per_repo.values() if r.instrumented),
        instrumented=any(r.instrumented for r in per_repo.values()),
        ok_members=ok_members,
        loops_run=_sum("loops_run"),
        loops_completed=_sum("loops_completed"),
        issues_completed=_sum("issues_completed"),
        issues_deferred=_sum("issues_deferred"),
    )


def aggregate_workspace_activity(
    members: list[WorkspaceMember], *, since: str | None, until: str | None = None
) -> WorkspaceActivityResult:
    """Return one `RepoActivity` per member plus workspace-wide `WorkspaceTotals`.

    Never raises: a missing db, a schema-version mismatch, or a
    ``sqlite3.Error`` on open/read/count all resolve to a status-carrying
    `RepoActivity` instead of an exception. `members` comes from
    `discover_workspace_members()`; keyed by ``str(member.db_path)`` (not
    ``repo_path`` -- see module docstring / issue Known limitations for why).
    """
    since_dt = _parse_ts(since)
    until_dt = _parse_ts(until)

    per_repo: dict[str, RepoActivity] = {}
    for member in members:
        label = _label(member)
        repo_path = str(member.repo_path)
        db_key = str(member.db_path)

        conn, reason, kind = _gate_member(member)
        if reason is not None:
            status = MemberActivityStatus(kind)
            per_repo[db_key] = RepoActivity(
                repo_path=repo_path,
                role=member.role,
                label=label,
                status=status,
                instrumented=status is not MemberActivityStatus.DB_MISSING,
                reason=reason,
            )
            continue

        assert conn is not None
        try:
            counts = _count_member_activity(conn, since_dt, until_dt)
        except sqlite3.Error as exc:
            per_repo[db_key] = RepoActivity(
                repo_path=repo_path,
                role=member.role,
                label=label,
                status=MemberActivityStatus.UNREADABLE,
                instrumented=True,
                reason=f"count query failed: {exc}",
            )
            continue
        finally:
            conn.close()

        loops_run, loops_completed, issues_completed, issues_deferred = counts
        per_repo[db_key] = RepoActivity(
            repo_path=repo_path,
            role=member.role,
            label=label,
            status=MemberActivityStatus.OK,
            instrumented=True,
            loops_run=loops_run,
            loops_completed=loops_completed,
            issues_completed=issues_completed,
            issues_deferred=issues_deferred,
        )

    return WorkspaceActivityResult(
        since=since, until=until, per_repo=per_repo, totals=_totals(per_repo)
    )


def _activity_count_lines(
    loops_run: int | None,
    loops_completed: int | None,
    issues_completed: int | None,
    issues_deferred: int | None,
) -> list[str]:
    """Shared count rows for the text/markdown formatters (FEAT-3446)."""
    return [
        f"loops run: {loops_run}",
        f"loops completed: {loops_completed}",
        f"issues completed: {issues_completed}",
        f"issues deferred: {issues_deferred}",
    ]


def _activity_window_line(result: WorkspaceActivityResult) -> str:
    bits = []
    if result.since is not None:
        bits.append(f"since {result.since}")
    if result.until is not None:
        bits.append(f"until {result.until}")
    return f"Window: {', '.join(bits) if bits else 'unbounded'}"


def format_workspace_activity_json(result: WorkspaceActivityResult) -> str:
    """Serialize via the duck-typed `to_dict()` contract, no transformation.

    Mirrors `format_agent_quality_json()`: `WorkspaceActivityResult.to_dict()`
    is the canonical consumer shape (stable key order, `null`-for-unavailable
    counts), so JSON output is a verbatim dump of it.
    """
    return json.dumps(result.to_dict(), indent=2)


def format_workspace_activity_yaml(result: WorkspaceActivityResult) -> str:
    """YAML rendering of the same `to_dict()` contract.

    Falls back to the JSON formatter when PyYAML is absent -- JSON is valid
    YAML, so output stays parseable either way.
    """
    try:
        import yaml
    except ImportError:
        return format_workspace_activity_json(result)
    return yaml.dump(result.to_dict(), default_flow_style=False, sort_keys=False)


def format_workspace_activity_text(result: WorkspaceActivityResult) -> str:
    """Human-readable report: one section per member, then workspace totals."""
    lines = [
        "Workspace Activity Report",
        "=" * 25,
        _activity_window_line(result),
        "",
    ]
    for activity in result.per_repo.values():
        lines.append(activity.label)
        lines.append("-" * len(activity.label))
        lines.append(f"status: {activity.status.value}")
        if activity.status is MemberActivityStatus.OK:
            lines.extend(
                _activity_count_lines(
                    activity.loops_run,
                    activity.loops_completed,
                    activity.issues_completed,
                    activity.issues_deferred,
                )
            )
        else:
            lines.append(f"error: {activity.reason}")
        lines.append("")

    totals = result.totals
    lines.append("Workspace totals")
    lines.append("-" * 16)
    lines.append(
        f"members: {totals.members} (ok: {totals.ok_members}, "
        f"instrumented: {totals.instrumented_members})"
    )
    if totals.ok_members:
        lines.extend(
            _activity_count_lines(
                totals.loops_run,
                totals.loops_completed,
                totals.issues_completed,
                totals.issues_deferred,
            )
        )
    else:
        lines.append("counts: unavailable (no ok members)")
    return "\n".join(lines)


def format_workspace_activity_markdown(result: WorkspaceActivityResult) -> str:
    """Markdown variant of the workspace activity report."""
    lines = [
        "# Workspace Activity Report",
        "",
        _activity_window_line(result),
        "",
    ]
    for activity in result.per_repo.values():
        lines.append(f"## {activity.label}")
        lines.append("")
        lines.append(f"- status: `{activity.status.value}`")
        if activity.status is MemberActivityStatus.OK:
            for line in _activity_count_lines(
                activity.loops_run,
                activity.loops_completed,
                activity.issues_completed,
                activity.issues_deferred,
            ):
                lines.append(f"- {line}")
        else:
            lines.append(f"- error: {activity.reason}")
        lines.append("")

    totals = result.totals
    lines.extend(["## Workspace totals", ""])
    lines.append(
        f"- members: {totals.members} (ok: {totals.ok_members}, "
        f"instrumented: {totals.instrumented_members})"
    )
    if totals.ok_members:
        for line in _activity_count_lines(
            totals.loops_run,
            totals.loops_completed,
            totals.issues_completed,
            totals.issues_deferred,
        ):
            lines.append(f"- {line}")
    else:
        lines.append("- counts: unavailable (no ok members)")
    return "\n".join(lines)
