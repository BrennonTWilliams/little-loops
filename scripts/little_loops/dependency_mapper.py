"""Cross-issue dependency discovery and mapping.

Analyzes active issues to discover potential dependencies based on
file overlap and validates existing dependency references for integrity.

Complements dependency_graph.py:
- dependency_graph.py = execution ordering (existing, unchanged)
- dependency_mapper.py = discovery and proposal of new relationships (new)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.dependency_graph import DependencyGraph

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)

# File path patterns for extraction from issue content
_BACKTICK_PATH = re.compile(r"`([^`\s]+\.[a-z]{2,4})`")
_BOLD_FILE_PATH = re.compile(r"\*\*File\*\*:\s*`?([^`\n]+\.[a-z]{2,4})`?")
_STANDALONE_PATH = re.compile(
    r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?:\s|$|:|\))", re.MULTILINE
)
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# File extensions that indicate real source file paths
_SOURCE_EXTENSIONS = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".html", ".css", ".scss", ".sh", ".bash",
    ".sql", ".go", ".rs", ".java", ".kt", ".rb", ".php",
})


@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues.

    Attributes:
        source_id: Issue that would be blocked
        target_id: Issue that would block (the blocker)
        reason: Category of discovery method
        confidence: Score from 0.0 to 1.0
        rationale: Human-readable explanation
        overlapping_files: Files referenced by both issues
    """

    source_id: str
    target_id: str
    reason: str
    confidence: float
    rationale: str
    overlapping_files: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of validating existing dependency references.

    Attributes:
        broken_refs: (issue_id, missing_ref_id) pairs
        missing_backlinks: (issue_id, should_have_backlink_from) pairs
        cycles: Cycle paths from DependencyGraph.detect_cycles()
        stale_completed_refs: (issue_id, completed_ref_id) pairs
    """

    broken_refs: list[tuple[str, str]] = field(default_factory=list)
    missing_backlinks: list[tuple[str, str]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    stale_completed_refs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Return True if any validation problems were found."""
        return bool(
            self.broken_refs
            or self.missing_backlinks
            or self.cycles
            or self.stale_completed_refs
        )


@dataclass
class DependencyReport:
    """Complete dependency analysis report.

    Attributes:
        proposals: Proposed new dependency relationships
        validation: Validation results for existing dependencies
        issue_count: Total issues analyzed
        existing_dep_count: Number of existing dependency edges
    """

    proposals: list[DependencyProposal] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=ValidationResult)
    issue_count: int = 0
    existing_dep_count: int = 0


def extract_file_paths(content: str) -> set[str]:
    """Extract file paths from issue content.

    Searches for file paths in:
    - Backtick-quoted paths: `path/to/file.py`
    - Location section bold paths: **File**: `path/to/file.py`
    - Standalone paths with recognized extensions

    Code fence blocks are stripped before extraction to avoid
    matching paths inside example code.

    Args:
        content: Issue file content

    Returns:
        Set of file paths found in the content
    """
    if not content:
        return set()

    # Strip code fences to avoid matching example paths
    stripped = _CODE_FENCE.sub("", content)

    paths: set[str] = set()
    for pattern in (_BOLD_FILE_PATH, _BACKTICK_PATH, _STANDALONE_PATH):
        for match in pattern.finditer(stripped):
            path = match.group(1).strip()
            # Only include paths with directory separators or recognized extensions
            ext = Path(path).suffix.lower()
            if ext in _SOURCE_EXTENSIONS and ("/" in path or ext):
                paths.add(path)
    return paths


