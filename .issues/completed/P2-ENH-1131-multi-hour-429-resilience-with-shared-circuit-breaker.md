---
id: ENH-1131
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
discovered_by: capture-issue
related: [BUG-1107, BUG-1108, BUG-1109, ENH-1115]
confidence_score: 100
outcome_confidence: 36
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
size: Very Large
---

# ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Summary

Extend the FSM executor's existing 429 handling (BUG-1107/1108/1109) so loops can survive sustained rate-limit outages of many hours without false failures, without runaway resource use, and without parallel worktrees stampeding each other. Combine four mechanisms: two-tier retry, wall-clock budget, shared circuit-breaker file, and heartbeat events during long waits.

## Motivation

Current 429 handling (commits `8dba4536`, `95b4fed2`, `c8ea14e9`) gives 3 in-place retries with 30s/60s/120s exponential backoff — total tolerance ~3.5min per state. That covers transient blips but fails immediately on real outages (token-per-day exhaustion, sustained API degradation).

Observed in autodev FEAT-292 trace (2026-04-16): both `refine_issue` and `run_size_review` exhausted retries and routed to `on_error`, masquerading as a clean "no decomposition" outcome. User saw misleading "no further decomposition possible" — when in reality the work simply hadn't been attempted past the 3.5min window.

Worse, `ll-parallel` worktrees independently discover the same outage and burn quota in parallel — N workers each retrying expensive slash commands during a global rate-limit event multiplies waste and delays recovery.

**Why:** Loops should be able to wait *hours* for quota to reset rather than failing fast and forcing the user to manually re-run. This is especially important for overnight `ll-auto`/`ll-parallel`/autodev runs.

**How to apply:** Affects `scripts/little_loops/fsm/executor.py` rate-limit detection block (currently lines 481–541), `StateConfig` schema (`fsm/schema.py:239-241`), persistence (`fsm/persistence.py:104`), and `lib/common.yaml` fragment (`loops/lib/common.yaml:49-55`).

## Current Behavior

- 3 in-place retries, exponential backoff (30s base), jittered.
- On exhaustion: emits `rate_limit_exhausted`, routes to `on_rate_limit_exhausted` or `on_error`.
- Storm detection: 3 consecutive exhaustions across states emits `rate_limit_storm`.
- No shared state between parallel processes — each worktree retries independently.
- Long sleeps interruptible via `_shutdown_requested`.
- No progress emitted during sleep windows.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Detection block** (`executor.py:481-541`): uses `classify_failure()` from `issue_lifecycle.py:47-75` to scan combined stdout+stderr for 429 patterns; only `FailureType.TRANSIENT` whose `_reason` contains `"rate limit"` or `"quota"` enters the retry branch.
- **Defaults** (`executor.py:49-58`): `_DEFAULT_RATE_LIMIT_RETRIES = 3`, `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 30`, `_RATE_LIMIT_STORM_THRESHOLD = 3`.
- **Retry counter** (`executor.py:164-172,540`): `self._rate_limit_retries: dict[str, int]` tracks per-state attempts; reset on clean success at line 540 and after exhaustion at line 504.
- **Storm counter NOT persisted**: `_consecutive_rate_limit_exhaustions` (`executor.py:172-173`) is an in-memory field only — **not** serialized into `LoopState` (`persistence.py:104`). On resume, storm state silently resets to 0. ENH-1131 should extend persistence to capture it alongside the new two-tier retry record.
- **Storm event is not routed** (`executor.py:516-523`): emits `rate_limit_storm` purely for observability; no automatic routing is triggered — the existing "give up entirely" behavior is solely via `on_rate_limit_exhausted`/`on_error`.
- **Post-exhaustion routing bypasses `_route()`** (`executor.py:505,524-526`): returns `state.on_rate_limit_exhausted or state.on_error` directly as a raw state name; skips the routing table. Returning `None` terminates the FSM with `terminated_by="error"`.
- **No `rate_limit_retry` event exists** — in-place retry is silent between emits; only `state_enter`/`route` fire on re-entry. Heartbeat event fills this gap.
- **`classify_failure` pattern set** (`issue_lifecycle.py:47-75`): matches `"rate limit"`, `"quota exceeded"`, `"too many requests"`, `"api limit"`, `"usage limit"`, `"429"`, `"resource exhausted"`, `"resourceexhausted"`, `"out of extra usage"`. Circuit-breaker file-write trigger should reuse this same classifier to stay consistent.
- **No pre-action interceptor hook exists**: `_interceptors` (`executor.py:181`) only supports `before_route` / `after_route` (`executor.py:542-553`), both of which fire **after** the action runs. The cleanest single insertion point for a pre-action circuit-breaker check is between `executor.py:427` and `428`, after the sub-loop dispatch guard and before `action_result = None` at line 449.
- **Interruptible-sleep pattern** (`executor.py:324-329,527-534`): `while time.time() < deadline: if self._shutdown_requested: break; time.sleep(min(0.1, deadline - time.time()))` — 100ms tick. Heartbeat emitter should wrap this same loop, emitting `rate_limit_waiting` on a 60s cadence derived from `elapsed % 60 == 0`.
- **File-locking precedent** (`concurrency.py:14,121-141`): `LockManager.acquire()` uses a sentinel `.acquire.lock` file with `fcntl.flock(dir_lock, fcntl.LOCK_EX)` inside a `with open(...)` block; lock released on block exit. Only stdlib `fcntl` is used — no `filelock`/`portalocker`. Circuit breaker should follow this identical pattern.
- **Atomic write precedent** (`persistence.py:200-207`): `tempfile.mkstemp` + `os.replace` for crash-safe JSON writes. Circuit-breaker file writes should use the same pattern (under the flock).
- **`.loops/tmp/` is shell-territory today**: no Python module currently reads/writes JSON under `.loops/tmp/`; it's only used by shell actions in loop YAMLs (`autodev.yaml:64-65`, `fix-quality-and-tests.yaml:77-79`, `prompt-regression-test.yaml` baseline). ENH-1131 introduces the first Python-managed file there — ensure `.loops/tmp/` is created on demand with `Path.mkdir(parents=True, exist_ok=True)`.
- **`rate_limit_exhausted` payload today carries `retries` = `_max_retries` (the configured limit), not the actual attempt count** (`executor.py:506-513`). For the two-tier version, consider adding explicit `short_retries` / `long_retries` / `total_wait_seconds` fields so observers can distinguish tiers.

