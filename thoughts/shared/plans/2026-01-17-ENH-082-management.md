# ENH-082: Report pending merges on ll-parallel startup - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-082-ll-parallel-pending-merge-status-on-startup.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: add

## Current State Analysis

The `ll-parallel` CLI tool processes issues in parallel using git worktrees. On startup, the orchestrator executes these steps in order (`orchestrator.py:97-122`):

1. `_setup_signal_handlers()` - Register graceful shutdown handlers
2. `_ensure_gitignore_entries()` - Add `.parallel-manage-state.json` and `.worktrees/` to `.gitignore`
3. `_cleanup_orphaned_worktrees()` - **Immediately removes all `worker-*` directories without inspection**
4. `_load_state()` - Load state from `.parallel-manage-state.json`

### Key Discoveries
- Cleanup happens at `orchestrator.py:178-229` without any status inspection
- Worktree naming: `.worktrees/worker-<issue-id>-<timestamp>` (e.g., `worker-bug-045-20260117-143022`)
- Branch naming: `parallel/<issue-id>-<timestamp>` (e.g., `parallel/bug-045-20260117-143022`)
- State file tracks: `in_progress_issues`, `completed_issues`, `failed_issues`, `pending_merges`
- CLI already has `--cleanup` flag for explicit cleanup (`cli.py:193-198`)

### Existing Patterns
- Worktree enumeration: `orchestrator.py:189-193` uses `iterdir()` + `startswith("worker-")`
- State loading: `orchestrator.py:238-260` loads and reports previous state counts
- Git operations: `GitLock` class provides thread-safe git command execution

## Desired End State

On startup, `ll-parallel` should:
1. Check for existing worktrees from previous runs
2. Inspect their state (uncommitted changes, commits ahead of main)
3. Report findings before any cleanup or processing
4. Offer user options via CLI flags or interactive prompt

Example output:
```
[ll-parallel] Checking for pending work from previous runs...
[ll-parallel] Found 2 worktrees with potential pending work:
  - worker-bug-045-20260117-143022: BUG-045 (3 commits ahead of main, no uncommitted changes)
  - worker-enh-067-20260117-144533: ENH-067 (1 commit ahead, has uncommitted changes)

Use --merge-pending to attempt merging, --clean-start to remove, or --ignore-pending to continue.
```

### How to Verify
- Run `ll-parallel` with orphaned worktrees present - should report status
- Test with `--merge-pending` flag - should attempt to merge detected worktrees
- Test with `--clean-start` flag - should clean up without prompting
- Test with `--ignore-pending` flag - should continue without action

## What We're NOT Doing

- **Not implementing interactive prompts** - Use CLI flags only to keep automation-friendly
- **Not auto-merging by default** - Too risky; require explicit flag
- **Not changing the default behavior** - Still cleans up after reporting, unless flags override
- **Not persisting detection state** - Fresh detection on each startup

## Problem Analysis

When `ll-parallel` is interrupted (Ctrl+C, crash, system shutdown), some workers may have completed their issue processing but not yet had their changes merged back to main. Currently:
- Worktrees are silently deleted on next startup
- Completed work may be lost
- Users have no visibility without manual investigation

## Solution Approach

Insert a new `_check_pending_worktrees()` method between `_ensure_gitignore_entries()` and `_cleanup_orphaned_worktrees()` in the `run()` method. This method will:

1. Enumerate existing worktrees
2. For each worktree, inspect git status (commits ahead, uncommitted changes)
3. Report findings to the user
4. Based on CLI flags, either merge pending work, clean up, or skip cleanup

## Implementation Phases

### Phase 1: Add Worktree Inspection Logic

#### Overview
Add a new dataclass to hold worktree status and a method to inspect worktrees.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add `PendingWorktreeInfo` dataclass after `OrchestratorState`

```python
@dataclass
class PendingWorktreeInfo:
    """Information about a pending worktree from a previous run.

    Attributes:
        worktree_path: Path to the worktree directory
        branch_name: Git branch name (parallel/<issue-id>-<timestamp>)
        issue_id: Extracted issue ID (e.g., BUG-045)
        commits_ahead: Number of commits ahead of main
        has_uncommitted_changes: Whether there are uncommitted changes
        changed_files: List of files with uncommitted changes
    """

    worktree_path: Path
    branch_name: str
    issue_id: str
    commits_ahead: int
    has_uncommitted_changes: bool
    changed_files: list[str] = field(default_factory=list)

    @property
    def has_pending_work(self) -> bool:
        """Return True if this worktree has work that could be merged."""
        return self.commits_ahead > 0 or self.has_uncommitted_changes
```

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add `_inspect_worktree()` helper method after `_cleanup_orphaned_worktrees()`

