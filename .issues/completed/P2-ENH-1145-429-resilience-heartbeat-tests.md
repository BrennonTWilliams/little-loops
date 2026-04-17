---
id: ENH-1145
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1135
related: [ENH-1131, ENH-1144]
size: Very Large
confidence_score: 85
outcome_confidence: 90
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# ENH-1145: 429 Resilience — Heartbeat Tests

## Summary

Update all test suites affected by the `rate_limit_waiting` heartbeat event added in ENH-1144: bump hard-coded count assertions from 21→22, add the new event to expected sets, add a heartbeat cadence test, add package-level import tests for the new constants, audit existing rate-limit tests for event-stream length breakage, and update `fake_sleep` signatures.

## Parent Issue

Decomposed from ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs

## Depends On

- ENH-1144 — core code must be merged first (constants, schema registration, `_interruptible_sleep` signature)

## Expected Behavior

### 1. `test_generate_schemas.py`

- Bump 4 `== 21` assertions to `== 22` at lines **19, 56, 63, 173**
- Add `"rate_limit_waiting"` to the expected event-type set in `test_all_event_types_in_catalog` near lines 32-33 (alongside `"rate_limit_exhausted"` / `"rate_limit_storm"`)

### 2. `test_fsm_executor.py` — heartbeat cadence test

Add a cadence test patterned on `test_rate_limit_backoff_sleep_called` (~line 4473-4497), which uses `patch("little_loops.fsm.executor.time.sleep", side_effect=_record_sleep)`. The new test should:
- Patch `time.time` and `time.sleep` to simulate 60s+ elapsing
- Confirm `rate_limit_waiting` events are emitted at the expected cadence
- Confirm `rate_limit_waiting` events carry the correct payload fields: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`

### 3. `test_fsm_executor.py` — existing rate-limit tests

The rate-limit suite lives at lines **4318-4509+** (~190 lines). Audit tests that assert exact event-stream length or order (e.g. `test_rate_limit_exhausted_event_emitted` at ~line 4388). These may now receive unexpected `rate_limit_waiting` events. Fix by:
- Filtering `events` by event type before asserting length/order, **or**
- Using short-enough ladder rungs that no 60s heartbeat fires during the test

### 4. `test_fsm_executor.py` — `fake_sleep` signatures

Three `fake_sleep` lambdas at lines **4880, 4906, 4930** use signature `(duration: float) -> float` for `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)`. If ENH-1144 extends `_interruptible_sleep` with `on_heartbeat` param, update these to `(duration: float, on_heartbeat=None) -> float`. These test the pre-action circuit-breaker sleep (line 984), not the long-tier sleep.

### 5. `test_fsm_executor.py` — package-level import tests

Add tests verifying `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` are importable from `little_loops.fsm` (not only from `little_loops.fsm.executor`). Pattern after `test_rate_limit_init_event_constant_exported` at lines 4499-4503.

### 6. `test_ll_loop_display.py`

At the `_collect_edges`-oriented test block (lines 2408-2421), assert that `rate_limit_waiting` does NOT appear in the collected edges (event-only, not a routed edge — no `on_rate_limit_waiting` field on `StateConfig`).

### 7. Conditional tests

If ENH-1144 adds a `rate_limit_waiting` color key to `CliColorsEdgeLabelsConfig`:
- `test_config.py:1353-1363` — add assertion for `rate_limit_waiting` default color in `TestCliColorsEdgeLabelsConfig.test_defaults`
- `test_config_schema.py` — add validation assertion following the existing `rate_limit_exhausted` pattern

## Integration Map

### Files to Modify

- `scripts/tests/test_generate_schemas.py` — count assertions + expected-set
- `scripts/tests/test_fsm_executor.py` — cadence test, audit existing rate-limit tests, fake_sleep signatures, package-level import tests
- `scripts/tests/test_ll_loop_display.py` — assert rate_limit_waiting not in edges
- `scripts/tests/test_ll_loop_execution.py` — spot-check no existing fixtures break
- `scripts/tests/test_ll_loop_state.py` — spot-check
- `scripts/tests/test_rate_limit_circuit.py` — spot-check; references rate-limit-adjacent executor code [Agent 1 finding]
- `scripts/tests/test_fsm_persistence.py` — spot-check; references `consecutive_rate_limit_exhaustions` [Agent 1 finding]
- `scripts/tests/test_fsm_fragments.py` — spot-check; references `on_rate_limit_exhausted` in fixture data [Agent 1 finding]
- (Conditional) `scripts/tests/test_config.py` — color key assertion
- (Conditional) `scripts/tests/test_config_schema.py` — schema validation assertion

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:89-98,141-191` — ENH-1144 must add `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` to the import block and `__all__` before Step 5 package-level import tests can pass. **Critical gap**: `RATE_LIMIT_STORM_EVENT` is currently absent from `__init__.py` entirely — it exists in `executor.py:63` but was never re-exported at the package level. [Agent 1 + Agent 3 findings]
- `scripts/little_loops/fsm/executor.py:61-63,986` — ENH-1144 must define `RATE_LIMIT_WAITING_EVENT` constant and extend `_interruptible_sleep` with `on_heartbeat` param before Steps 2–4 (cadence test, fake_sleep signatures) can be implemented. Current signature confirmed: `(self, duration: float) -> float` — no `on_heartbeat` yet. [Agent 3 finding]