def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
) -> list[DependencyProposal]:
    """Find issues that reference overlapping files and propose dependencies.

    For each pair of issues where both reference the same file(s), proposes
    a dependency where the lower-priority (or later ID at same priority)
    issue is blocked by the higher-priority (or earlier ID) issue.

    Pairs that already have a dependency relationship are skipped.

    Args:
        issues: List of parsed issue objects
        issue_contents: Mapping from issue_id to file content

    Returns:
        List of proposed dependencies with file overlap rationale
    """
    # Build existing dependency set for skip check
    existing_deps: set[tuple[str, str]] = set()
    for issue in issues:
        for blocker_id in issue.blocked_by:
            existing_deps.add((issue.issue_id, blocker_id))

    # Extract file paths per issue
    issue_paths: dict[str, set[str]] = {}
    for issue in issues:
        content = issue_contents.get(issue.issue_id, "")
        paths = extract_file_paths(content)
        if paths:
            issue_paths[issue.issue_id] = paths

    proposals: list[DependencyProposal] = []
    issue_ids = sorted(issue_paths.keys())

    for i, id_a in enumerate(issue_ids):
        for id_b in issue_ids[i + 1 :]:
            overlap = issue_paths[id_a] & issue_paths[id_b]
            if not overlap:
                continue

            # Determine direction: higher priority (lower number) blocks lower priority
            issue_a = next(iss for iss in issues if iss.issue_id == id_a)
            issue_b = next(iss for iss in issues if iss.issue_id == id_b)

            if (issue_a.priority_int, id_a) <= (issue_b.priority_int, id_b):
                target_id, source_id = id_a, id_b
            else:
                target_id, source_id = id_b, id_a

            # Skip if dependency already exists (in either direction)
            if (source_id, target_id) in existing_deps:
                continue
            if (target_id, source_id) in existing_deps:
                continue

            min_paths = min(len(issue_paths[id_a]), len(issue_paths[id_b]))
            confidence = len(overlap) / min_paths if min_paths > 0 else 0.0

            overlap_list = sorted(overlap)
            rationale = (
                f"{source_id} and {target_id} both reference "
                f"{', '.join(overlap_list[:3])}"
                f"{' and more' if len(overlap_list) > 3 else ''}. "
                f"{target_id} has higher priority and should be completed first."
            )

            proposals.append(
                DependencyProposal(
                    source_id=source_id,
                    target_id=target_id,
                    reason="file_overlap",
                    confidence=round(confidence, 2),
                    rationale=rationale,
                    overlapping_files=overlap_list,
                )
            )

    # Sort by confidence descending
    proposals.sort(key=lambda p: -p.confidence)
    return proposals


def validate_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
) -> ValidationResult:
    """Validate existing dependency references for integrity.

    Checks:
    - Broken refs: blocked_by entries referencing nonexistent issues
    - Missing backlinks: A blocks B but B doesn't list A in blocked_by
    - Cycles: circular dependency chains
    - Stale completed refs: blocked_by entries referencing completed issues

    Args:
        issues: List of parsed issue objects
        completed_ids: Set of completed issue IDs

    Returns:
        ValidationResult with all detected problems
    """
    completed = completed_ids or set()
    result = ValidationResult()

    active_ids = {issue.issue_id for issue in issues}
    all_known = active_ids | completed

    # Build lookup maps
    blocked_by_map: dict[str, set[str]] = {}
    blocks_map: dict[str, set[str]] = {}
    for issue in issues:
        blocked_by_map[issue.issue_id] = set(issue.blocked_by)
        blocks_map[issue.issue_id] = set(issue.blocks)

    for issue in issues:
        for ref_id in issue.blocked_by:
            if ref_id not in all_known:
                result.broken_refs.append((issue.issue_id, ref_id))
            elif ref_id in completed:
                result.stale_completed_refs.append((issue.issue_id, ref_id))

        # Check backlinks: if A.blocked_by contains B, then B.blocks should contain A
        for ref_id in issue.blocked_by:
            if ref_id in active_ids:
                target_blocks = blocks_map.get(ref_id, set())
                if issue.issue_id not in target_blocks:
                    result.missing_backlinks.append((issue.issue_id, ref_id))

    # Cycle detection using DependencyGraph
    graph = DependencyGraph.from_issues(issues, completed)
    result.cycles = graph.detect_cycles()

    return result


def analyze_dependencies(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
    completed_ids: set[str] | None = None,
) -> DependencyReport:
    """Run full dependency analysis: discovery and validation.

    Args:
        issues: List of parsed issue objects
        issue_contents: Mapping from issue_id to file content
        completed_ids: Set of completed issue IDs

    Returns:
        Comprehensive dependency report
    """
    proposals = find_file_overlaps(issues, issue_contents)
    validation = validate_dependencies(issues, completed_ids)

    existing_dep_count = sum(len(issue.blocked_by) for issue in issues)

    return DependencyReport(
        proposals=proposals,
        validation=validation,
        issue_count=len(issues),
        existing_dep_count=existing_dep_count,
    )


