# Merge Coordinator

Comprehensive documentation for the merge coordinator component used by `ll-parallel` and `ll-auto`.

## Overview

The `MergeCoordinator` is a production-grade git operations state machine that handles sequential integration of parallel worker changes back to the main branch. It goes far beyond simple merge queueing, implementing sophisticated error detection, recovery mechanisms, and adaptive strategies to handle real-world edge cases in concurrent git workflows.

**Location**: `scripts/little_loops/parallel/merge_coordinator.py`

**Key Characteristics**:
- Sequential processing to avoid merge conflicts
- Background daemon thread for non-blocking operation
- Comprehensive error detection and recovery
- Adaptive strategies based on failure patterns
- Preserves user's local changes through stash management
- Coordinates with orchestrator to avoid git index races

## Architecture

### Threading Model

```
┌─────────────────────────────────────────┐
│         Main Thread                     │
│  ┌────────────────────────────────┐    │
│  │   Orchestrator                  │    │
│  │   - Dispatches workers          │    │
│  │   - Manages lifecycle           │    │
│  └────────┬───────────────────────┘    │
│           │ queue_merge()               │
│           ▼                              │
│  ┌────────────────────────────────┐    │
│  │   Merge Queue (FIFO)            │    │
│  └────────┬───────────────────────┘    │
└───────────┼──────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│    Background Thread (daemon)           │
│  ┌────────────────────────────────┐    │
│  │   Merge Loop                    │    │
│  │   - Process one merge at a time │    │
│  │   - Stash/unstash local changes│    │
│  │   - Detect/recover from errors  │    │
│  │   - Track results               │    │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Git Lock Coordination

The merge coordinator shares a `GitLock` with the orchestrator to serialize operations on the main repository:

```python
# Shared lock prevents index.lock race conditions
git_lock = GitLock(logger)
orchestrator = ParallelOrchestrator(..., git_lock=git_lock)
merge_coordinator = MergeCoordinator(..., git_lock=git_lock)
```

This prevents scenarios like:
- Worker commits to main repo while merge coordinator is pulling
- Orchestrator updates state file while merge coordinator is checking status
- Multiple components trying to modify the git index simultaneously

## Core Features

### 1. Sequential Merge Queue

Issues are merged one at a time to avoid conflicts:

```python
coordinator = MergeCoordinator(config, logger, repo_path)
coordinator.start()  # Start background thread

# Queue merges (non-blocking)
for worker_result in completed_workers:
    coordinator.queue_merge(worker_result)

# Wait for all merges to complete
coordinator.wait_for_completion(timeout=300)
coordinator.shutdown()
```

### 2. Automatic Stash Management

Handles user's uncommitted local changes transparently:

**Stash Before Merge**:
```python
# Automatically stashes tracked changes, excluding:
# - State file (orchestrator manages it)
# - Lifecycle file moves (to prevent pop conflicts)
# - Files in completed/ directory
# - Claude Code context state file
```

**Pop After Merge**:
```python
# Restores stashed changes after merge completes
# Preserves merge even if pop fails (never does reset --hard)
# Tracks pop failures for user notification
```

**Exclusion Logic** (BUG-008, BUG-018):
- Lifecycle file moves are excluded because they can conflict with the merge when popping
- State file is excluded because orchestrator continuously updates it
- Completed directory files are excluded because they're lifecycle-managed

### 3. Lifecycle File Move Coordination

Auto-commits pending issue file moves to `completed/` directory:

```python
# Before merge, commit any uncommitted lifecycle moves
# Prevents "local changes would be overwritten" errors
self._commit_pending_lifecycle_moves()
```

**Why This Matters** (BUG-018):
- Orchestrator moves issue files to `completed/` after successful merge
- These moves are excluded from stash (to prevent pop conflicts)
- But uncommitted moves block subsequent merges
- Solution: Auto-commit them with descriptive message

### 4. State File Protection

Uses `git update-index --assume-unchanged` to hide state file modifications:

```python
# Mark state file as assume-unchanged before pull
self._mark_state_file_assume_unchanged()

