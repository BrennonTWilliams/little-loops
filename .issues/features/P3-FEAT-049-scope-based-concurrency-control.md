# FEAT-049: Scope-Based Concurrency Control

## Summary

Implement scope-based locking to prevent concurrent loops from conflicting when they operate on the same files or directories.

## Priority

P3 - Safety feature for parallel execution

## Dependencies

- FEAT-046: State Persistence and Events
- FEAT-047: ll-loop CLI Tool

## Blocked By

- FEAT-046, FEAT-047

## Description

When multiple loops run concurrently, they should not interfere with each other. Scope-based concurrency control:

1. **Scope Declaration** - Loops declare which paths they operate on
2. **Lock Management** - Running loops acquire locks on their scopes
3. **Conflict Detection** - New loops check for overlapping scopes
4. **Queue Mode** - Optionally wait for conflicting loops to finish

### Scope Rules

| Declaration | Behavior |
|-------------|----------|
| Explicit paths | Loop claims those paths |
| No scope | Treated as `["."]` (whole project) |

| Scenario | Behavior |
|----------|----------|
| No other loop running | Start immediately |
| Non-overlapping scopes | Start immediately (parallel OK) |
| Overlapping scopes | Queue or fail |

### Files to Create/Modify

```
scripts/little_loops/fsm/
├── concurrency.py    # Lock management
└── executor.py       # Integrate locking
```

## Technical Details

### Lock File Format

Locks are stored in `.loops/.running/<name>.lock`:

```json
{
  "loop_name": "fix-types",
  "scope": ["src/", "tests/"],
  "pid": 12345,
  "started_at": "2024-01-15T10:30:00Z"
}
```

### Implementation

```python
# concurrency.py
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import fcntl

@dataclass
class ScopeLock:
    loop_name: str
    scope: list[str]
    pid: int
    started_at: str


class LockManager:
    """Manage scope-based locks for concurrent loop execution."""

    def __init__(self, loops_dir: Path = Path(".loops")):
        self.running_dir = loops_dir / ".running"
        self.running_dir.mkdir(parents=True, exist_ok=True)

    def acquire(self, loop_name: str, scope: list[str]) -> bool:
        """
        Attempt to acquire lock for the given scope.
        Returns True if lock acquired, False if conflict.
        """
        # Normalize scope
        if not scope:
            scope = ["."]
        scope = [self._normalize_path(p) for p in scope]

        # Check for conflicts
        conflict = self._find_conflict(scope)
        if conflict:
            return False

        # Create lock file
        lock_file = self.running_dir / f"{loop_name}.lock"
        lock = ScopeLock(
            loop_name=loop_name,
            scope=scope,
            pid=os.getpid(),
            started_at=_iso_now(),
        )

        with open(lock_file, "w") as f:
            # Use file locking for atomicity
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(lock.__dict__, f)
            fcntl.flock(f, fcntl.LOCK_UN)

        return True

    def release(self, loop_name: str):
        """Release lock for a loop."""
        lock_file = self.running_dir / f"{loop_name}.lock"
        if lock_file.exists():
            lock_file.unlink()

    def _find_conflict(self, scope: list[str]) -> Optional[ScopeLock]:
        """Find any running loop with overlapping scope."""
        for lock_file in self.running_dir.glob("*.lock"):
            try:
                with open(lock_file) as f:
                    data = json.load(f)
                lock = ScopeLock(**data)

                # Check if process is still alive
                if not self._process_alive(lock.pid):
                    # Stale lock, remove it
                    lock_file.unlink()
                    continue

                # Check for overlap
                if self._scopes_overlap(scope, lock.scope):
                    return lock

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                continue

        return None

    def _scopes_overlap(self, scope1: list[str], scope2: list[str]) -> bool:
        """Check if two scopes have any overlapping paths."""
        for p1 in scope1:
            for p2 in scope2:
                if self._paths_overlap(p1, p2):
                    return True
        return False

    def _paths_overlap(self, path1: str, path2: str) -> bool:
        """
        Check if two paths overlap.
        Overlap means one is a prefix of the other or they're the same.
        """
        p1 = Path(path1).resolve()
        p2 = Path(path2).resolve()

        # Same path
        if p1 == p2:
            return True

        # One is parent of other
        try:
            p1.relative_to(p2)
            return True
        except ValueError:
            pass

        try:
            p2.relative_to(p1)
            return True
        except ValueError:
            pass

        return False

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent comparison."""
        return str(Path(path).resolve())

    def _process_alive(self, pid: int) -> bool:
        """Check if process is still running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def list_locks(self) -> list[ScopeLock]:
        """List all active locks."""
        locks = []
        for lock_file in self.running_dir.glob("*.lock"):
            try:
                with open(lock_file) as f:
                    data = json.load(f)
                lock = ScopeLock(**data)
                if self._process_alive(lock.pid):
                    locks.append(lock)
                else:
                    lock_file.unlink()
            except (json.JSONDecodeError, KeyError):
                continue
        return locks

    def wait_for_scope(self, scope: list[str], timeout: int = 300) -> bool:
        """
        Wait until scope is available.
        Returns True if acquired, False if timeout.
        """
        import time
        start = time.time()

        while time.time() - start < timeout:
            conflict = self._find_conflict(scope)
            if conflict is None:
                return True
            time.sleep(1)

        return False


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

### Integration with Executor

```python
# In executor.py or cli
class LockedExecutor:
    """FSM Executor with scope locking."""

    def __init__(self, fsm: FSMLoop, queue: bool = False, **kwargs):
        self.fsm = fsm
        self.queue = queue
        self.lock_manager = LockManager()
        self.executor = PersistentExecutor(fsm, **kwargs)

    def run(self) -> ExecutionResult:
        """Run with scope locking."""
        scope = self.fsm.scope or ["."]

        # Try to acquire lock
        if not self.lock_manager.acquire(self.fsm.name, scope):
            if self.queue:
                print(f"Waiting for conflicting loop to finish...")
                if not self.lock_manager.wait_for_scope(scope):
                    raise RuntimeError("Timeout waiting for scope")
                self.lock_manager.acquire(self.fsm.name, scope)
            else:
                conflict = self.lock_manager._find_conflict(scope)
                raise RuntimeError(
                    f"Scope conflict with running loop: {conflict.loop_name}"
                )

        try:
            return self.executor.run()
        finally:
            self.lock_manager.release(self.fsm.name)
