"""State persistence and event streaming for FSM loops.

This module provides persistence capabilities for FSM loop execution:
- LoopState: Dataclass representing loop execution state
- StatePersistence: File I/O for state and events
- PersistentExecutor: Wrapper that persists state during execution
- Utility functions for listing running loops and reading history

File structure:
    .loops/
    ├── fix-types.yaml          # Loop definition
    ├── .running/               # Runtime state (auto-managed)
    │   ├── fix-types-20260503T122306.state.json
    │   └── fix-types-20260503T122306.events.jsonl
    └── .history/               # Archived run logs (auto-populated)
        └── 2024-01-15T103000-fix-types/
            ├── state.json
            ├── events.jsonl
            └── summary.json    # present when loop wrote one to run_dir
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.events import EventBus
from little_loops.fsm.concurrency import _process_alive
from little_loops.fsm.executor import EventCallback, ExecutionResult, FSMExecutor
from little_loops.fsm.schema import FSMLoop
from little_loops.fsm.validation import _is_meta_loop

RUNNING_DIR = ".running"
HISTORY_DIR = ".history"

RESUMABLE_STATUSES: frozenset[str] = frozenset(
    {"running", "awaiting_continuation", "interrupted", "user_stopped"}
)
# ENH-2522: "system_signal" is intentionally NOT in RESUMABLE_STATUSES — the runner
# died mid-state, so resume is unsafe. "user_stopped" IS in the set because the user
# ran `ll-loop stop` and the state on disk reflects a clean user-initiated pause.

logger = logging.getLogger(__name__)


def _json_safe_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON-serializable subset of *context* (BUG-2485).

    Persisting ``fsm.context`` for resume must never raise inside
    ``StatePersistence.save_state()`` (which calls a plain ``json.dumps`` with no
    ``default=``). Any value that cannot round-trip through JSON is dropped and
    debug-logged, so a stray non-serializable context value degrades gracefully
    (that key simply isn't restored on resume) instead of crashing the save.
    """
    safe: dict[str, Any] = {}
    for key, value in context.items():
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            logger.debug(
                "Dropping non-JSON-serializable context key %r from persisted loop state", key
            )
            continue
        safe[key] = value
    return safe


_RUN_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$")
_INSTANCE_SUFFIX = re.compile(r"-\d{8}T\d{6}$")


def _parse_run_folder(name: str) -> tuple[str, str] | None:
    """Return (run_id, loop_name) from a flat history folder name, or None."""
    m = _RUN_FOLDER.match(name)
    return (m.group(1), m.group(2)) if m else None


