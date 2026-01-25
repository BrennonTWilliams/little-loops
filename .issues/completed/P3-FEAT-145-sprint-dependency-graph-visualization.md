---
discovered_date: 2026-01-25
discovered_by: capture_issue
---

# FEAT-145: Sprint Dependency Graph Visualization

## Summary

Enhance `ll-sprint show <sprint-name>` to output an organized visual depiction of issues in the sprint with their execution order, clearly showing which issues run in parallel vs sequential waves based on dependency relationships.

## Context

User description: "Create a new command to visualize a sprint + its dependency graph by running `ll-sprint show sprint-name` - this should output an organized visual depiction of the Issues in the sprint and their execution order, including which are parallel vs sequential"

The `ll-sprint show` command currently displays a simple flat list of issues without any dependency or execution order information. With ENH-144's dependency-aware wave execution now implemented, users need visibility into how their sprint will actually execute.

## Current Behavior

```bash
$ ll-sprint show sprint-1
Sprint: sprint-1
Description: Q1 Performance and Security Improvements
Created: 2026-01-14
Issues (4):
  - BUG-001 (valid)
  - BUG-002 (valid)
  - FEAT-010 (valid)
  - FEAT-015 (valid)
Options:
  Mode: auto
  Max iterations: 100
  Timeout: 3600s
  Max workers: 4
```

## Expected Behavior

```bash
$ ll-sprint show sprint-1
Sprint: sprint-1
Description: Q1 Performance and Security Improvements
Created: 2026-01-14

================================================================================
EXECUTION PLAN (4 issues, 3 waves)
================================================================================

Wave 1 (parallel):
  ├── BUG-001: Fix critical crash on startup (P0)
  └── FEAT-010: Add user settings page (P2)

Wave 2 (after Wave 1):
  └── BUG-002: Settings page validation error (P2)
      └── blocked by: FEAT-010

Wave 3 (after Wave 2):
  └── FEAT-015: Dark mode support (P3)
      └── blocked by: BUG-002

================================================================================
DEPENDENCY GRAPH
================================================================================

  BUG-001 ─────────────────────────────────┐
                                           ├──→ (complete)
  FEAT-010 ──→ BUG-002 ──→ FEAT-015 ──────┘

Legend: ──→ blocks (must complete before)

================================================================================
```

## Proposed Solution

### 1. Add `--graph` flag (optional, or make default)

Enhance `_cmd_sprint_show()` to:
1. Load issue files to get `IssueInfo` objects with `blocked_by` relationships
2. Build dependency graph using existing `DependencyGraph` class
3. Compute execution waves using `get_execution_waves()`
4. Render visual output showing wave structure and dependencies

### 2. Visualization Format

**Wave Display:**
- Group issues by execution wave
- Use tree-style characters (├── └──) for visual hierarchy
- Show issue ID, title (truncated), and priority
- For blocked issues, show "blocked by: [IDs]"

**Dependency Graph:**
- ASCII art showing dependency chains
- Parallel issues on same line or stacked
- Arrows (──→) indicating "blocks" relationships
- Legend explaining notation

### 3. Implementation Location

Modify `scripts/little_loops/cli.py`:
- Update `_cmd_sprint_show()` to include dependency visualization
- Use existing `DependencyGraph.from_issues()` and `get_execution_waves()`
- Add helper function `_render_sprint_graph()` for ASCII visualization

## Impact

- **Priority**: P3 - Quality of life improvement
- **Effort**: Low - Uses existing DependencyGraph infrastructure
- **Risk**: Low - Enhancement to existing command output

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| implementation | scripts/little_loops/dependency_graph.py | Provides DependencyGraph class and get_execution_waves() |
| implementation | scripts/little_loops/cli.py | Contains _cmd_sprint_show() to enhance |

## Blocked By

None

## Blocks

None

## Labels

`feature`, `cli`, `ll-sprint`, `visualization`, `dependency-management`

---

## Status

**Open** | Created: 2026-01-25 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-25
- **Status**: Completed

### Changes Made
- scripts/little_loops/cli.py: Added `_render_execution_plan()` and `_render_dependency_graph()` functions
- scripts/little_loops/cli.py: Enhanced `_cmd_sprint_show()` to display dependency visualization
- scripts/tests/test_cli.py: Added `TestSprintShowDependencyVisualization` test class with 6 tests

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS
