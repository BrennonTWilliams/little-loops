---
id: ENH-1136
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
parent: ENH-1134
related: [ENH-1134, ENH-1132]
size: Medium
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1136: 429 Resilience — `rate_limit_circuit.py` Module + Unit Tests

## Summary

Create `scripts/little_loops/fsm/rate_limit_circuit.py` with the `RateLimitCircuit` class and its dedicated unit test file `scripts/tests/test_rate_limit_circuit.py`. This is a self-contained module with no executor dependencies.

## Parent Issue

Decomposed from ENH-1134: 429 Resilience — Shared Circuit Breaker Module

## Expected Behavior

### New module: `scripts/little_loops/fsm/rate_limit_circuit.py`

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

**File locking**: use `fcntl.flock(fd, fcntl.LOCK_EX)` inside a `with open(...)` block — model on `concurrency.py:98-141` (`LockManager.acquire`). Only stdlib; no `filelock`/`portalocker`.

**Atomic write**: `tempfile.mkstemp` + `os.replace` — model on `persistence.py:229-236`.

**Directory creation**: `Path(circuit_breaker_path).parent.mkdir(parents=True, exist_ok=True)` on first write (`.loops/tmp/` does not pre-exist).

**Stale detection**: if `last_seen` is more than 1h ago, `is_stale()` returns `True` and `get_estimated_recovery()` returns `None`.

**429-detection gate**: do NOT duplicate patterns from `classify_failure()` at `scripts/little_loops/issue_lifecycle.py:47` (quota_patterns checked at line 63; matches return `(FailureType.TRANSIENT, ...)` at line 75). This module only handles the backoff-write side; detection stays in the executor.

Constructor receives an absolute path (e.g. `tmp_path / ".loops/tmp/rate-limit-circuit.json"`). The default path source-of-truth is `RateLimitsConfig.circuit_breaker_path` at `scripts/little_loops/config/automation.py:112-146` (default `.loops/tmp/rate-limit-circuit.json`). The circuit module itself accepts the path via constructor injection — it does not import config.

## Integration Map

### Files to Create

- `scripts/little_loops/fsm/rate_limit_circuit.py` (NEW) — `RateLimitCircuit` class
- `scripts/tests/test_rate_limit_circuit.py` (NEW)

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — add `from little_loops.fsm.rate_limit_circuit import RateLimitCircuit` import block, append `"RateLimitCircuit"` to `__all__`, add docstring entry under a `# Circuit Breaker` comment (mirrors the pattern used for other FSM public classes in this file)

### Dependent Files (Future Consumers)

- `scripts/little_loops/fsm/executor.py` — primary consumer per sibling issue ENH-1137 (circuit-breaker ↔ executor integration). This issue does NOT wire the executor; that is ENH-1137's scope.
- `scripts/little_loops/config/automation.py:112-146` — `RateLimitsConfig` already owns `circuit_breaker_enabled` and `circuit_breaker_path` defaults (added by completed ENH-1132). No changes required here.

### Similar Patterns to Model After

- `scripts/little_loops/fsm/concurrency.py:98-141` — `LockManager.acquire()` uses `with open(path, "w")` + `fcntl.flock(fd, fcntl.LOCK_EX)` (no explicit try/finally — `with` block releases lock on close)
- `scripts/little_loops/fsm/persistence.py:229-236` — atomic write: `tempfile.mkstemp(dir=self.state_file.parent, suffix=".tmp")` + `os.fdopen(tmp_fd, "w")` + `os.replace(tmp_path, ...)` inside try/except that `os.unlink`s tmp on failure and re-raises
- `scripts/little_loops/fsm/persistence.py:64-187` — canonical `@dataclass` + `to_dict()` / `from_dict()` pattern for JSON state; falsy-omit in `to_dict`, `.get()` with defaults in `from_dict`
- `scripts/little_loops/fsm/persistence.py:190-259` — `StatePersistence` class shape: path in `__init__`, dedicated `initialize()` for `mkdir(parents=True, exist_ok=True)`, `.exists()` guard on all reads, `json.JSONDecodeError` → return `None` (treat corrupted file as absent)
- `scripts/little_loops/fsm/executor.py:918-926` — `time.time()` epoch-float idiom for `first_seen_at` / recovery timestamps
- `scripts/tests/test_fsm_persistence.py:140-143` — fixture: `tmp_path / ".loops"`; lines 144-219 — test class structure (`TestStatePersistence`) and test method naming idiom
- `scripts/tests/test_git_lock.py:421-460` — `threading.Event` × 3 + `threading.Thread` × 2 + shared `list` for ordering assertion

