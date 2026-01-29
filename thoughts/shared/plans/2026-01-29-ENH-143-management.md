# ENH-143: Detect and Handle Overlapping File Modifications - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-143-detect-overlapping-file-modifications.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-parallel` system dispatches issues to workers without any pre-flight analysis of potential file overlaps:

### Key Discoveries
- Issues are dispatched based solely on priority and worker availability (`orchestrator.py:569-579`)
- Changed files ARE tracked after processing in `WorkerResult.changed_files` (`worker_pool.py:719-739`)
- No mechanism exists to predict file modifications before dispatch
- Merge conflicts are handled reactively via rebase retry logic (`merge_coordinator.py:915-1033`)
- The `DependencyGraph` class exists for explicit `blocked_by` relationships but not file-based inference

### Existing Patterns to Leverage
- `workflow_sequence_analyzer.py:49-56` - File path regex extraction from text
- `issue_parser.py` - Issue file parsing and metadata extraction
- `DependencyGraph` - Dependency tracking infrastructure
- `work_verification.py:18-41` - File filtering by excluded directories
- FEAT-049 defines `LockManager` and `_paths_overlap()` for scope-based detection (can adapt)

## Desired End State

Before dispatching issues, the orchestrator should:
1. Extract potential file hints from issue content (file paths mentioned)
2. Track which files are being modified by active workers
3. Detect overlapping file scopes between queued issues and active workers
4. Warn about or serialize issues with detected overlaps

### How to Verify
- Issues mentioning the same files are either serialized or warned about
- Merge conflict rate decreases when overlap detection is enabled
- No regression in processing speed for non-overlapping issues
- All tests pass

## What We're NOT Doing

- **Not implementing full scope-based locking** - That's FEAT-049's scope
- **Not implementing intelligent merge resolution** - Option C from the issue (deferred)
- **Not parsing code to determine actual file modifications** - Just using text hints
- **Not changing explicit dependency behavior** - `blocked_by` still works as-is
- **Not making this mandatory** - It's opt-in via configuration flag

## Problem Analysis

When multiple issues in `ll-parallel` modify the same files:
1. They're dispatched simultaneously without awareness of overlap
2. First completion merges successfully
3. Subsequent completions fail with rebase conflicts
4. Retry logic helps but often fails for complex conflicts
5. Manual intervention required, work potentially lost

The root cause is lack of **pre-dispatch overlap analysis**.

## Solution Approach

Implement **Option A (Pre-flight overlap detection)** from the issue, combined with **Option D (Dependency inference)** for serialization:

1. **FileHintExtractor** - Extract file paths from issue content
2. **OverlapDetector** - Track active issue scopes and detect conflicts
3. **Orchestrator integration** - Check for overlaps before dispatch, serialize if needed

This is additive (no breaking changes) and opt-in via config.

## Implementation Phases

### Phase 1: File Hint Extraction Module

#### Overview
Create a module to extract file path hints from issue content using regex patterns.

#### Changes Required

**File**: `scripts/little_loops/parallel/file_hints.py` (new)
**Changes**: Create new module for file hint extraction

```python
"""File hint extraction for overlap detection in parallel processing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# File path patterns - adapted from workflow_sequence_analyzer.py
FILE_PATH_PATTERN = re.compile(
    r"(?:^|[\s`\"'(])([a-zA-Z0-9_./\-]+\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|toml|sh|css|scss|html))",
    re.MULTILINE,
)

# Directory path patterns (paths ending with /)
DIR_PATH_PATTERN = re.compile(
    r"(?:^|[\s`\"'(])([a-zA-Z0-9_./\-]+/)",
    re.MULTILINE,
)

# Component/scope patterns from issue content
SCOPE_PATTERN = re.compile(
    r"(?:scope|component|module|directory|folder)[:\s]+[`\"']?([a-zA-Z0-9_./\-]+)[`\"']?",
    re.IGNORECASE,
)