# Pull with rebase (won't see state file changes)
git pull --rebase origin main

# Restore normal tracking after merge
self._restore_state_file_tracking()
```

**Why This Matters**:
- Orchestrator continuously updates the state file during processing
- `git pull --rebase` would fail if state file has uncommitted changes
- `assume-unchanged` tells git to ignore the modifications temporarily

## Sophisticated Error Handling

### Error Detection Methods

The coordinator implements 7 specialized error detectors:

| Method | Purpose |
|--------|---------|
| `_is_local_changes_error()` | Detects "local changes would be overwritten" |
| `_is_untracked_files_error()` | Detects untracked files blocking merge |
| `_is_index_error()` | Detects corrupted git index |
| `_is_unmerged_files_error()` | Detects pre-existing unmerged files |
| `_is_rebase_in_progress()` | Checks for incomplete rebase |
| `_detect_conflict_commit()` | Extracts commit hash from rebase conflict output |
| `_is_lifecycle_file_move()` | Identifies issue file renames to completed/ |

### Index Recovery System

Automatically detects and recovers from corrupted git state:

```python
def _check_and_recover_index() -> bool:
    """Health check before every merge."""

    # 1. Check for incomplete merge (MERGE_HEAD exists)
    if merge_head.exists():
        git merge --abort

    # 2. Check for incomplete rebase (rebase-merge/ exists)
    if rebase_dir.exists():
        git rebase --abort
        git reset --hard HEAD  # Defensive after abort

    # 3. Check for unmerged files (UU, AA, DD, AU, UA, DU, UD)
    if has_unmerged:
        git reset --hard HEAD

    # 4. Final safety check
    if MERGE_HEAD still exists:
        git reset --hard HEAD
```

**When It Runs**:
- At the start of every `_process_merge()` call
- Before merge attempts (to ensure clean state)
- After detecting index errors during operations

**Why It Matters**:
- Previous operations can leave git in dirty state
- Merge/rebase aborts don't always clean up completely
- Prevents cascading failures from one bad merge

### Adaptive Pull Strategy

Tracks commits that cause repeated rebase conflicts and adapts:

```python
self._problematic_commits: set[str] = set()

# First conflict with commit abc123...
conflict_commit = self._detect_conflict_commit(error_output)
self._problematic_commits.add(conflict_commit)
git rebase --abort
# Continue without pull (existing behavior)

# Second conflict with same commit abc123...
if conflict_commit in self._problematic_commits:
    # Use merge strategy instead of rebase
    git pull --no-rebase origin main
```

**Commit Detection** (ENH-037):
```python
# Extracts 40-character commit hash from rebase output
# Pattern: "dropping ae3b85ec...f6e5da362be37be1c99801 feat(ai): add stall detectio"
match = re.search(r"dropping\s+([a-f0-9]{40})\s+", error_output)
```

**Benefits**:
- Avoids repeated failed rebase attempts
- Reduces log noise
- Ensures upstream changes are integrated (merge instead of skip)

### Untracked File Conflict Handling

Backs up conflicting untracked files and retries:

```python
# Parse conflicting files from error message
conflicting_files = ["path/to/file.txt", ...]

# Create backup directory
backup_dir = .ll-backup/{issue_id}/

# Move conflicting files to backup
for file_path in conflicting_files:
    shutil.move(src, backup_dir / file_path)

# Retry merge (now succeeds without conflicts)
```

**Why This Matters**:
- Worker branches may create files that don't exist in main
- Git refuses to merge if it would overwrite untracked files
- Backing up preserves the files for user review

### Circuit Breaker

Pauses after consecutive failures to prevent cascading issues:

```python
self._consecutive_failures = 0
self._paused = False

# On merge failure
self._consecutive_failures += 1
if self._consecutive_failures >= 3:
    self._paused = True
    # Skip all subsequent merges until manual intervention

