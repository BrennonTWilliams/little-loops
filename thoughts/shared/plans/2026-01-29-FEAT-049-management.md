# FEAT-049: Scope-Based Concurrency Control - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-049-scope-based-concurrency-control.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The FSM loop system is fully functional with state persistence via `PersistentExecutor` (`persistence.py:207-387`). The `scope` field exists in the `FSMLoop` dataclass (`schema.py:356`) but is not used during execution.

### Key Discoveries
- `FSMLoop.scope: list[str]` field exists but unused (`schema.py:356`)
- State files stored in `.loops/.running/<name>.state.json` (`persistence.py:121-132`)
- CLI entry at `cli.py:730-771` creates `PersistentExecutor` directly
- Path overlap logic exists in `parallel/file_hints.py:100-110` (`_directories_overlap`, `_file_in_directory`)
- Similar context manager pattern in `parallel/git_lock.py:28-79`
- Similar dataclass serialization in `state.py:17-73` and `parallel/types.py:51-132`

## Desired End State

When multiple loops run concurrently:
1. Loops with overlapping scopes cannot run simultaneously
2. Stale locks from dead processes are automatically cleaned up
3. `--queue` flag allows waiting for conflicting loops to finish
4. Lock released on normal completion, error, or interrupt

### How to Verify
- Unit tests for `LockManager` methods
- Integration test: two loops with overlapping scopes fail to start simultaneously
- Integration test: two loops with non-overlapping scopes run in parallel
- Stale lock cleanup when process dies

## What We're NOT Doing

- Not implementing distributed locking (single-machine only)
- Not adding timeout for acquiring locks (only for `--queue` waiting)
- Not modifying FSMLoop schema (scope field already exists)
- Not adding lock visualization to CLI beyond existing `list --running`

## Problem Analysis

Without concurrency control, multiple loops operating on the same files can:
1. Create conflicting file changes
2. Interfere with each other's git operations
3. Corrupt state files or produce inconsistent results

## Solution Approach

1. Create `concurrency.py` with `ScopeLock` dataclass and `LockManager` class
2. Lock files stored in `.loops/.running/<name>.lock`
3. Use file-based locking (fcntl) for atomicity
4. Integrate via CLI layer (wrap `PersistentExecutor.run()`)
5. Add `--queue` flag to `run` subcommand

## Implementation Phases

### Phase 1: Create ScopeLock Dataclass and LockManager

#### Overview
Implement the core locking primitives following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/fsm/concurrency.py`
**Changes**: Create new module with `ScopeLock` and `LockManager`

```python
"""Scope-based concurrency control for FSM loops.

Prevents concurrent loops from conflicting when operating on
the same files or directories through file-based locking.

Public exports:
    ScopeLock: Dataclass representing a scope lock
    LockManager: Manager for acquiring/releasing scope locks
"""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

RUNNING_DIR = ".running"


