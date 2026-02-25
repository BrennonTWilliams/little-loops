"""Issue discovery and deduplication for little-loops.

Provides functions for finding existing issues, detecting duplicates,
and reopening completed issues when problems recur.

Public exports:
    # Types
    MatchClassification: Classification enum for how a finding matches an issue
    RegressionEvidence: Evidence dataclass for regression classification
    FindingMatch: Result dataclass from matching a finding to an issue

    # Search
    search_issues_by_content: Search issues by content with relevance scoring
    search_issues_by_file_path: Search for issues mentioning a specific file path

    # Detection
    detect_regression_or_duplicate: Classify a completed issue match

    # Discovery
    find_existing_issue: Multi-pass search for an existing issue matching a finding

    # Mutation
    reopen_issue: Move a completed issue back to active with Reopened section
    update_existing_issue: Add new findings to an existing issue
"""

from little_loops.issue_discovery.extraction import (
    _build_reopen_section,
    _commit_exists_in_history,
    _extract_completion_date,
    _extract_files_changed,
    _extract_fix_commit,
    _get_files_modified_since_commit,
    detect_regression_or_duplicate,
)
from little_loops.issue_discovery.matching import (
    FindingMatch,
    MatchClassification,
    RegressionEvidence,
    _calculate_word_overlap,
    _extract_line_numbers,
    _extract_words,
    _matches_issue_type,
    _normalize_text,
)
from little_loops.issue_discovery.search import (
    _get_all_issue_files,
    _get_category_from_issue_path,
    find_existing_issue,
    reopen_issue,
    search_issues_by_content,
    search_issues_by_file_path,
    update_existing_issue,
)

__all__ = [
    # Public types
    "MatchClassification",
    "RegressionEvidence",
    "FindingMatch",
    # Public functions
    "search_issues_by_content",
    "search_issues_by_file_path",
    "detect_regression_or_duplicate",
    "find_existing_issue",
    "reopen_issue",
    "update_existing_issue",
    # Private functions re-exported for test access
    "_normalize_text",
    "_extract_words",
    "_calculate_word_overlap",
    "_extract_line_numbers",
    "_matches_issue_type",
    "_extract_fix_commit",
    "_extract_files_changed",
    "_extract_completion_date",
    "_commit_exists_in_history",
    "_get_files_modified_since_commit",
    "_build_reopen_section",
    "_get_all_issue_files",
    "_get_category_from_issue_path",
]
