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
_STANDALONE_PATH = re.compile(r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?:\s|$|:|\))", re.MULTILINE)
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# File extensions that indicate real source file paths
_SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".html",
        ".css",
        ".scss",
        ".sh",
        ".bash",
        ".sql",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".php",
    }
)

# Semantic target extraction patterns
_PASCAL_CASE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b")
_FUNCTION_REF = re.compile(r"`(\w+)\(\)`")
_COMPONENT_SCOPE = re.compile(
    r"(?:component|module|class|widget|section)[:\s]+[`\"']?([a-zA-Z0-9_./\-]{3,})[`\"']?",
    re.IGNORECASE,
)

# UI region / section keywords mapped to canonical names
_SECTION_KEYWORDS: dict[str, frozenset[str]] = {
    "header": frozenset({"header", "heading", "title bar", "top bar", "nav", "navbar", "toolbar"}),
    "body": frozenset({"body", "content", "main", "droppable", "list", "table", "grid"}),
    "footer": frozenset({"footer", "bottom", "status bar", "action bar"}),
    "sidebar": frozenset({"sidebar", "side panel", "drawer", "menu"}),
    "card": frozenset({"card", "tile", "item", "row", "entry"}),
    "modal": frozenset({"modal", "dialog", "popup", "overlay", "sheet"}),
    "form": frozenset({"form", "input", "field", "editor", "picker"}),
}

