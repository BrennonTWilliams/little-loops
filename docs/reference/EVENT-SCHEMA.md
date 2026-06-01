# EventBus Event Types and Payload Schemas

This document catalogs every event type emitted by little-loops subsystems. It is the primary reference for extension authors, external consumers (e.g. loop-viz), and internal development.

> **Related Documentation:**
> - [API Reference — EventBus and LLExtension](API.md#littleloopsevents) — bus registration, transports, filter patterns
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

### Hook intents — sibling type

`LLEvent` covers pub/sub bus events. **Hook intents** (PreCompact, SessionStart, PreToolUse, …) are *request/response* and use a sibling dataclass [`LLHookEvent`](../../scripts/little_loops/hooks/types.py), with handler responses modeled as [`LLHookResult`](../../scripts/little_loops/hooks/types.py). Adapters under `hooks/adapters/<host>/` translate between each host's native hook protocol and these host-agnostic types; the dispatcher lives in [`little_loops.hooks.main_hooks`](../../scripts/little_loops/hooks/__init__.py) and is invoked as `python -m little_loops.hooks <intent>`.

#### `LLHookEvent` fields

Source of truth: `scripts/little_loops/hooks/types.py`.

| Key | Type | Description |
|-----|------|-------------|
| `host` | `str` | Host agent identifier (e.g. `"claude-code"`, `"opencode"`, `"codex"`). Adapters set this; the CLI reads `LL_HOOK_HOST` (default `"claude-code"`). |
| `intent` | `str` | Hook intent name matching the handler module (e.g. `pre_compact`, `session_start`). |
| `ts` | `str` | ISO 8601 UTC timestamp. **Field name differs from wire key**: stored as `timestamp` on the dataclass, serialized as `ts` by `to_dict()`. `from_dict()` accepts either `ts` or `timestamp`. |
| `payload` | `object` | Host-supplied event data. Schema is intent-specific (see per-intent notes below). |
| `session_id` | `str` *(optional)* | Host session identifier. Omitted from the wire dict when `None`. |
| `cwd` | `str` *(optional)* | Working directory the host was operating in. Omitted from the wire dict when `None`. |

#### `LLHookResult` fields

| Key | Type | Description |
|-----|------|-------------|
| `exit_code` | `int` | Always emitted. `0` = pass; `2` = block and surface `feedback` to the model. Non-Claude hosts map this to their own permit/deny semantics. |
| `feedback` | `str` *(optional)* | Human-readable message. Claude Code writes this to stderr when `exit_code == 2`. Omitted from the wire dict when `None`. |
| `decision` | `str` *(optional)* | Permission decision for permission-checking intents (`allow` / `deny` / `ask`). Omitted from the wire dict when `None`. |
| `data` | `object` | Additional structured data returned to the host. Omitted from the wire dict when empty. |
| `stdout` | `str` *(optional)* | Raw payload written to the host's stdout (e.g. `SessionStart`'s merged config JSON). Omitted from the wire dict when `None`. |

#### Wire-format example

```json
{
  "host": "claude-code",
  "intent": "pre_compact",
  "ts": "2026-05-12T14:00:00Z",
  "payload": {"transcript_path": "/tmp/session.jsonl"},
  "cwd": "/Users/me/project"
}
```

Round-trip note: `to_dict()` emits the timestamp under the key `ts`; `from_dict()` accepts both `ts` and `timestamp`. A dict produced by `to_dict()` round-trips cleanly through `from_dict()`.

#### Per-intent payload notes

- **`pre_compact`** — reads exactly one payload key, `transcript_path` (falls back to `""`). Writes `.ll/ll-precompact-state.json`. Returns `LLHookResult(exit_code=2, feedback=<line-budget-message>)` to surface a context-budget warning to the model.
- **`session_start`** — reads no payload keys; operates via `Path.cwd()`. Returns `LLHookResult(exit_code=0, feedback=<stderr-lines>, stdout=<merged-config-json-or-None>)`.
- **`session_end`** — reads no payload keys; operates via `Path.cwd()`. Handler reads done issue IDs via `find_issues(status_filter={"done"})` and the `hooks.stale_ref_fix` key from the raw config; outputs sweep findings in `result.feedback`. Always exits `0`.

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

### `action_error`

Emitted when an action raises an unhandled exception that is routed to the state's `on_error` target. Only emitted when `on_error` is defined; if absent, the exception propagates to the top-level loop handler and terminates execution instead.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `state` | `str` | always | Name of the state whose action raised |
| `error` | `str` | always | String representation of the raised exception |
| `route` | `str` | always | Route taken in response (always `"on_error"`) |

