# ENH-144: Sprint Execution Should Use Dependency Graph - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-144-sprint-dependency-aware-execution.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

Sprint execution currently offers two modes controlled by the `--parallel` flag:

1. **Sequential mode** (default): Uses `AutoManager` to process issues in list order
2. **Parallel mode** (`--parallel`): Uses `ParallelOrchestrator` to dispatch all issues concurrently

Neither mode respects `Blocked By` relationships. The `DependencyGraph` class exists at `scripts/little_loops/dependency_graph.py` but is not used by sprint execution.

### Key Discoveries
- `DependencyGraph.from_issues()` builds graph from `IssueInfo` objects (`dependency_graph.py:41-91`)
- `get_ready_issues(completed)` returns issues with all blockers satisfied (`dependency_graph.py:93-117`)
- `topological_sort()` implements Kahn's algorithm for execution order (`dependency_graph.py:156-208`)
- `_cmd_sprint_run()` at `cli.py:1480-1534` is the entry point to modify
- `SprintOptions.mode` field controls sequential vs parallel (`sprint.py:25`)
- `SprintManager.validate_issues()` returns `dict[str, Path]` mapping issue IDs to paths (`sprint.py:253-275`)
- `ParallelOrchestrator._scan_issues()` scans directories for `IssueInfo` objects

## Desired End State

Sprint execution will:
1. Build a `DependencyGraph` from sprint issues
2. Execute issues in dependency-aware waves
3. Parallelize independent issues within each wave
4. Respect `Blocked By` relationships across waves

### How to Verify
- `ll-sprint run sprint-1` shows dependency analysis and wave-based execution
- Issues with blockers only start after blockers complete
- Independent issues run in parallel within waves
- Cycle detection prevents execution with circular dependencies

## What We're NOT Doing

