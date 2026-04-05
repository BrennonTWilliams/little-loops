"""JSON Schema generation for all 19 LLEvent types.

Generates one JSON Schema (draft-07) file per event type to docs/reference/schemas/.
Schemas validate the flat wire format: {"event": type, "ts": timestamp, ...payload}.

Usage:
    python -m little_loops.generate_schemas [--output OUTPUT_DIR]

Or via CLI:
    ll-generate-schemas [--output OUTPUT_DIR]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema building helpers
# ---------------------------------------------------------------------------

_DRAFT07 = "http://json-schema.org/draft-07/schema#"

_BASE_PROPS: dict[str, Any] = {
    "event": {"type": "string", "description": "Event type identifier"},
    "ts": {"type": "string", "format": "date-time", "description": "ISO 8601 timestamp"},
}

_BASE_REQUIRED = ["event", "ts"]


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _nullable_str(description: str) -> dict[str, Any]:
    return {"type": ["string", "null"], "description": description}


def _nullable_bool(description: str) -> dict[str, Any]:
    return {"type": ["boolean", "null"], "description": description}


def _schema(
    event_type: str,
    title: str,
    description: str,
    extra_props: dict[str, Any],
    extra_required: list[str] | None = None,
) -> dict[str, Any]:
    """Build a complete JSON Schema dict for an event type."""
    return {
        "$schema": _DRAFT07,
        "$id": f"little-loops://event-{event_type}.json",
        "title": title,
        "description": description,
        "type": "object",
        "required": _BASE_REQUIRED + (extra_required or []),
        "properties": {**_BASE_PROPS, **extra_props},
        "additionalProperties": True,
    }


# ---------------------------------------------------------------------------
# Schema definitions — all 19 LLEvent types
# Source of truth: docs/reference/EVENT-SCHEMA.md
# ---------------------------------------------------------------------------

SCHEMA_DEFINITIONS: dict[str, dict[str, Any]] = {
    # FSM Executor (11 types)
    "loop_start": _schema(
        "loop_start",
        "Loop Start",
        "Emitted when an FSM loop begins execution.",
        {"loop": _str("Loop name")},
        ["loop"],
    ),
    "state_enter": _schema(
        "state_enter",
        "State Enter",
        "Emitted when the FSM enters a state.",
        {
            "state": _str("State name"),
            "iteration": _int("Iteration count (1-based)"),
        },
        ["state", "iteration"],
    ),
    "route": _schema(
        "route",
        "Route",
        "Emitted when the FSM transitions between states.",
        {
            "from": _str("Source state name"),
            "to": _str("Destination state name"),
            "reason": _str("Optional transition reason"),
        },
        ["from", "to"],
    ),
    "action_start": _schema(
        "action_start",
        "Action Start",
        "Emitted when a state action begins.",
        {
            "action": _str("Action name or command"),
            "is_prompt": _bool("True if action is a Claude prompt, false for shell command"),
        },
        ["action", "is_prompt"],
    ),
    "action_output": _schema(
        "action_output",
        "Action Output",
        "Emitted for each line of output from a running action.",
        {"line": _str("Output line text")},
        ["line"],
    ),
    "action_complete": _schema(
        "action_complete",
        "Action Complete",
        "Emitted when an action finishes.",
        {
            "exit_code": _int("Process exit code (0 = success)"),
            "duration_ms": _int("Execution duration in milliseconds"),
            "output_preview": _nullable_str("Short preview of output, null if none"),
            "is_prompt": _bool("True if action was a Claude prompt"),
            "session_jsonl": _nullable_str(
                "Path to Claude session JSONL file (prompt-only, null for shell commands)"
            ),
        },
        ["exit_code", "duration_ms", "is_prompt"],
    ),
    "evaluate": _schema(
        "evaluate",
        "Evaluate",
        "Emitted when an evaluator runs against action output.",
        {
            "type": _str("Evaluator type identifier"),
            "verdict": _str("Evaluator verdict (e.g. pass, fail, retry)"),
        },
        ["type", "verdict"],
    ),
    "retry_exhausted": _schema(
        "retry_exhausted",
        "Retry Exhausted",
        "Emitted when all retries for a state are exhausted.",
        {
            "state": _str("State name that exhausted retries"),
            "retries": _int("Number of retries attempted"),
            "next": _str("Next state the FSM transitions to"),
        },
        ["state", "retries", "next"],
    ),
    "handoff_detected": _schema(
        "handoff_detected",
        "Handoff Detected",
        "Emitted when a context-limit handoff is detected in a prompt action.",
        {
            "state": _str("State name where handoff was detected"),
            "iteration": _int("Iteration count at handoff"),
            "continuation": _str("Continuation prompt text"),
        },
        ["state", "iteration", "continuation"],
    ),
    "handoff_spawned": _schema(
        "handoff_spawned",
        "Handoff Spawned",
        "Emitted when a new process is spawned to continue after a handoff.",
        {
            "pid": _int("Process ID of the spawned continuation process"),
            "state": _str("State name the continuation will resume from"),
        },
        ["pid", "state"],
    ),
    "loop_complete": _schema(
        "loop_complete",
        "Loop Complete",
        "Emitted when an FSM loop finishes execution.",
        {
            "final_state": _str("Name of the terminal state reached"),
            "iterations": _int("Total number of iterations executed"),
            "terminated_by": _str(
                "What caused loop termination (e.g. terminal_state, max_iterations)"
            ),
        },
        ["final_state", "iterations", "terminated_by"],
    ),
    # FSM Persistence (1 type)
    "loop_resume": _schema(
        "loop_resume",
        "Loop Resume",
        "Emitted when a previously interrupted loop resumes from a persisted checkpoint.",
        {
            "loop": _str("Loop name"),
            "from_state": _str("State the loop resumes from"),
            "iteration": _int("Iteration count at resume"),
            "from_handoff": _bool("True if resuming from a context-limit handoff"),
            "continuation_prompt": _nullable_str(
                "Continuation prompt text (only present when from_handoff is true)"
            ),
        },
        ["loop", "from_state", "iteration"],
    ),
    # StateManager (2 types)
    "state.issue_completed": _schema(
        "state.issue_completed",
        "State: Issue Completed",
        "Emitted by StateManager when an issue transitions to completed status.",
        {
            "issue_id": _str("Issue identifier"),
            "status": {"type": "string", "enum": ["completed"], "description": "Completion status"},
        },
        ["issue_id", "status"],
    ),
    "state.issue_failed": _schema(
        "state.issue_failed",
        "State: Issue Failed",
        "Emitted by StateManager when an issue transitions to failed status.",
        {
            "issue_id": _str("Issue identifier"),
            "reason": _str("Failure reason description"),
            "status": {"type": "string", "enum": ["failed"], "description": "Failure status"},
        },
        ["issue_id", "reason", "status"],
    ),
    # Issue Lifecycle (4 types)
    "issue.failure_captured": _schema(
        "issue.failure_captured",
        "Issue: Failure Captured",
        "Emitted when an issue failure is captured and persisted as a bug report.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "parent_issue_id": _str("Identifier of the parent issue that failed"),
        },
        ["issue_id", "file_path", "parent_issue_id"],
    ),
    "issue.closed": _schema(
        "issue.closed",
        "Issue: Closed",
        "Emitted when an issue is closed.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the issue file"),
            "close_reason": _str("Reason the issue was closed"),
        },
        ["issue_id", "file_path", "close_reason"],
    ),
    "issue.completed": _schema(
        "issue.completed",
        "Issue: Completed",
        "Emitted when an issue is successfully completed.",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the completed issue file"),
        },
        ["issue_id", "file_path"],
    ),
    "issue.deferred": _schema(
        "issue.deferred",
        "Issue: Deferred",
        "Emitted when an issue is deferred (parked for later).",
        {
            "issue_id": _str("Issue identifier"),
            "file_path": _str("Path to the deferred issue file"),
            "reason": _str("Reason the issue was deferred"),
        },
        ["issue_id", "file_path", "reason"],
    ),
    # Parallel Orchestrator (1 type)
    "parallel.worker_completed": _schema(
        "parallel.worker_completed",
        "Parallel: Worker Completed",
        "Emitted by the parallel orchestrator when a worker finishes processing an issue.",
        {
            "issue_id": _str("Issue identifier processed by the worker"),
            "worker_name": _str("Worker name or identifier"),
            "status": _str("Completion status (e.g. completed, failed, deferred)"),
            "duration_seconds": {"type": "number", "description": "Wall-clock time in seconds"},
        },
        ["issue_id", "worker_name", "status", "duration_seconds"],
    ),
}


def event_type_to_filename(event_type: str) -> str:
    """Convert event type to safe filename (replace '.' with '_')."""
    return event_type.replace(".", "_") + ".json"


def generate_schemas(output_dir: Path) -> list[Path]:
    """Generate JSON Schema files for all 19 LLEvent types.

    Args:
        output_dir: Directory to write schema files into. Created if it doesn't exist.

    Returns:
        List of paths to generated files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for event_type, schema in SCHEMA_DEFINITIONS.items():
        filename = event_type_to_filename(event_type)
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2) + "\n")
        generated.append(path)
    return generated


if __name__ == "__main__":
    import sys

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/reference/schemas")
    paths = generate_schemas(output)
    print(f"Generated {len(paths)} schemas in {output}/")
