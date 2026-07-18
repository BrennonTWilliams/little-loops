"""ll-queue: persisted queue-entry store — add/list/status/remove commands (FEAT-2682).

Operates on a dedicated ``.ll/queue.db`` (via :mod:`little_loops.queue_store`),
distinct from ``ll-loop queue``'s PID-liveness marker mechanism
(``cli/loop/queue.py``), which FEAT-2684 migrates separately.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from little_loops.queue_store import DEFAULT_DB_PATH as QUEUE_DB_PATH
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_queue"]

_STATUS_COLOR: dict[str, str] = {
    "pending": "33",
    "running": "36",
    "done": "32",
    "failed": "38;5;208",
}


def _classify_action(
    target: str,
    *,
    runner_override: str | None,
    timeout: int,
    arg_pairs: list[str] | None,
) -> Any:
    """Normalize a bare *target* string into an :class:`ActionSpec` (FEAT-2682).

    With an explicit ``--runner``, the classification is skipped and *target*
    is used verbatim as that runner's target. Otherwise classifies in order:
    an FSM loop name (resolves via ``resolve_loop_path``), a skill/command
    name (resolves via ``skill_expander``'s ``skills/<name>/SKILL.md`` /
    ``commands/<name>.md`` lookup), or — the fallback — a raw CLI invocation.
    """
    from little_loops.cli.loop._helpers import resolve_loop_path
    from little_loops.config.core import BRConfig
    from little_loops.runner_spec import ActionSpec, RunnerType
    from little_loops.skill_expander import _find_plugin_root, _resolve_content_path

    args_dict: dict[str, str] = {}
    for pair in arg_pairs or []:
        if "=" not in pair:
            raise ValueError(f"--arg must be KEY=VALUE, got: {pair!r}")
        key, _, value = pair.partition("=")
        args_dict[key] = value

    if runner_override is not None:
        runner = RunnerType(runner_override)
        return ActionSpec(
            name=target, runner=runner, target=target, args=args_dict, timeout=timeout
        )

    loops_dir = Path(BRConfig(Path.cwd()).loops.loops_dir)
    try:
        resolve_loop_path(target, loops_dir)
        return ActionSpec(
            name=target, runner=RunnerType.LOOP, target=target, args=args_dict, timeout=timeout
        )
    except FileNotFoundError:
        pass

    plugin_root = _find_plugin_root()
    if _resolve_content_path(plugin_root, target) is not None:
        return ActionSpec(
            name=target, runner=RunnerType.SKILL, target=target, args=args_dict, timeout=timeout
        )

    return ActionSpec(
        name=target, runner=RunnerType.CMD, target=target, args=args_dict, timeout=timeout
    )


def cmd_add(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import add_entry

    try:
        spec = _classify_action(
            args.target,
            runner_override=args.runner,
            timeout=args.timeout,
            arg_pairs=args.arg,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    entry = add_entry(spec, args.priority, db_path=QUEUE_DB_PATH)

    if getattr(args, "json", False):
        print_json(entry.to_dict())
        return 0

    print(
        f"Queued {colorize(entry.id[:8], '34')}  "
        f"{entry.action.runner.value}:{entry.action.target}  "
        f"priority={entry.priority}"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import list_entries

    entries = list_entries(QUEUE_DB_PATH)

    if getattr(args, "json", False):
        print_json([e.to_dict() for e in entries])
        return 0

    if not entries:
        print("Queue is empty")
        return 0

    print(colorize(f"Queue entries ({len(entries)}):", "1"))
    print()
    for entry in entries:
        short_id = entry.id[:8]
        status_color = _STATUS_COLOR.get(entry.status, "0")
        print(
            f"  {colorize(short_id, '34')}  {colorize(entry.priority, '1')}  "
            f"{colorize(entry.status, status_color)}  "
            f"{entry.action.runner.value}:{entry.action.target}  {entry.enqueued_at}"
        )
    return 0


def _not_found_or_ambiguous(args: argparse.Namespace) -> int | None:
    """Resolve ``args.id`` to an entry; print/return an error for 0 or >1 matches.

    Returns None (caller should proceed) if exactly one entry matched, on
    ``args._resolved_entry``. Returns an exit code (1) if it already handled
    the not-found / ambiguous case.
    """
    from little_loops.cli.output import print_json
    from little_loops.queue_store import AmbiguousEntryIdError, resolve_entry

    json_mode = getattr(args, "json", False)
    try:
        entry = resolve_entry(args.id, QUEUE_DB_PATH)
    except AmbiguousEntryIdError as exc:
        msg = str(exc)
        if json_mode:
            print_json({"error": msg, "id": args.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    if entry is None:
        msg = f"No queued entry with id '{args.id}'"
        if json_mode:
            print_json({"error": msg, "id": args.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    args._resolved_entry = entry
    return None


def cmd_status(args: argparse.Namespace) -> int:
    import json as _json

    from little_loops.cli.output import print_json, status_block

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry

    if getattr(args, "json", False):
        print_json(entry.to_dict())
        return 0

    print(
        status_block(
            {
                "id": entry.id,
                "action": f"{entry.action.runner.value}:{entry.action.target}",
                "priority": entry.priority,
                "status": entry.status,
                "enqueuedAt": entry.enqueued_at,
                "result": _json.dumps(entry.result) if entry.result else "-",
            }
        )
    )
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    from little_loops.cli.output import colorize, print_json
    from little_loops.queue_store import remove_entry

    code = _not_found_or_ambiguous(args)
    if code is not None:
        return code
    entry = args._resolved_entry
    json_mode = getattr(args, "json", False)

    if entry.status != "pending" and not getattr(args, "force", False):
        msg = (
            f"Entry '{entry.id[:8]}' is {entry.status}, not pending; "
            "use --force to remove anyway"
        )
        if json_mode:
            print_json({"error": msg, "id": entry.id})
        else:
            print(msg, file=sys.stderr)
        return 1

    remove_entry(entry.id, QUEUE_DB_PATH)
    if json_mode:
        print_json({"removed": entry.id})
    else:
        print(f"Removed {colorize(entry.id[:8], '34')}")
    return 0


def main_queue() -> int:
    """CLI handler for ll-queue subcommands."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-queue", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-queue",
            description="Persisted work-item queue: add/list/status/remove commands",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  ll-queue add audit-docs
  ll-queue add "pytest scripts/tests/" --runner cmd --priority P1
  ll-queue list --json
  ll-queue status abcd1234
  ll-queue remove abcd1234 --force
