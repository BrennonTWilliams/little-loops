---
id: ENH-1148
type: ENH
priority: P2
status: closed
discovered_date: 2026-04-17
completed_date: 2026-04-17
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

- ENH-1144 — `RATE_LIMIT_WAITING_EVENT` constant and `_interruptible_sleep(on_heartbeat=)` param must exist before cadence test and fake_sleep updates can be implemented. **Completed 2026-04-17** (see `.issues/completed/P2-ENH-1144-*.md` and commit `f26f8a82`); pre-conditions are now met.

## Expected Behavior

### 1. `fake_sleep` signature fixes (Step 3 of parent) — ALREADY DONE

Three `fake_sleep` definitions at `test_fsm_executor.py:4912`, `:4938`, `:4962` (previously `:4876`, `:4902`, `:4926`) already accept `on_heartbeat: object | None = None` — landed alongside ENH-1144. They are patched via `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)` at lines `:4916`, `:4942`, `:4966`. **No signature changes required in this issue.**

### 2. Heartbeat cadence test (Step 4 of parent)

Add a cadence test in a new `TestRateLimitHeartbeat` class immediately after `TestRateLimitTwoTier` (now at `:4698`, ends `:4854`), i.e. inserted at approximately `:4855` (before `TestRateLimitCircuitIntegration` at `:4856`):

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

### 3. Package-level import tests (Step 5 of parent) — ALREADY PARTIALLY SATISFIED

Equivalent assertions already exist in `TestRateLimitRetries`, added alongside ENH-1144:
- `test_rate_limit_storm_event_constant_exported` at `:4505-4509` — imports `RATE_LIMIT_STORM_EVENT` from the `little_loops.fsm` package
- `test_rate_limit_waiting_event_constant_exported` at `:4511-4515` — imports `RATE_LIMIT_WAITING_EVENT` from the `little_loops.fsm` package

The issue originally called for these to live in `TestRateLimitStorm` (`:4585`, previously `:4549`, alongside `test_storm_event_constant_exported` now at `:4692-4695`) and in the new `TestRateLimitHeartbeat`. **Implementer decides**: either (a) treat these as satisfied and skip, (b) move them into the spec'd classes, or (c) add dedicated `_from_package` duplicates in the spec'd classes for class-level cohesion. Option (a) is the lowest-churn choice since the coverage is already in place.

Reference tests if duplication is chosen:
```python
def test_storm_event_constant_exported_from_package(self) -> None:
    from little_loops.fsm import RATE_LIMIT_STORM_EVENT
    assert RATE_LIMIT_STORM_EVENT == "rate_limit_storm"

def test_waiting_event_constant_exported_from_package(self) -> None:
    from little_loops.fsm import RATE_LIMIT_WAITING_EVENT
    assert RATE_LIMIT_WAITING_EVENT == "rate_limit_waiting"
```

Pattern after `test_rate_limit_init_event_constant_exported` at `:4499-4503`.

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
- `scripts/little_loops/fsm/executor.py` — ENH-1144 added `RATE_LIMIT_WAITING_EVENT` at `:66` (constants now at `:62/:64/:66`) and `on_heartbeat` param to `_interruptible_sleep` at `:1007-1011`. **Landed.**
- `scripts/little_loops/fsm/__init__.py` — ENH-1144 added both constants: imports at `:90-92` and `__all__` entries at `:146-148`. **Landed.**

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

**Pre-conditions (CONFIRMED IN PLACE as of 2026-04-17 — ENH-1144 has landed):**
- `executor.py:62` defines `RATE_LIMIT_EXHAUSTED_EVENT`; `:64` `RATE_LIMIT_STORM_EVENT`; `:66` `RATE_LIMIT_WAITING_EVENT`.
- `executor.py:1007-1011` signature: `def _interruptible_sleep(self, duration: float, on_heartbeat: Callable[[float], None] | None = None) -> float:` — `on_heartbeat` kwarg is present.
- `fsm/__init__.py:90-92` re-exports all three constants; `__all__:146-148` lists them. Package-import tests at `:4505-4515` (in `TestRateLimitRetries`) already assert this.
- `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` (`:54`), `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS` (`:57`), `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` (`:60`) are present and patchable.

**Class structure to clarify (important — issue is ambiguous here):**
- The three `fake_sleep` definitions at `:4912`, `:4938`, `:4962` live inside **`TestRateLimitCircuitIntegration`** (starts at `:4856`), not inside `TestRateLimitTwoTier` (`:4698-:4854`).
- The new `TestRateLimitHeartbeat` class should be inserted between `TestRateLimitTwoTier` (ends `:4854`) and `TestRateLimitCircuitIntegration` (starts `:4856`), i.e. around line `:4855` — consistent with "immediately after `TestRateLimitTwoTier`".

