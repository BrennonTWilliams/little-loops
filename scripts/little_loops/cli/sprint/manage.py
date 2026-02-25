"""ll-sprint list, delete, and analyze subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from little_loops.cli.sprint._helpers import _render_execution_plan
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention
from little_loops.logger import Logger
from little_loops.sprint import SprintManager


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


def _cmd_sprint_analyze(args: argparse.Namespace, manager: SprintManager) -> int:
    """Analyze sprint for file conflicts between issues."""
    import json as _json

    from little_loops.parallel.file_hints import FileHints, extract_file_hints

    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    if invalid:
        logger.warning(f"Issue IDs not found: {', '.join(sorted(invalid))}")

    # Load full IssueInfo objects
    issue_infos = manager.load_issue_infos(list(valid.keys()))
    if not issue_infos:
        logger.error("No valid issue files found")
        return 1

    # Gather all known IDs
    from little_loops.dependency_mapper import gather_all_issue_ids

    config = manager.config
    issues_dir = config.project_root / config.issues.base_dir if config else Path(".issues")
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)

    # Build dependency graph
    dep_graph = DependencyGraph.from_issues(issue_infos, all_known_ids=all_known_ids)
    has_cycles = dep_graph.has_cycles()

    if has_cycles:
        cycles = dep_graph.detect_cycles()
        for cycle in cycles:
            logger.error(f"Dependency cycle detected: {' -> '.join(cycle)}")
        return 1

    # Generate waves and refine for contention
    waves = dep_graph.get_execution_waves()
    waves, contention_notes = refine_waves_for_contention(waves)

    # Extract file hints and detect pairwise conflicts
    hints: dict[str, FileHints] = {}
    for info in issue_infos:
        content = info.path.read_text() if info.path.exists() else ""
        hints[info.issue_id] = extract_file_hints(content, info.issue_id)

    conflict_pairs: list[dict[str, Any]] = []
    for i, a in enumerate(issue_infos):
        for b in issue_infos[i + 1 :]:
            if hints[a.issue_id].overlaps_with(hints[b.issue_id]):
                overlapping = sorted(hints[a.issue_id].get_overlapping_paths(hints[b.issue_id]))
                conflict_pairs.append(
                    {
                        "issue_a": a.issue_id,
                        "issue_b": b.issue_id,
                        "overlapping_files": overlapping,
                    }
                )

    # Build parallel-safe groups from waves (issues in same wave with no conflicts)
    conflicting_ids = set()
    for pair in conflict_pairs:
        conflicting_ids.add(pair["issue_a"])
        conflicting_ids.add(pair["issue_b"])

    parallel_safe: list[list[str]] = []
    notes_list = contention_notes or [None] * len(waves)
    for idx, wave in enumerate(waves):
        note = notes_list[idx] if idx < len(notes_list) else None
        if note is None and len(wave) > 1:
            # Non-contention wave with multiple issues = parallel-safe group
            group = [issue.issue_id for issue in wave]
            parallel_safe.append(group)

    has_conflicts = len(conflict_pairs) > 0

    # Build wave plan for report
    wave_plan: list[dict[str, Any]] = []
    for idx, wave in enumerate(waves):
        note = notes_list[idx] if idx < len(notes_list) else None
        wave_info: dict[str, Any] = {
            "wave": idx + 1,
            "issues": [issue.issue_id for issue in wave],
        }
        if note is not None:
            wave_info["serialized"] = True
            wave_info["sub_wave"] = note.sub_wave_index + 1
            wave_info["total_sub_waves"] = note.total_sub_waves
            wave_info["contended_paths"] = note.contended_paths
        else:
            wave_info["serialized"] = False
        wave_plan.append(wave_info)

    if args.format == "json":
        data = {
            "sprint": sprint.name,
            "issue_count": len(issue_infos),
            "has_conflicts": has_conflicts,
            "conflicts": conflict_pairs,
            "waves": wave_plan,
            "parallel_safe_groups": parallel_safe,
        }
        print(_json.dumps(data, indent=2))
    else:
        # Text report
        total_issues = len(issue_infos)
        print(f"Sprint: {sprint.name}")
        print(f"Issues: {total_issues}")
        print()
        print("=" * 70)
        print("CONFLICT ANALYSIS")
        print("=" * 70)

        if not has_conflicts:
            print()
            print("No file conflicts detected. All issues can run in parallel.")
        else:
            print()
            print(f"Conflicts found: {len(conflict_pairs)} pair(s)")

            for i, pair in enumerate(conflict_pairs, 1):
                print()
                print(f"  {i}. {pair['issue_a']} <-> {pair['issue_b']}")
                files_str = ", ".join(pair["overlapping_files"][:3])
                if len(pair["overlapping_files"]) > 3:
                    files_str += f" +{len(pair['overlapping_files']) - 3} more"
                print(f"     Overlapping files: {files_str}")
                print("     Recommendation: Serialize execution")

        # Execution plan
        print()
        print(_render_execution_plan(waves, dep_graph, contention_notes))

        # Parallel-safe groups
        if parallel_safe:
            print()
            print("Parallel-safe groups:")
            for group in parallel_safe:
                print(f"  - {', '.join(group)} (no shared files)")

    return 1 if has_conflicts else 0