## Expected Behavior

### 1. Two-tier retry strategy

Keep current short-burst retries (3×, ~3min) as "transient blip" tier. On exhaustion, instead of routing immediately to `on_rate_limit_exhausted`, enter **long-wait tier**:

- Backoff ladder: 5min → 15min → 30min → 1h → 1h → 1h … capped at 1h per attempt.
- Continue until a configurable wall-clock budget elapses.
- Only then route to `on_rate_limit_exhausted`.

### 2. Wall-clock budget instead of (only) retry count

Add `rate_limit_max_wait_seconds` to `StateConfig` (per-state) and a global default in `ll-config.json` (`commands.rate_limits.max_wait_seconds`, default 21600 = 6h). Retry-count cap remains as a backstop, but the user-meaningful knob becomes "wait up to N hours."

### 3. Shared circuit-breaker file

When any process detects a 429:

1. Acquire file lock on `.loops/tmp/rate-limit-circuit.json`.
2. Update `{first_seen, last_seen, attempts, estimated_recovery_at}` with backoff-derived recovery estimate.
3. Release lock.

Before every LLM-bearing action (slash_command / prompt / sub-loop), executor checks the file:

- If `estimated_recovery_at` is in the future → pre-sleep until that time before attempting the action.
- If file is stale (>1h since `last_seen` with no recent updates) → ignore, attempt action normally.

This eliminates the parallel stampede where N worktrees each independently hit 429 and blow their retry budget within minutes.

### 4. Heartbeat events during long waits

Emit `rate_limit_waiting` event every 60s during sleep windows: `{state, elapsed_seconds, next_attempt_at, total_waited_seconds, budget_seconds}`. Renders in `ll-loop` UI and tail logs so users can see the loop is alive and waiting, not hung.

## Integration Map

### Files to Modify

**FSM core**
- `scripts/little_loops/fsm/executor.py` — rewrite rate-limit detection block at lines 481-541 for two-tier retries; add pre-action circuit-breaker check between lines 427-428; add heartbeat emit loop replacing direct `time.sleep` calls at lines 527-534; add new event constant near lines 49-58.
- `scripts/little_loops/fsm/schema.py` — add `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` fields to `StateConfig` at lines 239-241; extend `to_dict` (lines 287-291), `from_dict` (lines 352-354), and docstring (lines 208-214).
- `scripts/little_loops/fsm/persistence.py` — upgrade `rate_limit_retries` field at line 104 from `dict[str, int]` to a dict-of-record structure that holds `(short_retries, long_retries, total_wait_seconds, first_seen_at)`; update serialize (lines 128-129), deserialize (line 156), save (line 433), and restore (line 501). Also add a persisted `consecutive_rate_limit_exhaustions` field so storm state survives resume.
- `scripts/little_loops/fsm/validation.py` — extend rate-limit cross-field validation at lines 304-333 to cover the new fields (ladder non-empty, budget > 0, ladder values > 0).
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add new per-state properties near lines 261-275.