```python
def _inspect_worktree(self, worktree_path: Path) -> PendingWorktreeInfo | None:
    """Inspect a worktree to determine its status.

    Args:
        worktree_path: Path to the worktree directory

    Returns:
        PendingWorktreeInfo if inspection succeeded, None if failed
    """
    try:
        # Extract branch name from worktree path
        # worker-bug-045-20260117-143022 -> parallel/bug-045-20260117-143022
        branch_name = worktree_path.name.replace("worker-", "parallel/")

        # Extract issue ID (e.g., bug-045 -> BUG-045)
        # Pattern: worker-<issue-id>-<timestamp>
        match = re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)
        issue_id = match.group(1).upper() if match else worktree_path.name

        # Check commits ahead of main
        result = self._git_lock.run(
            ["rev-list", "--count", f"main..{branch_name}"],
            cwd=self.repo_path,
            timeout=10,
        )
        commits_ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

        # Check for uncommitted changes in worktree
        result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=worktree_path,
            timeout=10,
        )
        changed_files = []
        has_uncommitted = False
        if result.returncode == 0 and result.stdout.strip():
            has_uncommitted = True
            changed_files = [line[3:] for line in result.stdout.strip().split("\n") if line]

        return PendingWorktreeInfo(
            worktree_path=worktree_path,
            branch_name=branch_name,
            issue_id=issue_id,
            commits_ahead=commits_ahead,
            has_uncommitted_changes=has_uncommitted,
            changed_files=changed_files,
        )
    except Exception as e:
        self.logger.warning(f"Failed to inspect worktree {worktree_path.name}: {e}")
        return None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] N/A for this phase (internal helper only)

---

### Phase 2: Add Pending Worktree Reporting

#### Overview
Add the main `_check_pending_worktrees()` method that enumerates worktrees, inspects them, and reports status.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add `_check_pending_worktrees()` method and call it from `run()`

```python
def _check_pending_worktrees(self) -> list[PendingWorktreeInfo]:
    """Check for pending worktrees from previous runs and report status.

    Returns:
        List of pending worktree information
    """
    worktree_base = self.repo_path / self.parallel_config.worktree_base
    if not worktree_base.exists():
        return []

    # Find all worker directories
    worktrees = [
        item for item in worktree_base.iterdir()
        if item.is_dir() and item.name.startswith("worker-")
    ]

    if not worktrees:
        return []

    self.logger.info("Checking for pending work from previous runs...")

    # Inspect each worktree
    pending_info: list[PendingWorktreeInfo] = []
    for worktree_path in worktrees:
        info = self._inspect_worktree(worktree_path)
        if info:
            pending_info.append(info)

    # Report findings
    with_work = [p for p in pending_info if p.has_pending_work]
    if with_work:
        self.logger.warning(f"Found {len(with_work)} worktree(s) with pending work:")
        for info in with_work:
            status_parts = []
            if info.commits_ahead > 0:
                status_parts.append(f"{info.commits_ahead} commit(s) ahead of main")
            if info.has_uncommitted_changes:
                status_parts.append(f"{len(info.changed_files)} uncommitted file(s)")
            status = ", ".join(status_parts)
            self.logger.warning(f"  - {info.worktree_path.name}: {info.issue_id} ({status})")

        self.logger.info("")
        self.logger.info("Options:")
        self.logger.info("  --merge-pending   Attempt to merge pending work before continuing")
        self.logger.info("  --clean-start     Remove all worktrees and start fresh")
        self.logger.info("  --ignore-pending  Continue without action (worktrees will be cleaned up)")
    elif pending_info:
        self.logger.info(f"Found {len(pending_info)} orphaned worktree(s) with no pending work")

    return pending_info
```

Update `run()` method to call `_check_pending_worktrees()`:

```python
def run(self) -> int:
    """Run the parallel issue processor."""
    try:
        self._setup_signal_handlers()
        self._ensure_gitignore_entries()

        # Check for pending work before cleanup
        pending_worktrees = self._check_pending_worktrees()

        # Handle pending worktrees based on flags
        if pending_worktrees and any(p.has_pending_work for p in pending_worktrees):
            if self.parallel_config.merge_pending:
                self._merge_pending_worktrees(pending_worktrees)
            elif not self.parallel_config.ignore_pending and not self.parallel_config.clean_start:
                # Default: report and continue with cleanup
                pass

        self._cleanup_orphaned_worktrees()
        self._load_state()
        # ... rest unchanged
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Create test worktree manually, run ll-parallel, verify status is reported