def _iso_now() -> str:
    """Return current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


def _verdict_is_yes(verdict: str) -> bool:
    """Return True if verdict maps to a positive (yes) outcome."""
    return verdict.startswith("yes") or verdict in ("progress", "success")


def _parse_diff_stat(text: str) -> dict[str, int] | None:
    """Parse 'git diff --stat' summary line into structured dict."""
    last_line = text.strip().rsplit("\n", 1)[-1] if text.strip() else ""
    m = re.search(
        r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?",
        last_line,
    )
    if not m:
        return None
    return {
        "files_changed": int(m.group(1)),
        "insertions": int(m.group(2) or 0),
        "deletions": int(m.group(3) or 0),
    }


def _get_diff_stats() -> dict[str, int] | None:
    """Run 'git diff --stat HEAD' and return structured stats, or None on failure."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return _parse_diff_stat(proc.stdout)
    except Exception:
        pass
    return None


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """Append one JSONL row and durably sync to disk before returning.

    ``f.flush()`` drains Python's user-space buffer into the kernel; ``os.fsync``
    then forces the kernel page cache to disk. Pairing both preserves the row
    across SIGKILL (which Python cannot trap) — closing the audit-trail gap
    surfaced by BUG-2501, where ``events.jsonl`` ended short of the actual
    transition count when a loop was hard-killed.

    Performance: per-call ``os.fsync()`` is ~1–10 ms on SSD. Acceptable for
    FSM run-audit JSONL writers, which append at most once per state
    transition.
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read_pid_file(pid_file: Path) -> int | None:
    """Read and validate a PID file, returning the PID or None."""
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _resolve_live_pid(running_dir: Path, stem: str, state: LoopState) -> int | None:
    """Return the canonical PID for an instance via .pid → .lock → state.pid chain.

    Returns None when no PID can be resolved from any source.
    """
    pid = _read_pid_file(running_dir / f"{stem}.pid")
    if pid is not None:
        return pid
    lock_file = running_dir / f"{stem}.lock"
    if lock_file.exists():
        try:
            with open(lock_file) as _lf:
                lock_data = json.load(_lf)
            pid = lock_data.get("pid")
            if pid is not None:
                return pid
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return state.pid


def _reconcile_stale_running(
    state: LoopState,
    persistence: StatePersistence,
    running_dir: Path,
    stem: str,
) -> LoopState:
    """Flip a running-state entry to interrupted when its PID is provably dead.

    Called on the read path in cmd_status and list_running_loops so orphaned
    foreground-crash entries self-heal without requiring manual cleanup-loops
    intervention.
    """
    if state.status != "running":
        return state
    pid = _resolve_live_pid(running_dir, stem, state)
    if pid is None:
        return state  # no PID resolvable — cannot determine liveness, leave alone
    if _process_alive(pid):
        return state
    state.status = "interrupted"
    state.reconciled_at = datetime.now(UTC).isoformat()
    persistence.save_state(state)
    return state


@dataclass
class LoopState:
    """Persistent state for an FSM loop execution.

    This captures all runtime state needed to resume a loop:
    - Current state and iteration
    - Captured variables and previous result
    - Last evaluation result
    - Timestamps and status

    Attributes:
        loop_name: Name of the loop
        current_state: Current FSM state name
        iteration: Current iteration count (1-based)
        captured: Captured action outputs by variable name
        prev_result: Previous state's result (output, exit_code, state)
        last_result: Last evaluation result (verdict, details)
        started_at: ISO timestamp when loop started
        updated_at: ISO timestamp when state was last saved
        status: Execution status (running, completed, failed, interrupted, awaiting_continuation, timed_out)
        continuation_prompt: Continuation context from handoff signal (if status is awaiting_continuation)
        accumulated_ms: Total milliseconds elapsed across all segments up to this save (used to restore
            elapsed time correctly after resume, so duration_ms and ${loop.elapsed_ms} reflect the
            full loop lifetime rather than only the most recent segment)
    """

    loop_name: str
    current_state: str
    iteration: int
    captured: dict[str, dict[str, Any]]
    prev_result: dict[str, Any] | None
    last_result: dict[str, Any] | None
    started_at: str
    updated_at: str
    status: (
        str  # "running", "completed", "failed", "interrupted", "awaiting_continuation", "timed_out"
    )
    continuation_prompt: str | None = None
    accumulated_ms: int = 0  # total elapsed ms across all segments (for resume offset)
    retry_counts: dict[str, int] = field(default_factory=dict)  # per-state retry tracking
    # Per-state rate-limit retry tracking (ENH-1133: dict-of-record).
    # Each record: {"short_retries": int, "long_retries": int,
    #               "total_wait_seconds": float, "first_seen_at": float | None}.
    # Legacy int values (dict[str, int]) are coerced in from_dict.
    rate_limit_retries: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Count of consecutive rate_limit_exhausted emissions across states. Reset
    # on any non-rate-limited state outcome. Persisted for resume durability.
    consecutive_rate_limit_exhaustions: int = 0
    # Per-edge revisit tracking for cycle detection.
    edge_revisit_counts: dict[str, int] = field(default_factory=dict)
    # BUG-2204: full-pass counter (maintain-mode restarts); 0 for loops without maintain.
    iteration_count: int = 0
    active_sub_loop: str | None = None  # name of currently executing sub-loop (observability)
    pid: int | None = None  # OS PID of the process that started this run (for reconciliation sweep)
    reconciled_at: str | None = None  # ISO timestamp when orphaned-running state was auto-flipped
    messages: list[str] = field(default_factory=list)
    # BUG-2485: full FSM context (positional input, program.md fields, --context
    # values) so resumed action templates that reference ${context.*} render
    # correctly. Kept internal to the on-disk state (emitted only when
    # include_context=True, i.e. the persistence path) so the CLI status/list JSON
    # contract is unchanged.
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_context: bool = False) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Args:
            include_context: When True (the on-disk persistence path), emit the
                JSON-safe ``context`` dict. Defaults to False so CLI-facing
                serializers (``ll-loop status/list --json``, transport events)
                keep ``context`` out of their public contract (BUG-2485).
        """
        result = {
            "loop_name": self.loop_name,
            "current_state": self.current_state,
            "iteration": self.iteration,
            "captured": self.captured,
            "prev_result": self.prev_result,
            "last_result": self.last_result,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "accumulated_ms": self.accumulated_ms,
        }
        if self.continuation_prompt is not None:
            result["continuation_prompt"] = self.continuation_prompt
        if self.retry_counts:
            result["retry_counts"] = self.retry_counts
        if self.rate_limit_retries:
            result["rate_limit_retries"] = self.rate_limit_retries
        if self.consecutive_rate_limit_exhaustions:
            result["consecutive_rate_limit_exhaustions"] = self.consecutive_rate_limit_exhaustions
        if self.edge_revisit_counts:
            result["edge_revisit_counts"] = self.edge_revisit_counts
        if self.iteration_count:
            result["iteration_count"] = self.iteration_count
        if self.active_sub_loop is not None:
            result["active_sub_loop"] = self.active_sub_loop
        if self.pid is not None:
            result["pid"] = self.pid
        if self.reconciled_at is not None:
            result["reconciled_at"] = self.reconciled_at
        if self.messages:
            result["messages"] = self.messages
        if include_context and self.context:
            safe_context = _json_safe_context(self.context)
            if safe_context:
                result["context"] = safe_context
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopState:
        """Create LoopState from dictionary.

        Migrates legacy ``rate_limit_retries`` values from ``dict[str, int]``
        (BUG-1107 pre-ENH-1133 shape) to the dict-of-record shape. Integer
        values are coerced to ``{"short_retries": <int>, "long_retries": 0,
        "total_wait_seconds": 0.0, "first_seen_at": None}``.

        Args:
            data: Dictionary with loop state fields

        Returns:
            LoopState instance
        """
        raw_rl = data.get("rate_limit_retries", {}) or {}
        migrated_rl: dict[str, dict[str, Any]] = {}
        for state_name, value in raw_rl.items():
            if isinstance(value, int):
                migrated_rl[state_name] = {
                    "short_retries": value,
                    "long_retries": 0,
                    "total_wait_seconds": 0.0,
                    "first_seen_at": None,
                }
            elif isinstance(value, dict):
                migrated_rl[state_name] = value
        return cls(
            loop_name=data["loop_name"],
            current_state=data["current_state"],
            iteration=data["iteration"],
            captured=data.get("captured", {}),
            prev_result=data.get("prev_result"),
            last_result=data.get("last_result"),
            started_at=data["started_at"],
            updated_at=data.get("updated_at", ""),
            status=data["status"],
            continuation_prompt=data.get("continuation_prompt"),
            accumulated_ms=data.get("accumulated_ms", 0),
            retry_counts=data.get("retry_counts", {}),
            rate_limit_retries=migrated_rl,
            consecutive_rate_limit_exhaustions=data.get("consecutive_rate_limit_exhaustions", 0),
            edge_revisit_counts=data.get("edge_revisit_counts", {}),
            iteration_count=data.get("iteration_count", 0),
            active_sub_loop=data.get("active_sub_loop"),
            pid=data.get("pid"),
            reconciled_at=data.get("reconciled_at"),
            messages=data.get("messages", []),
            context=data.get("context", {}),
        )


