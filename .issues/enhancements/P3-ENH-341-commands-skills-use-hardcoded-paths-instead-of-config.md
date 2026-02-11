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

## Proposed Fix

Replace hardcoded values with `{{config.*}}` template references:
- `.loops/` -> `{{config.loops.loops_dir}}` (after BUG-339 adds the config key)
- `scripts/` -> `{{config.project.src_dir}}`
- `.worktrees` -> `{{config.parallel.worktree_base}}`
- `.issues` -> `{{config.issues.base_dir}}`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
