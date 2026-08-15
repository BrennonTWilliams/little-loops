---
id: BUG-3180
type: BUG
title: ll-mcp tasks/* and loop_start resolve .loops against cwd, not the resolved
  project root
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T16:14:54Z'
parent: EPIC-3127
labels:
- mcp
- multi-host
completed_at: '2026-08-15T16:31:35Z'
---

# BUG-3180: ll-mcp tasks/* and loop_start resolve .loops against cwd, not the resolved project root

## Summary

`tasks.py::_loops_dir` builds its path as `Path(config.loops.loops_dir)`, and
`config.loops.loops_dir` is the raw config string `".loops"` — a *relative* path. The
joining accessor is `BRConfig.get_loops_dir()` (`config/core.py:564`), which returns
`project_root / loops_dir`.

So every consumer of `_loops_dir` — `loop_start` (`tools.py::_tool_loop_start`),
`tasks/get` (`make_tasks_get_handler`), and `tasks/cancel`
(`make_tasks_cancel_handler`) — operates on `$CWD/.loops` rather than the project root
resolved by ENH-3171's `--project-root` / `LL_MCP_PROJECT_ROOT`. ENH-3171 swapped
`BRConfig(Path.cwd())` for `BRConfig(project_root)` at this site but left the
non-joining accessor in place, so the resolved root never reaches the filesystem path.

Reproduced: with a state file at `proj/.loops/.running/run-1.state.json` and
`project_root=proj`, `tasks/get` raises `-32002` (`no run found`) when cwd is elsewhere,
and reads the file normally when cwd is `proj`.

The existing guard, `test_enh_3171_mcp_project_root.py::test_loop_start_resolves_loops_dir_from_explicit_root`,
is a false positive: it starts a loop named `does-not-exist`, which is missing under both
the explicit root and cwd, so the `is_error` assertion holds with the bug present.

## Expected Behavior

`_loops_dir(project_root)` returns an absolute `project_root / ".loops"`, so a host that
spawns `ll-mcp --project-root /abs/path` from any cwd can start, poll, and cancel runs in
that project.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