def format_report(report: DependencyReport) -> str:
    """Format a dependency report as human-readable markdown.

    Args:
        report: The analysis report to format

    Returns:
        Markdown-formatted report string
    """
    lines: list[str] = []
    lines.append("# Dependency Analysis Report")
    lines.append("")
    lines.append(f"- **Issues analyzed**: {report.issue_count}")
    lines.append(f"- **Existing dependencies**: {report.existing_dep_count}")
    lines.append(f"- **Proposed new dependencies**: {len(report.proposals)}")
    lines.append(f"- **Validation issues**: "
                 f"{'Yes' if report.validation.has_issues else 'None'}")
    lines.append("")

    # Proposals section
    if report.proposals:
        lines.append("## Proposed Dependencies")
        lines.append("")
        lines.append("| # | Source (blocked) | Target (blocker) | Reason | Confidence | Rationale |")
        lines.append("|---|-----------------|-----------------|--------|------------|-----------|")
        for i, p in enumerate(report.proposals, 1):
            lines.append(
                f"| {i} | {p.source_id} | {p.target_id} | "
                f"{p.reason} | {p.confidence:.0%} | {p.rationale} |"
            )
        lines.append("")

    # Validation section
    v = report.validation
    if v.has_issues:
        lines.append("## Validation Issues")
        lines.append("")

        if v.broken_refs:
            lines.append("### Broken References")
            lines.append("")
            for issue_id, ref_id in v.broken_refs:
                lines.append(f"- {issue_id}: references nonexistent {ref_id}")
            lines.append("")

        if v.missing_backlinks:
            lines.append("### Missing Backlinks")
            lines.append("")
            for issue_id, ref_id in v.missing_backlinks:
                lines.append(
                    f"- {issue_id} is blocked by {ref_id}, "
                    f"but {ref_id} does not list {issue_id} in Blocks"
                )
            lines.append("")

        if v.cycles:
            lines.append("### Dependency Cycles")
            lines.append("")
            for cycle in v.cycles:
                lines.append(f"- {' -> '.join(cycle)}")
            lines.append("")

        if v.stale_completed_refs:
            lines.append("### Stale References (to completed issues)")
            lines.append("")
            for issue_id, ref_id in v.stale_completed_refs:
                lines.append(
                    f"- {issue_id}: blocked by {ref_id} (completed)"
                )
            lines.append("")

    if not report.proposals and not v.has_issues:
        lines.append("No dependency proposals or validation issues found.")
        lines.append("")

    return "\n".join(lines)


def format_mermaid(
    issues: list[IssueInfo],
    proposals: list[DependencyProposal] | None = None,
) -> str:
    """Generate a Mermaid dependency graph diagram.

    Shows existing dependencies as solid arrows and proposed
    dependencies as dashed arrows.

    Args:
        issues: List of parsed issue objects
        proposals: Optional proposed dependencies to include

    Returns:
        Mermaid graph definition string
    """
    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("graph TD")

    # Add nodes
    for issue in sorted(issues, key=lambda i: (i.priority_int, i.issue_id)):
        label = f"{issue.issue_id}: {issue.title[:30]}"
        lines.append(f"    {issue.issue_id}[\"{label}\"]")

    # Add existing edges (solid arrows)
    for issue in issues:
        for blocker_id in issue.blocked_by:
            # Only show edges where both nodes are in the issue set
            if any(i.issue_id == blocker_id for i in issues):
                lines.append(f"    {blocker_id} --> {issue.issue_id}")

    # Add proposed edges (dashed arrows)
    if proposals:
        for p in proposals:
            if (
                any(i.issue_id == p.target_id for i in issues)
                and any(i.issue_id == p.source_id for i in issues)
            ):
                lines.append(f"    {p.target_id} -.-> {p.source_id}")

    lines.append("```")
    return "\n".join(lines)


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
        insert_pos = start + len(section_content.rstrip()) + (
            len(section_content) - len(section_content.rstrip())
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
            anchor_match = re.search(
                rf"^{re.escape(anchor)}\s*$", content, re.MULTILINE
            )
            if anchor_match:
                insert_pos = anchor_match.start()
                content = content[:insert_pos] + new_section + "\n" + content[insert_pos:]
                break
        else:
            # Append at end
            content = content.rstrip() + "\n" + new_section

    file_path.write_text(content, encoding="utf-8")
