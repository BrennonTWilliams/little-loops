"""GitHub Issues sync implementation for little-loops.

Provides bidirectional sync between local .issues/ files and GitHub Issues.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from little_loops.frontmatter import parse_frontmatter, strip_frontmatter
from little_loops.issue_parser import get_next_issue_number
from little_loops.issue_template import assemble_issue_markdown, load_issue_sections

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
    github_error: str | None = None

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
            "github_error": self.github_error,
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
    fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        # No existing frontmatter, create it
        fm_text = yaml.dump(dict(updates), default_flow_style=False, sort_keys=False).strip()
        return f"---\n{fm_text}\n---\n{content}"

    existing: dict[str, Any] = yaml.safe_load(fm_match.group(1)) or {}
    existing.update(updates)
    fm_text = yaml.dump(existing, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{fm_text}\n---{content[fm_match.end() :]}"


def _parse_issue_title(content: str) -> str:
    """Extract title from issue content (after frontmatter).

    Looks for first markdown heading: # ISSUE-ID: Title

    Args:
        content: Full file content

    Returns:
        Title string or empty string if not found
    """
    content = strip_frontmatter(content)

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
    content = strip_frontmatter(content)

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
        dry_run: bool = False,
    ) -> None:
        """Initialize sync manager.

        Args:
            config: Project configuration
            logger: Logger for output
            dry_run: If True, show what would be done without making changes
        """
        self.config = config
        self.sync_config = config.sync
        self.logger = logger
        self.dry_run = dry_run
        self.issues_dir = config.project_root / config.issues.base_dir
        self._sections_data: dict[str, dict[str, Any]] = {}

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
        frontmatter = parse_frontmatter(content, coerce_types=True)
        title = _parse_issue_title(content)
        body = _get_issue_body(content)

        # Build full title with issue ID
        full_title = f"{issue_id}: {title}" if title else issue_id

        # Get labels
        labels = self._get_labels_for_issue(issue_path)

        github_number = frontmatter.get("github_issue")

        if self.dry_run:
            if github_number:
                result.updated.append(f"{issue_id} → #{github_number} (would update)")
                self.logger.info(f"Would update GitHub issue #{github_number} for {issue_id}")
            else:
                result.created.append(f"{issue_id} (would create)")
                self.logger.info(f"Would create GitHub issue for {issue_id}")
            return

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
            gh_args = [
                "issue",
                "list",
                "--json",
                "number,title,body,labels,state,url",
                "--limit",
                "100",
            ]
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

            if self.dry_run:
                gh_title = gh_issue.get("title", f"Issue #{gh_number}")
                result.created.append(f"#{gh_number}: {gh_title} (would create as {issue_type})")
                self.logger.info(f"Would create local issue from GitHub #{gh_number}: {gh_title}")
            else:
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
            frontmatter = parse_frontmatter(content, coerce_types=True)
            gh_num = frontmatter.get("github_issue")
            if gh_num is not None:
                try:
                    numbers.add(int(gh_num))
                except (ValueError, TypeError):
                    self.logger.warning(
                        f"Malformed github_issue value in {issue_path.name}: {gh_num!r}"
                    )
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
        cat = self.config.issues.get_category_by_prefix(issue_type)
        category = cat.dir if cat else "features"
        category_dir = self.config.get_issue_dir(category)
        category_dir.mkdir(parents=True, exist_ok=True)

        issue_path = category_dir / filename

        # Build content using per-type sections template
        now = datetime.now(UTC).isoformat(timespec="seconds")
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        if issue_type not in self._sections_data:
            templates_dir = (
                Path(self.config.issues.templates_dir) if self.config.issues.templates_dir else None
            )
            self._sections_data[issue_type] = load_issue_sections(issue_type, templates_dir)

        frontmatter = {
            "github_issue": gh_number,
            "github_url": gh_url,
            "last_synced": now,
            "discovered_by": "github_sync",
            "discovered_date": today,
        }
        section_content: dict[str, str] = {}
        if gh_body:
            section_content["Summary"] = gh_body
        section_content["Impact"] = (
            f"- **Priority**: {priority}\n"
            f"- **Effort**: Unknown\n"
            f"- **Risk**: Unknown\n"
            f"- **Breaking Change**: Unknown"
        )
        section_content["Status"] = f"**Open** | Created: {today} | Priority: {priority}"

        labels_str = ", ".join(f"`{lbl}`" for lbl in gh_labels) if gh_labels else ""
        if labels_str:
            section_content["Labels"] = labels_str

        variant = self.sync_config.github.pull_template
        content = assemble_issue_markdown(
            sections_data=self._sections_data[issue_type],
            issue_type=issue_type,
            variant=variant,
            issue_id=issue_id,
            title=gh_title,
            frontmatter=frontmatter,
            content=section_content,
            labels=gh_labels,
        )
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
            except Exception as e:
                status.github_error = f"Failed to query GitHub: {e}"
                self.logger.warning(status.github_error)

        return status

    def _find_local_issue(self, issue_id: str) -> Path | None:
        """Find the local file matching an issue ID.

        Searches active category directories and completed directory.

        Args:
            issue_id: Issue ID to find (e.g., BUG-123)

        Returns:
            Path to the issue file, or None if not found
        """
        for issue_path in self._get_local_issues():
            if self._extract_issue_id(issue_path.name) == issue_id:
                return issue_path
        # Also check completed directory
        completed_dir = self.config.get_completed_dir()
        if completed_dir.exists():
            for issue_file in completed_dir.glob("*.md"):
                if self._extract_issue_id(issue_file.name) == issue_id:
                    return issue_file
        return None

    def diff_issue(self, issue_id: str) -> SyncResult:
        """Show content differences between a local issue and its GitHub counterpart.

        Args:
            issue_id: Issue ID to diff (e.g., BUG-123)

        Returns:
            SyncResult with diff information
        """
        result = SyncResult(action="diff", success=True)

        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        issue_path = self._find_local_issue(issue_id)
        if not issue_path:
            result.success = False
            result.errors.append(f"Local issue {issue_id} not found")
            return result

        content = issue_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content, coerce_types=True)
        github_number = frontmatter.get("github_issue")

        if github_number is None:
            result.success = False
            result.errors.append(
                f"{issue_id} is not synced to GitHub (no github_issue in frontmatter)"
            )
            return result

        try:
            cmd_result = _run_gh_command(
                ["issue", "view", str(int(github_number)), "--json", "body", "-q", ".body"],
                self.logger,
            )
            github_body = cmd_result.stdout.rstrip("\n")
        except subprocess.CalledProcessError as e:
            result.success = False
            result.errors.append(f"Failed to fetch GitHub issue #{github_number}: {e.stderr}")
            return result

        local_body = _get_issue_body(content)

        local_lines = local_body.splitlines(keepends=True)
        github_lines = github_body.splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                github_lines,
                local_lines,
                fromfile=f"github:#{github_number}",
                tofile=f"local:{issue_id}",
            )
        )

        if diff:
            result.updated.append(f"{issue_id} (#{github_number}): differs")
            # Store diff lines in created field for display
            result.created = [line.rstrip("\n") for line in diff]
        else:
            result.skipped.append(f"{issue_id} (#{github_number}): in sync")

        return result

    def diff_all(self) -> SyncResult:
        """Show summary of differences between all synced local issues and GitHub.

        Returns:
            SyncResult with diff summary
        """
        result = SyncResult(action="diff", success=True)

        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        local_issues = self._get_local_issues()

        # First pass: collect all issues that have been synced to GitHub
        synced: list[tuple[str, int, str]] = []  # (issue_id, github_number, content)
        for issue_path in local_issues:
            issue_id = self._extract_issue_id(issue_path.name)
            if not issue_id:
                continue

            content = issue_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content, coerce_types=True)
            github_number = frontmatter.get("github_issue")

            if github_number is None:
                continue

            synced.append((issue_id, int(github_number), content))

        if not synced:
            return result

        # Batch-fetch all GitHub issue bodies in a single API call
        try:
            cmd_result = _run_gh_command(
                ["issue", "list", "--json", "number,body", "--limit", "500", "--state", "all"],
                self.logger,
            )
            github_bodies: dict[int, str] = {
                item["number"]: item["body"] for item in json.loads(cmd_result.stdout)
            }
        except subprocess.CalledProcessError as e:
            result.success = False
            result.errors.append(f"Failed to batch-fetch GitHub issues: {e.stderr}")
            return result
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to batch-fetch GitHub issues: {e}")
            return result

        # Compare local vs GitHub bodies using the batch-fetched data
        for issue_id, github_number, content in synced:
            if github_number not in github_bodies:
                result.failed.append((issue_id, f"Issue #{github_number} not found in GitHub"))
                continue

            local_body = _get_issue_body(content)
            github_body = github_bodies[github_number]

            if local_body.strip() != github_body.strip():
                result.updated.append(f"{issue_id} (#{github_number}): differs")
            else:
                result.skipped.append(f"{issue_id} (#{github_number}): in sync")

        if result.failed:
            result.success = False

        return result

    def close_issues(
        self,
        issue_ids: list[str] | None = None,
        all_completed: bool = False,
    ) -> SyncResult:
        """Close GitHub issues for completed local issues.

        Args:
            issue_ids: Specific issue IDs to close, or None
            all_completed: If True, close all GitHub issues whose local counterparts
                          are in the completed directory

        Returns:
            SyncResult with operation details
        """
        result = SyncResult(action="close", success=True)

        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        files_to_close: list[tuple[Path, str]] = []  # (path, issue_id)

        if all_completed:
            completed_dir = self.config.get_completed_dir()
            if completed_dir.exists():
                for issue_file in completed_dir.glob("*.md"):
                    eid = self._extract_issue_id(issue_file.name)
                    if eid:
                        files_to_close.append((issue_file, eid))
        elif issue_ids:
            for eid in issue_ids:
                issue_path = self._find_local_issue(eid)
                if issue_path:
                    files_to_close.append((issue_path, eid))
                else:
                    result.failed.append((eid, "Local issue not found"))
        else:
            result.success = False
            result.errors.append("Specify issue IDs or use --all-completed")
            return result

        for issue_path, issue_id in files_to_close:
            content = issue_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content, coerce_types=True)
            github_number = frontmatter.get("github_issue")

            if github_number is None:
                result.skipped.append(f"{issue_id} (not synced to GitHub)")
                continue

            if self.dry_run:
                result.updated.append(f"{issue_id} → #{github_number} (would close)")
                self.logger.info(f"Would close GitHub issue #{github_number} for {issue_id}")
                continue

            try:
                _run_gh_command(
                    [
                        "issue",
                        "close",
                        str(int(github_number)),
                        "--comment",
                        f"Closed via ll-sync. Issue {issue_id} completed locally.",
                    ],
                    self.logger,
                )
                result.updated.append(f"{issue_id} → #{github_number} (closed)")
                self.logger.success(f"Closed GitHub issue #{github_number} for {issue_id}")
            except subprocess.CalledProcessError as e:
                result.failed.append((issue_id, f"gh issue close failed: {e.stderr}"))
                self.logger.error(f"Failed to close GitHub issue #{github_number}: {e.stderr}")

        if result.failed:
            result.success = False

        return result

    def reopen_issues(
        self,
        issue_ids: list[str] | None = None,
        all_reopened: bool = False,
    ) -> SyncResult:
        """Reopen GitHub issues for locally-active issues.

        Args:
            issue_ids: Specific issue IDs to reopen, or None
            all_reopened: If True, reopen GitHub issues for all local issues in active
                          directories that are CLOSED on GitHub

        Returns:
            SyncResult with operation details
        """
        result = SyncResult(action="reopen", success=True)

        if not _check_gh_auth(self.logger):
            result.success = False
            result.errors.append("GitHub CLI not authenticated. Run: gh auth login")
            return result

        files_to_reopen: list[tuple[Path, str]] = []  # (path, issue_id)

        if all_reopened:
            for issue_path in self._get_local_issues():
                eid = self._extract_issue_id(issue_path.name)
                if eid:
                    files_to_reopen.append((issue_path, eid))
        elif issue_ids:
            for eid in issue_ids:
                found_path = self._find_local_issue(eid)
                if found_path:
                    files_to_reopen.append((found_path, eid))
                else:
                    result.failed.append((eid, "Local issue not found"))
        else:
            result.success = False
            result.errors.append("Specify issue IDs or use --all-reopened")
            return result

        for issue_path, issue_id in files_to_reopen:
            content = issue_path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content, coerce_types=True)
            github_number = frontmatter.get("github_issue")

            if github_number is None:
                result.skipped.append(f"{issue_id} (not synced to GitHub)")
                continue

            if all_reopened:
                try:
                    state_result = _run_gh_command(
                        [
                            "issue",
                            "view",
                            str(int(github_number)),
                            "--json",
                            "state",
                            "-q",
                            ".state",
                        ],
                        self.logger,
                    )
                    state = state_result.stdout.strip()
                    if state != "CLOSED":
                        result.skipped.append(
                            f"{issue_id} (#{github_number}: already open on GitHub)"
                        )
                        continue
                except subprocess.CalledProcessError as e:
                    result.failed.append((issue_id, f"gh issue view failed: {e.stderr}"))
                    continue

            if self.dry_run:
                result.updated.append(f"{issue_id} → #{github_number} (would reopen)")
                self.logger.info(f"Would reopen GitHub issue #{github_number} for {issue_id}")
                continue

            try:
                _run_gh_command(
                    [
                        "issue",
                        "reopen",
                        str(int(github_number)),
                        "--comment",
                        f"Reopened via ll-sync. Issue {issue_id} moved back to active locally.",
                    ],
                    self.logger,
                )
                result.updated.append(f"{issue_id} → #{github_number} (reopened)")
                self.logger.success(f"Reopened GitHub issue #{github_number} for {issue_id}")
            except subprocess.CalledProcessError as e:
                result.failed.append((issue_id, f"gh issue reopen failed: {e.stderr}"))
                self.logger.error(f"Failed to reopen GitHub issue #{github_number}: {e.stderr}")
                continue

            # Move local file from completed/ back to active directory if needed
            completed_dir = self.config.get_completed_dir()
            if issue_path.parent == completed_dir:
                type_prefix = issue_id.split("-")[0]
                category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
                category = category_map.get(type_prefix)
                if category:
                    target_dir = self.config.get_issue_dir(category)
                    target_path = target_dir / issue_path.name
                    try:
                        subprocess.run(
                            ["git", "mv", str(issue_path), str(target_path)],
                            check=True,
                            capture_output=True,
                        )
                        self.logger.info(f"Moved {issue_path.name} back to {category}/")
                    except subprocess.CalledProcessError:
                        target_path.write_text(content, encoding="utf-8")
                        issue_path.unlink()
                        self.logger.info(f"Moved {issue_path.name} back to {category}/ (fallback)")

        if result.failed:
            result.success = False

        return result