**Example:**
```json
{
  "event": "action_error",
  "ts": "...",
  "state": "fetch_data",
  "error": "ConnectionError: timed out after 30s",
  "route": "on_error"
}
```

---

### `evaluate`

Emitted after the evaluator runs to determine the next routing decision.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Evaluation type: `"default"` (exit-code based) or the custom type declared in the state's `evaluate` config (e.g. `"llm"`) |
| `verdict` | `str` | Evaluator verdict (e.g. `"pass"`, `"fail"`, `"yes"`, `"no"`, `"retry"`, `"error"`) |
| *(detail fields)* | varies | Additional evaluator-specific fields (e.g. `score`, `reason` for LLM evaluators) |

**`action_stall` evaluator detail fields:**

| Field | Type | Description |
|-------|------|-------------|
| `stall_count` | `int` | Number of consecutive identical-hash iterations so far |
| `max_repeat` | `int` | Configured threshold before stall verdict |
| `hash_changed` | `bool` | Whether the hash of tracked context values changed this iteration |
| `tracked_keys` | `list[str]` | Context keys that were hashed (default `["action"]`) |
| `repeated_hash` | `str` | *(only on `verdict="no"`)* The MD5 hex digest that repeated |

**Example (default exit-code evaluation):**
```json
{"event": "evaluate", "ts": "...", "type": "default", "verdict": "pass"}
```

**Example (`action_stall` stall detected):**
```json
{"event": "evaluate", "ts": "...", "type": "action_stall", "verdict": "no",
 "stall_count": 2, "max_repeat": 2, "hash_changed": false,
 "tracked_keys": ["action"], "repeated_hash": "a1b2c3d4e5f6"}
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

### `stall_detected`

Emitted when the FSM stall detector (FEAT-1637) observes `window` consecutive iterations producing an identical `(state, exit_code, verdict)` triple. Configured via the top-level `circuit.repeated_failure` block. On firing, the executor either terminates the run with `terminated_by="stall_detected"` (when `on_repeated_failure: "abort"`) or routes to the configured recovery state.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state whose repeated entry triggered the stall |
| `exit_code` | `int` | The repeating action exit code (timeouts surface as `124`) |
| `verdict` | `str` | The repeating evaluator verdict (e.g. `"no"`, `"error"`) |
| `consecutive` | `int` | Number of consecutive identical triples observed (equals configured `window`) |
| `action` | `str` | Resolved action: literal `"abort"` or `"route:<state>"` |

**Example:**
```json
{"event": "stall_detected", "ts": "...", "state": "check_semantic_vision", "exit_code": 124, "verdict": "error", "consecutive": 3, "action": "abort"}
```

---

### `cycle_detected`

Emitted when the same edge (`from_state->to_state`) is traversed more than `max_edge_revisits` times, indicating a tight cycle. The executor terminates the run with `terminated_by="cycle_detected"`.

| Field | Type | Description |
|-------|------|-------------|
| `edge` | `str` | Edge key (`from_state->to_state`) that triggered detection |
| `from` | `str` | Source state of the cyclic edge |
| `to` | `str` | Target state of the cyclic edge |
| `count` | `int` | Number of times this edge was traversed |
| `max` | `int` | Configured `max_edge_revisits` limit |

**Example:**
```json
{"event": "cycle_detected", "ts": "...", "edge": "build->test", "from": "build", "to": "test", "count": 6, "max": 5}
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

### `throttle_warn`

Emitted when a state's tool-call count reaches `warn_max` within a single state visit.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name where throttle warning was triggered |
| `count` | `int` | Current tool-call count at time of emission |
| `normal_max` | `int` | Configured `normal_max` threshold for this state |
| `warn_max` | `int` | Configured `warn_max` threshold for this state |
| `hard_max` | `int` | Configured `hard_max` threshold for this state |

**Example:**
```json
{"event": "throttle_warn", "ts": "...", "state": "implement", "count": 8, "normal_max": 3, "warn_max": 8, "hard_max": 12}
```

---

### `throttle_hard`

Emitted when a state's tool-call count reaches `hard_max`, triggering transition to `on_throttle_hard`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name where hard throttle was triggered |
| `count` | `int` | Current tool-call count at time of emission |
| `hard_max` | `int` | Configured `hard_max` threshold for this state |
| `next` | `str` | Target state (`on_throttle_hard` or `on_error`, or null) |

**Example:**
```json
{"event": "throttle_hard", "ts": "...", "state": "implement", "count": 12, "hard_max": 12, "next": "throttle_recovery"}
```

---

### `throttle_stop`

Emitted when a state's tool-call count exceeds `hard_max` with no `on_throttle_hard` target, causing a hard stop.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name where stop throttle was triggered |
| `count` | `int` | Current tool-call count at time of emission |
| `hard_max` | `int` | Configured `hard_max` threshold for this state |

