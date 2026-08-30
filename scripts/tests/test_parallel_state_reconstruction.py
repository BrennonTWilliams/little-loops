"""Tests that a parallel.* subscriber can reconstruct live run state (ENH-3346).

AC3: "A consumer subscribed to parallel.* can reconstruct active-worker count
and per-worker status at any point in a run without reading .issues/ or the
filesystem." None of the per-emitter tests in test_orchestrator.py /
test_worker_pool.py / test_merge_coordinator.py / test_priority_queue.py
exercise multi-event state reconstruction — each asserts a single emitter's
payload on a single fire. This file is the machine-checkable verification for
that stateful claim: it drives genuine emitter methods (not hand-built dicts)
against a real EventBus through multiple checkpoints, replays the captured
events into a small reconstruction function, and diffs the result against
ground truth at each checkpoint.

Two cases the reconstruction must cover explicitly (Pre-Implementation Review
Findings items 5-6):
    (a) an unpaired worker_completed with no preceding worker_started (a
        worktree-setup failure path) must not crash or miscount.
    (b) queue_changed events are applied by seq (last-writer-wins), not
        arrival order — emission happens after the queue's lock is released,
        so concurrent mutators can deliver snapshots out of order.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.events import EventBus
from little_loops.issue_parser import IssueInfo
from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import ParallelConfig, WorkerResult
from little_loops.parallel.worker_pool import WorkerPool

pytestmark = pytest.mark.integration


# =============================================================================
# Reconstruction function under test
# =============================================================================


def reconstruct_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct live run state from a captured parallel.* event stream.

    Returns:
        A dict with:
            workers: dict[worker_id, status] — the last-known lifecycle
                status for each worker seen ("started", "blocked",
                "unblocked", "merging", "merged", "merge_failed", "completed")
            active_count: number of workers currently "started", "unblocked",
                or "merging" (i.e. dispatched and not yet terminal)
            queue: the queue_changed counters from the highest-seq event seen
                so far (last-writer-wins by seq, NOT by arrival order), or
                None if no queue_changed event has arrived yet
    """
    workers: dict[str, str] = {}
    queue_state: dict[str, int] | None = None
    highest_seq_seen = -1

    for event in events:
        event_type = event.get("event")

        # Every worker-scoped event this issue adds carries worker_id; an
        # unpaired parallel.worker_completed (pre-existing event, worktree-
        # setup failure path) carries only issue_id — fall back to it so the
        # reconstruction still tracks the worker without crashing (case a).
        worker_key = str(event.get("worker_id") or event.get("issue_id"))

        if event_type == "parallel.worker_started":
            workers[worker_key] = "started"
        elif event_type == "parallel.worker_blocked":
            workers[worker_key] = "blocked"
        elif event_type == "parallel.worker_unblocked":
            workers[worker_key] = "unblocked"
        elif event_type == "parallel.merge_started":
            workers[worker_key] = "merging"
        elif event_type == "parallel.merge_completed":
            workers[worker_key] = "merged" if event.get("outcome") == "merged" else "merge_failed"
        elif event_type == "parallel.worker_completed":
            # Terminal regardless of whether a worker_started preceded it —
            # this is exactly case (a): a worktree-setup failure produces
            # worker_completed with no preceding worker_started.
            workers[worker_key] = "completed"
        elif event_type == "parallel.queue_changed":
            seq = event.get("seq", -1)
            if seq >= highest_seq_seen:
                highest_seq_seen = seq
                queue_state = {
                    "pending": event["pending"],
                    "active": event["active"],
                    "completed": event["completed"],
                    "failed": event["failed"],
                    "skipped": event["skipped"],
                }

    active_count = sum(
        1 for status in workers.values() if status in ("started", "unblocked", "merging")
    )
    return {"workers": workers, "active_count": active_count, "queue": queue_state}


# =============================================================================
# Fixtures — minimal real instances of every emitter's owning class
# =============================================================================


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def default_parallel_config() -> ParallelConfig:
    return ParallelConfig(
        max_workers=2,
        p0_sequential=True,
        worktree_base=Path(".worktrees"),
        state_file=Path(".parallel-state.json"),
        timeout_per_issue=1800,
        max_merge_retries=2,
    )


