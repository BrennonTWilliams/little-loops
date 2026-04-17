# ENH-1136 Management Plan — rate_limit_circuit.py module + tests

## Goal
Create `scripts/little_loops/fsm/rate_limit_circuit.py` with `RateLimitCircuit` class and `scripts/tests/test_rate_limit_circuit.py` (7 tests). Wire module export into `fsm/__init__.py` and add row to `docs/reference/API.md` Submodule Overview.

## Design Decisions

- **Path via constructor injection**: module does not import config; accepts absolute `Path` arg.
- **File lock pattern**: model on `concurrency.py:98-141` — `with open(path, "w") as fd: fcntl.flock(fd, LOCK_EX); ...` within the block; release on close.
  - BUT: `open("w")` truncates. Use `"a+"` or `"r+"` when the file needs reading, then seek/truncate before writing. Open file once with `fcntl.flock` and do read-modify-write atomically.
  - **Final approach**: read without lock (file may not exist / be stale), then for writes, acquire exclusive lock on a `.lock` sidecar file, do `mkstemp` + `os.replace` under the lock. This matches `LockManager.acquire()` which uses a sentinel `.acquire.lock` file.
- **Atomic write**: `tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")` + `os.fdopen` + `os.replace`. Model on `persistence.py:229-236`.
- **Stale threshold**: 1 hour (3600 s) on `last_seen`. Also cap `get_estimated_recovery()` to return `None` when stale.
- **Directory creation**: `self.path.parent.mkdir(parents=True, exist_ok=True)` on every write (cheap and safe). Also used by `initialize()` if we add one; inline on write is simpler for this scope.
- **Estimated recovery update semantics**: each `record_rate_limit(backoff_s)` sets `last_seen=now`, `estimated_recovery_at = now + backoff_s`, increments `attempts`. First call sets `first_seen`. Subsequent calls advance `estimated_recovery_at` only if the new value is later (monotonic extension — multiple workers observing a 429 during the same backoff window shouldn't shrink the window).
- **Clear semantics**: delete the JSON file entirely; `get_estimated_recovery()` treats missing file as `None`.

## File-by-File Changes

### NEW: `scripts/little_loops/fsm/rate_limit_circuit.py`
```python
from __future__ import annotations
import fcntl, json, logging, os, tempfile, time
from pathlib import Path
from typing import Any

STALE_THRESHOLD_SECONDS = 3600.0  # 1h

class RateLimitCircuit:
    def __init__(self, path: Path) -> None: ...
    def record_rate_limit(self, backoff_seconds: float) -> None: ...
    def get_estimated_recovery(self) -> float | None: ...
    def is_stale(self) -> bool: ...
    def clear(self) -> None: ...
    # internal:
    def _read(self) -> dict[str, Any] | None: ...
    def _write_atomic(self, data: dict[str, Any]) -> None: ...
```

Lock strategy: sidecar lock file `<path>.lock` held via `fcntl.LOCK_EX` around the read-modify-write in `record_rate_limit`.

### NEW: `scripts/tests/test_rate_limit_circuit.py`
7 tests per acceptance criteria:
- `test_record_creates_file`
- `test_record_updates_existing` (attempts increments, recovery advances)
- `test_stale_detection`
- `test_get_estimated_recovery_stale_returns_none`
- `test_concurrent_access` (threading.Thread × 2 w/ Events)
- `test_atomic_write_crash_safety` (either absent, or valid JSON — never partial)
- `test_clear_removes_file`

### MODIFY: `scripts/little_loops/fsm/__init__.py`
- Add `from little_loops.fsm.rate_limit_circuit import RateLimitCircuit`
- Add `"RateLimitCircuit"` to `__all__`
- Add docstring entry under a `# Circuit Breaker` comment in the public-exports section

### MODIFY: `docs/reference/API.md`
- Insert new row in Submodule Overview table (before `signal_detector`):
  `| little_loops.fsm.rate_limit_circuit | Shared circuit-breaker state file for cross-worktree 429 coordination |`

## Phase 0: Tests (Red)
Write all 7 tests in `test_rate_limit_circuit.py`. They should fail with ImportError or AttributeError until Phase 3b lands the module.

## Success Criteria

### Automated
- [ ] `python -m pytest scripts/tests/test_rate_limit_circuit.py -v` — 7 pass
- [ ] `python -m pytest scripts/tests/` — full suite passes
- [ ] `ruff check scripts/` clean
- [ ] `python -m mypy scripts/little_loops/` clean

### Manual
- [ ] `RateLimitCircuit` importable from `little_loops.fsm`
- [ ] API.md table includes new row
