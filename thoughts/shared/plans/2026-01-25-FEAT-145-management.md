# FEAT-145: Sprint Dependency Graph Visualization - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-145-sprint-dependency-graph-visualization.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `_cmd_sprint_show()` function in `cli.py:1413-1444` currently displays a flat list of issues with basic validation status. It does not leverage the existing `DependencyGraph` infrastructure or `get_execution_waves()` method.

### Key Discoveries
- `DependencyGraph.from_issues()` at `dependency_graph.py:42-91` builds graph from `IssueInfo` objects
- `DependencyGraph.get_execution_waves()` at `dependency_graph.py:119-166` returns `list[list[IssueInfo]]` grouped by parallel execution wave
- `SprintManager.load_issue_infos()` at `sprint.py:279-307` loads full `IssueInfo` objects with `blocked_by` relationships
- The `_cmd_sprint_run()` function at `cli.py:1481-1534` already demonstrates the complete dependency analysis flow
- Output formatting patterns in `issue_history.py:1067-1107` use `=` for main headers and `-` for subsections
- The codebase uses tree characters (`├──`, `└──`) in the logo and proposed output

## Desired End State

Running `ll-sprint show <sprint-name>` produces:
1. Basic sprint metadata (name, description, created)
2. An **Execution Plan** section showing issues grouped by wave with dependency info
3. An **ASCII Dependency Graph** showing visual representation of issue relationships
4. The existing options section (unchanged)

### How to Verify
- Running `ll-sprint show sprint-1` shows execution waves
- Issues blocked by others show their blockers
- Wave count and parallel/sequential grouping are accurate
- Cycle detection produces error message
- Missing issues are handled gracefully

## What We're NOT Doing

- Not adding a `--graph` flag (visualization is always shown when dependencies exist)
- Not changing the sprint YAML format
- Not modifying `DependencyGraph` class (reusing existing methods)
- Not adding Mermaid or external diagram formats (ASCII only)

## Problem Analysis

Users cannot visualize how their sprint will execute. The `show` command provides no insight into:
- Which issues will run in parallel
- Which issues are blocked and by what
- The total number of execution waves
- The dependency chain between issues

## Solution Approach

Enhance `_cmd_sprint_show()` to:
1. Load full `IssueInfo` objects (like `_cmd_sprint_run()` does)
2. Build `DependencyGraph` and compute execution waves
3. Render new output sections showing waves and dependency relationships
4. Keep existing basic metadata output unchanged

## Implementation Phases

### Phase 1: Add Dependency Loading to Sprint Show

#### Overview
Modify `_cmd_sprint_show()` to load issue info and build dependency graph when issues are valid.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add issue info loading and dependency graph construction

After line 1423 (after validation), add:

```python
    # Load full IssueInfo objects for dependency analysis
    issue_infos = manager.load_issue_infos(list(valid.keys()))
    dep_graph = None
    waves: list[list[IssueInfo]] = []

    if issue_infos:
        from little_loops.dependency_graph import DependencyGraph
        dep_graph = DependencyGraph.from_issues(issue_infos)

        # Check for cycles
        if not dep_graph.has_cycles():
            waves = dep_graph.get_execution_waves()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Running `ll-sprint show` with valid sprint still works
- [ ] No crashes when sprint has invalid/missing issues

---

### Phase 2: Implement Wave Rendering Function

#### Overview
Add helper function `_render_execution_plan()` to format waves with tree-style output.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add new rendering function before `_cmd_sprint_show()`

```python
def _render_execution_plan(
    waves: list[list[IssueInfo]],
    dep_graph: DependencyGraph,
) -> str:
    """Render execution plan with wave groupings.

    Args:
        waves: List of execution waves from get_execution_waves()
        dep_graph: DependencyGraph for looking up blockers

    Returns:
        Formatted string showing wave structure
    """
    if not waves:
        return ""

    total_issues = sum(len(wave) for wave in waves)
    lines: list[str] = []

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"EXECUTION PLAN ({total_issues} issues, {len(waves)} waves)")
    lines.append("=" * 70)

    for wave_num, wave in enumerate(waves, 1):
        lines.append("")
        parallel_note = "(parallel)" if len(wave) > 1 else ""
        if wave_num > 1:
            parallel_note = f"(after Wave {wave_num - 1})"
            if len(wave) > 1:
                parallel_note += " parallel"
        lines.append(f"Wave {wave_num} {parallel_note}:".strip())

        for i, issue in enumerate(wave):
            is_last = i == len(wave) - 1
            prefix = "  └── " if is_last else "  ├── "

            # Truncate title if too long
            title = issue.title
            if len(title) > 45:
                title = title[:42] + "..."

            lines.append(f"{prefix}{issue.issue_id}: {title} ({issue.priority})")

            # Show blockers for this issue
            blockers = dep_graph.blocked_by.get(issue.issue_id, set())
            if blockers:
                blocker_prefix = "      └── " if is_last else "  │   └── "
                blockers_str = ", ".join(sorted(blockers))
                lines.append(f"{blocker_prefix}blocked by: {blockers_str}")

    return "\n".join(lines)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Function renders correctly formatted output when called directly

