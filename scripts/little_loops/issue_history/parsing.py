"""Issue history parsing and scanning functions.

Provides functions to parse completed issue files, extract metadata
from frontmatter and content, scan directories for issues, and
extract file paths from issue content.
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from little_loops.frontmatter import parse_frontmatter
from little_loops.issue_history.models import CompletedIssue
from little_loops.text_utils import extract_file_paths

logger = logging.getLogger(__name__)

# (parsed date, tracked_without_history): the second element distinguishes a
# tracked file whose git log legitimately returned nothing from a pathspec
# that silently matched nothing (both would otherwise look like `None`).
_GitDateResult = tuple[date | None, bool]

# Count of _git_completion_date calls that hit the tracked-without-history
# case during the current scan_completed_issues() run. Reset at the start of
# each scan and drained into a single aggregated warning at the end, so a
# per-file warning doesn't spray stderr for routine staged-but-uncommitted
# issue files (BUG-3243).
_tracked_without_history_count = 0


def parse_completed_issue(
    file_path: Path, *, batch_dates: dict[str, date] | None = None
) -> CompletedIssue:
    """Parse a completed issue file.

    Args:
        file_path: Path to the issue markdown file
        batch_dates: Optional pre-fetched mapping of filename → add-date from a batch
            git log call; when provided, skips the per-file subprocess call.

    Returns:
        CompletedIssue with parsed metadata
    """
    filename = file_path.name
    content = file_path.read_text(encoding="utf-8")

    # Extract from filename: P[0-5]-[TYPE]-[NNN]-description.md
    issue_type = "UNKNOWN"
    priority = "P5"
    issue_id = "UNKNOWN"

    # Match priority
    priority_match = re.match(r"^(P\d)", filename)
    if priority_match:
        priority = priority_match.group(1)

    # Match type and ID
    type_match = re.search(r"(BUG|ENH|FEAT|EPIC)-(\d+)", filename)
    if type_match:
        issue_type = type_match.group(1)
        issue_id = f"{type_match.group(1)}-{type_match.group(2)}"

    # Parse frontmatter once for discovered_by, discovered_date, captured_at
    fm = parse_frontmatter(content)
    discovered_by = _parse_discovered_by(fm)
    captured_at = _parse_captured_at(fm)
    discovered_date = _parse_discovered_date(fm)

    # Parse completion date from Resolution section or file mtime
    completed_at = _parse_completed_at(fm)
    completed_date = _parse_completion_date(content, file_path, batch_dates=batch_dates, fm=fm)

    return CompletedIssue(
        path=file_path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        discovered_by=discovered_by,
        discovered_date=discovered_date,
        completed_date=completed_date,
        captured_at=captured_at,
        completed_at=completed_at,
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 string into a naive datetime, or return None.

    Strips a trailing ``Z`` for Python <3.11 compatibility (same convention as
    the sibling ``cli/issues/search.py`` implementation).
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_captured_at(fm: dict[str, Any]) -> datetime | None:
    """Extract captured_at datetime from parsed frontmatter."""
    return _parse_iso_datetime(fm.get("captured_at"))


def _parse_completed_at(fm: dict[str, Any]) -> datetime | None:
    """Extract completed_at datetime from parsed frontmatter."""
    return _parse_iso_datetime(fm.get("completed_at"))


def _parse_discovered_by(fm: dict[str, Any]) -> str | None:
    """Extract discovered_by from parsed frontmatter.

    Args:
        fm: Parsed frontmatter dictionary

    Returns:
        discovered_by value or None
    """
    value = fm.get("discovered_by")
    return value if isinstance(value, str) else None


def _batch_completion_dates(_issues_dir: Path) -> dict[str, date]:
    """No-op stub kept for legacy callers.

    The previous implementation used ``git log --diff-filter=A`` against
    ``completed/`` to detect when issue files were *moved* into completion.
    With status decoupled from directory location (ENH-1418), files no
    longer move on completion; ``completed_at:`` frontmatter is the primary
    source of truth, with a per-file ``git log -1`` fallback in
    ``_parse_completion_date``. ENH-1420 will backfill ``completed_at`` for
    pre-decoupling issues, after which the per-file fallback can also be
    removed.

    Args:
        _issues_dir: Unused (kept for signature stability).

    Returns:
        An empty mapping.
    """
    return {}


def _parse_completion_date(
    content: str,
    file_path: Path,
    *,
    batch_dates: dict[str, date] | None = None,
    fm: dict[str, Any] | None = None,
) -> date | None:
    """Extract completion date from frontmatter, Resolution section, or git log.

    Checks ``completed_at`` frontmatter first (coerced to ``date`` via ``.date()``
    to preserve the existing return type); then the Resolution section regex;
    then falls back to batch_dates or a per-file git log call.

    Args:
        content: File content
        file_path: Path for git log fallback
        batch_dates: Optional pre-fetched mapping of filename → add-date from a batch
            git log call; when provided, skips the per-file subprocess call if the
            file is found in the mapping.
        fm: Optional pre-parsed frontmatter dict. When absent, frontmatter is
            parsed from ``content`` so external callers with no ``fm`` benefit
            from the ``completed_at`` check transparently.

    Returns:
        Completion date or None
    """
    # Try completed_at frontmatter first (sub-day resolution source of truth)
    if fm is None:
        fm = parse_frontmatter(content)
    completed_at = _parse_completed_at(fm)
    if completed_at is not None:
        return completed_at.date()

    # Try Resolution section: **Completed/Fixed/Closed/Date**: YYYY-MM-DD
    match = re.search(r"\*\*(?:Completed|Fixed|Closed|Date)\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    # Check batch map before falling back to per-file git log
    if batch_dates is not None:
        return batch_dates.get(file_path.name)

    # Fallback to git log: most recent commit date for this file (typically
    # the close/done commit, since status writes are the latest change).
    parsed_date, tracked_without_history = _git_completion_date(file_path)
    if tracked_without_history:
        global _tracked_without_history_count
        _tracked_without_history_count += 1
        logger.debug("git log found no history for tracked file: %s", file_path)
    return parsed_date


def _git_completion_date(file_path: Path) -> _GitDateResult:
    """Look up ``file_path``'s most recent commit date via ``git log``.

    The pathspec is ``file_path.name`` (not ``file_path`` or
    ``file_path.resolve()``) so it agrees with ``cwd=file_path.parent`` —
    passing the caller's (possibly relative) path as-is while running from
    the file's own directory silently matches nothing (BUG-3243).
    ``.resolve()`` was considered and rejected: it collapses symlinks, which
    would mismatch a worktree git discovered by a logical path (e.g. macOS
    ``/tmp`` -> ``/private/tmp`` under ``tmp_path``-based tests).

    Returns:
        ``(date, False)`` when git log found a commit; ``(None, False)`` when
        the file has no git history at all (untracked, or outside a repo);
        ``(None, True)`` when the file *is* tracked but git log returned no
        commit for it — a state the caller logs but does not treat as an
        error, since a staged-but-uncommitted issue file legitimately looks
        like this.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--format=%as", "-1", "--", file_path.name],
            capture_output=True,
            text=True,
            cwd=file_path.parent,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return date.fromisoformat(result.stdout.strip()), False
        if result.returncode == 0:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", file_path.name],
                capture_output=True,
                text=True,
                cwd=file_path.parent,
                timeout=10,
            )
            return None, tracked.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None, False


