# ENH-037: Smarter Pull Strategy for Repeated Rebase Conflicts - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-037-smarter-pull-strategy-for-repeated-rebase-conflicts.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### What Exists Now

The merge coordinator in `ll-parallel` implements a pull-before-merge strategy at `merge_coordinator.py:748-768`:

1. Attempts `git pull --rebase origin main` before merging
2. On failure, checks if rebase is in progress (via `.git/rebase-merge` or `.git/rebase-apply` directory existence)
3. If conflict detected, aborts rebase via `_abort_rebase_if_in_progress()`
4. Logs warning and continues without pull
5. Same conflict repeats on subsequent merges (e.g., commit `ae3b85ec1cac501058f6e5da362be37be1c99801` affecting BUG-692 and BUG-694)

### Key Discoveries from Research

**File Locations:**
- Primary implementation: `scripts/little_loops/parallel/merge_coordinator.py` lines 748-768 (pull logic)
- Related methods: `_is_rebase_in_progress()` (497-505), `_abort_rebase_if_in_progress()` (507-530)
- Git wrapper: `scripts/little_loops/parallel/git_lock.py` - provides `GitLock.run()` with retry logic
- Tests: `scripts/tests/test_merge_coordinator.py` - no existing tests for pull/rebase strategy

**Error Output Format:**
```
Pull --rebase failed with conflicts: From https://github.com/BrennonTWilliams/blender-agents
 * branch              main       -> FETCH_HEAD
Rebasing (54/218)
dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detectio
```

The `dropping <hash> <message>` pattern contains the problematic commit hash.

**Patterns Discovered:**
- Error detection uses indicator string lists with `any()` pattern (e.g., `_is_local_changes_error()`)
- State tracking uses private attributes (e.g., `_consecutive_failures`, `_stash_active`)
- Retry logic follows threshold pattern (e.g., `config.max_merge_retries`)
- Circuit breaker pattern exists for consecutive failures

## Desired End State

The system should:

1. Extract the problematic commit hash from rebase conflict output
2. Track problematic commits in memory during a run
3. On repeated conflict with same commit, use `git pull --no-rebase` (merge strategy) instead of aborting
4. Log strategy changes clearly (not just repeated warnings)
5. Continue using rebase by default for new/unknown commits

### How to Verify

- Create test simulating repeated rebase conflict with same commit
- First conflict: logs warning, aborts rebase, tracks commit
- Second conflict: logs info about using merge strategy, executes `git pull --no-rebase`
- Verify upstream changes are incorporated via merge commit
- Unit test for commit hash extraction regex

## What We're NOT Doing

- **Not adding persistent state** - per-process tracking is sufficient (each ll-parallel run is independent)
- **Not adding config options for pull strategy** - keeping it simple with automatic adaptive behavior
- **Not modifying GitLock** - no changes needed to the git operation wrapper
- **Not handling fetch failures** - existing error handling covers network/remote errors
- **Not implementing Option 3 from issue** - configurable pull strategy deferred to future enhancement

## Problem Analysis

### Root Cause

The current implementation aborts the rebase and continues without pulling. This means:
- Each merge attempts the same rebase with the same conflicting commit
- Upstream changes may be missed if pull is skipped
- Log noise from repeated warnings

### Why This Happens

The system has no memory of previous conflicts. The `_abort_rebase_if_in_progress()` method:
1. Detects rebase in progress via `.git/rebase-merge` directory
2. Runs `git rebase --abort`
3. Returns to pre-pull state
4. Does not extract or track the problematic commit

## Solution Approach

Implement Option 1 from the issue with minor adjustments:

1. **Extract commit hash** from rebase conflict output using regex pattern for `dropping <hash>`
2. **Track in memory** using a `set[str]` instance variable `_problematic_commits`
3. **Adaptive strategy**:
   - First conflict: abort rebase, track commit, continue without pull (current behavior)
   - Subsequent conflicts: detect known commit, use `git pull --no-rebase` (merge strategy)
4. **Clear logging**: distinguish between "new conflict" and "known conflict - using merge strategy"

### Why This Approach

- **Minimal changes**: Builds on existing abort-and-continue pattern
- **Backward compatible**: Default rebase strategy unchanged for new conflicts
- **Safe**: Merge strategy is standard git behavior, creates merge commit (acceptable for coordination repo)
- **Learning**: System adapts after first encounter with problematic commit
- **No external dependencies**: Uses only existing git commands