### Typing Conventions

- Use `float | None` (PEP 604), NOT `Optional[float]` — `Optional` is not used in `scripts/little_loops/fsm/`
- All fsm modules begin with `from __future__ import annotations`
- Standard imports for this module: `json`, `os`, `tempfile`, `time`, `fcntl`, `logging`, `from pathlib import Path`, `from typing import Any`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3660-3672` — "Submodule Overview" table lists every `little_loops.fsm.*` module by name; add row `| \`little_loops.fsm.rate_limit_circuit\` | Shared circuit-breaker state file for cross-worktree 429 coordination |`

### Tests

- `scripts/tests/test_rate_limit_circuit.py` (NEW):
  - `test_record_creates_file` — first write creates `.loops/tmp/` directory and JSON file
  - `test_record_updates_existing` — successive records increment `attempts`, advance `estimated_recovery_at`
  - `test_stale_detection` — entry with `last_seen` > 1h ago returns `is_stale() == True`
  - `test_get_estimated_recovery_stale_returns_none` — stale entry returns `None`
  - `test_concurrent_access` — use `threading.Thread` + `threading.Event` (model on `test_git_lock.py:421-460`)
  - `test_atomic_write_crash_safety` — file content is never partially written
  - `test_clear_removes_file` — `clear()` removes JSON file; subsequent `get_estimated_recovery()` returns `None`

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Create `scripts/little_loops/fsm/rate_limit_circuit.py` with `RateLimitCircuit` class (primary deliverable)
2. Create `scripts/tests/test_rate_limit_circuit.py` with all 7 unit tests
3. Update `scripts/little_loops/fsm/__init__.py` — add import block, `__all__` entry, and docstring row for `RateLimitCircuit`
4. Update `docs/reference/API.md:3660-3672` — add `little_loops.fsm.rate_limit_circuit` row to Submodule Overview table

## Acceptance Criteria

- `rate_limit_circuit.py` exists with `RateLimitCircuit` class
- File locking uses only `fcntl.flock` (no third-party libs)
- Atomic write uses `mkstemp + os.replace`
- `.loops/tmp/` created on demand; no error if already exists
- `is_stale()` returns `True` for `last_seen` > 1h ago; `get_estimated_recovery()` returns `None` when stale
- All 7 unit tests pass using `tmp_path` fixture

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T05:19:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38cbbcb1-d247-49c4-847a-b37757a19e54.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3303c4-deb8-40c5-9253-5f167d6eee83.jsonl`
- `/ll:wire-issue` - 2026-04-17T05:12:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d83e882e-5419-4470-b2e5-3b9e7be5f775.jsonl`
- `/ll:refine-issue` - 2026-04-17T05:07:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44aeae3a-978e-42e3-bf20-03a0ecee55bb.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81193e52-67e2-461f-8b12-656dced49eb5.jsonl`
- `/ll:manage-issue` - 2026-04-17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00032768-5efc-466a-aad1-02f0fb698fb3.jsonl`

---

## Resolution
- Created `scripts/little_loops/fsm/rate_limit_circuit.py` with `RateLimitCircuit` class (record/get/is_stale/clear) backed by an atomic `mkstemp + os.replace` write guarded by `fcntl.flock` on a sidecar `.lock` file. `estimated_recovery_at` advances monotonically across concurrent observers; stale entries (>1h) gate `get_estimated_recovery()` to `None`.
- Added 9 unit tests in `scripts/tests/test_rate_limit_circuit.py` (create, update, stale, stale-returns-None, absent-returns-None, concurrent writers, atomic-read-during-write crash safety, clear removes file, clear on missing is no-op).
- Wired `RateLimitCircuit` export into `scripts/little_loops/fsm/__init__.py` (`__all__` + `# Circuit Breaker` docstring section).
- Added `little_loops.fsm.rate_limit_circuit` row to the Submodule Overview table in `docs/reference/API.md`.

## Status
- [x] Completed — 2026-04-17