**New module**
- `scripts/little_loops/fsm/rate_limit_circuit.py` (NEW) — `RateLimitCircuit` helper with file-locked read/write of `.loops/tmp/rate-limit-circuit.json`. Model on `fsm/concurrency.py:121-141` (fcntl.flock) + `fsm/persistence.py:200-207` (atomic write). Expose `record_rate_limit()`, `get_estimated_recovery()`, `is_stale()`, `clear()`.

**Config**
- `config-schema.json` — add `commands.rate_limits` block (nested object with `max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`, `circuit_breaker_path`) in the `commands` object near lines 282-340. **Note:** `commands` has `"additionalProperties": false` — new key must be declared here.
- `scripts/little_loops/config/automation.py` — add `RateLimitsConfig` dataclass; extend `CommandsConfig` at lines 112-131 to include it.
- `scripts/little_loops/config/core.py` — already wires `CommandsConfig.from_dict` at line 104; no change needed if added via dataclass composition.

**Fragments & event schemas**
- `scripts/little_loops/loops/lib/common.yaml` — extend `with_rate_limit_handling` fragment at lines 49-55 with long-wait defaults (`rate_limit_max_wait_seconds: 21600`, `rate_limit_long_wait_ladder: [300, 900, 1800, 3600]`).
- `scripts/little_loops/generate_schemas.py` — register `rate_limit_waiting` event near lines 161-181 (follow the `rate_limit_exhausted` / `rate_limit_storm` pattern). Also regenerate `docs/reference/schemas/rate_limit_waiting.json` via the `ll-generate-schemas` tool.

### Dependent Files (Callers / Observers)

- `scripts/little_loops/loops/autodev.yaml:92-98,165-168,310-318` — already uses `with_rate_limit_handling`; verify no breaking changes required beyond fragment opt-in.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:92-95` — same.
- `scripts/little_loops/loops/recursive-refine.yaml:95-101` — same.
- `scripts/little_loops/cli/loop/layout.py:36,67,204-205` — edge rendering for `rate_limit_exhausted`; add rendering for `rate_limit_waiting` if it should surface as an edge or status pill.
- `scripts/little_loops/config/cli.py:87,101,118` and `scripts/little_loops/config/core.py:484` — color config for `rate_limit_exhausted`; add corresponding color key for `rate_limit_waiting`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:87,140` — re-exports `RATE_LIMIT_EXHAUSTED_EVENT` (and many FSM symbols); ENH-1131 should add `RATE_LIMIT_WAITING_EVENT` (and `RATE_LIMIT_STORM_EVENT`, currently missing despite being defined in `executor.py`) and optionally `RateLimitCircuit` to the public API. Without this, consumers (`extension.py`, tests, downstream extensions) must import from private paths.
- `scripts/little_loops/config/__init__.py` — re-exports `CommandsConfig`, `AutomationConfig`, `ParallelAutomationConfig`; the new `RateLimitsConfig` dataclass should be added here too, following the existing composition pattern.
- `scripts/little_loops/extension.py` — lazy-imports `FSMExecutor`, `PersistentExecutor`, `RouteContext`, `RouteDecision`; no signature changes expected, but extension plugins that subclass the executor may observe the new pre-action circuit-breaker check — confirm `before_route` / `after_route` interceptor contract is unchanged.
- `scripts/little_loops/cli/loop/run.py` — `main_loop` calls `LockManager(loops_dir)` and `PersistentExecutor(...).run()`; must verify that a circuit-breaker wait during `run` respects `_shutdown_requested` so Ctrl-C still exits quickly during long waits.
- `scripts/little_loops/cli/loop/lifecycle.py` — resume path via `PersistentExecutor(...).resume()` must restore both the new dict-of-record rate-limit retries and the new `consecutive_rate_limit_exhaustions` field.
- `scripts/little_loops/cli/loop/testing.py` — `SimulationActionRunner` / `DefaultActionRunner` test harness; make sure simulated runs don't write to the real `.loops/tmp/rate-limit-circuit.json` (use the configured `circuit_breaker_path` so tests can redirect to `tmp_path`).
- `scripts/little_loops/cli/loop/info.py`, `cli/loop/_helpers.py`, `cli/loop/config_cmds.py` — consume `LoopState` / `FSMLoop` / `load_and_validate`; no change required unless new persisted fields surface in `ll-loop info` output (consider whether to show current tier / total wait).
- `scripts/little_loops/issue_manager.py:*` — uses `classify_failure()` from `issue_lifecycle.py`; the circuit breaker's "is this a rate-limit?" gate must reuse the **same** classifier (already called out in Open Questions) — confirm shared import path so a future pattern addition propagates to both.
- `scripts/little_loops/cli/schemas.py` — CLI wrapper for `generate_schemas`; invoked via `ll-generate-schemas`. No code change, but must be re-run to materialize `docs/reference/schemas/rate_limit_waiting.json`.

