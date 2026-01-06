"""Issue discovery and deduplication for little-loops.

Provides functions for finding existing issues, detecting duplicates,
and reopening completed issues when problems recur.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.logger import Logger


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class FindingMatch:
    """Result of matching a finding to an existing issue.

    Attributes:
        issue_path: Path to matched issue file, or None if no match
        match_type: Type of match ("exact", "similar", "content", "none")
        match_score: Confidence score from 0.0 to 1.0
        is_completed: Whether the matched issue is in completed/
        matched_terms: Terms that matched (for debugging)
    """

    issue_path: Path | None
    match_type: str
    match_score: float
    is_completed: bool = False
    matched_terms: list[str] = field(default_factory=list)

    @property
    def should_skip(self) -> bool:
        """Return True if finding is a duplicate and should be skipped."""
        return self.match_score >= 0.8

    @property
    def should_update(self) -> bool:
        """Return True if finding should update the existing issue."""
        return 0.5 <= self.match_score < 0.8

    @property
    def should_create(self) -> bool:
        """Return True if a new issue should be created."""
        return self.match_score < 0.5

    @property
    def should_reopen(self) -> bool:
        """Return True if a completed issue should be reopened."""
        return self.is_completed and self.match_score >= 0.5


# =============================================================================
# Text Matching Helpers
# =============================================================================


def _normalize_text(text: str) -> str:
    """Normalize text for comparison.

    Args:
        text: Input text

    Returns:
        Lowercase text with normalized whitespace
    """
    return re.sub(r"\s+", " ", text.lower().strip())


def _extract_words(text: str) -> set[str]:
    """Extract significant words from text.

    Args:
        text: Input text

    Returns:
        Set of lowercase words (3+ chars, excluding common words)
    """
    common_words = {
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "should",
        "would",
        "could",
        "may",
        "might",
        "must",
        "file",
        "code",
        "issue",
    }
    words = set(re.findall(r"\b[a-z]{3,}\b", text.lower()))
    return words - common_words


def _calculate_word_overlap(words1: set[str], words2: set[str]) -> float:
    """Calculate Jaccard similarity between word sets.

    Args:
        words1: First word set
        words2: Second word set

    Returns:
        Similarity score from 0.0 to 1.0
    """
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _extract_file_paths(text: str) -> set[str]:
    """Extract file paths from text.

    Args:
        text: Input text

    Returns:
        Set of file paths found in text
    """
    # Match common file path patterns
    patterns = [
        r"`([^`]+\.[a-z]{2,4})`",  # `path/to/file.py`
        r"\*\*File\*\*:\s*`?([^`\n]+)`?",  # **File**: path/to/file.py
        r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?:\s|$|:|\))",  # standalone paths
    ]
    paths: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            path = match.group(1).strip()
            if "/" in path or path.endswith((".py", ".md", ".js", ".ts", ".json")):
                paths.add(path)
    return paths


def _extract_line_numbers(text: str) -> set[int]:
    """Extract line numbers from text.

    Args:
        text: Input text

    Returns:
        Set of line numbers found
    """
    numbers: set[int] = set()
    # Match line number patterns
    patterns = [
        r"\*\*Line(?:\(s\))?\*\*:\s*(\d+)(?:-(\d+))?",  # **Line(s)**: 42-45
        r":(\d+)(?:-(\d+))?",  # :42-45 (in paths)
        r"line\s+(\d+)",  # line 42
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            numbers.add(int(match.group(1)))
            if match.lastindex and match.lastindex >= 2 and match.group(2):
                numbers.add(int(match.group(2)))
    return numbers


# =============================================================================
# Issue Search Functions
# =============================================================================


def _get_all_issue_files(
    config: BRConfig,
    include_completed: bool = True,
) -> list[tuple[Path, bool]]:
    """Get all issue files with their completion status.

    Args:
        config: Project configuration
        include_completed: Whether to include completed issues

    Returns:
        List of (path, is_completed) tuples
    """
    files: list[tuple[Path, bool]] = []

    # Active issues
    for category in config.issue_categories:
        issue_dir = config.get_issue_dir(category)
        if issue_dir.exists():
            for f in issue_dir.glob("*.md"):
                files.append((f, False))

    # Completed issues
    if include_completed:
        completed_dir = config.get_completed_dir()
        if completed_dir.exists():
            for f in completed_dir.glob("*.md"):
                files.append((f, True))

    return files


def search_issues_by_content(
    config: BRConfig,
    search_terms: list[str],
    include_completed: bool = True,
) -> list[tuple[Path, float, bool]]:
    """Search issues by content with relevance scoring.

    Args:
        config: Project configuration
        search_terms: Terms to search for
        include_completed: Whether to include completed issues

    Returns:
        List of (path, score, is_completed) sorted by score descending
    """
    results: list[tuple[Path, float, bool]] = []
    search_words = set()
    for term in search_terms:
        search_words.update(_extract_words(term))

    if not search_words:
        return results

    for issue_path, is_completed in _get_all_issue_files(config, include_completed):
        try:
            content = issue_path.read_text(encoding="utf-8")
            content_words = _extract_words(content)
            score = _calculate_word_overlap(search_words, content_words)
            if score > 0.1:  # Minimum threshold
                results.append((issue_path, score, is_completed))
        except Exception:
            continue

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def search_issues_by_file_path(
    config: BRConfig,
    file_path: str,
    include_completed: bool = True,
) -> list[tuple[Path, bool]]:
    """Search for issues mentioning a specific file path.

    Args:
        config: Project configuration
        file_path: File path to search for
        include_completed: Whether to include completed issues

    Returns:
        List of (issue_path, is_completed) tuples
    """
    results: list[tuple[Path, bool]] = []
    normalized_path = file_path.strip().lower()

    # Also match partial paths (e.g., "module.py" matches "src/module.py")
    path_parts = normalized_path.split("/")
    filename = path_parts[-1] if path_parts else normalized_path

    for issue_path, is_completed in _get_all_issue_files(config, include_completed):
        try:
            content = issue_path.read_text(encoding="utf-8").lower()
            # Check for exact path or filename match
            if normalized_path in content or filename in content:
                results.append((issue_path, is_completed))
        except Exception:
            continue

    return results


# =============================================================================
# Main Discovery Functions
# =============================================================================


def find_existing_issue(
    config: BRConfig,
    finding_type: str,
    file_path: str | None,
    finding_title: str,
    finding_content: str,
) -> FindingMatch:
    """Search for an existing issue matching this finding.

    Uses a multi-pass approach:
    1. Exact file path match in Location sections
    2. Title word overlap (>70% = likely duplicate)
    3. Content overlap analysis

    Args:
        config: Project configuration
        finding_type: Issue type ("BUG", "ENH", "FEAT")
        file_path: File path from finding (if any)
        finding_title: Title of the finding
        finding_content: Full content/description of finding

    Returns:
        FindingMatch with best match details
    """
    best_match = FindingMatch(
        issue_path=None,
        match_type="none",
        match_score=0.0,
    )

    # Pass 1: Exact file path match
    if file_path:
        path_matches = search_issues_by_file_path(config, file_path)
        for issue_path, is_completed in path_matches:
            try:
                content = issue_path.read_text(encoding="utf-8")
                # Check if same type of finding
                issue_type_match = (
                    (finding_type == "BUG" and "/bugs/" in str(issue_path))
                    or (finding_type == "ENH" and "/enhancements/" in str(issue_path))
                    or (finding_type == "FEAT" and "/features/" in str(issue_path))
                    or is_completed  # Completed issues could be any type
                )
                if issue_type_match:
                    # High confidence if same file + same type
                    return FindingMatch(
                        issue_path=issue_path,
                        match_type="exact",
                        match_score=0.85,
                        is_completed=is_completed,
                        matched_terms=[file_path],
                    )
            except Exception:
                continue

    # Pass 2: Title similarity
    title_words = _extract_words(finding_title)
    if title_words:
        for issue_path, is_completed in _get_all_issue_files(config):
            try:
                # Extract title from issue file
                content = issue_path.read_text(encoding="utf-8")
                title_match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
                if title_match:
                    issue_title = title_match.group(1)
                    issue_words = _extract_words(issue_title)
                    overlap = _calculate_word_overlap(title_words, issue_words)
                    if overlap > 0.7 and overlap > best_match.match_score:
                        best_match = FindingMatch(
                            issue_path=issue_path,
                            match_type="similar",
                            match_score=overlap,
                            is_completed=is_completed,
                            matched_terms=list(title_words & issue_words),
                        )
            except Exception:
                continue

    # Pass 3: Content analysis
    if best_match.match_score < 0.5:
        content_matches = search_issues_by_content(
            config,
            [finding_title, finding_content],
        )
        for issue_path, score, is_completed in content_matches[:5]:  # Top 5
            adjusted_score = score * 0.8  # Content matches are less precise
            if adjusted_score > best_match.match_score:
                best_match = FindingMatch(
                    issue_path=issue_path,
                    match_type="content",
                    match_score=adjusted_score,
                    is_completed=is_completed,
                )

    return best_match


# =============================================================================
# Issue Reopening
# =============================================================================


def _build_reopen_section(reason: str, new_context: str, source_command: str) -> str:
    """Build the reopened section for an issue.

    Args:
        reason: Reason for reopening
        new_context: New context/findings
        source_command: Command that triggered reopen

    Returns:
        Markdown section string
    """
    return f"""

