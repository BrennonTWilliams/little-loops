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
    try:
        result = subprocess.run(
            ["git", "log", "--format=%as", "-1", "--", str(file_path)],
            capture_output=True,
            text=True,
            cwd=file_path.parent,
        )
        if result.returncode == 0 and result.stdout.strip():
            return date.fromisoformat(result.stdout.strip())
    except (OSError, ValueError):
        pass
    return None


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

    return issues


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