def _parse_resolution_action(content: str) -> str:
    """Extract resolution action category from issue content.

    Categorizes based on Resolution section fields:
    - "completed": Normal completion with **Action**: fix/implement
    - "rejected": Explicitly rejected (out of scope, not valid)
    - "invalid": Invalid reference or spec
    - "duplicate": Duplicate of existing issue
    - "deferred": Deferred to future work

    Args:
        content: Issue file content

    Returns:
        Resolution category string
    """
    # Look for Status field patterns
    status_match = re.search(r"\*\*Status\*\*:\s*(.+?)(?:\n|$)", content)
    if status_match:
        status = status_match.group(1).strip().lower()
        if "closed" in status:
            # Check Reason field for specific category
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip().lower()
                if "duplicate" in reason:
                    return "duplicate"
                if "invalid" in reason:
                    return "invalid"
                if "deferred" in reason:
                    return "deferred"
                if "rejected" in reason or "out of scope" in reason:
                    return "rejected"
            # Generic closed without specific reason
            return "rejected"

    # Check for Action field (normal completion)
    action_match = re.search(r"\*\*Action\*\*:\s*(.+?)(?:\n|$)", content)
    if action_match:
        return "completed"

    # Default to completed if no resolution section
    return "completed"


def _detect_processing_agent(content: str, discovered_source: str | None = None) -> str:
    """Detect which processing agent handled an issue.

    Detection strategy (in priority order):
    1. Check discovered_source field for 'll-parallel' or 'll-auto'
    2. Check content for '**Log Type**:' field
    3. Check content for '**Tool**:' field
    4. Default to 'manual'

    Args:
        content: Issue file content
        discovered_source: Optional discovered_source frontmatter value

    Returns:
        Agent name: 'll-auto', 'll-parallel', or 'manual'
    """
    # Check discovered_source first
    if discovered_source:
        source_lower = discovered_source.lower()
        if "ll-parallel" in source_lower:
            return "ll-parallel"
        if "ll-auto" in source_lower:
            return "ll-auto"

    # Check Log Type field
    log_type_match = re.search(r"\*\*Log Type\*\*:\s*(.+?)(?:\n|$)", content)
    if log_type_match:
        log_type = log_type_match.group(1).strip().lower()
        if "ll-parallel" in log_type:
            return "ll-parallel"
        if "ll-auto" in log_type:
            return "ll-auto"

    # Check Tool field
    tool_match = re.search(r"\*\*Tool\*\*:\s*(.+?)(?:\n|$)", content)
    if tool_match:
        tool = tool_match.group(1).strip().lower()
        if "ll-parallel" in tool:
            return "ll-parallel"
        if "ll-auto" in tool:
            return "ll-auto"

    # Default to manual
    return "manual"


