---
id: ENH-1135
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1133, ENH-1134, BUG-1107, BUG-1108, BUG-1109]
confidence_score: 98
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs

## Summary

Add the `rate_limit_waiting` event (schema, emit, UI rendering), complete the FSM public API exports, fix hard-coded event counts in `generate_schemas.py` and tests, and write all documentation updates. This is the final integration layer for the ENH-1131 family. Depends on ENH-1132 (schema/config), ENH-1133 (executor retry logic), and ENH-1134 (circuit breaker).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Without heartbeat events, long rate-limit waits (up to 6h) look like a hung process to users watching `ll-loop` UI or tail logs. `rate_limit_waiting` events emitted every 60s provide live progress. The public API, test count assertions, and docs all need updates to close out the ENH-1131 feature set.

## Expected Behavior

### 1. Heartbeat emit loop (`executor.py:963` — long-wait tier sleep call site)

The long-wait sleep currently calls `self._interruptible_sleep(_wait)` at line 963 inside `_handle_rate_limit` (lines 884-967). The existing `_interruptible_sleep` helper (lines 986-999) runs a 100ms tick loop checking `_shutdown_requested`. Two implementation options:

**Option A (preferred):** Add an optional `on_heartbeat` callback param to `_interruptible_sleep`, fired at 60s cadence by tracking `last_heartbeat` inside the existing tick loop. Keeps the short-tier call site (line 952) unchanged.

**Option B:** Inline a heartbeat-aware variant at line 963 only, leaving `_interruptible_sleep` alone.

Either way, the emit must use variables **actually in scope** inside `_handle_rate_limit` at line 963:

```python
# Variables in scope at executor.py:963 (verified 2026-04-17):
#   state, state_name           — StateConfig + name (params to _handle_rate_limit)
#   _wait                       — current ladder rung duration (float)
#   _ladder, _idx, long_retries — ladder position
#   total_wait                  — accumulated wall-clock float (seconds)
#   _max_wait                   — resolved budget (int seconds)
#   record                      — self._rate_limit_retries[state_name] dict
#
# Not in scope: deadline, tier_start, next_attempt_at, self._current_state
# (use self.current_state or the state_name param)

tier_start = time.time()           # compute inside heartbeat scope
deadline  = tier_start + _wait     # local to the sleep call
# ... inside tick loop, every 60s:
self._emit(RATE_LIMIT_WAITING_EVENT, {
    "state": state_name,
    "elapsed_seconds": time.time() - tier_start,
    "next_attempt_at": deadline,
    "total_waited_seconds": total_wait + (time.time() - tier_start),
    "budget_seconds": _max_wait,
    "tier": "long_wait",
})
```

Reference emit sites for payload-shape parity: `_exhaust_rate_limit` at lines 1001-1031 emits `RATE_LIMIT_EXHAUSTED_EVENT` (1010-1021) and `RATE_LIMIT_STORM_EVENT` (1024-1029) via the `self._emit(event, data)` helper defined at lines 874-882.

### 2. Event registration (`generate_schemas.py:165-190`)

Register `rate_limit_waiting` in `SCHEMA_DEFINITIONS` following the sibling pattern (note: actual signature is `_schema(name, title, description, fields, required)`, with field helpers `_str`/`_int`/`_number`/`_nullable_str`):

```python
"rate_limit_waiting": _schema(
    "rate_limit_waiting",
    "Rate Limit Waiting",
    "Heartbeat emitted every ~60s during a long-wait rate-limit sleep so UIs can show live progress.",
    {
        "state": _str("State name currently waiting on rate-limit recovery"),
        "elapsed_seconds": _number("Wall-clock seconds elapsed in the current tier's sleep"),
        "next_attempt_at": _number("Unix timestamp when this sleep is scheduled to end"),
        "total_waited_seconds": _number("Accumulated wall-clock seconds across all rate-limit waits for this state"),
        "budget_seconds": _int("Configured rate_limit_max_wait_seconds budget"),
        "tier": _str("Wait tier identifier (currently only 'long_wait')"),
    },
    ["state", "elapsed_seconds", "next_attempt_at"],
),
```

Regenerate `docs/reference/schemas/rate_limit_waiting.json` via `ll-generate-schemas`.

### 3. Event count updates (`generate_schemas.py`)

