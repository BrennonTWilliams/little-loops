"""ll-issues check-flag: Exit 0 if a boolean frontmatter field equals 'true'."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int:
    """Exit 0 if the named frontmatter field on the issue equals 'true'.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id and .field

    Returns:
        0 if the field is 'true', 1 otherwise
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    fm = parse_frontmatter(path.read_text(), coerce_types=True)
    value = fm.get(args.field)
    return 0 if str(value).lower() == "true" else 1
