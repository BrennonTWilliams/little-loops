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
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_loops.parent)
            assert manager.acquire("loop1", ["src/"])
            assert not manager.acquire("loop2", ["src/api/"])  # Child conflicts
        finally:
            os.chdir(original_cwd)

    def test_acquire_conflict_child_scope(self, manager: LockManager, tmp_loops: Path) -> None:
        """Child scope conflicts with parent."""
        (tmp_loops.parent / "src" / "api").mkdir(parents=True)
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_loops.parent)
            assert manager.acquire("loop1", ["src/api/"])
            assert not manager.acquire("loop2", ["src/"])  # Parent conflicts
        finally:
            os.chdir(original_cwd)

    def test_acquire_no_conflict_sibling_scopes(
        self, manager: LockManager, tmp_loops: Path
    ) -> None:
        """Sibling scopes don't conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_loops.parent)
            assert manager.acquire("loop1", ["src/"])
            assert manager.acquire("loop2", ["tests/"])  # No overlap
        finally:
            os.chdir(original_cwd)

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

    def test_find_conflict_none_when_no_conflict(
        self, manager: LockManager, tmp_loops: Path
    ) -> None:
        """find_conflict returns None when no conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_loops.parent)
            manager.acquire("blocker", ["src/"])
            conflict = manager.find_conflict(["tests/"])
            assert conflict is None
        finally:
            os.chdir(original_cwd)

    def test_list_locks(self, manager: LockManager) -> None:
        """list_locks returns all active locks."""
        manager.acquire("loop1", ["src/"])
        manager.acquire("loop2", ["tests/"])

        locks = manager.list_locks()
        names = {lock.loop_name for lock in locks}
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


class TestLockManagerRaceConditions:
    """Tests for race condition fixes (BUG-423)."""

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

    def test_release_after_file_already_deleted(
        self, manager: LockManager, tmp_loops: Path
    ) -> None:
        """release() doesn't raise when lock file already deleted (BUG-423)."""
        manager.acquire("test", ["src/"])
        lock_file = tmp_loops / ".running" / "test.lock"
        assert lock_file.exists()

        # Simulate another process deleting the lock file
        lock_file.unlink()

        # release() should not raise FileNotFoundError
        manager.release("test")

    def test_find_conflict_stale_lock_already_deleted(
        self, manager: LockManager, tmp_loops: Path
    ) -> None:
        """find_conflict() handles stale lock deleted by another process (BUG-423)."""
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

        # Delete the file before find_conflict processes it
        lock_file.unlink()

        # Should not raise, should return None
        assert manager.find_conflict(["src/"]) is None

    def test_list_locks_stale_lock_already_deleted(
        self, manager: LockManager, tmp_loops: Path
    ) -> None:
        """list_locks() handles stale lock deleted by another process (BUG-423)."""
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

        # Delete the file before list_locks processes it
        lock_file.unlink()

        # Should not raise, should return empty list
        assert manager.list_locks() == []


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

    def test_scopes_overlap_any_match(self, manager: LockManager, tmp_path: Path) -> None:
        """Scopes overlap if any path pair overlaps."""
        src = tmp_path / "src"
        tests = tmp_path / "tests"
        docs = tmp_path / "docs"
        src.mkdir()
        tests.mkdir()
        docs.mkdir()

        # One overlap is enough
        assert manager._scopes_overlap([str(src), str(docs)], [str(tests), str(src)])

    def test_scopes_no_overlap_all_disjoint(self, manager: LockManager, tmp_path: Path) -> None:
        """Scopes don't overlap if all paths are disjoint."""
        src = tmp_path / "src"
        tests = tmp_path / "tests"
        docs = tmp_path / "docs"
        build = tmp_path / "build"
        src.mkdir()
        tests.mkdir()
        docs.mkdir()
        build.mkdir()

        assert not manager._scopes_overlap([str(src), str(docs)], [str(tests), str(build)])
