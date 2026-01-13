---
discovered_commit: b0fced8
discovered_branch: main
discovered_date: 2026-01-13T15:05:00Z
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# ENH-037: Smarter Pull Strategy for Repeated Rebase Conflicts

## Summary

Improve the merge coordinator's pull strategy to detect and handle commits that consistently cause rebase conflicts. Currently, the system aborts the rebase and continues without the pull, which works but logs warnings and may miss important upstream changes.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 2 (BUG-692 and BUG-694)
**Affected External Issues**: BUG-692, BUG-694

### Sample Log Output

```
[15:15:47] Pull --rebase failed with conflicts: From https://github.com/BrennonTWilliams/blender-agents
 * branch              main       -> FETCH_HEAD
Rebasing (54/141)
dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detectio
[15:15:47] Detected rebase in progress, aborting...
[15:15:47] Aborted incomplete rebase from pull
[15:15:47] Continuing without pull after rebase abort
[15:15:48] Merged BUG-692 successfully

[15:23:17] Pull --rebase failed with conflicts: From https://github.com/BrennonTWilliams/blender-agents
 * branch              main       -> FETCH_HEAD
Rebasing (54/143)
dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detectio
[15:23:17] Detected rebase in progress, aborting...
[15:23:17] Aborted incomplete rebase from pull
[15:23:17] Continuing without pull after rebase abort
[15:23:18] Merged BUG-694 successfully
```

## Current Behavior

1. Merge coordinator attempts `git pull --rebase` before merging
2. Rebase conflicts with specific commits (e.g., `ae3b85ec1cac501058f6e5da362be37be1c99801`)
3. System detects rebase in progress and aborts it
4. Continues without pull, merge proceeds
5. Same conflict repeats for subsequent merges

## Problem

The same commit (`ae3b85ec1cac501058f6e5da362be37be1c99801`) causes rebase conflicts repeatedly:
- **Wasted time**: Each merge attempts rebase, fails, and aborts
- **Log noise**: Repeated warnings clutter the output
- **Risk**: Skipping pull means missing potentially important upstream changes
- **No learning**: System doesn't remember problematic commits

## Expected Behavior

1. Detect when specific commits cause repeated rebase conflicts
2. Track problematic commits in memory (or state file)
3. Use alternative strategies:
   - Skip rebase and use `git pull --no-rebase` (merge strategy)
   - Or skip problematic commits with `git rebase --skip`
   - Or fetch without merging and check for conflicts before merging
4. Log the strategy change once, not repeated warnings

## Proposed Implementation

### Option 1: Track Problematic Commits and Use Merge Strategy

```python
class MergeCoordinator:
    def __init__(self, ...):
        # ...
        self._problematic_commits: set[str] = set()

    def _detect_conflict_commit(self, error_output: str) -> str | None:
        """Extract commit hash from rebase conflict output."""
        # Match patterns like:
        # "dropping ae3b85ec1cac501058f6e5da362be37be1c99801 feat(ai): add stall detectio"
        import re
        match = re.search(r'dropping ([a-f0-9]{40})', error_output)
        return match.group(1) if match else None

    def _pull_with_fallback(self, issue_id: str) -> bool:
        """Attempt pull with rebase, falling back to merge if commits are problematic."""
        # Try rebase first
        pull_result = self._git_lock.run(
            ["pull", "--rebase", "origin", "main"],
            cwd=self.repo_path,
            timeout=60,
        )

        if pull_result.returncode == 0:
            return True

        # Handle failure
        if self._is_rebase_in_progress():
            conflict_commit = self._detect_conflict_commit(pull_result.stderr)
            if conflict_commit:
                if conflict_commit in self._problematic_commits:
                    # Known problematic commit, use merge strategy
                    self.logger.info(f"Using merge strategy (known conflict: {conflict_commit[:8]})")
                    self._abort_rebase_if_in_progress()
                    return self._pull_merge_strategy()
                else:
                    # First time seeing this conflict
                    self._problematic_commits.add(conflict_commit)
                    self.logger.warning(f"New rebase conflict with {conflict_commit[:8]}, tracking for future merges")
                    self._abort_rebase_if_in_progress()
                    # Continue without pull as before
                    return True

        # Handle other errors...
```

### Option 2: Fetch and Check Strategy (Simpler)

```python
def _pull_smart(self, issue_id: str) -> bool:
    """Fetch first, then decide on merge strategy."""
    # Fetch without merging
    fetch_result = self._git_lock.run(
        ["fetch", "origin", "main"],
        cwd=self.repo_path,
        timeout=30,
    )

    if fetch_result.returncode != 0:
        self.logger.error(f"Fetch failed: {fetch_result.stderr}")
        return False

    # Check if we're behind
    ahead_behind = self._git_lock.run(
        ["rev-list", "--left-right", "--count", "HEAD...origin/main"],
        cwd=self.repo_path,
    )

    if ahead_behind.returncode == 0:
        behind = int(ahead_behind.stdout.split()[1])
        if behind == 0:
            # Already up to date
            return True

    # Try rebase, fall back to merge on conflict
    pull_result = self._git_lock.run(
        ["pull", "--rebase", "origin", "main"],
        cwd=self.repo_path,
        timeout=60,
    )

    if pull_result.returncode != 0 and self._is_rebase_in_progress():
        self.logger.info("Rebase conflict detected, using merge strategy instead")
        self._abort_rebase_if_in_progress()
        # Try merge strategy
        merge_result = self._git_lock.run(
            ["pull", "--no-rebase", "origin", "main"],
            cwd=self.repo_path,
            timeout=60,
        )
        return merge_result.returncode == 0

    return pull_result.returncode == 0
```

### Option 3: Configurable Pull Strategy

Allow users to configure the default strategy:

```yaml
# .ll-config.json
{
  "parallel": {
    "pull_strategy": "rebase",  # or "merge", or "auto"
    "pull_fallback_on_conflict": true
  }
}
```

## Affected Components

- **Tool**: ll-parallel
- **Module**: `scripts/little_loops/parallel/merge_coordinator.py` (lines 737-757)

## Acceptance Criteria

- [ ] Detect and extract problematic commit hash from rebase conflict output
- [ ] Track problematic commits in memory during a run
- [ ] Use `git pull --no-rebase` (merge strategy) after detecting repeated conflict
- [ ] Log strategy change clearly (not just warnings)
- [ ] Integration test: rebase conflict triggers merge strategy fallback
- [ ] Unit test: commit hash extraction from conflict output
- [ ] No regression: successful pulls still use rebase by default
- [ ] Consider adding config option for default pull strategy

## Impact

- **Severity**: Low (P3) - Current behavior works but is noisy
- **Effort**: Low - Small addition to existing pull logic
- **Risk**: Low - Fallback behavior is similar to current abort-and-continue

## Related Issues

None

## Blocked By

None

## Blocks

None

## Labels

`enhancement`, `cli`, `ll-parallel`, `git`, `merge-coordinator`, `optimization`

---

## Status

**Open** | Created: 2026-01-13 | Priority: P3
