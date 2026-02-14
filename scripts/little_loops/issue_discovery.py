"""Issue discovery and deduplication for little-loops.

Provides functions for finding existing issues, detecting duplicates,
and reopening completed issues when problems recur.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.logger import Logger


# =============================================================================
# Enums
# =============================================================================


class MatchClassification(Enum):
    """Classification of how a finding matches an existing issue.

    Used to distinguish between true duplicates, regressions, and invalid fixes
    when a finding matches a completed issue.
    """

    NEW_ISSUE = "new_issue"  # No existing issue matches
    DUPLICATE = "duplicate"  # Active issue exists
    REGRESSION = "regression"  # Completed, files modified AFTER fix (fix broke)
    INVALID_FIX = "invalid_fix"  # Completed, files NOT modified after fix (never worked)
    UNVERIFIED = "unverified"  # Completed, no fix commit tracked (can't determine)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class RegressionEvidence:
    """Evidence for regression vs invalid fix classification.

    Attributes:
        fix_commit_sha: SHA of the commit that fixed the original issue
        fix_commit_exists: Whether the fix commit exists in current history
        files_modified_since_fix: Files from the fix that were modified after fix
        days_since_fix: Number of days since the fix was applied
        related_commits: Commits that modified the relevant files after fix
    """

    fix_commit_sha: str | None = None
    fix_commit_exists: bool = True
    files_modified_since_fix: list[str] = field(default_factory=list)
    days_since_fix: int = 0
    related_commits: list[str] = field(default_factory=list)


@dataclass
class FindingMatch:
    """Result of matching a finding to an existing issue.

    Attributes:
        issue_path: Path to matched issue file, or None if no match
        match_type: Type of match ("exact", "similar", "content", "none")
        match_score: Confidence score from 0.0 to 1.0
        is_completed: Whether the matched issue is in completed/
        matched_terms: Terms that matched (for debugging)
        classification: How to classify this match (regression, duplicate, etc.)
        regression_evidence: Evidence supporting regression classification
    """

    issue_path: Path | None
    match_type: str
    match_score: float
    is_completed: bool = False
    matched_terms: list[str] = field(default_factory=list)
    classification: MatchClassification = MatchClassification.NEW_ISSUE
    regression_evidence: RegressionEvidence | None = None

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

    @property
    def should_reopen_as_regression(self) -> bool:
        """Return True if issue should be reopened as a regression.

        A regression means the fix was applied but later code changes broke it.
        """
        return (
            self.is_completed
            and self.match_score >= 0.5
            and self.classification == MatchClassification.REGRESSION
        )

    @property
    def should_reopen_as_invalid_fix(self) -> bool:
        """Return True if issue should be reopened due to invalid fix.

        An invalid fix means the original fix never actually resolved the issue.
        """
        return (
            self.is_completed
            and self.match_score >= 0.5
            and self.classification == MatchClassification.INVALID_FIX
        )

    @property
    def is_unverified(self) -> bool:
        """Return True if regression status cannot be determined.

        Unverified means the completed issue has no fix commit tracked,
        so we cannot determine if this is a regression or invalid fix.
        """
        return (
            self.is_completed
            and self.match_score >= 0.5
            and self.classification == MatchClassification.UNVERIFIED
        )


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
# Git History Analysis
# =============================================================================


def _extract_fix_commit(content: str) -> str | None:
    """Extract fix commit SHA from issue Resolution section.

    Args:
        content: Issue file content

    Returns:
        Fix commit SHA if found, None otherwise
    """
    # Look for "Fix Commit: <sha>" pattern in Resolution section
    match = re.search(r"\*\*Fix Commit\*\*:\s*([a-f0-9]{7,40})", content)
    if match:
        return match.group(1)
    return None


def _extract_files_changed(content: str) -> list[str]:
    """Extract files changed from issue Resolution section.

    Args:
        content: Issue file content

    Returns:
        List of file paths that were changed to fix the issue
    """
    files: list[str] = []

    # Look for Files Changed section
    section_match = re.search(
        r"###\s*Files Changed\s*\n(.*?)(?=\n###|\n##|\Z)",
        content,
        re.DOTALL,
    )
    if section_match:
        section = section_match.group(1)
        # Extract backtick-quoted paths: `path/to/file.py`
        for match in re.finditer(r"`([^`]+)`", section):
            path = match.group(1).strip()
            if path and not path.startswith("See "):  # Skip placeholder text
                files.append(path)

    return files


def _extract_completion_date(content: str) -> datetime | None:
    """Extract completion/closed date from issue Resolution section.

    Args:
        content: Issue file content

    Returns:
        Completion date if found, None otherwise
    """
    # Look for "Completed: YYYY-MM-DD" or "Closed: YYYY-MM-DD"
    match = re.search(r"\*\*(?:Completed|Closed)\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _commit_exists_in_history(commit_sha: str) -> bool:
    """Check if a commit exists in the current git history.

    Args:
        commit_sha: SHA of the commit to check

    Returns:
        True if commit exists in current history
    """
    result = subprocess.run(
        ["git", "cat-file", "-t", commit_sha],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "commit"


def _get_files_modified_since_commit(
    since_commit: str,
    target_files: list[str],
) -> tuple[list[str], list[str]]:
    """Find which target files have been modified since a given commit.

    Args:
        since_commit: SHA of the commit to check since
        target_files: List of file paths to check

    Returns:
        Tuple of (modified_files, related_commits) where:
        - modified_files: Target files that were modified after the commit
        - related_commits: SHAs of commits that modified the target files
    """
    if not target_files:
        return [], []

    modified_files: list[str] = []
    related_commits: set[str] = set()

    for file_path in target_files:
        # Get commits that modified this file since the fix commit
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H", f"{since_commit}..HEAD", "--", file_path],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            modified_files.append(file_path)
            for sha in result.stdout.strip().split("\n"):
                if sha:
                    related_commits.add(sha[:8])  # Short SHA

    return modified_files, list(related_commits)


def detect_regression_or_duplicate(
    config: BRConfig,
    completed_issue_path: Path,
) -> tuple[MatchClassification, RegressionEvidence]:
    """Analyze a completed issue to classify if a match is a regression or invalid fix.

    Classification Logic:
    - UNVERIFIED: No fix commit tracked - can't determine
    - INVALID_FIX: Fix commit not in history - fix was never merged/deployed
    - REGRESSION: Files modified AFTER fix - fix worked but later changes broke it
    - INVALID_FIX: Files NOT modified after fix - fix was applied but never worked

    Args:
        config: Project configuration
        completed_issue_path: Path to the completed issue file

    Returns:
        Tuple of (classification, evidence) with analysis results
    """
    evidence = RegressionEvidence()

    try:
        content = completed_issue_path.read_text(encoding="utf-8")
    except Exception:
        return MatchClassification.UNVERIFIED, evidence

    # Extract fix commit
    fix_commit = _extract_fix_commit(content)
    evidence.fix_commit_sha = fix_commit

    if not fix_commit:
        # No fix commit tracked - can't determine regression vs invalid fix
        return MatchClassification.UNVERIFIED, evidence

    # Check if fix commit exists in current history
    if not _commit_exists_in_history(fix_commit):
        evidence.fix_commit_exists = False
        return MatchClassification.INVALID_FIX, evidence

    # Extract files changed in the fix
    files_changed = _extract_files_changed(content)

    if not files_changed:
        # No files tracked - can't determine
        return MatchClassification.UNVERIFIED, evidence

    # Check if any of those files were modified since the fix
    modified_files, related_commits = _get_files_modified_since_commit(fix_commit, files_changed)
    evidence.files_modified_since_fix = modified_files
    evidence.related_commits = related_commits

    # Calculate days since fix
    completion_date = _extract_completion_date(content)
    if completion_date:
        evidence.days_since_fix = (datetime.now() - completion_date).days

    if modified_files:
        # Files were modified after fix - this is a regression
        return MatchClassification.REGRESSION, evidence
    else:
        # Files were NOT modified after fix - the fix never actually worked
        return MatchClassification.INVALID_FIX, evidence


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
# Issue Reopening
# =============================================================================


def _build_reopen_section(
    reason: str,
    new_context: str,
    source_command: str,
    classification: MatchClassification | None = None,
    regression_evidence: RegressionEvidence | None = None,
) -> str:
    """Build the reopened section for an issue.

    Args:
        reason: Reason for reopening
        new_context: New context/findings
        source_command: Command that triggered reopen
        classification: How this issue was classified (regression, invalid_fix, etc.)
        regression_evidence: Evidence supporting the classification

    Returns:
        Markdown section string
    """
    # Determine section header based on classification
    if classification == MatchClassification.REGRESSION:
        section_header = "## Regression"
        classification_line = "- **Classification**: Regression (fix was broken by later changes)"
    elif classification == MatchClassification.INVALID_FIX:
        section_header = "## Reopened (Invalid Fix)"
        classification_line = (
            "- **Classification**: Invalid Fix (original fix never resolved the issue)"
        )
    else:
        section_header = "## Reopened"
        classification_line = ""

    # Build evidence section if available
    evidence_section = ""
    if regression_evidence:
        evidence_lines = []
        if regression_evidence.fix_commit_sha:
            evidence_lines.append(
                f"- **Original Fix Commit**: {regression_evidence.fix_commit_sha}"
            )
        if not regression_evidence.fix_commit_exists:
            evidence_lines.append(
                "- **Fix Status**: Fix commit not found in history (possibly never merged)"
            )
        if regression_evidence.files_modified_since_fix:
            files_list = ", ".join(
                f"`{f}`" for f in regression_evidence.files_modified_since_fix[:5]
            )
            evidence_lines.append(f"- **Files Modified Since Fix**: {files_list}")
        if regression_evidence.related_commits:
            commits_list = ", ".join(regression_evidence.related_commits[:5])
            evidence_lines.append(f"- **Related Commits**: {commits_list}")
        if regression_evidence.days_since_fix > 0:
            evidence_lines.append(f"- **Days Since Fix**: {regression_evidence.days_since_fix}")

        if evidence_lines:
            evidence_section = "\n### Evidence\n\n" + "\n".join(evidence_lines)

    return f"""

---

{section_header}

- **Date**: {datetime.now().strftime("%Y-%m-%d")}
- **By**: {source_command}
- **Reason**: {reason}
{classification_line}
{evidence_section}

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


def _matches_issue_type(
    finding_type: str,
    issue_path: Path,
    config: BRConfig,
    is_completed: bool,
) -> bool:
    """Check if finding type matches issue path using configured categories.

    Args:
        finding_type: The type of finding (e.g., 'BUG', 'ENH', 'FEAT')
        issue_path: Path to the issue file
        config: Configuration with category definitions
        is_completed: Whether the issue is in the completed directory

    Returns:
        True if the finding type matches the issue path's category
    """
    if is_completed:
        return True

    path_str = str(issue_path)
    for category in config.issues.categories.values():
        if finding_type == category.prefix and f"/{category.dir}/" in path_str:
            return True
    return False


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
