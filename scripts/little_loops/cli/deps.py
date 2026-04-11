"""ll-deps: Cross-issue dependency discovery and validation."""

from __future__ import annotations

import argparse
from pathlib import Path


def _load_issues(
    issues_dir: Path,
    only_ids: set[str] | None = None,
) -> tuple[list, dict[str, str], set[str]]:
    """Load issues from directory for CLI use.

    Args:
        issues_dir: Path to the issues base directory (e.g., .issues)
        only_ids: If provided, only include issues with these IDs

    Returns:
        Tuple of (active issues, issue contents map, completed issue IDs)
    """
    from little_loops.config import BRConfig
    from little_loops.issue_parser import find_issues

    # Find project root by walking up from issues_dir
    project_root = issues_dir.resolve().parent
    if issues_dir.name != ".issues":
        # If issues_dir is already absolute, try to find config relative to it
        project_root = issues_dir.parent

    config = BRConfig(project_root)
    issues = find_issues(config, only_ids=only_ids)

    # Build contents map
    issue_contents: dict[str, str] = {}
    for info in issues:
        if info.path.exists():
            issue_contents[info.issue_id] = info.path.read_text(encoding="utf-8")

    # Gather completed and deferred issue IDs
    import re as _re

    completed_ids: set[str] = set()
    for non_active_dir in [config.get_completed_dir(), config.get_deferred_dir()]:
        if non_active_dir.exists():
            for f in non_active_dir.glob("*.md"):
                match = _re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)
                if match:
                    completed_ids.add(f"{match.group(1)}-{match.group(2)}")

    return issues, issue_contents, completed_ids


