# FEAT-226: Implement Sync Issues Execution Layer - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-226-sync-issues-execution-layer.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

FEAT-222 established the sync infrastructure:
- `SyncConfig` and `GitHubSyncConfig` dataclasses in `config.py:305-346`
- Configuration is already parsed during `BRConfig` initialization at `config.py:395`
- Config accessible via `config.sync` property at `config.py:432-435`
- Command spec at `commands/sync_issues.md` with detailed behavior
- Skill definition at `skills/sync-issues/SKILL.md`
- 13 configuration tests exist in `test_config.py`

### Key Discoveries
- Frontmatter parsing exists at `issue_parser.py:338-376` (key:value only, no nested structures)
- Frontmatter writing does NOT exist - needs to be implemented
- CLI pattern: argparse with subcommands, return int exit code (`cli.py:58-114`)
- Subprocess pattern: `subprocess.run([...], capture_output=True, text=True)` (`git_operations.py:178-199`)
- State persistence pattern: JSON file with `to_dict()`/`from_dict()` methods (`state.py:117-123`)
- Result dataclass pattern: `IssueProcessingResult` in `issue_manager.py:197-206`

## Desired End State

A fully functional `ll-sync` CLI tool that:
1. **Push**: Creates/updates GitHub Issues from local `.issues/` files
2. **Pull**: Creates/updates local `.issues/` files from GitHub Issues
3. **Status**: Reports sync state overview

### How to Verify
- `ll-sync status` reports accurate counts of local vs synced vs GitHub-only issues
- `ll-sync push` creates GitHub Issues and updates local frontmatter with `github_issue`, `github_url`, `last_synced`
- `ll-sync pull` creates local issue files from GitHub Issues with proper frontmatter
- All existing tests continue to pass
- New tests cover all three operations with mocked `gh` CLI

## What We're NOT Doing

- Not implementing conflict resolution (out of scope - detect conflicts, report, let user handle)
- Not implementing two-way merge (push and pull are separate directional operations)
- Not adding webhook-based real-time sync
- Not implementing bulk label management on GitHub side
- Deferring `ll-sync` CLI integration to pyproject.toml entry point to separate enhancement

## Problem Analysis

The sync command spec exists but has no execution layer. Users can configure sync settings, but when they run `/ll:sync-issues push`, nothing happens because there's no Python code to:
1. Invoke `gh` CLI commands
2. Parse GitHub API responses (JSON from `gh --json`)
3. Update issue frontmatter with sync metadata
4. Track sync state

## Solution Approach

Create `scripts/little_loops/sync.py` with:
1. `GitHubSyncManager` class - main orchestration
2. `SyncResult` / `SyncStatus` dataclasses - result tracking
3. Helper functions for frontmatter update, `gh` CLI invocation
4. Add CLI entry point `main_sync()` in `cli.py`

Follow existing patterns:
- Dataclasses with `to_dict()`/`from_dict()` (like `SprintState`)
- `subprocess.run()` for `gh` commands (like `git_operations.py`)
- Return int exit codes from CLI (like `main_auto()`)

## Implementation Phases

### Phase 1: Create Core Dataclasses and Types

#### Overview
Create the foundational data structures for sync operations.

#### Changes Required

**File**: `scripts/little_loops/sync.py` (CREATE)
**Changes**: Create new module with dataclasses