Four hard-coded "21" references need to become "22":
- Line 1: module docstring `"""JSON Schema generation for all 21 LLEvent types."""`
- Line 78: section comment `# Schema definitions — all 21 LLEvent types`
- Line 83: subsection comment `# FSM Executor (13 types)` → `(14 types)`
- Line 329: function docstring `"""Generate JSON Schema files for all 21 LLEvent types."""`

(Issue originally cited lines 1, 74, 78, 320 — corrected 2026-04-17 by direct inspection.)

### 4. Event constant (`executor.py` near lines 60-68)

`RATE_LIMIT_EXHAUSTED_EVENT` is at line 61, `RATE_LIMIT_STORM_EVENT` at line 63, `_RATE_LIMIT_STORM_THRESHOLD` at line 65. Add adjacent:

```python
# Event name emitted every ~60s during a long-wait rate-limit sleep.
RATE_LIMIT_WAITING_EVENT: str = "rate_limit_waiting"
```

### 5. Public API exports (`fsm/__init__.py`)

- Import block at line 89-98 currently contains `RATE_LIMIT_EXHAUSTED_EVENT` (line 90). Add `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` to the same `from little_loops.fsm.executor import (...)` block.
- `__all__` starts at line 141; the existing `"RATE_LIMIT_EXHAUSTED_EVENT"` entry is at line 144. Add string entries for the two new constants alphabetically nearby.
- `RateLimitCircuit` (line 117 import) is already handled by ENH-1134.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/schemas.py:15` — docstring reads "all 21 LLEvent types"; update to 22 when `generate_schemas.py` count changes [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — re-exports `main_generate_schemas`; no source change needed but verify after `cli/schemas.py` docstring update [Agent 1 finding]

### Depends On

- ENH-1132 — config fields for heartbeat payload (`budget_seconds`)
- ENH-1133 — interruptible sleep loop with `total_wait_seconds` accumulator to wrap
- ENH-1134 — `RateLimitCircuit` re-export (handles separately, but same `__init__.py` file)

### Tests

- `scripts/tests/test_generate_schemas.py` — update 4 hard-coded `== 21` assertions to `== 22` at lines **19, 56, 63, 173** (issue originally cited 19, 46, 52, 165 — corrected). Add `"rate_limit_waiting"` to the expected event-type set in `test_all_event_types_in_catalog` near line 32-33 where `"rate_limit_exhausted"` / `"rate_limit_storm"` already appear.
- `scripts/tests/test_fsm_executor.py` — rate-limit suite lives at lines **4318-4509+** (issue originally cited 4303-4637). Heartbeat emitter means event streams gain `rate_limit_waiting` events; existing tests that assert exact event-stream length/order (e.g. `test_rate_limit_exhausted_event_emitted` at line ~4388) must filter `events` by event type or run with short enough ladder rungs that no heartbeat fires. Add a cadence test that patches `time.time` / `time.sleep` (follow pattern at `test_rate_limit_backoff_sleep_called` line ~4473-4497 which uses `patch("little_loops.fsm.executor.time.sleep", side_effect=_record_sleep)`).
- `scripts/tests/test_ll_loop_display.py:2408-2421` — the `_collect_edges`-oriented test that enumerates edges. Confirm `rate_limit_waiting` does NOT appear (event-only, not a routed edge) because no `on_rate_limit_waiting` field exists on `StateConfig`.
- `scripts/tests/test_ll_loop_execution.py`, `test_ll_loop_state.py` — spot-check that no existing fixtures break when the new event appears in executor event streams.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:4499-4503` — `test_rate_limit_init_event_constant_exported` tests `RATE_LIMIT_EXHAUSTED_EVENT` from `little_loops.fsm`; add parallel tests verifying `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` are importable at package level (currently only `RATE_LIMIT_STORM_EVENT` is tested via `fsm.executor` at line 4657 — inconsistent) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:4880,4906,4930` — three `fake_sleep` lambdas use `(duration: float) -> float` signature for `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)`; if `_interruptible_sleep` gains an `on_heartbeat` param, update these to `(duration: float, on_heartbeat=None) -> float` — these tests exercise the pre-action circuit-breaker sleep (line 984), not the long-tier sleep, so they are likely safe but must be confirmed [Agent 3 finding]
- `scripts/tests/test_config.py:1353-1363` — `TestCliColorsEdgeLabelsConfig.test_defaults` asserts every edge-label color field; if `rate_limit_waiting` color key is added to `CliColorsEdgeLabelsConfig`, add a parallel assertion here [Agent 3 finding; conditional on color key]
- `scripts/tests/test_config_schema.py` — if `rate_limit_waiting` color key is added to `config-schema.json:fsm_edge_labels.properties`, add a validation assertion following the existing `rate_limit_exhausted` pattern [Agent 3 finding; conditional on color key]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1081` — `ll-generate-schemas` section reads "Generate JSON Schema (draft-07) files for all **19** LLEvent types" — two generations stale; update to 22 [Agent 2 finding]
- `scripts/little_loops/cli/schemas.py:15` — `main_generate_schemas()` docstring "all 21 LLEvent types" → "all 22 LLEvent types" [Agent 2 finding]
- `skills/analyze-loop/SKILL.md:108` — event payload table lists `rate_limit_exhausted`; add `rate_limit_waiting` row with its payload fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`) [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` 2026-04-17 — verified against current HEAD:_

