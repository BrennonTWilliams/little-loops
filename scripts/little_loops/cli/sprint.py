"""ll-sprint: Sprint and sequence management with dependency-aware execution."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Any

from little_loops.cli_args import (
    add_config_arg,
    add_dry_run_arg,
    add_max_workers_arg,
    add_quiet_arg,
    add_resume_arg,
    add_skip_analysis_arg,
    add_skip_arg,
    add_timeout_arg,
    parse_issue_ids,
)
from little_loops.config import BRConfig
from little_loops.dependency_graph import (
    DependencyGraph,
    WaveContentionNote,
    refine_waves_for_contention,
)
from little_loops.logger import Logger, format_duration
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.sprint import SprintManager, SprintOptions, SprintState

# Module-level shutdown flag for ll-sprint signal handling (ENH-183)
_sprint_shutdown_requested: bool = False


def _sprint_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-sprint.

    First signal: Set shutdown flag for graceful exit after current wave.
    Second signal: Force immediate exit.
    """
    global _sprint_shutdown_requested
    if _sprint_shutdown_requested:
        # Second signal - force exit
        print("\nForce shutdown requested", file=sys.stderr)
        sys.exit(1)
    _sprint_shutdown_requested = True
    print("\nShutdown requested, will exit after current wave...", file=sys.stderr)


def main_sprint() -> int:
    """Entry point for ll-sprint command.

    Manage and execute sprint/sequence definitions.

    Returns:
        Exit code (0 = success)
    """
    parser = argparse.ArgumentParser(
        prog="ll-sprint",
        description="Manage and execute sprint/sequence definitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
  %(prog)s run sprint-1
  %(prog)s run sprint-1 --dry-run
  %(prog)s list
  %(prog)s show sprint-1
  %(prog)s edit sprint-1 --add BUG-045,ENH-050
  %(prog)s edit sprint-1 --remove BUG-001
  %(prog)s edit sprint-1 --prune
  %(prog)s edit sprint-1 --revalidate
  %(prog)s delete sprint-1
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create subcommand
    create_parser = subparsers.add_parser("create", help="Create a new sprint")
    create_parser.add_argument("name", help="Sprint name (used as filename)")
    create_parser.add_argument(
        "--issues",
        required=True,
        help="Comma-separated issue IDs (e.g., BUG-001,FEAT-010)",
    )
    create_parser.add_argument("--description", "-d", default="", help="Sprint description")
    add_max_workers_arg(create_parser, default=2)
    add_timeout_arg(create_parser, default=3600)
    add_skip_arg(
        create_parser,
        help_text=(
            "Comma-separated list of issue IDs to exclude from sprint (e.g., BUG-003,FEAT-004)"
        ),
    )

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Execute a sprint")
    run_parser.add_argument("sprint", help="Sprint name to execute")
    add_dry_run_arg(run_parser)
    add_max_workers_arg(run_parser)
    add_timeout_arg(run_parser)
    add_config_arg(run_parser)
    add_resume_arg(run_parser)
    add_quiet_arg(run_parser)
    add_skip_arg(
        run_parser,
        help_text=(
            "Comma-separated list of issue IDs to skip during execution (e.g., BUG-003,FEAT-004)"
        ),
    )
    add_skip_analysis_arg(run_parser)

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all sprints")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed information"
    )

    # show subcommand
    show_parser = subparsers.add_parser("show", help="Show sprint details")
    show_parser.add_argument("sprint", help="Sprint name to show")
    add_config_arg(show_parser)
    add_skip_analysis_arg(show_parser)

    # edit subcommand
    edit_parser = subparsers.add_parser("edit", help="Edit a sprint's issue list")
    edit_parser.add_argument("sprint", help="Sprint name to edit")
    edit_parser.add_argument(
        "--add",
        default=None,
        help="Comma-separated issue IDs to add (e.g., BUG-045,ENH-050)",
    )
    edit_parser.add_argument(
        "--remove",
        default=None,
        help="Comma-separated issue IDs to remove",
    )
    edit_parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove invalid (missing file) and completed issue references",
    )
    edit_parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-run dependency analysis after edits",
    )
    add_config_arg(edit_parser)

    # delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a sprint")
    delete_parser.add_argument("sprint", help="Sprint name to delete")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Commands that don't need project root
    if args.command == "list":
        return _cmd_sprint_list(args, SprintManager())
    if args.command == "delete":
        return _cmd_sprint_delete(args, SprintManager())

    # Commands that need project root
    project_root = args.config if hasattr(args, "config") and args.config else Path.cwd()
    config = BRConfig(project_root)
    manager = SprintManager(config=config)

    if args.command == "create":
        return _cmd_sprint_create(args, manager)
    if args.command == "show":
        return _cmd_sprint_show(args, manager)
    if args.command == "edit":
        return _cmd_sprint_edit(args, manager)
    if args.command == "run":
        return _cmd_sprint_run(args, manager, config)

    return 1