# On merge success
self._consecutive_failures = 0  # Reset counter
```

**Why This Matters**:
- Prevents hundreds of failed merge attempts
- Signals that manual intervention is needed
- Preserves log readability

### Conflict Retry Logic

Attempts rebase in worktree on merge conflicts:

```python
# Merge failed with conflict
git merge --abort

# Stash worktree changes if any
cd {worktree_path}
git stash push

# Fetch latest main before rebase (BUG-180)
git fetch origin main

# Rebase branch onto latest main
git rebase origin/main

# If successful, restore stash and retry merge
if success:
    git stash pop
    coordinator.queue_merge(request)  # Re-queue for retry
else:
    git rebase --abort
    git stash pop
    mark_as_failed()
```

**Retry Limit**: Configurable via `ParallelConfig.max_merge_retries` (default: 3)

**Skip Retry When** (BUG-079):
- Merge strategy was used during pull (rebase would fail on same conflicts)
- Max retries exceeded

## Stash Pop Failure Handling

Preserves successful merge even if stash restoration fails:

```python
def _pop_stash() -> bool:
    """Restore stashed changes."""

    result = git stash pop

    if result.returncode != 0:
        # Check for conflicts from stash pop
        if has_unmerged:
            # Clean up conflicted stash pop WITHOUT affecting merge
            git checkout --theirs .  # Restore post-merge state
            git reset HEAD

        # Leave stash intact for manual recovery
        # NEVER do: git reset --hard HEAD (would undo the merge!)

        # Track failure for user notification
        self._stash_pop_failures[issue_id] = "Run 'git stash pop' to recover"

        return False  # Pop failed, but merge preserved
```

**Key Principle**: A successful merge is never undone, even if cleanup fails.

## Configuration

### ParallelConfig

```python
@dataclass
class ParallelConfig:
    max_workers: int = 3
    max_merge_retries: int = 3
    state_file: str = ".ll-parallel-state.json"
    # ... other fields
```

### Constructor

```python
MergeCoordinator(
    config: ParallelConfig,
    logger: Logger,
    repo_path: Path | None = None,
    git_lock: GitLock | None = None,
)
```

**Parameters**:
- `config`: Configuration for parallel processing
- `logger`: Logger instance for output
- `repo_path`: Path to git repository (default: current directory)
- `git_lock`: Shared lock for git operations (created if not provided)

## API Reference

### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start background merge thread |
| `shutdown(wait=True, timeout=30.0)` | Stop background thread |
| `queue_merge(worker_result)` | Queue a worker result for merging |
| `wait_for_completion(timeout=None)` | Wait for all pending merges |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `merged_ids` | `list[str]` | Successfully merged issue IDs |
| `failed_merges` | `dict[str, str]` | Failed issue IDs → error messages |
| `pending_count` | `int` | Number of pending merge requests |
| `stash_pop_failures` | `dict[str, str]` | Issue IDs where stash pop failed (merge succeeded) |

### State Tracking

```python
# Check results after completion
print(f"Merged: {coordinator.merged_ids}")
print(f"Failed: {coordinator.failed_merges}")
print(f"Stash issues: {coordinator.stash_pop_failures}")
```

## Usage Example

### Basic Usage

```python
from little_loops.parallel import MergeCoordinator, ParallelConfig
from little_loops.logger import Logger

config = ParallelConfig(max_merge_retries=3)
logger = Logger(verbose=True)

coordinator = MergeCoordinator(config, logger)
coordinator.start()

# Process worker results
for result in completed_workers:
    coordinator.queue_merge(result)

# Wait for completion
if coordinator.wait_for_completion(timeout=300):
    print(f"Successfully merged: {coordinator.merged_ids}")
    print(f"Failed: {coordinator.failed_merges}")

    # Check for stash pop failures
    if coordinator.stash_pop_failures:
        print("Warning: Some stashes could not be restored:")
        for issue_id, msg in coordinator.stash_pop_failures.items():
            print(f"  {issue_id}: {msg}")
