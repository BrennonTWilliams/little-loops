"""ll-sprint edit subcommand."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.sprint._helpers import _build_issue_contents, _render_dependency_analysis
from little_loops.cli_args import parse_issue_ids
from little_loops.logger import Logger
from little_loops.sprint import SprintManager


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
