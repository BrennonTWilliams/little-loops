---
id: ENH-1144
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1135
related: [ENH-1131, ENH-1132, ENH-1133, ENH-1134]
size: Very Large
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1144: 429 Resilience — Heartbeat Core Code

## Summary

Implement the `rate_limit_waiting` heartbeat event in the FSM executor: add the event constant, extend `_interruptible_sleep` with an optional heartbeat callback, emit the event every 60s during long-wait sleeps, register the schema, update event counts, and wire public API exports.

## Parent Issue

Decomposed from ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs

## Motivation

Without heartbeat events, long rate-limit waits (up to 6h) look like a hung process to users watching `ll-loop` UI or tail logs. `rate_limit_waiting` events emitted every 60s provide live progress.

## Expected Behavior

### 1. Event constant (`executor.py` near lines 60-68)

Add adjacent to `RATE_LIMIT_EXHAUSTED_EVENT` (line 61) and `RATE_LIMIT_STORM_EVENT` (line 63):

```python
# Event name emitted every ~60s during a long-wait rate-limit sleep.
RATE_LIMIT_WAITING_EVENT: str = "rate_limit_waiting"
```

### 2. Public API exports (`fsm/__init__.py`)

- Import block at line 89-98: add `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` to the existing `from little_loops.fsm.executor import (...)` block alongside `RATE_LIMIT_EXHAUSTED_EVENT` (line 90).
- `__all__` (line 141+): add string entries for both new constants alphabetically near `"RATE_LIMIT_EXHAUSTED_EVENT"` (line 144).

### 3. Heartbeat emit loop (`executor.py:963`)

Extend `_interruptible_sleep` (lines 986-999) with an optional `on_heartbeat: Callable[[float], None] | None = None` param. Fire it every 60s using a `last_heartbeat` tracker inside the existing tick loop.

Replace `self._interruptible_sleep(_wait)` at line 963 with a call passing a lambda that emits `RATE_LIMIT_WAITING_EVENT`:

```python
tier_start = time.time()
deadline = tier_start + _wait
self._interruptible_sleep(
    _wait,
    on_heartbeat=lambda elapsed: self._emit(RATE_LIMIT_WAITING_EVENT, {
        "state": state_name,
        "elapsed_seconds": elapsed,
        "next_attempt_at": deadline,
        "total_waited_seconds": total_wait + elapsed,
        "budget_seconds": _max_wait,
        "tier": "long_wait",
    }),
)
```

Leave the short-tier call at line 952 unchanged (no callback = old behavior).

### 4. Schema registration (`generate_schemas.py:165-190`)

Add `"rate_limit_waiting"` entry to `SCHEMA_DEFINITIONS` after `rate_limit_storm`:

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

### 5. Event count updates (`generate_schemas.py`)

Update four hard-coded "21" references to "22":
- Line 1: module docstring
- Line 78: section comment
- Line 83: `# FSM Executor (13 types)` → `(14 types)`
- Line 329: function docstring

Update `scripts/little_loops/cli/schemas.py:15` docstring "21" → "22".

Run `ll-generate-schemas` to regenerate `docs/reference/schemas/rate_limit_waiting.json`.

### 6. UI rendering (`cli/loop/layout.py`)

`rate_limit_waiting` is event-only — no `on_rate_limit_waiting` field on `StateConfig`, so `_collect_edges` needs no change. If a status-pill treatment is desired, add rendering at the terminal-event bucket (~line 67); otherwise the generic event renderer surfaces it automatically.

Color key in `config/cli.py` / `config/core.py` / `config-schema.json` is optional — resolve early if desired to avoid conditional cascades.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — `RATE_LIMIT_WAITING_EVENT` constant; `_interruptible_sleep` heartbeat param; emit at line 963
- `scripts/little_loops/fsm/__init__.py` — re-export `RATE_LIMIT_WAITING_EVENT`, `RATE_LIMIT_STORM_EVENT`
- `scripts/little_loops/generate_schemas.py` — register event; update 4 count references
- `scripts/little_loops/cli/schemas.py` — update docstring count 21→22
- `scripts/little_loops/cli/loop/layout.py` — optional status-pill for `rate_limit_waiting`
- `scripts/little_loops/config/cli.py` / `config/core.py` — optional color key
- `config-schema.json` — optional `fsm_edge_labels` entry

### Depends On

