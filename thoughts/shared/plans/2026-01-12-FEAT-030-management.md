# FEAT-030: Issue Dependency Parsing and Graph Construction - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-030-issue-dependency-parsing-and-graph.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The issue parser infrastructure currently extracts basic metadata from issue markdown files:
- Priority (P0-P5) from filename prefix
- Issue ID (BUG-123, FEAT-001, etc.) from filename
- Issue type (bugs, features, enhancements) from directory or prefix
- Title from markdown `# ISSUE-ID: Title` header

### Key Discoveries
- `IssueInfo` dataclass at `issue_parser.py:70-116` has 5 fields: `path`, `issue_type`, `priority`, `issue_id`, `title`
- `IssueParser.parse_file()` at `issue_parser.py:140-166` reads file content only for title extraction
- `_parse_title()` at `issue_parser.py:243-265` reads file content using `Path.read_text()`
- Sorting at `issue_parser.py:319` is strictly by `(priority_int, issue_id)` - no dependency awareness
- Existing section parsing pattern in `parallel/output_parsing.py:16-19` uses `re.compile()` with `MULTILINE` flag
- `to_dict()`/`from_dict()` serialization pattern exists at `issue_parser.py:97-116`

### Patterns to Follow
- Section parsing: `SECTION_PATTERN = re.compile(r"^#{1,3}\s*\**(\w+)\**\s*$", re.MULTILINE)` from `output_parsing.py`
- Issue ID extraction: `rf"({prefix})-(\d+)"` pattern from `issue_parser.py:206`
- Dataclass with list defaults: `field(default_factory=list)` from `parallel/types.py:52-88`
- Test patterns: Create temp files with test data, use pytest fixtures from `test_issue_parser.py`

## Desired End State