def scan_completed_issues(
    issues_dir: Path,
    category_dirs: list[str] | None = None,
) -> list[CompletedIssue]:
    """Scan type directories for issues with ``status: done`` frontmatter.

    Files no longer move into a ``completed/`` subdirectory on completion
    (ENH-1418). Completion is detected by ``status: done`` in the file's
    YAML frontmatter; files remain in their original type directory
    (``bugs/``, ``features/``, ``enhancements/``, ``epics/``).

    For backwards compatibility with pre-decoupling repos, a sibling
    ``completed/`` directory under ``issues_dir`` is also scanned when
    present so legacy completed issues continue to surface.

    Args:
        issues_dir: Path to ``.issues/`` (the parent of category dirs).
        category_dirs: Optional override of category subdirectories to scan.
            Defaults to ``["bugs", "features", "enhancements", "epics"]``.

    Returns:
        List of parsed ``CompletedIssue`` objects, sorted by file path.
    """
    issues: list[CompletedIssue] = []

    global _tracked_without_history_count
    _tracked_without_history_count = 0

    if not issues_dir.exists():
        return issues

    scan_dirs = category_dirs or ["bugs", "features", "enhancements", "epics"]
    paths_to_scan: list[Path] = []
    for category_dir in scan_dirs:
        category_path = issues_dir / category_dir
        if not category_path.exists():
            continue
        for file_path in category_path.glob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                fm = parse_frontmatter(content)
            except Exception as e:
                logger.warning("Failed to read %s: %s", file_path, e)
                continue
            if fm.get("status") != "done":
                continue
            paths_to_scan.append(file_path)

    # Legacy completed/ directory (pre-ENH-1418); scan unconditionally
    # so older repos keep working until ENH-1420 backfills.
    legacy_completed = issues_dir / "completed"
    if legacy_completed.exists():
        paths_to_scan.extend(legacy_completed.glob("*.md"))

    for file_path in sorted(paths_to_scan):
        try:
            issue = parse_completed_issue(file_path)
            issues.append(issue)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", file_path, e)
            continue

    if _tracked_without_history_count:
        logger.warning(
            "%d completed issue file(s) are tracked by git but have no commit "
            "history for the git-log completion-date fallback; their "
            "completed_date could not be determined this way",
            _tracked_without_history_count,
        )

    return issues