class StatePersistence:
    """Manage loop state persistence and event streaming.

    Handles file I/O for:
    - State file: JSON file with current execution state
    - Events file: JSONL file with execution events (append-only)

    Files are stored in .loops/.running/<instance_id>.*
    """

    def __init__(
        self, loop_name: str, loops_dir: Path | None = None, instance_id: str | None = None
    ) -> None:
        """Initialize persistence for a loop.

        Args:
            loop_name: Name of the loop
            loops_dir: Base directory for loops (default: .loops)
            instance_id: Optional unique instance identifier; falls back to loop_name when None
        """
        self.loop_name = loop_name
        self.loops_dir = loops_dir or Path(".loops")
        self.running_dir = self.loops_dir / RUNNING_DIR
        stem = instance_id or loop_name
        self.state_file = self.running_dir / f"{stem}.state.json"
        self.events_file = self.running_dir / f"{stem}.events.jsonl"
        self.meta_eval_file = self.running_dir / f"{stem}.meta-eval.jsonl"

    def initialize(self) -> None:
        """Create running directory if needed."""
        self.running_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: LoopState) -> None:
        """Save current state to file using an atomic write.

        Updates the updated_at timestamp before saving.  Writes to a temporary
        file first, then renames it over the target to avoid leaving a corrupt
        or empty state file if the process is killed mid-write.

        Args:
            state: LoopState to save
        """
        state.updated_at = _iso_now()
        # include_context=True: this is the on-disk persistence path, which must
        # carry fsm.context so resume can restore ${context.*} keys (BUG-2485).
        data = json.dumps(state.to_dict(include_context=True), indent=2)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(data)
            os.replace(tmp_path, self.state_file)
        except Exception:
            os.unlink(tmp_path)
            raise

    def load_state(self) -> LoopState | None:
        """Load state from file, or None if not exists.

        Returns:
            LoopState if file exists and is valid, None otherwise
        """
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text())
        except json.JSONDecodeError:
            return None
        try:
            return LoopState.from_dict(data)
        except KeyError as e:
            logger.warning("Corrupted state file %s: missing key %s", self.state_file, e)
            return None

    def clear_state(self) -> None:
        """Remove state file."""
        if self.state_file.exists():
            self.state_file.unlink()

    def append_event(self, event: dict[str, Any]) -> None:
        """Append event to JSONL file.

        Args:
            event: Event dictionary to append
        """
        _append_jsonl(self.events_file, event)

    def read_events(self) -> list[dict[str, Any]]:
        """Read all events from file.

        Returns:
            List of event dictionaries, empty if file doesn't exist
        """
        if not self.events_file.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(self.events_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines
        return events

    def clear_events(self) -> None:
        """Remove events file."""
        if self.events_file.exists():
            self.events_file.unlink()

    def clear_meta_eval(self) -> None:
        """Remove meta-eval file."""
        if self.meta_eval_file.exists():
            self.meta_eval_file.unlink()

    def archive_run(self, run_dir: Path | None = None) -> Path | None:
        """Archive current run files to .history/ before clearing.

        Reads the current state to derive the run timestamp, then copies
        state.json, events.jsonl, and (when present) meta-eval.jsonl and
        summary.json into:
            <loops_dir>/.history/<run_id>-<loop_name>/

        where run_id is a compact ISO timestamp derived from started_at
        (e.g. "2024-01-15T103000" from "2024-01-15T10:30:00.123456+00:00").

        Args:
            run_dir: Optional path to the loop's run directory. When provided,
                summary.json is copied from run_dir to the archive directory if
                it exists. Pass None (default) when the run directory is not
                available (e.g. stale-run cleanup paths).

        Returns:
            Path to the archive directory if files were archived, None if
            there were no files to archive (fresh run).
        """
        has_state = self.state_file.exists()
        has_events = self.events_file.exists()
        if not has_state and not has_events:
            return None

        # Derive run ID from started_at in state file, or fall back to now
        state = self.load_state()
        if state is not None and state.started_at:
            # Compact ISO: strip colons, dots, plus signs; take first 19 chars
            # e.g. "2024-01-15T10:30:00.123+00:00" → "2024-01-15T103000"
            run_id = state.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
        else:
            run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")

        run_folder = f"{run_id}-{self.loop_name}"
        archive_dir = self.loops_dir / HISTORY_DIR / run_folder
        archive_dir.mkdir(parents=True, exist_ok=True)

        if has_state:
            shutil.copy2(self.state_file, archive_dir / "state.json")
        if has_events:
            shutil.copy2(self.events_file, archive_dir / "events.jsonl")
        if self.meta_eval_file.exists():
            shutil.copy2(self.meta_eval_file, archive_dir / "meta-eval.jsonl")
        if run_dir is not None:
            summary_src = run_dir / "summary.json"
            if summary_src.exists():
                shutil.copy2(summary_src, archive_dir / "summary.json")

        return archive_dir

    def clear_all(self) -> None:
        """Archive current run files then clear state and events (for new run)."""
        self.archive_run()
        self.clear_state()
        self.clear_events()
        self.clear_meta_eval()


def _reconcile_stale_runs(loops_dir: Path) -> int:
    """Archive state files in .running/ that belong to dead or terminal processes.

    Called at loop startup to clean up files left by crashed or interrupted runs.
    Returns the count of archived files.

    Strategy (mirrors LockManager.find_conflict() stale-lock cleanup):
    - Terminal-status files (completed/failed/timed_out) are archived
      unconditionally — they are definitionally stale by invariant.
    - status="interrupted" files are left alone so the user can resume them.
    - status="running" files are checked via their sibling .pid file; archived
      only if the PID is confirmed dead. No .pid file → leave alone (can't confirm).
    """
    running_dir = loops_dir / RUNNING_DIR
    if not running_dir.exists():
        return 0

    terminal_statuses = {"completed", "failed", "timed_out"}
    archived = 0

    for state_file in running_dir.glob("*.state.json"):
        try:
            data = json.loads(state_file.read_text())
            state = LoopState.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError):
            continue

        is_stale = state.status in terminal_statuses

        if not is_stale and state.status == "running":
            stem = state_file.name.removesuffix(".state.json")
            pid_file = running_dir / f"{stem}.pid"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    is_stale = not _process_alive(pid)
                except (OSError, ValueError):
                    pass

        if not is_stale:
            continue

        stem = state_file.name.removesuffix(".state.json")
        instance_id = stem if stem != state.loop_name else None
        persistence = StatePersistence(
            loop_name=state.loop_name,
            loops_dir=loops_dir,
            instance_id=instance_id,
        )
        try:
            persistence.clear_all()
            (running_dir / f"{stem}.pid").unlink(missing_ok=True)
            archived += 1
            logger.debug("Archived stale run: %s (status=%s)", stem, state.status)
        except OSError as e:
            logger.warning("Failed to archive stale run %s: %s", stem, e)

    if archived:
        logger.info("Reconciliation sweep archived %d stale run(s) from .running/", archived)

    return archived


