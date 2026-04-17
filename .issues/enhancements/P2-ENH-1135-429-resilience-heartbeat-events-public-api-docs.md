---
id: ENH-1135
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1133, ENH-1134, BUG-1107, BUG-1108, BUG-1109]
---

# ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs

## Summary

Add the `rate_limit_waiting` event (schema, emit, UI rendering), complete the FSM public API exports, fix hard-coded event counts in `generate_schemas.py` and tests, and write all documentation updates. This is the final integration layer for the ENH-1131 family. Depends on ENH-1132 (schema/config), ENH-1133 (executor retry logic), and ENH-1134 (circuit breaker).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Without heartbeat events, long rate-limit waits (up to 6h) look like a hung process to users watching `ll-loop` UI or tail logs. `rate_limit_waiting` events emitted every 60s provide live progress. The public API, test count assertions, and docs all need updates to close out the ENH-1131 feature set.

## Expected Behavior

### 1. Heartbeat emit loop (`executor.py:527-534`)

Wrap the interruptible sleep loop (established in ENH-1133) to emit `rate_limit_waiting` every 60s:

```python
last_heartbeat = time.time()
while time.time() < deadline:
    if self._shutdown_requested:
        break
    time.sleep(min(0.1, deadline - time.time()))
    now = time.time()
    if now - last_heartbeat >= 60:
        self._emit(RATE_LIMIT_WAITING_EVENT, {
            "state": self._current_state,
            "elapsed_seconds": now - tier_start,
            "next_attempt_at": deadline,
            "total_waited_seconds": total_wait_seconds,
            "budget_seconds": rate_limit_max_wait_seconds,
            "tier": "long_wait"
        })
        last_heartbeat = now
```

### 2. Event registration (`generate_schemas.py:161-181`)

Register `rate_limit_waiting` following the `rate_limit_exhausted`/`rate_limit_storm` pattern:
```python
_schema("rate_limit_waiting", {
    "state": str,
    "elapsed_seconds": float,
    "next_attempt_at": float,
    "total_waited_seconds": float,
    "budget_seconds": int,
    "tier": str,
})
```

Regenerate `docs/reference/schemas/rate_limit_waiting.json` via `ll-generate-schemas`.

### 3. Event count updates (`generate_schemas.py`)

Update docstring and comments at lines 1, 74, 78, 320 (four locations hard-code "21"); change to "22" and update `# FSM Executor (13 types)` comment at line 78 to "14 types".

### 4. Event constant (`executor.py` near lines 49-58`)

Add:
```python
RATE_LIMIT_WAITING_EVENT = "rate_limit_waiting"
```

### 5. Public API exports (`fsm/__init__.py:87,140`)

Add `RATE_LIMIT_WAITING_EVENT` and the currently-missing `RATE_LIMIT_STORM_EVENT` to re-exports alongside `RATE_LIMIT_EXHAUSTED_EVENT`. (ENH-1134 handles `RateLimitCircuit`.)

### 6. UI rendering (`cli/loop/layout.py:36,67,204-205`)

Add rendering for `rate_limit_waiting` as a status pill or informational display — it should surface as event-only (not as an edge in the routing diagram). Update `cli/config.py` / `config/cli.py:87,101,118` and `config/core.py:484` with a color key for `rate_limit_waiting` if desired.

If `rate_limit_waiting` is given an edge-label color:
- Declare the key in `config-schema.json:916-919` (`fsm_edge_labels` has `additionalProperties: false`)
- Extend `BRConfig.to_dict` (`config/core.py:484`) for the `fsm_edge_labels` serialization block

### 7. Documentation

All doc touch points from ENH-1131:

- `docs/guides/LOOPS_GUIDE.md:1029-1031` — add 2 rows for `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` to per-state property table
- `docs/guides/LOOPS_GUIDE.md:1668-1680` — extend prose + YAML example with two-tier ladder + budget mechanics
- `docs/guides/LOOPS_GUIDE.md:2028` — update `with_rate_limit_handling` fragment row "Supplies" column
- `docs/reference/EVENT-SCHEMA.md:224-255,538-559,629-651` — add `rate_limit_waiting` in event detail section, file listing, and quick-reference table
- `docs/reference/CONFIGURATION.md:69-80,321-327,595` — add `commands.rate_limits` to example block and property table; add edge-label color entry if applicable
- `docs/reference/OUTPUT_STYLING.md:60,204,216` — add `rate_limit_waiting` parallel entries alongside `rate_limit_exhausted` entries
- `docs/reference/API.md:3802-3807` — append `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` rows to `StateConfig` rate-limit field table
- `docs/reference/COMMANDS.md:513` — add `rate_limit_waiting` alongside `rate_limit_exhausted` in event analysis mention
- `CHANGELOG.md` — entry consistent with prior BUG-1105/1107/1108/1109 entries

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — heartbeat emit in sleep loop; `RATE_LIMIT_WAITING_EVENT` constant
- `scripts/little_loops/fsm/__init__.py` — re-export `RATE_LIMIT_WAITING_EVENT`, `RATE_LIMIT_STORM_EVENT`
- `scripts/little_loops/generate_schemas.py` — register event; update 4 count references
- `scripts/little_loops/cli/loop/layout.py` — `rate_limit_waiting` rendering
- `scripts/little_loops/config/cli.py` / `config/core.py` — color key (if assigned)
- All `docs/` files listed above
- `CHANGELOG.md`

### Depends On

- ENH-1132 — config fields for heartbeat payload (`budget_seconds`)
- ENH-1133 — interruptible sleep loop with `total_wait_seconds` accumulator to wrap
- ENH-1134 — `RateLimitCircuit` re-export (handles separately, but same `__init__.py` file)

### Tests

- `scripts/tests/test_generate_schemas.py:19,46,52,165` — update hardcoded `len == 21` to 22 (4 places); add `rate_limit_waiting` to expected event-type set at line 46
- `scripts/tests/test_fsm_executor.py:4303-4637` — heartbeat emitter inside sleep loop means event streams gain `rate_limit_waiting` events; new tests should filter or mock heartbeat when asserting exact event-stream length/order; add a test asserting heartbeat fires at 60s cadence (mock `time.time`)
- `scripts/tests/test_ll_loop_display.py:2421` — confirm `rate_limit_waiting` does NOT appear in edge set (event-only rendering)
- `scripts/tests/test_ll_loop_execution.py`, `test_ll_loop_state.py` — spot-check new optional `StateConfig` fields don't break integration-style construction

## Acceptance Criteria

- `RATE_LIMIT_WAITING_EVENT` constant defined and exported from `fsm/__init__.py`
- `RATE_LIMIT_STORM_EVENT` also exported (was missing from `__init__.py`)
- Heartbeat events emitted at 60s intervals during long-wait sleeps; visible in `ll-loop` UI
- `rate_limit_waiting` registered in `generate_schemas.py`; schema JSON regenerated
- All 4 hard-coded "21" count references in `generate_schemas.py` updated to 22
- `test_generate_schemas.py` count and expected-set assertions updated; tests pass
- `test_fsm_executor.py` heartbeat cadence test passes
- All documentation files updated with correct line-range coverage
- `CHANGELOG.md` entry present
- `test_ll_loop_display.py:2421` confirms `rate_limit_waiting` is event-only (not an edge)

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Status
- [ ] Open