def _cmd_sprint_create(args: argparse.Namespace, manager: SprintManager) -> int:
    """Create a new sprint."""
    logger = Logger()
    issues = [i.strip().upper() for i in args.issues.split(",")]

    # Apply skip filter if provided
    skip_ids = parse_issue_ids(args.skip)
    if skip_ids:
        original_count = len(issues)
        issues = [i for i in issues if i not in skip_ids]
        skipped = original_count - len(issues)
        if skipped > 0:
            logger.info(
                f"Skipping {skipped} issue(s): "
                f"{', '.join(sorted(skip_ids & set(issues) | skip_ids))}"
            )

    # Validate issues exist
    valid = manager.validate_issues(issues)
    invalid = set(issues) - set(valid.keys())

    if invalid:
        logger.warning(f"Issue IDs not found: {', '.join(sorted(invalid))}")

    options = SprintOptions(
        max_workers=args.max_workers,
        timeout=args.timeout,
    )

    sprint = manager.create(
        name=args.name,
        issues=issues,
        description=args.description,
        options=options,
    )

    logger.success(f"Created sprint: {sprint.name}")
    logger.info(f"  Description: {sprint.description or '(none)'}")
    logger.info(f"  Issues: {', '.join(sprint.issues)}")
    logger.info(f"  File: .sprints/{sprint.name}.yaml")

    if invalid:
        logger.warning(f"  Invalid issues: {', '.join(sorted(invalid))}")

    return 0