---

### Phase 3: Implement Dependency Graph Rendering

#### Overview
Add helper function `_render_dependency_graph()` for ASCII visualization of dependencies.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add dependency graph rendering function

```python
def _render_dependency_graph(
    waves: list[list[IssueInfo]],
    dep_graph: DependencyGraph,
) -> str:
    """Render ASCII dependency graph.

    Args:
        waves: List of execution waves
        dep_graph: DependencyGraph for looking up relationships

    Returns:
        Formatted string showing dependency arrows
    """
    if not waves or len(waves) <= 1:
        return ""

    lines: list[str] = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("DEPENDENCY GRAPH")
    lines.append("=" * 70)
    lines.append("")

    # Build chains: track which issues block what
    # Show each independent chain on its own line

    # Find root issues (no blockers in this graph)
    roots: list[str] = []
    for wave in waves[:1]:  # First wave has roots
        for issue in wave:
            roots.append(issue.issue_id)

    # Build chain strings for each root
    chains: list[str] = []
    visited: set[str] = set()

    def build_chain(issue_id: str) -> str:
        """Recursively build chain string from issue."""
        if issue_id in visited:
            return ""
        visited.add(issue_id)

        blocked_issues = sorted(dep_graph.blocks.get(issue_id, set()))
        if not blocked_issues:
            return issue_id

        if len(blocked_issues) == 1:
            return f"{issue_id} ──→ {build_chain(blocked_issues[0])}"
        else:
            # Multiple branches - show first inline, note others
            result = f"{issue_id} ──→ {build_chain(blocked_issues[0])}"
            for other in blocked_issues[1:]:
                if other not in visited:
                    chains.append(f"  {issue_id} ──→ {build_chain(other)}")
            return result

    for root in roots:
        if root not in visited:
            chain = build_chain(root)
            if chain:
                chains.insert(0, f"  {chain}")

    # Handle any isolated issues not in chains
    all_ids = {issue.issue_id for wave in waves for issue in wave}
    for issue_id in sorted(all_ids - visited):
        chains.append(f"  {issue_id}")

    lines.extend(chains)
    lines.append("")
    lines.append("Legend: ──→ blocks (must complete before)")

    return "\n".join(lines)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Function renders chains correctly for test data

---

### Phase 4: Integrate Rendering into Sprint Show

#### Overview
Modify `_cmd_sprint_show()` to call rendering functions and output dependency visualization.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Update `_cmd_sprint_show()` to use new rendering functions

Replace the section that prints issues (lines 1428-1432) and add execution plan output:

```python
    print(f"Sprint: {sprint.name}")
    print(f"Description: {sprint.description or '(none)'}")
    print(f"Created: {sprint.created}")

    # Show execution plan if we have dependency info
    if waves:
        print(_render_execution_plan(waves, dep_graph))
        print(_render_dependency_graph(waves, dep_graph))
    else:
        # Fallback to simple list if no valid issues or cycles
        print(f"Issues ({len(sprint.issues)}):")
        for issue_id in sprint.issues:
            status = "valid" if issue_id in valid else "NOT FOUND"
            print(f"  - {issue_id} ({status})")

        # Warn about cycles if detected
        if dep_graph and dep_graph.has_cycles():
            cycles = dep_graph.detect_cycles()
            print("\nWarning: Dependency cycles detected:")
            for cycle in cycles:
                print(f"  {' -> '.join(cycle)}")

    # Show options (unchanged)
    if sprint.options:
        print("\nOptions:")
        print(f"  Mode: {sprint.options.mode}")
        # ... rest unchanged
