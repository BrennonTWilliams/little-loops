---
captured_at: '2026-05-09T19:39:32Z'
discovered_date: 2026-05-09
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1388: UnixSocketTransport skips initial state seed on client connect

## Summary

When a new client connects to the Unix socket (`events.sock`), `UnixSocketTransport` does not send current FSM state. The client only receives events from future state transitions, so any loop that is mid-execution with no imminent transition appears invisible to the new subscriber.

## Root Cause

`transport.py` — `UnixSocketTransport._accept_loop` (line ~163): after accepting a connection and appending the `_SocketClient` to `self._clients`, it starts the client drain thread and returns. No seed payload is sent. Compare to `FallbackTransport.connect()`, which reads all `.loops/.running/*.state.json` files and emits `state_change` events for each before registering the subscriber.

## Current Behavior

- `ll-loop run auto-refine-and-implement` is running (PID active, `.state.json` exists, REST API `/api/project/loop-viz/running` returns 64 entries including it)
- Opening the loop-viz dashboard while the loop is in a long-running `implement_issue` action (no imminent state transition) shows **0 FSM loops running**
- The SSE stream at `/api/project/loop-viz/events/stream` returns only `retry: 1000` — no state events — confirming the socket client received nothing on connect

## Expected Behavior

A new socket subscriber should immediately receive `state_change` events for all currently running loops, matching the behavior of `FallbackTransport`.

## Steps to Reproduce

1. Start a loop: `ll-loop run auto-refine-and-implement` (verify PID active and `.loops/.running/*.state.json` exists)
2. Wait until the loop is in a long-running action (e.g., `implement_issue`) with no imminent state transition
3. Open the loop-viz dashboard or connect a new socket subscriber (e.g., `nc -U .loops/events.sock`)
4. Observe: dashboard shows **0 FSM loops running** — the new subscriber received no state events on connect

## Proposed Solution

Add an `on_connect` callback parameter to `UnixSocketTransport.__init__`. When `_accept_loop` admits a new client (after appending to `self._clients`), call `on_connect(client)` if set. In `wire_transports`, supply a callback that reads `.loops/.running/*.state.json` and enqueues a `state_change` event to the specific new client's queue.

