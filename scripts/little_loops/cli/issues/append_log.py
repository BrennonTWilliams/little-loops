"""ll-issues append-log: Append a session log entry to an issue file."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_append_log(config: BRConfig, args: object) -> int:
    """Append a correctly-formatted session log entry to an issue file.

    Args:
        config: Project configuration
        args: Parsed arguments with issue_path and command attributes

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.session_log import append_session_log_entry

    issue_path = Path(args.issue_path)  # type: ignore[attr-defined]
    success = append_session_log_entry(issue_path, args.log_command)  # type: ignore[attr-defined]
    if not success:
        print(
            "Warning: could not resolve session JSONL; entry not written.",
            file=sys.stderr,
        )
        return 1
    return 0
