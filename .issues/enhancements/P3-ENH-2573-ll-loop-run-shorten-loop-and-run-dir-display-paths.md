---
id: ENH-2573
title: ll-loop run — show loop filename / relative run_dir instead of absolute paths
type: ENH
priority: P3
status: done
completed_at: 2026-07-10T02:52:26Z
discovered_date: "2026-07-10"
discovered_by: manual
labels: [cli, loops, ux, path-display]
---

# ENH-2573: ll-loop run — show loop filename / relative run_dir instead of absolute paths

## Summary

The artifact header printed by `ll-loop run ...` rendered every path-like
context value as an absolute path, which is noisy and leaks the machine's full
directory layout:

```
loop: /Users/brennon/AIProjects/brenentech/little-loops/scripts/little_loops/loops/general-task.yaml
run_dir: /Users/brennon/AIProjects/ai-workspaces/ll-labs/cards/.loops/runs/general-task-20260709T182714/
```

The header now shows the bare filename for a built-in FSM loop, a cwd-relative
path for a project-level (`.loops/`) loop, and relativizes other path values
(e.g. `run_dir`) to the current working directory when they live under it:

```
loop: general-task.yaml
run_dir: .loops/runs/general-task-20260709T182714/
```

## Current Behavior (before)

`_artifact_lines()` in `scripts/little_loops/cli/loop/_helpers.py` appended
`("loop", str(loop_path))` verbatim and emitted each path-like context value
(any string that looks like a filesystem path and has no unresolved `${...}`
template) exactly as stored — always absolute for `run_dir` and for built-in
loop paths.

## Expected Behavior (after)

- Built-in FSM loop (bundled under `get_builtin_loops_dir()`) → filename only
  (`general-task.yaml`).
- Project-level FSM loop under the cwd (typically in `.loops/`) → cwd-relative
  path (`.loops/general-task.yaml`).
- Other path-like context values (e.g. `run_dir`) → cwd-relative when nested
  under the cwd, with any trailing slash preserved
  (`.loops/runs/general-task-20260709T182714/`).
- Paths outside the cwd, or already-relative values, are left unchanged.

## Changes

- `scripts/little_loops/cli/loop/_helpers.py`
  - Added `_relativize_to_cwd(value)` — renders an absolute path nested under
    `Path.cwd()` relative to it (preserving a trailing slash); returns the value
    unchanged when it is already relative, points outside the cwd, or raises
    `ValueError`/`OSError`.
  - Added `_display_loop_path(loop_path)` — returns `loop_path.name` when the
    loop resolves under `get_builtin_loops_dir()`, otherwise falls back to
    `_relativize_to_cwd(str(loop_path))`.
  - `_artifact_lines()` now uses `_display_loop_path()` for the `loop` entry and
    `_relativize_to_cwd()` for every other path-like context value.

## Acceptance Criteria

- [x] Built-in loop path renders as the filename only.
- [x] Project-level `.loops/` loop path renders as a cwd-relative path.
- [x] Absolute `run_dir` under the cwd renders relative, keeping its trailing slash.
- [x] Paths outside the cwd and already-relative values are unchanged.
- [x] All four pre-existing `TestArtifactLines` tests remain compatible.
- [x] New tests added in `scripts/tests/test_state_feed_renderer.py`
      (`test_builtin_loop_shows_filename_only`,
      `test_project_loop_shows_cwd_relative_path`,
      `test_context_path_under_cwd_is_relativized`,
      `test_context_path_outside_cwd_is_unchanged`).

## Notes

Both edited files pass `py_compile`. The full `pytest` suite was not run in this
session: the connected sandbox only has Python 3.10, while the project requires
3.11+ (`datetime.UTC`), so the suite could not execute there. The pure
path-handling logic was verified with a standalone script replicating the two
new helpers against all acceptance cases (all passed); the suite should be run
in a 3.11+ environment to confirm end-to-end.