@pytest.fixture
def temp_repo_with_config(
    make_project: Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]],
) -> Path:
    repo_path, _ = make_project(config=None, extra_dirs=[".worktrees"])
    return repo_path


@pytest.fixture
def br_config(temp_repo_with_config: Path) -> BRConfig:
    return BRConfig(temp_repo_with_config)


@pytest.fixture
def mock_git_lock(mock_logger: MagicMock) -> GitLock:
    return GitLock(mock_logger)


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def received_events(event_bus: EventBus) -> list[dict[str, Any]]:
    received: list[dict[str, Any]] = []
    event_bus.register(lambda e: received.append(e))
    return received


@pytest.fixture
def orchestrator(
    default_parallel_config: ParallelConfig,
    br_config: BRConfig,
    temp_repo_with_config: Path,
    event_bus: EventBus,
) -> ParallelOrchestrator:
    """Real ParallelOrchestrator wired to ``event_bus`` (heavy subsystems mocked).

    Mirrors test_orchestrator.py's ``orchestrator`` fixture: WorkerPool/
    MergeCoordinator/IssuePriorityQueue are mocked during construction (they
    need real git/subprocess machinery this test doesn't exercise), but the
    orchestrator object itself — and its real _emit_worker_blocked/
    _emit_worker_unblocked methods — is genuine.
    """
    with (
        patch("little_loops.parallel.orchestrator.WorkerPool"),
        patch("little_loops.parallel.orchestrator.MergeCoordinator"),
        patch("little_loops.parallel.orchestrator.IssuePriorityQueue"),
    ):
        orch = ParallelOrchestrator(
            parallel_config=default_parallel_config,
            br_config=br_config,
            repo_path=temp_repo_with_config,
            verbose=False,
            event_bus=event_bus,
            run_id="run-recon-1",
        )
        return orch


@pytest.fixture
def worker_pool(
    default_parallel_config: ParallelConfig,
    br_config: BRConfig,
    mock_logger: MagicMock,
    temp_repo_with_config: Path,
    mock_git_lock: GitLock,
    event_bus: EventBus,
) -> WorkerPool:
    return WorkerPool(
        parallel_config=default_parallel_config,
        br_config=br_config,
        logger=mock_logger,
        repo_path=temp_repo_with_config,
        git_lock=mock_git_lock,
        event_bus=event_bus,
        run_id="run-recon-1",
    )


@pytest.fixture
def merge_coordinator(
    default_parallel_config: ParallelConfig,
    mock_logger: MagicMock,
    temp_repo_with_config: Path,
    event_bus: EventBus,
) -> MergeCoordinator:
    return MergeCoordinator(
        default_parallel_config,
        mock_logger,
        temp_repo_with_config,
        event_bus=event_bus,
        run_id="run-recon-1",
    )


def _issue(issue_id: str, priority: str = "P1") -> IssueInfo:
    return IssueInfo(
        path=Path(f".issues/bugs/{priority}-{issue_id}-test.md"),
        issue_type="bugs",
        priority=priority,
        issue_id=issue_id,
        title=f"Test issue {issue_id}",
    )


# =============================================================================
# Multi-checkpoint reconstruction against genuine emitters
# =============================================================================