class HistoryDbUnavailable(Exception):
    """Raised when the session DB exists but cannot be opened or queried.

    Distinguishes "no such store" / "unqueryable" from a genuine empty
    result set (ENH-3237) — callers that need to gate a file-scan fallback
    on availability rather than row count should catch this, not treat an
    empty list as ambiguous.
    """


def issue_events_ever_recorded(db_path: Path) -> bool:
    """True when ``issue_events`` has at least one row, of any transition.

    ENH-3237: ``ll-history`` writes a ``cli_events`` row on *every* invocation
    (``cli_event_context``), so ``db_path.exists()`` alone is true after the
    very first ``ll-history`` call ever made — including a project that has
    never backfilled or live-written any issue lifecycle data. Gating the
    ``summary`` DB-vs-files fallback on file existence alone would then
    silently report "0 completed issues" for a project with real `done`
    issue files simply because the DB happens to have been touched. This
    checks for genuine issue-lifecycle data (any transition, not just
    ``done``) so a never-backfilled DB still routes to the file scan, while a
    populated store answering a legitimately empty window does not.

    Raises :class:`HistoryDbUnavailable` on open/query failure, matching
    :func:`scan_completed_issues_from_db`'s contract, so callers can use one
    except clause for both.
    """
    from little_loops.session_store import connect

    if not db_path.exists():
        return False
    try:
        conn = connect(db_path)
    except Exception as exc:
        logger.warning("Failed to open session DB %s: %s", db_path, exc)
        raise HistoryDbUnavailable(str(exc)) from exc
    try:
        try:
            row = conn.execute("SELECT EXISTS(SELECT 1 FROM issue_events)").fetchone()
        except Exception as exc:
            logger.warning("issue_events existence check failed for %s: %s", db_path, exc)
            raise HistoryDbUnavailable(str(exc)) from exc
    finally:
        conn.close()
    return bool(row[0])


