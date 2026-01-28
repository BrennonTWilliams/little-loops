---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T00:00:00Z
---

# ENH-016: Dependency-Aware Sequencing in ll-auto

## Summary

Integrate the dependency graph (FEAT-030) into `ll-auto` so that sequential issue processing respects `Blocked By` relationships. Issues with unsatisfied dependencies should be skipped until their blockers are completed.

## Motivation

Currently, `ll-auto` processes issues strictly by priority:

```python
info = find_highest_priority_issue(self.config, self.category, skip_ids, self.only_ids)
```

This ignores the `Blocked By` section in issue files. If FEAT-003 is blocked by FEAT-001 and FEAT-002, but all have the same P1 priority, the order is arbitrary. `ll-auto` might attempt FEAT-003 first, which:

1. May fail because prerequisites aren't implemented
2. Wastes Claude API calls on doomed attempts
3. Could create partial implementations that conflict with blockers

## Proposed Implementation

### 1. Build Dependency Graph on Startup

In `AutoManager.__init__()` or `AutoManager.run()`:

```python
from little_loops.dependency_graph import DependencyGraph
from little_loops.issue_parser import find_issues

# Build graph from all active issues
all_issues = find_issues(self.config)
self.dep_graph = DependencyGraph.from_issues(all_issues)

# Check for cycles and warn
cycles = self.dep_graph.detect_cycles()
if cycles:
    for cycle in cycles:
        self.logger.warning(f"Dependency cycle detected: {' -> '.join(cycle)}")
```

### 2. Replace Priority-Only Selection

Replace `find_highest_priority_issue()` with dependency-aware selection:

```python
def _get_next_issue(self) -> IssueInfo | None:
    """Get next issue respecting dependencies."""
    # Get completed issues from state
    completed = self.state_manager.state.completed_issues

    # Get issues that are ready (blockers satisfied)
    ready_issues = self.dep_graph.get_ready_issues(completed)

    # Filter by skip_ids, only_ids, category
    candidates = [
        i for i in ready_issues
        if i.issue_id not in skip_ids
        and (self.only_ids is None or i.issue_id in self.only_ids)
        and (self.category is None or i.issue_type == self.category)
    ]

    if not candidates:
        # Check if there are blocked issues remaining
        all_remaining = [i for i in self.dep_graph.issues.values()
                        if i.issue_id not in completed and i.issue_id not in skip_ids]
        if all_remaining:
            blocked_ids = [i.issue_id for i in all_remaining]
            self.logger.warning(f"Remaining issues are blocked: {blocked_ids}")
            for issue in all_remaining:
                blockers = self.dep_graph.get_blocking_issues(issue.issue_id, completed)
                if blockers:
                    self.logger.info(f"  {issue.issue_id} blocked by: {blockers}")
        return None

    # Sort by priority, then ID
    candidates.sort(key=lambda x: (x.priority_int, x.issue_id))
    return candidates[0]
```

### 3. Update Main Loop

In `AutoManager.run()`:

```python
while not self._shutdown_requested:
    if self.max_issues > 0 and self.processed_count >= self.max_issues:
        self.logger.info(f"Reached max issues limit: {self.max_issues}")
        break

    info = self._get_next_issue()  # NEW: dependency-aware
    if not info:
        self.logger.success("No more issues to process!")
        break

    # ... rest of processing
```

### 4. Update State Manager Integration

Ensure completed issues are tracked in a way the dependency graph can use:

```python
# After successful completion
self.state_manager.mark_completed(info.issue_id, issue_timing)
# Dependency graph uses state_manager.state.completed_issues
```

### 5. Handle Dynamic Completions

When an issue completes, previously blocked issues may become ready. The current loop structure handles this naturally since we re-query `_get_next_issue()` each iteration.

### 6. CLI Feedback

Add logging to show dependency status:

```python
def _log_dependency_status(self):
    """Log current dependency state for visibility."""
    completed = self.state_manager.state.completed_issues
    ready = self.dep_graph.get_ready_issues(completed)
    blocked = [i for i in self.dep_graph.issues.values()
               if i.issue_id not in completed
               and i.issue_id not in {r.issue_id for r in ready}]

    self.logger.info(f"Dependency status: {len(ready)} ready, {len(blocked)} blocked")
```

## Location

- **Modified**: `scripts/little_loops/issue_manager.py` (AutoManager class)
- **Uses**: `scripts/little_loops/dependency_graph.py` (from FEAT-030)

## Current Behavior

- `AutoManager.run()` calls `find_highest_priority_issue()` each iteration
- Issues are selected purely by priority (P0 > P1 > ... > P5)
- `Blocked By` sections are ignored
- No cycle detection or warning

## Expected Behavior

- Issues with unsatisfied `Blocked By` are skipped
- Blocked issues become available when blockers complete
- Cycles are detected and warned about on startup
- CLI output shows dependency status
- Blocked issues are logged with their blockers when processing stalls

## Acceptance Criteria

- [ ] `DependencyGraph` built on `AutoManager` startup
- [ ] `_get_next_issue()` method respects dependencies
- [ ] Completed issues from state are used to determine "ready" status
- [ ] Cycles detected and logged as warnings
- [ ] When no ready issues remain, blocked issues are listed with their blockers
- [ ] Integration test: issues processed in correct dependency order
- [ ] Integration test: blocked issues become ready after blockers complete
- [ ] No regression: priority ordering still applies among ready issues

## Impact

- **Severity**: Medium - Improves automation reliability
- **Effort**: Small - Uses infrastructure from FEAT-016
- **Risk**: Low - Fallback to priority-only if graph is empty

## Dependencies

- FEAT-030: Issue Dependency Parsing and Graph Construction

## Blocked By

- FEAT-030

## Blocks

None

## Labels

`enhancement`, `cli`, `ll-auto`, `dependency-management`

---

## Verification Notes

**Verified: 2026-01-17**

- Blocker FEAT-030 (Issue Dependency Parsing and Graph Construction) is now **completed** (in `.issues/completed/`)
- `scripts/little_loops/dependency_graph.py` exists and provides the infrastructure needed
- This enhancement is now **unblocked** and ready for implementation

---

## Resolution

**Won't Do** - A separate CLI command already exists for executing sequences of issues with dependency awareness, making this enhancement redundant.

---

## Status

**Won't Do** | Created: 2026-01-12 | Closed: 2026-01-18 | Priority: P2

---

## Reopened

- **Date**: 2026-01-28
- **By**: capture_issue
- **Reason**: Issue recurred or was not fully resolved

### New Findings

The previous "Won't Do" resolution stated that "a separate CLI command already exists for executing sequences of issues with dependency awareness." However, this creates an inconsistency:

1. `ll-auto` is the primary/simplest entry point for users
2. `ll-sprint` and `ll-parallel` both use `DependencyGraph` to respect dependencies
3. `ll-auto` ignoring dependencies means it can attempt work that cannot succeed
4. Users who mark dependencies expect them to be honored

The "use a different tool" answer is insufficient - `ll-auto` should behave consistently with the rest of the toolset.

---

## Status (Updated)

**Open** | Reopened: 2026-01-28 | Priority: P2
