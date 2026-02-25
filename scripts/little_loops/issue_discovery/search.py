"""Issue file search and main discovery functions."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.issue_discovery.extraction import (
    _build_reopen_section,
    detect_regression_or_duplicate,
)
from little_loops.issue_discovery.matching import (
    FindingMatch,
    MatchClassification,
    RegressionEvidence,
    _calculate_word_overlap,
    _extract_words,
    _matches_issue_type,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.logger import Logger


# =============================================================================
# Issue Search Functions
# =============================================================================


def _get_all_issue_files(
    config: BRConfig,
    include_completed: bool = True,
    include_deferred: bool = False,
) -> list[tuple[Path, bool]]:
    """Get all issue files with their completion status.

    Args:
        config: Project configuration
        include_completed: Whether to include completed issues
        include_deferred: Whether to include deferred issues

    Returns:
        List of (path, is_completed) tuples.
        For deferred issues, is_completed is set to True (non-active).
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

    # Deferred issues
    if include_deferred:
        deferred_dir = config.get_deferred_dir()
        if deferred_dir.exists():
            for f in deferred_dir.glob("*.md"):
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

    For matches to completed issues, performs regression analysis to determine
    if the match is a regression (fix broke) or invalid fix (never worked).

    Args:
        config: Project configuration
        finding_type: Issue type ("BUG", "ENH", "FEAT")
        file_path: File path from finding (if any)
        finding_title: Title of the finding
        finding_content: Full content/description of finding

    Returns:
        FindingMatch with best match details, including classification and
        regression evidence for completed issue matches
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
                # Check if same type of finding (uses configured categories)
                issue_type_match = _matches_issue_type(
                    finding_type, issue_path, config, is_completed
                )
                if issue_type_match:
                    # Determine classification
                    if is_completed:
                        classification, evidence = detect_regression_or_duplicate(
                            config, issue_path
                        )
                    else:
                        classification = MatchClassification.DUPLICATE
                        evidence = None

                    # High confidence if same file + same type
                    return FindingMatch(
                        issue_path=issue_path,
                        match_type="exact",
                        match_score=0.85,
                        is_completed=is_completed,
                        matched_terms=[file_path],
                        classification=classification,
                        regression_evidence=evidence,
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
                        # Determine classification
                        if is_completed:
                            classification, evidence = detect_regression_or_duplicate(
                                config, issue_path
                            )
                        else:
                            classification = MatchClassification.DUPLICATE
                            evidence = None

                        best_match = FindingMatch(
                            issue_path=issue_path,
                            match_type="similar",
                            match_score=overlap,
                            is_completed=is_completed,
                            matched_terms=list(title_words & issue_words),
                            classification=classification,
                            regression_evidence=evidence,
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
                # Determine classification
                if is_completed:
                    classification, evidence = detect_regression_or_duplicate(config, issue_path)
                else:
                    classification = MatchClassification.DUPLICATE
                    evidence = None

                best_match = FindingMatch(
                    issue_path=issue_path,
                    match_type="content",
                    match_score=adjusted_score,
                    is_completed=is_completed,
                    classification=classification,
                    regression_evidence=evidence,
                )

    # If no match found, classification is NEW_ISSUE (the default)
    return best_match


# =============================================================================
# Issue Reopening and Updating
# =============================================================================


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
    classification: MatchClassification | None = None,
    regression_evidence: RegressionEvidence | None = None,
) -> Path | None:
    """Move issue from completed back to active with Reopened section.

    Args:
        config: Project configuration
        completed_issue_path: Path to issue in completed/
        reopen_reason: Reason for reopening
        new_context: New context/findings to add
        source_command: Command triggering the reopen
        logger: Logger for output
        classification: How this issue was classified (regression, invalid_fix, etc.)
        regression_evidence: Evidence supporting the classification

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

    # Log with classification info if available
    if classification == MatchClassification.REGRESSION:
        logger.info(f"Reopening {completed_issue_path.name} as REGRESSION -> {category}/")
    elif classification == MatchClassification.INVALID_FIX:
        logger.info(f"Reopening {completed_issue_path.name} as INVALID_FIX -> {category}/")
    else:
        logger.info(f"Reopening {completed_issue_path.name} -> {category}/")

    try:
        # Read and update content
        content = completed_issue_path.read_text(encoding="utf-8")

        # Add reopened section with classification info
        reopen_section = _build_reopen_section(
            reopen_reason,
            new_context,
            source_command,
            classification,
            regression_evidence,
        )
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
