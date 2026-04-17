---
id: ENH-1148
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1145
related: [ENH-1144, ENH-1145, ENH-1147, ENH-1149]
size: Very Large
confidence_score: 80
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# ENH-1148: 429 Resilience — Heartbeat Tests: Executor Test Suite

## Summary

Update `test_fsm_executor.py` for the heartbeat feature added in ENH-1144: fix `fake_sleep` signatures, add a heartbeat cadence test, and add package-level import tests for `RATE_LIMIT_STORM_EVENT` and `RATE_LIMIT_WAITING_EVENT`.

## Parent Issue

Decomposed from ENH-1145: 429 Resilience — Heartbeat Tests

## Depends On

- ENH-1144 — `RATE_LIMIT_WAITING_EVENT` constant and `_interruptible_sleep(on_heartbeat=)` param must exist before cadence test and fake_sleep updates can be implemented

## Expected Behavior

### 1. `fake_sleep` signature fixes (Step 3 of parent)

Three `fake_sleep` definitions at `test_fsm_executor.py:4876`, `:4902`, `:4926` use signature `(duration: float) -> float`. If ENH-1144 adds `on_heartbeat` param to `_interruptible_sleep`, update these to:

```python
def fake_sleep(duration: float, on_heartbeat=None) -> float:
```

These are patched via `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)` at lines 4880, 4906, 4930.

### 2. Heartbeat cadence test (Step 4 of parent)

Add a cadence test in a new `TestRateLimitHeartbeat` class immediately after `TestRateLimitTwoTier` (`:4662`):

```python
class TestRateLimitHeartbeat:
    def test_rate_limit_waiting_events_emitted_at_cadence(self):
        ...
```

Implementation approach (from parent research):
1. Patch `little_loops.fsm.executor.time.time` with a capped-index mock advancing in 60s steps:
   ```python
   time_values = [0.0, 0.0, 30.0, 30.0, 60.1, 60.1, 90.0, 90.0, 120.1, 120.1, 180.1]
   call_count = [0]
   def mock_time() -> float:
       result = time_values[min(call_count[0], len(time_values) - 1)]
       call_count[0] += 1
       return result
   ```
2. Patch `little_loops.fsm.executor.time.sleep` to no-op
3. Use `patch.multiple("little_loops.fsm.executor", _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0, _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[180], _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=300)`
4. Collect events via `event_callback=events.append`
5. Assert `[e for e in events if e.get("event") == "rate_limit_waiting"]` has expected count and payload keys: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`

Pattern the test after `test_rate_limit_backoff_sleep_called` at `:4473-4497`.

### 3. Package-level import tests (Step 5 of parent)

Add two tests:

**In `TestRateLimitStorm`** (`:4549`) — alongside `test_storm_event_constant_exported` at `:4656-4659`:
```python
def test_storm_event_constant_exported_from_package(self) -> None:
    from little_loops.fsm import RATE_LIMIT_STORM_EVENT
    assert RATE_LIMIT_STORM_EVENT == "rate_limit_storm"
```

**In `TestRateLimitHeartbeat`** (new class from Step 2):
```python
def test_waiting_event_constant_exported_from_package(self) -> None:
    from little_loops.fsm import RATE_LIMIT_WAITING_EVENT
    assert RATE_LIMIT_WAITING_EVENT == "rate_limit_waiting"
```

Pattern after `test_rate_limit_init_event_constant_exported` at lines 4499-4503.

### 4. Verify existing rate-limit tests are safe (Step 3 audit from parent)

Run this grep to confirm no raw `len(events)` assertions exist in rate-limit test classes:
```bash
grep -n "len(events)" scripts/tests/test_fsm_executor.py
```

Per parent research, all existing assertions already filter by event key — this is a verification step, not a code change.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py`

