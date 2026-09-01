---
description: Clean orphaned git worktrees from interrupted ll-parallel/ll-loop runs
---

# Cleanup Worktrees

You are tasked with cleaning up orphaned git worktrees that may remain after interrupted or failed ll-parallel or ll-loop runs.

This command delegates to `ll-parallel --cleanup-orphans`, which uses the canonical Python orphan-detection logic (`_is_ll_worktree` / `_cleanup_orphaned_worktrees`). It skips worktrees owned by live processes — checking an out-of-tree liveness registry first (ENH-3376, survives a `git clean -fdx` run inside the worktree that would erase the in-tree marker), falling back to the in-tree session marker when no registry entry exists, and finally a process-cwd sweep when neither signal is live (ENH-3377, catches a still-running host-CLI child left behind after its owning `ll-loop`/`ll-parallel` process was killed; skips with a warning instead of deleting if the sweep itself cannot be performed) — and deletes both the worktree directory and its associated branch (for both `parallel/*` and loop-style `YYYYMMDD-HHMMSS-*` branches).

## Process

### 1. Parse Mode

```
MODE="${mode:-run}"
```

### 2. Execute

#### Mode: dry-run

Preview what would be cleaned without making changes:

```bash
ll-parallel --cleanup-orphans --dry-run
```

#### Mode: run

Remove orphaned worktrees (skips any worktree with a live out-of-tree liveness registry entry — ENH-3376 — or, failing that, a still-alive session-marker PID, or, failing that, a live process whose cwd is inside the worktree — ENH-3377):

```bash
ll-parallel --cleanup-orphans
```

---

## Arguments

{{args}}

- **mode** (optional, default: `run`): Execution mode
  - `run` - Execute the cleanup (default)
  - `dry-run` - Preview what would be cleaned without making changes

---

## Examples

```bash
# Clean all orphaned worktrees
/ll:cleanup-worktrees

# Preview what would be cleaned
/ll:cleanup-worktrees dry-run
```