else:
    print("Timeout waiting for merges")

coordinator.shutdown()
```

### Integration with Orchestrator

```python
from little_loops.parallel import ParallelOrchestrator, ParallelConfig
from little_loops.config import BRConfig

# Orchestrator creates and manages merge coordinator
br_config = BRConfig(Path.cwd())
parallel_config = ParallelConfig(max_workers=3)

orchestrator = ParallelOrchestrator(parallel_config, br_config)

# Merge coordinator is automatically started and used
exit_code = orchestrator.run()
```

## Troubleshooting

### "Circuit breaker tripped" Message

**Cause**: 3+ consecutive merge failures

**Resolution**:
1. Check git status for conflicts: `git status`
2. Review recent merge failures in logs
3. Manually resolve any git state issues
4. Restart `ll-parallel` (circuit breaker resets)

### "Stash could not be restored" Warning

**Cause**: Stash pop failed due to conflicts with merged changes

**Resolution**:
```bash
# View stashed changes
git stash show

# Attempt manual restore
git stash pop

# If conflicts, resolve and continue
git add .
git stash drop
```

**Note**: The merge was successful; only the restoration of your local changes failed.

### Repeated "Pull --rebase failed with conflicts"

**Cause**: Specific commits consistently cause rebase conflicts

**Expected Behavior**: After first occurrence, should switch to merge strategy

**Check**:
- Look for "Using merge strategy (known conflict: abc12345)" in logs
- If not switching, may indicate commit hash detection failure

### "Merge blocked by local changes despite stash"

**Cause**: Lifecycle file moves or state file modifications not excluded from stash

**Check**:
1. Look for `.issues/completed/` files in `git status`
2. Check if state file has modifications
3. Verify stash exclusion logic is working

**Resolution**: These should be auto-committed; if not, file a bug report

## Implementation Notes

### Design Decisions

**Why sequential processing?**
- Merging in parallel causes frequent conflicts
- Sequential processing eliminates race conditions
- Slight performance cost is acceptable vs. conflict resolution complexity

**Why not just use git worktree merge?**
- Worktrees can have stale base branches
- Main repo merge ensures consistency
- Allows pull from remote before merge

**Why so many error detectors?**
- Git error messages vary across versions
- Different failure modes require different recovery strategies
- Defensive programming prevents cascading failures

**Why preserve merge on stash pop failure?**
- The work is done; the merge is valuable
- User's local changes are safely in stash
- Better to preserve merge + manual recovery than lose work

### Testing

The merge coordinator has 80%+ test coverage with comprehensive integration tests:

```bash
# Run merge coordinator tests
python -m pytest scripts/tests/test_merge_coordinator.py -v

# Integration tests (require git)
python -m pytest scripts/tests/test_merge_coordinator.py -m integration
```

**Test Categories**:
- Stash/pop operations
- Conflict handling and retry
- Index recovery
- Error detection
- Lifecycle file coordination
- Adaptive pull strategy
- Circuit breaker behavior

### Battle-Tested Evolution

This component has evolved through real-world usage with issues discovered and fixed:

- **BUG-007**: Worktree files leaking to main repo
- **BUG-008**: Stash pop failure losing local changes
- **BUG-018**: Merge blocked by lifecycle file moves (reopened, fixed twice)
- **BUG-038**: Gitignored leaked files causing cascading pull failures
- **ENH-037**: Smarter pull strategy for repeated rebase conflicts
- **BUG-079**: Post-merge rebase causing unnecessary failures
- **BUG-140**: Worktree merge race condition
- **BUG-141**: Context state JSON not excluded from stash
- **BUG-180**: Stale worktree base causing merge failures

Each issue added sophistication to handle edge cases that appear in production use.

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system architecture
- [API.md](API.md) - Complete API reference
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and solutions
- `scripts/little_loops/parallel/merge_coordinator.py` - Source code
- `scripts/tests/test_merge_coordinator.py` - Test suite
