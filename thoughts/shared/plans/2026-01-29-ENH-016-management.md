# ENH-016: Dependency-Aware Sequencing in ll-auto - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-016-dependency-aware-sequencing-ll-auto.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

`ll-auto` currently selects issues using `find_highest_priority_issue()` at `issue_manager.py:641-643`:

```python
info = find_highest_priority_issue(
    self.config, self.category, skip_ids, self.only_ids
)
```

This function (at `issue_parser.py:490-508`) returns issues sorted purely by `(priority_int, issue_id)` without considering `blocked_by` relationships.

### Key Discoveries
- `DependencyGraph` exists at `dependency_graph.py:21-319` with all needed methods
- `ll-sprint` demonstrates working integration at `cli.py:1640-1668`
- `find_issues()` at `issue_parser.py:435-487` parses `blocked_by` but doesn't filter by it
- `state_manager.state.completed_issues` is a `list[str]` available for tracking
- `get_ready_issues()` at `dependency_graph.py:93-117` returns dependency-ready issues sorted by priority

## Desired End State

`AutoManager` respects `Blocked By` relationships:
- Issues with unsatisfied blockers are skipped
- Blocked issues become available when blockers complete
- Cycles are detected and warned about on startup
- CLI output shows dependency status when blocked issues exist

### How to Verify
- Run `ll-auto` with issues that have dependencies - they should process in dependency order
- Test that a blocked issue is skipped until its blocker completes
- Test that cycle warnings are logged

## What We're NOT Doing