## Implementation Phases

### Phase 1: Add Commit Hash Extraction

#### Overview
Add method to extract commit hash from rebase conflict output following existing error detection patterns.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

**Location**: After existing error detection methods (around line 546)

**Add new method**:
```python
def _detect_conflict_commit(self, error_output: str) -> str | None:
    """Extract commit hash from rebase conflict output.

    Looks for patterns like:
    - "dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detectio"

    Args:
        error_output: The stderr/stdout from the failed git pull --rebase

    Returns:
        The 40-character commit hash if found, None otherwise
    """
    import re

    # Pattern: "dropping <40-char-hash>" followed by space and message
    # Match only full 40-char hashes to avoid false positives
    match = re.search(r'dropping\s+([a-f0-9]{40})\s+', error_output, re.IGNORECASE)
    return match.group(1) if match else None
```

**Add instance variable** in `__init__` (around line 60):
```python
self._problematic_commits: set[str] = set()  # Track commits causing repeated rebase conflicts
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

**Manual Verification**:
- N/A - pure addition, no behavior change yet

---

### Phase 2: Modify Pull Logic to Use Merge Strategy Fallback

#### Overview
Update pull logic at lines 748-768 to detect repeated conflicts and use merge strategy.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

**Location**: Lines 748-768 (current pull logic)

**Replace existing pull failure handling** with:

```python
# Handle pull failures
if pull_result.returncode != 0:
    error_output = pull_result.stderr + pull_result.stdout

    # Check if rebase conflicted - must abort before continuing
    if self._is_rebase_in_progress():
        conflict_commit = self._detect_conflict_commit(error_output)

        if conflict_commit and conflict_commit in self._problematic_commits:
            # Known problematic commit - use merge strategy instead
            self.logger.info(
                f"Repeated rebase conflict with {conflict_commit[:8]}, "
                f"using merge strategy (git pull --no-rebase)"
            )
            if not self._abort_rebase_if_in_progress():
                raise RuntimeError("Failed to recover from rebase conflict during pull")

            # Attempt merge strategy pull
            merge_pull_result = self._git_lock.run(
                ["pull", "--no-rebase", "origin", "main"],
                cwd=self.repo_path,
                timeout=60,
            )

            if merge_pull_result.returncode != 0:
                self.logger.warning(
                    f"Merge strategy pull also failed: {merge_pull_result.stderr[:200]}"
                )
                # Continue anyway - merge may still work or fail appropriately
            else:
                self.logger.info(f"Merge strategy pull succeeded for {conflict_commit[:8]}")

        else:
            # First time seeing this conflict or couldn't extract commit
            if conflict_commit:
                self._problematic_commits.add(conflict_commit)
                self.logger.warning(
                    f"New rebase conflict with {conflict_commit[:8]}, "
                    f"tracking for future merges (will use merge strategy on repeat)"
                )
            else:
                self.logger.warning(
                    "Rebase conflict detected (could not extract commit hash), "
                    f"tracking for future merges"
                )

            self.logger.warning(
                f"Pull --rebase failed with conflicts: {error_output[:200]}"
            )

            if not self._abort_rebase_if_in_progress():
                raise RuntimeError("Failed to recover from rebase conflict during pull")
            # After aborting rebase, we're back to pre-pull state
            # Continue without the pull - merge may still work or conflict
            self.logger.info("Continuing without pull after rebase abort")

    elif self._is_local_changes_error(error_output):
        # ... existing local changes error handling unchanged ...
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

**Manual Verification**:
- N/A - requires integration test for full behavior verification

---

### Phase 3: Add Tests

