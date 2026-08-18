"""ll-loop audit: deterministic counters for a loop run (ENH-2949).

Mechanical port of skills/audit-loop-run/SKILL.md's Steps 5.5/5.6/6a manual
counting/arithmetic (event tallies, tool-call counts, auxiliary-mutation
scan, budget-utilization ratio) into a `@dataclass` + `to_dict()` + `print_json`
CLI command — mirrors `scripts/little_loops/cli/loop/cleanup.py`'s shape
(ENH-2943 precedent). Only Steps 7-9 (rubric-vs-description audit, sub-loop
verdict-laundering detection, ranked improvement proposals) remain an LLM job
in the slimmed skill.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.cli.output import print_json

_AUX_EXCLUDED_NAMES = {
    "events.jsonl",
    "state.json",
    "summary.json",
    "usage.jsonl",
    "messages.jsonl",
    "meta-eval.jsonl",
}


@dataclass
class StateStats:
    entries: int = 0
    actions_complete: int = 0
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": self.entries,
            "actions_complete": self.actions_complete,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class RunAuditStats:
    run_id: str
    loop: str
    events_total: int
    events_by_type: dict[str, int] = field(default_factory=dict)
    per_state: dict[str, StateStats] = field(default_factory=dict)
    aux_mutation_count: int | None = None
    tool_call_count: int = 0
    diff_stall_present: bool = False
    steps_consumed: int = 0
    max_steps: int | None = None
    budget_utilization: float | None = None
    terminated_by: str | None = None
    failure_terminal: bool = False
    verdict_inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "loop": self.loop,
            "events_total": self.events_total,
            "events_by_type": self.events_by_type,
            "per_state": {name: s.to_dict() for name, s in self.per_state.items()},
            "aux_mutation_count": self.aux_mutation_count,
            "tool_call_count": self.tool_call_count,
            "diff_stall_present": self.diff_stall_present,
            "steps_consumed": self.steps_consumed,
            "max_steps": self.max_steps,
            "budget_utilization": (
                round(self.budget_utilization, 4) if self.budget_utilization is not None else None
            ),
            "terminated_by": self.terminated_by,
            "failure_terminal": self.failure_terminal,
            "verdict_inputs": self.verdict_inputs,
        }


def resolve_run(run: str | None, latest: str | None, loops_dir: Path) -> Path:
    """Resolve a run directory from either an explicit run-dir name or `--latest LOOP`.

    Mirrors the skill's Step 1 bash `ls -d .loops/.history/*-<loop>/ | sort | tail -1`.
    """
    from little_loops.fsm.persistence import HISTORY_DIR

    history_base = loops_dir / HISTORY_DIR

    if latest:
        suffix = f"-{latest}"
        candidates = sorted(
            (
                d
                for d in history_base.iterdir()
                if history_base.exists() and d.is_dir() and d.name.endswith(suffix)
            ),
            key=lambda d: d.name,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(f"No archived runs found for loop '{latest}'.")
        return candidates[0]

    if not run:
        raise FileNotFoundError("Either a run directory name or --latest LOOP is required.")

    run_dir = history_base / run
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run '{run}' not found under {history_base}.")
    return run_dir


def _read_events(run_dir: Path) -> list[dict[str, Any]]:
    events_file = run_dir / "events.jsonl"
    events: list[dict[str, Any]] = []
    if not events_file.exists():
        return events
    with open(events_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scan_aux_mutations(run_dir: Path, run_start_ts: str | None) -> int | None:
    """Filesystem-mtime fallback for auxiliary-mutation counting.

    Mirrors the skill's Step 5.5 filesystem fallback (used when the primary
    artifact path is gitignored or git evidence is otherwise unavailable):
    count files under `run_dir` modified after the run's start timestamp,
    excluding the loop's own bookkeeping files. Returns `None` (unknown) when
    the run start timestamp can't be parsed.
    """
    if not run_start_ts:
        return None
    try:
        start = datetime.fromisoformat(run_start_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)

    count = 0
    if not run_dir.exists():
        return 0
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.name in _AUX_EXCLUDED_NAMES:
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime >= start:
            count += 1
    return count


def audit_run(run_dir: Path, max_steps: int | None = None) -> RunAuditStats:
    """Compute deterministic counters for a single archived loop run.

    Reuses the event-stream access patterns of `ll-loop history`/`audit-meta`:
    defensive per-line JSONL parsing. `action_complete` events emitted after
    ENH-3240 carry their own `state` field and are attributed directly; older
    archived runs lack that field, so the `state_enter`-tracking correlation
    technique from `analytics/variance.py::_correlate_verdicts` is retained as
    a fallback for those. `evaluate` events never carry `state` and are always
    attributed via correlation.
    """
    events = _read_events(run_dir)
    state_data = _read_json_file(run_dir / "state.json") or {}
    summary = _read_json_file(run_dir / "summary.json")

    loop_name = str(state_data.get("loop_name", ""))
    dir_name = run_dir.name
    run_id = dir_name.removesuffix(f"-{loop_name}") if loop_name else dir_name

    events_by_type: dict[str, int] = {}
    per_state: dict[str, StateStats] = {}
    current_state: str | None = None
    tool_call_count = 0
    diff_stall_present = False
    terminated_by: str | None = None
    failure_terminal = False
    steps_consumed = 0

    for event in events:
        ev_type = event.get("event", "")
        events_by_type[ev_type] = events_by_type.get(ev_type, 0) + 1

        if ev_type == "state_enter":
            current_state = event.get("state")
            if current_state:
                per_state.setdefault(current_state, StateStats()).entries += 1
        elif ev_type == "action_complete":
            tool_call_count += 1
            # ENH-3240: prefer the event's own `state`, falling back to the
            # state_enter-tracked value for runs archived before this field
            # was added.
            action_state = event.get("state") or current_state
            if action_state:
                stats = per_state.setdefault(action_state, StateStats())
                stats.actions_complete += 1
                stats.duration_s += (event.get("duration_ms") or 0) / 1000.0
        elif ev_type == "evaluate":
            if event.get("type") == "diff_stall" and event.get("verdict") in ("stall", "no"):
                diff_stall_present = True
        elif ev_type == "loop_complete":
            terminated_by = event.get("terminated_by")
            failure_terminal = bool(event.get("failure_terminal", False))
            steps_consumed = int(event.get("iterations") or 0)

    aux_mutation_count = _scan_aux_mutations(run_dir, events[0].get("ts") if events else None)

    budget_utilization: float | None = None
    if max_steps:
        budget_utilization = steps_consumed / max_steps

    verdict_inputs: dict[str, Any] = {
        "terminated_by": terminated_by,
        "failure_terminal": failure_terminal,
    }
    if summary is not None:
        verdict_inputs["summary"] = summary

    return RunAuditStats(
        run_id=run_id,
        loop=loop_name,
        events_total=len(events),
        events_by_type=events_by_type,
        per_state=per_state,
        aux_mutation_count=aux_mutation_count,
        tool_call_count=tool_call_count,
        diff_stall_present=diff_stall_present,
        steps_consumed=steps_consumed,
        max_steps=max_steps,
        budget_utilization=budget_utilization,
        terminated_by=terminated_by,
        failure_terminal=failure_terminal,
        verdict_inputs=verdict_inputs,
    )


def _resolve_max_steps(loop_name: str, loops_dir: Path) -> int | None:
    """Best-effort `max_steps` lookup for budget-utilization; never raises."""
    try:
        from little_loops.cli.loop._helpers import load_loop_with_spec
        from little_loops.logger import Logger

        fsm, _spec = load_loop_with_spec(loop_name, loops_dir, Logger(verbose=False))
    except Exception:
        return None
    return fsm.max_steps


def cmd_audit(args: argparse.Namespace, loops_dir: Path) -> int:
    """Entry point for `ll-loop audit <run> [--latest LOOP] [--json]`."""
    run_arg = getattr(args, "run", None)
    latest = getattr(args, "latest", None)

    try:
        run_dir = resolve_run(run_arg, latest, loops_dir)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    max_steps: int | None = getattr(args, "max_steps", None)
    if max_steps is None:
        state_data = _read_json_file(run_dir / "state.json") or {}
        loop_name = state_data.get("loop_name")
        if loop_name:
            max_steps = _resolve_max_steps(str(loop_name), loops_dir)

    stats = audit_run(run_dir, max_steps=max_steps)

    if getattr(args, "json", False):
        print_json(stats.to_dict())
        return 0

    print(f"Audit for run: {stats.run_id} ({stats.loop})")
    print(f"  events_total={stats.events_total}  tool_call_count={stats.tool_call_count}")
    print(f"  aux_mutation_count={stats.aux_mutation_count}")
    print(f"  diff_stall_present={stats.diff_stall_present}")
    if stats.max_steps is not None:
        print(
            f"  budget_utilization={stats.budget_utilization:.2%} "
            f"({stats.steps_consumed}/{stats.max_steps} steps)"
        )
    print(f"  terminated_by={stats.terminated_by}  failure_terminal={stats.failure_terminal}")
    if stats.per_state:
        print("  per_state:")
        for name, s in stats.per_state.items():
            print(
                f"    {name}: entries={s.entries} actions_complete={s.actions_complete} "
                f"duration_s={s.duration_s:.1f}"
            )
    return 0