def _iso_now() -> str:
    """Return current time as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScopeLock:
    """Represents a lock on a set of paths for a running loop.

    Attributes:
        loop_name: Name of the loop holding the lock
        scope: List of paths this loop operates on
        pid: Process ID of the lock holder
        started_at: ISO timestamp when lock was acquired
    """

    loop_name: str
    scope: list[str]
    pid: int
    started_at: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "loop_name": self.loop_name,
            "scope": self.scope,
            "pid": self.pid,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScopeLock:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            loop_name=data["loop_name"],
            scope=data["scope"],
            pid=data["pid"],
            started_at=data["started_at"],
        )


class LockManager:
    """Manage scope-based locks for concurrent loop execution.

    Lock files are stored in .loops/.running/<name>.lock
    and contain JSON with ScopeLock data.
    """

    def __init__(self, loops_dir: Path | None = None) -> None:
        self.loops_dir = loops_dir or Path(".loops")
        self.running_dir = self.loops_dir / RUNNING_DIR

    def acquire(self, loop_name: str, scope: list[str]) -> bool:
        """Attempt to acquire lock for the given scope.

        Args:
            loop_name: Name of the loop to acquire lock for
            scope: List of paths the loop operates on

        Returns:
            True if lock acquired, False if conflict exists
        """
        # Normalize scope - empty means whole project
        if not scope:
            scope = ["."]
        scope = [self._normalize_path(p) for p in scope]

        # Check for conflicts with other running loops
        conflict = self.find_conflict(scope)
        if conflict:
            return False

        # Ensure running directory exists
        self.running_dir.mkdir(parents=True, exist_ok=True)

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
            try:
                json.dump(lock.to_dict(), f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        return True

    def release(self, loop_name: str) -> None:
        """Release lock for a loop.

        Args:
            loop_name: Name of the loop to release lock for
        """
        lock_file = self.running_dir / f"{loop_name}.lock"
        if lock_file.exists():
            lock_file.unlink()

    def find_conflict(self, scope: list[str]) -> ScopeLock | None:
        """Find any running loop with overlapping scope.

        Also cleans up stale locks from dead processes.

        Args:
            scope: Scope to check for conflicts

        Returns:
            ScopeLock of conflicting loop, or None if no conflict
        """
        if not self.running_dir.exists():
            return None

        for lock_file in self.running_dir.glob("*.lock"):
            try:
                with open(lock_file) as f:
                    data = json.load(f)
                lock = ScopeLock.from_dict(data)

                # Check if process is still alive
                if not self._process_alive(lock.pid):
                    # Stale lock, remove it
                    lock_file.unlink()
                    continue

                # Check for overlap
                if self._scopes_overlap(scope, lock.scope):
                    return lock

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                # Malformed or deleted lock file, skip
                continue

        return None

    def list_locks(self) -> list[ScopeLock]:
        """List all active locks.

        Cleans up stale locks as a side effect.

        Returns:
            List of active ScopeLock objects
        """
        locks = []
        if not self.running_dir.exists():
            return locks

        for lock_file in self.running_dir.glob("*.lock"):
            try:
                with open(lock_file) as f:
                    data = json.load(f)
                lock = ScopeLock.from_dict(data)

                if self._process_alive(lock.pid):
                    locks.append(lock)
                else:
                    # Stale lock, remove it
                    lock_file.unlink()
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                continue

        return locks

    def wait_for_scope(self, scope: list[str], timeout: int = 300) -> bool:
        """Wait until scope is available.

        Args:
            scope: Scope to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            True if scope became available, False if timeout
        """
        import time

        start = time.time()
        while time.time() - start < timeout:
            conflict = self.find_conflict(scope)
            if conflict is None:
                return True
            time.sleep(1)

        return False

    def _scopes_overlap(self, scope1: list[str], scope2: list[str]) -> bool:
        """Check if two scopes have any overlapping paths."""
        for p1 in scope1:
            for p2 in scope2:
                if self._paths_overlap(p1, p2):
                    return True
        return False

    def _paths_overlap(self, path1: str, path2: str) -> bool:
        """Check if two paths overlap (same, or one contains the other)."""
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_concurrency.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/concurrency.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/concurrency.py`

---

### Phase 2: Update FSM Module Exports

#### Overview
Export new classes from the fsm module.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add imports and exports for `ScopeLock` and `LockManager`

Add after line 97 (after persistence imports):
```python
from little_loops.fsm.concurrency import (
    LockManager,
    ScopeLock,
)
```

Add to `__all__` list (alphabetically):
```python
    "LockManager",
    "ScopeLock",
```

#### Success Criteria

**Automated Verification**:
- [ ] Import test: `python -c "from little_loops.fsm import LockManager, ScopeLock"`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/__init__.py`

---

### Phase 3: Integrate with CLI

#### Overview
Add `--queue` flag and wrap execution with lock management.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `--queue` flag and lock management to run command

1. Add import at top with other fsm imports:
```python
from little_loops.fsm.concurrency import LockManager
```

2. Add `--queue` flag to run_parser (around line 545):
```python
    run_parser.add_argument(
        "--queue", action="store_true", help="Wait for conflicting loops to finish"
    )
```

3. Modify `cmd_run()` function (around line 730-771) to wrap with lock management:
```python
    def cmd_run(loop_name: str) -> int:
        """Run a loop."""
        # ... existing code to resolve and load fsm ...

        # Scope-based locking
        lock_manager = LockManager()
        scope = fsm.scope or ["."]

        if not lock_manager.acquire(fsm.name, scope):
            conflict = lock_manager.find_conflict(scope)
            if args.queue:
                logger.info(f"Waiting for conflicting loop '{conflict.loop_name}' to finish...")
                if not lock_manager.wait_for_scope(scope, timeout=3600):
                    logger.error("Timeout waiting for scope to become available")
                    return 1
                lock_manager.acquire(fsm.name, scope)
            else:
                logger.error(f"Scope conflict with running loop: {conflict.loop_name}")
                logger.info(f"  Conflicting scope: {conflict.scope}")
                logger.info("  Use --queue to wait for it to finish")
                return 1

        try:
            executor = PersistentExecutor(fsm)
            return run_foreground(executor, fsm)
        finally:
            lock_manager.release(fsm.name)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] Help shows flag: `python -m little_loops.cli loop run --help | grep queue`

**Manual Verification**:
- [ ] Run two loops with overlapping scopes: second fails with conflict message
- [ ] Run with `--queue`: second loop waits for first

---

### Phase 4: Write Unit Tests

#### Overview
Comprehensive test coverage for `LockManager`.

#### Changes Required

**File**: `scripts/tests/test_concurrency.py`
**Changes**: Create new test file

```python
"""Tests for scope-based concurrency control."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from little_loops.fsm.concurrency import LockManager, ScopeLock


