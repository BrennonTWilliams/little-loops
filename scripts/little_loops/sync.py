"""GitHub Issues sync implementation for little-loops.

Provides bidirectional sync between local .issues/ files and GitHub Issues.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.issue_parser import get_next_issue_number

if TYPE_CHECKING:
    from little_loops.config import BRConfig
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

    def to_dict(self) -> dict[str, Any]:
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

    def to_dict(self) -> dict[str, Any]:
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


# =============================================================================
# Helper Functions
# =============================================================================


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

    # Parse existing frontmatter preserving as strings
    existing: dict[str, str] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            existing[key.strip()] = value.strip()

    # Merge updates (convert int to str for consistency)
    for key, value in updates.items():
        existing[key] = str(value)

    # Rebuild frontmatter
    frontmatter_lines = ["---"]
    for key, value in existing.items():
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


# =============================================================================
# GitHubSyncManager Class
# =============================================================================


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
            new_number = self._create_github_issue(full_title, body, labels, issue_id, result)
            if new_number:
                # Update local frontmatter
                self._update_local_frontmatter(issue_path, content, new_number)

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
            "issue",
            "edit",
            str(github_number),
            "--title",
            title,
            "--body",
            body,
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
        now = datetime.now(UTC).isoformat(timespec="seconds")

        updates: dict[str, str | int] = {
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
            gh_args = ["issue", "list", "--json", "number,title,body,labels,state,url", "--limit", "100"]
            if labels:
                for label in labels:
                    gh_args.extend(["--label", label])
            cmd_result = _run_gh_command(gh_args, self.logger)
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
        gh_issue: dict[str, Any],
        issue_type: str,
        result: SyncResult,
    ) -> None:
        """Create a local issue file from GitHub issue."""
        gh_number = gh_issue["number"]
        gh_title = gh_issue.get("title", f"Issue #{gh_number}")
        gh_body = gh_issue.get("body", "") or ""
        gh_url = gh_issue.get("url", "")
        gh_labels = [lbl.get("name", "") for lbl in gh_issue.get("labels", [])]

        # Determine priority from labels or default
        priority = "P3"
        for label in gh_labels:
            if re.match(r"^p[0-5]$", label, re.IGNORECASE):
                priority = label.upper()
                break

        # Generate next issue number (uses global numbering across all dirs)
        next_num = get_next_issue_number(self.config)

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
        now = datetime.now(UTC).isoformat(timespec="seconds")
        labels_str = ", ".join(f"`{lbl}`" for lbl in gh_labels) if gh_labels else ""
        content = f"""---
github_issue: {gh_number}
github_url: {gh_url}
last_synced: {now}
discovered_by: github_sync
---

# {issue_id}: {gh_title}

{gh_body}

## Labels

{labels_str}
"""
        issue_path.write_text(content, encoding="utf-8")
        result.created.append(f"#{gh_number} → {issue_id}")
        self.logger.success(f"Created {filename} from GitHub #{gh_number}")

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