```python
"""GitHub Issues sync implementation for little-loops.

Provides bidirectional sync between local .issues/ files and GitHub Issues.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig, SyncConfig
    from little_loops.logger import Logger


@dataclass
class SyncedIssue:
    """Represents an issue's sync state."""

    local_path: Path | None = None
    issue_id: str = ""
    github_number: int | None = None
    github_url: str = ""
    last_synced: str = ""
    local_changed: bool = False
    github_changed: bool = False


@dataclass
class SyncResult:
    """Result of a sync operation."""

    action: str  # push, pull, status
    success: bool
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (issue_id, reason)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "action": self.action,
            "success": self.success,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
        }


@dataclass
class SyncStatus:
    """Sync status overview."""

    provider: str
    repo: str
    local_total: int = 0
    local_synced: int = 0
    local_unsynced: int = 0
    github_total: int = 0
    github_only: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "provider": self.provider,
            "repo": self.repo,
            "local_total": self.local_total,
            "local_synced": self.local_synced,
            "local_unsynced": self.local_unsynced,
            "github_total": self.github_total,
            "github_only": self.github_only,
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Module imports without error: `python -c "from little_loops.sync import SyncResult, SyncStatus, SyncedIssue"`
- [ ] Lint passes: `ruff check scripts/little_loops/sync.py`
- [ ] Types pass: `mypy scripts/little_loops/sync.py`

---

### Phase 2: Implement GitHub CLI Helper Functions

#### Overview
Create utility functions for invoking `gh` CLI and parsing responses.

#### Changes Required

**File**: `scripts/little_loops/sync.py`
**Changes**: Add helper functions below the dataclasses

```python
def _run_gh_command(
    args: list[str],
    logger: Logger,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command and return result.

    Args:
        args: Arguments to pass to gh CLI (e.g., ["issue", "list", "--json", "number"])
        logger: Logger for output
        check: Whether to raise on non-zero exit (default True)

    Returns:
        CompletedProcess with stdout/stderr

    Raises:
        subprocess.CalledProcessError: If command fails and check=True
    """
    cmd = ["gh"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )
    return result


def _check_gh_auth(logger: Logger) -> bool:
    """Check if gh CLI is authenticated.

    Returns:
        True if authenticated, False otherwise
    """
    try:
        result = _run_gh_command(["auth", "status"], logger, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        logger.error("gh CLI not found. Install with: brew install gh")
        return False


def _get_repo_name(logger: Logger) -> str | None:
    """Get current repository name from gh CLI.

    Returns:
        Repository name in owner/repo format, or None if not in a repo
    """
    try:
        result = _run_gh_command(
            ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            logger,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Could not get repo name: {e}")
    return None


def _parse_issue_frontmatter(content: str) -> dict[str, str | int | None]:
    """Parse frontmatter from issue file content.

    Args:
        content: Full file content

    Returns:
        Dictionary of frontmatter fields
    """
    if not content or not content.startswith("---"):
        return {}

    # Find closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}

    frontmatter_text = content[4 : 3 + end_match.start()]

    result: dict[str, str | int | None] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.lower() in ("null", "~", ""):
                result[key] = None
            elif value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    return result


def _update_issue_frontmatter(
    content: str,
    updates: dict[str, str | int],
) -> str:
    """Update or add frontmatter fields in issue content.

    Args:
        content: Full file content
        updates: Fields to add/update in frontmatter

    Returns:
        Updated content with modified frontmatter
    """
    if not content.startswith("---"):
        # No existing frontmatter, create it
        frontmatter_lines = ["---"]
        for key, value in updates.items():
            frontmatter_lines.append(f"{key}: {value}")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")
        return "\n".join(frontmatter_lines) + content

    # Find closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return content  # Malformed, return unchanged

    frontmatter_text = content[4 : 3 + end_match.start()]
    body = content[3 + end_match.end() :]

    # Parse existing frontmatter
    existing: dict[str, str | int | None] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            existing[key.strip()] = value.strip()

    # Merge updates
    existing.update(updates)

    # Rebuild frontmatter
    frontmatter_lines = ["---"]
    for key, value in existing.items():
        if value is not None:
            frontmatter_lines.append(f"{key}: {value}")
    frontmatter_lines.append("---")
    frontmatter_lines.append("")

    return "\n".join(frontmatter_lines) + body


def _parse_issue_title(content: str) -> str:
    """Extract title from issue content (after frontmatter).

    Looks for first markdown heading: # ISSUE-ID: Title

    Args:
        content: Full file content

    Returns:
        Title string or empty string if not found
    """
    # Skip frontmatter
    if content.startswith("---"):
        end_match = re.search(r"\n---\s*\n", content[3:])
        if end_match:
            content = content[3 + end_match.end() :]

    # Find first heading
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            # Remove issue ID prefix if present
            title = line[2:].strip()
            # Pattern: ISSUE-ID: Title
            if ":" in title:
                parts = title.split(":", 1)
                if re.match(r"^[A-Z]+-\d+$", parts[0].strip()):
                    return parts[1].strip()
            return title
    return ""


def _get_issue_body(content: str) -> str:
    """Extract body from issue content (after frontmatter and title).

    Args:
        content: Full file content

    Returns:
        Body content
    """
    # Skip frontmatter
    if content.startswith("---"):
        end_match = re.search(r"\n---\s*\n", content[3:])
        if end_match:
            content = content[3 + end_match.end() :]

    # Skip leading blank lines
    lines = content.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)

    # Skip title line
    if lines and lines[0].startswith("# "):
        lines.pop(0)

    return "\n".join(lines).strip()
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/sync.py`
- [ ] Types pass: `mypy scripts/little_loops/sync.py`
- [ ] Unit test for frontmatter parsing/updating passes

---

### Phase 3: Implement GitHubSyncManager Class

#### Overview
Create the main orchestration class for sync operations.

#### Changes Required

**File**: `scripts/little_loops/sync.py`
**Changes**: Add GitHubSyncManager class

```python
class GitHubSyncManager:
    """Manages bidirectional sync between local issues and GitHub Issues."""

    def __init__(
        self,
        config: BRConfig,
        logger: Logger,
    ) -> None:
        """Initialize sync manager.

        Args:
            config: Project configuration
            logger: Logger for output
        """
        self.config = config
        self.sync_config = config.sync
        self.logger = logger
        self.issues_dir = config.project_root / config.issues.base_dir

    def _get_local_issues(self) -> list[Path]:
        """Get all local issue files to sync.

        Returns:
            List of issue file paths
        """
        issues: list[Path] = []
        for category in self.config.issue_categories:
            category_dir = self.config.get_issue_dir(category)
            if category_dir.exists():
                for issue_file in category_dir.glob("*.md"):
                    issues.append(issue_file)

        # Include completed if configured
        if self.sync_config.github.sync_completed:
            completed_dir = self.config.get_completed_dir()
            if completed_dir.exists():
                for issue_file in completed_dir.glob("*.md"):
                    issues.append(issue_file)

        return issues

    def _extract_issue_id(self, filename: str) -> str:
        """Extract issue ID from filename.

        Args:
            filename: Issue filename (e.g., P1-BUG-123-description.md)

        Returns:
            Issue ID (e.g., BUG-123)
        """
        # Pattern: P[0-5]-TYPE-NNN-description.md
        match = re.search(r"(BUG|FEAT|ENH)-(\d+)", filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return ""

    def _get_labels_for_issue(self, issue_path: Path) -> list[str]:
        """Determine GitHub labels for an issue.

        Args:
            issue_path: Path to issue file

        Returns:
            List of label names
        """
        labels: list[str] = []
        filename = issue_path.name

        # Get type label from mapping
        issue_id = self._extract_issue_id(filename)
        if issue_id:
            type_prefix = issue_id.split("-")[0]
            type_label = self.sync_config.github.label_mapping.get(type_prefix)
            if type_label:
                labels.append(type_label)

        # Add priority label if configured
        if self.sync_config.github.priority_labels:
            priority_match = re.match(r"^(P[0-5])-", filename)
            if priority_match:
                labels.append(priority_match.group(1).lower())

        return labels

    def push_issues(self, issue_ids: list[str] | None = None) -> SyncResult:
        """Push local issues to GitHub.

        Args:
            issue_ids: Specific issue IDs to push, or None for all

        Returns:
            SyncResult with operation details
        """
        result = SyncResult(action="push", success=True)

        # Verify gh auth
        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        # Get repo name
        repo = self.sync_config.github.repo or _get_repo_name(self.logger)
        if not repo:
            result.success = False
            result.errors.append("Could not determine repository. Set sync.github.repo in config.")
            return result

        local_issues = self._get_local_issues()
        self.logger.info(f"Found {len(local_issues)} local issues")

        for issue_path in local_issues:
            issue_id = self._extract_issue_id(issue_path.name)
            if not issue_id:
                self.logger.debug(f"Skipping {issue_path.name}: no issue ID found")
                continue

            # Filter by issue_ids if specified
            if issue_ids and issue_id not in issue_ids:
                continue

            try:
                self._push_single_issue(issue_path, issue_id, result)
            except Exception as e:
                result.failed.append((issue_id, str(e)))
                self.logger.error(f"Failed to push {issue_id}: {e}")

        if result.failed:
            result.success = False

        return result

    def _push_single_issue(
        self,
        issue_path: Path,
        issue_id: str,
        result: SyncResult,
    ) -> None:
        """Push a single issue to GitHub.

        Args:
            issue_path: Path to local issue file
            issue_id: Issue ID (e.g., BUG-123)
            result: SyncResult to update
        """
        content = issue_path.read_text(encoding="utf-8")
        frontmatter = _parse_issue_frontmatter(content)
        title = _parse_issue_title(content)
        body = _get_issue_body(content)

        # Build full title with issue ID
        full_title = f"{issue_id}: {title}" if title else issue_id

        # Get labels
        labels = self._get_labels_for_issue(issue_path)

        github_number = frontmatter.get("github_issue")

        if github_number:
            # Update existing issue
            self._update_github_issue(int(github_number), full_title, body, issue_id, result)
        else:
            # Create new issue
            github_number = self._create_github_issue(full_title, body, labels, issue_id, result)
            if github_number:
                # Update local frontmatter
                self._update_local_frontmatter(issue_path, content, github_number)

    def _create_github_issue(
        self,
        title: str,
        body: str,
        labels: list[str],
        issue_id: str,
        result: SyncResult,
    ) -> int | None:
        """Create a new GitHub issue.

        Returns:
            GitHub issue number if successful, None otherwise
        """
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args.extend(["--label", label])

        try:
            cmd_result = _run_gh_command(args, self.logger)
            # gh issue create outputs the URL
            url = cmd_result.stdout.strip()
            # Extract issue number from URL
            match = re.search(r"/issues/(\d+)$", url)
            if match:
                issue_num = int(match.group(1))
                result.created.append(f"{issue_id} → #{issue_num}")
                self.logger.success(f"Created GitHub issue #{issue_num} for {issue_id}")
                return issue_num
        except subprocess.CalledProcessError as e:
            result.failed.append((issue_id, f"gh issue create failed: {e.stderr}"))
            self.logger.error(f"Failed to create GitHub issue for {issue_id}: {e.stderr}")
        return None

    def _update_github_issue(
        self,
        github_number: int,
        title: str,
        body: str,
        issue_id: str,
        result: SyncResult,
    ) -> None:
        """Update an existing GitHub issue."""
        args = [
            "issue", "edit", str(github_number),
            "--title", title,
            "--body", body,
        ]
        try:
            _run_gh_command(args, self.logger)
            result.updated.append(f"{issue_id} → #{github_number}")
            self.logger.success(f"Updated GitHub issue #{github_number} for {issue_id}")
        except subprocess.CalledProcessError as e:
            result.failed.append((issue_id, f"gh issue edit failed: {e.stderr}"))
            self.logger.error(f"Failed to update GitHub issue #{github_number}: {e.stderr}")

    def _update_local_frontmatter(
        self,
        issue_path: Path,
        content: str,
        github_number: int,
    ) -> None:
        """Update local issue file with GitHub sync info."""
        repo = self.sync_config.github.repo or _get_repo_name(self.logger) or ""
        github_url = f"https://github.com/{repo}/issues/{github_number}" if repo else ""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        updates = {
            "github_issue": github_number,
            "github_url": github_url,
            "last_synced": now,
        }
        updated_content = _update_issue_frontmatter(content, updates)
        issue_path.write_text(updated_content, encoding="utf-8")
        self.logger.debug(f"Updated frontmatter in {issue_path.name}")

    def pull_issues(self, labels: list[str] | None = None) -> SyncResult:
        """Pull GitHub Issues to local files.

        Args:
            labels: Filter by labels, or None for all recognized labels

        Returns:
            SyncResult with operation details
        """
        result = SyncResult(action="pull", success=True)

        # Verify gh auth
        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        # List GitHub issues
        try:
            cmd_result = _run_gh_command(
                ["issue", "list", "--json", "number,title,body,labels,state,url", "--limit", "100"],
                self.logger,
            )
            github_issues = json.loads(cmd_result.stdout)
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to list GitHub issues: {e}")
            return result

        # Get existing local issue IDs
        local_github_numbers = self._get_local_github_numbers()

        for gh_issue in github_issues:
            gh_number = gh_issue["number"]
            gh_state = gh_issue.get("state", "OPEN")

            # Skip closed issues unless configured
            if gh_state != "OPEN" and not self.sync_config.github.sync_completed:
                result.skipped.append(f"#{gh_number} (closed)")
                continue

            # Skip if already tracked locally
            if gh_number in local_github_numbers:
                result.skipped.append(f"#{gh_number} (already tracked)")
                continue

            # Check if has recognized labels
            gh_labels = [lbl.get("name", "") for lbl in gh_issue.get("labels", [])]
            issue_type = self._determine_issue_type(gh_labels)
            if not issue_type:
                result.skipped.append(f"#{gh_number} (no recognized type label)")
                continue

            try:
                self._create_local_issue(gh_issue, issue_type, result)
            except Exception as e:
                result.failed.append((f"#{gh_number}", str(e)))

        if result.failed:
            result.success = False

        return result

    def _get_local_github_numbers(self) -> set[int]:
        """Get set of GitHub issue numbers tracked locally."""
        numbers: set[int] = set()
        for issue_path in self._get_local_issues():
            content = issue_path.read_text(encoding="utf-8")
            frontmatter = _parse_issue_frontmatter(content)
            gh_num = frontmatter.get("github_issue")
            if gh_num is not None:
                numbers.add(int(gh_num))
        return numbers

    def _determine_issue_type(self, labels: list[str]) -> str | None:
        """Determine issue type from GitHub labels.

        Returns:
            Issue type prefix (BUG, FEAT, ENH) or None
        """
        # Reverse lookup from label_mapping
        reverse_map: dict[str, str] = {}
        for type_prefix, label in self.sync_config.github.label_mapping.items():
            if label not in reverse_map:
                reverse_map[label] = type_prefix

        for label in labels:
            if label in reverse_map:
                return reverse_map[label]
        return None

    def _create_local_issue(
        self,
        gh_issue: dict,
        issue_type: str,
        result: SyncResult,
    ) -> None:
        """Create a local issue file from GitHub issue."""
        gh_number = gh_issue["number"]
        gh_title = gh_issue.get("title", f"Issue #{gh_number}")
        gh_body = gh_issue.get("body", "")
        gh_url = gh_issue.get("url", "")
        gh_labels = [lbl.get("name", "") for lbl in gh_issue.get("labels", [])]

        # Determine priority from labels or default
        priority = "P3"
        for label in gh_labels:
            if re.match(r"^p[0-5]$", label, re.IGNORECASE):
                priority = label.upper()
                break

        # Generate next issue number
        next_num = self._get_next_issue_number(issue_type)

        # Generate slug from title
        slug = re.sub(r"[^a-z0-9]+", "-", gh_title.lower())[:40].strip("-")

        issue_id = f"{issue_type}-{next_num}"
        filename = f"{priority}-{issue_id}-{slug}.md"

        # Determine category directory
        category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
        category = category_map.get(issue_type, "features")
        category_dir = self.config.get_issue_dir(category)
        category_dir.mkdir(parents=True, exist_ok=True)

        issue_path = category_dir / filename

        # Build content
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        content = f"""---
github_issue: {gh_number}
github_url: {gh_url}
last_synced: {now}
discovered_by: github_sync
---

# {issue_id}: {gh_title}

{gh_body}

## Labels

{', '.join(f'`{lbl}`' for lbl in gh_labels)}
"""
        issue_path.write_text(content, encoding="utf-8")
        result.created.append(f"#{gh_number} → {issue_id}")
        self.logger.success(f"Created {filename} from GitHub #{gh_number}")

    def _get_next_issue_number(self, issue_type: str) -> int:
        """Get next available issue number for type."""
        max_num = 0
        pattern = re.compile(rf"{issue_type}-(\d+)")

        for issue_path in self._get_local_issues():
            match = pattern.search(issue_path.name)
            if match:
                max_num = max(max_num, int(match.group(1)))

        return max_num + 1

    def get_status(self) -> SyncStatus:
        """Get sync status overview.

        Returns:
            SyncStatus with counts
        """
        repo = self.sync_config.github.repo or _get_repo_name(self.logger) or "unknown"

        status = SyncStatus(
            provider=self.sync_config.provider,
            repo=repo,
        )

        # Count local issues
        local_issues = self._get_local_issues()
        status.local_total = len(local_issues)

        # Count synced (have github_issue)
        local_github_numbers = self._get_local_github_numbers()
        status.local_synced = len(local_github_numbers)
        status.local_unsynced = status.local_total - status.local_synced

        # Count GitHub issues
        if _check_gh_auth(self.logger):
            try:
                cmd_result = _run_gh_command(
                    ["issue", "list", "--json", "number", "--limit", "500"],
                    self.logger,
                )
                github_issues = json.loads(cmd_result.stdout)
                status.github_total = len(github_issues)

                github_numbers = {issue["number"] for issue in github_issues}
                status.github_only = len(github_numbers - local_github_numbers)
            except Exception:
                pass

        return status
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/sync.py`
- [ ] Types pass: `mypy scripts/little_loops/sync.py`
- [ ] Module imports: `python -c "from little_loops.sync import GitHubSyncManager"`

---

### Phase 4: Add CLI Entry Point

#### Overview
Add `main_sync()` entry point to `cli.py`.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add main_sync function at end of file, add import

Add import near top after other imports:
```python
from little_loops.sync import GitHubSyncManager
```

Add function at end before any `if __name__` block:
```python
def main_sync() -> int:
    """Entry point for ll-sync command.

    Sync local issues with GitHub Issues.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-sync",
        description="Sync local .issues/ files with GitHub Issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status             # Show sync status
  %(prog)s push               # Push all local issues to GitHub
  %(prog)s push BUG-123       # Push specific issue
  %(prog)s pull               # Pull GitHub Issues to local
""",
    )

    subparsers = parser.add_subparsers(dest="action", help="Sync action")

    # Status subcommand
    subparsers.add_parser("status", help="Show sync status")

    # Push subcommand
    push_parser = subparsers.add_parser("push", help="Push local issues to GitHub")
    push_parser.add_argument(
        "issue_ids",
        nargs="*",
        help="Specific issue IDs to push (e.g., BUG-123)",
    )

    # Pull subcommand
    pull_parser = subparsers.add_parser("pull", help="Pull GitHub Issues to local")
    pull_parser.add_argument(
        "--labels",
        "-l",
        type=str,
        help="Filter by labels (comma-separated)",
    )

    # Common args
    add_config_arg(parser)
    add_quiet_arg(parser)

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    project_root = args.config or Path.cwd()
    config = BRConfig(project_root)
    logger = Logger(quiet=getattr(args, "quiet", False))

    # Check sync is enabled
    if not config.sync.enabled:
        logger.error("Sync is not enabled. Add to .claude/ll-config.json:")
        logger.error('  "sync": { "enabled": true }')
        return 1

    manager = GitHubSyncManager(config, logger)

    if args.action == "status":
        status = manager.get_status()
        _print_sync_status(status, logger)
        return 0

    elif args.action == "push":
        issue_ids = args.issue_ids if args.issue_ids else None
        result = manager.push_issues(issue_ids)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    elif args.action == "pull":
        labels = args.labels.split(",") if args.labels else None
        result = manager.pull_issues(labels)
        _print_sync_result(result, logger)
        return 0 if result.success else 1

    return 1


def _print_sync_status(status: SyncStatus, logger: Logger) -> None:
    """Print sync status in formatted output."""
    logger.info("=" * 80)
    logger.info("SYNC STATUS")
    logger.info("=" * 80)
    logger.info(f"Provider: {status.provider}")
    logger.info(f"Repository: {status.repo}")
    logger.info("")
    logger.info(f"Local Issues:     {status.local_total}")
    logger.info(f"Synced to GitHub: {status.local_synced}")
    logger.info(f"GitHub Issues:    {status.github_total}")
    logger.info("")
    logger.info(f"Unsynced local:   {status.local_unsynced}  (local only, not on GitHub)")
    logger.info(f"GitHub-only:      {status.github_only}  (on GitHub, not local)")
    logger.info("=" * 80)


def _print_sync_result(result: SyncResult, logger: Logger) -> None:
    """Print sync result in formatted output."""
    logger.info("=" * 80)
    logger.info(f"SYNC {result.action.upper()} {'COMPLETE' if result.success else 'FAILED'}")
    logger.info("=" * 80)
    logger.info("")
    logger.info("## SUMMARY")
    logger.info(f"- Created: {len(result.created)}")
    logger.info(f"- Updated: {len(result.updated)}")
    logger.info(f"- Skipped: {len(result.skipped)}")
    logger.info(f"- Failed:  {len(result.failed)}")
    logger.info("")
    if result.created:
        logger.info("## CREATED")
        for item in result.created:
            logger.info(f"  - {item}")
        logger.info("")
    if result.updated:
        logger.info("## UPDATED")
        for item in result.updated:
            logger.info(f"  - {item}")
        logger.info("")
    if result.failed:
        logger.info("## FAILED")
        for issue_id, reason in result.failed:
            logger.error(f"  - {issue_id}: {reason}")
        logger.info("")
    if result.errors:
        logger.info("## ERRORS")
        for error in result.errors:
            logger.error(f"  - {error}")
    logger.info("=" * 80)
```

**File**: `scripts/pyproject.toml`
**Changes**: Add ll-sync entry point

```toml
# In [project.scripts] section, add:
ll-sync = "little_loops.cli:main_sync"
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `mypy scripts/little_loops/cli.py`
- [ ] Entry point works: `python -c "from little_loops.cli import main_sync"`

---

### Phase 5: Write Tests

#### Overview
Create comprehensive tests for sync functionality.

#### Changes Required

**File**: `scripts/tests/test_sync.py` (CREATE)
**Changes**: Create test file

```python
"""Tests for GitHub Issues sync functionality."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.sync import (
    GitHubSyncManager,
    SyncResult,
    SyncStatus,
    _check_gh_auth,
    _get_issue_body,
    _get_repo_name,
    _parse_issue_frontmatter,
    _parse_issue_title,
    _update_issue_frontmatter,
)


