---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T00:00:00Z
---

# ENH-017: Dependency-Aware Scheduling in ll-parallel

## Summary

Integrate the dependency graph (FEAT-030) into `ll-parallel` so that parallel issue processing respects `Blocked By` relationships. Blocked issues should wait until their dependencies complete before being dispatched to workers.

## Motivation

Currently, `ll-parallel` processes all issues concurrently (up to `max_workers`), selecting solely by priority:

```python
queued = self.queue.get(block=False)
if queued:
    # Dispatch immediately regardless of dependencies
    self._process_parallel(queued.issue_info)
```

If FEAT-003 is blocked by FEAT-001, both could be dispatched to workers simultaneously, leading to:

1. **Race conditions**: FEAT-003 might complete first and be merged, then FEAT-001 changes the same files
2. **Merge conflicts**: Both branches modify overlapping code paths
3. **Wasted compute**: FEAT-003 implementation may be invalidated by FEAT-001

## Proposed Implementation

### 1. Extend `IssuePriorityQueue` with Blocking Awareness

Instead of modifying the priority queue directly, use a wrapper that filters blocked issues:

```python
class DependencyAwareQueue:
    """Wraps IssuePriorityQueue with dependency filtering."""

    def __init__(self, base_queue: IssuePriorityQueue, dep_graph: DependencyGraph):
        self.base_queue = base_queue
        self.dep_graph = dep_graph
        self._blocked_issues: dict[str, IssueInfo] = {}  # Issues waiting on blockers

    def get(self, block: bool = True, timeout: float | None = None) -> QueuedIssue | None:
        """Get next ready issue, holding back blocked ones."""
        completed = set(self.base_queue.completed_ids)

        # First, check if any blocked issues are now ready
        newly_ready = []
        for issue_id, info in list(self._blocked_issues.items()):
            if not self.dep_graph.is_blocked(issue_id, completed):
                newly_ready.append(info)
                del self._blocked_issues[issue_id]

        # Re-add newly ready issues to base queue
        for info in newly_ready:
            self.base_queue.add(info)

        # Try to get from base queue, checking dependencies
        queued = self.base_queue.get(block=False)
        if queued:
            issue_id = queued.issue_info.issue_id
            if self.dep_graph.is_blocked(issue_id, completed):
                # Hold this issue back
                self._blocked_issues[issue_id] = queued.issue_info
                return self.get(block=False)  # Try next
            return queued

        return None
```

### 2. Modify Orchestrator Initialization

In `ParallelOrchestrator.__init__()`:

```python
from little_loops.dependency_graph import DependencyGraph

# After scanning issues
all_issues = self._scan_issues()
self.dep_graph = DependencyGraph.from_issues(all_issues)

# Warn about cycles
cycles = self.dep_graph.detect_cycles()
for cycle in cycles:
    self.logger.warning(f"Dependency cycle: {' -> '.join(cycle)}")

# Wrap the queue
self.queue = IssuePriorityQueue()
self.dep_aware_queue = DependencyAwareQueue(self.queue, self.dep_graph)
```

### 3. Update Main Processing Loop

In `_execute()`:

```python
# Replace self.queue.get() with dependency-aware get
if self.worker_pool.active_count < self.parallel_config.max_workers:
    queued = self.dep_aware_queue.get(block=False)  # NEW
    if queued:
        # ... dispatch as before
```

### 4. Handle Completion Callbacks

When an issue completes, its dependents may become unblocked. The `DependencyAwareQueue.get()` method already handles this by checking blocked issues on each call.

For proactive unblocking (better performance):

```python
def on_issue_completed(self, issue_id: str) -> list[IssueInfo]:
    """Called when an issue completes. Returns newly unblocked issues."""
    completed = set(self.base_queue.completed_ids) | {issue_id}
    newly_ready = []

    for blocked_id, info in list(self._blocked_issues.items()):
        if not self.dep_graph.is_blocked(blocked_id, completed):
            newly_ready.append(info)
            del self._blocked_issues[blocked_id]
            self.base_queue.add(info)

    return newly_ready
```

### 5. Update Worker Completion Handler

In `_on_worker_complete()`:

```python
def _on_worker_complete(self, result: WorkerResult) -> None:
    if result.success:
        # Check for newly unblocked issues
        unblocked = self.dep_aware_queue.on_issue_completed(result.issue_id)
        if unblocked:
            self.logger.info(f"Unblocked {len(unblocked)} issue(s) after {result.issue_id}")
            for info in unblocked:
                self.logger.info(f"  - {info.issue_id} now ready")
```

### 6. Dry Run Updates

Update `_dry_run()` to show dependency information:

```python
def _dry_run(self) -> int:
    issues = self._scan_issues()
    dep_graph = DependencyGraph.from_issues(issues)

    # Show dependency tree
    self.logger.info("Dependency Information:")
    for issue in issues:
        blockers = dep_graph.blocked_by.get(issue.issue_id, set())
        if blockers:
            self.logger.info(f"  {issue.issue_id} blocked by: {', '.join(blockers)}")

    # Show processing order (topological)
    ordered = dep_graph.topological_sort()
    self.logger.info("Topological processing order:")
    for i, issue in enumerate(ordered, 1):
        self.logger.info(f"  {i}. {issue.issue_id}")
```

### 7. State Persistence for Blocked Issues

Track blocked issues in state for resume:

```python
class OrchestratorState:
    # ... existing fields ...
    blocked_issues: list[str] = field(default_factory=list)  # NEW
```

## Location

- **Modified**: `scripts/little_loops/parallel/orchestrator.py` (main orchestrator)
- **Modified**: `scripts/little_loops/parallel/priority_queue.py` (optional: add wrapper)
- **Uses**: `scripts/little_loops/dependency_graph.py` (from FEAT-030)

## Current Behavior

- `IssuePriorityQueue.get()` returns highest-priority issue without checking dependencies
- All issues in queue can be dispatched concurrently
- No awareness of `Blocked By` relationships
- Issues with dependencies may race with their blockers

## Expected Behavior

- Issues with unsatisfied `Blocked By` are held back from dispatch
- When a blocker completes, dependents become eligible for dispatch
- Dry run shows dependency tree and topological order
- CLI output shows when issues are unblocked
- State persistence includes blocked issues for resume

## Acceptance Criteria

- [ ] `DependencyAwareQueue` class wraps `IssuePriorityQueue`
- [ ] Blocked issues are held until dependencies complete
- [ ] Completion callback triggers unblocking check
- [ ] Dry run shows dependency information
- [ ] Cycles detected and warned about
- [ ] State file includes blocked issues list
- [ ] Integration test: dependent issues wait for blockers
- [ ] Integration test: completion unblocks dependents
- [ ] No regression: issues without dependencies dispatch immediately
- [ ] Performance: O(1) blocked check per get()

## Impact

- **Severity**: Medium - Improves parallel processing reliability
- **Effort**: Medium - Wrapper pattern adds complexity
- **Risk**: Medium - Must ensure blocked issues eventually dispatch

## Dependencies

- FEAT-030: Issue Dependency Parsing and Graph Construction

## Blocked By

- FEAT-030

## Blocks

None

## Labels

`enhancement`, `cli`, `ll-parallel`, `dependency-management`, `concurrency`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2
