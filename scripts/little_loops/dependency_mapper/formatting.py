"""Dependency report formatting functions.

Functions for formatting dependency analysis results as human-readable
markdown text and ASCII dependency graphs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from little_loops.dependency_mapper.models import DependencyProposal, DependencyReport

if TYPE_CHECKING:
    from little_loops.config import DependencyMappingConfig
    from little_loops.issue_parser import IssueInfo


def format_report(
    report: DependencyReport,
    *,
    config: DependencyMappingConfig | None = None,
) -> str:
    """Format a dependency report as human-readable markdown.

    Args:
        report: The analysis report to format
        config: Optional dependency mapping config for custom thresholds.

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
        high_threshold = config.high_conflict_threshold if config else 0.7
        conflict_threshold = config.conflict_threshold if config else 0.4
        for i, p in enumerate(report.proposals, 1):
            if p.conflict_score >= high_threshold:
                conflict_level = "HIGH"
            elif p.conflict_score >= conflict_threshold:
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