class TestSyncDataclasses:
    """Tests for sync dataclasses."""

    def test_sync_result_to_dict(self) -> None:
        """SyncResult converts to dictionary correctly."""
        result = SyncResult(
            action="push",
            success=True,
            created=["BUG-1 → #1"],
            updated=["BUG-2 → #2"],
        )
        d = result.to_dict()
        assert d["action"] == "push"
        assert d["success"] is True
        assert d["created"] == ["BUG-1 → #1"]

    def test_sync_status_to_dict(self) -> None:
        """SyncStatus converts to dictionary correctly."""
        status = SyncStatus(
            provider="github",
            repo="owner/repo",
            local_total=10,
            local_synced=5,
        )
        d = status.to_dict()
        assert d["provider"] == "github"
        assert d["local_total"] == 10


class TestFrontmatterParsing:
    """Tests for frontmatter parsing utilities."""

    def test_parse_empty_content(self) -> None:
        """Empty content returns empty dict."""
        assert _parse_issue_frontmatter("") == {}

    def test_parse_no_frontmatter(self) -> None:
        """Content without frontmatter returns empty dict."""
        assert _parse_issue_frontmatter("# Title\n\nBody") == {}

    def test_parse_simple_frontmatter(self) -> None:
        """Simple key:value frontmatter is parsed."""
        content = """---
github_issue: 123
github_url: https://example.com
---

# Title
"""
        result = _parse_issue_frontmatter(content)
        assert result["github_issue"] == 123
        assert result["github_url"] == "https://example.com"

    def test_parse_null_values(self) -> None:
        """Null and empty values are handled."""
        content = """---
field1: null
field2: ~
field3:
---
"""
        result = _parse_issue_frontmatter(content)
        assert result["field1"] is None
        assert result["field2"] is None
        assert result["field3"] is None

    def test_update_existing_frontmatter(self) -> None:
        """Updates are merged into existing frontmatter."""
        content = """---
existing: value
---

# Title
"""
        updates = {"github_issue": 42}
        result = _update_issue_frontmatter(content, updates)

        assert "existing: value" in result
        assert "github_issue: 42" in result
        assert "# Title" in result

    def test_update_creates_frontmatter(self) -> None:
        """Frontmatter is created if missing."""
        content = "# Title\n\nBody"
        updates = {"github_issue": 42}
        result = _update_issue_frontmatter(content, updates)

        assert result.startswith("---")
        assert "github_issue: 42" in result
        assert "# Title" in result


