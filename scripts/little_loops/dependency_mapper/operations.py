"""Dependency fix and mutation operations.

Functions for applying dependency proposals to issue files and
auto-repairing broken dependency references.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.dependency_mapper.analysis import validate_dependencies
from little_loops.dependency_mapper.models import DependencyProposal, FixResult

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo


def apply_proposals(
    proposals: list[DependencyProposal],
    issue_files: dict[str, Path],
) -> list[str]:
    """Write approved dependency proposals to issue files.

    For each proposal, adds the target to the source's ``## Blocked By``
    section and the source to the target's ``## Blocks`` section.

    Args:
        proposals: Approved proposals to apply
        issue_files: Mapping from issue_id to file path

    Returns:
        List of modified file paths
    """
    modified: set[str] = set()

    for proposal in proposals:
        # Update source issue: add to ## Blocked By
        source_path = issue_files.get(proposal.source_id)
        if source_path and source_path.exists():
            _add_to_section(source_path, "Blocked By", proposal.target_id)
            modified.add(str(source_path))

        # Update target issue: add to ## Blocks
        target_path = issue_files.get(proposal.target_id)
        if target_path and target_path.exists():
            _add_to_section(target_path, "Blocks", proposal.source_id)
            modified.add(str(target_path))

    return sorted(modified)


def _add_to_section(file_path: Path, section_name: str, issue_id: str) -> None:
    """Add an issue ID to a markdown section in a file.

    If the section exists, appends a new list item.
    If the section doesn't exist, creates it before the
    ``## Labels`` or ``## Status`` section, or at the end of the file.

    Args:
        file_path: Path to the issue file
        section_name: Section name (e.g., "Blocked By" or "Blocks")
        issue_id: Issue ID to add (e.g., "FEAT-001")
    """
    content = file_path.read_text(encoding="utf-8")

    # Check if the ID is already in the section
    section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
    section_match = re.search(section_pattern, content, re.MULTILINE | re.IGNORECASE)

    if section_match:
        # Section exists — check if ID already present
        start = section_match.end()
        next_section = re.search(r"^##\s+", content[start:], re.MULTILINE)
        if next_section:
            section_content = content[start : start + next_section.start()]
        else:
            section_content = content[start:]

        if issue_id in section_content:
            return  # Already present

        # Find insertion point: end of section content (before next section or EOF)
        insert_pos = (
            start
            + len(section_content.rstrip())
            + (len(section_content) - len(section_content.rstrip()))
        )
        # Actually, insert at end of the last list item in the section
        # Find the last non-blank line in the section
        section_lines = section_content.rstrip().split("\n")
        last_content_line_offset = 0
        for line in reversed(section_lines):
            if line.strip():
                break
            last_content_line_offset += len(line) + 1

        insert_pos = start + len(section_content.rstrip())
        new_entry = f"\n- {issue_id}"
        content = content[:insert_pos] + new_entry + content[insert_pos:]
    else:
        # Section doesn't exist — create it
        new_section = f"\n## {section_name}\n\n- {issue_id}\n"

        # Try to insert before ## Labels or ## Status
        for anchor in ("## Labels", "## Status"):
            anchor_match = re.search(rf"^{re.escape(anchor)}\s*$", content, re.MULTILINE)
            if anchor_match:
                insert_pos = anchor_match.start()
                content = content[:insert_pos] + new_section + "\n" + content[insert_pos:]
                break
        else:
            # Append at end
            content = content.rstrip() + "\n" + new_section

    file_path.write_text(content, encoding="utf-8")


def _remove_from_section(file_path: Path, section_name: str, issue_id: str) -> bool:
    """Remove an issue ID from a markdown section in a file.

    If the section becomes empty after removal, the entire section is removed.

    Args:
        file_path: Path to the issue file
        section_name: Section name (e.g., "Blocked By" or "Blocks")
        issue_id: Issue ID to remove (e.g., "FEAT-001")

    Returns:
        True if a change was made, False if the ID was not found.
    """
    content = file_path.read_text(encoding="utf-8")

    section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
    section_match = re.search(section_pattern, content, re.MULTILINE | re.IGNORECASE)

    if not section_match:
        return False

    start = section_match.end()
    next_section = re.search(r"^##\s+", content[start:], re.MULTILINE)
    if next_section:
        section_end = start + next_section.start()
    else:
        section_end = len(content)

    section_content = content[start:section_end]

    # Find the line containing this issue ID
    line_pattern = rf"^[-*]\s+\*{{0,2}}{re.escape(issue_id)}\b[^\n]*\n?"
    line_match = re.search(line_pattern, section_content, re.MULTILINE)
    if not line_match:
        return False

    # Remove the line
    new_section_content = (
        section_content[: line_match.start()] + section_content[line_match.end() :]
    )

    # Check if the section is now empty (no list items remaining)
    remaining_items = re.search(r"^[-*]\s+", new_section_content, re.MULTILINE)
    if not remaining_items:
        # Remove entire section (header + content)
        # Include leading newline if present
        remove_start = section_match.start()
        if remove_start > 0 and content[remove_start - 1] == "\n":
            remove_start -= 1
        content = content[:remove_start] + content[section_end:]
    else:
        content = content[:start] + new_section_content + content[section_end:]

    file_path.write_text(content, encoding="utf-8")
    return True


def fix_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
    dry_run: bool = False,
) -> FixResult:
    """Auto-repair broken dependency references.

    Fixes three types of validation issues:
    - Broken refs: removes references to non-existent issues from Blocked By
    - Stale completed refs: removes references to completed issues from Blocked By
    - Missing backlinks: adds missing Blocks entries for bidirectional consistency

    Cycles are explicitly out of scope and are skipped with a count.

    Args:
        issues: List of parsed issue objects
        completed_ids: Set of completed issue IDs
        all_known_ids: Set of all issue IDs that exist on disk
        dry_run: If True, report what would change without modifying files

    Returns:
        FixResult with changes made and files modified
    """
    validation = validate_dependencies(issues, completed_ids, all_known_ids)
    result = FixResult()

    if not validation.has_issues:
        return result

    # Build issue path map
    issue_path_map: dict[str, Path] = {issue.issue_id: issue.path for issue in issues}

    # Fix broken refs: remove from Blocked By
    for issue_id, ref_id in validation.broken_refs:
        path = issue_path_map.get(issue_id)
        if not path or not path.exists():
            continue
        desc = f"Removed broken ref {ref_id} from {issue_id}"
        result.changes.append(desc)
        if not dry_run:
            if _remove_from_section(path, "Blocked By", ref_id):
                result.modified_files.add(str(path))

    # Fix stale completed refs: remove from Blocked By
    for issue_id, ref_id in validation.stale_completed_refs:
        path = issue_path_map.get(issue_id)
        if not path or not path.exists():
            continue
        desc = f"Removed stale ref {ref_id} (completed) from {issue_id}"
        result.changes.append(desc)
        if not dry_run:
            if _remove_from_section(path, "Blocked By", ref_id):
                result.modified_files.add(str(path))

    # Fix missing backlinks: add to Blocks
    for issue_id, ref_id in validation.missing_backlinks:
        target_path = issue_path_map.get(ref_id)
        if not target_path or not target_path.exists():
            continue
        desc = f"Added backlink: {issue_id} to {ref_id}'s Blocks section"
        result.changes.append(desc)
        if not dry_run:
            _add_to_section(target_path, "Blocks", issue_id)
            result.modified_files.add(str(target_path))

    # Report skipped cycles
    result.skipped_cycles = len(validation.cycles)

    return result


def gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]:
    """Scan all issue directories for issue IDs (lightweight, filename-only).

    Scans active-category and completed subdirectories for markdown files
    with issue ID patterns in their filenames.

    Args:
        issues_dir: Path to the issues base directory (e.g., .issues)
        config: Optional project config.  When supplied, active category names
            and the completed-directory name are read from config so that
            custom categories are included.  When omitted, falls back to
            ``["bugs", "features", "enhancements", "completed"]``.

    Returns:
        Set of all issue IDs found across all categories and completed.
    """
    if config is not None:
        subdirs = config.issue_categories + [
            config.get_completed_dir().name,
            config.get_deferred_dir().name,
        ]
    else:
        subdirs = ["bugs", "features", "enhancements", "completed", "deferred"]

    ids: set[str] = set()
    for subdir in subdirs:
        d = issues_dir / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            match = re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)
            if match:
                ids.add(f"{match.group(1)}-{match.group(2)}")
    return ids