class TestScopeLock:
    """Tests for ScopeLock dataclass."""

    def test_to_dict(self) -> None:
        """to_dict produces expected structure."""
        lock = ScopeLock(
            loop_name="test",
            scope=["src/"],
            pid=12345,
            started_at="2024-01-15T10:30:00Z",
        )
        d = lock.to_dict()
        assert d["loop_name"] == "test"
        assert d["scope"] == ["src/"]
        assert d["pid"] == 12345
        assert d["started_at"] == "2024-01-15T10:30:00Z"

    def test_from_dict(self) -> None:
        """from_dict reconstructs ScopeLock."""
        data = {
            "loop_name": "test",
            "scope": ["src/", "tests/"],
            "pid": 12345,
            "started_at": "2024-01-15T10:30:00Z",
        }
        lock = ScopeLock.from_dict(data)
        assert lock.loop_name == "test"
        assert lock.scope == ["src/", "tests/"]
        assert lock.pid == 12345

    def test_roundtrip(self) -> None:
        """to_dict and from_dict are inverse operations."""
        original = ScopeLock(
            loop_name="roundtrip",
            scope=["a/", "b/"],
            pid=999,
            started_at="2024-01-01T00:00:00Z",
        )
        restored = ScopeLock.from_dict(original.to_dict())
        assert restored == original


