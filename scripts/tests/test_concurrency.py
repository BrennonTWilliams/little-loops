"""Tests for scope-based concurrency control."""

from __future__ import annotations

import errno
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.fsm.concurrency import LockManager, ScopeLock, resolve_scope


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

    def test_singleton_true_round_trips(self) -> None:
        """singleton=True survives to_dict() -> from_dict() (BUG-2526)."""
        lock = ScopeLock(
            loop_name="autodev",
            scope=[".loops/runs/autodev-x"],
            pid=12345,
            started_at="2026-07-07T00:00:00Z",
            singleton=True,
        )
        d = lock.to_dict()
        assert d.get("singleton") is True
        restored = ScopeLock.from_dict(d)
        assert restored.singleton is True

    def test_singleton_false_omitted_from_dict(self) -> None:
        """singleton=False (default) is omitted from to_dict() (parity with FSMLoop.maintain)."""
        lock = ScopeLock(
            loop_name="autodev",
            scope=[".loops/runs/autodev-x"],
            pid=12345,
            started_at="2026-07-07T00:00:00Z",
        )
        d = lock.to_dict()
        assert "singleton" not in d, (
            f"singleton=False must be omitted from to_dict(); got keys: {sorted(d.keys())}"
        )

    def test_singleton_defaults_false_for_legacy_lock_files(self) -> None:
        """from_dict() of a legacy lock file (no singleton key) defaults to False (migration)."""
        legacy_data = {
            "loop_name": "autodev",
            "scope": [".loops/runs/autodev-x"],
            "pid": 12345,
            "started_at": "2026-07-07T00:00:00Z",
        }
        lock = ScopeLock.from_dict(legacy_data)
        assert lock.singleton is False, (
            "Legacy lock files (no singleton key) must parse as singleton=False"
        )


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

    def test_acquire_conflict_parent_scope(
        self, manager: LockManager, tmp_loops: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parent scope conflicts with child."""
        # Create src directory for path resolution
        (tmp_loops.parent / "src" / "api").mkdir(parents=True)
        monkeypatch.chdir(tmp_loops.parent)
        assert manager.acquire("loop1", ["src/"])
        assert not manager.acquire("loop2", ["src/api/"])  # Child conflicts

    def test_acquire_conflict_child_scope(
        self, manager: LockManager, tmp_loops: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Child scope conflicts with parent."""
        (tmp_loops.parent / "src" / "api").mkdir(parents=True)
        monkeypatch.chdir(tmp_loops.parent)
        assert manager.acquire("loop1", ["src/api/"])
        assert not manager.acquire("loop2", ["src/"])  # Parent conflicts

    def test_acquire_no_conflict_sibling_scopes(
        self, manager: LockManager, tmp_loops: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sibling scopes don't conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        monkeypatch.chdir(tmp_loops.parent)
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

    def test_stale_lock_eperm_treated_as_alive(self, manager: LockManager, tmp_loops: Path) -> None:
        """EPERM on os.kill means process exists — lock must not be cleaned up (BUG-526)."""
        running_dir = tmp_loops / ".running"
        running_dir.mkdir()
        lock_file = running_dir / "privileged.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "loop_name": "privileged",
                    "scope": ["src/"],
                    "pid": 12345,
                    "started_at": "2024-01-01T00:00:00Z",
                }
            )
        )

        # EPERM: process exists but current user cannot signal it
        with patch("os.kill", side_effect=OSError(errno.EPERM, "Operation not permitted")):
            assert not manager.acquire("new", ["src/"])  # Conflict detected
            assert lock_file.exists()  # Lock must NOT be deleted

    def test_stale_lock_esrch_treated_as_dead(self, manager: LockManager, tmp_loops: Path) -> None:
        """ESRCH on os.kill means process is gone — lock should be cleaned up (BUG-526)."""
        running_dir = tmp_loops / ".running"
        running_dir.mkdir()
        lock_file = running_dir / "dead.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "loop_name": "dead",
                    "scope": ["src/"],
                    "pid": 12345,
                    "started_at": "2024-01-01T00:00:00Z",
                }
            )
        )

        # ESRCH: no such process
        with patch("os.kill", side_effect=OSError(errno.ESRCH, "No such process")):
            assert manager.acquire("new", ["src/"])  # Stale lock cleaned, no conflict
            assert not lock_file.exists()  # Lock was deleted

    def test_find_conflict_returns_lock(self, manager: LockManager) -> None:
        """find_conflict returns conflicting ScopeLock."""
        manager.acquire("blocker", ["src/"])
        conflict = manager.find_conflict(["src/"])
        assert conflict is not None
        assert conflict.loop_name == "blocker"

    def test_find_conflict_none_when_no_conflict(
        self, manager: LockManager, tmp_loops: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """find_conflict returns None when no conflict."""
        (tmp_loops.parent / "src").mkdir()
        (tmp_loops.parent / "tests").mkdir()
        monkeypatch.chdir(tmp_loops.parent)
        manager.acquire("blocker", ["src/"])
        conflict = manager.find_conflict(["tests/"])
        assert conflict is None

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

    def test_concurrent_acquire_same_scope_only_one_wins(self, manager: LockManager) -> None:
        """Concurrent acquire() on same scope: exactly one succeeds (BUG-525).

        Two threads race to acquire the same scope simultaneously.  The
        directory-level sentinel lock must ensure exactly one succeeds.
        """
        results: list[bool] = []
        barrier = threading.Barrier(2)

        def try_acquire(name: str) -> None:
            barrier.wait()  # Both threads start at the same instant
            result = manager.acquire(name, ["src/"])
            results.append(result)

        t1 = threading.Thread(target=try_acquire, args=("loop-a",))
        t2 = threading.Thread(target=try_acquire, args=("loop-b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        assert results.count(True) == 1, f"Expected exactly 1 success, got: {results}"
        assert results.count(False) == 1

    def test_n_waiters_all_acquire_with_retry_loop(self, manager: LockManager) -> None:
        """N queued waiters using the wait+retry pattern all eventually acquire (BUG-1281).

        Simulates the post-fix cmd_run retry loop: each thread calls wait_for_scope
        then acquire, looping back on loss until it wins.  All N threads must succeed.
        """
        n = 3
        results: list[str] = []
        results_lock = threading.Lock()

        manager.acquire("holder", ["src/"])

        def waiter(name: str) -> None:
            start = time.time()
            budget = 10.0
            acquired = False
            while time.time() - start < budget:
                remaining = budget - (time.time() - start)
                if not manager.wait_for_scope(["src/"], timeout=remaining):
                    break
                if manager.acquire(name, ["src/"]):
                    acquired = True
                    break
            with results_lock:
                results.append(name if acquired else f"{name}-failed")
            if acquired:
                time.sleep(0.01)
                manager.release(name)

        threads = [threading.Thread(target=waiter, args=(f"loop-{i}",)) for i in range(n)]
        for t in threads:
            t.start()
        time.sleep(0.1)  # let threads enter wait_for_scope before releasing
        manager.release("holder")
        for t in threads:
            t.join(timeout=15)

        assert len(results) == n
        failed = [r for r in results if r.endswith("-failed")]
        assert not failed, f"Some waiters failed to acquire: {failed}"


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


class TestMultiInstanceSameName:
    """Two instances of the same loop name with distinct instance_ids use distinct lock files (ENH-1354)."""

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    def test_distinct_instance_ids_produce_distinct_lock_files(self, tmp_loops: Path) -> None:
        """Two same-name instances with different instance_ids write to distinct lock files."""
        manager = LockManager(tmp_loops)
        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"

        # First instance acquires; second conflicts on scope but uses a distinct lock file
        assert manager.acquire("autodev", ["src/"], instance_id=id1)
        # Release first, then second can acquire — verifies lock files are independently named
        manager.release("autodev", instance_id=id1)
        assert manager.acquire("autodev", ["src/"], instance_id=id2)
        manager.release("autodev", instance_id=id2)

        # Both lock files are gone after release
        lock_file1 = tmp_loops / ".running" / f"{id1}.lock"
        lock_file2 = tmp_loops / ".running" / f"{id2}.lock"
        assert not lock_file1.exists()
        assert not lock_file2.exists()

    def test_concurrent_same_name_non_overlapping_scopes_both_acquire(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent same-name instances on non-overlapping scopes both succeed (ENH-1354)."""
        src_dir = tmp_path / "src"
        lib_dir = tmp_path / "lib"
        src_dir.mkdir()
        lib_dir.mkdir()

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("autodev", scope, instance_id=instance_id)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, ["src/"]))
        t2 = threading.Thread(target=try_acquire, args=(id2, ["lib/"]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 2, (
            f"Both non-overlapping instances should acquire; got: {results}"
        )

    def test_autodev_with_run_dir_scopes_both_acquire_concurrently(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two autodev instances with different run_dir scopes acquire concurrently (FEAT-1789)."""
        run1 = tmp_path / ".loops" / "runs" / "autodev-20240115T103000"
        run2 = tmp_path / ".loops" / "runs" / "autodev-20240115T103001"
        run1.mkdir(parents=True)
        run2.mkdir(parents=True)

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("autodev", scope, instance_id=instance_id)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, [str(run1.relative_to(tmp_path))]))
        t2 = threading.Thread(target=try_acquire, args=(id2, [str(run2.relative_to(tmp_path))]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 2, (
            f"Both instances with different run_dir scopes should acquire; got: {results}"
        )

    def test_autodev_with_dot_scope_still_conflicts(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two autodev instances with ["."] scope still conflict (FEAT-1789 regression guard)."""
        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("autodev", scope, instance_id=instance_id)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, ["."]))
        t2 = threading.Thread(target=try_acquire, args=(id2, ["."]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1, (
            f"Both instances with dot scope should conflict; exactly one should acquire, got: {results}"
        )
        assert results.count(False) == 1, (
            f"Both instances with dot scope should conflict; exactly one should fail, got: {results}"
        )


class TestSingletonLock:
    """BUG-2526: singleton field serializes loop-name conflicts regardless of scope.

    When `singleton: true` is set on a loop YAML, two concurrent instances of that
    loop name must conflict regardless of whether their scopes overlap. This
    closes the autodev implementation-phase race where two `ll-loop run autodev`
    invocations pass LockManager (because their `${context.run_dir}` scopes are
    disjoint siblings) and then both shell to `ll-auto --only` on the main
    working tree.
    """

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    def test_singleton_loop_conflicts_on_name_regardless_of_scope(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two singleton locks with disjoint scopes conflict on loop_name alone.

        Mirrors TestMultiInstanceSameName.test_concurrent_same_name_non_overlapping_scopes_both_acquire
        but with singleton=True: the second acquire must FAIL even though scopes
        don't overlap.
        """
        run1 = tmp_path / ".loops" / "runs" / "autodev-20240115T103000"
        run2 = tmp_path / ".loops" / "runs" / "autodev-20240115T103001"
        run1.mkdir(parents=True)
        run2.mkdir(parents=True)

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("autodev", scope, instance_id=instance_id, singleton=True)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, [str(run1.relative_to(tmp_path))]))
        t2 = threading.Thread(target=try_acquire, args=(id2, [str(run2.relative_to(tmp_path))]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1, (
            f"Singleton predicate: exactly one acquire must succeed regardless of disjoint scopes; "
            f"got: {results}"
        )
        assert results.count(False) == 1, (
            f"Singleton predicate: the second acquire must fail on loop_name match; got: {results}"
        )

    def test_non_singleton_same_name_disjoint_scopes_still_both_acquire(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for ENH-1354 / FEAT-1789: non-singleton + disjoint scopes = both acquire.

        This is the same scenario as
        TestMultiInstanceSameName.test_concurrent_same_name_non_overlapping_scopes_both_acquire
        but uses the default singleton=False. Locks both must succeed — singleton
        must NOT be enabled by default.
        """
        src_dir = tmp_path / "src"
        lib_dir = tmp_path / "lib"
        src_dir.mkdir()
        lib_dir.mkdir()

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            # Default singleton=False explicitly to assert backward compatibility
            result = manager.acquire("autodev", scope, instance_id=instance_id, singleton=False)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, ["src/"]))
        t2 = threading.Thread(target=try_acquire, args=(id2, ["lib/"]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 2, (
            f"Non-singleton disjoint scopes must both acquire (ENH-1354 regression); got: {results}"
        )

    def test_singleton_paths_overlap_still_conflicts(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Singleton + overlapping paths must still conflict (parity with non-singleton).

        Two singleton locks with overlapping paths AND same loop_name must
        produce a conflict (the singleton predicate should never relax the
        scope-overlap conflict — only add a name-match conflict where one
        would not otherwise exist).
        """
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("autodev", scope, instance_id=instance_id, singleton=True)
            results.append(result)

        id1 = "autodev-20240115T103000"
        id2 = "autodev-20240115T103001"
        t1 = threading.Thread(target=try_acquire, args=(id1, ["src/"]))
        t2 = threading.Thread(target=try_acquire, args=(id2, ["src/sub/"]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 1, (
            f"Singleton + overlapping paths must conflict (scope overlap already triggers); "
            f"got: {results}"
        )

    def test_singleton_ancestor_does_not_self_conflict(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_ancestry carve-out extends to singleton: parent PID forked → child singleton loop must NOT self-conflict.

        A parent `ll-loop run` process that shells to nested `ll-loop run autodev`
        would otherwise self-conflict on singleton (same loop_name). The carve-out
        at concurrency.py:223-229 must extend to the new singleton predicate.
        """
        manager = LockManager(tmp_loops)
        run1 = tmp_path / ".loops" / "runs" / "autodev-parent"
        run1.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        # Hold a singleton lock as the parent
        assert manager.acquire(
            "autodev",
            [str(run1.relative_to(tmp_path))],
            instance_id="parent",
            singleton=True,
        )

        # Patch _get_ancestry to include a sentinel ancestor PID so the
        # child acquire is recognized as nested in the parent. The parent's
        # own PID is the current PID, which is NOT in _get_ancestry (the set
        # walks up from current). We patch to include the current PID
        # to simulate the parent→child fork relationship.
        current_pid = 12345
        with (
            patch.object(manager, "_get_ancestry", return_value={current_pid}),
            patch("os.getpid", return_value=current_pid),
        ):
            # Recreate ScopeLock holder under fake parent pid
            lock_file = tmp_loops / ".running" / "parent.lock"
            data = json.loads(lock_file.read_text())
            data["pid"] = current_pid
            lock_file.write_text(json.dumps(data))

            # Now the child tries to acquire singleton autodev with disjoint scope
            run2 = tmp_path / ".loops" / "runs" / "autodev-child"
            run2.mkdir(parents=True)
            result = manager.acquire(
                "autodev",
                [str(run2.relative_to(tmp_path))],
                instance_id="child",
                singleton=True,
            )

        assert result is True, (
            "Singleton ancestor carve-out: child autodev must NOT self-conflict "
            "on parent's singleton lock when child is an ancestor of self"
        )

        manager.release("autodev", instance_id="child")
        manager.release("autodev", instance_id="parent")


class TestResolveScope:
    """Tests for resolve_scope() template variable resolution."""

    def test_static_passthrough(self) -> None:
        """Static paths pass through unchanged."""
        scope = ["src/", "docs/", "*.md"]
        result = resolve_scope(scope, {"plan_file": "foo.md"})
        assert result == ["src/", "docs/", "*.md"]

    def test_with_context_var(self) -> None:
        """${context.var} is resolved to the context value."""
        scope = ["${context.plan_file}"]
        result = resolve_scope(scope, {"plan_file": "path/to/plan.md"})
        assert result == ["path/to/plan.md"]

    def test_unresolved_var_preserved(self) -> None:
        """Unknown ${context.var} is kept as literal."""
        scope = ["${context.unknown}"]
        result = resolve_scope(scope, {})
        assert result == ["${context.unknown}"]

    def test_mixed_static_and_template(self) -> None:
        """Mixed static and template paths both resolve correctly."""
        scope = ["src/", "${context.out_dir}", "*.md"]
        result = resolve_scope(scope, {"out_dir": "build/"})
        assert result == ["src/", "build/", "*.md"]

    def test_empty_scope(self) -> None:
        """Empty scope list returns empty list."""
        result = resolve_scope([], {"plan_file": "x.md"})
        assert result == []

    def test_empty_context(self) -> None:
        """All templates with empty context are preserved as literals."""
        scope = ["${context.a}", "${context.b}"]
        result = resolve_scope(scope, {})
        assert result == ["${context.a}", "${context.b}"]

    def test_partial_template_in_path(self) -> None:
        """Template var can appear as part of a larger path string."""
        scope = ["${context.base_dir}/src/"]
        result = resolve_scope(scope, {"base_dir": "/home/user/project"})
        assert result == ["/home/user/project/src/"]

    def test_multiple_templates_in_path(self) -> None:
        """Multiple templates in a single path are all resolved."""
        scope = ["${context.root}/${context.sub}/"]
        result = resolve_scope(scope, {"root": "/a", "sub": "b"})
        assert result == ["/a/b/"]

    def test_partial_unresolved_template(self) -> None:
        """Path with mixed resolved and unresolved templates keeps unresolved parts."""
        scope = ["${context.known}/${context.unknown}"]
        result = resolve_scope(scope, {"known": "data"})
        assert result == ["data/${context.unknown}"]

    def test_non_context_template_not_resolved(self) -> None:
        """Only ${context.*} templates are resolved; other namespaces are left alone."""
        scope = ["${env.HOME}", "${captured.x}"]
        result = resolve_scope(scope, {"HOME": "/home/user", "x": "val"})
        assert result == ["${env.HOME}", "${captured.x}"]

    def test_context_var_int_value(self) -> None:
        """Context variable with int value is stringified."""
        scope = ["${context.port}"]
        result = resolve_scope(scope, {"port": 8080})
        assert result == ["8080"]

    def test_run_dir_template_resolves(self) -> None:
        """[${{context.run_dir}}] resolves to the per-instance path (ENH-2500)."""
        scope = ["${context.run_dir}"]
        result = resolve_scope(
            scope, {"run_dir": ".loops/runs/prompt-across-issues-20260706T140004/"}
        )
        assert result == [".loops/runs/prompt-across-issues-20260706T140004/"]

    def test_two_distinct_run_dirs_resolve_disjoint(self) -> None:
        """Distinct run_dir values resolve to disjoint scope paths (ENH-2500,
        EPIC-2457 vs EPIC-2451 collision scenario)."""
        run_a = ".loops/runs/prompt-across-issues-20260706T140004/"
        run_b = ".loops/runs/prompt-across-issues-20260706T140754/"
        scope_a = resolve_scope(["${context.run_dir}"], {"run_dir": run_a})
        scope_b = resolve_scope(["${context.run_dir}"], {"run_dir": run_b})
        assert scope_a == [run_a]
        assert scope_b == [run_b]
        assert scope_a != scope_b


class TestPromptAcrossIssuesScopeIsolation:
    """ENH-2500: prompt-across-issues concurrent instances on disjoint run_dirs
    must not collide at the LockManager layer.
    """

    @pytest.fixture
    def tmp_loops(self, tmp_path: Path) -> Path:
        """Local fixture so this class can stand alone."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        return loops_dir

    def test_two_prompt_across_issues_instances_disjoint_run_dirs_both_acquire_concurrently(
        self, tmp_loops: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reproduces the 2026-07-06 collision: an EPIC-2457 sweep and an
        EPIC-2451 sweep running concurrently must both acquire (no 'Scope
        conflict' error).
        """
        run1 = tmp_path / ".loops" / "runs" / "prompt-across-issues-20260706T140004"
        run2 = tmp_path / ".loops" / "runs" / "prompt-across-issues-20260706T140754"
        run1.mkdir(parents=True)
        run2.mkdir(parents=True)

        manager = LockManager(tmp_loops)
        results: list[bool] = []
        barrier = threading.Barrier(2)

        monkeypatch.chdir(tmp_path)

        def try_acquire(instance_id: str, scope: list[str]) -> None:
            barrier.wait()
            result = manager.acquire("prompt-across-issues", scope, instance_id=instance_id)
            results.append(result)

        id1 = "prompt-across-issues-20260706T140004"
        id2 = "prompt-across-issues-20260706T140754"
        t1 = threading.Thread(
            target=try_acquire,
            args=(id1, [str(run1.relative_to(tmp_path))]),
        )
        t2 = threading.Thread(
            target=try_acquire,
            args=(id2, [str(run2.relative_to(tmp_path))]),
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count(True) == 2, (
            "Both prompt-across-issues instances with disjoint run_dir scopes "
            f"should acquire concurrently; got: {results}"
        )