class PersistentExecutor:
    """FSM Executor with state persistence and event streaming.

    Wraps FSMExecutor to:
    - Save state after each state transition
    - Append events to JSONL file as they occur
    - Support resuming from saved state
    - Support graceful shutdown via signal handling
    """

    def __init__(
        self,
        fsm: FSMLoop,
        persistence: StatePersistence | None = None,
        loops_dir: Path | None = None,
        instance_id: str | None = None,
        pid: int | None = None,
        **executor_kwargs: Any,
    ) -> None:
        """Initialize persistent executor.

        Args:
            fsm: FSM loop definition
            persistence: Optional pre-configured persistence (for testing)
            loops_dir: Base directory for loops (default: .loops)
            instance_id: Optional unique instance identifier for file path scoping
            pid: OS PID of the running process; stored in saved state for reconciliation
            **executor_kwargs: Additional kwargs for FSMExecutor
        """
        from little_loops.fsm.handoff_handler import HandoffBehavior, HandoffHandler
        from little_loops.fsm.signal_detector import SignalDetector

        self.fsm = fsm
        self.loops_dir = loops_dir
        self._run_pid = pid
        self.persistence = persistence or StatePersistence(
            fsm.name, loops_dir or Path(".loops"), instance_id=instance_id
        )
        self.persistence.initialize()

        # Create signal detector and handler based on FSM config
        signal_detector = SignalDetector()
        handoff_handler = HandoffHandler(HandoffBehavior(fsm.on_handoff))

        # Create base executor with event callback that persists
        self._executor = FSMExecutor(
            fsm,
            event_callback=self._handle_event,
            signal_detector=signal_detector,
            handoff_handler=handoff_handler,
            loops_dir=self.loops_dir,
            **executor_kwargs,
        )
        self._last_result: dict[str, Any] | None = None
        self._last_non_llm_result: dict[str, Any] | None = None
        self._continuation_prompt: str | None = None
        self.event_bus = EventBus()

    @property
    def _on_event(self) -> EventCallback | None:
        """Backward-compatible access to the first observer on the event bus."""
        return self.event_bus._observers[0][0] if self.event_bus._observers else None

    @_on_event.setter
    def _on_event(self, callback: EventCallback | None) -> None:
        """Backward-compatible setter: replaces all observers with this one."""
        self.event_bus._observers.clear()
        if callback is not None:
            self.event_bus.register(callback)

    def close_transports(self) -> None:
        """Close all transports registered on the underlying EventBus."""
        self.event_bus.close_transports()

    def request_shutdown(self, marker_path: Path | None = None) -> None:
        """Request graceful shutdown of the executor.

        Delegates to the underlying FSMExecutor's request_shutdown method.
        The loop will exit cleanly after the current state completes,
        saving state as "interrupted" so it can be resumed later.

        Args:
            marker_path: Optional path to a user-stop.marker sentinel that
                tells the runner this shutdown came from ``ll-loop stop``
                rather than Ctrl-C (ENH-2522). When present at finish time,
                the executor tags the run as ``user_stopped`` instead of
                ``interrupted``.
        """
        self._executor.request_shutdown(marker_path=marker_path)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle event: persist to file and save state.

        Args:
            event: Event dictionary from executor
        """
        self.persistence.append_event(event)

        event_type = event.get("event")

        # Write per-state token usage to usage.jsonl when an LLM action completes.
        # Shell and mcp_tool invocations produce no token data and are skipped.
        if event_type == "action_complete" and "input_tokens" in event:
            run_dir = self.fsm.context.get("run_dir", "")
            if run_dir:
                usage_path = Path(run_dir) / "usage.jsonl"
                entry = {
                    "iteration": self._executor.iteration,
                    "state": self._executor.current_state,
                    "action_type": "prompt" if event.get("is_prompt") else "shell_or_mcp",
                    "input_tokens": event["input_tokens"],
                    "output_tokens": event["output_tokens"],
                    "cache_read_tokens": event.get("cache_read_tokens", 0),
                    "cache_creation_tokens": event.get("cache_creation_tokens", 0),
                    "model": event.get("model", "unknown"),
                    "timestamp": event.get("ts", ""),
                }
                _append_jsonl(usage_path, entry)

        # Append shared message to messages.jsonl when a state appends to the log.
        if event_type == "messages_append":
            run_dir = self.fsm.context.get("run_dir", "")
            if run_dir:
                messages_path = Path(run_dir) / "messages.jsonl"
                entry = {
                    "iteration": self._executor.iteration,
                    "state": event.get("state", ""),
                    "message": event.get("message", ""),
                    "timestamp": event.get("ts", ""),
                }
                _append_jsonl(messages_path, entry)

        # Save state after state transitions
        if event_type in ("state_enter", "loop_complete", "baseline_complete"):
            self._save_state()

        # Track evaluation results for state persistence
        if event_type == "evaluate":
            self._last_result = {
                "verdict": event.get("verdict"),
                "details": {
                    k: v for k, v in event.items() if k not in ("event", "ts", "type", "verdict")
                },
            }
            eval_type = event.get("type", "")
            if eval_type != "llm_structured":
                self._last_non_llm_result = {
                    "state": self._executor.current_state,
                    "evaluator": eval_type,
                    "verdict": event.get("verdict", ""),
                    "details": {
                        k: v
                        for k, v in event.items()
                        if k not in ("event", "ts", "type", "verdict")
                    },
                }
            elif _is_meta_loop(self.fsm):
                self._write_meta_eval_entry(event)

        # Track handoff events for continuation prompt
        if event_type == "handoff_detected":
            self._continuation_prompt = event.get("continuation")

        # Delegate to registered observers (e.g. progress display, extensions)
        self.event_bus.emit(event)

    def _write_meta_eval_entry(self, event: dict[str, Any]) -> None:
        """Append one JSONL entry to meta-eval.jsonl for an llm_structured evaluate in a meta-loop."""
        non_llm = self._last_non_llm_result or {}
        non_llm_details = non_llm.get("details", {})

        llm_verdict = event.get("verdict", "")
        ext_verdict = non_llm.get("verdict", "")
        agreed: bool | None = (
            _verdict_is_yes(llm_verdict) == _verdict_is_yes(ext_verdict) if ext_verdict else None
        )

        ext_value = non_llm_details.get("current", non_llm_details.get("value"))
        ext_target = non_llm_details.get("target")

        entry: dict[str, Any] = {
            "iteration": self._executor.iteration,
            "ts": _iso_now(),
            "loop": self.fsm.name,
            "state": self._executor.current_state,
            "llm_verdict": llm_verdict,
            "llm_rationale": (event.get("reason") or "")[:200],
            "external_verdict": ext_verdict or None,
            "external_state": non_llm.get("state"),
            "external_evaluator": non_llm.get("evaluator") or None,
            "external_value": str(ext_value) if ext_value is not None else None,
            "external_target": str(ext_target) if ext_target is not None else None,
            "diff_stats": _get_diff_stats(),
            "agreed": agreed,
        }
        _append_jsonl(self.persistence.meta_eval_file, entry)

    def _save_state(self) -> None:
        """Save current executor state to file."""
        status = "running"
        if self._executor.current_state:
            state_config = self.fsm.states.get(self._executor.current_state)
            if state_config and state_config.terminal:
                status = "completed"

        state = LoopState(
            loop_name=self.fsm.name,
            current_state=self._executor.current_state,
            iteration=self._executor.iteration,
            captured=self._executor.captured,
            prev_result=self._executor.prev_result,
            last_result=self._last_result,
            started_at=self._executor.started_at,
            updated_at="",  # Will be set by save_state
            status=status,
            accumulated_ms=_now_ms()
            - self._executor.start_time_ms
            + self._executor.elapsed_offset_ms,
            retry_counts=dict(self._executor._retry_counts),
            rate_limit_retries={k: dict(v) for k, v in self._executor._rate_limit_retries.items()},
            consecutive_rate_limit_exhaustions=(self._executor._consecutive_rate_limit_exhaustions),
            edge_revisit_counts=dict(self._executor._edge_revisit_counts),
            iteration_count=self._executor._iteration_count,
            pid=self._run_pid,
            messages=list(self._executor.messages),
            context=dict(self.fsm.context),
        )
        self.persistence.save_state(state)

    def archive_run_only(self, terminated_by: str) -> Path | None:
        """Archive the current run without re-entering executor.run().

        Signal-handler-safe: does NOT mutate executor state. Invokes save_state
        + archive_run. Returns the archive path or None if neither state.json
        nor events.jsonl exists.

        Mirrors the post-block of ``run()`` so the ``terminated_by`` →
        ``final_status`` mapping stays consistent. Used by
        ``_loop_signal_handler``'s second-SIGINT force-exit branch (ENH-2516)
        to close the audit-trail gap exposed by BUG-2501 / BUG-2513.

        Args:
            terminated_by: ``ExecutionResult.terminated_by`` value to map to a
                ``LoopState.status`` field. Use ``"interrupted_force"`` for a
                signal-driven force-exit (maps to ``status="interrupted"``).

        Returns:
            Path to the archive directory if files were archived, ``None`` if
            neither ``state.json`` nor ``events.jsonl`` exists.
        """
        final_status = "completed" if terminated_by == "terminal" else "failed"
        if terminated_by in (
            "max_steps",
            "max_iterations_reached",
            "interrupted",
            "interrupted_force",
        ):
            final_status = "interrupted"
        if terminated_by == "handoff":
            final_status = "awaiting_continuation"
        if terminated_by == "timeout":
            final_status = "timed_out"
        if terminated_by == "cycle_detected":
            final_status = "failed"
        # ENH-2522: user_stopped and system_signal share the "failed" terminal bucket
        # but remain distinct enum values so audit tooling can read the cause.

        final_state = LoopState(
            loop_name=self.fsm.name,
            current_state=self._executor.current_state,
            iteration=self._executor.iteration,
            captured=self._executor.captured,
            prev_result=self._executor.prev_result,
            last_result=self._last_result,
            started_at=self._executor.started_at,
            updated_at="",
            status=final_status,
            continuation_prompt=self._continuation_prompt,
            accumulated_ms=_now_ms()
            - self._executor.start_time_ms
            + self._executor.elapsed_offset_ms,
            context=dict(self.fsm.context),
        )
        self.persistence.save_state(final_state)
        run_dir_str = self.fsm.context.get("run_dir", "")
        return self.persistence.archive_run(run_dir=Path(run_dir_str) if run_dir_str else None)

    def run(self, clear_previous: bool = True) -> ExecutionResult:
        """Run the FSM with persistence.

        Args:
            clear_previous: If True, clear previous state/events before running

        Returns:
            ExecutionResult from the execution
        """
        if clear_previous:
            self.persistence.clear_all()

        result = self._executor.run()

        # Update final state
        final_status = "completed" if result.terminated_by == "terminal" else "failed"
        if result.terminated_by in ("max_steps", "max_iterations_reached", "interrupted"):
            final_status = "interrupted"
        if result.terminated_by == "handoff":
            final_status = "awaiting_continuation"
        if result.terminated_by == "timeout":
            final_status = "timed_out"
        if result.terminated_by == "cycle_detected":
            final_status = "failed"
        # ENH-2522: user_stopped and system_signal share the "failed" terminal bucket
        # but remain distinct enum values so audit tooling can read the cause.

        final_state = LoopState(
            loop_name=self.fsm.name,
            current_state=result.final_state,
            iteration=result.iterations,
            captured=result.captured,
            prev_result=self._executor.prev_result,
            last_result=self._last_result,
            started_at=self._executor.started_at,
            updated_at="",
            status=final_status,
            continuation_prompt=self._continuation_prompt,
            accumulated_ms=result.duration_ms,
            context=dict(self.fsm.context),
        )
        self.persistence.save_state(final_state)
        run_dir_str = self.fsm.context.get("run_dir", "")
        self.persistence.archive_run(run_dir=Path(run_dir_str) if run_dir_str else None)

        return result

    def resume(self) -> ExecutionResult | None:
        """Resume from saved state, or None if no resumable state.

        Resumable states are: "running", "awaiting_continuation", and "interrupted".

        Returns:
            ExecutionResult if resumed and completed, None if no resumable state
        """
        state = self.persistence.load_state()
        if state is None:
            return None

        if state.status not in RESUMABLE_STATUSES:
            return None  # Already completed/failed

        # Restore executor state
        self._executor.current_state = state.current_state
        self._executor.iteration = state.iteration
        self._executor.captured = state.captured
        self._executor.prev_result = state.prev_result
        self._executor.started_at = state.started_at
        self._last_result = state.last_result
        self._executor._retry_counts = dict(state.retry_counts)
        self._executor._rate_limit_retries = {
            k: dict(v) for k, v in state.rate_limit_retries.items()
        }
        self._executor._consecutive_rate_limit_exhaustions = (
            state.consecutive_rate_limit_exhaustions
        )
        self._executor._edge_revisit_counts = dict(state.edge_revisit_counts)
        self._executor._iteration_count = state.iteration_count
        self._executor.messages = list(state.messages)

        # BUG-2485: restore the persisted FSM context (positional input, program.md
        # fields, prior --context values) so resumed action templates referencing
        # ${context.*} render instead of raising "Path 'input' not found in context".
        # setdefault: anything already on fsm.context (resume-time --context
        # overrides and re-derived run_dir/input_hash applied by cmd_resume before
        # this runs) wins over the persisted base.
        for key, value in state.context.items():
            self.fsm.context.setdefault(key, value)

        # Restore accumulated elapsed time so duration_ms and ${loop.elapsed_ms} reflect
        # the full loop lifetime (all segments), not just the resumed segment.
        # FSMExecutor.run() will reset start_time_ms to _now_ms(), so we use elapsed_offset_ms
        # to carry forward the time already spent before this resume.
        self._executor.elapsed_offset_ms = state.accumulated_ms

        # Clear any pending signals from previous run
        self._executor._pending_handoff = None
        self._executor._pending_error = None

        # Emit resume event with continuation context if available
        resume_event: dict[str, Any] = {
            "event": "loop_resume",
            "ts": _iso_now(),
            "loop": self.fsm.name,
            "from_state": state.current_state,
            "iteration": state.iteration,
        }
        if state.status == "awaiting_continuation" and state.continuation_prompt:
            resume_event["from_handoff"] = True
            resume_event["continuation_prompt"] = state.continuation_prompt
        self.persistence.append_event(resume_event)
        self.event_bus.emit(resume_event)

        # Continue execution (don't clear previous events)
        return self.run(clear_previous=False)


def _find_instances(loop_name: str, running_dir: Path) -> list[tuple[str | None, LoopState]]:
    """Discover all state-file instances for *loop_name* in *running_dir*.

    Globs ``{loop_name}-*.state.json`` for instance-scoped files and
    ``{loop_name}.state.json`` for legacy bare-name files.

    Returns:
        List of ``(instance_id, LoopState)`` tuples sorted by file name.
        *instance_id* is the file stem (e.g. ``"autodev-20260503T122306"``)
        for instance-scoped files, or ``None`` for legacy bare-name files.
    """
    if not running_dir.exists():
        return []

    instances: list[tuple[str | None, LoopState]] = []

    # Instance-scoped files: {loop_name}-YYYYMMDDTHHMMSS.state.json
    # Use Path(stem).stem to strip both suffixes (.state.json → base stem).
    for state_file in sorted(running_dir.glob(f"{loop_name}-*.state.json")):
        base_stem = Path(state_file.stem).stem  # e.g. "autodev-20260503T122306"
        if not _INSTANCE_SUFFIX.search(base_stem):
            continue  # skip files like "loop-name-extra" that don't match timestamp pattern
        try:
            data = json.loads(state_file.read_text())
            instances.append((base_stem, LoopState.from_dict(data)))
        except (json.JSONDecodeError, KeyError):
            continue

    # Legacy bare-name file: {loop_name}.state.json
    legacy_file = running_dir / f"{loop_name}.state.json"
    if legacy_file.exists():
        try:
            data = json.loads(legacy_file.read_text())
            instances.append((None, LoopState.from_dict(data)))
        except (json.JSONDecodeError, KeyError):
            pass

    return instances


def list_running_loops(loops_dir: Path | None = None) -> list[LoopState]:
    """List all loops with saved state.

    Args:
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of LoopState objects for all loops with state files
    """
    base_dir = loops_dir or Path(".loops")
    running_dir = base_dir / RUNNING_DIR

    if not running_dir.exists():
        return []

    states: list[LoopState] = []
    for state_file in running_dir.glob("*.state.json"):
        try:
            data = json.loads(state_file.read_text())
            state = LoopState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            continue  # Skip malformed files
        stem = state_file.stem.removesuffix(".state")
        persistence = StatePersistence(
            state.loop_name, base_dir, instance_id=stem if stem != state.loop_name else None
        )
        state = _reconcile_stale_running(state, persistence, running_dir, stem)
        states.append(state)

    # Include loops that have a PID file but no state file yet (still starting up).
    # Match on the full instance stem (not the logical name) to avoid suppressing a
    # live PID file when a *different* instance of the same loop has a stale state
    # file — as observed in BUG-2386 where the state file lived in the worktree.
    known_stems = {
        Path(sf.stem).stem  # strip double suffix: loop-20260628T.state.json → loop-20260628T
        for sf in running_dir.glob("*.state.json")
    }
    for pid_file in running_dir.glob("*.pid"):
        if pid_file.stem in known_stems:
            continue  # exact instance already has a state file
        logical_name = _INSTANCE_SUFFIX.sub("", pid_file.stem)
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            continue
        if _process_alive(pid):
            states.append(
                LoopState(
                    loop_name=logical_name,
                    current_state="(initializing)",
                    iteration=0,
                    captured={},
                    prev_result=None,
                    last_result=None,
                    started_at="",
                    updated_at="",
                    status="starting",
                )
            )

    return states


def list_run_history(loop_name: str, loops_dir: Path | None = None) -> list[LoopState]:
    """List archived runs for a loop, newest first.

    Reads state files from .loops/.history/<run_id>-<loop_name>/state.json and
    returns them sorted by started_at descending (most recent run first).

    Also checks the legacy nested layout .loops/.history/<loop_name>/*/state.json
    for backward compatibility with existing history folders.

    Args:
        loop_name: Name of the loop
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of LoopState objects for all archived runs, newest first.
        Returns an empty list if no history exists.
    """
    base_dir = loops_dir or Path(".loops")
    history_dir = base_dir / HISTORY_DIR

    if not history_dir.exists():
        return []

    states: list[LoopState] = []

    # Flat layout: <run_id>-<loop_name>/state.json
    for state_file in history_dir.glob(f"*-{loop_name}/state.json"):
        try:
            data = json.loads(state_file.read_text())
            states.append(LoopState.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue

    # Backward compat: legacy nested layout <loop_name>/<run_id>/state.json
    old_loop_dir = history_dir / loop_name
    if old_loop_dir.exists():
        logger.warning(
            "Found legacy nested history at %s; migrate to flat layout by moving "
            "each run to .history/<run_id>-%s/",
            old_loop_dir,
            loop_name,
        )
        for state_file in old_loop_dir.glob("*/state.json"):
            try:
                data = json.loads(state_file.read_text())
                states.append(LoopState.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

    states.sort(key=lambda s: s.started_at, reverse=True)
    return states


def get_archived_events(
    loop_name: str, run_id: str, loops_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Read events for a specific archived run.

    Args:
        loop_name: Name of the loop
        run_id: The run directory name (compact timestamp)
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of event dictionaries, empty if not found.
    """
    base_dir = loops_dir or Path(".loops")
    run_folder = f"{run_id}-{loop_name}"
    events_file = base_dir / HISTORY_DIR / run_folder / "events.jsonl"

    if not events_file.exists():
        return []

    events: list[dict[str, Any]] = []
    with open(events_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def get_loop_history(loop_name: str, loops_dir: Path | None = None) -> list[dict[str, Any]]:
    """Get event history for a loop.

    Args:
        loop_name: Name of the loop
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of event dictionaries
    """
    persistence = StatePersistence(loop_name, loops_dir)
    return persistence.read_events()