- **Long-wait sleep call site**: `scripts/little_loops/fsm/executor.py:963` — `total_wait += self._interruptible_sleep(_wait)` inside `_handle_rate_limit` (lines 884-967). The short-tier counterpart at line 952 should NOT emit heartbeats (backoff is seconds, not minutes).
- **Interruptible sleep helper**: `executor.py:986-999` — 100ms tick loop with `_shutdown_requested` check. Adding an `on_heartbeat: Callable[[float], None] | None = None` param here centralizes the cadence logic for both tiers (short-tier passes `None`).
- **Emit helper**: `executor.py:874-882` — `self._emit(event, data)` injects `"event"` and `"ts"` keys before calling `self.event_callback`.
- **Circuit breaker interaction**: lines 950-951 (short) and 961-962 (long) already call `self._circuit.record_rate_limit(...)` before sleeping. Heartbeat additions do not need to re-interact with the circuit.
- **State attribute**: use `self.current_state` (public, set at line 145) or the `state_name` param; there is NO `self._current_state`.
- **Missing edge field**: `StateConfig` has no `on_rate_limit_waiting` field. `rate_limit_waiting` is event-only — `cli/loop/layout.py:_collect_edges` needs no change. Color keys in `config/cli.py` / `config/core.py` are only needed if we want the event labeled in live-tail output.
- **`fsm/__init__.py` current state**: `RATE_LIMIT_EXHAUSTED_EVENT` is imported (line 90) and in `__all__` (line 144). `RATE_LIMIT_STORM_EVENT` is imported **directly from `executor` in tests** (test_fsm_executor.py:4657) because it is NOT re-exported — this confirms the issue's claim.
- **Schema registration helper**: `generate_schemas.py` uses `_schema(name, title, description, fields, required)` with field-type helpers `_str` / `_int` / `_number` / `_nullable_str` — NOT raw Python types as originally shown in §2.
- **Existing schema JSON artifacts**: `docs/reference/schemas/rate_limit_exhausted.json` and `rate_limit_storm.json` exist — new file `rate_limit_waiting.json` will be generated by `ll-generate-schemas`.
- **EVENT-SCHEMA.md anchor verified**: `### rate_limit_exhausted` at line 224, `### rate_limit_storm` at line 244. Insert `### rate_limit_waiting` between them (alphabetical) or after `rate_limit_storm` (ordered by severity).

## Implementation Steps

