---
id: EPIC-3111
title: Worktree state inheritance — machine-local state, history, and docs
type: EPIC
priority: P2
status: done
captured_at: '2026-08-08T20:32:03Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
relates_to: [BUG-3112, ENH-3113, ENH-3114, ENH-3115]
labels:
- worktree
- automation
- history
---

# EPIC-3111: Worktree state inheritance — machine-local state, history, and docs

## Summary

`worktree_utils.setup_worktree()` is the single entry point for every
auto-created worktree in little-loops — FSM sub-loop attach
(`fsm/executor.py:942`), `ll-loop run --worktree` (`cli/loop/run.py:484`),
ll-parallel workers (`parallel/worker_pool.py:774`), and the epic verify gate
(`worktree_utils.py:445`). Beyond `git worktree add`, it does exactly three
things: copies git identity, `copytree`s `.claude/` wholesale, and copies the
files listed in `parallel.worktree_copy_files` (default
`[".claude/settings.local.json", ".env"]`).

Everything else machine-local is left behind. Tracked `.ll/` content arrives via
the git checkout, but every gitignored `.ll/` file does not — most consequentially
`history.db` (the session/analytics store) and `ll.local.md` (local config
overrides plus the machine-written `## Active Rules`). A worktree session
therefore runs with a subtly different config than the main tree and writes its
history into a throwaway DB that `cleanup_worktree` deletes.

This epic groups the fixes: make history writes land in the real store, make
local config reach the worktree, remove the copy/copytree inconsistency in
`copy_files`, and document the resulting contract so the next person does not
have to read three call sites and `.gitignore` to answer "what crosses into a
worktree?".

## Goal

A worktree session sees the same effective configuration as the main tree, and
the work it records (history, analytics, test runs) survives worktree teardown.

## Scope

**In scope**
- `scripts/little_loops/worktree_utils.py` — `setup_worktree` copy semantics
- The four `setup_worktree` call sites and the environment they hand to child
  processes
- `parallel.worktree_copy_files` config schema and defaults
- Reference documentation for worktree copy semantics

**Out of scope**
- Worktree lifecycle/cleanup policy (`cleanup_worktree`, orphan sweeping)
- Epic-branch merge/verify behavior beyond what the copy semantics affect
- Any change to `.gitignore` policy for `.ll/`

## Children

- **BUG-3112** — Worktree sessions write session history to a throwaway `.ll/history.db` that is deleted with the worktree
- **ENH-3113** — Worktrees don't inherit machine-local `.ll/` state (`ll.local.md` config overrides and Active Rules)
- **ENH-3114** — `worktree_copy_files` silently skips directory entries while `.claude/` gets a full `copytree`
- **ENH-3115** — Document what does and does not cross into an auto-created worktree

## Motivation

Worktree-scoped automation is the default path for real work in this repo:
`sprint-refine-and-implement` → `auto-refine-and-implement` attaches a scratch
worktree per epic branch, and ll-parallel runs every worker in one. Any state
that fails to cross the boundary silently degrades exactly the runs that matter
most — the long autonomous ones nobody is watching.

The failure mode is quiet in both directions. Reads degrade without erroring
(empty SessionStart digest, `decisions.py:574` falling back to a filesystem
scan instead of `scan_completed_issues_from_db`), and writes succeed into a
directory that is about to be `rmtree`d. Nothing surfaces a warning.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — `setup_worktree` (:157-269)
- `scripts/little_loops/fsm/executor.py` (:942) — sub-loop worktree attach
- `scripts/little_loops/cli/loop/run.py` (:484) — `--worktree` flag
- `scripts/little_loops/parallel/worker_pool.py` (:774) — worker worktrees
- `scripts/little_loops/config/automation.py` (:91, :131) — `worktree_copy_files` default
- `scripts/little_loops/config-schema.json` (:360) — schema description

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/db.py` — `_resolve_db_path`, `LL_HISTORY_DB`
- `scripts/little_loops/subprocess_utils.py` — environment handed to host CLI invocations

### Tests
- `scripts/tests/` — existing worktree_utils coverage; add per-child cases

### Documentation
- `docs/reference/` — new or extended worktree copy-semantics reference (ENH-3115)

## Impact

- **Priority**: P2 - Silent data loss and silent config divergence on the default automation path
- **Effort**: Medium - Four scoped changes over one well-isolated module plus its call sites
- **Risk**: Medium - Sharing one SQLite DB across concurrent worktree processes is the intended design (WAL + `busy_timeout`) but widens contention
- **Breaking Change**: No

## Success Metrics

- A sub-loop run inside a worktree leaves its session/analytics rows in the main
  repo's `.ll/history.db` after the worktree is torn down
- A worktree session resolves the same `project.test_cmd` as the main tree when
  `.ll/ll.local.md` overrides it
- `worktree_copy_files` entries behave consistently for files and directories
- The copy contract is stated in one documented place

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

- Verified 2026-08-10 via /ll:verify-issues: all child issues confirmed done — closing epic.

## Session Log
- `/ll:verify-issues` - 2026-08-10T16:25:23 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:49 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Done** | Created: 2026-08-08 | Priority: P2
