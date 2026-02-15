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
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNNING_DIR = ".running"


def _iso_now() -> str:
    """Return current time as ISO8601 string."""
    return datetime.now(UTC).isoformat()


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "loop_name": self.loop_name,
            "scope": self.scope,
            "pid": self.pid,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopeLock:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            loop_name=str(data["loop_name"]),
            scope=list(data["scope"]) if isinstance(data["scope"], list) else [str(data["scope"])],
            pid=int(data["pid"]),
            started_at=str(data["started_at"]),
        )


class LockManager:
    """Manage scope-based locks for concurrent loop execution.

    Lock files are stored in .loops/.running/<name>.lock
    and contain JSON with ScopeLock data.
    """

    def __init__(self, loops_dir: Path | None = None) -> None:
        """Initialize the lock manager.

        Args:
            loops_dir: Base directory for loops (default: .loops)
        """
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
        lock_file.unlink(missing_ok=True)

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
                    lock_file.unlink(missing_ok=True)
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
        locks: list[ScopeLock] = []
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
                    lock_file.unlink(missing_ok=True)
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
