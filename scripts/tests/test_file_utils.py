"""Tests for atomic_write_json and acquire_lock in little_loops.file_utils (FEAT-1454)."""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.file_utils import acquire_lock, atomic_write_json


class TestAtomicWriteJson:
    """Verify atomic_write_json round-trips, creates parent dirs, leaves no orphans."""

    def test_writes_json_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write_json(target, {"hello": "world", "n": 42})
        assert json.loads(target.read_text()) == {"hello": "world", "n": 42}

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "deep" / "out.json"
        atomic_write_json(target, {"ok": True})
        assert target.is_file()
        assert json.loads(target.read_text()) == {"ok": True}

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        target.write_text('{"old": true}')
        atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}

    def test_rejects_non_finite_floats(self, tmp_path: Path) -> None:
        """NaN/Infinity must be rejected (parity with bash `jq empty` strict mode)."""
        target = tmp_path / "out.json"
        with pytest.raises(ValueError):
            atomic_write_json(target, {"bad": float("nan")})
        assert not target.exists()
        with pytest.raises(ValueError):
            atomic_write_json(target, {"bad": float("inf")})
        assert not target.exists()

    def test_no_tmp_files_on_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write_json(target, {"k": "v"})
        assert list(tmp_path.glob("*.tmp")) == []

    def test_no_tmp_orphan_on_replace_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        with patch("os.replace", side_effect=OSError("simulated disk full")):
            with pytest.raises(OSError):
                atomic_write_json(target, {"k": "v"})
        assert list(tmp_path.glob("*.tmp")) == []

    def test_preserves_existing_file_on_replace_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        target.write_text('{"original": true}')
        with patch("os.replace", side_effect=OSError("simulated disk full")):
            with pytest.raises(OSError):
                atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"original": True}


class TestAcquireLock:
    """Verify acquire_lock provides exclusive access and times out cleanly."""

    def test_acquires_and_releases(self, tmp_path: Path) -> None:
        lock = tmp_path / "out.lock"
        with acquire_lock(lock, timeout=1.0):
            assert lock.exists()
        # Re-acquire after release should succeed immediately.
        with acquire_lock(lock, timeout=1.0):
            pass

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        lock = tmp_path / "nested" / "deep" / "out.lock"
        with acquire_lock(lock, timeout=1.0):
            assert lock.exists()

    def test_timeout_raises_when_held(self, tmp_path: Path) -> None:
        lock = tmp_path / "out.lock"
        holder_ready = threading.Event()
        release_holder = threading.Event()

        def hold_lock() -> None:
            with acquire_lock(lock, timeout=1.0):
                holder_ready.set()
                release_holder.wait(timeout=5.0)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold_lock)
            assert holder_ready.wait(timeout=2.0), "holder thread never acquired lock"
            start = time.monotonic()
            with pytest.raises(TimeoutError, match="acquire_lock"):
                with acquire_lock(lock, timeout=0.2):
                    pass
            elapsed = time.monotonic() - start
            assert elapsed >= 0.2
            assert elapsed < 1.5, f"timeout took too long: {elapsed:.2f}s"
            release_holder.set()
            future.result(timeout=5.0)

    def test_exclusive_acquisition_one_wins(self, tmp_path: Path) -> None:
        """Two threads racing for the same lock: exactly one acquires immediately."""
        lock = tmp_path / "race.lock"
        barrier = threading.Barrier(2)
        results: list[bool] = []
        results_lock = threading.Lock()

        def try_acquire() -> None:
            barrier.wait(timeout=5.0)
            try:
                with acquire_lock(lock, timeout=0.1):
                    with results_lock:
                        results.append(True)
                    # Hold briefly so the other thread definitely sees contention.
                    time.sleep(0.3)
            except TimeoutError:
                with results_lock:
                    results.append(False)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(try_acquire) for _ in range(2)]
            for f in as_completed(futures):
                f.result(timeout=5.0)

        assert results.count(True) == 1, f"expected exactly one winner, got {results}"
        assert results.count(False) == 1

    def test_lock_released_on_exception_inside_block(self, tmp_path: Path) -> None:
        """If the with-body raises, the lock is still released."""
        lock = tmp_path / "err.lock"

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom):
            with acquire_lock(lock, timeout=1.0):
                raise _Boom()

        # Should be re-acquirable immediately.
        with acquire_lock(lock, timeout=0.5):
            pass

    def test_concurrent_writers_via_acquire_lock(self, tmp_path: Path) -> None:
        """ThreadPoolExecutor pattern: N threads serialize through acquire_lock + atomic_write_json."""
        target = tmp_path / "counter.json"
        lock = tmp_path / "counter.lock"
        target.write_text(json.dumps({"count": 0}))

        def increment() -> None:
            with acquire_lock(lock, timeout=5.0):
                current = json.loads(target.read_text())
                current["count"] += 1
                atomic_write_json(target, current)

        n = 8
        with ThreadPoolExecutor(max_workers=n) as pool:
            for f in as_completed([pool.submit(increment) for _ in range(n)]):
                f.result(timeout=10.0)

        final = json.loads(target.read_text())
        assert final == {"count": n}
        assert list(tmp_path.glob("*.tmp")) == []
        # Lock file exists but is empty (write-mode open truncates).
        assert lock.exists()
        # No silent corruption: every increment landed.
        assert isinstance(final, dict)
        # Ensure os module wasn't shadowed by import (regression smoke).
        assert os.path.exists(target)