## Implementation Steps

1. Update `test_generate_schemas.py`: bump 4 count assertions 21→22, add `"rate_limit_waiting"` to expected set
2. Audit `test_fsm_executor.py` lines 4318-4509 for exact event-stream assertions; filter by type or use short rungs
3. Update `fake_sleep` signatures at lines 4880, 4906, 4930 if needed
4. Add heartbeat cadence test to `test_fsm_executor.py`
5. Add package-level import tests for `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT`
6. Update `test_ll_loop_display.py` to assert `rate_limit_waiting` not in edges
7. Spot-check `test_ll_loop_execution.py` and `test_ll_loop_state.py`
8. (Conditional) Update `test_config.py` and `test_config_schema.py` if color key added
9. Run full suite: `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_generate_schemas.py scripts/tests/test_ll_loop_display.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

0. **Pre-condition check**: Before implementing, verify ENH-1144 has landed: `RATE_LIMIT_WAITING_EVENT` exists in `executor.py:61-63`, `_interruptible_sleep` has `on_heartbeat` param at `executor.py:986`, and both `RATE_LIMIT_STORM_EVENT` + `RATE_LIMIT_WAITING_EVENT` are in `fsm/__init__.py:89-98` + `__all__:141-191`. If any are missing, ENH-1144 is incomplete — Steps 4, 5, and the fake_sleep update are blocked.
10. Spot-check `scripts/tests/test_rate_limit_circuit.py` — run it; no changes expected but confirm it passes with ENH-1144's executor changes
11. Spot-check `scripts/tests/test_fsm_persistence.py` — run it; tests `consecutive_rate_limit_exhaustions` which is adjacent to rate-limit retry logic
12. Spot-check `scripts/tests/test_fsm_fragments.py` — run it; has `on_rate_limit_exhausted` in fixture data
13. Expand Step 9 pytest command: `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_generate_schemas.py scripts/tests/test_ll_loop_display.py scripts/tests/test_rate_limit_circuit.py scripts/tests/test_fsm_persistence.py scripts/tests/test_fsm_fragments.py -v`

## Acceptance Criteria

- `test_generate_schemas.py` count and expected-set assertions updated; tests pass
- `test_fsm_executor.py` heartbeat cadence test passes
- Existing rate-limit tests pass (no event-stream length breakage)
- `test_ll_loop_display.py` confirms `rate_limit_waiting` is event-only (not an edge)
- Package-level import tests for `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT` pass

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all line numbers verified against current tree):_

**Line-number corrections**

- **`fake_sleep` definitions** live at `test_fsm_executor.py:4876`, `:4902`, `:4926` — **NOT** 4880/4906/4930 as Step 4 claims. The `:4880/:4906/:4930` lines are the corresponding `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)` calls. ENH-1144 correctly lists `:4876/:4902/:4926`; the two issues must agree before implementation. **Canonical: `:4876`, `:4902`, `:4926`.**
- **`expected` event-type set** in `test_expected_event_types_present` lives at `test_generate_schemas.py:23-45` (inside the test at `:21-46`). Insert `"rate_limit_waiting"` in the set.

**Missing updates in Step 1 (test names and docstrings — not just assertions)**

Step 1 currently only says "bump 4 `== 21` assertions." The file also hard-codes the count in **test names and docstrings** that must be updated for consistency:

- `:17` — `def test_all_21_event_types_defined` → rename to `test_all_22_event_types_defined`
- `:18` — docstring `"""All 21 LLEvent types must be defined."""` → `"""All 22 LLEvent types must be defined."""`
- `:22` — docstring `"""Each of the 21 known event types must appear in catalog."""` → `"22 known"`
- `:52` — `def test_creates_21_files` → rename to `test_creates_22_files`
- `:53` — docstring `"""Generates exactly 21 schema files."""` → `"22"`
- `:168` — docstring `"""CLI generates 21 schema files in the specified output directory."""` → `"22"`

This matches the "five `== 21` locations" tally ENH-1144 uses in its Acceptance Criteria (lines 17-19, 22-46, 52-56, 63, 168-173).

**Existing rate-limit tests — audit result (Step 3)**

The feared "event-stream length breakage" is largely unfounded in the current suite because existing tests deliberately collapse the long-wait ladder to zero:

- `test_rate_limit_exhausted_event_emitted` (`:4388-4409`) uses `patch.multiple` with `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0]` and `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0` (`:4399-4404`). With a zero-second rung no 60s heartbeat fires. **Safe.**
- Storm tests in `TestRateLimitStorm` (`:4549`+) filter by event type: `[e for e in events if e.get("event") == "rate_limit_storm"]` (`:4651`). Length assertions target the filtered list, not raw `events`. **Safe.**
- `TestRateLimitTwoTier` (`:4662`+) similarly collapses the ladder.

**Audit deliverable**: grep `test_fsm_executor.py` for `len(events)` to catch any assertion on raw event-stream length that could break. Most existing assertions already filter by `event` key.

**Package-level import tests — context**

A test importing `RATE_LIMIT_STORM_EVENT` **from the executor module** already exists at `:4656-4659`:

```python
def test_storm_event_constant_exported(self) -> None:
    from little_loops.fsm.executor import RATE_LIMIT_STORM_EVENT
    assert RATE_LIMIT_STORM_EVENT == "rate_limit_storm"
