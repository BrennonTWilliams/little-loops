"""Git history analysis and regression detection for issue discovery."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.issue_discovery.matching import (
    MatchClassification,
    RegressionEvidence,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig


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

    Uses a single batched git log call instead of per-file subprocess calls.

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

    # Single batched git log call with all file paths
    result = subprocess.run(
        ["git", "log", "--pretty=format:%H", "--name-only", f"{since_commit}..HEAD", "--"]
        + target_files,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return [], []

    # Parse output: blocks separated by blank lines, each block is SHA followed by file names
    target_set = set(target_files)
    modified_set: set[str] = set()
    related_commits: set[str] = set()

    for block in result.stdout.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if not lines:
            continue
        commit_sha = lines[0]
        related_commits.add(commit_sha[:8])
        for file_name in lines[1:]:
            file_name = file_name.strip()
            if file_name in target_set:
                modified_set.add(file_name)

    # Preserve original order from target_files
    modified_files = [f for f in target_files if f in modified_set]
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
# Issue Reopening Section Builder
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