def scan_completed_issues_from_db(
    db_path: Path,
    since: date | None = None,
    until: date | None = None,
) -> list[CompletedIssue]:
    """Read completed-issue summary rows from the unified session DB (ENH-1621).

    Queries the v2 ``issue_events`` table for rows with ``transition='done'``
    and rebuilds :class:`CompletedIssue` dataclasses. Only the summary-relevant
    fields (path, type, priority, id, completion timestamps) are populated —
    ``analyze`` / ``export`` paths that need file bodies or git history must
    continue to use :func:`scan_completed_issues`.

    Args:
        since: When given, keep only issues with ``completed_date >= since``.
        until: When given, keep only issues with ``completed_date <= until``.

    Returns ``[]`` when the DB is present and queryable but has no matching
    rows — a real, empty answer. Raises :class:`HistoryDbUnavailable` when
    the DB cannot be opened or the query fails, so a caller windowing this
    (ENH-3237) can tell "no such store" apart from "no matching rows" instead
    of collapsing both into the same empty list (the fallback trap: falling
    back to an unfiltered file scan on an empty *window* would silently
    misreport a quiet period as a data-source failure).
    """
    from little_loops.session_store import connect

    if not db_path.exists():
        return []
    try:
        conn = connect(db_path)
    except Exception as exc:
        logger.warning("Failed to open session DB %s: %s", db_path, exc)
        raise HistoryDbUnavailable(str(exc)) from exc

    issues: list[CompletedIssue] = []
    try:
        try:
            rows = conn.execute(
                "SELECT issue_id, issue_type, priority, discovered_by, "
                "captured_at, completed_at, completed_date "
                "FROM issue_events WHERE transition = 'done'"
            ).fetchall()
        except Exception as exc:
            logger.warning("issue_events read failed for %s: %s", db_path, exc)
            raise HistoryDbUnavailable(str(exc)) from exc
    finally:
        conn.close()

    for row in rows:
        issue_id = row["issue_id"] or "UNKNOWN"
        issue_type = row["issue_type"] or "UNKNOWN"
        priority = row["priority"] or "P5"
        captured_at = _parse_iso_datetime(row["captured_at"])
        completed_at = _parse_iso_datetime(row["completed_at"])
        completed_date_val = row["completed_date"]
        completed_date: date | None = None
        if isinstance(completed_date_val, str) and completed_date_val:
            try:
                completed_date = date.fromisoformat(completed_date_val[:10])
            except ValueError:
                completed_date = None
        if completed_date is None and completed_at is not None:
            completed_date = completed_at.date()
        # discovered_date is not stored as a discrete column; derive from
        # captured_at when present (mirrors `_parse_discovered_date`).
        discovered_date = captured_at.date() if captured_at is not None else None
        issues.append(
            CompletedIssue(
                path=Path(""),  # not tracked in the DB row
                issue_type=issue_type,
                priority=priority,
                issue_id=issue_id,
                discovered_by=row["discovered_by"],
                discovered_date=discovered_date,
                completed_date=completed_date,
                captured_at=captured_at,
                completed_at=completed_at,
            )
        )

    if since is not None or until is not None:
        issues = [
            i
            for i in issues
            if i.completed_date is not None
            and (since is None or i.completed_date >= since)
            and (until is None or i.completed_date <= until)
        ]

    return issues


def count_loop_runs_in_window(
    db_path: Path,
    since: date | None,
    until: date | None,
) -> tuple[int | None, int | None]:
    """Count ``loop_runs`` rows started/ended within ``[since, until]`` (ENH-3237).

    Started and ended are counted separately since they answer different
    questions: an in-flight run (``ended_at IS NULL``) counts toward
    "started" but never toward "ended", even inside its own window.

    Returns ``(None, None)`` when the DB is absent or unqueryable — a
    metric the store cannot answer must not be reported as ``(0, 0)``
    (see Expected Behavior in ENH-3237).
    """
    from little_loops.session_store import connect

    if not db_path.exists():
        return (None, None)
    try:
        conn = connect(db_path)
    except Exception as exc:
        logger.warning("Failed to open session DB %s: %s", db_path, exc)
        return (None, None)

    try:
        try:
            rows = conn.execute("SELECT started_at, ended_at FROM loop_runs").fetchall()
        except Exception as exc:
            logger.warning("loop_runs read failed for %s: %s", db_path, exc)
            return (None, None)
    finally:
        conn.close()

    def _in_window(ts: Any) -> bool:
        parsed = _parse_iso_datetime(ts)
        if parsed is None:
            return False
        d = parsed.date()
        if since is not None and d < since:
            return False
        if until is not None and d > until:
            return False
        return True

    started = sum(1 for r in rows if _in_window(r["started_at"]))
    ended = sum(1 for r in rows if r["ended_at"] is not None and _in_window(r["ended_at"]))
    return (started, ended)


def _parse_discovered_date(fm: dict[str, Any]) -> date | None:
    """Extract discovered date from parsed frontmatter.

    Prefers ``captured_at`` (ISO datetime, sub-day resolution) when present,
    coercing via ``.date()`` to preserve the legacy ``date | None`` return type
    so callers in ``summary.py`` / ``analysis.py`` / ``cli/history.py`` don't
    need ``.date()`` adjustments. Falls back to ``discovered_date`` on absence
    or parse failure.

    Args:
        fm: Parsed frontmatter dictionary

    Returns:
        Discovered date or None
    """
    captured = _parse_captured_at(fm)
    if captured is not None:
        return captured.date()

    value = fm.get("discovered_date")
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _extract_subsystem(content: str) -> str | None:
    """Extract primary subsystem/directory from issue content.

    Args:
        content: Issue file content

    Returns:
        Directory path (e.g., "scripts/little_loops/") or None
    """
    # Look for file paths in Location or common patterns
    patterns = [
        r"\*\*File\*\*:\s*`?([^`\n]+/)[^/`\n]+`?",  # **File**: path/to/file.py
        r"`([a-zA-Z_][\w/.-]+/)[^/`]+\.py`",  # `path/to/file.py`
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1)

    return None


