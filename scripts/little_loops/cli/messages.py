"""ll-messages: Extract user messages from Claude Code session logs."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.logger import Logger


def main_messages() -> int:
    """Entry point for ll-messages command.

    Extract user messages from Claude Code session logs.

    Returns:
        Exit code (0 = success)
    """
    import json
    from datetime import datetime

    from little_loops.user_messages import (
        CommandRecord,
        UserMessage,
        extract_commands,
        extract_user_messages,
        get_project_folder,
    )

    parser = argparse.ArgumentParser(
        description="Extract user messages from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Last 100 messages to file
  %(prog)s -n 50                        # Last 50 messages
  %(prog)s --since 2026-01-01           # Messages since date
  %(prog)s -o output.jsonl              # Custom output path
  %(prog)s --stdout                     # Print to terminal
  %(prog)s --include-response-context   # Include response metadata
  %(prog)s --include-commands           # Include CLI commands
  %(prog)s --commands-only              # Extract only CLI commands
""",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=100,
        help="Maximum number of messages to extract (default: 100)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only include messages after this date (YYYY-MM-DD or ISO format)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: .claude/user-messages-{timestamp}.jsonl)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory to use (default: current directory)",
    )
    parser.add_argument(
        "--exclude-agents",
        action="store_true",
        help="Exclude agent session files (agent-*.jsonl)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print messages to stdout instead of writing to file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose progress information",
    )
    parser.add_argument(
        "--include-response-context",
        action="store_true",
        help="Include metadata from assistant responses (tools used, files modified)",
    )
    parser.add_argument(
        "--skip-cli",
        action="store_true",
        help="Exclude CLI commands from output (included by default)",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Extract only CLI commands, no user messages",
    )
    parser.add_argument(
        "--tools",
        type=str,
        default="Bash",
        help="Comma-separated list of tools to extract commands from (default: Bash)",
    )

    args = parser.parse_args()

    logger = Logger(verbose=args.verbose)

    # Parse since date if provided
    since = None
    if args.since:
        try:
            # Try ISO format first
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            try:
                # Try YYYY-MM-DD format
                since = datetime.strptime(args.since, "%Y-%m-%d")
            except ValueError:
                logger.error(f"Invalid date format: {args.since}")
                logger.error("Use YYYY-MM-DD or ISO format")
                return 1

    # Get project folder
    cwd = args.cwd or Path.cwd()
    project_folder = get_project_folder(cwd)

    if project_folder is None:
        logger.error(f"No Claude project folder found for: {cwd}")
        logger.error(f"Expected: ~/.claude/projects/{str(cwd).replace('/', '-')}")
        return 1

    logger.info(f"Project folder: {project_folder}")
    logger.info(f"Limit: {args.limit}")
    if since:
        logger.info(f"Since: {since}")

    # Parse tools list
    tools_list = [t.strip() for t in args.tools.split(",")]

    # Extract data based on flags
    messages: list[UserMessage] = []
    commands: list[CommandRecord] = []

    if not args.commands_only:
        messages = extract_user_messages(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            include_response_context=args.include_response_context,
        )

    if not args.skip_cli or args.commands_only:
        commands = extract_commands(
            project_folder=project_folder,
            limit=None,  # Apply limit after merging
            since=since,
            include_agent_sessions=not args.exclude_agents,
            tools=tools_list,
        )

    if not messages and not commands:
        logger.warning("No user messages or commands found")
        return 0

    # Merge and sort by timestamp
    combined: list[UserMessage | CommandRecord] = []
    combined.extend(messages)
    combined.extend(commands)
    combined.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply limit
    if args.limit is not None:
        combined = combined[: args.limit]

    msg_count = len([x for x in combined if isinstance(x, UserMessage)])
    cmd_count = len([x for x in combined if isinstance(x, CommandRecord)])
    logger.info(f"Found {msg_count} messages, {cmd_count} commands")

    # Output
    if args.stdout:
        for item in combined:
            print(json.dumps(item.to_dict()))
    else:
        output_path = _save_combined(combined, args.output)
        logger.success(f"Saved {len(combined)} records to: {output_path}")

    return 0


def _save_combined(
    items: list,
    output_path: Path | None = None,
) -> Path:
    """Save combined messages and commands to JSONL file."""
    import json
    from datetime import datetime

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.cwd() / ".claude"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"user-messages-{timestamp}.jsonl"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.to_dict()) + "\n")

    return output_path