---

## Reopened

- **Date**: {datetime.now().strftime("%Y-%m-%d")}
- **By**: {source_command}
- **Reason**: {reason}

### New Findings

{new_context}
"""


def _get_category_from_issue_path(issue_path: Path, config: BRConfig) -> str:
    """Determine the category for an issue based on its filename.

    Args:
        issue_path: Path to issue file
        config: Project configuration

    Returns:
        Category name (e.g., "bugs", "enhancements", "features")
    """
    filename = issue_path.name.upper()
    for category_name, category_config in config.issues.categories.items():
        if category_config.prefix in filename:
            return category_name
    return "bugs"  # Default


def reopen_issue(
    config: BRConfig,
    completed_issue_path: Path,
    reopen_reason: str,
    new_context: str,
    source_command: str,
    logger: Logger,
) -> Path | None:
    """Move issue from completed back to active with Reopened section.

    Args:
        config: Project configuration
        completed_issue_path: Path to issue in completed/
        reopen_reason: Reason for reopening
        new_context: New context/findings to add
        source_command: Command triggering the reopen
        logger: Logger for output

    Returns:
        New path to reopened issue, or None if failed
    """
    if not completed_issue_path.exists():
        logger.error(f"Completed issue not found: {completed_issue_path}")
        return None

    # Determine target category directory
    category = _get_category_from_issue_path(completed_issue_path, config)
    target_dir = config.get_issue_dir(category)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / completed_issue_path.name

    # Safety check - don't overwrite existing active issue
    if target_path.exists():
        logger.warning(f"Active issue already exists: {target_path}")
        return None

    logger.info(f"Reopening {completed_issue_path.name} -> {category}/")

    try:
        # Read and update content
        content = completed_issue_path.read_text(encoding="utf-8")

        # Add reopened section
        reopen_section = _build_reopen_section(reopen_reason, new_context, source_command)
        content += reopen_section

        # Try git mv first for history preservation
        result = subprocess.run(
            ["git", "mv", str(completed_issue_path), str(target_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Fall back to manual copy
            logger.warning(f"git mv failed, using manual copy: {result.stderr}")
            target_path.write_text(content, encoding="utf-8")
            completed_issue_path.unlink()
        else:
            # Write updated content
            target_path.write_text(content, encoding="utf-8")

        logger.success(f"Reopened: {target_path.name}")
        return target_path

    except Exception as e:
        logger.error(f"Failed to reopen issue: {e}")
        return None


def update_existing_issue(
    config: BRConfig,
    issue_path: Path,
    update_section_name: str,
    update_content: str,
    source_command: str,
    logger: Logger,
) -> bool:
    """Add new findings to an existing issue.

    Args:
        config: Project configuration
        issue_path: Path to issue file
        update_section_name: Name for the update section
        update_content: Content to add
        source_command: Command triggering the update
        logger: Logger for output

    Returns:
        True if update succeeded
    """
    if not issue_path.exists():
        logger.error(f"Issue not found: {issue_path}")
        return False

    try:
        content = issue_path.read_text(encoding="utf-8")

        # Build update section
        update_section = f"""

---

## {update_section_name}

- **Date**: {datetime.now().strftime("%Y-%m-%d")}
- **Source**: {source_command}

{update_content}
"""

        # Check if section already exists
        if f"## {update_section_name}" not in content:
            content += update_section
            issue_path.write_text(content, encoding="utf-8")
            logger.success(f"Updated: {issue_path.name}")
        else:
            logger.info(f"Section already exists in {issue_path.name}, skipping")

        return True

    except Exception as e:
        logger.error(f"Failed to update issue: {e}")
        return False
