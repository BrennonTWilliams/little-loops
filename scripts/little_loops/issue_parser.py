"""Issue file parsing for little-loops.

Parses issue markdown files to extract metadata like priority, ID, type, and title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig


# Regex pattern for issue IDs in list items
# Matches: "- FEAT-001", "- BUG-123", "* ENH-005", "- FEAT-001 (some note)"
# Also handles bold markdown: "- **ENH-1000**: description"
ISSUE_ID_PATTERN = re.compile(r"^[-*]\s+\*{0,2}([A-Z]+-\d+)", re.MULTILINE)


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


def get_next_issue_number(config: BRConfig, category: str | None = None) -> int:
    """Determine the next globally unique issue number.

    Scans ALL issue directories (active and completed) to find the highest
    existing number across ALL issue types (BUG, FEAT, ENH). Issue numbers
    are globally unique regardless of type.

    Args:
        config: Project configuration
        category: Unused, kept for backwards compatibility

    Returns:
        Next available issue number (globally unique across all types)
    """
    max_num = 0

    # Get all known prefixes from configuration
    all_prefixes = [cat_config.prefix for cat_config in config.issues.categories.values()]

    # Directories to scan: ALL category directories + completed
    dirs_to_scan = [config.get_completed_dir()]
    for cat_name in config.issues.categories:
        dirs_to_scan.append(config.get_issue_dir(cat_name))

    for dir_path in dirs_to_scan:
        if not dir_path.exists():
            continue
        for file in dir_path.glob("*.md"):
            # Check all prefixes to find global maximum
            for prefix in all_prefixes:
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
        blocked_by: List of issue IDs that block this issue
        blocks: List of issue IDs that this issue blocks
        discovered_by: Source command/workflow that created this issue
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    discovered_by: str | None = None

    @property
    def priority_int(self) -> int:
        """Convert priority to integer for comparison (lower = higher priority)."""
        # Support P0-P5 priorities
        match = re.match(r"^P(\d+)$", self.priority)
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
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "discovered_by": self.discovered_by,
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
            blocked_by=data.get("blocked_by", []),
            blocks=data.get("blocks", []),
            discovered_by=data.get("discovered_by"),
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

        # Read content once for all content-based parsing
        content = self._read_content(issue_path)

        # Parse frontmatter for discovered_by
        frontmatter = self._parse_frontmatter(content)
        discovered_by = frontmatter.get("discovered_by")

        # Parse title and dependencies from file content
        title = self._parse_title_from_content(content, issue_path)
        blocked_by = self._parse_blocked_by(content)
        blocks = self._parse_blocks(content)

        return IssueInfo(
            path=issue_path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            discovered_by=discovered_by,
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

    def _get_category_for_prefix(self, prefix: str) -> str:
        """Get category name from issue prefix.

        Args:
            prefix: Issue prefix (e.g., "BUG", "FEAT")

        Returns:
            Category name (e.g., "bugs", "features"), defaults to "bugs"
        """
        return self._prefix_to_category.get(prefix, "bugs")

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
        # Use next sequential number instead of hash-based fallback
        # This ensures IDs are deterministic and don't collide with existing issues
        category = self._get_category_for_prefix(prefix)
        next_num = get_next_issue_number(self.config, category)
        return f"{prefix}-{next_num:03d}"

    def _read_content(self, issue_path: Path) -> str:
        """Read file content, returning empty string on error.

        Args:
            issue_path: Path to issue file

        Returns:
            File content or empty string on error
        """
        try:
            return issue_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _parse_frontmatter(self, content: str) -> dict[str, Any]:
        """Extract YAML frontmatter from issue content.

        Looks for content between opening and closing '---' markers.
        Returns empty dict if no frontmatter found or on parse error.

        Args:
            content: File content to parse

        Returns:
            Dictionary of frontmatter fields, or empty dict
        """
        if not content or not content.startswith("---"):
            return {}

        # Find closing ---
        end_match = re.search(r"\n---\s*\n", content[3:])
        if not end_match:
            return {}

        frontmatter_text = content[4 : 3 + end_match.start()]

        # Simple YAML-like parsing for key: value pairs
        # Avoids adding yaml dependency for this simple use case
        result: dict[str, Any] = {}
        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                # Handle null/empty values
                if value.lower() in ("null", "~", ""):
                    result[key] = None
                else:
                    result[key] = value
        return result

    def _parse_title_from_content(self, content: str, issue_path: Path) -> str:
        """Extract title from issue file content.

        Args:
            content: Pre-read file content
            issue_path: Path to issue file (for fallback)

        Returns:
            Issue title or filename stem as fallback
        """
        if content:
            # Look for markdown header: # ISSUE-ID: Title
            match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            # Try first header of any format
            match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        # Fall back to filename
        return issue_path.stem

    def _parse_section_items(self, content: str, section_name: str) -> list[str]:
        """Extract issue IDs from a markdown section.

        Finds section header (## Section Name) and extracts issue IDs
        from list items until the next section or end of file.
        Skips content inside code fences.

        Args:
            content: File content to parse
            section_name: Section name to find (e.g., "Blocked By")

        Returns:
            List of issue IDs found in the section
        """
        if not content:
            return []

        # Strip code fences to avoid matching sections in examples
        content_without_code = self._strip_code_fences(content)

        # Match section header case-insensitively
        section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
        match = re.search(section_pattern, content_without_code, re.MULTILINE | re.IGNORECASE)
        if not match:
            return []

        # Get content after section header until next ## header or end
        start = match.end()
        next_section = re.search(r"^##\s+", content_without_code[start:], re.MULTILINE)
        if next_section:
            section_content = content_without_code[start : start + next_section.start()]
        else:
            section_content = content_without_code[start:]

        # Extract issue IDs from list items
        issue_ids = ISSUE_ID_PATTERN.findall(section_content)
        return issue_ids

    def _strip_code_fences(self, content: str) -> str:
        """Remove code fence blocks from content.

        Replaces content between ``` markers with empty lines to preserve
        line numbers while removing code fence content from parsing.

        Args:
            content: File content

        Returns:
            Content with code fence blocks replaced by empty lines
        """
        # Match code fences: ``` or ```language through closing ```
        result = []
        in_fence = False
        for line in content.split("\n"):
            if line.startswith("```"):
                in_fence = not in_fence
                result.append("")  # Preserve line count
            elif in_fence:
                result.append("")  # Replace fenced content with empty line
            else:
                result.append(line)
        return "\n".join(result)

    def _parse_blocked_by(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocked By section.

        Args:
            content: File content to parse

        Returns:
            List of issue IDs that block this issue
        """
        return self._parse_section_items(content, "Blocked By")

    def _parse_blocks(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocks section.

        Args:
            content: File content to parse

        Returns:
            List of issue IDs that this issue blocks
        """
        return self._parse_section_items(content, "Blocks")


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
