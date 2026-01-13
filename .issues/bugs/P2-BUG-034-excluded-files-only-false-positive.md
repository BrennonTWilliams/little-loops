---
discovered_commit: 08fba71
discovered_date: 2026-01-13
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-034: Work verification: possible false positive on "Only excluded files modified"

## Summary

During parallel processing, ENH-686 failed with "Only excluded files modified" despite the worker spending 15+ minutes processing the issue. This may indicate a false positive in the work verification logic, where meaningful work was done but not detected because it only touched files in excluded directories.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: ENH-686

### Sample Log Output

```
[12:52:29] Dispatching ENH-686 to worker pool
[12:52:29] Copied .claude/ directory to worktree
[12:52:30] Copied .env to worktree
[12:52:30] Created worktree at /Users/brennon/AIProjects/blender-ai/blender-agents/.worktrees/worker-enh-686-20260113-125228 on branch parallel/enh-686-20260113-125228
...
[13:09:19] No meaningful changes detected - only excluded files modified
[13:09:20] ENH-686 failed: Only excluded files modified (e.g., .issues/, thoughts/)
```

### Timeline

- **12:52:29**: ENH-686 dispatched to worker
- **13:09:19**: Work verification failed (16.8 minutes elapsed)
- **Reason**: Only excluded files were modified

## Current Behavior

1. Worker processes issue for 16+ minutes
2. Work verification checks `git diff` for modified files
3. If all modified files are in excluded directories (`.issues/`, `thoughts/`), verification fails
4. Issue is marked as failed with "Only excluded files modified"

## Expected Behavior

Several possible improvements:

1. **Early detection**: If an issue only requires documentation/thought changes, detect this earlier and mark as "documentation-only" rather than failing
2. **Better heuristics**: Consider elapsed time and Claude activity when determining if meaningful work occurred
3. **Issue categorization**: Allow issues to be tagged as "documentation" or "planning" type that don't require code changes
4. **Investigation**: Before failing, check if the excluded changes are actually relevant to the issue

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/work_verification.py`
- **Secondary**: `scripts/little_loops/parallel/worker_pool.py`

## Proposed Investigation

1. Review the actual ENH-686 issue in blender-agents to understand what work was expected
2. Check the worktree branch to see what files were actually modified
3. Determine if the work verification exclusion patterns are too aggressive
4. Consider if some excluded directories (like `thoughts/`) should count as valid work for certain issue types

## Proposed Improvements

1. Add logging of which excluded files were modified (helps diagnose false positives)
2. Consider adding an "allowed" list for issues that only modify documentation
3. Add configuration option to control excluded directories per issue type
4. Improve the "meaningful changes" heuristic to consider:
   - Time spent processing
   - Number of tool calls made
   - Type of issue (enhancement vs bug vs documentation)

## Impact

- **Severity**: Medium (P2) - Causes valid work to be marked as failed
- **Frequency**: 1 occurrence in 9 issues (11.1%)
- **Data Risk**: Low - Work is preserved in worktree branch, but not merged

## Reproduction Steps

1. Create an issue that primarily requires documentation changes (e.g., updating README or adding design docs)
2. Process with `ll-parallel`
3. Observe failure if only excluded files were modified

---

## Status
**Open** | Created: 2026-01-13 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/work_verification.py`: Added diagnostic logging of which excluded files were modified when work verification fails. The warning message now includes the actual file names (truncated to first 10) to help diagnose false positives.
- `scripts/little_loops/parallel/worker_pool.py`: Updated error message returned by `_verify_work_was_done()` to include the actual excluded files that were detected (truncated to first 5), providing actionable diagnostic information.
- `scripts/tests/test_work_verification.py`: Added 4 new tests to verify the new diagnostic logging behavior.

### What This Fixes
Previously when work verification failed, the log output was:
```
[13:09:19] No meaningful changes detected - only excluded files modified
[13:09:20] ENH-686 failed: Only excluded files modified (e.g., .issues/, thoughts/)
```

Now the output includes which files were actually modified:
```
[13:09:19] No meaningful changes detected - only excluded files modified: ['.issues/bugs/ENH-686.md', 'thoughts/plan.md']
[13:09:20] ENH-686 failed: Only excluded files modified: .issues/bugs/ENH-686.md, thoughts/plan.md
```

This helps users distinguish between "no work was done" and "documentation work was done but not detected as meaningful", aiding investigation of false positives.

### Verification Results
- Tests: PASS (42 tests in test_work_verification.py, 731 tests total)
- Lint: PASS
- Types: PASS