class TestParallelStateReconstruction:
    """Drives real emitter methods through multiple checkpoints and
    reconstructs run state from the captured event stream, diffing against
    ground truth at each checkpoint."""

    def test_reconstructs_active_worker_count_across_checkpoints(
        self,
        worker_pool: WorkerPool,
        orchestrator: ParallelOrchestrator,
        received_events: list[dict[str, Any]],
    ) -> None:
        """Two workers dispatch, one is blocked/unblocked, one completes —
        reconstructed active_count and per-worker status must match ground
        truth at each checkpoint."""
        # Checkpoint 1: worker A starts (genuine WorkerPool emitter).
        worker_pool._emit_worker_started("BUG-001", Path("/tmp/worker-bug-001"), "parallel/bug-001")
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-001"] == "started"
        assert state["active_count"] == 1

        # Checkpoint 2: worker B is blocked on overlap (genuine orchestrator emitter).
        orchestrator._emit_worker_blocked("BUG-002", "overlap")
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-002"] == "blocked"
        # A blocked issue never had a worktree — not counted as active.
        assert state["active_count"] == 1

        # Checkpoint 3: worker B is unblocked (requeue succeeded).
        orchestrator._emit_worker_unblocked("BUG-002")
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-002"] == "unblocked"
        assert state["active_count"] == 2

        # Checkpoint 4: worker A finishes (genuine orchestrator emitter, via
        # _on_worker_complete so the real code path is exercised end to end).
        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worker-bug-001"),
            duration=5.0,
        )
        orchestrator._on_worker_complete(result)
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-001"] == "completed"
        assert state["active_count"] == 1  # only BUG-002 (unblocked) remains

    def test_reconstructs_merge_lifecycle(
        self,
        merge_coordinator: MergeCoordinator,
        received_events: list[dict[str, Any]],
    ) -> None:
        """merge_started -> merge_completed transitions a worker to a terminal state."""
        merge_coordinator._emit_merge_started("BUG-003", "parallel/bug-003")
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-003"] == "merging"
        assert state["active_count"] == 1

        merge_coordinator._emit_merge_completed("BUG-003", "merged")
        state = reconstruct_state(received_events)
        assert state["workers"]["BUG-003"] == "merged"
        assert state["active_count"] == 0

    def test_reconstructs_queue_counters_from_real_queue(
        self, received_events: list[dict[str, Any]], event_bus: EventBus
    ) -> None:
        """A real IssuePriorityQueue's queue_changed events reconstruct to the
        latest counters after a sequence of mutations."""
        queue = IssuePriorityQueue(event_bus=event_bus, run_id="run-recon-1")
        queue.add_many([_issue("BUG-010"), _issue("BUG-011")])
        queue.get()
        queue.get()
        queue.mark_completed("BUG-010")
        queue.mark_failed("BUG-011")

        state = reconstruct_state(received_events)
        assert state["queue"] == {
            "pending": 0,
            "active": 0,
            "completed": 1,
            "failed": 1,
            "skipped": 0,
        }

    def test_unpaired_worker_completed_does_not_crash_or_miscount(
        self,
        orchestrator: ParallelOrchestrator,
        received_events: list[dict[str, Any]],
    ) -> None:
        """A worker_completed with no preceding worker_started (worktree-setup
        failure path, orchestrator.py _on_worker_complete on the failure
        branch) must not crash the reconstruction and must still be tracked
        as a completed (terminal) worker."""
        result = WorkerResult(
            issue_id="BUG-999",
            success=False,
            branch_name="parallel/bug-999",
            worktree_path=Path("/tmp/worker-bug-999"),
            error="worktree setup failed",
        )
        # No _emit_worker_started call precedes this — simulating a failure
        # before worktree creation ever completed.
        orchestrator._on_worker_complete(result)

        state = reconstruct_state(received_events)  # must not raise
        assert state["workers"]["BUG-999"] == "completed"
        assert state["active_count"] == 0

    def test_queue_changed_applied_by_seq_not_arrival_order(self) -> None:
        """Two queue_changed events delivered out of seq order (as can happen
        when emit() runs after the lock is released across threads) must be
        reconstructed by the higher seq, not by whichever arrived last."""
        # seq=2 (the "newer" snapshot) is placed FIRST in the captured list —
        # simulating an emit-order inversion relative to lock-acquisition order.
        events = [
            {
                "event": "parallel.queue_changed",
                "ts": "2026-01-01T00:00:02Z",
                "run_id": "run-recon-1",
                "seq": 2,
                "pending": 0,
                "active": 1,
                "completed": 1,
                "failed": 0,
                "skipped": 0,
            },
            {
                "event": "parallel.queue_changed",
                "ts": "2026-01-01T00:00:01Z",
                "run_id": "run-recon-1",
                "seq": 1,
                "pending": 1,
                "active": 1,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
            },
        ]

        state = reconstruct_state(events)

        # The seq=2 snapshot is authoritative even though it arrived first.
        assert state["queue"] == {
            "pending": 0,
            "active": 1,
            "completed": 1,
            "failed": 0,
            "skipped": 0,
        }

    def test_empty_event_stream_reconstructs_to_empty_state(self) -> None:
        """No events -> no workers, zero active, no queue snapshot yet."""
        state = reconstruct_state([])
        assert state == {"workers": {}, "active_count": 0, "queue": None}
