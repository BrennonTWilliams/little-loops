---
id: ENH-1133
type: ENH
priority: P2
status: completed
completed_date: 2026-04-16
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1134, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1133: 429 Resilience — Two-Tier Retry Logic & Persistence

## Summary

Refactor the FSM executor's rate-limit detection block to implement two-tier retry (short burst → long-wait ladder → exhaustion route), upgrade `LoopState` persistence to store dict-of-record retry state and storm counter, and add a migration path for legacy state files. Depends on ENH-1132 (schema/config foundation).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Current handling (3 retries, ~3.5min total) fails on real outages. The fix adds a long-wait tier that sleeps 5min → 15min → 30min → 1h in a budget-bounded loop before giving up. Persistence must be upgraded so the two-tier state and storm counter survive process restarts (today, storm count silently resets to 0 on resume).

## Current Behavior

- `executor.py:479-541`: 3 in-place retries, exponential backoff (30s base), jittered
  - Detection at 482-486 (`classify_failure` + `"rate limit"`/`"quota"` substring match on `output + "\n" + stderr`)
  - Counter increment at 498-501 (exhausts when `_attempt > _max_retries`)
  - Exhaustion path 502-526 pops per-state counter (504), resolves `_target = state.on_rate_limit_exhausted or state.on_error` (505), emits exhausted event (506-513), increments storm counter (515), emits storm event if threshold hit (516-523), returns `_target` raw (525) — **confirmed bypasses `_route()` at 549 and interceptor loops at 542-548, 550-552**
  - Retry path 527-535 computes `_sleep`, interruptible tick-sleep, returns `route_ctx.state_name`
  - Non-rate-limited outcome 536-540 resets both per-state counter and storm counter
- `_consecutive_rate_limit_exhaustions` (`executor.py:172`): in-memory only, **never persisted** (not in `_save_state` at `persistence.py:419-434` nor restored at `resume()` lines 500-501)
- `rate_limit_retries` (`persistence.py:104-106`): `dict[str, int]` — per-state attempt count only
- Defaults live at `executor.py:49-58`: `_DEFAULT_RATE_LIMIT_RETRIES=3`, `_DEFAULT_RATE_LIMIT_BACKOFF_BASE=30`, `_RATE_LIMIT_STORM_THRESHOLD=3`
- ENH-1132 already landed: `RateLimitsConfig` at `config/automation.py:131-132` defines `max_wait_seconds: int = 21600` and `long_wait_ladder: list[int] = [300, 900, 1800, 3600]`; `StateConfig` overrides at `fsm/schema.py:249-250`; ladder validation at `fsm/validation.py:348-367` (non-empty, positive ints, per-index error reporting)

## Expected Behavior

### 1. Two-tier retry logic (`executor.py:481-541`)

Refactor to track a per-state record:
```python
{
    "short_retries": int,       # attempts in burst tier
    "long_retries": int,        # attempts in long-wait tier
    "total_wait_seconds": float,
    "first_seen_at": float      # epoch timestamp
}
```

On short-tier exhaustion (after `max_rate_limit_retries` attempts), instead of routing to `on_rate_limit_exhausted`, enter **long-wait tier**:
- Use `rate_limit_long_wait_ladder` from `StateConfig` (falls back to global `commands.rate_limits.long_wait_ladder`)
- Advance ladder index on each long-wait exhaustion, capping at the last value
- Only route to `on_rate_limit_exhausted` once `total_wait_seconds >= rate_limit_max_wait_seconds`

The existing `rate_limit_exhausted` event payload should be extended with `short_retries`, `long_retries`, `total_wait_seconds` fields so observers can distinguish tiers.

Post-exhaustion routing still returns `state.on_rate_limit_exhausted or state.on_error` directly (preserving current bypass-of-`_route()` behavior).

### 2. Sleep-loop replacement

During long-wait sleeps, replace direct `time.sleep` calls at `executor.py:527-534` with the same interruptible pattern (100ms tick, check `_shutdown_requested`). The heartbeat emit wrapping will be added in ENH-1135; this issue just ensures the interruptible loop is in place with a `total_wait_seconds` accumulator.

### 3. Persistence: dict-of-record (`persistence.py:104`)

Upgrade `rate_limit_retries` from `dict[str, int]` to `dict[str, dict]`. Update:
- `LoopState` dataclass field type (line 104)
- `to_dict` serialization (line 128)
- `from_dict` deserialization (line 156) — **include migration**: detect `int` values and coerce to `{"short_retries": int, "long_retries": 0, "total_wait_seconds": 0, "first_seen_at": None}`
- `save` path (line 433)
- `restore` path (line 501)

### 4. Persistence: storm counter (`persistence.py`)