class TestLockManager:
    """Tests for LockManager."""

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    @pytest.fixture
    def manager(self, tmp_loops: Path) -> LockManager:
        """Create LockManager with temp directory."""
        return LockManager(tmp_loops)

    def test_acquire_creates_lock_file(self, manager: LockManager, tmp_loops: Path) -> None:
        """acquire() creates lock file."""
        assert manager.acquire("test", ["src/"])
        lock_file = tmp_loops / ".running" / "test.lock"
        assert lock_file.exists()

    def test_release_removes_lock_file(self, manager: LockManager, tmp_loops: Path) -> None:
        """release() removes lock file."""
        manager.acquire("test", ["src/"])
        lock_file = tmp_loops / ".running" / "test.lock"
        assert lock_file.exists()

        manager.release("test")
        assert not lock_file.exists()

    def test_release_nonexistent_is_safe(self, manager: LockManager) -> None:
        """release() on non-existent lock doesn't raise."""
        manager.release("nonexistent")  # Should not raise

    def test_acquire_conflict_same_scope(self, manager: LockManager) -> None:
        """Same scope conflicts."""
        assert manager.acquire("loop1", ["src/"])
        assert not manager.acquire("loop2", ["src/"])

    def test_acquire_conflict_parent_scope(self, manager: LockManager, tmp_loops: Path) -> None:
        """Parent scope conflicts with child."""
        # Create src directory for path resolution
        (tmp_loops.parent / "src" / "api").mkdir(parents=True)
        os.chdir(tmp_loops.parent)

        assert manager.acquire("loop1", ["src/"])
        assert not manager.acquire("loop2", ["src/api/"])  # Child conflicts

    def test_acquire_conflict_child_scope(self, manager: LockManager, tmp_loops: Path) -> None:
        """Child scope conflicts with parent."""
        (tmp_loops.parent / "src" / "api").mkdir(parents=True)
        os.chdir(tmp_loops.parent)

        assert manager.acquire("loop1", ["src/api/"])
        assert not manager.acquire("loop2", ["src/"])  # Parent conflicts

    def test_acquire_no_conflict_sibling_scopes(self, manager: LockManager, tmp_loops: Path) -> None:
        """Sibling scopes don't conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        os.chdir(tmp_loops.parent)

        assert manager.acquire("loop1", ["src/"])
        assert manager.acquire("loop2", ["tests/"])  # No overlap

    def test_empty_scope_defaults_to_project(self, manager: LockManager) -> None:
        """Empty scope treated as ['.']."""
        assert manager.acquire("loop1", [])
        assert not manager.acquire("loop2", [])  # Both default to "."

    def test_stale_lock_cleanup(self, manager: LockManager, tmp_loops: Path) -> None:
        """Stale locks from dead processes cleaned up."""
        # Create lock with fake dead PID
        running_dir = tmp_loops / ".running"
        running_dir.mkdir()
        lock_file = running_dir / "stale.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "loop_name": "stale",
                    "scope": ["src/"],
                    "pid": 99999999,  # Non-existent PID
                    "started_at": "2024-01-01T00:00:00Z",
                }
            )
        )

        # Should not conflict (stale lock removed)
        assert manager.acquire("new", ["src/"])
        assert not lock_file.exists()  # Stale lock was cleaned

    def test_find_conflict_returns_lock(self, manager: LockManager) -> None:
        """find_conflict returns conflicting ScopeLock."""
        manager.acquire("blocker", ["src/"])
        conflict = manager.find_conflict(["src/"])
        assert conflict is not None
        assert conflict.loop_name == "blocker"

    def test_find_conflict_none_when_no_conflict(self, manager: LockManager, tmp_loops: Path) -> None:
        """find_conflict returns None when no conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        os.chdir(tmp_loops.parent)

        manager.acquire("blocker", ["src/"])
        conflict = manager.find_conflict(["tests/"])
        assert conflict is None

    def test_list_locks(self, manager: LockManager) -> None:
        """list_locks returns all active locks."""
        manager.acquire("loop1", ["src/"])
        manager.acquire("loop2", ["tests/"])

        locks = manager.list_locks()
        names = {l.loop_name for l in locks}
        assert names == {"loop1", "loop2"}

    def test_list_locks_cleans_stale(self, manager: LockManager, tmp_loops: Path) -> None:
        """list_locks cleans stale locks."""
        running_dir = tmp_loops / ".running"
        running_dir.mkdir()
        lock_file = running_dir / "stale.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "loop_name": "stale",
                    "scope": ["src/"],
                    "pid": 99999999,
                    "started_at": "2024-01-01T00:00:00Z",
                }
            )
        )

        locks = manager.list_locks()
        assert len(locks) == 0
        assert not lock_file.exists()