```

ENH-1144 adds the re-export in `fsm/__init__.py`. The new Step 5 tests must import **from the package** (`from little_loops.fsm import RATE_LIMIT_STORM_EVENT`) — this is the specific guarantee the re-export is providing, and is what `test_rate_limit_init_event_constant_exported` (`:4499-4503`) models for `RATE_LIMIT_EXHAUSTED_EVENT`.

**Cadence test — implementation sketch (Step 2)**

The existing `test_rate_limit_backoff_sleep_called` pattern at `:4473-4497` patches `time.sleep` with a `side_effect` recorder — but it does **not** exercise `_interruptible_sleep`'s internal 100ms tick loop against simulated elapsed time. The new cadence test is the first test of that loop's callback. Approach:

1. Patch `little_loops.fsm.executor.time.time` to return a monotonically advancing clock (e.g., `[start, start+0.1, start+60.1, start+120.1, ...]` via `side_effect`) so the tick loop sees 60s elapse across a small number of iterations.
2. Patch `little_loops.fsm.executor.time.sleep` to no-op (return immediately).
3. Use `patch.multiple("little_loops.fsm.executor", _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0, _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[180], _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=300)` so the executor walks into the long-wait tier.
4. Collect events via `event_callback=events.append`, then assert `[e for e in events if e.get("event") == "rate_limit_waiting"]` has the expected count and payload keys (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`).

**Test class placement**

- Cadence test and package-level import tests for `RATE_LIMIT_WAITING_EVENT`: add to `TestRateLimitTwoTier` (`:4662`) since heartbeats only fire in the long-wait tier. Alternatively, create a dedicated `TestRateLimitHeartbeat` class immediately after `TestRateLimitTwoTier` to group all heartbeat-specific tests — cleaner grouping for future ENH-1146 docs cross-references.
- Package-level import test for `RATE_LIMIT_STORM_EVENT`: co-locate with the existing `test_storm_event_constant_exported` (`:4656-4659`) in `TestRateLimitStorm` (`:4549`). Name it `test_storm_event_constant_exported_from_package` to distinguish from the existing executor-module variant.

**Conditional color-key tests (Step 7) — schema file is thin**

`test_config_schema.py` is only 63 lines and has no existing `fsm_edge_labels` assertions (it validates `extensions`, `scratch_pad`, `commands.rate_limits`). If ENH-1144 ends up adding a `rate_limit_waiting` color key, the assertion in this file would be a net-new test case, not an addition to an existing one. Since ENH-1144 marks the color key as **optional** ("Color key in `config/cli.py` / `config/core.py` / `config-schema.json` is optional — resolve early if desired"), the current guidance to keep Step 7 conditional is correct.

`test_config.py:1353-1363` (`TestCliColorsEdgeLabelsConfig.test_defaults`) is the right anchor — it already asserts `rate_limit_exhausted == "38;5;214"` at `:1363`, so a new `rate_limit_waiting` default assertion slots in right after.

### Second-pass research (re-run 2026-04-17)

_Added by `/ll:refine-issue --auto` on a prior-refined issue. All first-pass claims re-verified against the current tree and still accurate; additions below:_

**Wider audit surface** — the locator found additional test files that reference rate-limit concepts beyond the four spot-check targets already listed. None need structural edits, but all should be in the expanded pytest command to catch regressions:

