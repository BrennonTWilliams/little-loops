---
discovered_date: "2026-04-22"
discovered_by: issue-size-review
parent_issue: ENH-1197
depends_on: [FEAT-1075, ENH-1176]
decision_needed: false
size: Small
---

# ENH-1249: Add PID Liveness Check to cleanup-worktrees Command

## Summary

`commands/cleanup-worktrees.md` is a shell-only command that blindly removes all `worker-*` directories (lines 109-144) with no liveness check. It risks nuking worktrees belonging to a sibling `ll-parallel` run that is currently active. Add a `.ll-session-<pid>` probe that mirrors `orchestrator.py:249-265` before removing each directory.

## Parent Issue

Decomposed from ENH-1197: Harden Worktree Cleanup Against SIGKILL Mid-Teardown

## Current Behavior

`commands/cleanup-worktrees.md` lines 109-144: iterates `worker-*` directories and removes them with `git worktree remove --force` + `rm -rf`. No process-liveness check. If a user runs `/ll:cleanup-worktrees` while an `ll-parallel` job is running in another terminal, live worker worktrees are nuked mid-run.

## Expected Behavior

Before removing any `worker-*` directory, the command reads the `.ll-session-<pid>` marker file (glob `<dir>/.ll-session-*`), extracts the PID, and runs `kill -0 <pid>` to check liveness. If the process is alive, skip that directory with a log line `Skipping <dir>: worker process <pid> is alive`. Only remove worktrees whose process is confirmed dead (or has no marker file).

## Proposed Solution

In the cleanup loop in `commands/cleanup-worktrees.md` (around line 120-135), add a liveness probe:

```bash
for dir in $(find .worktrees -maxdepth 1 -name "worker-*" -type d); do
    marker=$(ls "${dir}/.ll-session-"* 2>/dev/null | head -1)
    if [ -n "$marker" ]; then
        pid=$(basename "$marker" | sed 's/^\.ll-session-//')
        if kill -0 "$pid" 2>/dev/null; then
            echo "Skipping ${dir}: worker process ${pid} is alive"
            continue
        fi
    fi
    # proceed with removal
    git worktree remove --force "$dir" 2>/dev/null || true
    rm -rf "$dir"
done
```

Mirror the liveness check pattern from `orchestrator.py:249-265`.

## Files to Modify

- `commands/cleanup-worktrees.md` — add `.ll-session-*` PID probe in the cleanup loop (lines 109-144)

## Acceptance Criteria

- Running `/ll:cleanup-worktrees` while `ll-parallel` is active does NOT remove live worker worktrees
- Dead or unowned `worker-*` directories are still removed as before
- Skipped live directories produce a log line identifying the PID
- No new Python changes required (shell-only change)

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`

## Session Log
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
