---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-341: Commands and skills use hardcoded paths instead of config refs

## Summary

Several commands and skills hardcode directory paths and tool names instead of referencing config values, making them brittle when users customize their config.

## Context

Identified during a config consistency audit. These are in command/skill markdown files where `{{config.*}}` references are available but unused.

## Affected Files

- `commands/create_loop.md`: hardcodes `.loops/` in 6+ locations instead of a config ref
- `commands/loop-suggester.md`: hardcodes `.loops/` in 2 locations
- `commands/manage_release.md`: hardcodes `scripts/pyproject.toml` instead of using `{{config.project.src_dir}}`
- `commands/init.md`: hardcodes `.worktrees` and `.issues` in find patterns

## Current Behavior

Commands and skills hardcode directory paths (`.loops/`, `scripts/`, `.worktrees`, `.issues`) instead of using `{{config.*}}` template references that are available in command/skill markdown files.

## Expected Behavior

Commands and skills should use `{{config.*}}` template references for all configurable paths, ensuring they respect user config overrides.

## Motivation

This enhancement would:
- Ensure config overrides are respected in command/skill behavior
- Improve consistency: some commands already use config refs while others hardcode paths
- Reduce brittleness when users customize their project layout

## Proposed Solution

Replace hardcoded values with `{{config.*}}` template references:
- `.loops/` -> `{{config.loops.loops_dir}}` (after BUG-339 adds the config key)
- `scripts/` -> `{{config.project.src_dir}}`
- `.worktrees` -> `{{config.parallel.worktree_base}}`
- `.issues` -> `{{config.issues.base_dir}}`

## Scope Boundaries

- **In scope**: Replacing hardcoded paths in commands/skills with config references
- **Out of scope**: Adding new config keys (handled by BUG-339), changing command behavior

## Implementation Steps

1. Replace hardcoded `.loops/` in `create_loop.md` and `loop-suggester.md` with config refs
2. Replace hardcoded `scripts/` in `manage_release.md` with config ref
3. Replace hardcoded `.worktrees` and `.issues` in `init.md` with config refs
4. Verify template rendering works correctly

## Integration Map

### Files to Modify
- `commands/create_loop.md` - Replace `.loops/` references
- `commands/loop-suggester.md` - Replace `.loops/` references
- `commands/manage_release.md` - Replace `scripts/` reference
- `commands/init.md` - Replace `.worktrees` and `.issues` references

### Dependent Files (Callers/Importers)
- N/A - commands are user-invoked

### Similar Patterns
- `commands/refine_issue.md` already uses `{{config.issues.base_dir}}` correctly

### Tests
- Manual testing of affected commands

### Documentation
- N/A

### Configuration
- Depends on BUG-339 for `loops.loops_dir` config key

## Impact

- **Priority**: P3 - Config overrides not respected in commands/skills
- **Effort**: Small - String replacements in 4 files
- **Risk**: Low - Template references are a supported feature
- **Breaking Change**: No

## Blocked By

- ~~BUG-339~~: CLI hardcodes .loops directory path (completed - `loops.loops_dir` config key now available)

## Blocks

- ENH-342: Command examples hardcode tool names

## Labels

`enhancement`, `commands`, `config`, `captured`

---

## Status

**Completed** | Created: 2026-02-11 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Replaced 8 hardcoded `.loops/` references with `{{config.loops.loops_dir}}/`
- `commands/loop-suggester.md`: Replaced 1 hardcoded `.loops/` reference with `{{config.loops.loops_dir}}/`
- `commands/manage_release.md`: Replaced all `scripts/pyproject.toml` and `scripts/little_loops/__init__.py` references with `{{config.project.src_dir}}` prefixed paths
- `commands/init.md`: Replaced hardcoded `.issues` and `.worktrees` in find patterns with `{{config.issues.base_dir}}` and `{{config.parallel.worktree_base}}`

### Verification Results
- Tests: PASS (2691 passed)
- Lint: PASS
