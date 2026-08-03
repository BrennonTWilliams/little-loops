---
id: ENH-3011
title: ll-init has no git-repo check before writing/updating .gitignore
type: ENH
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
testable: true
labels:
- ll-init
- ux
---

# ENH-3011: `ll-init` has no git-repo check before writing/updating `.gitignore`

## Summary

`ll-init` runs identically whether or not the target directory is a git
repository. It unconditionally creates/updates `.gitignore`
(`writers.update_gitignore`, called from `cli.py:522` in the headless path and
the TUI's `_apply_config`) with no check for `.git/` presence and no warning
to the user that little-loops' gitignore/commit-adjacent features (e.g.
`issues.auto_commit`, git-based scratch cleanup) won't function without one.

## Current Behavior

No git-repo detection exists anywhere in `init/cli.py`, `init/tui.py`,
`init/detect.py`, `init/writers.py`, or `init/validate.py` (confirmed by
search). Running `ll-init` in a non-git directory silently produces the same
output as in a git repo, including a `.gitignore` file that has no practical
effect without version control.

## Scope Boundaries

In scope: detecting absence of a `.git` directory (walking up from
`project_root`, consistent with how other `ll-*` tooling resolves project
roots) and emitting a single non-blocking warning line in both the headless
and TUI output paths. Out of scope: blocking `ll-init` when no git repo is
found, auto-running `git init`, or validating git remote/branch state.

## Expected Behavior

Detect absence of a `.git` directory (walking up, consistent with how other
`ll-*` tooling finds project roots) and surface a one-line, non-blocking
notice — e.g. "Note: this directory isn't a git repository; git-dependent
features (auto-commit, worktree-based parallel epics) won't work until you run
`git init`." — in both the headless and TUI success/summary output. Should not
block init; git-independent config is still valid to write.

## Suggested Fix Direction

Add a small `_is_git_repo(project_root)` helper (walk-up check for `.git`) in
`init/cli.py` or `init/detect.py`, call it once during `_run_yes`/`run_tui`,
and fold the resulting warning into the existing warnings list printed
alongside dependency-validation warnings (`cli.py:546-556`) / the TUI's
warning panel. Add a test in `test_init_core.py`/`test_init_tui.py` asserting
the warning appears when `.git` is absent and doesn't when present.

## Program Design

### Signatures

- `_is_git_repo(project_root: Path) -> bool` — new, `scripts/little_loops/init/cli.py`

### Existing precedent to follow

`scripts/little_loops/paths.py:14-42` (`find_project_root`) already implements
the walk-up `.git` check and documents the non-obvious detail the new helper must
match: **`.git` is checked with `.exists()`, not `.is_dir()`**, because git
worktrees and submodules use a `.git` *file*, not a directory. A helper that uses
`.is_dir()` will false-negative inside every worktree — including the ones
`ll-parallel` creates.

Do **not** call `find_project_root` itself here: it requires an existing `.ll/`
on the walk and returns a root rather than a boolean, so it answers a different
question. Write a small local helper with the same `.exists()` semantics.

### Call Path

`_run_yes`/`run_tui` -> `_is_git_repo(project_root)` -> appended to the
existing dependency-warning list printed at `cli.py:546-556` (headless) and
the TUI's warning panel (`tui.py`, near the Screen-1 warnings).

## Acceptance Criteria

- [ ] Running `ll-init --yes` in a directory with no `.git` on the walk-up prints
      exactly one non-blocking notice line and still exits `0`, having written
      the config.
- [ ] The same run inside a git repo prints no such notice.
- [ ] The notice also appears in the TUI warning panel, not just headless.
- [ ] Detection uses `.exists()` (not `.is_dir()`) so a git *worktree* — where
      `.git` is a file — is correctly treated as a repo. Covered by an explicit test.
- [ ] `.gitignore` is still written in both cases (the notice does not gate writes).
- [ ] Tests in `test_init_core.py` and `test_init_tui.py`;
      `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — not a correctness bug (nothing breaks), but a missed
  opportunity to warn users before they discover git-dependent features
  silently no-op later.
- **Effort**: Small.
- **Risk**: Low — purely additive warning text.
- **Breaking Change**: No.
