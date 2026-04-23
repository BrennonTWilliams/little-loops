"""ll-logs: Discover and extract ll-relevant JSONL entries from ~/.claude/projects/."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from little_loops.cli.loop.info import (  # private symbol: cross-module coupling; verify signature on upgrade
    _format_history_event,
)
from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.user_messages import get_project_folder

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

    # (c) assistant records: check for Bash tool-use invoking an ll- command
    if record_type == "assistant":
        message = record.get("message", {})
        content = message.get("content", [])
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                ):
                    cmd = block.get("input", {}).get("command", "")
                    if re.search(r"\bll-\w+", cmd):
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


def _cmd_matches(record: dict, cmd: str) -> bool:
    """Return True if record contains a Bash tool-use whose command includes cmd."""
    message = record.get("message", {})
    content = message.get("content", [])
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Bash"
            ):
                command = block.get("input", {}).get("command", "")
                if cmd in command:
                    return True
    return False


def _cmd_extract(args: argparse.Namespace, logger: Logger) -> int:
    """Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl."""
    if args.project:
        cwd_path: Path = args.project
        project_folder = get_project_folder(cwd_path)
        if project_folder is None:
            logger.error(f"No Claude project folder found for: {cwd_path}")
            logger.error(f"Expected: ~/.claude/projects/{str(cwd_path).replace('/', '-')}")
            return 1
        project_items = [(cwd_path, project_folder)]
    else:
        decoded_paths = discover_all_projects(logger)
        project_items = []
        for decoded_path in decoded_paths:
            folder = get_project_folder(decoded_path)
            if folder is not None:
                project_items.append((decoded_path, folder))

    for cwd_path, project_folder in project_items:
        slug = cwd_path.resolve().name
        buckets: dict[str, list[dict]] = {}

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
                            session_id = record.get("sessionId", "")
                            buckets.setdefault(session_id, []).append(record)
            except OSError:
                continue

        if args.cmd:
            filtered: dict[str, list[dict]] = {}
            for session_id, records in buckets.items():
                matching = [r for r in records if _cmd_matches(r, args.cmd)]
                if matching:
                    filtered[session_id] = matching
            buckets = filtered

        out_base = Path.cwd() / "logs" / slug
        for session_id, records in buckets.items():
            out_file = out_base / f"{session_id}.jsonl"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

    return 0


def _cmd_tail(args: argparse.Namespace, loops_dir: Path) -> int:
    """Stream live events from an active loop session."""
    events_file = loops_dir / ".running" / f"{args.loop}.events.jsonl"

    if not events_file.exists():
        print(f"No active session for loop '{args.loop}'", file=sys.stderr)
        return 1

    width = shutil.get_terminal_size().columns
    try:
        with open(events_file, encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        formatted = _format_history_event(event, verbose=False, width=width)
                        if formatted is not None:
                            print(formatted)
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        return 0

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-logs."""
    parser = argparse.ArgumentParser(
        prog="ll-logs",
        description="Discover and extract ll-relevant JSONL entries from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s discover              # List all projects with ll activity
  %(prog)s tail --loop <name>   # Stream live events from an active loop session
  %(prog)s extract --all             # Extract all projects to logs/
  %(prog)s extract --project /path  # Extract one project to logs/<slug>/
  %(prog)s extract --all --cmd ll-history  # Filter to ll-history invocations
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser(
        "discover",
        help="List all Claude projects with ll activity (one path per line, sorted)",
    )

    tail_parser = subparsers.add_parser(
        "tail",
        help="Stream live events from an active loop session",
    )
    tail_parser.add_argument("--loop", required=True, metavar="NAME", help="Loop name to tail")

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl",
    )
    target_group = extract_parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project",
    )
    target_group.add_argument(
        "--all",
        action="store_true",
        help="Extract all projects with ll activity",
    )
    extract_parser.add_argument(
        "--cmd",
        metavar="TOOL",
        help="Filter to records containing this ll- tool name (e.g. ll-history)",
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

    if args.command == "tail":
        config = BRConfig(Path.cwd())
        loops_dir = Path(config.loops.loops_dir)
        return _cmd_tail(args, loops_dir)

    if args.command == "extract":
        return _cmd_extract(args, logger)

    return 1
