# EventBus Event Types and Payload Schemas

This document catalogs every event type emitted by little-loops subsystems. It is the primary reference for extension authors, external consumers (e.g. loop-viz), and internal development.

> **Related Documentation:**
> - [API Reference — EventBus and LLExtension](API.md#littleloopsevents) — bus registration, file sinks, filter patterns
> - [Architecture Overview](../ARCHITECTURE.md) — Event persistence patterns and FSM executor design

---

## Wire Format

All events are emitted as flat Python dicts and serialized to JSON:

```json
{
  "event": "<event-type>",
  "ts": "2026-04-02T12:00:00.123456",
  "<field>": "<value>"
}
```

| Key | Type | Description |
|-----|------|-------------|
| `event` | `str` | Event type identifier (see tables below) |
| `ts` | `str` | ISO 8601 timestamp, UTC |
| *(payload fields)* | varies | Type-specific fields documented per event |

When received by an `LLExtension`, the raw dict is wrapped into an `LLEvent` dataclass:

```python
event.type      # the "event" key
event.timestamp # the "ts" key
event.payload   # all remaining keys as a dict
```

---

## Naming Conventions

| Namespace | Pattern | Source |
|-----------|---------|--------|
| FSM executor | bare names (`loop_start`, `state_enter`, …) | `fsm/executor.py` |
| FSM persistence | bare names (`loop_resume`) | `fsm/persistence.py` |
| StateManager | `state.*` | `state.py` |
| Issue lifecycle | `issue.*` | `issue_lifecycle.py` |
| Parallel orchestrator | `parallel.*` | `parallel/orchestrator.py` |

Use these namespaces in `event_filter` patterns when registering observers:

```python
# Subscribe only to FSM events
bus.register(callback, filter="state_*")

# Subscribe only to issue lifecycle events
bus.register(callback, filter="issue.*")

# Subscribe to multiple namespaces
bus.register(callback, filter=["issue.*", "parallel.*"])
```

---

## Subsystem: FSM Executor

**Source:** `little_loops.fsm.executor.FSMExecutor`  
**Path:** `scripts/little_loops/fsm/executor.py`  
**Flow:** `FSMExecutor._emit()` → `event_callback` → `EventBus.emit()`

These events use bare names (no dot namespace) for historical compatibility.

### `loop_start`

Emitted once at the very beginning of loop execution, before any state is entered.

| Field | Type | Description |
|-------|------|-------------|
| `loop` | `str` | Name of the FSM loop (from the loop YAML `name` field) |

**Example:**
```json
{"event": "loop_start", "ts": "2026-04-02T12:00:00Z", "loop": "my-loop"}
```

---

### `state_enter`

Emitted when the executor enters a state, before the state's action is executed.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state being entered |
| `iteration` | `int` | Current iteration count (1-based) |

**Example:**
```json
{"event": "state_enter", "ts": "...", "state": "build", "iteration": 1}
```

---

### `route`

Emitted when the executor selects the next state after an evaluation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | `str` | always | Source state name |
| `to` | `str` | always | Destination state name |
| `reason` | `str` | optional | `"maintain"` when the loop is in maintain mode; absent otherwise |

**Example:**
```json
{"event": "route", "ts": "...", "from": "build", "to": "test"}
```

---

### `action_start`

Emitted immediately before executing the current state's action.

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | The resolved action string (interpolated prompt text or shell command) |
| `is_prompt` | `bool` | `true` if the action is a Claude prompt; `false` if a shell command |

**Example:**
```json
{"event": "action_start", "ts": "...", "action": "Run tests", "is_prompt": true}
```

---

### `action_output`

Emitted for each line of streaming output produced by the action. High-frequency event — may fire hundreds of times per state.

| Field | Type | Description |
|-------|------|-------------|
| `line` | `str` | A single line of output from the running action |

**Example:**
```json
{"event": "action_output", "ts": "...", "line": "✓ 42 tests passed"}
```

---

### `action_complete`

Emitted after the action finishes, regardless of success or failure.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `exit_code` | `int` | always | Exit code of the action (0 = success) |
| `duration_ms` | `int` | always | Wall-clock execution time in milliseconds |
| `output_preview` | `str \| null` | always | Last 2 000 characters of the action's output; `null` if no output was produced |
| `is_prompt` | `bool` | always | `true` for Claude prompt actions, `false` for shell commands |
| `session_jsonl` | `str \| null` | prompt only | Absolute path to the Claude session JSONL file for this prompt run; `null` if path cannot be determined |

**Example (shell command):**
```json
{
  "event": "action_complete",
  "ts": "...",
  "exit_code": 0,
  "duration_ms": 1234,
  "output_preview": "Build succeeded",
  "is_prompt": false
}
```

**Example (Claude prompt):**
```json
{
  "event": "action_complete",
  "ts": "...",
  "exit_code": 0,
  "duration_ms": 45000,
  "output_preview": "I have completed the task...",
  "is_prompt": true,
  "session_jsonl": "/Users/user/.claude/projects/.../abc123.jsonl"
}
```

---

### `evaluate`

Emitted after the evaluator runs to determine the next routing decision.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Evaluation type: `"default"` (exit-code based) or the custom type declared in the state's `evaluate` config (e.g. `"llm"`) |
| `verdict` | `str` | `"pass"` or `"fail"` |
| *(detail fields)* | varies | Additional evaluator-specific fields (e.g. `score`, `reason` for LLM evaluators) |

**Example (default exit-code evaluation):**
```json
{"event": "evaluate", "ts": "...", "type": "default", "verdict": "pass"}
```

---

### `retry_exhausted`

Emitted when a state exceeds its `max_retries` limit and the executor transitions to `on_retry_exhausted`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state that exhausted its retry budget |
| `retries` | `int` | Number of retries that were attempted |
| `next` | `str` | Name of the `on_retry_exhausted` target state |

**Example:**
```json
{"event": "retry_exhausted", "ts": "...", "state": "test", "retries": 3, "next": "fail"}
```

---

### `rate_limit_exhausted`

Emitted when the wall-clock rate-limit budget is spent across the short-burst and long-wait retry tiers and the executor transitions to `on_rate_limit_exhausted` (or `on_error`). See `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` on `StateConfig` for budget configuration.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state that exhausted rate-limit retries |
| `retries` | `int` | Total rate-limit retries attempted across both tiers (`short_retries + long_retries`) |
| `short_retries` | `int` | Retries attempted in the short-burst tier (before entering long-wait) |
| `long_retries` | `int` | Retries attempted in the long-wait tier (ladder-based) |
| `total_wait_seconds` | `number` | Accumulated wall-clock seconds spent sleeping in rate-limit waits |
| `next` | `str \| null` | Name of the `on_rate_limit_exhausted` target state, or null |

**Example:**
```json
{"event": "rate_limit_exhausted", "ts": "...", "state": "implement", "retries": 7, "short_retries": 3, "long_retries": 4, "total_wait_seconds": 21600.0, "next": "halt"}
```

---

### `rate_limit_storm`

Emitted when consecutive `rate_limit_exhausted` events across any states reach the storm threshold (3). The counter resets on any successful non-rate-limited state transition.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state that triggered the storm threshold |
| `count` | `int` | Consecutive `rate_limit_exhausted` count at emission time |

**Example:**
```json
{"event": "rate_limit_storm", "ts": "...", "state": "implement", "count": 3}
```

---

### `rate_limit_waiting`

Emitted periodically by the FSM executor while sleeping between 429 retry attempts (both short-burst and long-wait tiers). Provides heartbeat visibility into in-progress waits so dashboards and analysis tooling can surface progress toward the wall-clock budget defined by `rate_limit_max_wait_seconds`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state currently retrying |
| `elapsed_seconds` | `number` | Wall-clock seconds elapsed in the current sleep window |
| `next_attempt_at` | `str` | ISO-8601 timestamp at which the next retry will fire |
| `total_waited_seconds` | `number` | Accumulated wall-clock seconds across all 429 waits for this state |
| `budget_seconds` | `number` | Configured `rate_limit_max_wait_seconds` budget |
| `tier` | `str` | Current retry tier: `"short"` or `"long"` |

**Example:**
```json
{"event": "rate_limit_waiting", "ts": "...", "state": "implement", "elapsed_seconds": 60.0, "next_attempt_at": "2026-04-17T12:34:56Z", "total_waited_seconds": 180.0, "budget_seconds": 21600, "tier": "short"}
```

---

### `handoff_detected`

Emitted when the executor detects a handoff signal in the action output, indicating the loop needs to be paused and resumed in a fresh session.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Current state name when the handoff was detected |
| `iteration` | `int` | Current iteration count |
| `continuation` | `str` | The continuation prompt payload extracted from the handoff signal |

**Example:**
```json
{
  "event": "handoff_detected",
  "ts": "...",
  "state": "implement",
  "iteration": 3,
  "continuation": "Continue from: implement auth middleware..."
}
```

---

### `handoff_spawned`

Emitted when the handoff handler spawns a new child process to continue the loop.

| Field | Type | Description |
|-------|------|-------------|
| `pid` | `int` | PID of the spawned child process |
| `state` | `str` | Current state name at the time of spawning |

**Example:**
```json
{"event": "handoff_spawned", "ts": "...", "pid": 98765, "state": "implement"}
```

---

### `loop_complete`

Emitted once when the executor finishes, regardless of how it terminated.

| Field | Type | Description |
|-------|------|-------------|
| `final_state` | `str` | Name of the state where execution ended |
| `iterations` | `int` | Total number of iterations completed |
| `terminated_by` | `str` | Reason for termination: `"signal"` (OS signal), `"error"` (no valid transition or unhandled error), or the terminal state name |

**Example:**
```json
{
  "event": "loop_complete",
  "ts": "...",
  "final_state": "done",
  "iterations": 5,
  "terminated_by": "done"
}
```

---

## Subsystem: FSM Persistence

**Source:** `little_loops.fsm.persistence.PersistentExecutor`  
**Path:** `scripts/little_loops/fsm/persistence.py`

### `loop_resume`

Emitted when a paused or interrupted loop is resumed. Occurs after the executor state is restored from disk, before execution continues.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `loop` | `str` | always | Name of the loop being resumed |
| `from_state` | `str` | always | State to resume from (as saved in the state file) |
| `iteration` | `int` | always | Iteration count at the time of resume |
| `from_handoff` | `bool` | optional | `true` when resuming from a `handoff_detected` pause; absent otherwise |
| `continuation_prompt` | `str` | optional | The continuation prompt (only present when `from_handoff` is `true`) |

**Example (normal resume):**
```json
{"event": "loop_resume", "ts": "...", "loop": "my-loop", "from_state": "test", "iteration": 2}
```

**Example (handoff resume):**
```json
{
  "event": "loop_resume",
  "ts": "...",
  "loop": "my-loop",
  "from_state": "implement",
  "iteration": 3,
  "from_handoff": true,
  "continuation_prompt": "Continue from: implement auth middleware..."
}
```

---

## Subsystem: StateManager

**Source:** `little_loops.state.StateManager`  
**Path:** `scripts/little_loops/state.py`  
**Flow:** `StateManager._emit()` → `EventBus.emit()`  
**Filter pattern:** `"state.*"`

These events track per-run issue processing state for `ll-auto` and `ll-sprint`.

### `state.issue_completed`

Emitted when an issue is marked as completed in the sequential run state.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier (e.g. `"BUG-001"`) |
| `status` | `str` | Always `"completed"` |

**Example:**
```json
{"event": "state.issue_completed", "ts": "...", "issue_id": "BUG-001", "status": "completed"}
```

---

### `state.issue_failed`

Emitted when an issue is marked as failed in the sequential run state.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `reason` | `str` | Human-readable failure reason |
| `status` | `str` | Always `"failed"` |

**Example:**
```json
{
  "event": "state.issue_failed",
  "ts": "...",
  "issue_id": "BUG-002",
  "reason": "Command exited with code 1",
  "status": "failed"
}
```

---

## Subsystem: Issue Lifecycle

**Source:** `little_loops.issue_lifecycle`  
**Path:** `scripts/little_loops/issue_lifecycle.py`  
**Filter pattern:** `"issue.*"`

These events are emitted by the standalone lifecycle functions used by `ll-auto`, `ll-sprint`, and `ll-parallel`.

### `issue.failure_captured`

Emitted when a new bug issue is automatically created from a failed parent issue.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | ID of the newly created bug issue |
| `file_path` | `str` | Absolute path to the new bug issue file |
| `parent_issue_id` | `str` | ID of the parent issue that triggered this capture |

**Example:**
```json
{
  "event": "issue.failure_captured",
  "ts": "...",
  "issue_id": "BUG-042",
  "file_path": "/path/to/.issues/bugs/P1-BUG-042-....md",
  "parent_issue_id": "ENH-025"
}
```

---

### `issue.closed`

Emitted when an issue is closed without being implemented (e.g. invalid, duplicate, or already fixed).

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `file_path` | `str` | Absolute path to the issue file in `completed/` |
| `close_reason` | `str` | Reason code, e.g. `"already_fixed"`, `"invalid_ref"`, `"duplicate"`, `"unknown"` |

**Example:**
```json
{
  "event": "issue.closed",
  "ts": "...",
  "issue_id": "BUG-015",
  "file_path": "/path/to/.issues/completed/P2-BUG-015-....md",
  "close_reason": "already_fixed"
}
```

---

### `issue.completed`

Emitted when an issue successfully completes its full lifecycle and is moved to `completed/`.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `file_path` | `str` | Absolute path to the issue file in `completed/` |

**Example:**
```json
{
  "event": "issue.completed",
  "ts": "...",
  "issue_id": "ENH-025",
  "file_path": "/path/to/.issues/completed/P3-ENH-025-....md"
}
```

---

### `issue.deferred`

Emitted when an issue is moved to the deferred pool.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `file_path` | `str` | Absolute path to the issue file in `deferred/` |
| `reason` | `str` | Human-readable reason for deferral |

**Example:**
```json
{
  "event": "issue.deferred",
  "ts": "...",
  "issue_id": "FEAT-099",
  "file_path": "/path/to/.issues/deferred/P2-FEAT-099-....md",
  "reason": "Blocked on external dependency"
}
```

---

## Subsystem: Parallel Orchestrator

**Source:** `little_loops.parallel.orchestrator.Orchestrator`  
**Path:** `scripts/little_loops/parallel/orchestrator.py`  
**Filter pattern:** `"parallel.*"`

### `parallel.worker_completed`

Emitted when a parallel worker finishes processing an issue in its isolated git worktree.

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier processed by this worker |
| `worker_name` | `str` | Name of the git worktree directory used by this worker |
| `status` | `str` | `"success"` if the worker succeeded, `"failure"` otherwise |
| `duration_seconds` | `float` | Wall-clock time in seconds for the entire worker run |

**Example:**
```json
{
  "event": "parallel.worker_completed",
  "ts": "...",
  "issue_id": "BUG-007",
  "worker_name": "ll-worker-BUG-007-abc123",
  "status": "success",
  "duration_seconds": 142.7
}
```

---

## Machine-Readable Schemas

Every event type listed in this document has a corresponding JSON Schema (draft-07) file committed to `docs/reference/schemas/`. These files can be used for programmatic validation, IDE autocomplete, and external tooling.

```
docs/reference/schemas/
├── action_complete.json
├── action_output.json
├── action_start.json
├── evaluate.json
├── handoff_detected.json
├── handoff_spawned.json
├── issue_closed.json
├── issue_completed.json
├── issue_deferred.json
├── issue_failure_captured.json
├── loop_complete.json
├── loop_resume.json
├── loop_start.json
├── parallel_worker_completed.json
├── rate_limit_exhausted.json
├── rate_limit_storm.json
├── rate_limit_waiting.json
├── retry_exhausted.json
├── route.json
├── state_enter.json
├── state_issue_completed.json
└── state_issue_failed.json
```

### Naming Convention

Event type identifiers map to filenames by replacing dots with underscores:

| Event type | Schema file |
|------------|-------------|
| `loop_start` | `loop_start.json` |
| `issue.completed` | `issue_completed.json` |
| `state.issue_completed` | `state_issue_completed.json` |
| `parallel.worker_completed` | `parallel_worker_completed.json` |

### Schema Format

Each file is a self-contained JSON Schema (draft-07) object. All schemas set `"additionalProperties": true` so forward-compatible extensions to event payloads do not break validation. Example (`loop_start.json`):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "little-loops://event-loop_start.json",
  "title": "Loop Start",
  "description": "Emitted when an FSM loop begins execution.",
  "type": "object",
  "required": ["event", "ts", "loop"],
  "properties": {
    "event": { "type": "string", "description": "Event type identifier" },
    "ts":    { "type": "string", "format": "date-time", "description": "ISO 8601 timestamp" },
    "loop":  { "type": "string", "description": "Loop name" }
  },
  "additionalProperties": true
}
```

### Programmatic Validation

Use the `jsonschema` library to validate event dicts against the generated files:

```python
import json
import jsonschema
from pathlib import Path