**Example:**
```json
{"event": "throttle_stop", "ts": "...", "state": "implement", "count": 13, "hard_max": 12}
```

---

### `learning_target_proven`

Emitted when a target's learning-tests registry record is found with `status='proven'`. The state continues to the next target (or to `on_yes` when all targets are proven).

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `target` | `str` | Target identifier (e.g. "Anthropic SDK streaming") |

---

### `learning_target_stale`

Emitted when a target's registry record is missing or has `status='stale'`, immediately before `/ll:explore-api` fires.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `target` | `str` | Target identifier |
| `cause` | `str` | `"missing"` or `"stale"` |

---

### `learning_explore_invoked`

Emitted just before the learning state invokes `/ll:explore-api <target>`. Pairs with `action_start`/`action_complete` from the underlying skill invocation.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `target` | `str` | Target identifier being explored |
| `attempt` | `int` | Attempt number (1-based), capped by `learning.max_retries` |

---

### `learning_target_refuted`

Emitted when a target's record has `status='refuted'`. Routes to `on_blocked` / `on_no`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `target` | `str` | Target identifier |

---

### `learning_complete`

Emitted when every target in a learning state has been proven. The state transitions via `on_yes`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `targets` | `list[str]` | Targets that were all proven |

---

### `learning_blocked`

Emitted when a learning state cannot advance: a target is refuted, or `/ll:explore-api` retries are exhausted without proving the target.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | State name executing the learning dispatch |
| `target` | `str` | Target that blocked progress |
| `reason` | `str` | `"refuted"` or `"retries_exhausted"` |

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
| `final_state` | `str` | Name of the state at termination. Usually the last state entered; when `terminated_by="timeout"` this may be a state that was routed to but never entered. **Exception (BUG-1226):** when that pending state is a shell action, the executor flushes it — emitting `state_enter` with `flushed: true` and running its action — before honoring the timeout, so `state_enter` for `final_state` is always emitted before `loop_complete`. Slash commands and sub-loops are not flushed. |
| `iterations` | `int` | Total number of iterations completed |
| `terminated_by` | `str` | Reason for termination: `"signal"` (OS signal), `"error"` (no valid transition or unhandled error), `"stall_detected"` (FEAT-1637 circuit fired with `on_repeated_failure: "abort"`), `"cycle_detected"` (same edge traversed more than `max_edge_revisits` times), `"max_iterations"` (iteration cap reached), or the terminal state name |

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

### `max_iterations_summary`

Emitted when the iteration cap fires and `on_max_iterations` is set on the loop. Signals that the executor is about to run the summary state before terminating. Always immediately precedes the `state_enter` for the summary state. `loop_complete` fires after the summary state completes with `terminated_by="max_iterations"`.

| Field | Type | Description |
|-------|------|-------------|
| `summary_state` | `str` | Name of the state the executor will transition to |
| `iterations` | `int` | Iteration count at which the cap fired |