```

Also need to add import at top of file:

```python
from little_loops.dependency_graph import DependencyGraph
```

And update type import:

```python
if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `ll-sprint show sprint-1` displays execution plan
- [ ] `ll-sprint show sprint-1` displays dependency graph
- [ ] Sprints with no dependencies show simple list
- [ ] Sprints with cycles show warning

---

### Phase 5: Add Unit Tests

#### Overview
Add tests for the new rendering functions and updated `_cmd_sprint_show()` behavior.

#### Changes Required

**File**: `scripts/tests/test_cli.py`
**Changes**: Add tests for sprint show dependency visualization

```python
class TestSprintShowDependencyVisualization:
    """Tests for sprint show dependency visualization."""

    def test_render_execution_plan_single_wave(self) -> None:
        """Single wave with multiple parallel issues."""
        # Create test issues with no dependencies
        issue1 = make_issue("BUG-001", priority="P0", title="Fix crash")
        issue2 = make_issue("FEAT-002", priority="P2", title="Add feature")

        from little_loops.dependency_graph import DependencyGraph
        graph = DependencyGraph.from_issues([issue1, issue2])
        waves = graph.get_execution_waves()

        from little_loops.cli import _render_execution_plan
        output = _render_execution_plan(waves, graph)

        assert "EXECUTION PLAN (2 issues, 1 waves)" in output
        assert "Wave 1" in output
        assert "BUG-001" in output
        assert "FEAT-002" in output

    def test_render_execution_plan_with_dependencies(self) -> None:
        """Multiple waves with dependencies."""
        issue1 = make_issue("FEAT-001", priority="P0")
        issue2 = make_issue("BUG-002", priority="P1", blocked_by=["FEAT-001"])

        from little_loops.dependency_graph import DependencyGraph
        graph = DependencyGraph.from_issues([issue1, issue2])
        waves = graph.get_execution_waves()

        from little_loops.cli import _render_execution_plan
        output = _render_execution_plan(waves, graph)

        assert "2 waves" in output
        assert "Wave 1" in output
        assert "Wave 2" in output
        assert "blocked by: FEAT-001" in output

    def test_render_dependency_graph_chain(self) -> None:
        """Dependency chain A -> B -> C."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P2", blocked_by=["FEAT-002"])

        from little_loops.dependency_graph import DependencyGraph
        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])
        waves = graph.get_execution_waves()

        from little_loops.cli import _render_dependency_graph
        output = _render_dependency_graph(waves, graph)

        assert "DEPENDENCY GRAPH" in output
        assert "FEAT-001" in output
        assert "──→" in output
        assert "Legend" in output
```

Note: Will need to add `make_issue` helper if not already available, or import from test_dependency_graph.

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_cli.py -v -k "SprintShowDependency"`
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Tests cover single wave, multi-wave, and dependency chain cases

---

## Testing Strategy

### Unit Tests
- `_render_execution_plan()` with various wave configurations
- `_render_dependency_graph()` with linear chains, diamond patterns, independent issues
- Edge cases: empty waves, single issue, all parallel, all sequential

### Integration Tests
- End-to-end `ll-sprint show` with real sprint files
- Verify cycle detection warning appears
- Verify missing issues handled gracefully

## References

- Original issue: `.issues/features/P3-FEAT-145-sprint-dependency-graph-visualization.md`
- Sprint run implementation: `cli.py:1481-1534`
- DependencyGraph class: `dependency_graph.py:21-319`
- Similar output formatting: `issue_history.py:1067-1107`
- Tree characters pattern: `assets/ll-cli-logo.txt`