@dataclass
class FileHints:
    """Extracted file hints from issue content.

    Attributes:
        files: Specific file paths mentioned
        directories: Directory paths mentioned
        scopes: Component/scope identifiers
        issue_id: Source issue ID
    """
    files: set[str] = field(default_factory=set)
    directories: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    issue_id: str = ""

    @property
    def all_paths(self) -> set[str]:
        """All paths (files and directories) combined."""
        return self.files | self.directories

    def overlaps_with(self, other: FileHints) -> bool:
        """Check if this hint set overlaps with another.

        Returns True if:
        - Any files match exactly
        - Any directories overlap (one contains the other)
        - Any scopes match
        """
        # Exact file matches
        if self.files & other.files:
            return True

        # Directory overlaps
        for d1 in self.directories:
            for d2 in other.directories:
                if _directories_overlap(d1, d2):
                    return True

        # File in directory
        for f in self.files:
            for d in other.directories:
                if f.startswith(d.rstrip("/") + "/"):
                    return True
        for f in other.files:
            for d in self.directories:
                if f.startswith(d.rstrip("/") + "/"):
                    return True

        # Scope matches
        if self.scopes & other.scopes:
            return True

        return False


def _directories_overlap(dir1: str, dir2: str) -> bool:
    """Check if two directory paths overlap (one contains the other)."""
    d1 = dir1.rstrip("/") + "/"
    d2 = dir2.rstrip("/") + "/"
    return d1.startswith(d2) or d2.startswith(d1)


def extract_file_hints(content: str, issue_id: str = "") -> FileHints:
    """Extract file hints from issue content.

    Args:
        content: Issue markdown content
        issue_id: Optional issue ID for tracking

    Returns:
        FileHints with extracted paths and scopes
    """
    hints = FileHints(issue_id=issue_id)

    # Extract file paths
    for match in FILE_PATH_PATTERN.findall(content):
        # Filter out obvious non-paths
        if not _is_valid_path(match):
            continue
        hints.files.add(match)

    # Extract directory paths
    for match in DIR_PATH_PATTERN.findall(content):
        if not _is_valid_path(match):
            continue
        hints.directories.add(match)

    # Extract scopes
    for match in SCOPE_PATTERN.findall(content):
        hints.scopes.add(match.lower())

    return hints


def _is_valid_path(path: str) -> bool:
    """Filter out false positive paths."""
    # Skip URLs
    if path.startswith("http") or path.startswith("//"):
        return False
    # Skip very short paths
    if len(path) < 3:
        return False
    # Skip paths that are likely just file extensions
    if path.startswith("."):
        return False
    return True
```

**File**: `scripts/little_loops/issue_parser.py`
**Changes**: Add method to extract file hints from parsed issue

```python
# Add to IssueInfo class after line 120
    def get_file_hints(self) -> FileHints:
        """Extract file hints from the issue content.

        Returns:
            FileHints extracted from the issue file
        """
        from little_loops.parallel.file_hints import extract_file_hints

        content = self.path.read_text() if self.path.exists() else ""
        return extract_file_hints(content, self.issue_id)
