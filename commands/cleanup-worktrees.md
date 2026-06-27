---
description: Clean orphaned git worktrees from interrupted ll-parallel/ll-loop runs
argument-hint: "[mode]"
allowed-tools:
  - Bash(ll-parallel:*)
arguments:
  - name: mode
    description: Execution mode (run|dry-run)
    required: false
---

# Cleanup Worktrees

You are tasked with cleaning up orphaned git worktrees that may remain after interrupted or failed ll-parallel or ll-loop runs.

This command delegates to `ll-parallel --cleanup-orphans`, which uses the canonical Python orphan-detection logic (`_is_ll_worktree` / `_cleanup_orphaned_worktrees`). It skips worktrees owned by live processes and deletes both the worktree directory and its associated branch (for both `parallel/*` and loop-style `YYYYMMDD-HHMMSS-*` branches).

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

Remove orphaned worktrees (skips any worktree whose session-marker PID is still alive):

```bash
ll-parallel --cleanup-orphans
```

---

## Arguments

$ARGUMENTS

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