**Example:**
```json
{
  "event": "max_iterations_summary",
  "ts": "...",
  "summary_state": "summarize_partial",
  "iterations": 100
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

#### Transport behavior

`loop_resume` is emitted via `EventBus.emit()` and therefore fans out to every registered observer **and** every registered transport (FEAT-1322 / FEAT-1323). In `ll-loop resume` (`cli/loop/lifecycle.py:cmd_resume`), `wire_transports()` is called immediately after `wire_extensions()`, so transports configured under `events.transports` in `ll-config.json` see `loop_resume` for resumed runs the same way `ll-loop run` sees `loop_start` for fresh runs. Earlier builds wired transports only on `cmd_run`, which meant resumed loops bypassed the transport layer; that gap is closed by FEAT-1323. Teardown happens in a `try/finally` around the resume call: `executor.close_transports()` runs even on `KeyboardInterrupt` so any buffered `loop_resume` (and downstream) events are flushed before the process exits.

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
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

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
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

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
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

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
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

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

### `issue.skipped`

Emitted when an issue is skipped during automated processing (e.g., by `ll-auto` when the issue does not meet filter criteria or is explicitly excluded).

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `file_path` | `str` | Absolute path to the issue file |
| `reason` | `str` | Human-readable reason for skipping |
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

**Example:**
```json
{
  "event": "issue.skipped",
  "ts": "...",
  "issue_id": "BUG-042",
  "file_path": "/path/to/.issues/bugs/P2-BUG-042-....md",
  "reason": "Issue type excluded by --type filter"
}
```

---

### `issue.started`

Emitted when a deferred issue is undeferred and returned to active status (via `undefer_issue()`).

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | `str` | Issue identifier |
| `file_path` | `str` | Absolute path to the issue file |
| `reason` | `str` | Human-readable reason for restarting |
| `captured_at` | `string \| null` | ISO 8601 timestamp from the issue's frontmatter; `null` for issues created before ENH-1839. |

**Example:**
```json
{
  "event": "issue.started",
  "ts": "...",
  "issue_id": "FEAT-099",
  "file_path": "/path/to/.issues/features/P2-FEAT-099-....md",
  "reason": "Unblocked after dependency resolved"
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
├── action_error.json
├── action_output.json
├── action_start.json
├── cycle_detected.json
├── evaluate.json
├── handoff_detected.json
├── handoff_spawned.json
├── issue_closed.json
├── issue_completed.json
├── issue_deferred.json
├── issue_failure_captured.json
├── issue_skipped.json
├── issue_started.json
├── learning_blocked.json
├── learning_complete.json
├── learning_explore_invoked.json
├── learning_target_proven.json
├── learning_target_refuted.json
├── learning_target_stale.json
├── loop_complete.json
├── loop_resume.json
├── loop_start.json
├── max_iterations_summary.json
├── parallel_worker_completed.json
├── rate_limit_exhausted.json
├── rate_limit_storm.json
├── rate_limit_waiting.json
├── retry_exhausted.json
├── route.json
├── stall_detected.json
├── state_enter.json
├── state_issue_completed.json
├── state_issue_failed.json
├── throttle_hard.json
├── throttle_stop.json
└── throttle_warn.json
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
| `action_error` | FSM | `fsm/executor.py` |
| `evaluate` | FSM | `fsm/executor.py` |
| `retry_exhausted` | FSM | `fsm/executor.py` |
| `stall_detected` | FSM | `fsm/executor.py` |
| `rate_limit_exhausted` | FSM | `fsm/executor.py` |
| `rate_limit_storm` | FSM | `fsm/executor.py` |
| `rate_limit_waiting` | FSM | `fsm/executor.py` |
| `handoff_detected` | FSM | `fsm/executor.py` |
| `handoff_spawned` | FSM | `fsm/executor.py` |
| `loop_complete` | FSM | `fsm/executor.py` |
| `max_iterations_summary` | FSM | `fsm/executor.py` |
| `throttle_warn` | FSM | `fsm/executor.py` |
| `throttle_hard` | FSM | `fsm/executor.py` |
| `throttle_stop` | FSM | `fsm/executor.py` |
| `learning_target_proven` | FSM | `fsm/executor.py` |
| `learning_target_stale` | FSM | `fsm/executor.py` |
| `learning_explore_invoked` | FSM | `fsm/executor.py` |
| `learning_target_refuted` | FSM | `fsm/executor.py` |
| `learning_complete` | FSM | `fsm/executor.py` |
| `learning_blocked` | FSM | `fsm/executor.py` |
| `loop_resume` | FSM Persistence | `fsm/persistence.py` |
| `state.issue_completed` | StateManager | `state.py` |
| `state.issue_failed` | StateManager | `state.py` |
| `issue.failure_captured` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.closed` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.completed` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.deferred` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.skipped` | Issue Lifecycle | `issue_lifecycle.py` |
| `issue.started` | Issue Lifecycle | `issue_lifecycle.py` |
| `parallel.worker_completed` | Parallel | `parallel/orchestrator.py` |

---

## OTel Transport Field Mapping

When `OTelTransport` is active (`events.transports: ["otel"]`), the following event fields are used to construct OpenTelemetry spans and span events. All other fields are serialized as span event attributes (`str(value)`).

### Span-opening events

| Event | OTel action | Field used |
|-------|-------------|------------|
| `loop_start` | Opens root span (trace) | `loop` → span name |
| `loop_resume` | Closes all open spans; opens new root span | `loop` → span name |
| `state_enter` | Opens child span of loop span | `state` → span name |
| `action_start` | Opens grandchild span of state span | `action` → span name |

### Span-closing events

| Event | OTel action | Field used |
|-------|-------------|------------|
| `action_complete` | Closes action span | — |
| `loop_complete` | Closes state + action spans; sets loop span status; closes loop span | `outcome` → status code (`"error"` / `"failed"` / `"exhausted"` → `ERROR`, all others → `OK`) |

### Span event records

These events are added as OTel span events on the innermost open span (action > state > loop):

`evaluate`, `route`, `retry_exhausted`, `handoff_detected`, `handoff_spawned`, `action_output`

All fields except `"event"` are included as span event attributes (string-coerced).

### Sub-loop events

Events with `depth > 0` are no-ops. A single `WARNING` is logged per `OTelTransport` session. Full nested-trace support is out of scope.
