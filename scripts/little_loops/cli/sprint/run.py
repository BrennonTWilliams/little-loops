"""ll-sprint run subcommand with signal handling and state management."""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from little_loops.cli.sprint._helpers import _build_issue_contents, _render_dependency_analysis
from little_loops.cli_args import parse_issue_ids, parse_issue_types
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention
from little_loops.logger import Logger, format_duration
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.sprint import SprintManager, SprintState

if TYPE_CHECKING:
    import argparse

    from little_loops.config import BRConfig

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

    # Apply type filter if provided
    type_prefixes = parse_issue_types(getattr(args, "type", None))
    if type_prefixes:
        original_count = len(issues_to_process)
        issues_to_process = [i for i in issues_to_process if i.split("-", 1)[0] in type_prefixes]
        filtered = original_count - len(issues_to_process)
        if filtered > 0:
            logger.info(f"Filtered {filtered} issue(s) by type: {', '.join(sorted(type_prefixes))}")

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
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)

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

    # Refine waves for file overlap (ENH-306)
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
                # Detect current branch for rebase/merge operations (BUG-439)
                _br = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=Path.cwd(),
                )
                _base_branch = _br.stdout.strip() if _br.returncode == 0 else "main"
                parallel_config = config.create_parallel_config(
                    max_workers=min(max_workers, len(wave)),
                    only_ids=only_ids,
                    dry_run=args.dry_run,
                    overlap_detection=True,
                    serialize_overlapping=True,
                    base_branch=_base_branch,
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
                        state.failed_issues[issue_id] = "Issue failed during wave execution"
                    # else: issue was neither completed nor failed (interrupted/stranded)
                    # — leave untracked so it can be retried on resume

                # Sequential retry for failed issues (ENH-308)
                if actually_failed:
                    logger.info(f"Retrying {len(actually_failed)} failed issue(s) sequentially...")
                    from little_loops.issue_manager import process_issue_inplace

                    retried_ok = 0
                    for issue in wave:
                        if issue.issue_id not in actually_failed:
                            continue
                        logger.info(f"  Retrying {issue.issue_id} in-place...")
                        retry_result = process_issue_inplace(
                            info=issue,
                            config=config,
                            logger=logger,
                            dry_run=args.dry_run,
                        )
                        total_duration += retry_result.duration
                        if retry_result.success:
                            retried_ok += 1
                            state.failed_issues.pop(issue.issue_id, None)
                            state.completed_issues.append(issue.issue_id)
                            state.timing[issue.issue_id] = {"total": retry_result.duration}
                            logger.success(f"  Retry succeeded: {issue.issue_id}")
                        else:
                            logger.warning(f"  Retry failed: {issue.issue_id}")
                    if retried_ok > 0:
                        logger.info(
                            f"Sequential retry recovered {retried_ok}/{len(actually_failed)} issue(s)"
                        )

                # Check whether failures remain after retry (ENH-308)
                remaining_failures = {iid for iid in actually_failed if iid in state.failed_issues}
                if result == 0 or not remaining_failures:
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