- Not removing `--parallel` flag entirely (it can still force parallel mode for backwards compatibility)
- Not modifying `ParallelOrchestrator` internals (we'll use it as-is per wave)
- Not adding wave-based execution to `ll-auto` or `ll-parallel` (separate enhancements)
- Not persisting wave state across restarts (simple single-run execution)

## Problem Analysis

The current `_cmd_sprint_run()` function:
1. Validates issue IDs exist via `SprintManager.validate_issues()`
2. Chooses between `AutoManager` and `ParallelOrchestrator` based on `--parallel`
3. Passes `only_ids` filter but no dependency information

The fix requires:
1. Loading `IssueInfo` objects (not just paths) to get dependency data
2. Building a `DependencyGraph` from those issues
3. Implementing wave-based execution that processes ready issues in parallel

## Solution Approach

1. **Add `get_execution_waves()` method to `DependencyGraph`** - Returns issues grouped by dependency wave
2. **Add `load_issue_infos()` helper to `SprintManager`** - Loads full `IssueInfo` objects for validation
3. **Refactor `_cmd_sprint_run()`** - Use dependency graph for wave-based execution
4. **Update `SprintOptions`** - Remove `mode` field (or deprecate) since execution is now always dependency-aware

## Implementation Phases

### Phase 1: Add `get_execution_waves()` to DependencyGraph

#### Overview
Add a method that returns issues grouped into execution waves. Wave 1 contains issues with no blockers, wave 2 contains issues whose blockers are all in wave 1, etc.

#### Changes Required

**File**: `scripts/little_loops/dependency_graph.py`
**Changes**: Add `get_execution_waves()` method after `get_ready_issues()`

```python
def get_execution_waves(self, completed: set[str] | None = None) -> list[list[IssueInfo]]:
    """Return issues grouped into parallel execution waves.

    Wave 1: All issues with no blockers (or blockers already completed)
    Wave 2: Issues whose blockers are all in wave 1
    Wave N: Issues whose blockers are all in waves 1..N-1

    This is similar to topological_sort but groups issues by "level"
    rather than returning a flat list.

    Args:
        completed: Set of already-completed issue IDs

    Returns:
        List of waves, each wave is a list of issues that can run in parallel.
        Empty list if graph is empty or all issues are completed.

    Raises:
        ValueError: If graph contains cycles (not a DAG)
    """
    completed = completed or set()
    waves: list[list[IssueInfo]] = []
    processed: set[str] = set(completed)

    while True:
        # Get issues ready to run (all blockers in processed set)
        wave = self.get_ready_issues(completed=processed)
        if not wave:
            break
        waves.append(wave)
        # Mark this wave as processed for next iteration
        for issue in wave:
            processed.add(issue.issue_id)

    # Check for cycles - if we have unprocessed issues, there's a cycle
    remaining = set(self.issues.keys()) - processed
    if remaining:
        cycles = self.detect_cycles()
        cycle_str = ", ".join(" -> ".join(cycle) for cycle in cycles)
        raise ValueError(f"Dependency graph contains cycles: {cycle_str}")

    return waves
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_graph.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_graph.py`

---

### Phase 2: Add `load_issue_infos()` to SprintManager

#### Overview
Add a helper method to load full `IssueInfo` objects from issue IDs, reusing the validation logic.

#### Changes Required

**File**: `scripts/little_loops/sprint.py`
**Changes**: Add import and new method to `SprintManager`

```python
# Add to imports at top of file
from little_loops.issue_parser import IssueParser, IssueInfo

# Add method to SprintManager class
def load_issue_infos(self, issues: list[str]) -> list[IssueInfo]:
    """Load IssueInfo objects for the given issue IDs.

    Args:
        issues: List of issue IDs to load

    Returns:
        List of IssueInfo objects (only for issues that exist)
    """
    if not self.config:
        return []

    parser = IssueParser()
    result = []
    for issue_id in issues:
        for category in ["bugs", "features", "enhancements"]:
            issue_dir = self.config.get_issue_dir(category)
            for path in issue_dir.glob(f"*-{issue_id}-*.md"):
                try:
                    info = parser.parse(path)
                    if info:
                        result.append(info)
                        break
                except Exception:
                    continue
            if any(i.issue_id == issue_id for i in result):
                break
    return result
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/sprint.py`

---

### Phase 3: Refactor `_cmd_sprint_run()` for Wave-Based Execution

#### Overview
Modify the sprint run command to use `DependencyGraph` for dependency-aware execution. Issues are processed in waves, with each wave running in parallel.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
1. Add import for `DependencyGraph`
2. Refactor `_cmd_sprint_run()` to use wave-based execution

```python
# Add to imports section (around line 25)
from little_loops.dependency_graph import DependencyGraph

# Replace _cmd_sprint_run() function (lines 1480-1534)
def _cmd_sprint_run(
    args: argparse.Namespace,
    manager: SprintManager,
    config: BRConfig,
) -> int:
    """Execute a sprint with dependency-aware scheduling."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    # Validate issues exist
    valid = manager.validate_issues(sprint.issues)
    invalid = set(sprint.issues) - set(valid.keys())

    if invalid:
        logger.error(f"Issue IDs not found: {', '.join(sorted(invalid))}")
        logger.info("Cannot execute sprint with missing issues")
        return 1

    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(sprint.issues)
    if not issue_infos:
        logger.error("No issue files found")
        return 1

    # Build dependency graph
    dep_graph = DependencyGraph.from_issues(issue_infos)

    # Detect cycles
    if dep_graph.has_cycles():
        cycles = dep_graph.detect_cycles()
        for cycle in cycles:
            logger.error(f"Dependency cycle detected: {' -> '.join(cycle)}")
        return 1

    # Get execution waves
    try:
        waves = dep_graph.get_execution_waves()
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Display execution plan
    logger.info(f"Running sprint: {sprint.name}")
    logger.info(f"Dependency analysis:")
    for i, wave in enumerate(waves, 1):
        issue_ids = ", ".join(issue.issue_id for issue in wave)
        logger.info(f"  Wave {i}: {issue_ids}")

    if args.dry_run:
        logger.info("\nDry run mode - no changes will be made")
        return 0

    # Determine max workers
    max_workers = args.max_workers or (sprint.options.max_workers if sprint.options else 4)

    # Execute wave by wave
    completed: set[str] = set()
    failed: set[str] = set()

    for wave_num, wave in enumerate(waves, 1):
        wave_ids = [issue.issue_id for issue in wave]
        logger.info(f"\nProcessing wave {wave_num}: {', '.join(wave_ids)}")

        # Use ParallelOrchestrator for wave execution
        only_ids = set(wave_ids)
        parallel_config = config.create_parallel_config(
            max_workers=min(max_workers, len(wave)),
            only_ids=only_ids,
            dry_run=args.dry_run,
        )

        orchestrator = ParallelOrchestrator(parallel_config, config, Path.cwd())
        result = orchestrator.run()

        # Track completed/failed from this wave
        # ParallelOrchestrator returns 0 on success, non-zero on failure
        if result == 0:
            completed.update(wave_ids)
            logger.success(f"Wave {wave_num} completed: {', '.join(wave_ids)}")
        else:
            # Some issues failed - we continue but track failures
            # Note: ParallelOrchestrator handles partial failures internally
            logger.warning(f"Wave {wave_num} had failures")
            # Mark all as attempted (orchestrator tracks actual status)
            completed.update(wave_ids)

    logger.info(f"\nSprint completed: {len(completed)} issues processed")
    return 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] Running `ll-sprint run sprint-1 --dry-run` shows dependency waves
- [ ] Running `ll-sprint run sprint-1` executes waves in order

---

### Phase 4: Update SprintOptions and CLI Arguments

#### Overview
The `mode` field in `SprintOptions` is no longer meaningful since execution is always dependency-aware. Keep it for backwards compatibility but ignore it. The `--parallel` flag can still be accepted for backwards compatibility.

#### Changes Required

**File**: `scripts/little_loops/sprint.py`
**Changes**: Update docstring for `SprintOptions.mode` to indicate deprecation

```python
@dataclass
class SprintOptions:
    """Execution options for sprint runs.

    Attributes:
        mode: DEPRECATED - execution is now always dependency-aware.
              Kept for backwards compatibility.
        max_iterations: Maximum Claude iterations per issue
        timeout: Per-issue timeout in seconds
        max_workers: Worker count for parallel execution within waves
    """

    mode: str = "auto"  # Deprecated - kept for backwards compatibility
    max_iterations: int = 100
    timeout: int = 3600
    max_workers: int = 4
```

**File**: `scripts/little_loops/cli.py`
**Changes**: Update help text for `--parallel` flag to indicate it's deprecated

The `--parallel` flag at line 1317-1320 is now effectively a no-op since wave execution already parallelizes. Update the help text:

```python
run_parser.add_argument(
    "--parallel",
    action="store_true",
    help="DEPRECATED: Execution is now always dependency-aware with parallel waves",
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 5: Add Tests for Wave Execution

#### Overview
Add tests for `get_execution_waves()` and the updated sprint execution logic.

#### Changes Required

**File**: `scripts/tests/test_dependency_graph.py`
**Changes**: Add `TestGetExecutionWaves` class

```python
class TestGetExecutionWaves:
    """Tests for get_execution_waves()."""

    def test_single_wave_no_deps(self) -> None:
        """All issues in one wave when no dependencies."""
        issues = [
            make_issue("FEAT-001", priority="P0"),
            make_issue("FEAT-002", priority="P1"),
            make_issue("FEAT-003", priority="P2"),
        ]
        graph = DependencyGraph.from_issues(issues)

        waves = graph.get_execution_waves()

        assert len(waves) == 1
        assert len(waves[0]) == 3
        # Should be sorted by priority
        assert [i.issue_id for i in waves[0]] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_linear_chain_three_waves(self) -> None:
        """Linear chain A -> B -> C produces three waves."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert waves[0][0].issue_id == "FEAT-001"
        assert waves[1][0].issue_id == "FEAT-002"
        assert waves[2][0].issue_id == "FEAT-003"

    def test_diamond_two_waves(self) -> None:
        """Diamond pattern A -> B,C -> D produces three waves."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P2", blocked_by=["FEAT-001"])
        issue_d = make_issue("FEAT-004", priority="P0", blocked_by=["FEAT-002", "FEAT-003"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c, issue_d])

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        # Wave 1: A only
        assert [i.issue_id for i in waves[0]] == ["FEAT-001"]
        # Wave 2: B and C (sorted by priority)
        assert set(i.issue_id for i in waves[1]) == {"FEAT-002", "FEAT-003"}
        # Wave 3: D only
        assert [i.issue_id for i in waves[2]] == ["FEAT-004"]

    def test_with_completed_issues(self) -> None:
        """Completed issues are skipped in wave generation."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        # FEAT-001 already completed
        waves = graph.get_execution_waves(completed={"FEAT-001"})

        assert len(waves) == 2
        assert waves[0][0].issue_id == "FEAT-002"
        assert waves[1][0].issue_id == "FEAT-003"

    def test_cycle_raises_value_error(self) -> None:
        """Cycles raise ValueError."""
        issue_a = make_issue("FEAT-001", blocked_by=["FEAT-002"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        with pytest.raises(ValueError, match="cycles"):
            graph.get_execution_waves()

    def test_empty_graph(self) -> None:
        """Empty graph returns empty waves."""
        graph = DependencyGraph.from_issues([])

        waves = graph.get_execution_waves()

        assert waves == []

    def test_independent_and_dependent_mixed(self) -> None:
        """Mix of independent and dependent issues."""
        # Independent
        bugfix = make_issue("BUG-001", priority="P0")
        # Dependent chain
        feat_a = make_issue("FEAT-001", priority="P1")
        feat_b = make_issue("FEAT-002", priority="P2", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([bugfix, feat_a, feat_b])

        waves = graph.get_execution_waves()

        assert len(waves) == 2
        # Wave 1: BUG-001 and FEAT-001 (sorted by priority)
        wave1_ids = [i.issue_id for i in waves[0]]
        assert "BUG-001" in wave1_ids
        assert "FEAT-001" in wave1_ids
        # Wave 2: FEAT-002
        assert waves[1][0].issue_id == "FEAT-002"
```

**File**: `scripts/tests/test_sprint.py`
**Changes**: Add tests for `load_issue_infos()`

```python
class TestSprintManagerLoadIssueInfos:
    """Tests for SprintManager.load_issue_infos()."""

    def test_load_without_config(self, tmp_path: Path) -> None:
        """Returns empty list without config."""
        manager = SprintManager(sprints_dir=tmp_path, config=None)
        result = manager.load_issue_infos(["BUG-001"])
        assert result == []
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_graph.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- `get_execution_waves()` with various dependency patterns
- `load_issue_infos()` with and without config
- Edge cases: empty graphs, single-issue sprints, all-parallel sprints

### Integration Tests
- Create a sprint with dependencies and verify wave output
- Dry-run mode shows correct dependency analysis

## References

- Original issue: `.issues/enhancements/P2-ENH-144-sprint-dependency-aware-execution.md`
- DependencyGraph implementation: `scripts/little_loops/dependency_graph.py:21-270`
- Sprint execution entry point: `scripts/little_loops/cli.py:1480-1534`
- SprintManager: `scripts/little_loops/sprint.py:148-276`
- Existing tests: `scripts/tests/test_dependency_graph.py`