- ENH-1132 — config fields (`budget_seconds`)
- ENH-1133 — `_interruptible_sleep` with `total_wait` accumulator
- ENH-1134 — `RateLimitCircuit` re-export in same `__init__.py`

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must update):**
- `scripts/tests/test_generate_schemas.py:52-56` — `test_creates_21_files` asserts `len(files) == 21` → update to 22 [Agent 3 finding]
- `scripts/tests/test_generate_schemas.py:63` — asserts `len(list(output_dir.glob("*.json"))) == 21` → update to 22 [Agent 3 finding]
- `scripts/tests/test_generate_schemas.py:168-173` — `test_cli_creates_files` asserts `len == 21` → update to 22 [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:4876` — `fake_sleep(duration: float) -> float` receives unexpected `on_heartbeat` kwarg when `_interruptible_sleep` gains the new param; add `on_heartbeat=None` to the signature [Agent 2 finding]
- `scripts/tests/test_fsm_executor.py:4902` — same `fake_sleep` signature issue [Agent 2 finding]
- `scripts/tests/test_fsm_executor.py:4926` — same `fake_sleep` signature issue [Agent 2 finding]

**New tests to write:**
- `scripts/tests/test_fsm_executor.py` — add `test_rate_limit_waiting_event_constant_exported`: assert `from little_loops.fsm import RATE_LIMIT_WAITING_EVENT` returns `"rate_limit_waiting"` (pattern: line 4499-4503) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add `test_on_heartbeat_called_during_long_wait`: call real `_interruptible_sleep` with a short duration and a mock `on_heartbeat` callable; assert it was invoked — no existing test exercises the real method's internal tick loop [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:540-562` — file-tree block listing all schema files; add `rate_limit_waiting.json` alphabetically between `rate_limit_storm.json` and `retry_exhausted.json` [Agent 2 finding; owned by ENH-1146]
- `docs/reference/EVENT-SCHEMA.md:631-654` — Quick Reference table; add `rate_limit_waiting` row between `rate_limit_storm` and `retry_exhausted` rows [Agent 2 finding; owned by ENH-1146]
- `docs/reference/CLI.md:1081` — `"all 19 LLEvent types"` → `"all 22 LLEvent types"` (two generations stale) [Agent 2 finding; owned by ENH-1146]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all issue line numbers verified against current tree):_

**Line-number verification**
- `executor.py:61` / `:63` — `RATE_LIMIT_EXHAUSTED_EVENT` / `RATE_LIMIT_STORM_EVENT` confirmed
- `executor.py:952` (short tier) / `:963` (long-wait tier) — `_interruptible_sleep` call sites confirmed
- `executor.py:986-999` — `_interruptible_sleep` body confirmed (single `duration` param today)
- `executor.py:874` — `_emit` helper (`self.event_callback({"event": ..., "ts": _iso_now(), **data})`)
- `executor.py:1010` / `:1024` — existing `RATE_LIMIT_EXHAUSTED_EVENT` / `RATE_LIMIT_STORM_EVENT` emissions in `_exhaust_rate_limit`
- `fsm/__init__.py:89-98` (import block) / `:141-191` (`__all__`) / `:144` (`"RATE_LIMIT_EXHAUSTED_EVENT"`) confirmed; `RATE_LIMIT_STORM_EVENT` is indeed absent from both
- `fsm/__init__.py:117` — `RateLimitCircuit` import already present (ENH-1134 wiring landed)
- Variables in scope at `executor.py:963`: `state_name`, `total_wait`, `_wait`, `_max_wait`, `_ladder`, `_idx`, `record` — confirmed available for the heartbeat lambda

**Correction — `generate_schemas.py` count references (issue Step 5)**
The file contains **three** hard-coded `"21"` strings, not four. They sit at:
- Line 1 — module docstring
- Line 78 — `# Schema definitions — all 21 LLEvent types` section comment
- Line 329 — `generate_schemas()` function docstring

The "fourth" reference listed in the issue (`# FSM Executor (13 types)` at line 83) is a **sub-group counter** containing `"13"`, not `"21"`. It still needs updating (13 → 14 for the new FSM-executor-emitted event), but it is a separate count — not part of the total-events count.

**Missing file — test count assertion**
`scripts/tests/test_generate_schemas.py` hard-codes the `21` count in two places and will fail when the new schema is registered:
- `:17-19` — `test_all_21_event_types_defined` asserts `len(SCHEMA_DEFINITIONS) == 21` (rename + update to 22)
- `:21-46` — `test_expected_event_types_present` enumerates the 21 expected keys (add `"rate_limit_waiting"` to the `expected` set)

**Correction — UI rendering location (issue Step 6)**
The issue references `cli/loop/layout.py` `~line 67`, but `layout.py:27-75` (`_EDGE_LABEL_COLORS`, `_edge_line_color`) colors **FSM routing edges** (edge labels like `"yes"`, `"no"`, `"rate_limit_exhausted"`). `rate_limit_waiting` is a **runtime status event**, not a routing edge, so `layout.py` needs no change. Status-pill rendering for runtime events lives in `scripts/little_loops/cli/loop/_helpers.py` inside the `display_progress` closure (`:319-513`), which already handles `state_enter`, `action_start`, `action_output`, `action_complete`, `evaluate`, `route`. Note: `rate_limit_exhausted` / `rate_limit_storm` are **not currently rendered** in `display_progress` either — so matching the existing pattern means either skipping UI rendering for this issue (generic renderer surfaces the event) or adding rendering for all three rate-limit events together.

**Callback-parameter precedent (for issue Step 3)**
The `on_heartbeat: Callable[[float], None] | None = None` signature directly mirrors the existing `on_output_line: Callable[[str], None] | None = None` used by `fsm/runners.py:36` (`ActionRunner.run`) and `fsm/executor.py:623` (`_run_subprocess`). Guard with `if on_heartbeat is not None:` before invocation (consistent with how `on_output_line` is used at `runners.py:~80`). The existing 100ms tick loop in `_interruptible_sleep` is a natural place to check elapsed time and fire the callback every 60s using a `last_heartbeat` float initialized to `_start`.

