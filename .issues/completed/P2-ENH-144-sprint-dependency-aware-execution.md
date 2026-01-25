---
discovered_date: 2026-01-25
discovered_by: capture_issue
---

# ENH-144: Sprint Execution Should Use Dependency Graph

## Summary

Sprint execution should use the `DependencyGraph` class to determine optimal issue execution order instead of simple sequential/parallel modes. Remove the `--parallel` flag - sprints should automatically execute independent issues in parallel while respecting `Blocked By` relationships.

## Context

The `DependencyGraph` class exists in `scripts/little_loops/dependency_graph.py` (implemented via FEAT-030) but is not used anywhere. Sprint execution currently offers two modes:

1. **Sequential** (default): Issues process in list order via `AutoManager`
2. **Parallel** (`--parallel` flag): All issues dispatch concurrently via `ParallelOrchestrator`

Neither mode respects `Blocked By` relationships defined in issue files. This can lead to:
- Race conditions when blocked issues complete before their blockers
- Merge conflicts from overlapping changes
- Wasted compute when implementations are invalidated by blocker changes

## Current Behavior

```bash
# Sequential - ignores dependencies, processes in list order
ll-sprint run sprint-1

# Parallel - ignores dependencies, dispatches all concurrently
ll-sprint run sprint-1 --parallel
```

The `_cmd_sprint_run()` function in `cli.py` simply passes issue IDs to either `AutoManager` or `ParallelOrchestrator` without any dependency analysis.

## Expected Behavior

```bash
# Single mode - dependency-aware execution
ll-sprint run sprint-1

# Output shows dependency-driven scheduling
Running sprint: sprint-1
Dependency analysis:
  FEAT-001: no blockers (ready)
  FEAT-003: blocked by FEAT-001
  BUG-005: no blockers (ready)

Wave 1 (parallel): FEAT-001, BUG-005
Wave 2 (after FEAT-001): FEAT-003

Processing wave 1...
  [worker 1] FEAT-001
  [worker 2] BUG-005
FEAT-001 completed - unblocking: FEAT-003
Processing wave 2...
  [worker 1] FEAT-003
```

## Proposed Solution

### 1. Remove `--parallel` Flag

The `--parallel` flag becomes unnecessary when execution is dependency-driven. Independent issues naturally parallelize while dependent issues wait.

Remove from `_cmd_sprint_run()`:
- `--parallel` argument
- `parallel` mode selection logic
- Sequential-only `AutoManager` path

### 2. Integrate DependencyGraph into Sprint Execution

```python
from little_loops.dependency_graph import DependencyGraph

def _cmd_sprint_run(args, manager, config):
    sprint = manager.load(args.sprint)

    # Parse issue files to get IssueInfo objects
    issues = [parse_issue(id) for id in sprint.issues]

    # Build dependency graph
    dep_graph = DependencyGraph.from_issues(issues, completed_ids=set())

    # Detect and warn about cycles
    cycles = dep_graph.detect_cycles()
    if cycles:
        for cycle in cycles:
            logger.warning(f"Dependency cycle: {' -> '.join(cycle)}")

    # Get topological order with parallelization info
    execution_waves = dep_graph.get_execution_waves()

    # Execute wave by wave
    for wave_num, wave_issues in enumerate(execution_waves, 1):
        logger.info(f"Wave {wave_num}: {', '.join(i.issue_id for i in wave_issues)}")
        # Process wave in parallel (all issues in wave are independent)
        parallel_execute(wave_issues, max_workers=config.max_workers)
```

### 3. Add `get_execution_waves()` to DependencyGraph

New method that returns issues grouped by execution wave:

```python
def get_execution_waves(self) -> list[list[IssueInfo]]:
    """Return issues grouped into parallel execution waves.

    Wave 1: All issues with no blockers
    Wave 2: Issues whose blockers are all in wave 1
    Wave N: Issues whose blockers are all in waves 1..N-1

    Returns:
        List of waves, each wave is a list of issues that can run in parallel
    """
```

### 4. Update SprintOptions

Remove `mode` field (no longer needed):

```python
@dataclass
class SprintOptions:
    max_iterations: int = 100
    timeout: int = 3600
    max_workers: int = 4
    # Remove: mode: str = "auto"
```

## Location

- **Modified**: `scripts/little_loops/cli.py` - `_cmd_sprint_run()`, remove `--parallel` flag
- **Modified**: `scripts/little_loops/sprint.py` - Remove `mode` from `SprintOptions`
- **Modified**: `scripts/little_loops/dependency_graph.py` - Add `get_execution_waves()`
- **Modified**: `scripts/tests/test_sprint*.py` - Update tests

## Impact

- **Priority**: P2 - Important for correct sprint execution
- **Effort**: Medium - Requires integration work
- **Risk**: Low - DependencyGraph already tested, mostly wiring

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design patterns |
| implementation | scripts/little_loops/dependency_graph.py | Existing dependency infrastructure |
| implementation | scripts/little_loops/cli.py | Sprint execution entry point |

## Blocked By

None

## Blocks

None

## Labels

`enhancement`, `cli`, `ll-sprint`, `dependency-management`

---

## Status

**Completed** | Created: 2026-01-25 | Completed: 2026-01-25 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-25
- **Status**: Completed

### Changes Made

**scripts/little_loops/dependency_graph.py**:
- Added `get_execution_waves()` method that groups issues into parallel execution waves based on dependency relationships

**scripts/little_loops/sprint.py**:
- Added `load_issue_infos()` method to load full `IssueInfo` objects for dependency analysis
- Updated `SprintOptions` docstring to mark `mode` as deprecated

**scripts/little_loops/cli.py**:
- Imported `DependencyGraph`
- Refactored `_cmd_sprint_run()` to use dependency-aware wave execution
- Updated CLI help text to mark `--parallel` and `--mode` flags as deprecated

**scripts/tests/test_dependency_graph.py**:
- Added `TestGetExecutionWaves` test class with 8 tests

**scripts/tests/test_sprint.py**:
- Added `test_load_issue_infos_without_config` test

### Verification Results
- Tests: PASS (127 tests for modified modules)
- Lint: PASS
- Types: PASS