### Dependent Files
- `scripts/little_loops/fsm/executor.py` — ENH-1144 must add `RATE_LIMIT_WAITING_EVENT` at `:61-63` and `on_heartbeat` param to `_interruptible_sleep` at `:986`
- `scripts/little_loops/fsm/__init__.py` — ENH-1144 must add both constants to `__init__.py:89-98` and `__all__:141-191`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_schemas.py:17,21-46,52,63,173` — five `== 21` count/set assertions will break as a side effect of ENH-1144 adding a 22nd event to `generate_schemas.py`; owned by **ENH-1147** (schema sibling), not ENH-1148 — but ENH-1148 pytest runs should be sequenced after ENH-1147 merges to avoid false failures [Agent 1 + 3 finding]
- `scripts/tests/conftest.py` — provides only path fixtures (`fixtures_dir`, `fsm_fixtures`, `temp_project_dir`, `valid_loop_file`); no executor or sleep fixtures to coordinate with — no changes needed [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py:82-190` — `SCHEMA_DEFINITIONS` dict and "all 21 LLEvent types" docstring must gain a `"rate_limit_waiting"` entry; owned by **ENH-1144**, not ENH-1148, but ENH-1148's package-import tests assert on the constant that flows from this chain [Agent 2 finding]
- `docs/reference/schemas/rate_limit_waiting.json` — generated schema artifact; does not exist yet; created when `ll-generate-schemas` runs post ENH-1144; ENH-1148 does not generate it but the cadence test's payload fields describe the shape it will codify [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current tree on 2026-04-17:_

**Pre-conditions (confirmed not yet in place — hard block on ENH-1144):**
- `executor.py:61` defines `RATE_LIMIT_EXHAUSTED_EVENT`; `:63` defines `RATE_LIMIT_STORM_EVENT`. `RATE_LIMIT_WAITING_EVENT` does **not** exist yet.
- `executor.py:986` current signature: `def _interruptible_sleep(self, duration: float) -> float:` — no `on_heartbeat` kwarg.
- `fsm/__init__.py:90` re-exports only `RATE_LIMIT_EXHAUSTED_EVENT`; `__all__:144` lists only that constant. Neither `RATE_LIMIT_STORM_EVENT` nor `RATE_LIMIT_WAITING_EVENT` is exported at the package level today — both package-import tests are net-new assertions, not regressions.
- `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` (`:53`), `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` (`:56`), `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` (`:59`) are present and patchable.

**Class structure to clarify (important — issue is ambiguous here):**
- The three `fake_sleep` definitions at `:4876`, `:4902`, `:4926` live inside **`TestRateLimitCircuitIntegration`** (starts at `:4820`), not inside `TestRateLimitTwoTier` (`:4662-:4817`).
- The new `TestRateLimitHeartbeat` class should be inserted between `TestRateLimitTwoTier` (ends `:4817`) and `TestRateLimitCircuitIntegration` (starts `:4820`), i.e. around line `:4818` — consistent with "immediately after `TestRateLimitTwoTier`".

**Patterns to model (file:line):**
- Cadence test skeleton: combine `test_rate_limit_backoff_sleep_called` (`:4473-4497`, three-patch parenthesized `with`) + `mock_time` time-value array clamp from `:2023-2037` (`time_values[min(call_count[0], len(time_values) - 1)]`).
- `patch.multiple` on executor defaults: `:4399-4406`, `:4426-4433`, `:4447-4455` — note `FSMExecutor(...)` is constructed **inside** the `with` block.
- Event filtering convention: `[e for e in events if e.get("event") == "..."]` using `.get()` not `[...]` (`:4517-4527`, `:4601-4608`, `:4646-4653`, `:4704-4711`).
- `fake_sleep` convention: returns `float` (`0.0`), not `None`; patched via `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)` against the instance — signature update must preserve both the `-> float` return and the `patch.object` target (`:4876-4880`, `:4902-4906`, `:4926-4930`).
- Package-import test: pattern exactly `test_rate_limit_init_event_constant_exported` (`:4499-4503`) — `from little_loops.fsm import X; assert X == "..."`. Note the existing `test_storm_event_constant_exported` at `:4656-4659` imports from `little_loops.fsm.executor` (module path), so the new `..._from_package` variant importing from `little_loops.fsm` is a distinct assertion.

**Scope bounds confirmed:**
- `_interruptible_sleep` and `fake_sleep` appear **only** in `scripts/tests/test_fsm_executor.py`. No other test file (including `test_rate_limit_circuit.py`, `test_ll_loop_execution.py`, `test_ll_loop_commands.py`) needs signature updates.
- No `len(events)` assertions exist anywhere in the file — the Step 4 audit grep will come back clean.
- `scripts/tests/conftest.py` defines only path fixtures; no executor/sleep fixtures to coordinate with.
- `scripts/tests/test_generate_schemas.py:33` will need `rate_limit_waiting` added to the expected-event-types set when ENH-1144 lands — this is explicitly covered by **ENH-1147** (schema tests sibling), out of scope for ENH-1148.

