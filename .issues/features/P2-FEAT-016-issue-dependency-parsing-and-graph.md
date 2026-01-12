---
discovered_commit: 8279174
discovered_branch: main
discovered_date: 2026-01-12T00:00:00Z
---

# FEAT-016: Issue Dependency Parsing and Graph Construction

## Summary

Add infrastructure to parse `Blocked By` and `Blocks` sections from issue markdown files and construct a dependency graph (DAG) that can be used by `ll-auto` and `ll-parallel` to sequence issue processing correctly.

## Motivation

Issue files already include dependency metadata:

```markdown
## Blocked By
- FEAT-001
- FEAT-002

## Blocks
- FEAT-004
- ENH-005
```

However, the CLI tools (`ll-auto`, `ll-parallel`) completely ignore this metadata. They process issues strictly by priority level (P0 > P1 > ... > P5) with FIFO ordering within the same priority.

This leads to potential problems:
1. An issue may be worked on before its prerequisites are complete
2. `ll-parallel` may process dependent issues concurrently, causing conflicts
3. Completed prerequisites don't automatically unblock dependent issues

## Proposed Implementation

### 1. Extend `IssueInfo` Dataclass

Update `scripts/little_loops/issue_parser.py`:

```python
@dataclass
class IssueInfo:
    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)  # NEW
    blocks: list[str] = field(default_factory=list)       # NEW
```

### 2. Add Dependency Parsing to `IssueParser`

Add methods to `IssueParser` class:

```python
def _parse_blocked_by(self, content: str) -> list[str]:
    """Extract issue IDs from ## Blocked By section."""
    # Match section and extract issue IDs (e.g., FEAT-001, BUG-123)
    ...

def _parse_blocks(self, content: str) -> list[str]:
    """Extract issue IDs from ## Blocks section."""
    ...
```

Update `parse_file()` to call these methods and populate the new fields.

### 3. Create Dependency Graph Module

New file: `scripts/little_loops/dependency_graph.py`

```python
from dataclasses import dataclass
from little_loops.issue_parser import IssueInfo

@dataclass
class DependencyGraph:
    """Directed acyclic graph of issue dependencies."""

    issues: dict[str, IssueInfo]  # issue_id -> IssueInfo
    blocked_by: dict[str, set[str]]  # issue_id -> set of blocking issue_ids
    blocks: dict[str, set[str]]  # issue_id -> set of blocked issue_ids

    @classmethod
    def from_issues(cls, issues: list[IssueInfo]) -> "DependencyGraph":
        """Build graph from list of issues."""
        ...

    def get_ready_issues(self, completed: set[str]) -> list[IssueInfo]:
        """Return issues whose blockers are all completed."""
        ...

    def topological_sort(self) -> list[IssueInfo]:
        """Return issues in dependency order (Kahn's algorithm)."""
        ...

    def detect_cycles(self) -> list[list[str]]:
        """Detect and return any dependency cycles."""
        ...

    def is_blocked(self, issue_id: str, completed: set[str]) -> bool:
        """Check if an issue is still blocked."""
        ...

    def get_blocking_issues(self, issue_id: str, completed: set[str]) -> set[str]:
        """Return incomplete issues blocking this one."""
        ...
```

### 4. Handle Missing/Completed Dependencies

When building the graph:
- If a `blocked_by` issue ID doesn't exist in active issues, check if it's in `completed/`
- If blocker is completed, treat as satisfied (not blocking)
- If blocker doesn't exist anywhere, log warning but don't block

### 5. Cycle Detection and Reporting

Implement cycle detection to prevent infinite loops:

```python
def detect_cycles(self) -> list[list[str]]:
    """Use DFS to find cycles in the dependency graph."""
    # Returns list of cycles, each cycle is a list of issue IDs
    # e.g., [["FEAT-001", "FEAT-002", "FEAT-001"]]
```

When cycles are detected:
- Log a clear warning with the cycle path
- Break cycles by ignoring the back-edge (last dependency in cycle)
- Continue processing with degraded dependency ordering

## Location

- **Modified**: `scripts/little_loops/issue_parser.py` (extend IssueInfo, add parsing)
- **New File**: `scripts/little_loops/dependency_graph.py` (graph construction and algorithms)

## Current Behavior

- `IssueInfo` only contains: `path`, `issue_type`, `priority`, `issue_id`, `title`
- `find_issues()` sorts by `(priority_int, issue_id)` only
- `IssuePriorityQueue` orders by priority with FIFO within same priority
- `Blocked By` and `Blocks` sections exist in issue files but are ignored

## Expected Behavior

- `IssueInfo` includes `blocked_by` and `blocks` lists
- `DependencyGraph` can be constructed from issues
- Graph provides methods for topological sort and ready-issue queries
- Cycles are detected and handled gracefully

## Acceptance Criteria

- [ ] `IssueInfo` dataclass extended with `blocked_by` and `blocks` fields
- [ ] `IssueParser._parse_blocked_by()` extracts issue IDs from markdown
- [ ] `IssueParser._parse_blocks()` extracts issue IDs from markdown
- [ ] `DependencyGraph.from_issues()` builds graph correctly
- [ ] `DependencyGraph.topological_sort()` returns valid ordering
- [ ] `DependencyGraph.get_ready_issues()` respects completed set
- [ ] `DependencyGraph.detect_cycles()` finds cycles if present
- [ ] Completed dependencies are correctly resolved
- [ ] Missing dependencies logged as warnings
- [ ] Unit tests cover all graph operations
- [ ] Integration test with sample issues having dependencies

## Impact

- **Severity**: High - Foundation for dependency-aware processing
- **Effort**: Medium - New module with well-defined algorithms
- **Risk**: Low - Purely additive, existing behavior unchanged until integrated

## Dependencies

None - this is foundational infrastructure.

## Blocked By

None

## Blocks

- ENH-016: Dependency-Aware Sequencing in ll-auto
- ENH-017: Dependency-Aware Scheduling in ll-parallel

## Labels

`feature`, `cli`, `infrastructure`, `dependency-management`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2