### Tests

- `scripts/tests/test_fsm_executor.py` — extend rate-limit test class at lines ~4303+. Use the existing pattern of `patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` to skip sleeps; add new tests for two-tier ladder transitions, budget exhaustion, heartbeat cadence. See `test_fsm_executor.py:4357,4376,4392,4410,4426` for the pattern.
- `scripts/tests/test_fsm_persistence.py` — extend for dict-of-record shape, migration from old dict-of-int format, and persisted storm counter.
- `scripts/tests/test_fsm_schema.py` — coverage for new StateConfig fields.
- `scripts/tests/test_fsm_validation.py` — coverage for new cross-field validation.
- `scripts/tests/test_fsm_fragments.py` — updated fragment expansion with long-wait defaults.
- `scripts/tests/test_builtin_loops.py` — confirm built-in loops still validate.
- `scripts/tests/test_generate_schemas.py` — register new `rate_limit_waiting` schema.
- `scripts/tests/test_rate_limit_circuit.py` (NEW) — unit tests for the circuit-breaker helper: write/read under lock, stale entry detection, atomic write crash-safety. Use `tmp_path` fixture.

_Wiring pass added by `/ll:wire-issue` — tests that will break without changes:_
- `scripts/tests/test_fsm_persistence.py:1737,1787,1815` (`TestRateLimitRetriesPersistence`) — three tests assert `rate_limit_retries == {"execute": 2}` (raw int values); they will fail when the value type becomes a dict-of-record. Update fixtures to the new shape and add a new "int → record migration" case (`test_fsm_persistence.py:1770` already covers the empty default).
- `scripts/tests/test_generate_schemas.py:19,46,52,165` — hard-codes `len(SCHEMA_DEFINITIONS) == 21` and the full expected event-type set. Adding `rate_limit_waiting` raises the count to 22; the count literal appears in at least four places and the `expected` set at line 46 must gain the new entry.
- `scripts/tests/test_fsm_fragments.py:628,634` — `test_with_rate_limit_handling_default_fields` and `test_with_rate_limit_handling_resolves_from_real_common_yaml` assert exact fragment expansion (`max_rate_limit_retries == 3`, `rate_limit_backoff_base_seconds == 30`); both must gain assertions for `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder`.

_Wiring pass added by `/ll:wire-issue` — tests that need new coverage:_
- `scripts/tests/test_config.py:371` (`TestCommandsConfig`) — add a new `TestRateLimitsConfig` class following the `TestAutomationConfig`/`TestConfidenceGateConfig` pattern (defaults + full-fields round-trip). No existing test breaks, but `CommandsConfig` gains a nested dataclass that needs its own coverage.
- `scripts/tests/test_config.py:1325` — add a parallel `CliColorsEdgeLabelsConfig` assertion for `rate_limit_waiting` color code if the new event is given an edge-label color key.
- `scripts/tests/test_fsm_executor.py:4303-4637` (`TestRateLimitRetries`, `TestRateLimitStorm`) — heartbeat emitter inside the sleep loop means event streams will now contain `rate_limit_waiting` events; any new test that asserts on event-stream exact length/order must mock the heartbeat or filter it out. `patch("little_loops.fsm.executor.time.sleep", side_effect=sleep_calls.append)` already collects the sleep calls — extend the pattern to capture both short-tier and long-tier ladder transitions (verify cumulative wait ≥ budget triggers exhaust routing).
- `scripts/tests/test_ll_loop_display.py:2421` (`test_collect_edges_includes_on_rate_limit_exhausted`) — if `rate_limit_waiting` ever renders as an edge label, add a companion assertion; otherwise confirm it stays event-only and does NOT appear in the edge set.
- `scripts/tests/test_ll_loop_execution.py` and `scripts/tests/test_ll_loop_state.py` — import `FSMExecutor`/`PersistentExecutor`/`StateConfig`; spot-check that the new optional `StateConfig` fields don't trip up any integration-style construction paths (they're `Optional[...] = None` per the schema template).
- `scripts/tests/test_issue_lifecycle.py` (`TestClassifyFailure`) — circuit breaker reuses `classify_failure()` as its 429-detection gate; ensure the existing pattern coverage is referenced, not duplicated, in `test_rate_limit_circuit.py`.

