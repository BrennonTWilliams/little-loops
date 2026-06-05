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
from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context
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


def _extract_cwd_from_project(project_dir: Path) -> Path | None:
    """Extract the project working directory from cwd fields in JSONL records.

    Claude Code encodes project paths by replacing '/' with '-', which is
    lossy for paths containing hyphens. Reading the cwd field from JSONL
    records gives the canonical path without ambiguity.
    """
    jsonl_files = [f for f in project_dir.glob("*.jsonl") if not f.name.startswith("agent-")]
    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        cwd = record.get("cwd")
                        if isinstance(cwd, str) and cwd:
                            return Path(cwd)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return None


def discover_all_projects(logger: Logger, *, host: str | None = None) -> list[Path]:
    """Discover all projects with ll activity for the given host.

    Iterates the host's session directory (e.g. ``~/.claude/projects/`` for
    Claude Code, ``~/.codex/projects/`` for Codex), resolves each directory
    name back to an absolute path, checks for ll-relevant JSONL records, and
    returns a sorted list of paths that exist on disk.

    Args:
        logger: Logger instance for warnings.
        host: Host identifier. If None, auto-detects from ``LL_HOOK_HOST``
            env var (default ``"claude-code"``).

    Returns:
        Sorted list of decoded absolute paths for projects with ll activity.
    """
    import os as _os

    if host is None:
        host = _os.environ.get("LL_HOOK_HOST", "claude-code")

    if host == "claude-code":
        projects_root = Path.home() / ".claude" / "projects"
    elif host == "codex":
        projects_root = Path.home() / ".codex" / "projects"
    elif host == "opencode":
        projects_root = Path.home() / ".opencode" / "projects"
    elif host == "pi":
        projects_root = Path.home() / ".pi" / "projects"
    else:
        return []

    if not projects_root.exists():
        return []

    results: list[Path] = []

    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue

        # Prefer cwd field from JSONL records; fall back to lossy decode.
        # The lossy decode ("-Users-foo-bar" -> "/Users/foo/bar") breaks for
        # paths that contain hyphens (e.g. "little-loops", macOS per-user
        # temp dirs like /tmp/claude-501/).
        decoded_path = _extract_cwd_from_project(project_dir) or Path(
            project_dir.name.replace("-", "/")
        )

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


def generate_index(logs_dir: Path) -> None:
    """Generate logs/index.md summarising extracted projects."""
    rows = []

    if logs_dir.exists():
        for subdir in sorted(logs_dir.iterdir()):
            if not subdir.is_dir():
                continue

            jsonl_files = [f for f in subdir.glob("*.jsonl") if not f.name.startswith("agent-")]
            if not jsonl_files:
                continue

            timestamps: list[str] = []
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
                            ts = record.get("timestamp")
                            if ts:
                                timestamps.append(ts)
                except OSError:
                    continue

            if timestamps:
                earliest = min(timestamps)[:10]
                latest = max(timestamps)[:10]
                date_range = f"{earliest} – {latest}" if earliest != latest else earliest
            else:
                date_range = ""

            rows.append((subdir.name, len(jsonl_files), date_range))

    lines = ["# Logs Index", ""]
    if rows:
        lines.append("| Project | Sessions | Date Range |")
        lines.append("|---------|----------|------------|")
        for name, count, date_range in rows:
            lines.append(f"| {name} | {count} | {date_range} |")
    else:
        lines.append("*No projects extracted yet.*")
    lines.append("")

    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _cmd_extract(args: argparse.Namespace, logger: Logger) -> int:
    """Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl."""
    if args.project:
        cwd_path: Path = args.project
        project_folder = get_project_folder(cwd_path)
        if project_folder is None:
            logger.error(f"No session project folder found for: {cwd_path}")
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

    generate_index(Path.cwd() / "logs")
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
    discover_parser = subparsers.add_parser(
        "discover",
        help="List all Claude projects with ll activity (one path per line, sorted)",
    )
    add_json_arg(discover_parser)

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
    with cli_event_context(DEFAULT_DB_PATH, "ll-logs", sys.argv[1:]):
        configure_output()
        logger = Logger(use_color=use_color_enabled())

        parser = _build_parser()
        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return 1

        if args.command == "discover":
            projects = discover_all_projects(logger)
            if args.json:
                print_json({"paths": [str(p) for p in projects]})
            else:
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
