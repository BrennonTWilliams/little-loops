"""Issue matching types and text similarity helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


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