def _render_execution_plan(
    waves: list[list[Any]],
    dep_graph: DependencyGraph,
    contention_notes: list[WaveContentionNote | None] | None = None,
) -> str:
    """Render execution plan with wave groupings.

    Args:
        waves: List of execution waves from get_execution_waves()
        dep_graph: DependencyGraph for looking up blockers
        contention_notes: Optional per-wave contention annotations from
            refine_waves_for_contention(). Same length as waves.

    Returns:
        Formatted string showing wave structure
    """
    if not waves:
        return ""

    total_issues = sum(len(wave) for wave in waves)
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"EXECUTION PLAN ({total_issues} issues, {len(waves)} waves)")
    lines.append("=" * 70)

    for wave_num, wave in enumerate(waves, 1):
        lines.append("")
        if wave_num == 1:
            parallel_note = "(parallel)" if len(wave) > 1 else ""
        else:
            parallel_note = f"(after Wave {wave_num - 1})"
            if len(wave) > 1:
                parallel_note += " parallel"
        lines.append(f"Wave {wave_num} {parallel_note}:".strip())

        for i, issue in enumerate(wave):
            is_last = i == len(wave) - 1
            prefix = "  \u2514\u2500\u2500 " if is_last else "  \u251c\u2500\u2500 "

            # Truncate title if too long
            title = issue.title
            if len(title) > 45:
                title = title[:42] + "..."

            lines.append(f"{prefix}{issue.issue_id}: {title} ({issue.priority})")

            # Show blockers for this issue
            blockers = dep_graph.blocked_by.get(issue.issue_id, set())
            if blockers:
                blocker_prefix = (
                    "      \u2514\u2500\u2500 " if is_last else "  \u2502   \u2514\u2500\u2500 "
                )
                blockers_str = ", ".join(sorted(blockers))
                lines.append(f"{blocker_prefix}blocked by: {blockers_str}")

        # Show file contention annotation if this wave was split
        if contention_notes and wave_num <= len(contention_notes):
            note = contention_notes[wave_num - 1]
            if note:
                lines.append(
                    f"  \u26a0  File contention \u2014 sub-wave "
                    f"{note.sub_wave_index + 1}/{note.total_sub_waves}"
                )
                paths_str = ", ".join(note.contended_paths[:3])
                if len(note.contended_paths) > 3:
                    paths_str += f" +{len(note.contended_paths) - 3} more"
                lines.append(f"     Contended: {paths_str}")

    return "\n".join(lines)


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
    # (waves > 1 can happen from file contention splitting alone)
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

    # Find root issues (no blockers in this graph)
    roots: list[str] = []
    for wave in waves[:1]:  # First wave has roots
        for issue in wave:
            roots.append(issue.issue_id)

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            if chain:
                chains.insert(0, f"  {chain}")

    # Handle any isolated issues not in chains
    all_ids = {issue.issue_id for wave in waves for issue in wave}
    for issue_id in sorted(all_ids - visited):
        chains.append(f"  {issue_id}")

    lines.extend(chains)
    lines.append("")
    lines.append("Legend: \u2500\u2500\u2192 blocks (must complete before)")

    return "\n".join(lines)


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

    # Dependency analysis (ENH-301)
    if issue_infos and not args.skip_analysis:
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents, all_known_ids=all_known_ids)
        _render_dependency_analysis(dep_report, logger)

    if sprint.options:
        print("\nOptions:")
        print(f"  Max iterations: {sprint.options.max_iterations}")
        print(f"  Timeout: {sprint.options.timeout}s")
        print(f"  Max workers: {sprint.options.max_workers}")

    if invalid:
        print(f"\nWarning: {len(invalid)} issue(s) not found")

    return 0