- `scripts/tests/test_fsm_schema.py` — 64 rate_limit refs; `on_rate_limit_exhausted` round-trip at `:541,:563,:577,:612,:635,:647`
- `scripts/tests/test_fsm_validation.py` — 28 rate_limit refs; paired-field validation
- `scripts/tests/test_enh1138_doc_wiring.py` — 12 rate_limit refs; circuit-breaker doc wiring
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — 8 rate_limit refs
- `scripts/tests/test_cli_loop_lifecycle.py` — 9 rate_limit refs; executor+circuit wiring
- `scripts/tests/test_builtin_loops.py` — 5 rate_limit refs (e.g. `on_rate_limit_exhausted == "done"` at `:1101`)

**Expanded Step 9 pytest command** (supersedes the Step 13 expansion):

```
python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_generate_schemas.py \
  scripts/tests/test_ll_loop_display.py scripts/tests/test_rate_limit_circuit.py \
  scripts/tests/test_fsm_persistence.py scripts/tests/test_fsm_fragments.py \
  scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py \
  scripts/tests/test_enh1138_doc_wiring.py scripts/tests/test_circuit_breaker_doc_wiring.py \
  scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_builtin_loops.py -v
```

**Cadence test — concrete `time.time` call budget**

`_interruptible_sleep` at `executor.py:986-999` calls `time.time()` at least 3 times per tick iteration (`while` check, `_deadline - time.time()` inside `min()`, then implicit by `time.sleep`'s no-op if patched), plus once at `_start` and once at the return. A safe `side_effect` pattern uses a capped-index helper (modeled on `test_fsm_executor.py:2039-2072`) rather than a fixed-length list:

```python
time_values = [0.0, 0.0, 30.0, 30.0, 60.1, 60.1, 90.0, 90.0, 120.1, 120.1, 180.1]
call_count = [0]
def mock_time() -> float:
    result = time_values[min(call_count[0], len(time_values) - 1)]
    call_count[0] += 1
    return result
```

**Negative-edge assertion shape (Step 6) — first of its kind in the suite**

No existing `_collect_edges` test asserts *absence*. The three positive assertions at `test_ll_loop_display.py:2386-2421` all use `assert (src, dst, label) in edges`. The new negative assertion should read:

```python
assert not any(label == "rate_limit_waiting" for _, _, label in edges)
```

Construct the FSM with `max_rate_limit_retries=3` and `on_rate_limit_exhausted="b"` (same as the existing `test_collect_edges_includes_on_rate_limit_exhausted` fixture at `:2408-2421`) — the point is that the heartbeat event never routes, so even with rate-limit wiring present no `rate_limit_waiting` edge appears.

**Confirmation: all existing rate-limit assertions are filter-based**

Analyzer confirmed **zero** raw `len(events)` assertions exist in `TestRateLimitRetries`, `TestRateLimitStorm`, `TestRateLimitTwoTier`, or `TestRateLimitCircuitIntegration`. Every length check filters first via `[e for e in events if e.get("event") == "..."]`. Step 3's audit is safe to skip as a discovery exercise and can be trimmed to a single grep: `grep -n "len(events)" scripts/tests/test_fsm_executor.py` returns nothing in the rate-limit classes today.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-17 (updated)_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 90/100 → HIGH CONFIDENCE

### Concerns
- **ENH-1144 still unmerged**: `RATE_LIMIT_WAITING_EVENT` absent from `executor.py:61-63`, `_interruptible_sleep` has no `on_heartbeat` param, and neither constant re-exported from `fsm/__init__.py`. Steps 2, 4, 5 fully blocked.
- **Partial green path available**: Steps 1 (21→22 count/name bumps in `test_generate_schemas.py`), 3 (`fake_sleep` signature prep), and 6 (`test_ll_loop_display.py` negative-edge assertion) can be authored now — but won't pass until ENH-1144 registers the event in the schema catalog.

## Session Log
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/714a7073-85c4-4a11-87ff-d55b6cd3eeba.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/faeaeb5a-809b-44dc-a863-28110125b5ea.jsonl`
- `/ll:refine-issue` - 2026-04-17T07:58:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd7378b1-5c6a-491b-b199-a9b79a40d66f.jsonl`
- `/ll:wire-issue` - 2026-04-17T07:51:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02d78f1d-4b44-4cb7-b63a-520183b732f8.jsonl`
- `/ll:refine-issue` - 2026-04-17T07:34:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ff18843-b017-4e27-8795-63d01109cadb.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95f7723-f6c7-4abc-9358-01f0d396ef30.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fdf85f78-783b-4c7d-b356-a778f3565d95.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- ENH-1147: 429 Resilience — Heartbeat Tests: Schema Updates
- ENH-1148: 429 Resilience — Heartbeat Tests: Executor Test Suite
- ENH-1149: 429 Resilience — Heartbeat Tests: Display, Spot-checks & Conditional

---

## Status
- [ ] Open
