"""Issue file parsing for little-loops.

Parses issue markdown files to extract metadata like priority, ID, type, and title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def slugify(text: str) -> str:
    """Convert text to slug format for filenames.

    Args:
        text: Text to convert

    Returns:
        Lowercase slug with hyphens
    """
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-").lower()


def get_next_issue_number(config: BRConfig, category: str) -> int:
    """Determine the next issue number for a category.

    Scans both active and completed issue directories to find the highest
    existing number for the category's prefix.

    Args:
        config: Project configuration
        category: Category key (e.g., "bugs", "features")

    Returns:
        Next available issue number
    """
    prefix = config.get_issue_prefix(category)
    max_num = 0

    # Directories to scan
    dirs_to_scan = [
        config.get_issue_dir(category),
        config.get_completed_dir(),
    ]

    for dir_path in dirs_to_scan:
        if not dir_path.exists():
            continue
        for file in dir_path.glob("*.md"):
            match = re.search(rf"{prefix}-(\d+)", file.name)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num

    return max_num + 1


@dataclass
class IssueInfo:
    """Parsed information from an issue file.

    Attributes:
        path: Path to the issue file
        issue_type: Type of issue (e.g., "bugs", "features")
        priority: Priority level (e.g., "P0", "P1")
        issue_id: Issue identifier (e.g., "BUG-123")
        title: Issue title from markdown header
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str

    @property
    def priority_int(self) -> int:
        """Convert priority to integer for comparison (lower = higher priority)."""
        # Support P0-P5 priorities
        match = re.match(r"P(\d+)", self.priority)
        if match:
            return int(match.group(1))
        return 99  # Unknown priority sorts last

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "issue_type": self.issue_type,
            "priority": self.priority,
            "issue_id": self.issue_id,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueInfo:
        """Create IssueInfo from dictionary."""
        return cls(
            path=Path(data["path"]),
            issue_type=data["issue_type"],
            priority=data["priority"],
            issue_id=data["issue_id"],
            title=data["title"],
        )


class IssueParser:
    """Parses issue files based on project configuration.

    Uses BRConfig to understand issue categories, prefixes, and priorities.
    """

    def __init__(self, config: BRConfig) -> None:
        """Initialize parser with project configuration.

        Args:
            config: Project configuration
        """
        self.config = config
        self._build_prefix_map()

    def _build_prefix_map(self) -> None:
        """Build mapping from issue prefixes to category names."""
        self._prefix_to_category: dict[str, str] = {}
        for category_name, category in self.config.issues.categories.items():
            self._prefix_to_category[category.prefix] = category_name

    def parse_file(self, issue_path: Path) -> IssueInfo:
        """Parse an issue file to extract metadata.

        Args:
            issue_path: Path to the issue markdown file

        Returns:
            Parsed IssueInfo
        """
        filename = issue_path.name

        # Parse priority from filename prefix (e.g., P1-BUG-123-...)
        priority = self._parse_priority(filename)

        # Parse issue type and ID from filename
        issue_type, issue_id = self._parse_type_and_id(filename, issue_path)

        # Parse title from file content
        title = self._parse_title(issue_path)

        return IssueInfo(
            path=issue_path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
        )

    def _parse_priority(self, filename: str) -> str:
        """Extract priority from filename.

        Args:
            filename: Issue filename

        Returns:
            Priority string (e.g., "P1") or last priority if not found
        """
        for priority in self.config.issue_priorities:
            if filename.startswith(f"{priority}-"):
                return priority
        # Default to lowest priority if not found
        return self.config.issue_priorities[-1] if self.config.issue_priorities else "P3"

    def _parse_type_and_id(self, filename: str, issue_path: Path) -> tuple[str, str]:
        """Extract issue type and ID from filename.

        Args:
            filename: Issue filename
            issue_path: Full path to issue file

        Returns:
            Tuple of (issue_type, issue_id)
        """
        # Try to match known prefixes (BUG, FEAT, ENH, etc.)
        for prefix, category in self._prefix_to_category.items():
            pattern = rf"({prefix})-(\d+)"
            match = re.search(pattern, filename)
            if match:
                issue_id = f"{match.group(1)}-{match.group(2)}"
                return category, issue_id

        # Fall back to inferring from directory
        parent_name = issue_path.parent.name
        for category_name, category_config in self.config.issues.categories.items():
            if parent_name == category_config.dir:
                # Generate ID from filename
                issue_id = self._generate_id_from_filename(filename, category_config.prefix)
                return category_name, issue_id

        # Last resort: use filename as ID
        return "bugs", filename.replace(".md", "")

    def _generate_id_from_filename(self, filename: str, prefix: str) -> str:
        """Generate an issue ID from filename when not explicitly present.

        Args:
            filename: Issue filename
            prefix: Issue prefix to use

        Returns:
            Generated issue ID
        """
        # Try to extract a number from the filename
        numbers = re.findall(r"\d+", filename)
        if numbers:
            return f"{prefix}-{numbers[0]}"
        # Use hash of filename as fallback
        return f"{prefix}-{abs(hash(filename)) % 10000:04d}"

    def _parse_title(self, issue_path: Path) -> str:
        """Extract title from issue file content.

        Args:
            issue_path: Path to issue file

        Returns:
            Issue title or filename stem as fallback
        """
        try:
            content = issue_path.read_text(encoding="utf-8")
            # Look for markdown header: # ISSUE-ID: Title
            match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            # Try first header of any format
            match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        # Fall back to filename
        return issue_path.stem


def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: set[str] | None = None,
) -> list[IssueInfo]:
    """Find all issues matching criteria.

    Args:
        config: Project configuration
        category: Optional category to filter (e.g., "bugs")
        skip_ids: Issue IDs to skip
        only_ids: If provided, only include these issue IDs

    Returns:
        List of IssueInfo sorted by priority
    """
    skip_ids = skip_ids or set()
    parser = IssueParser(config)
    issues: list[IssueInfo] = []

    # Get completed directory for duplicate detection
    completed_dir = config.get_completed_dir()

    # Determine which categories to search
    if category:
        categories = [category] if category in config.issue_categories else []
    else:
        categories = config.issue_categories

    for cat in categories:
        issue_dir = config.get_issue_dir(cat)
        if not issue_dir.exists():
            continue

        for issue_file in issue_dir.glob("*.md"):
            # Pre-flight check: skip if already exists in completed directory
            completed_path = completed_dir / issue_file.name
            if completed_path.exists():
                continue

            info = parser.parse_file(issue_file)
            # Apply skip filter
            if info.issue_id in skip_ids:
                continue
            # Apply only filter (if specified)
            if only_ids is not None and info.issue_id not in only_ids:
                continue
            issues.append(info)

    # Sort by priority (lower int = higher priority)
    issues.sort(key=lambda x: (x.priority_int, x.issue_id))
    return issues


def find_highest_priority_issue(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: set[str] | None = None,
) -> IssueInfo | None:
    """Find the highest priority issue.

    Args:
        config: Project configuration
        category: Optional category to filter
        skip_ids: Issue IDs to skip
        only_ids: If provided, only include these issue IDs

    Returns:
        Highest priority IssueInfo or None if no issues found
    """
    issues = find_issues(config, category, skip_ids, only_ids)
    return issues[0] if issues else None