def _cmd_sprint_edit(args: argparse.Namespace, manager: SprintManager) -> int:
    """Edit a sprint's issue list."""
    import re

    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    if not args.add and not args.remove and not args.prune and not args.revalidate:
        logger.error("No edit flags specified. Use --add, --remove, --prune, or --revalidate.")
        return 1

    original_issues = list(sprint.issues)
    changed = False

    # --add: add new issue IDs
    if args.add:
        add_ids = parse_issue_ids(args.add)
        if add_ids:
            valid = manager.validate_issues(list(add_ids))
            invalid = add_ids - set(valid.keys())
            if invalid:
                logger.warning(f"Issue IDs not found (skipping): {', '.join(sorted(invalid))}")

            existing = set(sprint.issues)
            added = []
            for issue_id in sorted(valid.keys()):
                if issue_id not in existing:
                    sprint.issues.append(issue_id)
                    added.append(issue_id)
                else:
                    logger.info(f"Already in sprint: {issue_id}")
            if added:
                logger.success(f"Added: {', '.join(added)}")
                changed = True

    # --remove: remove issue IDs
    if args.remove:
        remove_ids = parse_issue_ids(args.remove)
        if remove_ids:
            before = len(sprint.issues)
            sprint.issues = [i for i in sprint.issues if i not in remove_ids]
            removed_count = before - len(sprint.issues)
            not_found = remove_ids - set(original_issues)
            if not_found:
                logger.warning(f"Not in sprint: {', '.join(sorted(not_found))}")
            if removed_count > 0:
                logger.success(f"Removed {removed_count} issue(s)")
                changed = True

    # --prune: remove invalid and completed references
    if args.prune:
        valid = manager.validate_issues(sprint.issues)
        invalid_ids = set(sprint.issues) - set(valid.keys())

        # Also detect completed issues
        completed_ids: set[str] = set()
        if manager.config:
            completed_dir = manager.config.get_completed_dir()
            if completed_dir.exists():
                for path in completed_dir.glob("*.md"):
                    match = re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)
                    if match:
                        completed_ids.add(f"{match.group(1)}-{match.group(2)}")

        prune_ids = invalid_ids | (completed_ids & set(sprint.issues))
        if prune_ids:
            sprint.issues = [i for i in sprint.issues if i not in prune_ids]
            pruned_invalid = invalid_ids & prune_ids
            pruned_completed = (completed_ids & set(original_issues)) - invalid_ids
            if pruned_invalid:
                logger.success(f"Pruned invalid: {', '.join(sorted(pruned_invalid))}")
            if pruned_completed:
                logger.success(f"Pruned completed: {', '.join(sorted(pruned_completed))}")
            changed = True
        else:
            logger.info("Nothing to prune — all issues are valid and active")

    # Save if changed
    if changed:
        sprint.save(manager.sprints_dir)
        logger.success(f"Saved {args.sprint} ({len(sprint.issues)} issues)")
        if original_issues != sprint.issues:
            logger.info(f"  Was: {', '.join(original_issues)}")
            logger.info(f"  Now: {', '.join(sprint.issues)}")

    # --revalidate: re-run dependency analysis
    if args.revalidate:
        valid = manager.validate_issues(sprint.issues)
        issue_infos = manager.load_issue_infos(list(valid.keys()))
        if issue_infos:
            from little_loops.dependency_mapper import (
                analyze_dependencies,
                gather_all_issue_ids,
            )

            _config = manager.config
            _issues_dir = (
                _config.project_root / _config.issues.base_dir if _config else Path(".issues")
            )
            _all_known_ids = gather_all_issue_ids(_issues_dir)
            issue_contents = _build_issue_contents(issue_infos)
            dep_report = analyze_dependencies(
                issue_infos, issue_contents, all_known_ids=_all_known_ids
            )
            _render_dependency_analysis(dep_report, logger)
        else:
            logger.info("No valid issues to analyze")

        invalid = set(sprint.issues) - set(valid.keys())
        if invalid:
            logger.warning(f"{len(invalid)} issue(s) not found: {', '.join(sorted(invalid))}")

    return 0


def _cmd_sprint_list(args: argparse.Namespace, manager: SprintManager) -> int:
    """List all sprints."""
    sprints = manager.list_all()

    if not sprints:
        print("No sprints defined")
        return 0

    print(f"Available sprints ({len(sprints)}):")

    for sprint in sprints:
        if args.verbose:
            print(f"\n{sprint.name}:")
            print(f"  Description: {sprint.description or '(none)'}")
            print(f"  Issues: {', '.join(sprint.issues)}")
            print(f"  Created: {sprint.created}")
        else:
            desc = f" - {sprint.description}" if sprint.description else ""
            print(f"  {sprint.name}{desc}")

    return 0


def _cmd_sprint_delete(args: argparse.Namespace, manager: SprintManager) -> int:
    """Delete a sprint."""
    logger = Logger()
    if not manager.delete(args.sprint):
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    logger.success(f"Deleted sprint: {args.sprint}")
    return 0


def _get_sprint_state_file() -> Path:
    """Get path to sprint state file."""
    return Path.cwd() / ".sprint-state.json"


def _load_sprint_state(logger: Logger) -> SprintState | None:
    """Load sprint state from file."""
    import json

    state_file = _get_sprint_state_file()
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        state = SprintState.from_dict(data)
        logger.info(f"State loaded from {state_file}")
        return state
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load state: {e}")
        return None