# Modification type classification keywords
_MODIFICATION_TYPES: dict[str, frozenset[str]] = {
    "structural": frozenset(
        {
            "extract",
            "split",
            "refactor",
            "restructure",
            "reorganize",
            "create new component",
            "break out",
            "separate",
            "decompose",
        }
    ),
    "infrastructure": frozenset(
        {
            "enable",
            "hook",
            "handler",
            "event",
            "listener",
            "provider",
            "context",
            "store",
            "state management",
            "routing",
            "middleware",
            "dragging",
            "drag",
            "drop",
            "dnd",
        }
    ),
    "enhancement": frozenset(
        {
            "add button",
            "add field",
            "add column",
            "add stats",
            "add icon",
            "add toggle",
            "display",
            "show",
            "render",
            "style",
            "format",
            "empty state",
            "placeholder",
            "tooltip",
            "badge",
        }
    ),
}


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
        conflict_score: Semantic conflict score from 0.0 to 1.0
    """

    source_id: str
    target_id: str
    reason: str
    confidence: float
    rationale: str
    overlapping_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.5


@dataclass
class ParallelSafePair:
    """A pair of issues that share files but can safely run in parallel.

    Attributes:
        issue_a: First issue ID
        issue_b: Second issue ID
        shared_files: Files referenced by both issues
        conflict_score: Semantic conflict score (< 0.4)
        reason: Why these are parallel-safe
    """

    issue_a: str
    issue_b: str
    shared_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.0
    reason: str = ""


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
            self.broken_refs or self.missing_backlinks or self.cycles or self.stale_completed_refs
        )


@dataclass
class DependencyReport:
    """Complete dependency analysis report.

    Attributes:
        proposals: Proposed new dependency relationships
        parallel_safe: Pairs of issues that share files but can run in parallel
        validation: Validation results for existing dependencies
        issue_count: Total issues analyzed
        existing_dep_count: Number of existing dependency edges
    """

    proposals: list[DependencyProposal] = field(default_factory=list)
    parallel_safe: list[ParallelSafePair] = field(default_factory=list)
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


def _extract_semantic_targets(content: str) -> set[str]:
    """Extract component and function references from issue content.

    Identifies PascalCase component names, function references,
    and explicitly mentioned component/module scopes.

    Args:
        content: Issue file content

    Returns:
        Set of normalized semantic target names
    """
    if not content:
        return set()

    stripped = _CODE_FENCE.sub("", content)
    targets: set[str] = set()

    for match in _PASCAL_CASE.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _FUNCTION_REF.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _COMPONENT_SCOPE.finditer(stripped):
        targets.add(match.group(1).lower())

    return targets


def _extract_section_mentions(content: str) -> set[str]:
    """Extract UI region/section references from issue content.

    Maps keywords like "header", "body", "sidebar" to canonical
    section names using word-boundary matching.

    Args:
        content: Issue file content

    Returns:
        Set of canonical section names mentioned
    """
    if not content:
        return set()

    content_lower = content.lower()
    sections: set[str] = set()

    for section_name, keywords in _SECTION_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary for single words, substring for multi-word phrases
            if " " in keyword:
                if keyword in content_lower:
                    sections.add(section_name)
                    break
            else:
                if re.search(rf"\b{re.escape(keyword)}\b", content_lower):
                    sections.add(section_name)
                    break

    return sections


def _classify_modification_type(content: str) -> str:
    """Classify the modification type of an issue.

    Returns one of: "structural", "infrastructure", "enhancement".
    Falls back to "enhancement" if no clear match.

    Args:
        content: Issue file content

    Returns:
        Modification type classification string
    """
    if not content:
        return "enhancement"

    content_lower = content.lower()

    for mod_type in ("structural", "infrastructure", "enhancement"):
        keywords = _MODIFICATION_TYPES[mod_type]
        for keyword in keywords:
            if keyword in content_lower:
                return mod_type

    return "enhancement"


def compute_conflict_score(
    content_a: str,
    content_b: str,
) -> float:
    """Compute semantic conflict score between two issues.

    Combines three signals:
    - Semantic target overlap (component/function names): weight 0.5
    - Section mention overlap (UI regions): weight 0.3
    - Modification type match: weight 0.2

    Args:
        content_a: First issue's file content
        content_b: Second issue's file content

    Returns:
        Conflict score from 0.0 (parallel-safe) to 1.0 (definite conflict)
    """
    targets_a = _extract_semantic_targets(content_a)
    targets_b = _extract_semantic_targets(content_b)

    sections_a = _extract_section_mentions(content_a)
    sections_b = _extract_section_mentions(content_b)

    type_a = _classify_modification_type(content_a)
    type_b = _classify_modification_type(content_b)

    # Signal 1: Semantic target overlap (0.0 - 1.0)
    if targets_a and targets_b:
        target_union = len(targets_a | targets_b)
        target_score = len(targets_a & targets_b) / target_union if target_union > 0 else 0.0
    else:
        target_score = 0.5  # Unknown — default to moderate

    # Signal 2: Section overlap (0.0 or 1.0)
    if sections_a and sections_b:
        section_score = 1.0 if sections_a & sections_b else 0.0
    else:
        section_score = 0.5  # Unknown

    # Signal 3: Modification type match (0.0 or 1.0)
    type_score = 1.0 if type_a == type_b else 0.0

    return round(target_score * 0.5 + section_score * 0.3 + type_score * 0.2, 2)


def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
) -> tuple[list[DependencyProposal], list[ParallelSafePair]]:
    """Find issues that reference overlapping files and propose dependencies.

    For each pair of issues where both reference the same file(s), computes
    a semantic conflict score. High-conflict pairs get dependency proposals;
    low-conflict pairs are reported as parallel-safe.

    Pairs that already have a dependency relationship are skipped.

    Args:
        issues: List of parsed issue objects
        issue_contents: Mapping from issue_id to file content

    Returns:
        Tuple of (proposed dependencies, parallel-safe pairs)
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
    parallel_safe: list[ParallelSafePair] = []
    issue_ids = sorted(issue_paths.keys())

    _type_order = {"structural": 0, "infrastructure": 1, "enhancement": 2}

    for i, id_a in enumerate(issue_ids):
        for id_b in issue_ids[i + 1 :]:
            overlap = issue_paths[id_a] & issue_paths[id_b]
            if not overlap:
                continue

            # Skip if dependency already exists (in either direction)
            if (id_a, id_b) in existing_deps or (id_b, id_a) in existing_deps:
                continue

            content_a = issue_contents.get(id_a, "")
            content_b = issue_contents.get(id_b, "")
            conflict = compute_conflict_score(content_a, content_b)

            overlap_list = sorted(overlap)

            # Low-conflict pairs are parallel-safe
            if conflict < 0.4:
                sections_a = _extract_section_mentions(content_a)
                sections_b = _extract_section_mentions(content_b)
                if sections_a and sections_b:
                    reason = (
                        f"Different sections ({', '.join(sorted(sections_a))}"
                        f" vs {', '.join(sorted(sections_b))})"
                    )
                else:
                    reason = "Low semantic conflict score"
                parallel_safe.append(
                    ParallelSafePair(
                        issue_a=id_a,
                        issue_b=id_b,
                        shared_files=overlap_list,
                        conflict_score=conflict,
                        reason=reason,
                    )
                )
                continue

            # Determine direction for high-conflict pairs
            issue_a = next(iss for iss in issues if iss.issue_id == id_a)
            issue_b = next(iss for iss in issues if iss.issue_id == id_b)

            confidence_modifier = 1.0

            if issue_a.priority_int != issue_b.priority_int:
                # Different priorities: higher priority blocks lower
                if issue_a.priority_int < issue_b.priority_int:
                    target_id, source_id = id_a, id_b
                else:
                    target_id, source_id = id_b, id_a
            else:
                # Same priority: use modification type ordering
                type_a = _classify_modification_type(content_a)
                type_b = _classify_modification_type(content_b)
                order_a = _type_order.get(type_a, 2)
                order_b = _type_order.get(type_b, 2)

                if order_a != order_b:
                    if order_a < order_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                else:
                    # Fall back to ID ordering with reduced confidence
                    if id_a < id_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                    confidence_modifier = 0.5

            min_paths = min(len(issue_paths[id_a]), len(issue_paths[id_b]))
            confidence = len(overlap) / min_paths if min_paths > 0 else 0.0
            confidence *= confidence_modifier

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
                    conflict_score=conflict,
                )
            )

    # Sort by confidence descending
    proposals.sort(key=lambda p: -p.confidence)
    return proposals, parallel_safe


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
    proposals, parallel_safe = find_file_overlaps(issues, issue_contents)
    validation = validate_dependencies(issues, completed_ids)

    existing_dep_count = sum(len(issue.blocked_by) for issue in issues)

    return DependencyReport(
        proposals=proposals,
        parallel_safe=parallel_safe,
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
    lines.append(f"- **Parallel-safe pairs**: {len(report.parallel_safe)}")
    lines.append(f"- **Validation issues**: {'Yes' if report.validation.has_issues else 'None'}")
    lines.append("")

    # Proposals section
    if report.proposals:
        lines.append("## Proposed Dependencies")
        lines.append("")
        lines.append(
            "| # | Source (blocked) | Target (blocker) | Reason "
            "| Conflict | Confidence | Rationale |"
        )
        lines.append(
            "|---|-----------------|-----------------|--------|----------|------------|-----------|"
        )
        for i, p in enumerate(report.proposals, 1):
            if p.conflict_score >= 0.7:
                conflict_level = "HIGH"
            elif p.conflict_score >= 0.4:
                conflict_level = "MEDIUM"
            else:
                conflict_level = "LOW"
            lines.append(
                f"| {i} | {p.source_id} | {p.target_id} | "
                f"{p.reason} | {conflict_level} | {p.confidence:.0%} | {p.rationale} |"
            )
        lines.append("")

    # Parallel-safe section
    if report.parallel_safe:
        lines.append("## Parallel Execution Safe")
        lines.append("")
        lines.append("| Issue A | Issue B | Shared Files | Conflict Score | Reason |")
        lines.append("|---------|---------|--------------|---------------|--------|")
        for pair in report.parallel_safe:
            files_str = ", ".join(pair.shared_files[:3])
            if len(pair.shared_files) > 3:
                files_str += " and more"
            lines.append(
                f"| {pair.issue_a} | {pair.issue_b} | "
                f"{files_str} | {pair.conflict_score:.0%} | {pair.reason} |"
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
                lines.append(f"- {issue_id}: blocked by {ref_id} (completed)")
            lines.append("")

    if not report.proposals and not report.parallel_safe and not v.has_issues:
        lines.append("No dependency proposals or validation issues found.")
        lines.append("")

    return "\n".join(lines)


def format_text_graph(
    issues: list[IssueInfo],
    proposals: list[DependencyProposal] | None = None,
) -> str:
    """Generate an ASCII dependency graph diagram.

    Shows existing dependencies as solid arrows and proposed
    dependencies as dashed arrows.

    Args:
        issues: List of parsed issue objects
        proposals: Optional proposed dependencies to include

    Returns:
        Text graph string readable in the terminal
    """
    if not issues:
        return "(no issues)"

    issue_ids = {i.issue_id for i in issues}
    sorted_issues = sorted(issues, key=lambda i: (i.priority_int, i.issue_id))

    # Build adjacency: blocker -> list of blocked issues
    blocks: dict[str, list[str]] = {}
    for issue in sorted_issues:
        for blocker_id in issue.blocked_by:
            if blocker_id in issue_ids:
                blocks.setdefault(blocker_id, []).append(issue.issue_id)

    # Add proposed edges
    proposed_edges: set[tuple[str, str]] = set()
    if proposals:
        for p in proposals:
            if p.target_id in issue_ids and p.source_id in issue_ids:
                blocks.setdefault(p.target_id, []).append(p.source_id)
                proposed_edges.add((p.target_id, p.source_id))

    # Build chains from roots (issues not blocked by anything in the set)
    blocked_ids: set[str] = set()
    for targets in blocks.values():
        blocked_ids.update(targets)
    roots = [i.issue_id for i in sorted_issues if i.issue_id not in blocked_ids]

    visited: set[str] = set()
    chains: list[str] = []

    def build_chain(issue_id: str) -> str:
        if issue_id in visited:
            return issue_id
        visited.add(issue_id)
        targets = sorted(blocks.get(issue_id, []))
        if not targets:
            return issue_id
        if len(targets) == 1:
            arrow = "-.→" if (issue_id, targets[0]) in proposed_edges else "──→"
            return f"{issue_id} {arrow} {build_chain(targets[0])}"
        # Multiple branches: first inline, rest as separate chains
        arrow = "-.→" if (issue_id, targets[0]) in proposed_edges else "──→"
        result = f"{issue_id} {arrow} {build_chain(targets[0])}"
        for other in targets[1:]:
            if other not in visited:
                arrow_other = "-.→" if (issue_id, other) in proposed_edges else "──→"
                chains.append(f"  {issue_id} {arrow_other} {build_chain(other)}")
        return result

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            chains.append(f"  {chain}")

    # Isolated issues (not in any chain)
    for issue in sorted_issues:
        if issue.issue_id not in visited:
            chains.append(f"  {issue.issue_id}")

    lines: list[str] = list(chains)

    if any("──→" in c for c in chains) or any("-.→" in c for c in chains):
        lines.append("")
        legend_parts = []
        if any("──→" in c for c in chains):
            legend_parts.append("──→ blocks")
        if any("-.→" in c for c in chains):
            legend_parts.append("-.→ proposed")
        lines.append(f"Legend: {', '.join(legend_parts)}")

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