""",
        )

        subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
        subparsers.required = True

        add_parser = subparsers.add_parser(
            "add",
            help="Enqueue a work item (FSM loop, skill/command, or raw CLI invocation)",
            description="Classify and persist a new queue entry",
        )
        add_parser.add_argument(
            "target", help="Loop name, skill/command name, or raw CLI invocation"
        )
        add_parser.add_argument(
            "--priority",
            default="P3",
            choices=["P0", "P1", "P2", "P3", "P4", "P5"],
            help="Priority tier (default: P3)",
        )
        add_parser.add_argument(
            "--runner",
            default=None,
            choices=["skill", "cmd", "mcp", "prompt", "loop"],
            help="Force a specific runner kind instead of classifying the target",
        )
        add_parser.add_argument(
            "--arg",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Extra ActionSpec arg (repeatable)",
        )
        add_parser.add_argument(
            "--timeout", type=int, default=120, help="Timeout in seconds (default: 120)"
        )
        add_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        list_parser = subparsers.add_parser(
            "list", help="List all queue entries", description="List persisted queue entries"
        )
        list_parser.add_argument("--json", action="store_true", default=False, help="JSON output")

        status_parser = subparsers.add_parser(
            "status",
            help="Show a single entry's state and result",
            description="Show a queue entry by full id or 8+-char prefix",
        )
        status_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        status_parser.add_argument(
            "--json", action="store_true", default=False, help="JSON output"
        )

        remove_parser = subparsers.add_parser(
            "remove",
            help="Delete a pending entry",
            description="Delete a queue entry by full id or 8+-char prefix",
        )
        remove_parser.add_argument("id", help="Entry id (full uuid or 8+-char prefix)")
        remove_parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Remove even if the entry is not pending",
        )
        remove_parser.add_argument(
            "--json", action="store_true", default=False, help="JSON output"
        )

        parsed = parser.parse_args()

        if parsed.command == "add":
            return cmd_add(parsed)
        elif parsed.command == "list":
            return cmd_list(parsed)
        elif parsed.command == "status":
            return cmd_status(parsed)
        elif parsed.command == "remove":
            return cmd_remove(parsed)
        else:
            parser.print_help()
            return 1
