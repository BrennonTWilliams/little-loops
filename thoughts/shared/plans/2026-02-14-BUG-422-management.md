# BUG-422 Implementation Plan: Add timeout to subprocess.run in issue_lifecycle.py

**Date**: 2026-02-14
**Issue**: P3-BUG-422-git-subprocess-run-without-timeout
**Action**: fix

## Problem

Six `subprocess.run()` calls in `issue_lifecycle.py` lack timeout parameters. If git hangs (GPG passphrase, network issues, lock contention), these calls block indefinitely — especially problematic in automated/parallel processing.

## Research Findings

- **6 calls without timeout** in `issue_lifecycle.py` (lines 252, 269, 270, 310, 352, 362)
- **Existing pattern**: `parallel/git_lock.py` and `parallel/merge_coordinator.py` use `timeout=30` for standard git ops
- **Timeout handling pattern**: Catch `subprocess.TimeoutExpired`, log warning, continue or re-raise
- **Tests**: `scripts/tests/test_issue_lifecycle.py` uses mocks — no subprocess calls in tests

## Solution

Add `timeout=30` to all 6 `subprocess.run()` calls. Wrap each in try/except `subprocess.TimeoutExpired` with appropriate handling:

### Changes

**File: `scripts/little_loops/issue_lifecycle.py`**

1. **`_is_git_tracked()` (line 252)** — `git ls-files`
   - Add `timeout=30`
   - Catch TimeoutExpired, return `False` (conservative: treat as untracked)

2. **`_cleanup_stale_source()` (lines 269-274)** — `git add -A` + `git commit`
   - Add `timeout=30` to both calls
   - Catch TimeoutExpired, log warning (cleanup is best-effort)

3. **`_move_issue_to_completed()` (line 310)** — `git mv`
   - Add `timeout=30`
   - Catch TimeoutExpired, fall back to manual copy + delete (same as returncode != 0 path)

4. **`_commit_issue_completion()` (lines 352, 362)** — `git add -A` + `git commit`
   - Add `timeout=30` to both calls
   - Catch TimeoutExpired on add: log warning, continue
   - Catch TimeoutExpired on commit: log warning, return True (best-effort)

## Success Criteria

- [ ] All 6 subprocess.run calls have timeout=30
- [ ] TimeoutExpired handled gracefully at each call site
- [ ] Tests pass
- [ ] Lint passes
- [ ] Type check passes

## Scope

- **In scope**: `issue_lifecycle.py` only (per issue)
- **Out of scope**: Other files with missing timeouts (separate issues)