class TestTitleParsing:
    """Tests for title parsing."""

    def test_parse_title_with_issue_id(self) -> None:
        """Title with issue ID prefix is parsed correctly."""
        content = """---
key: value
---

# BUG-123: Fix the bug
"""
        assert _parse_issue_title(content) == "Fix the bug"

    def test_parse_title_without_issue_id(self) -> None:
        """Title without issue ID is returned as-is."""
        content = "# Simple Title\n"
        assert _parse_issue_title(content) == "Simple Title"


class TestBodyParsing:
    """Tests for body extraction."""

    def test_get_body_skips_frontmatter_and_title(self) -> None:
        """Body extraction skips frontmatter and title."""
        content = """---
key: value
---

# BUG-123: Title

This is the body.
"""
        body = _get_issue_body(content)
        assert body == "This is the body."


class TestGitHubHelpers:
    """Tests for GitHub CLI helper functions."""

    def test_check_gh_auth_success(self) -> None:
        """Returns True when gh auth status succeeds."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            assert _check_gh_auth(mock_logger) is True

    def test_check_gh_auth_failure(self) -> None:
        """Returns False when gh auth status fails."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=""
            )
            assert _check_gh_auth(mock_logger) is False

    def test_check_gh_auth_not_installed(self) -> None:
        """Returns False when gh is not installed."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert _check_gh_auth(mock_logger) is False

    def test_get_repo_name_success(self) -> None:
        """Returns repo name when gh repo view succeeds."""
        mock_logger = MagicMock(spec=Logger)
        with patch("little_loops.sync._run_gh_command") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="owner/repo\n", stderr=""
            )
            assert _get_repo_name(mock_logger) == "owner/repo"


class TestGitHubSyncManager:
    """Tests for GitHubSyncManager."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> BRConfig:
        """Create a mock BRConfig with test directories."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "ll-config.json"
        config_file.write_text(json.dumps({
            "sync": {
                "enabled": True,
                "github": {
                    "repo": "test/repo",
                    "label_mapping": {"BUG": "bug", "FEAT": "enhancement"},
                },
            },
            "issues": {
                "base_dir": ".issues",
                "categories": ["bugs", "features"],
            },
        }))

        # Create issue directories
        issues_dir = tmp_path / ".issues"
        (issues_dir / "bugs").mkdir(parents=True)
        (issues_dir / "features").mkdir(parents=True)
        (issues_dir / "completed").mkdir(parents=True)

        return BRConfig(tmp_path)

    @pytest.fixture
    def mock_logger(self) -> MagicMock:
        """Create a mock logger."""
        return MagicMock(spec=Logger)

    def test_extract_issue_id(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Issue ID is extracted from filename."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        assert manager._extract_issue_id("P1-BUG-123-description.md") == "BUG-123"
        assert manager._extract_issue_id("P2-FEAT-42-new-feature.md") == "FEAT-42"
        assert manager._extract_issue_id("invalid.md") == ""

    def test_get_labels_for_issue(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Labels are generated from issue type and priority."""
        manager = GitHubSyncManager(mock_config, mock_logger)
        issue_path = tmp_path / ".issues" / "bugs" / "P1-BUG-123-test.md"
        issue_path.write_text("# BUG-123: Test")

        labels = manager._get_labels_for_issue(issue_path)
        assert "bug" in labels
        assert "p1" in labels

    def test_push_checks_auth(
        self, mock_config: BRConfig, mock_logger: MagicMock
    ) -> None:
        """Push returns error if gh is not authenticated."""
        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = False
            result = manager.push_issues()

        assert not result.success
        assert "not authenticated" in result.errors[0]

    def test_get_status(
        self, mock_config: BRConfig, mock_logger: MagicMock, tmp_path: Path
    ) -> None:
        """Status counts local and GitHub issues."""
        # Create a local issue
        issue_file = tmp_path / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue_file.write_text("""---
github_issue: 1
---

# BUG-001: Test
""")

        manager = GitHubSyncManager(mock_config, mock_logger)

        with patch("little_loops.sync._check_gh_auth") as mock_auth:
            mock_auth.return_value = True
            with patch("little_loops.sync._run_gh_command") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout='[{"number": 1}, {"number": 2}]',
                    stderr=""
                )
                status = manager.get_status()

        assert status.local_total == 1
        assert status.local_synced == 1
        assert status.github_total == 2
        assert status.github_only == 1  # Issue #2 is not tracked locally
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_sync.py`
- [ ] Types pass: `mypy scripts/tests/test_sync.py`

---

### Phase 6: Update Module Exports

#### Overview
Export sync classes from `__init__.py`.

#### Changes Required

**File**: `scripts/little_loops/__init__.py`
**Changes**: Add sync exports

Add import:
```python
from little_loops.sync import GitHubSyncManager, SyncResult, SyncStatus
```

Add to `__all__`:
```python
    # sync
    "GitHubSyncManager",
    "SyncResult",
    "SyncStatus",
```

#### Success Criteria

**Automated Verification**:
- [ ] Exports work: `python -c "from little_loops import GitHubSyncManager, SyncResult, SyncStatus"`
- [ ] Lint passes: `ruff check scripts/little_loops/__init__.py`

---

## Testing Strategy

### Unit Tests
- Dataclass serialization (`to_dict`)
- Frontmatter parsing (empty, valid, null values)
- Frontmatter updating (existing, create new)
- Title/body extraction
- Issue ID extraction from filename
- Label generation from type/priority

### Integration Tests (mocked gh CLI)
- Push single issue (create new)
- Push single issue (update existing)
- Push returns error on auth failure
- Pull creates local files
- Pull skips already tracked issues
- Status counts correctly

## References

- Original issue: `.issues/features/P2-FEAT-226-sync-issues-execution-layer.md`
- Predecessor: `.issues/completed/P3-FEAT-222-sync-issues-with-github.md`
- Config dataclasses: `scripts/little_loops/config.py:305-346`
- CLI pattern: `scripts/little_loops/cli.py:58-114`
- Frontmatter parsing: `scripts/little_loops/issue_parser.py:338-376`
- Command spec: `commands/sync_issues.md`
