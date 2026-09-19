"""ll-loop cleanup: classify stuck/stale loops, archive stale interrupted, emit JSON."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from little_loops.fsm.concurrency import _process_alive
from little_loops.fsm.persistence import (
    ACTIVE_RUN_STATUSES,
    HISTORY_DIR,
    RUNNING_DIR,
    StatePersistence,
    _find_instances,
    _read_pid_file,
    list_running_loops,
)
from little_loops.logger import Logger


class RunClass(Enum):
    """The 6-way classification. Order matters for reporting (most-actionable first)."""

    STUCK_RUNNING = "stuck_running"  # status=running, pid dead OR updated_at > threshold
    STALE_INTERRUPTED = "stale_interrupted"  # status=interrupted, orphaned pid file
    STALE_INTERRUPTED_AGED = "stale_interrupted_aged"  # status=interrupted, aged, no pid
    ABANDONED_HANDOFF = "abandoned_handoff"  # status=awaiting_continuation, aged
    TERMINAL = "terminal"  # status=failed/timed_out — diagnostic only, do not auto-clean
    HEALTHY = "healthy"  # running alive, or fresh terminal states


@dataclass
class CleanupThresholds:
    """Tunable thresholds (minutes / hours). Defaults match the skill's behavior."""

    running_stale_minutes: float = 15.0  # status=running → stuck if updated_at > this
    interrupted_aged_hours: float = 24.0  # status=interrupted (no pid) → aged if > this


@dataclass
class CleanupEntry:
    """Per-run cleanup classification result."""

    loop: str
    instance_id: str
    status: str
    cls: RunClass
    age_minutes: float
    pid: int | None
    pid_alive: bool
    pid_source: str | None
    action_taken: str = "none"  # "none" | "stopped" | "archived"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cls"] = self.cls.value
        return d


def _age_minutes(updated_at: str, now: datetime | None = None) -> float:
    """Compute age in minutes from an ISO 8601 timestamp."""
    now = now or datetime.now(UTC)
    ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return (now - ts).total_seconds() / 60.0


def _pid_alive(pid: int | None) -> bool:
    """True if pid is non-None and the process is alive."""
    if pid is None:
        return False
    return _process_alive(pid)


def _classify(status: str, pid_alive_v: bool, age_minutes_v: float, t: CleanupThresholds) -> RunClass:
    """Pure classification: status × pid_liveness × age."""
    if status == "running":
        if (pid_alive_v is False) or age_minutes_v > t.running_stale_minutes:
            return RunClass.STUCK_RUNNING
        return RunClass.HEALTHY
    if status == "interrupted":
        if pid_alive_v:  # pid exists and is alive → orphaned lock holder
            return RunClass.STALE_INTERRUPTED
        # No pid (or dead pid) and aged
        if age_minutes_v > t.interrupted_aged_hours * 60:
            return RunClass.STALE_INTERRUPTED_AGED
        return RunClass.HEALTHY  # recent interrupt, leave alone
    if status == "awaiting_continuation":
        if age_minutes_v > t.running_stale_minutes:
            return RunClass.ABANDONED_HANDOFF
        return RunClass.HEALTHY
    if status in ("failed", "timed_out"):
        return RunClass.TERMINAL
    return RunClass.HEALTHY


def _collect_state(stem: str, running_dir: Path, lock_data: dict | None) -> tuple[str | None, str | None]:
    """Read pid and lock-data for `stem`. Returns (pid, pid_source) where pid_source is 'pid_file' or 'lock_file'."""
    pid_file = running_dir / f"{stem}.pid"
    pid = _read_pid_file(pid_file)
    if pid is not None:
        return pid, "pid_file"
    if lock_data and "pid" in lock_data:
        return lock_data["pid"], "lock_file"
    return None, None


def _archive_stale_interrupted_aged(
    stem: str, state_persistence: StatePersistence, running_dir: Path, dry_run: bool
) -> str:
    """Archive one stale-interrupted-aged run. Returns action label."""
    if dry_run:
        return "would_archive"
    archived = state_persistence.archive_run()
    if archived:
        # Clear the .state.json / .events.jsonl / .meta-eval.jsonl after archiving.
        for ext in ("state.json", "events.jsonl", "meta-eval.jsonl"):
            p = running_dir / f"{stem}.{ext}"
            if p.exists():
                p.unlink()
        return "archived"
    return "none"