**Patterns to model (file:line):**
- Cadence test skeleton: combine `test_rate_limit_backoff_sleep_called` (`:4473-4497`, three-patch parenthesized `with`) + `mock_time` time-value array clamp from `:2028-2033` (`time_values[min(call_count[0], len(time_values) - 1)]`).
- `patch.multiple` on executor defaults: `:4399-4406`, `:4426-4433`, `:4447-4455` — note `FSMExecutor(...)` is constructed **inside** the `with` block.
- Event filtering convention: `[e for e in events if e.get("event") == "..."]` using `.get()` not `[...]`, used throughout the rate-limit test classes.
- `fake_sleep` convention: returns `float` (`0.0`), not `None`; patched via `patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep)` against the instance. Already updated with `on_heartbeat` param at `:4912-4916`, `:4938-4942`, `:4962-4966`.
- Package-import test: pattern exactly `test_rate_limit_init_event_constant_exported` (`:4499-4503`) — `from little_loops.fsm import X; assert X == "..."`. Note the existing module-path variant `test_storm_event_constant_exported` at `:4692-4695` imports from `little_loops.fsm.executor`, so the package-path variants at `:4505-4515` are distinct assertions.

**Scope bounds confirmed:**
- `_interruptible_sleep` and `fake_sleep` appear **only** in `scripts/tests/test_fsm_executor.py`. No other test file (including `test_rate_limit_circuit.py`, `test_ll_loop_execution.py`, `test_ll_loop_commands.py`) needs signature updates.
- No `len(events)` assertions exist anywhere in the file — the Step 4 audit grep will come back clean.
- `scripts/tests/conftest.py` defines only path fixtures; no executor/sleep fixtures to coordinate with.
- `scripts/tests/test_generate_schemas.py:33` will need `rate_limit_waiting` added to the expected-event-types set when ENH-1144 lands — this is explicitly covered by **ENH-1147** (schema tests sibling), out of scope for ENH-1148.