```

**File**: `scripts/little_loops/parallel/__init__.py`
**Changes**: Export new module

```python
# Add to exports
from little_loops.parallel.file_hints import FileHints, extract_file_hints
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_file_hints.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/file_hints.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/file_hints.py`

**Manual Verification**:
- [ ] Verify file hints are extracted from sample issue content

---

### Phase 2: Overlap Detector

#### Overview
Create an overlap detector that tracks active issue scopes and detects conflicts.

#### Changes Required

**File**: `scripts/little_loops/parallel/overlap_detector.py` (new)
**Changes**: Create overlap detection module

```python
"""Overlap detection for parallel issue processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import TYPE_CHECKING

from little_loops.parallel.file_hints import FileHints, extract_file_hints

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)


@dataclass
class OverlapResult:
    """Result of an overlap check.

    Attributes:
        has_overlap: Whether overlap was detected
        overlapping_issues: Issue IDs that overlap
        overlapping_files: Specific files/paths that overlap
    """
    has_overlap: bool = False
    overlapping_issues: list[str] = field(default_factory=list)
    overlapping_files: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return self.has_overlap


class OverlapDetector:
    """Detects overlapping file modifications between parallel issues.

    Thread-safe tracking of which issues are currently being processed
    and what files they're expected to modify.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._active_hints: dict[str, FileHints] = {}

    def register_issue(self, issue: IssueInfo) -> None:
        """Register an issue as actively being processed.

        Args:
            issue: Issue being processed
        """
        with self._lock:
            content = issue.path.read_text() if issue.path.exists() else ""
            hints = extract_file_hints(content, issue.issue_id)
            self._active_hints[issue.issue_id] = hints
            logger.debug(
                f"Registered {issue.issue_id} with hints: "
                f"files={hints.files}, dirs={hints.directories}, scopes={hints.scopes}"
            )

    def unregister_issue(self, issue_id: str) -> None:
        """Unregister an issue when processing completes.

        Args:
            issue_id: ID of the completed issue
        """
        with self._lock:
            if issue_id in self._active_hints:
                del self._active_hints[issue_id]
                logger.debug(f"Unregistered {issue_id}")

    def check_overlap(self, issue: IssueInfo) -> OverlapResult:
        """Check if an issue overlaps with any active issues.

        Args:
            issue: Issue to check

        Returns:
            OverlapResult with overlap details
        """
        with self._lock:
            content = issue.path.read_text() if issue.path.exists() else ""
            new_hints = extract_file_hints(content, issue.issue_id)

            result = OverlapResult()

            for active_id, active_hints in self._active_hints.items():
                if new_hints.overlaps_with(active_hints):
                    result.has_overlap = True
                    result.overlapping_issues.append(active_id)
                    # Find specific overlapping paths
                    result.overlapping_files.update(
                        new_hints.files & active_hints.files
                    )
                    result.overlapping_files.update(
                        new_hints.directories & active_hints.directories
                    )

            if result.has_overlap:
                logger.info(
                    f"{issue.issue_id} overlaps with {result.overlapping_issues}: "
                    f"{result.overlapping_files or 'scope/directory overlap'}"
                )

            return result

    def get_active_issues(self) -> list[str]:
        """Get list of currently active issue IDs.

        Returns:
            List of active issue IDs
        """
        with self._lock:
            return list(self._active_hints.keys())

    def clear(self) -> None:
        """Clear all tracked issues."""
        with self._lock:
            self._active_hints.clear()
```

**File**: `scripts/little_loops/parallel/__init__.py`
**Changes**: Export new module

```python
# Add to exports
from little_loops.parallel.overlap_detector import OverlapDetector, OverlapResult
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_overlap_detector.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/overlap_detector.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/overlap_detector.py`

**Manual Verification**:
- [ ] Verify overlap detection works with sample issues

---

### Phase 3: Orchestrator Integration

#### Overview
Integrate overlap detection into the parallel orchestrator with a config flag to enable/disable.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add overlap detection config to `ParallelConfig`

```python
# Add to ParallelConfig dataclass (around line 290)
    overlap_detection: bool = False  # Enable pre-flight overlap detection
    serialize_overlapping: bool = True  # If True, serialize overlapping issues; if False, just warn
```

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add overlap detection to dispatch logic

```python
# Add import at top
from little_loops.parallel.overlap_detector import OverlapDetector

# In ParallelOrchestrator.__init__ (around line 107), add:
        self.overlap_detector = OverlapDetector() if self.parallel_config.overlap_detection else None

# Modify _process_parallel method (around line 652):
    def _process_parallel(self, issue: IssueInfo) -> None:
        """Process an issue in parallel (non-blocking).

        Args:
            issue: Issue to process
        """
        # Check for overlaps if enabled
        if self.overlap_detector:
            overlap = self.overlap_detector.check_overlap(issue)
            if overlap:
                if self.parallel_config.serialize_overlapping:
                    self.logger.warning(
                        f"Deferring {issue.issue_id} - overlaps with {overlap.overlapping_issues}"
                    )
                    # Re-queue with a delay by putting back in queue
                    self.queue.requeue(issue)
                    return
                else:
                    self.logger.warning(
                        f"Warning: {issue.issue_id} may conflict with {overlap.overlapping_issues}"
                    )

            # Register as active
            self.overlap_detector.register_issue(issue)

        self.logger.info(f"Dispatching {issue.issue_id} to worker pool")
        self.worker_pool.submit(issue, self._on_worker_complete)

# Modify _on_worker_complete method to unregister (around line 661):
    def _on_worker_complete(self, result: WorkerResult) -> None:
        """Callback when a worker completes.

        Args:
            result: Result from the worker
        """
        # Unregister from overlap tracking
        if self.overlap_detector:
            self.overlap_detector.unregister_issue(result.issue_id)

        # ... rest of existing code