```

### CLI Integration

```bash
# Fail on conflict (default)
ll-loop fix-types
# Error: Scope conflict with running loop: lint-cycle

# Wait for conflicting loop
ll-loop fix-types --queue
# Waiting for conflicting loop to finish...
# [continues when available]
```

### Example Scope Declarations

```yaml
# Operates only on API code
name: "fix-api-types"
scope:
  - "src/api/"
  - "tests/api/"
states:
  # ...

# Operates on entire project (default)
name: "full-lint-check"
# No scope = ["."]
states:
  # ...
```

## Acceptance Criteria

- [ ] `LockManager.acquire()` creates lock file with scope and PID
- [ ] `LockManager.release()` removes lock file
- [ ] `_find_conflict()` detects overlapping scopes
- [ ] `_paths_overlap()` handles: same path, parent/child, siblings (no overlap)
- [ ] Stale locks (dead PID) are automatically cleaned up
- [ ] `--queue` flag waits for conflicting loops
- [ ] No scope defaults to `["."]` (whole project)
- [ ] Non-overlapping scopes allow parallel execution
- [ ] Lock released on normal completion
- [ ] Lock released on error/interrupt

## Testing Requirements

```python
# tests/unit/test_concurrency.py
class TestLockManager:
    def test_acquire_release(self, tmp_path):
        """Basic acquire/release cycle."""
        manager = LockManager(tmp_path)
        assert manager.acquire("test", ["src/"])
        assert (tmp_path / ".running" / "test.lock").exists()
        manager.release("test")
        assert not (tmp_path / ".running" / "test.lock").exists()

    def test_conflict_detection(self, tmp_path):
        """Overlapping scopes detected."""
        manager = LockManager(tmp_path)
        manager.acquire("loop1", ["src/"])

        # Same scope conflicts
        assert not manager.acquire("loop2", ["src/"])

        # Parent scope conflicts
        assert not manager.acquire("loop3", ["."])

        # Child scope conflicts
        assert not manager.acquire("loop4", ["src/api/"])

    def test_non_overlapping_scopes(self, tmp_path):
        """Non-overlapping scopes allowed."""
        manager = LockManager(tmp_path)
        assert manager.acquire("loop1", ["src/"])
        assert manager.acquire("loop2", ["tests/"])  # No overlap

    def test_stale_lock_cleanup(self, tmp_path):
        """Stale locks from dead processes cleaned up."""
        manager = LockManager(tmp_path)

        # Create lock with fake dead PID
        lock_file = tmp_path / ".running" / "stale.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(json.dumps({
            "loop_name": "stale",
            "scope": ["src/"],
            "pid": 99999999,  # Non-existent PID
            "started_at": "2024-01-01T00:00:00Z"
        }))

        # Should not conflict (stale lock removed)
        assert manager.acquire("new", ["src/"])

    def test_wait_for_scope(self, tmp_path):
        """Queue mode waits for scope."""
        import threading
        manager = LockManager(tmp_path)
        manager.acquire("blocker", ["src/"])

        # Release in background after delay
        def release_later():
            import time
            time.sleep(0.5)
            manager.release("blocker")

        thread = threading.Thread(target=release_later)
        thread.start()

        # Should wait and succeed
        assert manager.wait_for_scope(["src/"], timeout=2)
        thread.join()
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Concurrency and Locking"