Add `consecutive_rate_limit_exhaustions: int = 0` to `LoopState`. Update `to_dict`, `from_dict`, `save`, and `restore` so storm state survives resume.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — lines 479-541: two-tier state machine; lines 527-534: interruptible long-wait loop with accumulator; event payload extension at 506-513; storm counter reset at 515/540
- `scripts/little_loops/fsm/persistence.py` — field decl at 104-106; `to_dict` omit-when-empty at 127-128; `from_dict` at 156; `_save_state` at 433; `resume()` restore at 500-501; add `consecutive_rate_limit_exhaustions` field and wire it through all five locations
- `scripts/little_loops/cli/loop/lifecycle.py:262` — `cmd_resume` calls `executor.resume()`; no direct changes required here, but verify CLI resume path exercises restored storm counter + record shape
- `docs/reference/schemas/rate_limit_exhausted.json` — extend event schema with optional `short_retries`, `long_retries`, `total_wait_seconds` fields (keep backward-compatible; `LLEvent.from_dict` at `events.py:51-59` forwards unknown keys automatically, but the schema doc needs the new fields)
- `scripts/little_loops/generate_schemas.py:161-170` — **CRITICAL**: add `short_retries`, `long_retries`, `total_wait_seconds` to the `rate_limit_exhausted` properties dict in Python source; `ll-generate-schemas` regenerates `docs/reference/schemas/rate_limit_exhausted.json` from this source — editing only the JSON file will be overwritten on the next schema generation run [Agent 2 finding]

### Dependent Files (Callers / Entry Points)