schema = json.loads(Path("docs/reference/schemas/loop_start.json").read_text())
event = {"event": "loop_start", "ts": "2026-04-04T12:00:00Z", "loop": "my-loop"}
jsonschema.validate(event, schema)  # raises jsonschema.ValidationError on failure
```

To resolve a schema path from an event type at runtime:

```python
def schema_path(event_type: str, base: Path) -> Path:
    return base / f"{event_type.replace('.', '_')}.json"
```

### Regenerating

To regenerate all schema files after adding or modifying an event type, run:

```bash
ll-generate-schemas
```

See [`ll-generate-schemas`](CLI.md#ll-generate-schemas) in the CLI reference and the [schema maintenance workflow](../../CONTRIBUTING.md#event-schema-maintenance) in CONTRIBUTING.md.

---

## Quick Reference

| Event | Namespace | Source |
|-------|-----------|--------|
| `loop_start` | FSM | `fsm/executor.py` |
| `state_enter` | FSM | `fsm/executor.py` |
| `route` | FSM | `fsm/executor.py` |
| `action_start` | FSM | `fsm/executor.py` |
| `action_output` | FSM | `fsm/executor.py` |
| `action_complete` | FSM | `fsm/executor.py` |
| `evaluate` | FSM | `fsm/executor.py` |
| `retry_exhausted` | FSM | `fsm/executor.py` |
| `rate_limit_exhausted` | FSM | `fsm/executor.py` |
| `rate_limit_storm` | FSM | `fsm/executor.py` |
| `rate_limit_waiting` | FSM | `fsm/executor.py` |
| `handoff_detected` | FSM | `fsm/executor.py` |
| `handoff_spawned` | FSM | `fsm/executor.py` |
| `loop_complete` | FSM | `fsm/executor.py` |
| `loop_resume` | FSM Persistence | `fsm/persistence.py` |
| `state.issue_completed` | StateManager | `state.py` |
| `state.issue_failed` | StateManager | `state.py` |
| `issue.failure_captured` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.closed` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.completed` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.deferred` | Issue Lifecycle | `issue_lifecycle.py` |
| `parallel.worker_completed` | Parallel | `parallel/orchestrator.py` |