_Wiring pass added by `/ll:wire-issue` — concurrency test pattern:_
- `scripts/tests/test_git_lock.py:395-460` + `scripts/tests/test_concurrency.py:256-307` — established **threading** pattern (`threading.Thread` + `threading.Event` + file-based state assertion via `tmp_path`). No `multiprocessing` precedent exists in the suite, so the concurrent-access test in the new `test_rate_limit_circuit.py` should use threading, not `multiprocessing` as the refined issue originally suggested.

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — document two-tier retry strategy and wall-clock budget concept.
- `docs/reference/CONFIGURATION.md` — document new `commands.rate_limits` block and per-state fields.
- `docs/reference/EVENT-SCHEMA.md` — document `rate_limit_waiting` event.
- `docs/reference/OUTPUT_STYLING.md` — document color key for new event (if added).
- `docs/reference/schemas/rate_limit_waiting.json` — generated by `ll-generate-schemas`.
- `CHANGELOG.md` — entry in line with prior BUG-1105/1107/1108/1109 entries.

_Wiring pass added by `/ll:wire-issue` — precise doc touch points:_
- `docs/reference/API.md:3802-3807` — **not previously listed**. Documents `StateConfig` rate-limit trio; append `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` rows following the existing row pattern.
- `docs/guides/LOOPS_GUIDE.md:1029-1031` — per-state rate-limit property table (3 rows today). Add 2 rows for the new fields.
- `docs/guides/LOOPS_GUIDE.md:1668-1680` — prose + YAML example of rate-limit behavior. Extend with two-tier ladder + budget mechanics.
- `docs/guides/LOOPS_GUIDE.md:2028` — `with_rate_limit_handling` fragment row in the fragments table; update "Supplies" column to reflect the expanded defaults.
- `docs/reference/EVENT-SCHEMA.md:224-255,538-559,629-651` — event detail section, file listing, quick-reference table (three locations).
- `docs/reference/CONFIGURATION.md:69-80,321-327,595` — `commands` example block (add `rate_limits`), `commands` property table (add `rate_limits` sub-block), and `cli.colors.fsm_edge_labels` table (if `rate_limit_waiting` gets an edge color).
- `docs/reference/OUTPUT_STYLING.md:60,204,216` — three separate tables/notes referencing `rate_limit_exhausted`; add parallel entries if a color code is assigned.
- `docs/reference/COMMANDS.md:513` — mentions `rate_limit_exhausted` as an event checked during loop event analysis; parallel entry for `rate_limit_waiting` if applicable.
- `scripts/little_loops/generate_schemas.py:1,74,78,320` — module docstring and comments hard-code "21" event types in **four** locations; all must update to 22 and the `# FSM Executor (13 types)` comment at line 78 becomes "14 types".
- `config-schema.json:916-919` — `cli.colors.fsm_edge_labels` has `additionalProperties: false`; if `rate_limit_waiting` becomes a colorable edge label, the key must be declared here OR the feature is color-disabled by default (decide explicitly).
- `scripts/little_loops/config/core.py:401-411,484` — `BRConfig.to_dict` serializes both the `commands` block and `cli.colors.fsm_edge_labels`; extend both alongside `automation.py` changes so `resolve_variable("commands.rate_limits.max_wait_seconds")` works inside loop YAMLs.

### Configuration

- `.loops/tmp/` — runtime directory (not under version control); ensure callers create with `Path(...).mkdir(parents=True, exist_ok=True)` on first circuit-breaker write. Directory is project-local (matches the resolution from completed BUG-817 / BUG-744 that moved tmp files out of global paths).

### Similar Patterns to Model After

- **Shared state file with flock**: `scripts/little_loops/fsm/concurrency.py:121-141` (LockManager.acquire).
- **Atomic JSON write**: `scripts/little_loops/fsm/persistence.py:200-207` (mkstemp + os.replace).
- **Interruptible sleep loop**: `scripts/little_loops/fsm/executor.py:324-329,527-534` — heartbeat emitter wraps this idiom.
- **Event schema registration**: `scripts/little_loops/generate_schemas.py:161-181` — follow `_schema(...)` helper shape.
- **Per-state config field addition**: `scripts/little_loops/fsm/schema.py:239-241,287-291,352-354` + `fsm/fsm-loop-schema.json:261-275` + `fsm/validation.py:304-333` — the existing rate-limit trio is the template to copy.
- **Nested config block under `commands`**: `config-schema.json:300-325` (`confidence_gate`) + `scripts/little_loops/config/automation.py:112-131` (`CommandsConfig`/`ConfidenceGateConfig`).
- **Prior circuit-breaker experience**: `.issues/completed/P2-BUG-965-circuit-breaker-bypass-exception-path.md` — review for lessons learned on exception-path bypass.