def _extract_paths_from_issue(content: str) -> list[str]:
    """Extract all file paths from issue content.

    Delegates to :func:`~little_loops.text_utils.extract_file_paths`
    and returns results as a sorted list for backward compatibility.

    Args:
        content: Issue file content

    Returns:
        Sorted list of file paths found in content
    """
    return sorted(extract_file_paths(content))


def _find_test_file(source_path: str, project_root: Path | None = None) -> str | None:
    """Find corresponding test file for a source file.

    Checks common test file naming patterns:
    - tests/test_<name>.py
    - tests/<path>/test_<name>.py
    - <path>/test_<name>.py
    - <path>/<name>_test.py
    - <path>/tests/test_<name>.py

    Args:
        source_path: Path to source file (e.g., "src/core/processor.py")
        project_root: Project root for anchoring existence checks. Defaults to CWD.

    Returns:
        Path to test file if found, None otherwise
    """
    if not source_path.endswith(".py"):
        return None  # Only check Python files for now

    path = Path(source_path)
    stem = path.stem  # filename without extension
    parent = str(path.parent) if path.parent != Path(".") else ""

    # Generate candidate test file paths
    candidates: list[str] = [
        f"tests/test_{stem}.py",
        f"{parent}/test_{stem}.py" if parent else f"test_{stem}.py",
        f"{parent}/{stem}_test.py" if parent else f"{stem}_test.py",
        f"{parent}/tests/test_{stem}.py" if parent else f"tests/test_{stem}.py",
    ]

    # Add path-aware test locations
    if parent:
        candidates.append(f"tests/{parent}/test_{stem}.py")

    # Project-specific pattern for little-loops
    # e.g., scripts/little_loops/foo.py -> scripts/tests/test_foo.py
    if source_path.startswith("scripts/little_loops/"):
        candidates.append(f"scripts/tests/test_{stem}.py")

    for candidate in candidates:
        if (project_root / candidate).exists() if project_root else Path(candidate).exists():
            return candidate

    return None


def scan_active_issues(
    issues_dir: Path,
    category_dirs: list[str] | None = None,
) -> list[tuple[Path, str, str, date | None]]:
    """Scan active issue directories.

    Args:
        issues_dir: Path to .issues/ directory
        category_dirs: List of category subdirectory names to scan.  When
            omitted, defaults to ``["bugs", "features", "enhancements"]`` for
            backward compatibility.  Pass ``config.issue_categories`` to
            include custom project categories.

    Returns:
        List of (path, issue_type, priority, discovered_date) tuples
    """
    results: list[tuple[Path, str, str, date | None]] = []

    for category_dir in category_dirs or ["bugs", "features", "enhancements"]:
        category_path = issues_dir / category_dir
        if not category_path.exists():
            continue

        for file_path in category_path.glob("*.md"):
            filename = file_path.name

            # Extract priority
            priority = "P5"
            priority_match = re.match(r"^(P\d)", filename)
            if priority_match:
                priority = priority_match.group(1)

            # Extract type
            issue_type = "UNKNOWN"
            type_match = re.search(r"(BUG|ENH|FEAT|EPIC)", filename)
            if type_match:
                issue_type = type_match.group(1)

            # Extract discovered date from content
            discovered_date = None
            try:
                content = file_path.read_text(encoding="utf-8")
                fm = parse_frontmatter(content)
                discovered_date = _parse_discovered_date(fm)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", file_path, e)

            results.append((file_path, issue_type, priority, discovered_date))

    return results
