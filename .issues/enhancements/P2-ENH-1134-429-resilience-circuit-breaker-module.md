---
id: ENH-1134
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1133, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
---

# ENH-1134: 429 Resilience — Shared Circuit Breaker Module

## Summary

Create `rate_limit_circuit.py`, a new FSM helper that maintains a shared file-locked circuit-breaker record under `.loops/tmp/rate-limit-circuit.json`. Insert a pre-action check in the executor so parallel `ll-parallel` worktrees skip redundant API calls when a rate-limit outage is known. Depends on ENH-1132 (config with `circuit_breaker_path`).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Today, `ll-parallel` worktrees independently discover the same outage and burn quota in parallel — N workers each retrying expensive slash commands during a global rate-limit event multiplies waste and delays recovery. A shared file visible to all processes lets any worker record a detected outage, and all others pre-sleep until the estimated recovery time.

## Expected Behavior

### 1. New module: `rate_limit_circuit.py`

```python
class RateLimitCircuit:
    def record_rate_limit(self, backoff_seconds: float) -> None: ...
    def get_estimated_recovery(self) -> float | None: ...  # epoch timestamp or None if stale/absent
    def is_stale(self) -> bool: ...
    def clear(self) -> None: ...
```

Circuit-breaker JSON structure:
```json
{
  "first_seen": 1713300000.0,
  "last_seen": 1713302000.0,
  "attempts": 5,
  "estimated_recovery_at": 1713305600.0
}
```

**File locking**: use `fcntl.flock(fd, fcntl.LOCK_EX)` inside a `with open(...)` block — model on `concurrency.py:121-141` (`LockManager.acquire`). Only stdlib; no `filelock`/`portalocker`.

**Atomic write**: `tempfile.mkstemp` + `os.replace` — model on `persistence.py:200-207`.

**Directory creation**: `Path(circuit_breaker_path).parent.mkdir(parents=True, exist_ok=True)` on first write (`.loops/tmp/` does not pre-exist as a Python-managed directory).

**Stale detection**: if `last_seen` is more than 1h ago with no recent updates, `is_stale()` returns `True` and `get_estimated_recovery()` returns `None` — the calling code treats stale entries as absent and proceeds normally.

**429-detection gate**: reuse `classify_failure()` from `issue_lifecycle.py:47-75` as the single source of truth for rate-limit pattern matching. Do NOT re-implement the pattern set.

### 2. Pre-action circuit-breaker check in executor

Insert between `executor.py:427` and `428` (after sub-loop dispatch guard, before `action_result = None` at line 449):

```python
if circuit_breaker_enabled and action_type in LLM_ACTION_TYPES:
    recovery = self._circuit.get_estimated_recovery()
    if recovery is not None:
        wait = recovery - time.time()
        if wait > 0:
            self._interruptible_sleep(wait)
```

Skip check for non-LLM action types (e.g. `action_type: shell` without embedded `slash_command`).

`LLM_ACTION_TYPES` = `{"slash_command", "prompt"}` (the set that hits the Claude API).

The `RateLimitCircuit` instance is created once per executor with the configured `circuit_breaker_path`; inject via constructor so tests can redirect to `tmp_path`.

### 3. Record on 429 detection

Inside the existing rate-limit detection block (`executor.py:481-541`), after confirming a 429, call `self._circuit.record_rate_limit(next_backoff_seconds)` to update the shared file.

### 4. Public API export (`fsm/__init__.py`)

Add `RateLimitCircuit` to `fsm/__init__.py` re-exports (alongside `RATE_LIMIT_EXHAUSTED_EVENT`).

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/fsm/rate_limit_circuit.py` (NEW) — `RateLimitCircuit` class
- `scripts/little_loops/fsm/executor.py` — pre-action check (between lines 427-428); `record_rate_limit` call inside detection block; constructor wiring for `_circuit`
- `scripts/little_loops/fsm/__init__.py:87,140` — re-export `RateLimitCircuit`
- `scripts/little_loops/cli/loop/run.py` — pass `circuit_breaker_path` from config to executor constructor
- `scripts/little_loops/cli/loop/testing.py` — `SimulationActionRunner` / `DefaultActionRunner`: use configured `circuit_breaker_path` (not hardcoded) so tests redirect to `tmp_path`

### Depends On

- ENH-1132 — `RateLimitsConfig` with `circuit_breaker_enabled` and `circuit_breaker_path` fields

### Similar Patterns to Model After

- `scripts/little_loops/fsm/concurrency.py:121-141` — `LockManager.acquire()` with `fcntl.flock`
- `scripts/little_loops/fsm/persistence.py:200-207` — atomic write with `mkstemp + os.replace`
- `scripts/little_loops/issue_lifecycle.py:47-75` — `classify_failure()` pattern set
- `.issues/completed/P2-BUG-965-circuit-breaker-bypass-exception-path.md` — prior circuit-breaker lessons

### Tests

- `scripts/tests/test_rate_limit_circuit.py` (NEW):
  - `test_record_creates_file` — first write creates `.loops/tmp/` directory and JSON file
  - `test_record_updates_existing` — successive records increment `attempts`, advance `estimated_recovery_at`
  - `test_stale_detection` — entry with `last_seen` > 1h ago returns `is_stale() == True`
  - `test_get_estimated_recovery_stale_returns_none` — stale entry returns `None`
  - `test_concurrent_access` — use `threading.Thread` + `threading.Event` (model on `test_git_lock.py:395-460`; no `multiprocessing` — no precedent in the suite)
  - `test_atomic_write_crash_safety` — file content is never partially written (simulate interrupted write)
  - `test_clear_removes_file` — `clear()` removes the JSON file; subsequent `get_estimated_recovery()` returns `None`
- `scripts/tests/test_fsm_executor.py` — add tests for pre-action pre-sleep:
  - Circuit breaker active → action delayed by recovery wait
  - Stale circuit breaker → action proceeds immediately
  - Non-LLM action type → pre-check skipped

## Acceptance Criteria

- `rate_limit_circuit.py` exists with `RateLimitCircuit` helper
- File locking uses only `fcntl.flock` (no third-party libs)
- Atomic write uses `mkstemp + os.replace`
- `.loops/tmp/` created on demand; no error if already exists
- 429-detection gate reuses `classify_failure()` (no duplicated pattern set)
- Pre-action check skipped for non-LLM action types
- Pre-action check respects `_shutdown_requested` (Ctrl-C exits quickly)
- `RateLimitCircuit` exported from `fsm/__init__.py`
- Tests pass using `tmp_path` fixture; concurrent-access test uses `threading`

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Status
- [ ] Open