## Acceptance Criteria

- New config keys validated in `fsm-loop-schema.json`:
  - `rate_limit_max_wait_seconds` (per state, optional)
  - `rate_limit_long_wait_ladder` (per state, optional, list of seconds)
- Global defaults under `commands.rate_limits` in `ll-config.json` schema.
- `with_rate_limit_handling` fragment in `lib/common.yaml` updated to set sane long-wait defaults.
- Executor implements two-tier retry: short burst → long wait → exhaustion route.
- Shared circuit-breaker file with file locking; works correctly across `ll-parallel` worktrees.
- Pre-action circuit-breaker check skipped for non-LLM action types (`shell` without slash_command, etc.).
- Heartbeat events emitted at 60s intervals during waits; visible in `ll-loop` UI.
- New events registered in `cli/schemas.py` and EVENT-SCHEMA docs.
- Storm detection still functional as the "give up entirely" escape hatch.
- Persistence handles two-tier retry state across resume.
- Tests:
  - Two-tier ladder transitions correctly on persistent 429s.
  - Wall-clock budget enforced; respects per-state override.
  - Circuit-breaker file written/read with locking; stale entries ignored.
  - Heartbeat events emitted at expected cadence.
  - Resume restores two-tier state correctly.
- Docs updated: `LOOPS_GUIDE.md`, `CONFIGURATION.md`, `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`.

## Implementation Steps

