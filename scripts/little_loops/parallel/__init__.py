"""Parallel issue processing with worker pools and git worktrees.

This subpackage provides components for processing multiple issues concurrently
using git worktrees for isolation and a merge coordinator for conflict resolution.

Components:
    IssuePriorityQueue: Thread-safe priority queue for issues
    WorkerPool: ThreadPoolExecutor-based worker management
    MergeCoordinator: Sequential merge queue with conflict handling
    ParallelOrchestrator: Main controller coordinating all components
"""

from little_loops.parallel.merge_coordinator import MergeCoordinator
from little_loops.parallel.orchestrator import ParallelOrchestrator
from little_loops.parallel.priority_queue import IssuePriorityQueue
from little_loops.parallel.types import (
    MergeRequest,
    MergeStatus,
    OrchestratorState,
    ParallelConfig,
    QueuedIssue,
    WorkerResult,
)
from little_loops.parallel.worker_pool import WorkerPool

__all__ = [
    "IssuePriorityQueue",
    "MergeCoordinator",
    "MergeRequest",
    "MergeStatus",
    "OrchestratorState",
    "ParallelConfig",
    "ParallelOrchestrator",
    "QueuedIssue",
    "WorkerPool",
    "WorkerResult",
]
