# BUG-338: Hook scripts ignore configured paths - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P3-BUG-338-hook-scripts-ignore-configured-paths.md
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

Three files hardcode directory paths instead of reading from `ll-config.json`:
1. `hooks/scripts/check-duplicate-issue-id.sh` - hardcodes `.issues`
2. `hooks/scripts/session-cleanup.sh` - hardcodes `.worktrees`
3. `commands/cleanup_worktrees.md` - hardcodes `.worktrees` despite documenting `{{config.parallel.worktree_base}}`

## Solution

- Shell scripts: Add `jq`-based config reading with fallback defaults
- Command template: Replace hardcoded value with `{{config.parallel.worktree_base}}`

## Implementation

### Phase 1: check-duplicate-issue-id.sh
- Read `issues.base_dir` from config once after jq availability check
- Use configured value for both the early path check and directory resolution
- [x] Implemented

### Phase 2: session-cleanup.sh
- Read `parallel.worktree_base` from config with jq guard (cleanup must never fail)
- Use configured value for directory check and grep pattern
- [x] Implemented

### Phase 3: cleanup_worktrees.md
- Replace `WORKTREE_BASE=".worktrees"` with `WORKTREE_BASE="{{config.parallel.worktree_base}}"`
- [x] Implemented

## Verification
- [x] Tests pass
- [x] Lint passes
- [x] Shell scripts have valid syntax
