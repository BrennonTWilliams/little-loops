# Worktree Copy Semantics

When `ll-loop run --worktree`, `ll-parallel`, `ll-sprint`, or the merge-verify
gate create an isolated git worktree, `worktree_utils.setup_worktree()`
decides what from the main repo reaches it. This is the single reference for
that contract — see [CLI.md](CLI.md#ll-loop-run-loop--ll-loop-r-loop) for the
`--worktree` flag itself and
[CONFIGURATION.md](CONFIGURATION.md#parallel) for the `worktree_copy_files`
config key.

## What crosses

| Category | Crosses? | Mechanism |
|---|---|---|
| Tracked files (including tracked `.ll/` content: `ll-config.json`, `decisions.d/`, `learning-tests/`) | Yes | `git worktree add` checkout |
| `.claude/` (including gitignored contents, e.g. `settings.local.json`) | Yes | wholesale `copytree`, replace semantics (existing destination is removed first) |
| git `user.name` / `user.email` | Yes | read from the main repo, set via `git config` in the worktree |
| `worktree_copy_files` entries — default `[".claude/settings.local.json", ".env", ".ll/ll.local.md"]` | Yes, files and directories | files use `shutil.copy2`; directories use `shutil.copytree(dirs_exist_ok=True)` (merges into an existing destination, unlike the `.claude/` replace semantics above) |
| `history.db` | Shared by reference, not copied | `LL_HISTORY_DB` is exported into the orchestrator's own `os.environ` before the worktree is created, so every descendant process (host-CLI sessions, FSM shell actions, hooks, pytest runs) reads/writes the main repo's DB — see the [`LL_HISTORY_DB` row in HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md) |
| Other gitignored `.ll/` state (`queue.db*`, `*.lock`, and anything else not listed above) | No | not copied, no sharing mechanism |
| Other untracked/gitignored files outside `.claude/` | No | not copied |

A `worktree_copy_files` entry missing from the main repo is skipped silently
(logged at `debug` level), not an error.

## Verify-gate exception

`verify_epic_branch_before_merge()` calls `setup_worktree(..., copy_files=[])`.
That worktree still gets `.claude/`, git identity, and the shared
`LL_HISTORY_DB` (steps that don't depend on `copy_files`), but none of the
`worktree_copy_files` entries — no `.env`, no `settings.local.json`, no
`.ll/ll.local.md`.

## Related

- [CLI.md](CLI.md#ll-loop-run-loop--ll-loop-r-loop) — `--worktree` flag
- [CONFIGURATION.md](CONFIGURATION.md#parallel) — `worktree_copy_files` config key
- [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md) — `LL_HISTORY_DB` environment variable
- [TROUBLESHOOTING.md](../development/TROUBLESHOOTING.md#worktree-not-inheriting-settings) — symptom/fix for a missing `.claude/settings.local.json` or `.ll/ll.local.md`
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()`, `verify_epic_branch_before_merge()`, `setup_prepatch_worktree()`
