"""ll-issues set-scores: Write confidence and dimension scores to issue frontmatter."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

SCORE_KEYS = (
    "confidence_score",
    "outcome_confidence",
    "score_complexity",
    "score_test_coverage",
    "score_ambiguity",
    "score_change_surface",
)
_SCORE_ARG_DESTS = (
    "confidence",
    "outcome",
    "score_complexity",
    "score_test_coverage",
    "score_ambiguity",
    "score_change_surface",
)


def cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int:
    """Write confidence and outcome scores into an issue's YAML frontmatter.

    Idempotent: calling with the same values has no net effect. Only the
    flags that are explicitly provided are written; omitted flags leave the
    corresponding frontmatter field unchanged. ``--clear`` instead removes all
    six score keys (absent keys are a no-op) and is exclusive with score flags.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id and optional score flags

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import remove_frontmatter_keys, update_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    if getattr(args, "clear", False):
        if any(getattr(args, dest, None) is not None for dest in _SCORE_ARG_DESTS):
            print("Error: --clear cannot be combined with score arguments.", file=sys.stderr)
            return 1
        content = path.read_text()
        new_content = remove_frontmatter_keys(content, SCORE_KEYS)
        if new_content != content:
            path.write_text(new_content)
        return 0

    updates: dict[str, str | int] = {}
    if args.confidence is not None:
        updates["confidence_score"] = args.confidence
    if args.outcome is not None:
        updates["outcome_confidence"] = args.outcome
    if args.score_complexity is not None:
        updates["score_complexity"] = args.score_complexity
    if args.score_test_coverage is not None:
        updates["score_test_coverage"] = args.score_test_coverage
    if args.score_ambiguity is not None:
        updates["score_ambiguity"] = args.score_ambiguity
    if args.score_change_surface is not None:
        updates["score_change_surface"] = args.score_change_surface

    if not updates:
        print("Warning: no score flags provided; nothing to write.", file=sys.stderr)
        return 0

    content = path.read_text()
    new_content = update_frontmatter(content, updates)
    path.write_text(new_content)
    return 0