---

### Phase 3: Add CLI Flags and Configuration

#### Overview
Add CLI flags (`--merge-pending`, `--clean-start`, `--ignore-pending`) and wire them to ParallelConfig.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add new fields to `ParallelConfig` dataclass

```python
# Add to ParallelConfig attributes
merge_pending: bool = False  # Attempt to merge pending worktrees
clean_start: bool = False    # Remove all worktrees without checking
ignore_pending: bool = False # Skip pending worktree handling
```

**File**: `scripts/little_loops/cli.py`
**Changes**: Add argument parsing for new flags in `main_parallel()`

```python
# Add after --cleanup argument
parser.add_argument(
    "--merge-pending",
    action="store_true",
    help="Attempt to merge pending work from previous interrupted runs",
)
parser.add_argument(
    "--clean-start",
    action="store_true",
    help="Remove all worktrees and start fresh (skip pending work check)",
)
parser.add_argument(
    "--ignore-pending",
    action="store_true",
    help="Report pending work but continue without merging",
)
```

Update `create_parallel_config()` call to include new flags:

```python
parallel_config = config.create_parallel_config(
    # ... existing params ...
    merge_pending=args.merge_pending,
    clean_start=args.clean_start,
    ignore_pending=args.ignore_pending,
)
```

**File**: `scripts/little_loops/config.py`
**Changes**: Update `create_parallel_config()` to accept new parameters

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Help shows new flags: `ll-parallel --help`

**Manual Verification**:
- [ ] `ll-parallel --help` displays new flags with descriptions
- [ ] Flags are parsed correctly (verify with debug print)

---

### Phase 4: Implement Merge Pending Logic

#### Overview
Add `_merge_pending_worktrees()` method to attempt merging detected pending work.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add `_merge_pending_worktrees()` method