**Implementation nuances for the cadence test:**
- **Do NOT patch `_interruptible_sleep`** in the cadence test. That method is the unit under test — it's what emits the `rate_limit_waiting` events via `on_heartbeat`. Patch the underlying `time.time` and `time.sleep` at the module level (as Step 4.2 of the parent describes) so the real `_interruptible_sleep` runs with a controlled clock. Contrast with the three `fake_sleep` cases at `:4912/:4938/:4962`, which patch `_interruptible_sleep` because those tests target *callers* of that method, not the method itself.
- **Helper methods for `TestRateLimitHeartbeat`**: each existing rate-limit test class owns its own `_make_fsm`, `_rl_result`, `_ok_result` helpers (see `TestRateLimitRetries` at `:4303`, `TestRateLimitStorm` at `:4585`, `TestRateLimitTwoTier` at `:4698`). Follow the same convention — copy the closest-fitting pair (e.g. `TestRateLimitTwoTier`'s two-tier setup is the natural parent since heartbeat emission is a two-tier-wait behavior) rather than reaching across classes.
- **Event-shape assertion targets**: the six payload keys listed in the Expected Behavior section (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`) define the contract ENH-1144 must produce. If ENH-1144 ships a different key set, either ENH-1144 or this test must be reconciled before merge — flag as a cross-issue invariant, not a silent test-side adjustment.

## Implementation Steps

1. **Pre-condition check**: ENH-1144 has landed — `RATE_LIMIT_WAITING_EVENT` at `executor.py:66`, `_interruptible_sleep` at `:1007-1011` with `on_heartbeat` kwarg, package exports at `fsm/__init__.py:90-92` and `__all__:146-148`. Pre-conditions confirmed on 2026-04-17.
2. Run audit grep: `grep -n "len(events)" scripts/tests/test_fsm_executor.py` (expect no hits; confirmed clean)
3. ~~Update `fake_sleep` signatures~~ — **ALREADY DONE**: signatures at `:4912/:4938/:4962` already accept `on_heartbeat: object | None = None`.
4. Add `TestRateLimitHeartbeat` class with `test_rate_limit_waiting_events_emitted_at_cadence` using the mock-time approach; insert at approximately `:4855` (between `TestRateLimitTwoTier` end `:4854` and `TestRateLimitCircuitIntegration` start `:4856`).
5. *(Optional — already satisfied at `:4505-4515`)* Add `test_waiting_event_constant_exported_from_package` in `TestRateLimitHeartbeat` if class-level cohesion is desired.
6. *(Optional — already satisfied at `:4505-4515`)* Add `test_storm_event_constant_exported_from_package` in `TestRateLimitStorm` (`:4585`) if class-level cohesion is desired.
7. Run: `python -m pytest scripts/tests/test_fsm_executor.py -v -k "rate_limit"`

### Wiring Phase (added by `/ll:wire-issue`)

_These ordering constraints were identified by wiring analysis:_

8. **Sequence gate**: ENH-1147 has already closed (Already-Fixed, 2026-04-17 commit `8c001a1a`). No further sequencing required; the full suite (`python -m pytest scripts/tests/`) should pass after this issue's cadence test is added.
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
- ~~ENH-1144 is the sole hard blocker~~ — **Resolved 2026-04-17**: ENH-1144 landed; `RATE_LIMIT_WAITING_EVENT`, `_interruptible_sleep(on_heartbeat=)`, and package-level exports are all in place.
- ~~ENH-1147 should also merge~~ — **Resolved 2026-04-17**: ENH-1147 closed (Already-Fixed).
- **Remaining scope has shrunk**: Step 3 (fake_sleep signatures) is already done; Steps 5/6 (package-import tests) are already satisfied at `:4505-4515`. The only net-new work is **Step 4** — adding `TestRateLimitHeartbeat` with the cadence test `test_rate_limit_waiting_events_emitted_at_cadence`.

## Session Log
- `/ll:ready-issue` - 2026-04-17T14:20:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024ac8a1-d9a1-4dc5-9242-769d3acfac30.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:26:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5c96713-3899-4dcf-98ee-038f7e93041a.jsonl`
- `/ll:wire-issue` - 2026-04-17T08:23:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43715745-a98d-450d-b9e5-d3f6adb74cdf.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:17:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c02a7ed-1490-42fb-8832-5cffd4e1b2d8.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/714a7073-85c4-4a11-87ff-d55b6cd3eeba.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43715745-a98d-450d-b9e5-d3f6adb74cdf.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9c07c85-7a12-40a0-9e1f-d2073d5d2025.jsonl`

---

## Status
- [x] Closed

## Resolution

**Completed**: 2026-04-17
**Commit**: (see git log for ENH-1148)

Added `TestRateLimitHeartbeat` class with `test_rate_limit_waiting_events_emitted_at_cadence` to `scripts/tests/test_fsm_executor.py`, inserted between `TestRateLimitTwoTier` and `TestRateLimitCircuitIntegration`. The cadence test exercises `_handle_rate_limit`'s long-wait tier end-to-end with a patched `_RATE_LIMIT_HEARTBEAT_INTERVAL` (0.01s) and sub-second ladder (0.3s), then asserts that emitted `rate_limit_waiting` events carry the six-key payload contract: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`.

**Design note**: the issue's spec-style pseudocode patched `little_loops.fsm.executor.time.time` with a capped-index array. That approach was rejected because the module-level patch leaks through to `persistence._now_ms` (called multiple times per run), making the fixed-length array fragile against unrelated call-count shifts. The chosen pattern mirrors the proven `test_on_heartbeat_called_during_long_wait` at `:4517-4538` — tiny heartbeat interval + sub-second real sleep — which is robust and still deterministic on the observable contract (event emitted with payload keys).

**Steps skipped (already satisfied)**:
- Step 3 (`fake_sleep` signature updates) — signatures already accept `on_heartbeat=None` at `:4912/:4938/:4962`, landed alongside ENH-1144.
- Steps 5/6 (package-import tests) — already present at `:4505-4515` in `TestRateLimitRetries`. Went with option (a) from the Expected Behavior section (treat as satisfied, skip duplication).

**Verification**:
- `python -m pytest scripts/tests/test_fsm_executor.py::TestRateLimitHeartbeat -v` → 1 passed
- `python -m pytest scripts/tests/test_fsm_executor.py -v -k rate_limit` → 14 passed
- `python -m pytest scripts/tests/` → 4933 passed, 5 skipped
- `ruff check scripts/` → All checks passed
- `python -m mypy scripts/little_loops/` → 1 pre-existing error (`wcwidth` stub in `cli/loop/layout.py:15`) unrelated to this change.

## Session Log
- `/ll:manage-issue` - 2026-04-17 - (current session)
