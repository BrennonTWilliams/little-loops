---
id: ENH-3382
type: ENH
title: Refresh the Install line of an existing little-loops CLI Commands block on
  ll-init --upgrade
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-03'
captured_at: '2026-09-03T01:47:09Z'
depends_on:
  - BUG-3380
---

# ENH-3382: Refresh the Install line of an existing little-loops CLI Commands block on ll-init --upgrade

## Summary

`write_claude_md()`, `write_agents_md()`, and `write_gemini_md()`
(`scripts/little_loops/init/writers.py`) return `False` without touching the
file whenever the `## little-loops` section marker is already present, and
nothing in `ll-init --upgrade`, `ll-init apply`, or `skills/update/SKILL.md`
refreshes the existing `## little-loops CLI Commands` block. BUG-3380 fixes
the `Install:` line for *newly generated* blocks only; every consumer that
ran `ll-init` before that fix keeps the wrong
`pip install -e "./scripts[dev]"` line, and re-running `ll-init` does not
correct it.

## Current Behavior

Each writer checks `_CLAUDE_MD_SECTION_MARKER in existing` and returns
`False` early. The block (command list + `Install:` line) is never rewritten
once present, so stale command descriptions and a stale `Install:` line
persist indefinitely.

## Expected Behavior

On `ll-init --upgrade` (and the `requested_upgrade` plan flag in `apply`),
an existing `## little-loops CLI Commands` block is replaced in place with the
freshly rendered block for the current `install_source`/`install_path`
(per the BUG-3380 Expected Behavior table). The rewrite is bounded to the
block: from the `## little-loops CLI Commands` heading to the next `## `
heading or EOF. User content outside the block is untouched. Plain
`ll-init` (no `--upgrade`) keeps today's idempotent no-op so it never
surprises a user who hand-edited the block.

## Proposed Solution

Add a `refresh: bool = False` keyword to the three writers; when set and the
marker is present, splice the newly rendered block over the existing one
instead of returning `False`. Pass `refresh=upgrade` from `_run_yes()` and
`refresh=bool(plan.get("requested_upgrade"))` from `_run_apply()`. Mirror
the existing per-writer tests in `scripts/tests/test_init_core.py`
(`TestWriteClaudeMd`, `TestWriteAgentsMd`) with a refresh case that asserts
the old `Install:` line is gone, the new one is present, and surrounding
user content is byte-identical.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related

- Follow-up to BUG-3380 (per-`install_source` `Install:` line for newly
  generated blocks). Depends on it: the refreshed block must render through
  the same `install_source`/`install_path`-aware `_render_commands_block()`.

## Status

**Open** | Created: 2026-09-03 | Priority: P4
