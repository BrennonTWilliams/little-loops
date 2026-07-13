"""ll-loop queue: inspect the process-backed run queue (.loops/.queue/*.json)."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import read_queue_entries
from little_loops.cli.output import colorize, print_json


def cmd_queue_list(args: argparse.Namespace, loops_dir: Path) -> int:
    """List pending entries in the process-backed run queue.

    Reads ``.loops/.queue/*.json`` via ``read_queue_entries()`` (which prunes
    dead-PID entries and returns them sorted ascending by ``enqueuedAt``), then
    renders id, loop name, PID, liveness, and enqueued time. Emits a JSON array
    when ``--json`` is set (``[]`` for an empty queue). See FEAT-2618.
    """
    queue_dir = loops_dir / ".queue"
    entries = read_queue_entries(queue_dir)

    if getattr(args, "json", False):
        print_json(entries)
        return 0

    if not entries:
        print("Queue is empty")
        return 0

    print(colorize(f"Pending queue entries ({len(entries)}):", "1"))
    print()
    for entry in entries:
        entry_id = str(entry.get("id", ""))
        short_id = entry_id[:8] if entry_id else "?"
        loop_name = entry.get("loopName", "?")
        pid = entry.get("context", {}).get("pid", "?")
        # read_queue_entries prunes dead-PID entries, so every returned entry is
        # live by construction (FEAT-2618 Open Questions, option a).
        liveness = colorize("alive", "32")
        enqueued = str(entry.get("enqueuedAt", ""))
        enqueued_disp = enqueued[:19].replace("T", " ") if enqueued else "?"
        print(
            f"  {colorize(short_id, '34')}  {colorize(str(loop_name), '1')}  "
            f"pid={pid}  {liveness}  {enqueued_disp}"
        )
    return 0
