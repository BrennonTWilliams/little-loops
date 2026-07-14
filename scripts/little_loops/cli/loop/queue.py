"""ll-loop queue: inspect the process-backed run queue (.loops/.queue/*.json).

Verbs: ``list`` (FEAT-2618) inspects pending entries; ``remove`` (FEAT-2619)
cancels a queued waiter — verifying the tracked PID's *identity* (not just
liveness) before signaling it, terminating the waiter (SIGTERM), and deleting
its ``{id}.json`` entry.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path

import psutil

from little_loops.cli.loop._helpers import read_queue_entries
from little_loops.cli.output import colorize, print_json
from little_loops.fsm.concurrency import _process_alive


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


def _resolve_queue_entries(queue_dir: Path, target_id: str) -> list[tuple[Path, dict]]:
    """Return (path, entry) pairs in queue_dir whose id matches target_id.

    Matches the full uuid exactly, or an 8+-char prefix of the id (mirroring the
    short-id ``queue list`` renders). Unlike ``read_queue_entries``, this does
    NOT prune dead-PID entries — ``remove`` must still delete an entry whose
    tracked process has already exited, so a dead PID cannot make the file
    invisible. Malformed / unreadable files are skipped.
    """
    if not queue_dir.exists():
        return []
    matches: list[tuple[Path, dict]] = []
    for f in sorted(queue_dir.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        entry_id = str(data.get("id", ""))
        if not entry_id:
            continue
        if entry_id == target_id or (len(target_id) >= 8 and entry_id.startswith(target_id)):
            matches.append((f, data))
    return matches


def _verify_queue_pid_identity(pid: int, entry: dict) -> bool:
    """Return True if the live process at ``pid`` is genuinely a queued ll-loop waiter.

    Confirms identity — not merely liveness — before we signal, so a recycled
    PID now owned by an unrelated process is never killed (FEAT-2619). Checks the
    live command line for an ``ll-loop`` / ``little_loops.cli.loop`` marker, and
    as a fallback accepts a process whose ``create_time`` predates the entry's
    ``enqueuedAt`` (a long-lived waiter). Any psutil error
    (NoSuchProcess/AccessDenied/…) or an unparseable time yields False — the
    caller then refuses to signal (but still deletes the file) unless ``--force``.
    """
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        if "ll-loop" in cmdline or "little_loops.cli.loop" in cmdline:
            return True
        enqueued = str(entry.get("enqueuedAt", ""))
        if enqueued:
            from datetime import datetime

            enq_ts = datetime.fromisoformat(enqueued).timestamp()
            if proc.create_time() <= enq_ts:
                return True
        return False
    except Exception:
        return False


def cmd_queue_remove(args: argparse.Namespace, loops_dir: Path) -> int:
    """Cancel a queued waiter: verify identity, signal (SIGTERM), delete its entry.

    Resolves the target ``{id}.json`` by full uuid or 8+-char prefix. Verifies
    the tracked ``context.pid`` is really a live ll-loop waiter (psutil identity
    check, FEAT-2619 Option A) before signaling; ``--force`` bypasses the check.
    The entry file is ALWAYS deleted — the waiter's ``atexit`` cleanup does not
    fire on SIGTERM, so ``remove`` owns file deletion whether or not the signal
    landed. Never touches the running lock-holder (whose PID lives in a separate
    ``.running/`` namespace). Returns 0 on success, 1 for unknown/ambiguous id.
    """
    queue_dir = loops_dir / ".queue"
    target_id = args.id
    force = getattr(args, "force", False)
    json_mode = getattr(args, "json", False)

    matches = _resolve_queue_entries(queue_dir, target_id)

    if not matches:
        msg = f"No queued entry with id '{target_id}'"
        if json_mode:
            print_json({"error": msg, "id": target_id})
        else:
            print(msg)
        return 1

    if len(matches) > 1:
        ids = [str(e.get("id", "")) for _, e in matches]
        msg = f"Ambiguous id '{target_id}' matches {len(matches)} entries: {', '.join(ids)}"
        if json_mode:
            print_json({"error": msg, "id": target_id, "matches": ids})
        else:
            print(msg)
        return 1

    entry_path, entry = matches[0]
    entry_id = str(entry.get("id", ""))
    pid = entry.get("context", {}).get("pid")

    identity_ok = bool(force)
    if not identity_ok and pid is not None:
        identity_ok = _verify_queue_pid_identity(pid, entry)

    signaled = False
    if pid is not None and identity_ok and _process_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            signaled = True
        except OSError:
            signaled = False

    entry_path.unlink(missing_ok=True)

    if json_mode:
        print_json(
            {
                "id": entry_id,
                "removed": True,
                "signaled": signaled,
                "identityVerified": identity_ok,
                "pid": pid,
            }
        )
        return 0

    short_id = entry_id[:8] if entry_id else "?"
    if signaled:
        print(f"Removed queue entry {colorize(short_id, '34')} (signaled pid={pid}, SIGTERM)")
    elif pid is not None and not identity_ok:
        print(
            f"Removed queue entry {colorize(short_id, '34')} "
            f"({colorize('did not signal', '33')} pid={pid}: identity unverified; "
            f"pass --force to signal anyway)"
        )
    else:
        print(f"Removed queue entry {colorize(short_id, '34')} (pid={pid} not signaled)")
    return 0