def _save_sprint_state(state: SprintState, logger: Logger) -> None:
    """Save sprint state to file."""
    import json
    from datetime import datetime

    state.last_checkpoint = datetime.now().isoformat()
    state_file = _get_sprint_state_file()
    state_file.write_text(json.dumps(state.to_dict(), indent=2))
    logger.info(f"State saved to {state_file}")


def _cleanup_sprint_state(logger: Logger) -> None:
    """Remove sprint state file."""
    state_file = _get_sprint_state_file()
    if state_file.exists():
        state_file.unlink()
        logger.info("Sprint state file cleaned up")


def _build_issue_contents(issue_infos: list) -> dict[str, str]:
    """Build issue_id -> file content mapping for dependency analysis."""
    return {info.issue_id: info.path.read_text() for info in issue_infos if info.path.exists()}


def _render_dependency_analysis(report: Any, logger: Logger) -> None:
    """Display dependency analysis results in CLI format."""
    if not report.proposals and not report.validation.has_issues:
        return

    logger.header("Dependency Analysis", char="-", width=60)

    if report.proposals:
        logger.warning(f"Found {len(report.proposals)} potential missing dependency(ies):")
        for p in report.proposals:
            if p.conflict_score >= 0.7:
                conflict = "HIGH"
            elif p.conflict_score >= 0.4:
                conflict = "MEDIUM"
            else:
                conflict = "LOW"
            logger.warning(
                f"  {p.source_id} may depend on {p.target_id} "
                f"({conflict} conflict, {p.confidence:.0%} confidence)"
            )
            if p.overlapping_files:
                files = ", ".join(p.overlapping_files[:3])
                if len(p.overlapping_files) > 3:
                    files += " and more"
                logger.info(f"    Shared files: {files}")

    if report.validation.has_issues:
        v = report.validation
        if v.broken_refs:
            for issue_id, ref_id in v.broken_refs:
                logger.warning(f"  {issue_id}: references nonexistent {ref_id}")
        if v.stale_completed_refs:
            for issue_id, ref_id in v.stale_completed_refs:
                logger.warning(f"  {issue_id}: blocked by {ref_id} (completed)")
        if v.missing_backlinks:
            for issue_id, ref_id in v.missing_backlinks:
                logger.warning(f"  {issue_id} blocked by {ref_id}, but {ref_id} missing backlink")

    logger.info("Run /ll:map-dependencies to apply discovered dependencies")
    print()  # blank line separator


