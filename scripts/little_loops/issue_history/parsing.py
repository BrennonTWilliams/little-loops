"""Issue history parsing and scanning functions.

Provides functions to parse completed issue files, extract metadata
from frontmatter and content, scan directories for issues, and
extract file paths from issue content.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from little_loops.frontmatter import parse_frontmatter
from little_loops.issue_history.models import CompletedIssue


def parse_completed_issue(file_path: Path) -> CompletedIssue:
    """Parse a completed issue file.

    Args:
        file_path: Path to the issue markdown file

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
    type_match = re.search(r"(BUG|ENH|FEAT)-(\d+)", filename)
    if type_match:
        issue_type = type_match.group(1)
        issue_id = f"{type_match.group(1)}-{type_match.group(2)}"

    # Parse frontmatter for discovered_by and discovered_date
    discovered_by = _parse_discovered_by(content)
    discovered_date = _parse_discovered_date(content)

    # Parse completion date from Resolution section or file mtime
    completed_date = _parse_completion_date(content, file_path)

    return CompletedIssue(
        path=file_path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        discovered_by=discovered_by,
        discovered_date=discovered_date,
        completed_date=completed_date,
    )


def _parse_discovered_by(content: str) -> str | None:
    """Extract discovered_by from YAML frontmatter.

    Args:
        content: File content

    Returns:
        discovered_by value or None
    """
    fm = parse_frontmatter(content)
    value = fm.get("discovered_by")
    return value if isinstance(value, str) else None


def _parse_completion_date(content: str, file_path: Path) -> date | None:
    """Extract completion date from Resolution section or file mtime.

    Args:
        content: File content
        file_path: Path for mtime fallback

    Returns:
        Completion date or None
    """
    # Try Resolution section: **Completed**: YYYY-MM-DD
    match = re.search(r"\*\*Completed\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    # Fallback to file mtime
    try:
        mtime = file_path.stat().st_mtime
        return date.fromtimestamp(mtime)
    except OSError:
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


def scan_completed_issues(completed_dir: Path) -> list[CompletedIssue]:
    """Scan completed directory for issue files.

    Args:
        completed_dir: Path to .issues/completed/

    Returns:
        List of parsed CompletedIssue objects
    """
    issues: list[CompletedIssue] = []

    if not completed_dir.exists():
        return issues

    for file_path in sorted(completed_dir.glob("*.md")):
        try:
            issue = parse_completed_issue(file_path)
            issues.append(issue)
        except Exception:
            # Skip unparseable files
            continue

    return issues


def _parse_discovered_date(content: str) -> date | None:
    """Extract discovered_date from YAML frontmatter.

    Args:
        content: File content

    Returns:
        discovered_date value or None
    """
    fm = parse_frontmatter(content)
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

    Args:
        content: Issue file content

    Returns:
        List of file paths found in content
    """
    patterns = [
        r"\*\*File\*\*:\s*`?([^`\n:]+)`?",  # **File**: path/to/file.py
        r"`([a-zA-Z_][\w/.-]+\.[a-z]{2,4})`",  # `path/to/file.py`
        r"(?:^|\s)([a-zA-Z_][\w/.-]+\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",  # path.py:123
    ]

    paths: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            path = match.group(1).strip()
            # Must look like a file path
            if "/" in path or path.endswith((".py", ".md", ".js", ".ts", ".json", ".yaml", ".yml")):
                # Normalize: remove line numbers (path.py:123 -> path.py)
                if ":" in path and path.split(":")[-1].isdigit():
                    path = ":".join(path.split(":")[:-1])
                paths.add(path)

    return sorted(paths)


def _find_test_file(source_path: str) -> str | None:
    """Find corresponding test file for a source file.

    Checks common test file naming patterns:
    - tests/test_<name>.py
    - tests/<path>/test_<name>.py
    - <path>/test_<name>.py
    - <path>/<name>_test.py
    - <path>/tests/test_<name>.py

    Args:
        source_path: Path to source file (e.g., "src/core/processor.py")

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
        if Path(candidate).exists():
            return candidate

    return None


def scan_active_issues(issues_dir: Path) -> list[tuple[Path, str, str, date | None]]:
    """Scan active issue directories.

    Args:
        issues_dir: Path to .issues/ directory

    Returns:
        List of (path, issue_type, priority, discovered_date) tuples
    """
    results: list[tuple[Path, str, str, date | None]] = []

    for category_dir in ["bugs", "features", "enhancements"]:
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
            type_match = re.search(r"(BUG|ENH|FEAT)", filename)
            if type_match:
                issue_type = type_match.group(1)

            # Extract discovered date from content
            discovered_date = None
            try:
                content = file_path.read_text(encoding="utf-8")
                discovered_date = _parse_discovered_date(content)
            except Exception:
                pass

            results.append((file_path, issue_type, priority, discovered_date))

    return results