```python
def _merge_pending_worktrees(self, pending: list[PendingWorktreeInfo]) -> None:
    """Attempt to merge pending worktrees from previous runs.

    Args:
        pending: List of pending worktree information
    """
    with_work = [p for p in pending if p.has_pending_work]
    if not with_work:
        return

    self.logger.info(f"Attempting to merge {len(with_work)} pending worktree(s)...")

    for info in with_work:
        try:
            # If there are uncommitted changes, commit them first
            if info.has_uncommitted_changes:
                self.logger.info(f"  Committing uncommitted changes in {info.issue_id}...")
                self._git_lock.run(
                    ["add", "-A"],
                    cwd=info.worktree_path,
                    timeout=30,
                )
                self._git_lock.run(
                    ["commit", "-m", f"WIP: Auto-commit from interrupted session for {info.issue_id}"],
                    cwd=info.worktree_path,
                    timeout=30,
                )

            # Attempt merge
            self.logger.info(f"  Merging {info.issue_id} ({info.branch_name})...")
            result = self._git_lock.run(
                ["merge", "--no-ff", info.branch_name, "-m", f"Merge pending work for {info.issue_id}"],
                cwd=self.repo_path,
                timeout=60,
            )

            if result.returncode == 0:
                self.logger.success(f"  Successfully merged {info.issue_id}")
                # Clean up the worktree after successful merge
                self._git_lock.run(
                    ["worktree", "remove", "--force", str(info.worktree_path)],
                    cwd=self.repo_path,
                    timeout=30,
                )
                self._git_lock.run(
                    ["branch", "-D", info.branch_name],
                    cwd=self.repo_path,
                    timeout=10,
                )
            else:
                self.logger.warning(f"  Failed to merge {info.issue_id}: {result.stderr}")
                # Abort the merge if it failed
                self._git_lock.run(
                    ["merge", "--abort"],
                    cwd=self.repo_path,
                    timeout=10,
                )

        except Exception as e:
            self.logger.warning(f"  Error merging {info.issue_id}: {e}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Create worktree with commits, run `ll-parallel --merge-pending`, verify merge occurs
- [ ] Test conflict scenario - should abort cleanly and report failure

---

### Phase 5: Add Unit Tests

#### Overview
Add comprehensive tests for the new functionality.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add test class for pending worktree detection

```python
class TestCheckPendingWorktrees:
    """Tests for _check_pending_worktrees method."""

    def test_no_worktrees_dir(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns empty list when worktree directory doesn't exist."""
        worktree_base = temp_repo_with_config / ".worktrees"
        if worktree_base.exists():
            worktree_base.rmdir()

        result = orchestrator._check_pending_worktrees()
        assert result == []

    def test_empty_worktrees_dir(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Returns empty list when no worker directories exist."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        result = orchestrator._check_pending_worktrees()
        assert result == []

    def test_detects_orphaned_worktrees(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Detects worker directories from previous runs."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)

        # Create fake worktree directory
        orphan = worktree_base / "worker-bug-001-20260117-120000"
        orphan.mkdir()

        # Mock git operations
        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[0] == "rev-list":
                result.stdout = "2\n"
            elif args[0] == "status":
                result.stdout = ""
            return result

        orchestrator._git_lock.run = mock_git_run

        result = orchestrator._check_pending_worktrees()
        assert len(result) == 1
        assert result[0].issue_id == "BUG-001"
        assert result[0].commits_ahead == 2


class TestInspectWorktree:
    """Tests for _inspect_worktree method."""

    def test_extracts_issue_id(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Correctly extracts issue ID from worktree path."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-enh-042-20260117-150000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "0\n" if args[0] == "rev-list" else ""
            return result

        orchestrator._git_lock.run = mock_git_run

        result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.issue_id == "ENH-042"
        assert result.branch_name == "parallel/enh-042-20260117-150000"

    def test_detects_uncommitted_changes(
        self,
        orchestrator: ParallelOrchestrator,
        temp_repo_with_config: Path,
    ) -> None:
        """Detects uncommitted changes in worktree."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(exist_ok=True)
        worktree_path = worktree_base / "worker-bug-099-20260117-160000"
        worktree_path.mkdir()

        def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            if args[0] == "rev-list":
                result.stdout = "1\n"
            elif args[0] == "status":
                result.stdout = " M src/file.py\n?? new_file.txt\n"
            return result

        orchestrator._git_lock.run = mock_git_run

        result = orchestrator._inspect_worktree(worktree_path)
        assert result is not None
        assert result.has_uncommitted_changes is True
        assert len(result.changed_files) == 2
        assert result.has_pending_work is True
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestCheckPendingWorktrees -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestInspectWorktree -v`
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] All new tests run and pass

---

### Phase 6: Update run() Method Flow

#### Overview
Wire everything together in the `run()` method with proper flow control.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Update `run()` method to integrate pending worktree handling

```python
def run(self) -> int:
    """Run the parallel issue processor.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        self._setup_signal_handlers()
        self._ensure_gitignore_entries()

        # Check for pending work from previous runs (unless clean start)
        if not self.parallel_config.clean_start:
            pending_worktrees = self._check_pending_worktrees()

            # Handle pending worktrees based on flags
            pending_with_work = [p for p in pending_worktrees if p.has_pending_work]
            if pending_with_work:
                if self.parallel_config.merge_pending:
                    self._merge_pending_worktrees(pending_worktrees)
                elif not self.parallel_config.ignore_pending:
                    # Default behavior: just report (cleanup happens below)
                    self.logger.info("Continuing with cleanup (use --merge-pending to merge)...")

        self._cleanup_orphaned_worktrees()
        self._load_state()

        if self.parallel_config.dry_run:
            return self._dry_run()

        return self._execute()

    except KeyboardInterrupt:
        self.logger.warning("Interrupted by user")
        return 1
    except Exception as e:
        self.logger.error(f"Fatal error: {e}")
        return 1
    finally:
        self._cleanup()
        self._restore_signal_handlers()
```

Add import for `PendingWorktreeInfo` at top of file:

```python
from little_loops.parallel.types import (
    OrchestratorState,
    ParallelConfig,
    PendingWorktreeInfo,
    WorkerResult,
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run `ll-parallel` with orphaned worktrees - status is reported
- [ ] Run `ll-parallel --merge-pending` - merges are attempted
- [ ] Run `ll-parallel --clean-start` - skips status check, cleans immediately
- [ ] Run `ll-parallel --ignore-pending` - reports but continues

---

## Testing Strategy

### Unit Tests
- Test worktree enumeration with various scenarios (empty, none, multiple)
- Test status inspection (commits ahead, uncommitted changes)
- Test issue ID extraction from various worktree names
- Test merge attempt success and failure paths

### Integration Tests
- Create actual worktree, interrupt ll-parallel, restart and verify detection
- Test merge conflict handling
- Test with state file present/absent

## References

- Original issue: `.issues/enhancements/P3-ENH-082-ll-parallel-pending-merge-status-on-startup.md`
- Current cleanup: `orchestrator.py:178-229`
- Startup flow: `orchestrator.py:97-122`
- CLI entry: `cli.py:117-286`
- Related FEAT-081: `.issues/completed/P3-FEAT-081-cleanup-worktrees-command.md`