1. **Schema + config** — Add `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` to `StateConfig` at `fsm/schema.py:239-241` (extend `to_dict`/`from_dict` at lines 287-291, 352-354). Add matching properties to `fsm/fsm-loop-schema.json` near lines 261-275. Add `commands.rate_limits` block to `config-schema.json` inside the `commands` object near lines 282-340 (remember `additionalProperties: false`). Create `RateLimitsConfig` dataclass in `scripts/little_loops/config/automation.py` and compose it into `CommandsConfig` at lines 112-131.
2. **Executor two-tier logic** — Refactor `executor.py:481-541` to track a per-state record `{short_retries, long_retries, total_wait_seconds, first_seen_at}`. On short-tier exhaustion, transition to long-tier with ladder-based sleeps instead of routing. Only route to `on_rate_limit_exhausted` after total wait ≥ `rate_limit_max_wait_seconds`.
3. **Circuit breaker** — Create `scripts/little_loops/fsm/rate_limit_circuit.py` with `RateLimitCircuit` helper. Model locking on `concurrency.py:121-141` (fcntl.LOCK_EX in a `with open(...)` block) and atomic write on `persistence.py:200-207` (mkstemp + os.replace). Insert pre-action check in `executor.py` between lines 427 and 428 (after sub-loop guard, before action runs); skip for non-LLM action types (e.g. `action_type: shell` without embedded `slash_command`).
4. **Heartbeat events** — Replace the direct `time.sleep(min(0.1, ...))` loop at `executor.py:527-534` with a sleep-and-emit loop that fires `rate_limit_waiting` every 60s. Register the new event in `generate_schemas.py` near lines 161-181 following the `rate_limit_exhausted`/`rate_limit_storm` shape. Regenerate `docs/reference/schemas/rate_limit_waiting.json` with `ll-generate-schemas`.
5. **Persistence** — Upgrade `rate_limit_retries` at `persistence.py:104` from `dict[str, int]` to dict-of-record; include a migration path in `from_dict` (line 156) for old state files (coerce int → record). Also add a persisted `consecutive_rate_limit_exhaustions: int` field so storm state survives resume (today it's in-memory only at `executor.py:172-173` and silently resets on restart).
6. **Fragment update** — Update `with_rate_limit_handling` at `loops/lib/common.yaml:49-55` to include `rate_limit_max_wait_seconds: 21600` and `rate_limit_long_wait_ladder: [300, 900, 1800, 3600]` defaults. Document opt-out (set budget to 0 or omit ladder) in the fragment description. Verify existing consumers (`loops/autodev.yaml:92-98,165-168,310-318`, `loops/auto-refine-and-implement.yaml:92-95`, `loops/recursive-refine.yaml:95-101`) still work.
7. **Tests** — Unit + integration coverage per acceptance criteria. Use the established pattern from `scripts/tests/test_fsm_executor.py:4303-4471`: `patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` to skip sleeps; `patch("little_loops.fsm.executor.time.sleep", side_effect=sleep_calls.append)` to collect sleep durations; `patch("little_loops.fsm.executor.time.time", ...)` to trigger shutdown mid-backoff. Add a new `scripts/tests/test_rate_limit_circuit.py` for the helper (tmp_path fixture, concurrent-access test via `multiprocessing`).
8. **Docs** — Update `docs/guides/LOOPS_GUIDE.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/reference/OUTPUT_STYLING.md`, and `CHANGELOG.md`. Schema JSON under `docs/reference/schemas/` is generated, not hand-edited.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Public API exports** — Update `scripts/little_loops/fsm/__init__.py` to import and re-export `RATE_LIMIT_WAITING_EVENT` (and also add the currently-missing `RATE_LIMIT_STORM_EVENT`) and `RateLimitCircuit` from the new module. Update `scripts/little_loops/config/__init__.py` to re-export `RateLimitsConfig` alongside `CommandsConfig`.
10. **Config serialization wiring** — Extend `scripts/little_loops/config/core.py:401-411` so `BRConfig.to_dict()` serializes the new `commands.rate_limits` block; required for `${commands.rate_limits.max_wait_seconds}` variable interpolation in loop YAMLs. If `rate_limit_waiting` gets an edge-label color, extend `config/core.py:484` (`fsm_edge_labels` serialization) and declare the key in `config-schema.json:916-919` (note: `fsm_edge_labels` has `additionalProperties: false`).
11. **Persistence: storm counter resume** — Extend `LoopState` dataclass in `persistence.py:104` to include `consecutive_rate_limit_exhaustions: int = 0`. Update `to_dict` (line 128), `from_dict` (line 156), save (line 433 — currently only copies `_rate_limit_retries`), and restore (line 501) so storm state survives resume. Without this, the "give up entirely" escape hatch degrades to 0 after each restart.
12. **Persistence: old-state migration** — In `persistence.py:from_dict` (line 156), detect legacy `dict[str, int]` values in `rate_limit_retries` and coerce each `int` value to the new record `{"short_retries": int, "long_retries": 0, "total_wait_seconds": 0, "first_seen_at": None}`. Add a dedicated `test_fsm_persistence.py` case that loads a hand-crafted legacy state file and asserts successful coercion.
13. **Event count updates** — Update `scripts/little_loops/generate_schemas.py` docstring and comments at lines 1, 74, 78, 320 (four locations hard-code "21"); update `scripts/tests/test_generate_schemas.py:19,46,52,165` to match the new count of 22 and include `rate_limit_waiting` in the expected set.
14. **Existing test fixups** — Update `test_fsm_persistence.py:1737,1787,1815` (three `TestRateLimitRetriesPersistence` tests) to the new dict-of-record shape, and update `test_fsm_fragments.py:628,634` to assert on new fragment defaults. Add new `TestRateLimitsConfig` class in `test_config.py` following the `TestConfidenceGateConfig` pattern.
15. **Concurrency test pattern** — In the new `test_rate_limit_circuit.py`, use the established `threading.Thread` + `threading.Event` pattern from `test_git_lock.py:395-460` (not `multiprocessing` — no `multiprocessing` precedent exists in the suite).
16. **Docs coverage** — In addition to the docs already listed, update `docs/reference/API.md:3802-3807` (StateConfig rate-limit field table) and the specific line ranges called out above in `LOOPS_GUIDE.md:1029-1031,1668-1680,2028`, `EVENT-SCHEMA.md:224-255,538-559,629-651`, `CONFIGURATION.md:69-80,321-327,595`, and `OUTPUT_STYLING.md:60,204,216`.

## API/Interface

```yaml
# StateConfig (new optional fields)
my_llm_state:
  fragment: with_rate_limit_handling
  action: "/ll:something"
  action_type: slash_command
  max_rate_limit_retries: 3              # short-burst tier (existing)
  rate_limit_backoff_base_seconds: 30    # short-burst tier (existing)
  rate_limit_max_wait_seconds: 21600     # NEW: total wall-clock budget (6h)
  rate_limit_long_wait_ladder:           # NEW: long-wait tier sleep schedule (seconds)
    - 300                                #   5min
    - 900                                #  15min
    - 1800                               #  30min
    - 3600                               #   1h (repeats until budget exhausted)
  on_rate_limit_exhausted: dequeue_next
```

```json
// ll-config.json (new section)
{
  "commands": {
    "rate_limits": {
      "max_wait_seconds": 21600,
      "long_wait_ladder": [300, 900, 1800, 3600],
      "circuit_breaker_enabled": true,
      "circuit_breaker_path": ".loops/tmp/rate-limit-circuit.json"
    }
  }
}
```

```jsonc
// rate_limit_waiting event payload
{
  "type": "rate_limit_waiting",
  "state": "refine_issue",
  "elapsed_seconds": 1830,
  "next_attempt_at": "2026-04-17T03:15:00Z",
  "total_waited_seconds": 1830,
  "budget_seconds": 21600,
  "tier": "long_wait"
}
```

## Tradeoffs / Open Questions

- **Cheap-probe optimization** (mechanism #4 from brainstorm) deferred to a follow-up — needs a decision on canonical health check.
- **`retry-after` header parsing** (mechanism #5) deferred — Claude CLI must surface the header through stderr for this to work; verify first.
- **Notification escalation** (mechanism #7) deferred — UX nicety, separate ENH if needed.
- **Circuit-breaker scope**: file is project-local (under `.loops/tmp/`), so cross-project parallel runs don't share state. That's probably fine — quotas are per-account, not per-project, so cross-project sharing would require a user-home-dir file (`~/.claude/rate-limit-circuit.json`). Worth discussing.
- **Heartbeat cadence**: 60s feels right for human observers but spams logs. Consider exponential heartbeat (60s → 5min → 15min) to match the wait ladder.
- **Storm counter resume gap**: today `_consecutive_rate_limit_exhaustions` (`executor.py:172-173`) lives only in memory — on a process restart mid-outage, storm counting silently resets to 0. ENH-1131 should persist it alongside the new retry record, otherwise the "give up entirely" escape hatch degrades after each resume. Flagging explicitly since the existing issue text says "Persistence handles two-tier retry state" without calling out the storm counter.
- **Post-exhaustion routing bypasses `_route()`**: the current code at `executor.py:505,524-526` returns `state.on_rate_limit_exhausted or state.on_error` as a raw state name, skipping the routing table entirely. Decide whether the long-wait exhaustion path should preserve that behavior or integrate with `_route()` (which also consults `state.route.error`). Leaning toward preserve — consistent with current semantics — but worth documenting.
- **Classifier reuse for circuit breaker**: `classify_failure()` (`issue_lifecycle.py:47-75`) is the single source of truth for 429 pattern matching. The circuit breaker's "should I record this as rate-limit?" gate should call it rather than reimplementing the pattern set, so new patterns (e.g. future CLI error phrasing) only need to be added in one place.

## References

- Builds on: BUG-1105 (umbrella), BUG-1107 (executor 429 detection), BUG-1108 (per-state config + storm), BUG-1109 (tests + docs)
- Related but distinct: ENH-1115 (progressive throttling for *successful* repeated calls)
- Triggering observation: autodev FEAT-292 trace, 2026-04-16 — both `refine_issue` and `run_size_review` exhausted in ~3.5min on a sustained 429 storm, parent issue then misleadingly marked "no further decomposition possible"
- Related fix already shipped this session: `run_size_review` in `loops/autodev.yaml` now opts into `with_rate_limit_handling` with `on_rate_limit_exhausted: dequeue_next`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-16_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 36/100 → VERY LOW

### Outcome Risk Factors
- **Blast radius**: 14+ dependent callers; run full test suite after each step, not just at the end.
- **Test breakage pre-identified**: `test_fsm_persistence.py:1737,1787,1815`, `test_fsm_fragments.py:628,634`, and `test_generate_schemas.py` hard-coded counts will fail immediately — fix these in Step 7 before the rest of the suite turns red.
- **Executor complexity**: pre-action circuit-breaker check, two-tier state machine, and heartbeat emitter all touch the same inner loop — implement and test each independently before integrating.
- **Open: circuit-breaker scope**: project-local (`.loops/tmp/`) is specified; cross-project/account sharing is unresolved. Accept project-local for now; don't let this stall implementation.
- **Open: heartbeat cadence**: 60s fixed is fine to ship; defer exponential heartbeat to follow-up if logs are noisy.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T03:49:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37eb6f91-ce88-4b2e-ac38-9ea0e63feafd.jsonl`
- `/ll:wire-issue` - 2026-04-17T03:40:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/607ed87d-f6ba-49c0-a4f2-fe4e4118bd49.jsonl`
- `/ll:refine-issue` - 2026-04-17T03:28:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcd4368d-b7a1-4238-98dd-40992b932b88.jsonl`
- `/ll:capture-issue` - 2026-04-16T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a1d5130-4f36-4679-8288-365c673b3c29.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1db273db-92c0-4518-a02e-d131c8a6790d.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-16
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1132: 429 Resilience — Schema, Config & Fragment Foundation
- ENH-1133: 429 Resilience — Two-Tier Retry Logic & Persistence
- ENH-1134: 429 Resilience — Shared Circuit Breaker Module
- ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs

---

## Status
- [ ] Open