class TestLockManagerWait:
    """Tests for wait_for_scope functionality."""

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    @pytest.fixture
    def manager(self, tmp_loops: Path) -> LockManager:
        """Create LockManager with temp directory."""
        return LockManager(tmp_loops)

    def test_wait_immediate_if_no_conflict(self, manager: LockManager) -> None:
        """wait_for_scope returns immediately if no conflict."""
        start = time.time()
        result = manager.wait_for_scope(["src/"], timeout=10)
        elapsed = time.time() - start

        assert result is True
        assert elapsed < 1  # Should be nearly instant

    def test_wait_timeout(self, manager: LockManager) -> None:
        """wait_for_scope returns False on timeout."""
        manager.acquire("blocker", ["src/"])

        start = time.time()
        result = manager.wait_for_scope(["src/"], timeout=2)
        elapsed = time.time() - start

        assert result is False
        assert 1.5 < elapsed < 3  # Should wait close to timeout

    def test_wait_succeeds_when_released(self, manager: LockManager) -> None:
        """wait_for_scope succeeds when lock is released."""
        manager.acquire("blocker", ["src/"])

        def release_later() -> None:
            time.sleep(0.5)
            manager.release("blocker")

        thread = threading.Thread(target=release_later)
        thread.start()

        result = manager.wait_for_scope(["src/"], timeout=5)
        thread.join()

        assert result is True


class TestPathOverlap:
    """Tests for path overlap detection."""

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    @pytest.fixture
    def manager(self, tmp_loops: Path) -> LockManager:
        """Create LockManager with temp directory."""
        return LockManager(tmp_loops)

    def test_same_path_overlaps(self, manager: LockManager, tmp_path: Path) -> None:
        """Same path overlaps with itself."""
        src = tmp_path / "src"
        src.mkdir()
        assert manager._paths_overlap(str(src), str(src))

    def test_parent_child_overlap(self, manager: LockManager, tmp_path: Path) -> None:
        """Parent and child paths overlap."""
        src = tmp_path / "src"
        api = src / "api"
        api.mkdir(parents=True)

        assert manager._paths_overlap(str(src), str(api))
        assert manager._paths_overlap(str(api), str(src))

    def test_siblings_no_overlap(self, manager: LockManager, tmp_path: Path) -> None:
        """Sibling paths don't overlap."""
        src = tmp_path / "src"
        tests = tmp_path / "tests"
        src.mkdir()
        tests.mkdir()

        assert not manager._paths_overlap(str(src), str(tests))
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_concurrency.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_concurrency.py`

---

### Phase 5: Verify and Complete

#### Overview
Run full verification suite and complete the issue.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Create two test loops with overlapping scopes
- [ ] Verify first runs, second shows conflict error
- [ ] Verify `--queue` makes second wait for first
- [ ] Verify non-overlapping scopes run in parallel

---

## Testing Strategy

### Unit Tests
- `ScopeLock` serialization/deserialization
- `LockManager.acquire()` and `release()` basic operations
- Conflict detection for same/parent/child/sibling scopes
- Stale lock cleanup
- Wait timeout behavior

### Integration Tests
- CLI with `--queue` flag
- Lock file creation and cleanup in actual `.loops/.running/` directory

## References

- Original issue: `.issues/features/P3-FEAT-049-scope-based-concurrency-control.md`
- Similar locking pattern: `scripts/little_loops/parallel/git_lock.py:28-79`
- Similar dataclass pattern: `scripts/little_loops/state.py:17-73`
- Path overlap logic: `scripts/little_loops/parallel/file_hints.py:100-110`
- State persistence pattern: `scripts/little_loops/fsm/persistence.py:111-205`