- `IssueInfo` dataclass includes `blocked_by: list[str]` and `blocks: list[str]` fields
- `IssueParser` extracts dependency information from `## Blocked By` and `## Blocks` sections
- New `DependencyGraph` class provides:
  - Graph construction from list of issues
  - Topological sorting (Kahn's algorithm)
  - Cycle detection (DFS-based)
  - Ready issue queries (blockers resolved)
  - Blocking issue queries

### How to Verify
- Unit tests pass for all parsing methods
- Unit tests pass for all graph operations
- Existing tests still pass (backward compatibility)
- Type checking passes with new fields

## What We're NOT Doing

- Not integrating with `ll-auto` or `ll-parallel` - deferred to ENH-016/ENH-017
- Not changing any CLI behavior - purely additive infrastructure
- Not adding UI/logging for dependency status
- Not modifying `IssuePriorityQueue` ordering

## Problem Analysis

Issue files already contain dependency metadata in markdown sections:

```markdown
## Blocked By
- FEAT-001
- FEAT-002

## Blocks
- FEAT-004
- ENH-005
```

The parser currently ignores this metadata. We need to:
1. Parse these sections from file content
2. Extract issue IDs from list items
3. Store in `IssueInfo` for downstream use
4. Build a graph structure for dependency queries

## Solution Approach

1. Extend `IssueInfo` with dependency fields (using `field(default_factory=list)`)
2. Add section parsing methods to `IssueParser` using regex patterns
3. Update `parse_file()` to populate dependency fields
4. Update `to_dict()`/`from_dict()` for serialization
5. Create new `dependency_graph.py` module with `DependencyGraph` class
6. Implement graph algorithms: topological sort, cycle detection
7. Add comprehensive unit tests

## Implementation Phases

### Phase 1: Extend IssueInfo Dataclass

#### Overview
Add `blocked_by` and `blocks` fields to `IssueInfo`, update serialization methods.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Changes**: Add two new fields with defaults, update `to_dict()` and `from_dict()`

```python
from dataclasses import dataclass, field

@dataclass
class IssueInfo:
    # ... existing fields ...
    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)  # NEW
    blocks: list[str] = field(default_factory=list)       # NEW

    def to_dict(self) -> dict[str, Any]:
        return {
            # ... existing keys ...
            "blocked_by": self.blocked_by,  # NEW
            "blocks": self.blocks,           # NEW
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueInfo:
        return cls(
            # ... existing args ...
            blocked_by=data.get("blocked_by", []),  # NEW
            blocks=data.get("blocks", []),           # NEW
        )
```

#### Success Criteria

**Automated Verification**:
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/issue_parser.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_parser.py`

---

### Phase 2: Add Dependency Parsing Methods

#### Overview
Add `_parse_blocked_by()` and `_parse_blocks()` methods to `IssueParser`, update `parse_file()`.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Changes**: Add two parsing methods, update `parse_file()` to call them

```python
# Regex pattern for issue IDs in list items
# Matches: "- FEAT-001", "- BUG-123", "* ENH-005"
ISSUE_ID_PATTERN = re.compile(r"^[-*]\s+([A-Z]+-\d+)", re.MULTILINE)

class IssueParser:
    def parse_file(self, issue_path: Path) -> IssueInfo:
        filename = issue_path.name
        priority = self._parse_priority(filename)
        issue_type, issue_id = self._parse_type_and_id(filename, issue_path)

        # Read content once for all parsing
        content = self._read_content(issue_path)
        title = self._parse_title_from_content(content, issue_path)
        blocked_by = self._parse_blocked_by(content)
        blocks = self._parse_blocks(content)

        return IssueInfo(
            path=issue_path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
        )

    def _read_content(self, issue_path: Path) -> str:
        """Read file content, returning empty string on error."""
        try:
            return issue_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _parse_section_items(self, content: str, section_name: str) -> list[str]:
        """Extract issue IDs from a markdown section.

        Finds section header (## Section Name) and extracts issue IDs
        from list items until the next section or end of file.
        """
        # Match section header case-insensitively
        section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
        match = re.search(section_pattern, content, re.MULTILINE | re.IGNORECASE)
        if not match:
            return []

        # Get content after section header until next ## header or end
        start = match.end()
        next_section = re.search(r"^##\s+", content[start:], re.MULTILINE)
        if next_section:
            section_content = content[start:start + next_section.start()]
        else:
            section_content = content[start:]

        # Extract issue IDs from list items
        issue_ids = ISSUE_ID_PATTERN.findall(section_content)
        return issue_ids

    def _parse_blocked_by(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocked By section."""
        return self._parse_section_items(content, "Blocked By")

    def _parse_blocks(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocks section."""
        return self._parse_section_items(content, "Blocks")
```

Note: Refactor `_parse_title()` to use pre-read content instead of re-reading.

#### Success Criteria

**Automated Verification**:
- [ ] New parsing tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v -k "blocked" or -k "blocks"`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/issue_parser.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_parser.py`

---

### Phase 3: Create DependencyGraph Module

#### Overview
Create new module with `DependencyGraph` class implementing graph construction and algorithms.

#### Changes Required

**File**: `scripts/little_loops/dependency_graph.py` (NEW)
**Changes**: Full implementation of `DependencyGraph` class

```python
"""Dependency graph for issue management.

Constructs a directed acyclic graph (DAG) from issue dependencies,
providing topological sorting and cycle detection.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)


@dataclass
class DependencyGraph:
    """Directed acyclic graph of issue dependencies.

    Attributes:
        issues: Mapping from issue_id to IssueInfo
        blocked_by: Mapping from issue_id to set of blocking issue_ids
        blocks: Mapping from issue_id to set of blocked issue_ids
    """

    issues: dict[str, IssueInfo] = field(default_factory=dict)
    blocked_by: dict[str, set[str]] = field(default_factory=dict)
    blocks: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_issues(
        cls,
        issues: list[IssueInfo],
        completed_ids: set[str] | None = None,
    ) -> DependencyGraph:
        """Build graph from list of issues.

        Args:
            issues: List of IssueInfo objects
            completed_ids: Set of completed issue IDs (treated as resolved)

        Returns:
            Constructed DependencyGraph
        """
        completed = completed_ids or set()
        graph = cls()

        # Index all issues by ID
        for issue in issues:
            graph.issues[issue.issue_id] = issue
            graph.blocked_by[issue.issue_id] = set()
            graph.blocks[issue.issue_id] = set()

        # Build dependency edges
        all_issue_ids = set(graph.issues.keys())
        for issue in issues:
            for blocker_id in issue.blocked_by:
                # Skip completed blockers (satisfied)
                if blocker_id in completed:
                    continue
                # Skip missing blockers with warning
                if blocker_id not in all_issue_ids:
                    logger.warning(
                        f"Issue {issue.issue_id} blocked by unknown issue {blocker_id}"
                    )
                    continue
                # Add edge
                graph.blocked_by[issue.issue_id].add(blocker_id)
                graph.blocks[blocker_id].add(issue.issue_id)

        return graph

    def get_ready_issues(self, completed: set[str] | None = None) -> list[IssueInfo]:
        """Return issues whose blockers are all completed.

        Args:
            completed: Set of completed issue IDs

        Returns:
            List of IssueInfo for issues with no active blockers
        """
        completed = completed or set()
        ready = []
        for issue_id, issue in self.issues.items():
            if issue_id in completed:
                continue
            blockers = self.get_blocking_issues(issue_id, completed)
            if not blockers:
                ready.append(issue)
        return ready

    def is_blocked(self, issue_id: str, completed: set[str] | None = None) -> bool:
        """Check if an issue is still blocked.

        Args:
            issue_id: Issue ID to check
            completed: Set of completed issue IDs

        Returns:
            True if issue has unresolved blockers
        """
        return bool(self.get_blocking_issues(issue_id, completed))

    def get_blocking_issues(
        self, issue_id: str, completed: set[str] | None = None
    ) -> set[str]:
        """Return incomplete issues blocking this one.

        Args:
            issue_id: Issue ID to check
            completed: Set of completed issue IDs

        Returns:
            Set of issue IDs still blocking this issue
        """
        completed = completed or set()
        blockers = self.blocked_by.get(issue_id, set())
        return blockers - completed

    def topological_sort(self) -> list[IssueInfo]:
        """Return issues in dependency order (Kahn's algorithm).

        Issues with no dependencies come first, followed by issues
        whose dependencies have been satisfied.

        Returns:
            List of IssueInfo in topological order

        Raises:
            ValueError: If graph contains cycles
        """
        # Calculate in-degree for each node
        in_degree: dict[str, int] = {
            issue_id: len(blockers)
            for issue_id, blockers in self.blocked_by.items()
        }

        # Start with nodes that have no blockers
        queue: deque[str] = deque(
            issue_id for issue_id, degree in in_degree.items() if degree == 0
        )

        result: list[IssueInfo] = []
        while queue:
            issue_id = queue.popleft()
            result.append(self.issues[issue_id])

            # Reduce in-degree for nodes this one blocks
            for blocked_id in self.blocks.get(issue_id, set()):
                in_degree[blocked_id] -= 1
                if in_degree[blocked_id] == 0:
                    queue.append(blocked_id)

        # Check for cycles
        if len(result) != len(self.issues):
            cycles = self.detect_cycles()
            cycle_str = ", ".join(
                " -> ".join(cycle) for cycle in cycles
            )
            raise ValueError(f"Dependency graph contains cycles: {cycle_str}")

        return result

    def detect_cycles(self) -> list[list[str]]:
        """Detect and return any dependency cycles.

        Uses DFS to find back edges indicating cycles.

        Returns:
            List of cycles, each cycle is a list of issue IDs
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {issue_id: WHITE for issue_id in self.issues}
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)

            for neighbor in self.blocked_by.get(node, set()):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found cycle - extract from path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                elif color[neighbor] == WHITE:
                    dfs(neighbor)

            path.pop()
            color[node] = BLACK

        for issue_id in self.issues:
            if color[issue_id] == WHITE:
                dfs(issue_id)

        return cycles
```

#### Success Criteria

**Automated Verification**:
- [ ] New module tests pass: `python -m pytest scripts/tests/test_dependency_graph.py -v`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/dependency_graph.py`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_graph.py`

---

### Phase 4: Write Unit Tests

#### Overview
Comprehensive tests for dependency parsing and graph operations.

#### Changes Required

**File**: `scripts/tests/test_issue_parser.py`
**Changes**: Add tests for dependency parsing

```python
class TestDependencyParsing:
    """Tests for dependency parsing in IssueParser."""

    def test_parse_blocked_by_single(self, temp_project_dir, sample_config):
        """Test parsing single blocker."""
        # Setup and create issue file with ## Blocked By section
        ...

    def test_parse_blocked_by_multiple(self, temp_project_dir, sample_config):
        """Test parsing multiple blockers."""
        ...

    def test_parse_blocked_by_empty(self, temp_project_dir, sample_config):
        """Test parsing when no Blocked By section exists."""
        ...

    def test_parse_blocks_section(self, temp_project_dir, sample_config):
        """Test parsing ## Blocks section."""
        ...

    def test_dependency_fields_in_serialization(self, temp_project_dir, sample_config):
        """Test that blocked_by and blocks survive to_dict/from_dict roundtrip."""
        ...
```

**File**: `scripts/tests/test_dependency_graph.py` (NEW)
**Changes**: Full test suite for DependencyGraph

```python
class TestDependencyGraphConstruction:
    """Tests for DependencyGraph.from_issues()."""
    ...

class TestTopologicalSort:
    """Tests for topological sorting."""
    ...

class TestCycleDetection:
    """Tests for cycle detection."""
    ...

class TestReadyIssues:
    """Tests for get_ready_issues()."""
    ...
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Coverage adequate for new code

---

## Testing Strategy

### Unit Tests
- Parsing empty/missing sections returns empty list
- Parsing sections with various formats (bullets, asterisks)
- Parsing handles mixed case section headers
- Serialization roundtrip preserves dependency data
- Graph construction handles missing/completed blockers
- Topological sort produces valid ordering
- Cycle detection finds all cycles
- Ready issue filtering respects completed set

### Integration Tests
- Parse real issue files from `.issues/` directory
- Build graph from multiple interconnected issues
- Verify FEAT-030's own dependencies are parsed correctly

## References

- Original issue: `.issues/features/P2-FEAT-030-issue-dependency-parsing-and-graph.md`
- Section parsing pattern: `scripts/little_loops/parallel/output_parsing.py:16-19`
- Dataclass pattern: `scripts/little_loops/parallel/types.py:52-88`
- Existing parser: `scripts/little_loops/issue_parser.py:70-266`
- Existing tests: `scripts/tests/test_issue_parser.py`
