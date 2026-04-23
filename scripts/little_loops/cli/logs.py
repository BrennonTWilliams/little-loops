"""ll-logs: Discover and extract ll-relevant JSONL entries from ~/.claude/projects/."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger

_COMMAND_NAME_RE = re.compile(r"<command-name>/ll:")


def _is_ll_relevant(record: dict) -> bool:
    """Return True if a JSONL record indicates ll activity.

    Detects three signal types:
    (a) queue-operation enqueue with /ll: content
    (b) user records with <command-name>/ll: pattern in message content
    """
    record_type = record.get("type")

    # (a) queue-operation: only enqueue records with /ll: content signal ll activity
    if record_type == "queue-operation":
        return (
            record.get("operation") == "enqueue"
            and isinstance(record.get("content"), str)
            and record["content"].startswith("/ll:")
        )

    # (b) user records: check message content for <command-name>/ll: pattern
    if record_type == "user":
        message = record.get("message", {})
        if not isinstance(message, dict):
            return False
        content = message.get("content")
        if isinstance(content, str):
            return bool(_COMMAND_NAME_RE.search(content))
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str) and _COMMAND_NAME_RE.search(text):
                        return True

    return False


def _has_ll_activity(project_folder: Path) -> bool:
    """Return True if any non-agent JSONL file in project_folder has ll activity."""
    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if _is_ll_relevant(record):
                        return True
        except OSError:
            continue

    return False


def discover_all_projects(logger: Logger) -> list[Path]:
    """Discover all Claude projects with ll activity.

    Iterates ~/.claude/projects/, decodes each directory name back to an
    absolute path, checks for ll-relevant JSONL records, and returns a
    sorted list of paths that exist on disk.

    Args:
        logger: Logger instance for warnings.

    Returns:
        Sorted list of decoded absolute paths for projects with ll activity.
    """
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        return []

    results: list[Path] = []

    for project_dir in claude_projects.iterdir():
        if not project_dir.is_dir():
            continue

        # Decode directory name to path: "-Users-foo-bar" -> "/Users/foo/bar"
        decoded_path = Path(project_dir.name.replace("-", "/"))

        if not decoded_path.exists():
            logger.warning(f"Decoded path does not exist: {decoded_path}")
            continue

        if _has_ll_activity(project_dir):
            results.append(decoded_path)

    return sorted(results)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-logs."""
    parser = argparse.ArgumentParser(
        prog="ll-logs",
        description="Discover and extract ll-relevant JSONL entries from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s discover    # List all projects with ll activity
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser(
        "discover",
        help="List all Claude projects with ll activity (one path per line, sorted)",
    )

    return parser


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments. Exposed for testing."""
    return _build_parser().parse_args()


def main_logs() -> int:
    """Entry point for ll-logs command.

    Returns:
        0 on success, 1 when no subcommand given or on error.
    """
    configure_output()
    logger = Logger(use_color=use_color_enabled())

    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "discover":
        projects = discover_all_projects(logger)
        for path in projects:
            print(path)
        return 0

    return 1