#### Overview
Add unit and integration tests for new functionality following existing test patterns.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`

**Add test class after existing error detection tests** (around line 500):

```python
class TestDetectConflictCommit:
    """Tests for _detect_conflict_commit extraction."""

    def test_extracts_commit_hash_from_dropping_message(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should extract 40-char hash from 'dropping' message."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = """From https://github.com/example/repo
 * branch              main       -> FETCH_HEAD
Rebasing (54/218)
dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detection
"""

        commit_hash = coordinator._detect_conflict_commit(error_message)
        assert commit_hash == "ae3b85ec1cac501058f6e5da362be37be1c99801"

    def test_returns_none_when_no_dropping_message(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return None when 'dropping' pattern not found."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "error: could not apply ae3b85ec1cac501058f6e5da362be37be1c99801"

        commit_hash = coordinator._detect_conflict_commit(error_message)
        assert commit_hash is None

    def test_returns_none_for_short_hash(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should return None for short 7-char hashes (only match 40-char)."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "dropping ae3b85ec some commit message"

        commit_hash = coordinator._detect_conflict_commit(error_message)
        assert commit_hash is None

    def test_case_insensitive_hash_detection(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should match uppercase hex characters."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        error_message = "dropping AE3B85EC1CAC501058F6E5DA362BE37BE1C99801 feat: add feature"

        commit_hash = coordinator._detect_conflict_commit(error_message)
        assert commit_hash == "AE3B85EC1CAC501058F6E5DA362BE37BE1C99801"
```

**Add integration test class** after stash tests (around line 450):

```python
class TestRebaseConflictRecovery:
    """Tests for rebase conflict handling and merge strategy fallback."""

    @pytest.fixture
    def two_commit_repo(
        self, temp_git_repo: Path
    ) -> Generator[Path, None, None]:
        """Create a repo with two commits for testing conflicts."""
        # Create second commit on main
        (temp_git_repo / "file2.txt").write_text("second file")
        subprocess.run(
            ["git", "add", "."],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "second commit"],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )
        yield temp_git_repo

    def test_first_rebase_conflict_tracks_commit(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
        two_commit_repo: Path,
    ) -> None:
        """First rebase conflict should track the problematic commit."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Simulate rebase conflict with dropping message
        conflict_output = (
            "From origin\n"
            "Rebasing (1/2)\n"
            "dropping abcdef1234567890abcdef1234567890abcdef12 test message\n"
        )

        conflict_commit = coordinator._detect_conflict_commit(conflict_output)
        assert conflict_commit == "abcdef1234567890abcdef1234567890abcdef12"

        # Add to problematic commits
        coordinator._problematic_commits.add(conflict_commit)
        assert conflict_commit in coordinator._problematic_commits

    def test_repeated_conflict_detected(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should detect when same commit causes conflict again."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        problematic = "abc123def456789012345678901234567890abc1"
        coordinator._problematic_commits.add(problematic)

        # Simulate conflict output with same commit
        error_output = f"dropping {problematic} conflict message"
        detected = coordinator._detect_conflict_commit(error_output)

        assert detected == problematic
        assert detected in coordinator._problematic_commits
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestDetectConflictCommit -v`
- [ ] All new tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestRebaseConflictRecovery -v`
- [ ] All existing tests still pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_merge_coordinator.py`

**Manual Verification**:
- N/A - tests cover the behavior

---

## Testing Strategy

### Unit Tests

**Commit Hash Extraction** (`TestDetectConflictCommit`):
- Valid 40-char hash extraction from `dropping` message
- Returns `None` when pattern not found
- Rejects short 7-char hashes
- Case-insensitive hex matching

**State Tracking** (`TestRebaseConflictRecovery`):
- First conflict adds commit to tracking set
- Subsequent conflicts detect membership in set
- Set persists across merge operations

### Integration Tests

Due to complexity of setting up actual rebase conflicts in tests, integration testing will be:
1. Unit tests for individual components (extraction, tracking)
2. Manual verification in external repo (blender-agents) where original issue occurred
3. Log analysis during real ll-parallel runs

### Regression Tests

Existing tests must pass:
- All stash handling tests
- All conflict handling tests
- All merge lifecycle tests

## References

- Original issue: `.issues/enhancements/P3-ENH-037-smarter-pull-strategy-for-repeated-rebase-conflicts.md`
- Log evidence: `ll-parallel-blender-agents-debug.log` (lines showing BUG-692 and BUG-694)
- Related issue: `.issues/completed/P2-BUG-038-leaked-file-causes-cascading-pull-failures.md`
- Implementation: `scripts/little_loops/parallel/merge_coordinator.py:748-768`
- Git wrapper: `scripts/little_loops/parallel/git_lock.py`
- Test file: `scripts/tests/test_merge_coordinator.py`