```

**File**: `scripts/little_loops/parallel/priority_queue.py`
**Changes**: Add requeue method for deferred issues

```python
# Add to IssuePriorityQueue class
    def requeue(self, issue: IssueInfo, delay_priority: int = 1) -> None:
        """Re-queue an issue with lowered priority for later processing.

        Args:
            issue: Issue to re-queue
            delay_priority: How much to lower priority (higher = lower priority)
        """
        # Create a modified priority for re-queued items
        adjusted_priority = issue.priority_int + delay_priority
        heapq.heappush(
            self._queue,
            QueuedIssue(priority=adjusted_priority, issue_info=issue),
        )
        self.logger.debug(f"Re-queued {issue.issue_id} with adjusted priority {adjusted_priority}")
```

**File**: `scripts/little_loops/cli.py`
**Changes**: Add CLI flags for overlap detection

```python
# In main_parallel() argument parser (around line 142), add:
    parser.add_argument(
        "--overlap-detection",
        action="store_true",
        help="Enable pre-flight overlap detection to reduce merge conflicts",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="With --overlap-detection, warn about overlaps instead of serializing",
    )

# In ParallelConfig construction (around line 200), add:
    overlap_detection=args.overlap_detection,
    serialize_overlapping=not args.warn_only,
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Running `ll-parallel --overlap-detection` shows detection behavior
- [ ] Overlapping issues are deferred or warned about

---

### Phase 4: Unit Tests

#### Overview
Add comprehensive unit tests for file hints and overlap detection.

#### Changes Required

**File**: `scripts/tests/test_file_hints.py` (new)
**Changes**: Create tests for file hint extraction

```python
"""Tests for file hint extraction."""

import pytest

from little_loops.parallel.file_hints import (
    FileHints,
    extract_file_hints,
    _directories_overlap,
)


class TestFileHintExtraction:
    """Tests for extract_file_hints function."""

    def test_extracts_python_files(self):
        """Should extract .py file paths."""
        content = "Fix the bug in `scripts/little_loops/cli.py`"
        hints = extract_file_hints(content)
        assert "scripts/little_loops/cli.py" in hints.files

    def test_extracts_typescript_files(self):
        """Should extract .ts and .tsx file paths."""
        content = "Modified src/components/Button.tsx and utils/helpers.ts"
        hints = extract_file_hints(content)
        assert "src/components/Button.tsx" in hints.files
        assert "utils/helpers.ts" in hints.files

    def test_extracts_directories(self):
        """Should extract directory paths."""
        content = "Changes to scripts/little_loops/ directory"
        hints = extract_file_hints(content)
        assert "scripts/little_loops/" in hints.directories

    def test_extracts_scopes(self):
        """Should extract scope identifiers."""
        content = "scope: sidebar\nComponent: auth-flow"
        hints = extract_file_hints(content)
        assert "sidebar" in hints.scopes

    def test_filters_urls(self):
        """Should filter out URLs."""
        content = "See https://example.com/path/file.py"
        hints = extract_file_hints(content)
        assert not any("example.com" in f for f in hints.files)

    def test_stores_issue_id(self):
        """Should store the issue ID."""
        hints = extract_file_hints("content", "ENH-143")
        assert hints.issue_id == "ENH-143"


class TestFileHintsOverlap:
    """Tests for FileHints.overlaps_with method."""

    def test_exact_file_match(self):
        """Should detect exact file matches."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/cli.py", "src/other.py"})
        assert hints1.overlaps_with(hints2)

    def test_no_file_overlap(self):
        """Should return False for non-overlapping files."""
        hints1 = FileHints(files={"src/cli.py"})
        hints2 = FileHints(files={"src/other.py"})
        assert not hints1.overlaps_with(hints2)

    def test_directory_contains_file(self):
        """Should detect when a directory contains a file."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(files={"src/cli.py"})
        assert hints1.overlaps_with(hints2)

    def test_nested_directories(self):
        """Should detect nested directory overlap."""
        hints1 = FileHints(directories={"src/"})
        hints2 = FileHints(directories={"src/components/"})
        assert hints1.overlaps_with(hints2)

    def test_scope_match(self):
        """Should detect scope matches."""
        hints1 = FileHints(scopes={"sidebar"})
        hints2 = FileHints(scopes={"sidebar", "auth"})
        assert hints1.overlaps_with(hints2)

    def test_empty_hints_no_overlap(self):
        """Empty hints should not overlap."""
        hints1 = FileHints()
        hints2 = FileHints(files={"src/cli.py"})
        assert not hints1.overlaps_with(hints2)


class TestDirectoriesOverlap:
    """Tests for _directories_overlap helper."""

    def test_same_directory(self):
        """Same directory should overlap."""
        assert _directories_overlap("src/", "src/")

    def test_parent_child(self):
        """Parent and child directories should overlap."""
        assert _directories_overlap("src/", "src/components/")
        assert _directories_overlap("src/components/", "src/")

    def test_siblings(self):
        """Sibling directories should not overlap."""
        assert not _directories_overlap("src/", "tests/")

    def test_trailing_slash_handling(self):
        """Should handle inconsistent trailing slashes."""
        assert _directories_overlap("src", "src/")
        assert _directories_overlap("src/", "src")
```