**Implementation nuances for the cadence test:**
- **Do NOT patch `_interruptible_sleep`** in the cadence test. That method is the unit under test — it's what emits the `rate_limit_waiting` events via `on_heartbeat`. Patch the underlying `time.time` and `time.sleep` at the module level (as Step 4.2 of the parent describes) so the real `_interruptible_sleep` runs with a controlled clock. Contrast with the three `fake_sleep` cases at `:4876/:4902/:4926`, which patch `_interruptible_sleep` because those tests target *callers* of that method, not the method itself.
- **Helper methods for `TestRateLimitHeartbeat`**: each existing rate-limit test class owns its own `_make_fsm`, `_rl_result`, `_ok_result` (see `TestRateLimitRetries:4313/4346/4350`, `TestRateLimitStorm:_make_multi_fsm/4582/4585`, `TestRateLimitTwoTier:_make_fsm/4665/4668`). Follow the same convention — copy the closest-fitting pair (e.g. `TestRateLimitTwoTier`'s two-tier setup is the natural parent since heartbeat emission is a two-tier-wait behavior) rather than reaching across classes.
- **Event-shape assertion targets**: the six payload keys listed in the Expected Behavior section (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`) define the contract ENH-1144 must produce. If ENH-1144 ships a different key set, either ENH-1144 or this test must be reconciled before merge — flag as a cross-issue invariant, not a silent test-side adjustment.

## Implementation Steps

1. **Pre-condition check**: Verify ENH-1144 has landed — grep for `RATE_LIMIT_WAITING_EVENT` in `executor.py` and `fsm/__init__.py`; confirm `_interruptible_sleep` signature at `:986`
2. Run audit grep: `grep -n "len(events)" scripts/tests/test_fsm_executor.py` (expect no hits in rate-limit classes)
3. Update `fake_sleep` signatures at `:4876`, `:4902`, `:4926` if `on_heartbeat` param was added in ENH-1144
4. Add `TestRateLimitHeartbeat` class with cadence test using the mock-time approach
5. Add `test_waiting_event_constant_exported_from_package` in `TestRateLimitHeartbeat`
6. Add `test_storm_event_constant_exported_from_package` in `TestRateLimitStorm`
7. Run: `python -m pytest scripts/tests/test_fsm_executor.py -v -k "rate_limit"`

### Wiring Phase (added by `/ll:wire-issue`)

_These ordering constraints were identified by wiring analysis:_

8. **Sequence gate**: Confirm ENH-1147 has merged before running the full test suite (`python -m pytest scripts/tests/`). ENH-1144 adds a 22nd entry to `generate_schemas.py`; until ENH-1147 updates the five `== 21` assertions in `test_generate_schemas.py`, the broader suite will show failures unrelated to ENH-1148's changes.
9. **Verify no `test_generate_schemas.py` regressions**: After ENH-1147 is applied, run `python -m pytest scripts/tests/test_generate_schemas.py -v` to confirm schema count assertions pass (expected: 22 types). This is a sanity check, not an ENH-1148 code change.

## Acceptance Criteria

- `fake_sleep` signatures accept `on_heartbeat=None` param (if ENH-1144 requires it)
- `TestRateLimitHeartbeat.test_rate_limit_waiting_events_emitted_at_cadence` passes
- `test_waiting_event_constant_exported_from_package` imports successfully from `little_loops.fsm`
- `test_storm_event_constant_exported_from_package` imports successfully from `little_loops.fsm`
- All existing rate-limit tests in `test_fsm_executor.py` continue to pass

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-17_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

### Concerns
- ENH-1144 is the sole hard blocker: `RATE_LIMIT_WAITING_EVENT` does not exist, `_interruptible_sleep` lacks the `on_heartbeat` param, and `fsm/__init__.py` doesn't export either constant yet. All three steps of ENH-1148 depend on ENH-1144 landing first.
- ENH-1147 should also merge before running the full test suite to avoid false failures from the 21→22 event count change.

## Session Log
- `/ll:refine-issue` - 2026-04-17T08:26:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5c96713-3899-4dcf-98ee-038f7e93041a.jsonl`
- `/ll:wire-issue` - 2026-04-17T08:23:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43715745-a98d-450d-b9e5-d3f6adb74cdf.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:17:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c02a7ed-1490-42fb-8832-5cffd4e1b2d8.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/714a7073-85c4-4a11-87ff-d55b6cd3eeba.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43715745-a98d-450d-b9e5-d3f6adb74cdf.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9c07c85-7a12-40a0-9e1f-d2073d5d2025.jsonl`

---

## Status
- [ ] Open
