"""ll-sprint create subcommand."""

from __future__ import annotations

import argparse

from little_loops.cli_args import parse_issue_ids, parse_issue_types
from little_loops.logger import Logger
from little_loops.sprint import SprintManager, SprintOptions


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

    # Apply type filter if provided
    type_prefixes = parse_issue_types(getattr(args, "type", None))
    if type_prefixes:
        original_count = len(issues)
        issues = [i for i in issues if i.split("-", 1)[0] in type_prefixes]
        filtered = original_count - len(issues)
        if filtered > 0:
            logger.info(f"Filtered {filtered} issue(s) by type: {', '.join(sorted(type_prefixes))}")

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