- Not changing `find_highest_priority_issue()` signature - keep it for backward compatibility
- Not adding wave-based parallel execution (that's for ll-parallel/ll-sprint)
- Not modifying the CLI interface - just the internal logic
- Not changing state file format - using existing `completed_issues`

## Problem Analysis

The inconsistency: `ll-sprint` and `ll-parallel` both use `DependencyGraph` to respect dependencies, but `ll-auto` ignores them entirely. Users who mark dependencies expect them to be honored.

Root cause: `AutoManager.run()` calls `find_highest_priority_issue()` directly instead of using dependency-aware selection.

## Solution Approach

1. Build `DependencyGraph` on startup from all active issues
2. Detect and warn about cycles
3. Replace direct `find_highest_priority_issue()` call with dependency-aware selection using `get_ready_issues()`
4. Log blocked issues when processing stalls

The design follows `ll-sprint`'s pattern at `cli.py:1640-1668` but simplified for sequential processing.

## Implementation Phases

### Phase 1: Add DependencyGraph Import and Build

#### Overview
Add the import and build the dependency graph in `AutoManager.__init__()`.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
**Changes**: Add import and build graph in constructor

Add import at top of file (around line 28):
```python
from little_loops.dependency_graph import DependencyGraph
from little_loops.issue_parser import IssueInfo, IssueParser, find_highest_priority_issue, find_issues
```

Update `__init__()` to build the dependency graph (after line 593, before line 595):
```python
# Build dependency graph for dependency-aware sequencing
all_issues = find_issues(self.config, self.category)
self.dep_graph = DependencyGraph.from_issues(all_issues)

# Warn about any cycles
if self.dep_graph.has_cycles():
    cycles = self.dep_graph.detect_cycles()
    for cycle in cycles:
        self.logger.warning(f"Dependency cycle detected: {' -> '.join(cycle)}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`

**Manual Verification**:
- [ ] Create issues with a cycle (A blocked by B, B blocked by A), run ll-auto, verify warning appears

---

### Phase 2: Add Dependency-Aware Issue Selection Method

#### Overview
Add a `_get_next_issue()` method that uses `DependencyGraph.get_ready_issues()` instead of `find_highest_priority_issue()`.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
**Changes**: Add new method after `_signal_handler()` (around line 600)

```python
def _get_next_issue(self) -> IssueInfo | None:
    """Get next issue respecting dependencies.

    Returns the highest priority issue whose blockers have all been
    completed. If no ready issues exist but blocked issues remain,
    logs warnings about what is blocking progress.

    Returns:
        Next IssueInfo to process, or None if no ready issues
    """
    # Get completed issues from state
    completed = set(self.state_manager.state.completed_issues)

    # Combine skip_ids from state and CLI argument
    skip_ids = self.state_manager.state.attempted_issues | self.skip_ids

    # Get issues that are ready (blockers satisfied)
    ready_issues = self.dep_graph.get_ready_issues(completed)

    # Filter by skip_ids, only_ids, category
    candidates = [
        i for i in ready_issues
        if i.issue_id not in skip_ids
        and (self.only_ids is None or i.issue_id in self.only_ids)
    ]

    if candidates:
        return candidates[0]  # Already sorted by priority in get_ready_issues()

    # No ready candidates - check if there are blocked issues remaining
    all_in_graph = set(self.dep_graph.issues.keys())
    remaining = all_in_graph - completed - skip_ids
    if self.only_ids is not None:
        remaining = remaining & self.only_ids

    if remaining:
        self._log_blocked_issues(remaining, completed)

    return None

def _log_blocked_issues(self, remaining: set[str], completed: set[str]) -> None:
    """Log information about blocked issues when processing stalls.

    Args:
        remaining: Set of issue IDs that haven't been processed
        completed: Set of completed issue IDs
    """
    blocked_count = 0
    for issue_id in remaining:
        blockers = self.dep_graph.get_blocking_issues(issue_id, completed)
        if blockers:
            blocked_count += 1
            self.logger.info(f"  {issue_id} blocked by: {', '.join(sorted(blockers))}")

    if blocked_count > 0:
        self.logger.warning(f"{blocked_count} issue(s) remain blocked - check dependencies")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`

**Manual Verification**:
- [ ] Method signature and docstring are correct

---

### Phase 3: Update Main Loop to Use Dependency-Aware Selection

#### Overview
Replace the `find_highest_priority_issue()` call in `run()` with the new `_get_next_issue()` method.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
**Changes**: Update the main loop in `run()` at lines 639-646

Replace:
```python
# Combine skip_ids from state and CLI argument
skip_ids = self.state_manager.state.attempted_issues | self.skip_ids
info = find_highest_priority_issue(
    self.config, self.category, skip_ids, self.only_ids
)
if not info:
    self.logger.success("No more issues to process!")
    break
```

With:
```python
info = self._get_next_issue()
if not info:
    self.logger.success("No more issues to process!")
    break
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_manager.py`

**Manual Verification**:
- [ ] Run ll-auto with independent issues - behavior unchanged
- [ ] Run ll-auto with dependent issues - processes in correct order

---

### Phase 4: Add Integration Tests

#### Overview
Add tests for dependency-aware sequencing behavior.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`
**Changes**: Add new test class for dependency-aware sequencing

```python
class TestDependencyAwareSequencing:
    """Tests for dependency-aware issue selection in AutoManager."""

    @pytest.fixture
    def temp_project_with_deps(self, temp_project_dir: Path) -> Path:
        """Set up project with issues that have dependencies."""
        import json

        # Create .claude directory with config
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir(exist_ok=True)

        config_content = {
            "project": {"name": "test-project"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    }
                },
                "completed_dir": "completed",
            },
            "automation": {
                "timeout_seconds": 60,
                "state_file": ".auto-manage-state.json",
            },
        }
        (claude_dir / "ll-config.json").write_text(json.dumps(config_content))

        # Create issues directory
        issues_dir = temp_project_dir / ".issues" / "features"
        issues_dir.mkdir(parents=True)
        (temp_project_dir / ".issues" / "completed").mkdir()

        # Create FEAT-001 (no dependencies)
        (issues_dir / "P1-FEAT-001-first-feature.md").write_text(
            "# FEAT-001: First Feature\n\n## Summary\nFirst\n"
        )

        # Create FEAT-002 (blocked by FEAT-001)
        (issues_dir / "P1-FEAT-002-second-feature.md").write_text(
            "# FEAT-002: Second Feature\n\n## Summary\nSecond\n\n## Blocked By\n\n- FEAT-001\n"
        )

        return temp_project_dir

    def test_dependency_graph_built_on_init(self, temp_project_with_deps: Path) -> None:
        """Test that AutoManager builds dependency graph on initialization."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig.from_project_root(temp_project_with_deps)
        manager = AutoManager(config, dry_run=True)

        assert hasattr(manager, "dep_graph")
        assert len(manager.dep_graph) == 2
        assert "FEAT-001" in manager.dep_graph
        assert "FEAT-002" in manager.dep_graph

    def test_blocked_issue_not_selected_first(self, temp_project_with_deps: Path) -> None:
        """Test that blocked issue is not selected before its blocker."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig.from_project_root(temp_project_with_deps)
        manager = AutoManager(config, dry_run=True)

        # First issue selected should be FEAT-001 (not blocked)
        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-001"

    def test_blocked_issue_selected_after_blocker_completed(
        self, temp_project_with_deps: Path
    ) -> None:
        """Test that blocked issue becomes available after blocker completes."""
        from little_loops.config import BRConfig
        from little_loops.issue_manager import AutoManager

        config = BRConfig.from_project_root(temp_project_with_deps)
        manager = AutoManager(config, dry_run=True)

        # Mark FEAT-001 as completed
        manager.state_manager.state.completed_issues.append("FEAT-001")

        # Now FEAT-002 should be selected
        info = manager._get_next_issue()
        assert info is not None
        assert info.issue_id == "FEAT-002"
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestDependencyAwareSequencing -v`
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_manager.py`

**Manual Verification**:
- [ ] Review test coverage for edge cases

---

## Testing Strategy

### Unit Tests
- Test `_get_next_issue()` returns correct issue based on dependencies
- Test cycle detection warning on startup
- Test blocked issue logging when stalled

### Integration Tests
- Test full workflow: process FEAT-001, then FEAT-002 becomes available
- Test with all issues blocked (should log warnings)
- Test with cycles (should warn but not crash)

## References

- Original issue: `.issues/enhancements/P2-ENH-016-dependency-aware-sequencing-ll-auto.md`
- DependencyGraph class: `scripts/little_loops/dependency_graph.py:21-319`
- ll-sprint integration pattern: `scripts/little_loops/cli.py:1640-1668`
- Existing tests: `scripts/tests/test_dependency_graph.py`