1. **Constants & public API** (`fsm/executor.py`, `fsm/__init__.py`): add `RATE_LIMIT_WAITING_EVENT` constant at executor.py:~64; add it and `RATE_LIMIT_STORM_EVENT` to the `fsm/__init__.py:89-98` import block and `__all__` (line 141-ish).
2. **Emit helper & heartbeat** (`fsm/executor.py`): extend `_interruptible_sleep` (lines 986-999) with an optional heartbeat-callback param. Replace `self._interruptible_sleep(_wait)` at line 963 with a call that passes a lambda emitting `rate_limit_waiting` via `self._emit(...)`. Leave the short-tier call at line 952 unchanged (no callback = old behavior).
3. **Schema registration** (`generate_schemas.py`): add `"rate_limit_waiting"` entry to `SCHEMA_DEFINITIONS` near line 190 (after `rate_limit_storm`); update `# FSM Executor (13 types)` to `(14 types)` at line 83; update all four "21" references (lines 1, 78, 83, 329) to "22". Run `ll-generate-schemas` to regenerate `docs/reference/schemas/rate_limit_waiting.json`.
4. **Tests**:
   - `test_generate_schemas.py`: bump 4 `== 21` assertions to `== 22` (lines 19, 56, 63, 173); add `"rate_limit_waiting"` to expected-set at line 32-33 block.
   - `test_fsm_executor.py`: add heartbeat cadence test patterned on `test_rate_limit_backoff_sleep_called` (~line 4473); audit existing rate-limit tests for event-list length assertions and filter or narrow rungs to avoid heartbeat noise.
   - `test_ll_loop_display.py`: assert `rate_limit_waiting` absent from `_collect_edges` output (line 2408-2421 block).
5. **UI rendering** (`cli/loop/layout.py`): if a status-pill treatment is desired, add `rate_limit_waiting` handling at the terminal-event bucket (~line 67); otherwise no change — live-tail will surface the event via the generic event renderer.
6. **Config color key (optional)**: only if UI step 5 adds styling — extend `config/cli.py` (lines 87, 101, 118), `config/core.py:490`, and `config-schema.json:949` (`fsm_edge_labels` block with `additionalProperties: false`).
7. **Documentation** (see §7 above): update all doc files; add `CHANGELOG.md` entry consistent with BUG-1105/1107/1108/1109 style.
8. **Verification**:
   - `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_generate_schemas.py scripts/tests/test_ll_loop_display.py -v`
   - `ll-generate-schemas && git diff docs/reference/schemas/`
   - `ll-verify-docs` (event counts)
   - `python -m mypy scripts/little_loops/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/cli/schemas.py:15` — docstring "21" → "22" alongside `generate_schemas.py` count update
10. Update `docs/reference/CLI.md:1081` — "all 19 LLEvent types" → "all 22 LLEvent types" (two generations stale)
11. Update `skills/analyze-loop/SKILL.md:108` — add `rate_limit_waiting` row to event payload table
12. Add package-level import tests to `test_fsm_executor.py` — verify `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` are importable from `little_loops.fsm` (not only from `fsm.executor`)
13. Inspect and update `test_fsm_executor.py:4880,4906,4930` `fake_sleep` signatures if `_interruptible_sleep` gains the `on_heartbeat` optional param
14. (Conditional) If color key added: update `test_config.py:1353-1363` and `test_config_schema.py` with `rate_limit_waiting` assertions

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-17_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- UI color key decision (`rate_limit_waiting` in `fsm_edge_labels`) is left optional — resolve early to avoid conditional cascades across config/core.py, config-schema.json, test_config.py, and test_config_schema.py.
- `_interruptible_sleep` signature extension (Option A) requires updating 3 fake_sleep test lambdas at test_fsm_executor.py:4880, 4906, 4930 — mechanical but easy to miss.

### Outcome Risk Factors
- **File count**: 15+ files modified; majority are doc text edits. Risk is manageable if docs are batched as a final step after code+tests pass.
- **Heartbeat test isolation**: existing rate-limit tests asserting exact event stream length/order require filtering or short-ladder rungs to avoid heartbeat noise — audit the ~190-line rate-limit suite (lines 4318-4509) carefully.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T07:16:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95f7723-f6c7-4abc-9358-01f0d396ef30.jsonl`
- `/ll:refine-issue` - 2026-04-17T07:03:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0244746-544d-4d51-b805-0c54a1e0dab0.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`
- `/ll:wire-issue` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0244746-544d-4d51-b805-0c54a1e0dab0.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0244746-544d-4d51-b805-0c54a1e0dab0.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95f7723-f6c7-4abc-9358-01f0d396ef30.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score: 11/11 — Very Large)

### Decomposed Into
- ENH-1144: 429 Resilience — Heartbeat Core Code
- ENH-1145: 429 Resilience — Heartbeat Tests
- ENH-1146: 429 Resilience — Heartbeat Documentation

---

## Status
- [ ] Open