This keeps the transport layer generic (no filesystem knowledge baked in) and lets `wire_transports` own the seeding logic alongside the rest of the transport wiring.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — `UnixSocketTransport.__init__`, `UnixSocketTransport._accept_loop`, `wire_transports`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:348` — `wire_transports(executor.event_bus, _config.events)` (foreground loop startup)
- `scripts/little_loops/cli/loop/lifecycle.py:415` — `wire_transports(executor.event_bus, config.events)` (resume path)
- `scripts/little_loops/cli/parallel.py:230` — `wire_transports(event_bus, config.events)` (parallel orchestration)
- `scripts/little_loops/cli/sprint/run.py:405` — `wire_transports(event_bus, config.events)` (sprint per-wave)
- `scripts/little_loops/__init__.py:37,39,70,72` — re-exports `UnixSocketTransport` and `wire_transports` as public API

### Similar Patterns

**Note**: `FallbackTransport` is in the loop-viz JavaScript frontend, not this Python codebase. The Python patterns to follow are:
- `scripts/little_loops/fsm/persistence.py:615` — `list_running_loops()` reads all `.loops/.running/*.state.json` files and returns `list[LoopState]`; this is the exact state enumeration the on-connect seed callback should use
- `scripts/little_loops/transport.py:214` — `UnixSocketTransport.send()` shows the per-client enqueue pattern: `payload = (json.dumps(event) + "\n").encode("utf-8"); client.queue.put_nowait(payload)`
- `scripts/little_loops/fsm/executor.py:1259` — `_interruptible_sleep` shows canonical guarded optional-callback invocation: `if on_heartbeat is not None: on_heartbeat(...)` (use same style for `on_connect`)
- `scripts/little_loops/fsm/runners.py:36` — `ActionRunner.run` shows the `Callable[[str], None] | None = None` inline parameter style (no `Optional[...]`; use `from collections.abc import Callable`)

### Tests
- `scripts/tests/test_transport.py` — add test for on-connect seeding behavior (see Implementation Steps for pattern)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_transport.py` — `TestWireTransports.test_socket_registered_by_name`, `test_socket_uses_socket_path_from_config`, `test_socket_and_jsonl_both_registered` call the real `wire_transports` with `transports=["socket"]` and will run through `_make_seed_callback()`. They need either a mock of `list_running_loops` or a `.loops/.running/` dir in `short_tmp_path` to avoid errors when the callback reads the filesystem on connect. Patch at `"little_loops.fsm.persistence.list_running_loops"` returning `[]` is the minimal fix (matches pattern in `test_ll_loop_commands.py:239`).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5516` — `UnixSocketTransport` constructor signature is documented as `UnixSocketTransport(path: Path, max_clients: int = 8)`; update to include `on_connect: Callable[[_SocketClient], None] | None = None` with a parameter description explaining it is called after each new client is accepted (used by `wire_transports` to seed current state)

### Configuration
- N/A

## Implementation Steps

1. **Add import** to `scripts/little_loops/transport.py`: `from collections.abc import Callable` (already imported via `TYPE_CHECKING`? verify; add to runtime imports if absent)
2. **Modify `UnixSocketTransport.__init__`** (`transport.py:130`): add parameter `on_connect: Callable[[_SocketClient], None] | None = None` and store as `self._on_connect = on_connect`
3. **Modify `UnixSocketTransport._accept_loop`** (`transport.py:191`): after `self._clients.append(client)` and before `client.thread.start()` (still inside `with self._clients_lock:`), add:
   ```python
   if self._on_connect is not None:
       self._on_connect(client)
   ```
4. **Modify `wire_transports` socket branch** (`transport.py:579–586`): supply an `on_connect` callback to `UnixSocketTransport(resolved, config.socket.max_clients, on_connect=_make_seed_callback())`. The seed callback should:
   - Call `list_running_loops(Path(".loops"))` (from `little_loops.fsm.persistence`) — **note**: `list_running_loops` expects the `.loops` dir, not the `.ll` log dir stored in `base`
   - For each `LoopState`, serialize `{"event": "state_change", **state.to_dict()}` and enqueue to the new client: `client.queue.put_nowait((json.dumps(event) + "\n").encode("utf-8"))`
   - Handle `Full` via `self._record_drop(client)` — but this needs access to the transport instance; alternatively, silently skip full-queue drops for the seed (rare since the client just connected with an empty queue)
5. **Add test** in `scripts/tests/test_transport.py` (`TestUnixSocketTransport` class): follow `test_end_to_end_send_and_receive` pattern (`short_tmp_path` fixture, `time.sleep(0.2)` after connect, `_read_lines(client, expected=N)` helper at `test_transport.py:64`). Construct transport with `on_connect` callback that pre-loads a seed event dict; connect client; read lines immediately (no `send()` needed); assert seeded JSON arrives.
6. **Verify** with `ll-loop run auto-refine-and-implement` running: open loop-viz dashboard mid-execution and confirm running loops appear immediately.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/API.md:5516` — change `UnixSocketTransport(path: Path, max_clients: int = 8)` to include the new `on_connect` parameter; add it to the **Parameters** list with description: "`on_connect` — Optional callback invoked by `_accept_loop` immediately after a new client is registered. Receives the new `_SocketClient`; used internally by `wire_transports` to seed current loop state. Defaults to `None` (no-op)."
8. Update `scripts/tests/test_transport.py` — `TestWireTransports.test_socket_registered_by_name`, `test_socket_uses_socket_path_from_config`, and `test_socket_and_jsonl_both_registered` will execute `_make_seed_callback()` via real `wire_transports`. Add `patch("little_loops.fsm.persistence.list_running_loops", return_value=[])` to each of these three tests to prevent filesystem reads in the tmp context.

## Motivation

Any tool that connects to the Unix socket after a loop has started (loop-viz dashboard opened late, TUI reconnect, `nc -U` diagnostic) sees no state — appearing as if no loops are running. This is the common case, not an edge case:
- `FallbackTransport` already handles this correctly; `UnixSocketTransport` is inconsistent with the expected contract
- Long-running actions like `implement_issue` can last minutes with no state transitions, making the window of broken observability significant
- Breaks the primary use case for loop-viz: monitoring an already-running loop

## Impact

Any consumer of the Unix socket (loop-viz dashboard, TUI tools, `nc -U` one-liners) will show stale/empty state if it connects while a loop is mid-action with no transitions pending. This is the common case for long-running actions like `implement_issue`.

- **Priority**: P2 - Breaks observability for all late-connecting socket subscribers; common case during long-running actions
- **Effort**: Small - Localized change to `transport.py`; pattern already exists in `FallbackTransport.connect()`
- **Risk**: Low - Additive change (new optional callback); no breaking changes to existing behavior
- **Breaking Change**: No

## Labels

`transport`, `unix-socket`, `fsm`, `loop-viz`, `captured`

## Status

**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-05-09T20:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2a2a4de-26eb-47e2-9317-a2bfc01e3b85.jsonl`
- `/ll:wire-issue` - 2026-05-09T19:52:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2df5355d-3dd9-4237-a537-69cfafacc825.jsonl`
- `/ll:refine-issue` - 2026-05-09T19:49:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c14fd24d-a091-4319-ab55-68b4549e8413.jsonl`
- `/ll:format-issue` - 2026-05-09T19:42:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/249e3bdb-aeab-44e0-a65e-23aaef5f0a28.jsonl`
- `/ll:capture-issue` - 2026-05-09T19:39:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b297ddb7-801f-4ba1-aabc-68f533f30384.jsonl`
