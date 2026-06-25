"""ll-issues sections: Print section template JSON for an issue type."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from little_loops.config import BRConfig

_VALID_TYPES = ("bug", "feat", "enh", "epic")


def cmd_sections(config: BRConfig, args: argparse.Namespace) -> int:
    """Print section template JSON (or its path) for an issue type.

    Args:
        config: Project configuration
        args: Parsed arguments with .type (str) and optional .path (bool)

    Returns:
        0 on success, 1 on invalid type or missing template
    """
    from little_loops.issue_template import resolve_templates_dir

    issue_type = args.type.lower()
    if issue_type not in _VALID_TYPES:
        print(
            f"Error: invalid type '{args.type}' — must be bug, feat, enh, or epic",
            file=sys.stderr,
        )
        return 1

    templates_dir = resolve_templates_dir(config)
    json_path = templates_dir / f"{issue_type}-sections.json"

    if not json_path.exists():
        print(f"Error: template not found: {json_path}", file=sys.stderr)
        return 1

    if getattr(args, "path", False):
        print(json_path)
        return 0

    print(json_path.read_text())
    return 0