def _stop_stuck_running(loop: str, loops_dir: Path, dry_run: bool) -> str:
    """Stop a stuck-running loop via ll-loop stop. Returns action label."""
    if dry_run:
        return "would_stop"
    # Subprocess the CLI; circular imports prevent direct import here.
    import subprocess
    rc = subprocess.run(
        ["ll-loop", "stop", loop], capture_output=True, text=True, cwd=str(loops_dir.parent)
    ).returncode
    return "stopped" if rc == 0 else "stop_failed"


def cleanup(
    *,
    dry_run: bool = True,
    loops_dir: Path,
    thresholds: CleanupThresholds | None = None,
) -> list[CleanupEntry]:
    """Discover all loop state files, classify each, and run cleanup actions."""
    thresholds = thresholds or CleanupThresholds()
    now = datetime.now(UTC)
    states = list_running_loops(loops_dir)
    entries: list[CleanupEntry] = []
    running_dir = loops_dir / RUNNING_DIR

    for state in states:
        stem = state.loop_name
        instances = _find_instances(stem, running_dir)
        if not instances:
            continue
        instance_id, _st = instances[0]
        # Read lock data if present.
        lock_data: dict | None = None
        lock_file = running_dir / f"{stem}.lock"
        if lock_file.exists():
            try:
                import json as _json
                lock_data = _json.loads(lock_file.read_text())
            except (OSError, ValueError):
                lock_data = None
        pid, pid_source = _collect_state(stem, running_dir, lock_data)
        age = _age_minutes(state.updated_at, now)
        cls = _classify(state.status, _pid_alive(pid), age, thresholds)

        # Apply actions for actionable classes.
        action = "none"
        if cls == RunClass.STUCK_RUNNING and not dry_run:
            action = _stop_stuck_running(stem, loops_dir, dry_run=False)
        elif cls == RunClass.STALE_INTERRUPTED_AGED:
            persistence = StatePersistence(stem, loops_dir, instance_id=instance_id)
            action = _archive_stale_interrupted_aged(
                instance_id or stem, persistence, running_dir, dry_run=dry_run
            )

        entries.append(
            CleanupEntry(
                loop=stem,
                instance_id=instance_id or "",
                status=state.status,
                cls=cls,
                age_minutes=age,
                pid=pid,
                pid_alive=_pid_alive(pid),
                pid_source=pid_source,
                action_taken=action,
            )
        )

    # Sort: most-actionable first, then by age desc.
    priority_order = {
        RunClass.STUCK_RUNNING: 0,
        RunClass.STALE_INTERRUPTED: 1,
        RunClass.STALE_INTERRUPTED_AGED: 2,
        RunClass.ABANDONED_HANDOFF: 3,
        RunClass.TERMINAL: 4,
        RunClass.HEALTHY: 5,
    }
    entries.sort(key=lambda e: (priority_order[e.cls], -e.age_minutes))
    return entries


def cmd_cleanup(args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int:
    """CLI entry point for `ll-loop cleanup`. Always emits JSON; --dry-run previews actions."""
    thresholds = CleanupThresholds(
        running_stale_minutes=float(getattr(args, "threshold", 15.0)),
        interrupted_aged_hours=float(getattr(args, "interrupted_age", 24.0)),
    )
    entries = cleanup(dry_run=args.dry_run, loops_dir=loops_dir, thresholds=thresholds)

    if getattr(args, "json", False):
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return 0

    # Human-readable summary (mirrors the skill's output shape).
    by_class: dict[str, list[CleanupEntry]] = {}
    for e in entries:
        by_class.setdefault(e.cls.value, []).append(e)

    actionable = {"stuck_running", "stale_interrupted", "stale_interrupted_aged"}
    has_actionable = any(c in by_class for c in actionable)
    if not has_actionable:
        print("No stuck or stale loops found.")
    else:
        for cls_name in ["stuck_running", "stale_interrupted", "stale_interrupted_aged"]:
            if cls_name not in by_class:
                continue
            for e in by_class[cls_name]:
                pid_str = (
                    f"PID: {e.pid} (dead)"
                    if e.pid and not e.pid_alive
                    else f"PID: {e.pid} (alive)"
                    if e.pid
                    else "no PID"
                )
                age_str = f"{e.age_minutes:.0f}m"
                print(
                    f"  [{e.cls.value}] {e.loop} — status: {e.status} — "
                    f"{pid_str} — last updated: {age_str} ago — action: {e.action_taken}"
                )
        if by_class.get("abandoned_handoff"):
            print("\nNEEDS ATTENTION (manual resume recommended):")
            for e in by_class["abandoned_handoff"]:
                print(f"  [{e.cls.value}] {e.loop} — last updated: {e.age_minutes:.0f}m ago")

    if args.dry_run:
        print("\nNo changes applied (--dry-run).")
    return 0
