"""Argparse CLI shim over the ENH-2565 spike queue library.

Usage::

    python -m scripts.tests.spike.rn_refine_synth_pop try-pop <run_dir>
    python -m scripts.tests.spike.rn_refine_synth_pop mark-complete <run_dir> <node_id>

Stdout-only contract (nothing else is written to stdout — no logs):

    try-pop        -> "<node_id>\\n"  on a successful pop
                   -> "DRAIN\\n"       if the queue is empty (no ready nodes AND drained)
                   -> "WAIT\\n"        if the queue is non-empty but nothing is ready yet
    mark-complete  -> touches rd/done/<node_id>.done; prints nothing

Always exits 0: the protocol has no failure modes of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .queue import mark_complete, queue_is_empty, try_pop_ready


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rn_refine_synth_pop",
        description="Readiness-gated concurrent pop for rn-refine synthesis (ENH-2565 spike).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pop = sub.add_parser("try-pop", help="atomically pop the deepest ready node")
    p_pop.add_argument("run_dir", help="run directory containing synth_queue.txt")

    p_done = sub.add_parser("mark-complete", help="touch the done-sentinel for a node")
    p_done.add_argument("run_dir", help="run directory")
    p_done.add_argument("node_id", help="node id to mark complete")

    args = parser.parse_args(argv)
    rd = Path(args.run_dir)

    if args.command == "try-pop":
        node = try_pop_ready(rd)
        if node is not None:
            sys.stdout.write(f"{node}\n")
        elif queue_is_empty(rd):
            sys.stdout.write("DRAIN\n")
        else:
            sys.stdout.write("WAIT\n")
        return 0

    if args.command == "mark-complete":
        mark_complete(rd, args.node_id)
        return 0

    return 0  # pragma: no cover — argparse enforces a valid subcommand


if __name__ == "__main__":
    raise SystemExit(main())
