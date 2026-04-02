"""ll-sprint show subcommand and dependency visualization renderers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli.output import colorize, format_relative_time, print_json, terminal_width
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

    width = terminal_width()
    lines: list[str] = []
    header_text = "Dependency Graph"
    fill = "\u2500" * max(0, width - len(header_text) - 4)
    lines.append("")
    lines.append(f"\u2500\u2500 {header_text} {fill}")
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

    _STATUS_COLOR = {"OK": "32", "REVIEW": "33", "WARNING": "38;5;208", "BLOCKED": "31"}

    if has_cycles:
        return f"{colorize('BLOCKED', _STATUS_COLOR['BLOCKED'])} -- dependency cycles detected"

    if invalid:
        return f"{colorize('WARNING', _STATUS_COLOR['WARNING'])} -- {len(invalid)} issue(s) not found on disk"

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
            return f"{colorize('REVIEW', _STATUS_COLOR['REVIEW'])} -- {novel_count} potential dependency(ies) to review"

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

    return f"{colorize('OK', _STATUS_COLOR['OK'])} -- {total_issues} issues in {logical_count} {wave_word}{suffix}"


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
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)

    if issue_infos:
        dep_graph = DependencyGraph.from_issues(issue_infos, all_known_ids=all_known_ids)
        has_cycles = dep_graph.has_cycles()

        if not has_cycles:
            waves = dep_graph.get_execution_waves()
            dep_config = config.dependency_mapping if config else None
            waves, contention_notes = refine_waves_for_contention(waves, config=dep_config)

    # JSON early-exit
    if getattr(args, "json", False):
        return _show_json(sprint, issue_infos, waves, contention_notes, has_cycles, dep_graph)

    print(f"{colorize('Sprint:', '1')} {sprint.name}")
    if sprint.description:
        print(f"Description: {sprint.description}")
    print(f"Created: {_format_created(sprint.created)}")

    # Options on a single compact line right after metadata
    if sprint.options:
        opts = sprint.options
        print(
            f"Options: max_workers={opts.max_workers}, timeout={opts.timeout}s, max_iterations={opts.max_iterations}"
        )

    # Sprint run state from .sprint-state.json
    _print_run_state(sprint.name)

    # Dependency analysis (ENH-301) - run before health summary so we can reference it
    dep_report: Any = None
    issue_to_wave: dict[str, int] = {}
    if issue_infos and not args.skip_analysis:
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(
            issue_infos, issue_contents, all_known_ids=all_known_ids, config=dep_config
        )

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

        # Composition breakdown
        _print_composition(issue_infos)

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
            dep_report,
            logger,
            issue_to_wave=issue_to_wave if issue_to_wave else None,
            config=dep_config,
        )

    if invalid:
        print(f"\nWarning: {len(invalid)} issue(s) not found")

    return 0


# ---------------------------------------------------------------------------
# Helper functions for enhanced show output (ENH-923)
# ---------------------------------------------------------------------------


def _format_created(iso_str: str) -> str:
    """Format an ISO 8601 created timestamp as a human-friendly string."""
    import time
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        formatted = dt.strftime("%Y-%m-%d %H:%M UTC")
        elapsed = time.time() - dt.timestamp()
        if elapsed >= 0:
            return f"{formatted} ({format_relative_time(elapsed)})"
        return formatted
    except (ValueError, OSError):
        return iso_str


def _print_composition(issue_infos: list[Any]) -> None:
    """Print type/priority composition breakdown."""
    if not issue_infos:
        return
    from collections import Counter

    types: Counter[str] = Counter()
    priorities: Counter[str] = Counter()
    for info in issue_infos:
        issue_type = info.issue_id.split("-", 1)[0]
        types[issue_type] += 1
        if info.priority:
            priorities[info.priority] += 1

    type_parts = [f"{count} {t}" for t, count in sorted(types.items())]
    prio_parts = [f"{p}: {count}" for p, count in sorted(priorities.items())]
    print(f"Composition: {', '.join(type_parts)}  |  {', '.join(prio_parts)}")


def _print_run_state(sprint_name: str) -> None:
    """Print last run state if .sprint-state.json exists for this sprint."""
    import json

    state_file = Path.cwd() / ".sprint-state.json"
    if not state_file.exists():
        return
    try:
        data = json.loads(state_file.read_text())
        if data.get("sprint_name") != sprint_name:
            return
        completed = data.get("completed_issues", [])
        failed = data.get("failed_issues", {})
        skipped = data.get("skipped_blocked_issues", {})
        total = len(completed) + len(failed) + len(skipped)

        started = data.get("started_at", "")
        date_str = started[:10] if started else "unknown"

        parts = [f"{len(completed)} completed"]
        if failed:
            failed_ids = ", ".join(sorted(failed.keys()))
            parts.append(f"{len(failed)} failed ({failed_ids})")
        if skipped:
            parts.append(f"{len(skipped)} skipped")
        print(f"Last run: {date_str} \u2014 {', '.join(parts)} of {total}")
    except (json.JSONDecodeError, OSError):
        pass


def _show_json(
    sprint: Any,
    issue_infos: list[Any],
    waves: list[list[Any]],
    contention_notes: Any,
    has_cycles: bool,
    dep_graph: Any,
) -> int:
    """Render sprint show output as JSON."""
    issues_data = []
    for info in issue_infos:
        issues_data.append(
            {
                "id": info.issue_id,
                "title": info.title,
                "priority": info.priority,
                "path": str(info.path),
                "confidence_score": info.confidence_score,
                "outcome_confidence": info.outcome_confidence,
            }
        )

    waves_data = []
    for wave_idx, wave in enumerate(waves):
        waves_data.append(
            {
                "wave": wave_idx + 1,
                "issues": [issue.issue_id for issue in wave],
            }
        )

    data = {
        "name": sprint.name,
        "description": sprint.description or None,
        "created": sprint.created,
        "issues": issues_data,
        "waves": waves_data,
        "has_cycles": has_cycles,
    }
    print_json(data)
    return 0