**File**: `scripts/tests/test_overlap_detector.py` (new)
**Changes**: Create tests for overlap detector

```python
"""Tests for overlap detector."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from little_loops.issue_parser import IssueInfo
from little_loops.parallel.overlap_detector import OverlapDetector, OverlapResult


def make_issue(issue_id: str, content: str = "") -> IssueInfo:
    """Create a mock issue with given content."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = content

    return IssueInfo(
        path=mock_path,
        issue_type="enhancements",
        priority="P3",
        issue_id=issue_id,
        title=f"Test {issue_id}",
    )


class TestOverlapDetector:
    """Tests for OverlapDetector class."""

    def test_register_and_unregister(self):
        """Should track registered issues."""
        detector = OverlapDetector()
        issue = make_issue("ENH-001", "Modify src/cli.py")

        detector.register_issue(issue)
        assert "ENH-001" in detector.get_active_issues()

        detector.unregister_issue("ENH-001")
        assert "ENH-001" not in detector.get_active_issues()

    def test_detect_file_overlap(self):
        """Should detect when issues modify same file."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Modify src/cli.py")
        issue2 = make_issue("ENH-002", "Also modify src/cli.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert result.has_overlap
        assert "ENH-001" in result.overlapping_issues

    def test_no_overlap_different_files(self):
        """Should return no overlap for different files."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Modify src/cli.py")
        issue2 = make_issue("ENH-002", "Modify src/config.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert not result.has_overlap

    def test_detect_directory_overlap(self):
        """Should detect directory overlaps."""
        detector = OverlapDetector()

        issue1 = make_issue("ENH-001", "Changes in scripts/")
        issue2 = make_issue("ENH-002", "Modify scripts/little_loops/cli.py")

        detector.register_issue(issue1)
        result = detector.check_overlap(issue2)

        assert result.has_overlap

    def test_clear(self):
        """Should clear all tracked issues."""
        detector = OverlapDetector()

        detector.register_issue(make_issue("ENH-001", "content"))
        detector.register_issue(make_issue("ENH-002", "content"))

        detector.clear()
        assert len(detector.get_active_issues()) == 0


class TestOverlapResult:
    """Tests for OverlapResult dataclass."""

    def test_bool_conversion(self):
        """Should be truthy when overlap detected."""
        assert OverlapResult(has_overlap=True)
        assert not OverlapResult(has_overlap=False)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_file_hints.py scripts/tests/test_overlap_detector.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Coverage adequate for new modules

**Manual Verification**:
- [ ] Tests cover edge cases identified in research

---

## Testing Strategy

### Unit Tests
- File hint extraction with various content patterns
- Overlap detection with different overlap scenarios
- Edge cases: empty content, no files mentioned, nested directories

### Integration Tests
- Orchestrator dispatch behavior with overlap detection enabled
- Requeue behavior for overlapping issues
- End-to-end parallel processing with overlap detection

## References

- Original issue: `.issues/enhancements/P3-ENH-143-detect-overlapping-file-modifications.md`
- Related feature: `.issues/features/P3-FEAT-049-scope-based-concurrency-control.md` (has `LockManager` implementation)
- File extraction patterns: `scripts/little_loops/workflow_sequence_analyzer.py:49-56`
- Dependency graph: `scripts/little_loops/dependency_graph.py`
- Worker dispatch: `scripts/little_loops/parallel/orchestrator.py:652-659`
- Changed files tracking: `scripts/little_loops/parallel/worker_pool.py:719-739`