def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint with dependency-aware scheduling."""
    from datetime import datetime

    logger = Logger(verbose=not args.quiet)

    # Setup signal handlers for graceful shutdown (ENH-183)
    global _sprint_shutdown_requested
    _sprint_shutdown_requested = False  # Reset in case of multiple runs
    signal.signal(signal.SIGINT, _sprint_signal_handler)
    signal.signal(signal.SIGTERM, _sprint_signal_handler)

    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Apply skip filter if provided
    issues_to_process = list(sprint.issues)
    skip_ids = parse_issue_ids(args.skip)
    if skip_ids:
        original_count = len(issues_to_process)
        issues_to_process = [i for i in issues_to_process if i not in skip_ids]
        skipped = original_count - len(issues_to_process)
        if skipped > 0:
            logger.info(f"Skipping {skipped} issue(s): {', '.join(sorted(skip_ids))}")

    # Validate issues exist
    valid = manager.validate_issues(issues_to_process)
    invalid = set(issues_to_process) - set(valid.keys())

    if invalid:
        logger.error(f"Issue IDs not found: {', '.join(sorted(invalid))}")
        logger.info("Cannot execute sprint with missing issues")
        return 1

    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(issues_to_process)
    if not issue_infos:
        logger.error("No issue files found")
        return 1

    # Gather all issue IDs on disk to avoid false "nonexistent" warnings
    from little_loops.dependency_mapper import gather_all_issue_ids

    issues_dir = config.project_root / config.issues.base_dir
    all_known_ids = gather_all_issue_ids(issues_dir)

    # Dependency analysis (ENH-301)
    if not getattr(args, "skip_analysis", False):
        from little_loops.dependency_mapper import analyze_dependencies

        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents, all_known_ids=all_known_ids)
        _render_dependency_analysis(dep_report, logger)

    # Build dependency graph
    dep_graph = DependencyGraph.from_issues(issue_infos, all_known_ids=all_known_ids)

    # Detect cycles
    if dep_graph.has_cycles():
        cycles = dep_graph.detect_cycles()
        for cycle in cycles:
            logger.error(f"Dependency cycle detected: {' -> '.join(cycle)}")
        return 1

    # Get execution waves
    try:
        waves = dep_graph.get_execution_waves()
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Refine waves for file contention (ENH-306)
    waves, contention_notes = refine_waves_for_contention(waves)

    # Display execution plan
    logger.info(f"Running sprint: {sprint.name}")
    logger.info("Dependency analysis:")
    for i, wave in enumerate(waves, 1):
        issue_ids = ", ".join(issue.issue_id for issue in wave)
        note = contention_notes[i - 1] if contention_notes else None
        if note:
            logger.info(
                f"  Wave {i}: {issue_ids}"
                f" [sub-wave {note.sub_wave_index + 1}/{note.total_sub_waves}]"
            )
        else:
            logger.info(f"  Wave {i}: {issue_ids}")

    if args.dry_run:
        logger.info("\nDry run mode - no changes will be made")
        return 0

    # Initialize or load state
    state: SprintState
    start_wave = 1

    if args.resume:
        loaded_state = _load_sprint_state(logger)
        if loaded_state and loaded_state.sprint_name == args.sprint:
            state = loaded_state
            # Find first incomplete wave by checking completed issues
            completed_set = set(state.completed_issues)
            for i, wave in enumerate(waves, 1):
                wave_issue_ids = {issue.issue_id for issue in wave}
                if not wave_issue_ids.issubset(completed_set):
                    start_wave = i
                    break
            else:
                # All waves completed
                logger.info("Sprint already completed - nothing to resume")
                _cleanup_sprint_state(logger)
                return 0
            logger.info(f"Resuming from wave {start_wave}/{len(waves)}")
            logger.info(f"  Previously completed: {len(state.completed_issues)} issues")
        else:
            if loaded_state:
                logger.warning(
                    f"State file is for sprint '{loaded_state.sprint_name}', "
                    f"not '{args.sprint}' - starting fresh"
                )
            else:
                logger.warning("No valid state found - starting fresh")
            state = SprintState(
                sprint_name=args.sprint,
                started_at=datetime.now().isoformat(),
            )
    else:
        # Fresh start - delete any old state
        _cleanup_sprint_state(logger)
        state = SprintState(
            sprint_name=args.sprint,
            started_at=datetime.now().isoformat(),
        )

    # Track exit status for error handling (ENH-185)
    exit_code = 0

    try:
        # Determine max workers
        max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 2)

        # Execute wave by wave
        completed: set[str] = set(state.completed_issues)
        failed_waves = 0
        total_duration = 0.0
        total_waves = len(waves)

        for wave_num, wave in enumerate(waves, 1):
            # Check for shutdown request (ENH-183)
            if _sprint_shutdown_requested:
                logger.warning("Shutdown requested - saving state and exiting")
                _save_sprint_state(state, logger)
                exit_code = 1
                return exit_code

            # Skip already-completed waves when resuming
            if wave_num < start_wave:
                continue

            wave_ids = [issue.issue_id for issue in wave]
            state.current_wave = wave_num
            logger.info(f"\nProcessing wave {wave_num}/{total_waves}: {', '.join(wave_ids)}")

            if len(wave) == 1:
                # Single issue — process in-place (no worktree overhead)
                from little_loops.issue_manager import process_issue_inplace

                issue_result = process_issue_inplace(
                    info=wave[0],
                    config=config,
                    logger=logger,
                    dry_run=args.dry_run,
                )
                total_duration += issue_result.duration
                if issue_result.success:
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    state.timing[wave_ids[0]] = {"total": issue_result.duration}
                    logger.success(f"Wave {wave_num}/{total_waves} completed: {wave_ids[0]}")
                else:
                    failed_waves += 1
                    completed.update(wave_ids)
                    state.completed_issues.extend(wave_ids)
                    state.failed_issues[wave_ids[0]] = "Issue processing failed"
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
                _save_sprint_state(state, logger)
                if wave_num < total_waves:
                    logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")
                    # Check for shutdown before next wave (ENH-183)
                    if _sprint_shutdown_requested:
                        logger.warning("Shutdown requested - exiting after wave completion")
                        exit_code = 1
                        return exit_code
            else:
                # Multi-issue — use ParallelOrchestrator with worktrees
                only_ids = set(wave_ids)
                parallel_config = config.create_parallel_config(
                    max_workers=min(max_workers, len(wave)),
                    only_ids=only_ids,
                    dry_run=args.dry_run,
                    overlap_detection=True,
                    serialize_overlapping=True,
                )

                orchestrator = ParallelOrchestrator(
                    parallel_config, config, Path.cwd(), wave_label=f"Wave {wave_num}/{total_waves}"
                )
                result = orchestrator.run()
                total_duration += orchestrator.execution_duration

                # Track completed/failed from this wave using per-issue results
                actually_completed = set(orchestrator.queue.completed_ids)
                actually_failed = set(orchestrator.queue.failed_ids)

                for issue_id in wave_ids:
                    if issue_id in actually_completed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.timing[issue_id] = {
                            "total": orchestrator.execution_duration / len(wave)
                        }
                    elif issue_id in actually_failed:
                        completed.add(issue_id)
                        state.completed_issues.append(issue_id)
                        state.failed_issues[issue_id] = "Issue failed during wave execution"
                    # else: issue was neither completed nor failed (interrupted/stranded)
                    # — leave untracked so it can be retried on resume

                if result == 0:
                    logger.success(
                        f"Wave {wave_num}/{total_waves} completed: {', '.join(wave_ids)}"
                    )
                else:
                    failed_waves += 1
                    logger.warning(f"Wave {wave_num}/{total_waves} had failures")
                _save_sprint_state(state, logger)
                if wave_num < total_waves:
                    logger.info(f"Continuing to wave {wave_num + 1}/{total_waves}...")
                    # Check for shutdown before next wave (ENH-183)
                    if _sprint_shutdown_requested:
                        logger.warning("Shutdown requested - exiting after wave completion")
                        exit_code = 1
                        return exit_code

        wave_word = "wave" if len(waves) == 1 else "waves"
        logger.info(
            f"\nSprint completed: {len(completed)} issues processed ({len(waves)} {wave_word})"
        )
        logger.timing(f"Total execution time: {format_duration(total_duration)}")
        if failed_waves > 0:
            logger.warning(f"{failed_waves} wave(s) had failures")
            exit_code = 1
        else:
            # Clean up state on successful completion
            _cleanup_sprint_state(logger)

    except KeyboardInterrupt:
        # Belt-and-suspenders with signal handler (ENH-185)
        logger.warning("Sprint interrupted by user (KeyboardInterrupt)")
        exit_code = 130

    except Exception as e:
        # Catch unexpected exceptions (ENH-185)
        logger.error(f"Sprint failed unexpectedly: {e}")
        exit_code = 1

    finally:
        # Guaranteed state save on any non-success exit (ENH-185)
        if exit_code != 0:
            _save_sprint_state(state, logger)
            logger.info("State saved before exit")

    return exit_code