def main_deps() -> int:
    """Entry point for ll-deps command.

    Analyze cross-issue dependencies and validate existing references.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    import json as _json
    import sys

    from little_loops.dependency_mapper import (
        analyze_dependencies,
        fix_dependencies,
        format_report,
        format_text_graph,
        gather_all_issue_ids,
        validate_dependencies,
    )

    parser = argparse.ArgumentParser(
        prog="ll-deps",
        description="Cross-issue dependency discovery and validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s analyze                    # Full analysis with markdown output
  %(prog)s analyze --format json      # JSON output for programmatic use
  %(prog)s analyze --graph            # Include ASCII dependency graph
  %(prog)s analyze --sprint my-sprint # Analyze only issues in a sprint
  %(prog)s validate                   # Validation only (broken refs, cycles)
  %(prog)s validate --sprint my-sprint # Validate only sprint issue deps
  %(prog)s fix                        # Auto-fix broken refs, stale refs, backlinks
  %(prog)s fix --dry-run              # Preview fixes without modifying files
  %(prog)s apply                      # Apply proposals >= 0.7 confidence
  %(prog)s apply --min-confidence 0.5 # Lower threshold
  %(prog)s apply --dry-run            # Preview only (no writes)
  %(prog)s apply --sprint my-sprint   # Sprint-scoped apply
  %(prog)s apply FEAT-001 blocks FEAT-002     # Manual explicit pair
  %(prog)s apply FEAT-001 blocked-by FEAT-002 # Manual explicit pair (inverse)
""",
    )

    parser.add_argument(
        "-d",
        "--issues-dir",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Full dependency analysis (file overlaps + validation)",
    )
    analyze_parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text/markdown)",
    )
    analyze_parser.add_argument(
        "--graph",
        action="store_true",
        help="Include ASCII dependency graph in output",
    )
    analyze_parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Restrict analysis to issues in the named sprint",
    )

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate existing dependency references only",
    )
    validate_parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Restrict validation to issues in the named sprint",
    )

    # fix subcommand
    fix_parser = subparsers.add_parser(
        "fix",
        help="Auto-fix broken refs, stale refs, and missing backlinks",
    )
    fix_parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    fix_parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Restrict fixes to issues in the named sprint",
    )

    # apply subcommand
    apply_parser = subparsers.add_parser(
        "apply",
        help="Write dependency relationships to issue files",
    )
    apply_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Source issue ID for explicit pair (e.g. FEAT-001)",
    )
    apply_parser.add_argument(
        "relation",
        nargs="?",
        default=None,
        choices=["blocks", "blocked-by"],
        help="Relationship direction: 'blocks' or 'blocked-by'",
    )
    apply_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target issue ID for explicit pair (e.g. FEAT-002)",
    )
    apply_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        help="Minimum confidence threshold for implicit apply (default: 0.7)",
    )
    apply_parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview without writing",
    )
    apply_parser.add_argument(
        "--sprint",
        type=str,
        default=None,
        help="Restrict to issues in named sprint",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    issues_dir = args.issues_dir or Path.cwd() / ".issues"
    if not issues_dir.exists():
        print(f"Error: Issues directory not found: {issues_dir}", file=sys.stderr)
        return 1

    # Sprint-scoped filtering
    only_ids: set[str] | None = None
    if getattr(args, "sprint", None):
        from little_loops.config import BRConfig as _BRConfig
        from little_loops.sprint import Sprint

        project_root = issues_dir.resolve().parent
        if issues_dir.name != ".issues":
            project_root = issues_dir.parent
        _config = _BRConfig(project_root)
        sprints_dir = Path(_config.sprints.sprints_dir)
        if not sprints_dir.is_absolute():
            sprints_dir = project_root / sprints_dir

        sprint = Sprint.load(sprints_dir, args.sprint)
        if sprint is None:
            print(f"Error: Sprint not found: {args.sprint}", file=sys.stderr)
            return 1
        only_ids = set(sprint.issues)
        if not only_ids:
            print(f"Sprint '{args.sprint}' has no issues.")
            return 0

    try:
        issues, issue_contents, completed_ids = _load_issues(issues_dir, only_ids=only_ids)
    except Exception as e:
        print(f"Error loading issues: {e}", file=sys.stderr)
        return 1

    if not issues:
        print("No active issues found.")
        return 0

    # Gather all issue IDs on disk to avoid false "nonexistent" warnings
    # when sprint-scoped analysis references issues outside the sprint
    try:
        from little_loops.config import BRConfig as _BRConfig

        _dm_config = _BRConfig(issues_dir.resolve().parent)
    except Exception:
        _dm_config = None
    all_known_ids = gather_all_issue_ids(issues_dir, config=_dm_config)

    # Load dependency mapping config
    dep_config = _dm_config.dependency_mapping if _dm_config else None

    if args.command == "analyze":
        report = analyze_dependencies(
            issues, issue_contents, completed_ids, all_known_ids, config=dep_config
        )

        if args.format == "json":
            data = {
                "issue_count": report.issue_count,
                "existing_dep_count": report.existing_dep_count,
                "proposals": [
                    {
                        "source_id": p.source_id,
                        "target_id": p.target_id,
                        "reason": p.reason,
                        "confidence": p.confidence,
                        "rationale": p.rationale,
                        "overlapping_files": p.overlapping_files,
                        "conflict_score": p.conflict_score,
                    }
                    for p in report.proposals
                ],
                "parallel_safe": [
                    {
                        "issue_a": ps.issue_a,
                        "issue_b": ps.issue_b,
                        "shared_files": ps.shared_files,
                        "conflict_score": ps.conflict_score,
                        "reason": ps.reason,
                    }
                    for ps in report.parallel_safe
                ],
                "validation": {
                    "broken_refs": report.validation.broken_refs,
                    "missing_backlinks": report.validation.missing_backlinks,
                    "cycles": report.validation.cycles,
                    "stale_completed_refs": report.validation.stale_completed_refs,
                    "has_issues": report.validation.has_issues,
                },
            }
            print(_json.dumps(data, indent=2))
        else:
            print(format_report(report, config=dep_config))
            if args.graph:
                print()
                print("## Dependency Graph")
                print()
                print(format_text_graph(issues, report.proposals))

        return 0

    if args.command == "validate":
        result = validate_dependencies(issues, completed_ids, all_known_ids)

        if not result.has_issues:
            print("No validation issues found.")
            return 0

        lines: list[str] = []
        lines.append("# Dependency Validation Report")
        lines.append("")

        if result.broken_refs:
            lines.append("## Broken References")
            lines.append("")
            for issue_id, ref_id in result.broken_refs:
                lines.append(f"- {issue_id}: references nonexistent {ref_id}")
            lines.append("")

        if result.missing_backlinks:
            lines.append("## Missing Backlinks")
            lines.append("")
            for issue_id, ref_id in result.missing_backlinks:
                lines.append(
                    f"- {issue_id} is blocked by {ref_id}, "
                    f"but {ref_id} does not list {issue_id} in Blocks"
                )
            lines.append("")

        if result.cycles:
            lines.append("## Dependency Cycles")
            lines.append("")
            for cycle in result.cycles:
                lines.append(f"- {' -> '.join(cycle)}")
            lines.append("")

        if result.stale_completed_refs:
            lines.append("## Stale References (to completed issues)")
            lines.append("")
            for issue_id, ref_id in result.stale_completed_refs:
                lines.append(f"- {issue_id}: blocked by {ref_id} (completed)")
            lines.append("")

        print("\n".join(lines))
        return 0

    if args.command == "fix":
        fix_result = fix_dependencies(issues, completed_ids, all_known_ids, dry_run=args.dry_run)

        if not fix_result.changes:
            print("No fixable issues found.")
            if fix_result.skipped_cycles:
                print(f"({fix_result.skipped_cycles} cycle(s) detected — resolve manually)")
            return 0

        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"# {prefix}Dependency Fix Report")
        print()
        for change in fix_result.changes:
            print(f"  {prefix}{change}")
        print()
        print(f"{prefix}{len(fix_result.changes)} fix(es) applied.")

        if fix_result.modified_files:
            print()
            print("Modified files:")
            for fpath in sorted(fix_result.modified_files):
                print(f"  {fpath}")

        if fix_result.skipped_cycles:
            print()
            print(f"({fix_result.skipped_cycles} cycle(s) detected — resolve manually)")

        return 0

    if args.command == "apply":
        from little_loops.dependency_mapper.operations import _add_to_section

        prefix = "[DRY RUN] " if args.dry_run else ""
        issue_files = {i.issue_id: i.path for i in issues}

        # Explicit-pair mode: all three positional args must be provided together
        if args.source or args.relation or args.target:
            if not (args.source and args.relation and args.target):
                print(
                    "Error: explicit pair requires all three arguments: "
                    "<source> <relation> <target>",
                    file=sys.stderr,
                )
                return 1

            all_ids = {i.issue_id for i in issues} | all_known_ids
            for id_to_check, label in [(args.source, "source"), (args.target, "target")]:
                if id_to_check not in all_ids:
                    print(
                        f"Error: {label} issue {id_to_check!r} not found",
                        file=sys.stderr,
                    )
                    return 1

            # Determine which issue receives the "Blocked By" entry
            if args.relation == "blocks":
                # source blocks target → target is blocked by source
                blocked_id, blocker_id = args.target, args.source
            else:  # blocked-by
                # source blocked-by target → source is blocked by target
                blocked_id, blocker_id = args.source, args.target

            blocked_path = issue_files.get(blocked_id)
            if blocked_path is None:
                print(
                    f"Error: issue {blocked_id!r} is not in active issues (cannot write to it)",
                    file=sys.stderr,
                )
                return 1

            print(f"# {prefix}Dependency Apply Report")
            print()
            print(f"  {prefix}{blocked_id} blocked by {blocker_id}")
            print()

            if not args.dry_run:
                _add_to_section(blocked_path, "Blocked By", blocker_id)
                print("1 relationship(s) applied.")
                print()
                print("Modified files:")
                print(f"  {blocked_path}")
            else:
                print("[DRY RUN] 1 relationship(s) would be applied.")

            return 0

        # Implicit mode: run analysis and apply proposals above confidence threshold
        report = analyze_dependencies(
            issues, issue_contents, completed_ids, all_known_ids, config=dep_config
        )
        filtered = [p for p in report.proposals if p.confidence >= args.min_confidence]

        if not filtered:
            print(f"No proposals at or above confidence threshold ({args.min_confidence}).")
            return 0

        print(f"# {prefix}Dependency Apply Report")
        print()

        modified: set[str] = set()
        applied = 0

        for proposal in filtered:
            source_path = issue_files.get(proposal.source_id)
            if source_path is None or not source_path.exists():
                continue
            desc = (
                f"{proposal.source_id} blocked by {proposal.target_id}"
                f" (confidence: {proposal.confidence:.2f})"
            )
            print(f"  {prefix}{desc}")
            applied += 1

            if not args.dry_run:
                _add_to_section(source_path, "Blocked By", proposal.target_id)
                modified.add(str(source_path))

        print()
        if args.dry_run:
            print(f"[DRY RUN] {applied} relationship(s) would be applied.")
        else:
            print(f"{applied} relationship(s) applied.")
            if modified:
                print()
                print("Modified files:")
                for fpath in sorted(modified):
                    print(f"  {fpath}")

        return 0

    return 1
