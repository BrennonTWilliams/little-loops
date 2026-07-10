"""Readiness-gated concurrent pop for rn-refine bottom-up synthesis (ENH-2565).

This module is the concurrency core of rn-refine's parallel integration phase. It
is invoked by the ``oracles/integrate-node`` worker sub-loop (which rn-refine
background-spawns N-wide) both as a library and as a CLI. It exposes three pure
functions over a single run directory ``rd``:

    try_pop_ready(rd)          -> str | None   atomically pop the deepest ready node
    mark_complete(rd, node_id) -> None         touch the done-sentinel (idempotent)
    queue_is_empty(rd)         -> bool         is synth_queue.txt drained?

Queue format (produced by ``rn-refine.yaml:build_synth`` / ``resume_build_synth``)
---------------------------------------------------------------------------------
``rd/synth_queue.txt`` holds one internal-node id per line, deepest-first
(a node always sorts after every one of its children). ``rd/edges.tsv`` holds
``parent<TAB>child<TAB>title`` rows. A node's refined output lands at
``rd/nodes/<node>/final.md`` — leaves are backfilled by ``build_synth``,
internal nodes are written by the integrate prompt after their children roll up.

Implicit-barrier property
-------------------------
There is NO explicit join or barrier primitive at the protocol level, and none is
needed. N concurrent workers each loop ``try_pop_ready`` -> integrate ->
``mark_complete``. A node is *ready* only once every child has been integrated
(its ``final.md`` exists), so the deepest-first readiness gate serializes each
parent strictly after all of its children without any worker ever blocking on a
barrier-wait. When ``synth_queue.txt`` is empty, every worker's next
``try_pop_ready`` returns ``None`` and ``queue_is_empty`` returns ``True`` — that
shared DRAIN state IS the barrier. (rn-refine additionally ``wait``s on the worker
PIDs in ``synth_dispatch`` so ``assemble`` only runs once every worker has exited.)

``try_pop_ready`` returning ``None`` is deliberately overloaded: it means DRAIN
(queue empty, nothing left) OR WAIT (queue non-empty but no node is ready yet,
because some child is still integrating). Callers disambiguate with
``queue_is_empty(rd)``: empty => route to assemble; non-empty => sleep and retry.

Locking
-------
A single advisory lock at ``rd/.queue.lock`` (via
``little_loops.file_utils.acquire_lock``) guards the read-select-rewrite of
``synth_queue.txt`` together with the ``in_flight/<node>.pending`` marker, making
the pop atomic: no node is ever popped twice and no ready node is ever lost
under N-worker contention. The child ``final.md`` existence checks that decide
readiness are read-only snapshots of files written by the integrate prompt outside
this lock; ``done/<node>.done`` writes in ``mark_complete`` are idempotent
touches and take no lock.

CLI
---
    python -m little_loops.rn_synth_queue try-pop <run_dir>
        -> "<node_id>\\n"  on a successful pop
        -> "DRAIN\\n"       if the queue is empty (drained)
        -> "WAIT\\n"        if the queue is non-empty but nothing is ready yet
    python -m little_loops.rn_synth_queue mark-complete <run_dir> <node_id>
        -> touches rd/done/<node_id>.done; prints nothing

Always exits 0: the protocol has no failure modes of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.file_utils import acquire_lock

LOCK_NAME = ".queue.lock"
QUEUE_NAME = "synth_queue.txt"


def _read_queue(rd: Path) -> list[str]:
    """Return the non-blank queued node-ids in file order (deepest-first)."""
    sq = rd / QUEUE_NAME
    if not sq.exists():
        return []
    return [ln.strip() for ln in sq.read_text().splitlines() if ln.strip()]


def _write_queue(rd: Path, nodes: list[str]) -> None:
    (rd / QUEUE_NAME).write_text("".join(f"{n}\n" for n in nodes))


def _children_of(rd: Path) -> dict[str, list[str]]:
    """Parse ``edges.tsv`` into a parent -> [child, ...] map.

    Re-read on every pop (inside the lock); ``edges.tsv`` is tiny (<= one row
    per edge, <= K rows for K internal nodes) so the parse is sub-millisecond
    at rn-refine plan sizes.
    """
    edges = rd / "edges.tsv"
    children: dict[str, list[str]] = {}
    if edges.exists():
        for line in edges.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                children.setdefault(parts[0], []).append(parts[1])
    return children


def _is_ready(rd: Path, node_id: str, children: dict[str, list[str]]) -> bool:
    """True iff every child of ``node_id`` has a ``final.md`` (vacuously true for none)."""
    for child in children.get(node_id, []):
        if not (rd / "nodes" / child / "final.md").exists():
            return False
    return True


def try_pop_ready(rd: Path, lock_timeout: float = 10.0) -> str | None:
    """Atomically pop the deepest ready internal node, or return None.

    Ready iff every child of ``node`` in ``rd/edges.tsv`` has
    ``rd/nodes/<child>/final.md``. Returns the popped node-id, or None if the
    queue is empty (DRAIN) OR the queue is non-empty but no node is ready yet
    (WAIT). Caller disambiguates via ``queue_is_empty(rd)``.

    The read-select-rewrite of ``synth_queue.txt`` and the ``in_flight`` marker
    happen under a single exclusive lock, so concurrent callers never pop the
    same node twice and never lose a ready node.
    """
    rd = Path(rd)
    with acquire_lock(rd / LOCK_NAME, timeout=lock_timeout):
        queue = _read_queue(rd)  # already deepest-first
        if not queue:
            return None
        children = _children_of(rd)
        for idx, node_id in enumerate(queue):
            if _is_ready(rd, node_id, children):
                _write_queue(rd, queue[:idx] + queue[idx + 1 :])
                in_flight = rd / "in_flight"
                in_flight.mkdir(parents=True, exist_ok=True)
                (in_flight / f"{node_id}.pending").touch()
                return node_id
        # Queue non-empty but nothing ready yet: WAIT.
        return None


def mark_complete(rd: Path, node_id: str) -> None:
    """Touch ``rd/done/<node_id>.done``. Idempotent.

    Also clears the node's ``in_flight/<node_id>.pending`` marker if present.
    Both operations are idempotent and lock-free: each node is completed by the
    single worker that popped it, so there is no contention on its markers.
    """
    rd = Path(rd)
    done_dir = rd / "done"
    done_dir.mkdir(parents=True, exist_ok=True)
    (done_dir / f"{node_id}.done").touch()
    pending = rd / "in_flight" / f"{node_id}.pending"
    try:
        pending.unlink()
    except FileNotFoundError:
        pass


def queue_is_empty(rd: Path) -> bool:
    """True iff ``rd/synth_queue.txt`` is missing or has no non-blank lines."""
    return not _read_queue(Path(rd))


def main(argv: list[str] | None = None) -> int:
    """Stdout-only CLI over the queue protocol; always exits 0.

    ``try-pop`` prints the popped node id, or ``DRAIN`` (queue empty) / ``WAIT``
    (non-empty, nothing ready) so a shell worker can route without a second call.
    ``mark-complete`` touches the done-sentinel and prints nothing.
    """
    parser = argparse.ArgumentParser(
        prog="little_loops.rn_synth_queue",
        description="Readiness-gated concurrent pop for rn-refine synthesis (ENH-2565).",
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
