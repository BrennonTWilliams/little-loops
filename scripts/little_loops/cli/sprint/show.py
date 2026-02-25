"""ll-sprint show subcommand and dependency visualization renderers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli.sprint._helpers import (
    _build_issue_contents,
    _render_dependency_analysis,
    _render_execution_plan,
)
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention
from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.dependency_graph import WaveContentionNote
    from little_loops.sprint import SprintManager


def _render_dependency_graph(
    waves: list[list[Any]],
    dep_graph: DependencyGraph,
) -> str:
    """Render ASCII dependency graph.

    Args:
        waves: List of execution waves
        dep_graph: DependencyGraph for looking up relationships

    Returns:
        Formatted string showing dependency arrows
    """
    if not waves or len(waves) <= 1:
        return ""

    # Don't render graph if there are no actual dependency edges
    # (waves > 1 can happen from file overlap splitting alone)
    all_ids = {issue.issue_id for wave in waves for issue in wave}
    has_edges = any(dep_graph.blocks.get(issue_id, set()) & all_ids for issue_id in all_ids)
    if not has_edges:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("DEPENDENCY GRAPH")
    lines.append("=" * 70)
    lines.append("")

    # Build chains: track which issues block what
    # Show each independent chain on its own line
    chains: list[str] = []
    visited: set[str] = set()

    def build_chain(issue_id: str) -> str:
        """Recursively build chain string from issue."""
        if issue_id in visited:
            return issue_id
        visited.add(issue_id)

        blocked_issues = sorted(dep_graph.blocks.get(issue_id, set()))
        if not blocked_issues:
            return issue_id

        if len(blocked_issues) == 1:
            return f"{issue_id} \u2500\u2500\u2192 {build_chain(blocked_issues[0])}"
        else:
            # Multiple branches - show first inline, note others
            result = f"{issue_id} \u2500\u2500\u2192 {build_chain(blocked_issues[0])}"
            for other in blocked_issues[1:]:
                if other not in visited:
                    chains.append(f"  {issue_id} \u2500\u2500\u2192 {build_chain(other)}")
            return result

    # Find root issues structurally (not blocked by anything in this graph)
    roots = [iid for iid in sorted(all_ids) if not (dep_graph.blocked_by.get(iid, set()) & all_ids)]

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            if chain and "──→" in chain:
                chains.append(f"  {chain}")

    lines.extend(chains)
    lines.append("")
    lines.append("Legend: \u2500\u2500\u2192 blocks (must complete before)")

    return "\n".join(lines)


def _render_health_summary(
    waves: list[list[Any]],
    contention_notes: list[WaveContentionNote | None] | None,
    has_cycles: bool,
    invalid: set[str],
    dep_report: Any | None = None,
    issue_to_wave: dict[str, int] | None = None,
) -> str:
    """Render a one-line sprint health summary.

    Returns:
        Health summary string like "OK -- 5 issues in 1 wave, contention serialized"
    """
    total_issues = sum(len(w) for w in waves)

    if has_cycles:
        return "BLOCKED -- dependency cycles detected"

    if invalid:
        return f"WARNING -- {len(invalid)} issue(s) not found on disk"

    # Check for novel (unsatisfied) high-confidence proposals
    if dep_report and dep_report.proposals and issue_to_wave is not None:
        novel_count = 0
        for p in dep_report.proposals:
            target_wave = issue_to_wave.get(p.target_id)
            source_wave = issue_to_wave.get(p.source_id)
            if target_wave is None or source_wave is None or target_wave >= source_wave:
                if p.confidence >= 0.5:
                    novel_count += 1
        if novel_count > 0:
            return f"REVIEW -- {novel_count} potential dependency(ies) to review"

    # Count logical waves (group contention sub-waves)
    notes = contention_notes or [None] * len(waves)
    logical_count = 0
    has_contention = False
    prev_parent: int | None = None
    for idx in range(len(waves)):
        note = notes[idx] if idx < len(notes) else None
        if note is not None:
            has_contention = True
            if prev_parent is None or note.parent_wave_index != prev_parent:
                logical_count += 1
                prev_parent = note.parent_wave_index
        else:
            logical_count += 1
            prev_parent = None

    wave_word = "wave" if logical_count == 1 else "waves"
    suffix = ", overlap serialized" if has_contention else ", all parallelizable"
    if logical_count == 1 and total_issues == 1:
        suffix = ""

    return f"OK -- {total_issues} issues in {logical_count} {wave_word}{suffix}"


def _cmd_sprint_show(args: argparse.Namespace, manager: SprintManager) -> int:
    """Show sprint details with dependency visualization."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(list(valid.keys()))
    dep_graph: DependencyGraph | None = None
    waves: list[list[Any]] = []
    contention_notes: list[WaveContentionNote | None] | None = None
    has_cycles = False

    # Gather all issue IDs on disk to avoid false "nonexistent" warnings
    from little_loops.dependency_mapper import gather_all_issue_ids

    config = manager.config
    issues_dir = config.project_root / config.issues.base_dir if config else Path(".issues")
    all_known_ids = gather_all_issue_ids(issues_dir)

    if issue_infos:
        dep_graph = DependencyGraph.from_issues(issue_infos, all_known_ids=all_known_ids)
        has_cycles = dep_graph.has_cycles()

        if not has_cycles:
            waves = dep_graph.get_execution_waves()
            waves, contention_notes = refine_waves_for_contention(waves)

    print(f"Sprint: {sprint.name}")
    print(f"Description: {sprint.description or '(none)'}")
    print(f"Created: {sprint.created}")

    # Options on a single compact line right after metadata
    if sprint.options:
        opts = sprint.options
        print(
            f"Options: max_workers={opts.max_workers}, timeout={opts.timeout}s, max_iterations={opts.max_iterations}"
        )

    # Dependency analysis (ENH-301) - run before health summary so we can reference it
    dep_report: Any = None
    issue_to_wave: dict[str, int] = {}
    if issue_infos and not args.skip_analysis:
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents, all_known_ids=all_known_ids)

        # Build wave ordering map so we can filter already-satisfied proposals
        for wave_idx, wave in enumerate(waves):
            for issue in wave:
                issue_to_wave[issue.issue_id] = wave_idx

    # Sprint health summary
    if waves:
        health = _render_health_summary(
            waves,
            contention_notes,
            has_cycles,
            invalid,
            dep_report=dep_report,
            issue_to_wave=issue_to_wave if issue_to_wave else None,
        )
        print(f"Sprint health: {health}")

    # Show execution plan if we have dependency info and no cycles
    if waves and dep_graph:
        print(_render_execution_plan(waves, dep_graph, contention_notes))
        print(_render_dependency_graph(waves, dep_graph))
    else:
        # Fallback to simple list if no valid issues or cycles
        print(f"Issues ({len(sprint.issues)}):")
        for issue_id in sprint.issues:
            status = "valid" if issue_id in valid else "NOT FOUND"
            print(f"  - {issue_id} ({status})")

        # Warn about cycles if detected
        if has_cycles and dep_graph:
            cycles = dep_graph.detect_cycles()
            print("\nWarning: Dependency cycles detected:")
            for cycle in cycles:
                print(f"  {' -> '.join(cycle)}")

    # Render dependency analysis output
    if dep_report is not None:
        _render_dependency_analysis(
            dep_report, logger, issue_to_wave=issue_to_wave if issue_to_wave else None
        )

    if invalid:
        print(f"\nWarning: {len(invalid)} issue(s) not found")

    return 0
