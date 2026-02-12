---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-338: Hook scripts ignore configured paths

## Summary

Hook shell scripts hardcode directory paths instead of reading from `ll-config.json`, meaning user config overrides for `issues.base_dir` and `parallel.worktree_base` are silently ignored.

## Context

Identified during a config consistency audit of the codebase. These scripts cannot adapt to custom config paths.

## Current Behavior

Hook shell scripts (`check-duplicate-issue-id.sh`, `session-cleanup.sh`) and the `cleanup_worktrees.md` command hardcode directory paths (`.issues`, `.worktrees`) instead of reading from `ll-config.json`. Users who customize `issues.base_dir` or `parallel.worktree_base` in their config have those overrides silently ignored.

## Expected Behavior

Hook scripts should read directory paths from `.claude/ll-config.json` with fallback defaults, so user config overrides are respected.

## Steps to Reproduce

1. Set `issues.base_dir` to a custom path in `.claude/ll-config.json`
2. Trigger the `check-duplicate-issue-id.sh` hook (e.g., via issue capture)
3. Observe: hook checks `.issues/` instead of the configured path

## Actual Behavior

Hook scripts always use hardcoded paths regardless of config settings.

## Root Cause

- **File**: `hooks/scripts/check-duplicate-issue-id.sh`
- **Anchor**: `line 74, ISSUES_DIR=".issues"`
- **Cause**: Shell scripts were written with hardcoded defaults and never wired to read from the JSON config file

## Affected Files

- `hooks/scripts/check-duplicate-issue-id.sh` (line 74): hardcodes `ISSUES_DIR=".issues"` instead of reading `issues.base_dir`
- `hooks/scripts/session-cleanup.sh` (lines 17-20): hardcodes `if [ -d .worktrees ]` instead of reading `parallel.worktree_base`
- `commands/cleanup_worktrees.md` (line 24): hardcodes `WORKTREE_BASE=".worktrees"` despite documenting `{{config.parallel.worktree_base}}` on line 16

## Proposed Solution

Add jq-based config reading with fallback defaults:

```bash
CONFIG_FILE=".claude/ll-config.json"
ISSUES_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")
WORKTREE_BASE=$(jq -r '.parallel.worktree_base // ".worktrees"' "$CONFIG_FILE" 2>/dev/null || echo ".worktrees")
```

## Implementation Steps

1. Add jq-based config reading with fallback defaults to `check-duplicate-issue-id.sh`
2. Add jq-based config reading to `session-cleanup.sh`
3. Fix `cleanup_worktrees.md` to use `{{config.parallel.worktree_base}}` consistently
4. Test hooks with both default and custom config paths

## Integration Map

### Files to Modify
- `hooks/scripts/check-duplicate-issue-id.sh` - Read `issues.base_dir` from config
- `hooks/scripts/session-cleanup.sh` - Read `parallel.worktree_base` from config
- `commands/cleanup_worktrees.md` - Use `{{config.parallel.worktree_base}}` consistently

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` - Registers these hook scripts

### Similar Patterns
- `commands/init.md` also hardcodes `.worktrees` and `.issues` (tracked in ENH-341)

### Tests
- Manual testing of hooks with custom config paths

### Documentation
- N/A

### Configuration
- `.claude/ll-config.json` - `issues.base_dir` and `parallel.worktree_base` keys

## Impact

- **Priority**: P3 - Config overrides silently ignored, but defaults work correctly
- **Effort**: Small - Add config reading to 3 files
- **Risk**: Low - Fallback defaults preserve existing behavior
- **Breaking Change**: No

## Labels

`bug`, `hooks`, `config`, `captured`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle and config loading |

---

## Status

**Completed** | Created: 2026-02-11 | Completed: 2026-02-11 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `hooks/scripts/check-duplicate-issue-id.sh`: Read `issues.base_dir` from `ll-config.json` with `.issues` fallback
- `hooks/scripts/session-cleanup.sh`: Read `parallel.worktree_base` from `ll-config.json` with `.worktrees` fallback
- `commands/cleanup_worktrees.md`: Replace hardcoded `.worktrees` with `{{config.parallel.worktree_base}}`

### Verification Results
- Tests: PASS (2691 passed)
- Lint: PASS
- Shell syntax: PASS