**Test patterns to model after** (for the companion ENH-1145)
- `scripts/tests/test_fsm_executor.py:4303` — `TestRateLimitRetries`
- `scripts/tests/test_fsm_executor.py:4549` — `TestRateLimitStorm`
- `scripts/tests/test_fsm_executor.py:4662` — `TestRateLimitTwoTier`
- `scripts/tests/test_fsm_executor.py:4820` — `TestRateLimitCircuitIntegration`
- `scripts/tests/test_fsm_executor.py:4499-4503` — existing `test_rate_limit_init_event_constant_exported` pattern for asserting `from little_loops.fsm import RATE_LIMIT_EXHAUSTED_EVENT` — mirror for both `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT`
- `test_fsm_executor.py:4484-4497` — pattern for patching `little_loops.fsm.executor.time.sleep` with a `side_effect` recorder
- `test_fsm_executor.py:4880` — pattern for patching `_interruptible_sleep` directly with `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)`
- `test_fsm_executor.py:4399-4404` — `patch.multiple` to collapse `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` / `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` / `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` so tier walks don't block

**Additional files to audit for "21" count drift**
Beyond `generate_schemas.py` and `cli/schemas.py:15`, grep the tree for other `21 LLEvent` / `21 event` / `len(SCHEMA_DEFINITIONS) == 21` occurrences before regenerating schemas. At minimum, `test_generate_schemas.py` (above) must be updated in the same change to keep tests green.

## Implementation Steps

1. Add `RATE_LIMIT_WAITING_EVENT` constant at `executor.py:~64`
2. Add `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` to `fsm/__init__.py` import block and `__all__`
3. Extend `_interruptible_sleep` (lines 986-999) with `on_heartbeat` param
4. Update long-wait call site at line 963 to pass heartbeat lambda
5. Add `"rate_limit_waiting"` schema entry to `generate_schemas.py`; update count references (21→22)
6. Update `cli/schemas.py:15` docstring
7. Run `ll-generate-schemas`; verify `docs/reference/schemas/rate_limit_waiting.json` created
8. (Optional) Add color key and UI rendering

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Fix `fake_sleep` signatures in `scripts/tests/test_fsm_executor.py` at lines 4876, 4902, and 4926 — add `on_heartbeat=None` to each `(duration: float) -> float` signature; without this the `patch.object` side_effect will raise `TypeError` when `_interruptible_sleep` passes the new kwarg
10. Fix ALL FIVE `== 21` count assertions in `scripts/tests/test_generate_schemas.py`: lines 17-19 (rename + 21→22), 22-46 (add `"rate_limit_waiting"` to expected set), 52-56 (→22), 63 (→22), and 168-173 (→22)
11. Add `test_rate_limit_waiting_event_constant_exported` to `test_fsm_executor.py` asserting `from little_loops.fsm import RATE_LIMIT_WAITING_EVENT` returns `"rate_limit_waiting"` (follow pattern at line 4499-4503)
12. Add `test_on_heartbeat_called_during_long_wait` to `test_fsm_executor.py`: call real `_interruptible_sleep` with short duration and a mock `on_heartbeat` callable; assert it was invoked (first direct test of the method's callback mechanism)

## Acceptance Criteria

- `RATE_LIMIT_WAITING_EVENT` constant defined and exported from `fsm/__init__.py`
- `RATE_LIMIT_STORM_EVENT` also exported from `fsm/__init__.py`
- Heartbeat events emitted at 60s intervals during long-wait sleeps
- `rate_limit_waiting` registered in `generate_schemas.py`; schema JSON regenerated
- All **three** hard-coded "21" count references in `generate_schemas.py` (lines 1, 78, 329) updated to 22, and the "13" sub-group counter at line 83 updated to 14
- `cli/schemas.py:15` docstring updated 21 → 22
- `scripts/tests/test_generate_schemas.py` updated in all **five** `== 21` locations: lines 17-19 (rename + →22), 22-46 (add `"rate_limit_waiting"` to `expected` set), 52-56 (→22), 63 (→22), and 168-173 (→22)
- `scripts/tests/test_fsm_executor.py:4876`, `:4902`, `:4926` — `fake_sleep` signatures updated with `on_heartbeat=None` parameter so `patch.object` side_effects don't raise `TypeError`
- Short-tier `_interruptible_sleep` call at `executor.py:952` remains callback-free (backward compatible)

## Session Log
- `/ll:wire-issue` - 2026-04-17T07:28:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9285cc5a-ccb9-40de-81d2-22a31b8af554.jsonl`
- `/ll:refine-issue` - 2026-04-17T07:21:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/011d2dd3-667a-4e14-8841-6cb6d04b6a05.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95f7723-f6c7-4abc-9358-01f0d396ef30.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66558bdd-4b8e-4ddb-99d3-bb9d5749e796.jsonl`

---

## Status
- [ ] Open