- `scripts/little_loops/cli/loop/lifecycle.py:262` — sole resume entry point
- `scripts/little_loops/fsm/executor.py:898-906` — `_emit` helper (no change; new payload keys pass through `**data`)
- `scripts/little_loops/events.py:51-59` — `LLEvent.from_dict` (no change; dumps all non-`event`/`ts` keys into `payload`)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py:63` — calls `LoopState.to_dict()` for `ll-loop list --json` output; `rate_limit_retries` values will change shape from `int` to `dict` in the emitted JSON (public CLI API shape change — verify `analyze-loop` skill is not broken) [Agent 1 finding]
- `scripts/little_loops/cli/loop/run.py:217` — constructs `PersistentExecutor`; verify no init-time assumptions about `_rate_limit_retries` shape [Agent 1 finding]
- `scripts/little_loops/extension.py` — imports `PersistentExecutor` (type annotation); no runtime impact [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — re-exports `LoopState`, `PersistentExecutor`, `StateConfig`, `RATE_LIMIT_EXHAUSTED_EVENT`; no change required [Agent 1 finding]
- `scripts/little_loops/cli/loop/_helpers.py` — wires `EventBus` onto `PersistentExecutor`; no rate-limit field coupling [Agent 1 finding]

### Depends On

- ENH-1132 — `StateConfig` new fields must exist before executor can read them (**already landed**: `schema.py:249-250`, `automation.py:131-132`, `validation.py:348-367`)

### Tests

- `scripts/tests/test_fsm_executor.py:4303+` — extend `TestRateLimitRetries` / `TestRateLimitStorm`:
  - Use `patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` to skip sleeps
  - Two-tier ladder transitions: verify long-tier entered after short-tier exhausted
  - Budget enforcement: `total_wait_seconds >= max_wait_seconds` triggers exhaust route
  - Short-circuit on `_shutdown_requested` during long-wait sleep
- `scripts/tests/test_fsm_persistence.py:1737,1787,1815` — update `TestRateLimitRetriesPersistence` (3 tests assert `rate_limit_retries == {"execute": 2}`) to new dict-of-record shape
- `scripts/tests/test_fsm_persistence.py` — add migration test: load hand-crafted legacy `dict[str, int]` state file, assert successful coercion to record shape
- `scripts/tests/test_fsm_persistence.py` — add `consecutive_rate_limit_exhaustions` serialization round-trip test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:1754` — `test_loop_state_rate_limit_retries_omitted_when_empty` uses int-value fixture; must be updated to new dict shape (also in `TestRateLimitRetriesPersistence`) [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py:1770` — `test_loop_state_from_dict_missing_rate_limit_retries_defaults_to_empty` uses int-value fixture; must be updated [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py` — add `consecutive_rate_limit_exhaustions` restore-on-resume integration test mirroring existing pattern at line 1815 (`PersistentExecutor.resume()` restores the storm counter to `_executor._consecutive_rate_limit_exhaustions`) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add test for `rate_limit_exhausted` event payload containing `short_retries`, `long_retries`, `total_wait_seconds` fields (extend `test_rate_limit_exhausted_event_emitted` at line 4382 or add sibling) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add shutdown-during-long-wait-sleep test using Pattern C from `TestBackoff.test_shutdown_during_backoff_terminates_cleanly` at line 2993 (mock `time.time`, call `request_shutdown()` after N ticks, assert `terminated_by == "signal"`) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add `total_wait_seconds` accumulation test: verify accumulator increments across tick-sleeps and triggers exhaustion when budget exceeded [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — add ladder-cap test: verify `long_retries >= len(ladder)` clamps to `ladder[-1]` (i.e., `ladder[min(long_retries, len(ladder) - 1)]`) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:224-237` — `rate_limit_exhausted` event table lists only `state`, `retries`, `next`; add `short_retries`, `long_retries`, `total_wait_seconds` and update example JSON [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:1668-1680` — describes single-tier retry loop; add long-wait tier description and behavior [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:1029-1031` — per-state property table lists only 3 rate-limit fields; add `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` (ENH-1132 landed these fields but doc wasn't updated) [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:2028` — `with_rate_limit_handling` fragment row says "3 retries and 30s base backoff"; update to mention long-wait tier defaults [Agent 2 finding]
- `docs/reference/API.md:3802-3807` — `StateConfig` field table missing `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` [Agent 2 finding]
- `skills/analyze-loop/SKILL.md:108,150-155` — `rate_limit_exhausted` field table lists `retries (int)` only; update to show `short_retries`, `long_retries`, `total_wait_seconds`; review signal classification logic at lines 150-155 that reads `retries` count [Agent 2 finding]

### Similar Patterns to Model After

- `executor.py:323-329` and `527-534` — existing interruptible sleep idiom (100ms tick, check `_shutdown_requested`, `min(0.1, remaining)` cap); extend it with a `total_wait_seconds += tick` accumulator for budget enforcement
- `executor.py:49-58` — existing module-level default constants (follow pattern if adding executor-side defaults; note ENH-1132 put the new knobs in `config/automation.py` + `StateConfig`, so no new executor constants are strictly needed)
- `persistence.py:200-207` — atomic JSON write with `mkstemp + os.replace` (unchanged; already handles the new larger record shape transparently)
- `persistence.py:125-128,155-156` — existing `retry_counts` omit-when-empty serialization + plain `.get(key, {})` deserialization; model new dict-of-record pattern after this
- `config/automation.py:101-109` — `ConfidenceGateConfig.from_dict` legacy-key fallback (`data.get("threshold", 85)` as default for `readiness_threshold`); structural precedent for backward-compat coercion, though the `int → dict` coercion ENH-1133 needs does not yet exist anywhere in the codebase
- `executor.py:898-906` — `_emit` helper unpacks `**data` so new payload keys (`short_retries`, `long_retries`, `total_wait_seconds`) require no schema registration; observers via `LLEvent.from_dict` (`events.py:51-59`) pick them up automatically
- No existing "walk-a-ladder-with-capped-index" pattern exists — the validation at `fsm/validation.py:348-367` guarantees the list is non-empty and positive, so the runtime walk is safe as `ladder[min(long_retries, len(ladder) - 1)]`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Line-number corrections from original draft**: `executor.py:172-173` is really just line 172 (173 is an unrelated comment); `executor.py:481-541` is more precisely `479-541`; `executor.py:324-329` is `323-329`; `persistence.py:104` spans `104-106`; `persistence.py:128` is `127-128`.
- **Resume path is a single choke-point**: `PersistentExecutor.resume()` at `persistence.py:478-527` assigns directly to `_executor` attributes at 494-511. Adding `_executor._consecutive_rate_limit_exhaustions = state.consecutive_rate_limit_exhaustions` here is a one-line change.
- **`_save_state()` is at `persistence.py:419-434`** (not just line 433): captures `_retry_counts` (432) and `_rate_limit_retries` (433). Add a sibling line for the storm counter.
- **Storm-counter reset location**: `executor.py:540` resets `_consecutive_rate_limit_exhaustions = 0` on any non-rate-limited outcome. Preserve this reset after persistence upgrade.
- **Event payload fanout is free**: `LLEvent.from_dict` at `events.py:51-59` forwards all non-`event`/`ts` keys into `payload` as-is. New keys are observable with zero registration cost — but the JSON schema doc at `docs/reference/schemas/rate_limit_exhausted.json` still needs updating for external consumers.
- **No `int → dict` coercion pattern exists in the codebase** — ENH-1133 introduces it. Coercion should be inlined in `LoopState.from_dict` around line 156.

## Implementation Steps — Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/little_loops/generate_schemas.py:161-170` — add `short_retries`, `long_retries`, `total_wait_seconds` properties to the `rate_limit_exhausted` schema dict **before** running `ll-generate-schemas` to regenerate the JSON output file (editing only the JSON will be overwritten)
2. Verify `scripts/little_loops/cli/loop/info.py:63` (`ll-loop list --json`) — the `rate_limit_retries` field in the emitted JSON changes shape; confirm `analyze-loop` skill Step 1 JSON parsing is not broken by the dict-of-dict shape
3. Update `scripts/tests/test_fsm_persistence.py:1754,1770` — two additional tests in `TestRateLimitRetriesPersistence` (beyond the 3 already listed) use the old int-value fixture shape and must be updated
4. Update `docs/reference/EVENT-SCHEMA.md:224-237` — add new payload fields to `rate_limit_exhausted` event table and example JSON
5. Update `docs/guides/LOOPS_GUIDE.md:1668-1680,1029-1031,2028` — add long-wait tier description, ENH-1132 per-state fields, and updated fragment row
6. Update `skills/analyze-loop/SKILL.md:108,150-155` — update `rate_limit_exhausted` field table and review signal classification logic reading `retries`

## Acceptance Criteria

- Short-tier exhaustion enters long-wait tier (does not immediately route to `on_rate_limit_exhausted`)
- Long-wait tier uses `rate_limit_long_wait_ladder`; advances index, caps at last value
- Wall-clock budget (`rate_limit_max_wait_seconds`) enforced; per-state override respected
- `_shutdown_requested` exits long-wait sleep promptly
- `rate_limit_exhausted` payload includes `short_retries`, `long_retries`, `total_wait_seconds`
- `LoopState` persists dict-of-record retry state and storm counter; restored correctly on resume
- Legacy `dict[str, int]` state files migrate cleanly
- Existing `TestRateLimitRetriesPersistence` tests updated and passing; new migration test passes

## Session Log
- `/ll:refine-issue` - 2026-04-17T04:23:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/381101e8-8f6f-4391-867a-92e9dfdd3d59.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`
- `/ll:wire-issue` - 2026-04-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ce365ab-5b19-413d-a2ee-85f0dd55422f.jsonl`
- `/ll:manage-issue` - 2026-04-16T23:45:00 - completed

---

## Resolution

Implemented two-tier rate-limit retry ladder, dict-of-record persistence, and storm-counter durability across process restarts.

**Changes:**
- `scripts/little_loops/fsm/executor.py` — added `_handle_rate_limit`, `_interruptible_sleep`, `_exhaust_rate_limit` helpers; refactored detection block to two-tier flow (short-burst → long-wait → budget-gated exhaustion). New module defaults `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=21600` and `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[300, 900, 1800, 3600]` mirror `RateLimitsConfig`.
- `scripts/little_loops/fsm/persistence.py` — `LoopState.rate_limit_retries` is now `dict[str, dict[str, Any]]` (short_retries, long_retries, total_wait_seconds, first_seen_at). Added `consecutive_rate_limit_exhaustions` field. `from_dict` coerces legacy `dict[str, int]` values to record shape. `_save_state` and `resume()` now persist/restore the storm counter and deep-copy the record dict.
- `scripts/little_loops/generate_schemas.py` — `rate_limit_exhausted` schema extended with `short_retries`, `long_retries`, `total_wait_seconds` properties. Added `_number()` helper for numeric (non-integer) fields. Regenerated `docs/reference/schemas/rate_limit_exhausted.json`.
- `docs/reference/EVENT-SCHEMA.md` — updated event payload table and example.
- `docs/guides/LOOPS_GUIDE.md` — added `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` rows to per-state property table (1029-1031); rewrote the 429 safeguard section (1668-1680) to describe two-tier behavior; updated `with_rate_limit_handling` fragment row.
- `docs/reference/API.md` — added new `StateConfig` fields; updated rate-limit handling blurb.
- `skills/analyze-loop/SKILL.md` — updated `rate_limit_exhausted` field table and signal classification rule.
- `scripts/tests/test_fsm_executor.py` — updated `TestRateLimitRetries`/`TestRateLimitStorm` fixtures and assertions for new semantics; added `TestRateLimitTwoTier` class with 5 new tests (tier transition, ladder cap, budget enforcement, shutdown-during-long-wait, total_wait_seconds accumulation).
- `scripts/tests/test_fsm_persistence.py` — added legacy-int migration test, storm-counter round-trip test, storm-counter default-to-zero test; updated 3 existing tests for new dict-of-record shape; extended resume-restore test to cover storm counter.

**Verification:**
- `ruff check scripts/` — clean
- `python -m mypy scripts/little_loops/` — only pre-existing unrelated error
- `python -m pytest scripts/tests/` — 4884 passed, 5 skipped

---

## Status
- [x] Completed
