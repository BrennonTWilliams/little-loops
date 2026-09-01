---
id: ENH-3379
type: ENH
title: document ll-parallel --cleanup-orphans in CLI.md
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T21:38:04Z'
relates_to:
- BUG-3373
testable: false
program_design_not_applicable: true
---

# ENH-3379: document ll-parallel --cleanup-orphans in CLI.md

## Summary

`ll-parallel --cleanup-orphans` is defined in `scripts/little_loops/cli/parallel.py:97` (entry point calls `_cleanup_orphaned_worktrees()` at line 224) but `docs/reference/CLI.md` contains no occurrence of the literal `--cleanup-orphans`; it only documents `--cleanup` (lines 513, 552). Add a row/paragraph for the flag under the `ll-parallel` section, describing the registry → marker → process-cwd liveness order it now uses after ENH-3376/ENH-3377. Docs-only; no code change. Found while closing BUG-3373.


## Current Behavior

`docs/reference/CLI.md`'s `ll-parallel` Flags table (lines 506-538) and Examples
block document `--cleanup` (row at line 513, example at line 552) but have no
entry for `--cleanup-orphans`, which is defined in
`scripts/little_loops/cli/parallel.py:97` and wired to
`_cleanup_orphaned_worktrees()` at line 224. Anyone scanning CLI.md for
orphan-cleanup behavior has no way to discover the flag or its liveness-check
order.

## Expected Behavior

Add a `--cleanup-orphans` row to the `ll-parallel` Flags table (near
`--cleanup`) describing its liveness-aware behavior: it scans
`worktree_base` for `.ll-*` worktrees and removes only those confirmed dead
by, in order — (1) the out-of-tree PID registry (`_registry_entry_is_live`,
ENH-3376 — survives an in-worktree `git clean -fdx` that would erase the
in-tree marker), (2) an in-tree `.ll-session-<pid>` marker checked via
`os.kill(pid, 0)`, and (3) a last-resort scan of live processes' cwds
(`_collect_live_process_cwds` / `_worktree_has_live_cwd`, ENH-3377). Add a
`--cleanup-orphans --dry-run` example alongside the existing `--cleanup`
example.

## Scope Boundaries

- Out of scope: changing `--cleanup-orphans` behavior, renaming the flag, or
  touching `_cleanup_orphaned_worktrees()` / the ENH-3376/ENH-3377 liveness
  logic itself — this issue documents existing, shipped behavior only.
- Out of scope: a general audit of other undocumented `ll-parallel` flags;
  scope is limited to `--cleanup-orphans`.

## Impact

- **Priority**: P4 - Docs-only gap; doesn't block any workflow, but leaves a
  shipped flag undiscoverable via the CLI reference.
- **Effort**: Small - One table row, one descriptive paragraph, and one
  example line in `docs/reference/CLI.md`; no code changes.
- **Risk**: Low - Documentation-only change; no behavior touched.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-01 | Priority: P4


## Session Log
- `/ll:ready-issue` - 2026-09-01T21:41:47 - `4b16ef85-c362-493d-849c-c846475b72fa.jsonl`
