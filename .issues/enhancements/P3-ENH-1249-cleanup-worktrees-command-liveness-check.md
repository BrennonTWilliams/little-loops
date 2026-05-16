---
completed_at: 2026-04-22T19:15:25Z
discovered_date: "2026-04-22"
discovered_by: issue-size-review

depends_on: [FEAT-1075, ENH-1176]
decision_needed: false
size: Small
confidence_score: 90
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
parent: ENH-1197
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

## Integration Map

### Files to Modify
- `commands/cleanup-worktrees.md:109-138` — run-mode cleanup loop: insert liveness probe before `git worktree remove --force`
- `commands/cleanup-worktrees.md:87-93` — dry-run loop: add liveness label so output shows `[SKIP - live]` vs `[REMOVE]` for each directory

### Dependent Files (Callers/Importers)
- `scripts/little_loops/worktree_utils.py:96-99` — writes `.ll-session-<pid>` marker after every `setup_worktree()` call; this is the file that creates the markers the probe will read. Called by `ll-parallel`, `ll-sprint`, and `ll-loop` runners.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/worktree-health.yaml:29` — FSM loop that invokes `/ll:cleanup-worktrees`; will automatically benefit from liveness check, no change required [Agent 1 finding]
- `hooks/scripts/session-cleanup.sh:27-43` — session cleanup hook with similar blind worktree-removal logic (no liveness check); out of scope for this issue but a candidate for follow-on hardening [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/parallel/orchestrator.py:249-265` — Python equivalent of the exact liveness check to mirror; handles `ProcessLookupError` (dead), `ValueError` (bad filename), `PermissionError` (alive, no signal permission)
- `scripts/little_loops/fsm/concurrency.py:26-38` — `_process_alive()` function with same ESRCH/EPERM logic (Python reference; cannot be imported into shell)

### Tests
- `scripts/tests/test_orchestrator.py:402-428` — `test_skips_worktree_owned_by_live_process`: uses current PID as marker, asserts directory survives cleanup
- `scripts/tests/test_orchestrator.py:430-463` — `test_removes_worktree_with_dead_process_marker`: patches `os.kill` to raise `ProcessLookupError`, asserts directory is removed
- No unit test file exists for `commands/cleanup-worktrees.md` (shell command — not directly unit-testable); acceptance criteria verified manually

### Documentation
- `docs/reference/COMMANDS.md:409-413` — add note on liveness-skip behavior; dry-run mode will now emit `[SKIP - live <pid>]` labels, not currently described here
- `commands/help.md:149-151` — describes the command as "Clean orphaned git worktrees from interrupted runs"; optionally extend to mention the live-worker skip behavior [Agent 2 finding, wiring pass added by `/ll:wire-issue`]

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add liveness probe to the run-mode loop** (`commands/cleanup-worktrees.md:109-138`): after the `if [ -n "$w" ] && [ -d "$w" ]` guard (line 110), insert the `.ll-session-*` glob + `kill -0` check before the `echo "Removing: $WORKTREE_NAME"` line (line 114). Use the pattern from `orchestrator.py:249-265` translated to bash:
   ```bash
   marker=$(ls "${w}/.ll-session-"* 2>/dev/null | head -1)
   if [ -n "$marker" ]; then
       pid=$(basename "$marker" | sed 's/^\.ll-session-//')
       if kill -0 "$pid" 2>/dev/null; then
           echo "Skipping ${WORKTREE_NAME}: worker process ${pid} is alive"
           continue
       fi
   fi
   ```
2. **Update the dry-run loop** (`commands/cleanup-worktrees.md:87-93`): after extracting `BRANCH_NAME` (line 89), add the same probe and emit `[SKIP - live <pid>]` or `[REMOVE]` so users can see which would be preserved.
3. **Verify marker filename convention** matches `worktree_utils.py:96-99`: filename is `.ll-session-<pid>`, content is the PID string. The `split("-")[-1]` (Python) / `sed 's/^\.ll-session-//'` (bash) extractions both yield the PID correctly.
4. **Smoke test**: start `ll-parallel` in one terminal; run `/ll:cleanup-worktrees` in another. Confirm live worker directories are skipped. Kill the `ll-parallel` process and re-run; confirm the now-orphaned directories are removed.

## Acceptance Criteria

- Running `/ll:cleanup-worktrees` while `ll-parallel` is active does NOT remove live worker worktrees
- Dead or unowned `worker-*` directories are still removed as before
- Skipped live directories produce a log line identifying the PID
- No new Python changes required (shell-only change)

## Impact

- **Priority**: P3 - Minor enhancement; prevents data loss only when user manually runs cleanup during an active parallel run
- **Effort**: Small - Shell-only change in one command file; mirrors existing Python liveness pattern
- **Risk**: Low - Additive guard only; skipping directories is the safe default; no Python changes
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: `commands/cleanup-worktrees.md` run-mode and dry-run loops only
- **Out of scope**: `hooks/scripts/session-cleanup.sh` liveness hardening (follow-on candidate noted in Integration Map)
- **Out of scope**: Python `orchestrator.py` / `worktree_utils.py` — no changes needed; they already have the liveness check
- **Out of scope**: `ll-sprint` or `ll-loop` cleanup paths — separate cleanup mechanisms

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`

## Resolution

Added `.ll-session-<pid>` liveness probe to both the run-mode and dry-run loops in `commands/cleanup-worktrees.md`. Live worker directories are skipped with a log message identifying the PID; dead/unmarked directories are removed as before. Dry-run output now shows `[SKIP - live <pid>]` or `[REMOVE]` per directory.

## Session Log
- `/ll:manage-issue` - 2026-04-22T19:15:25Z - implementation complete
- `/ll:ready-issue` - 2026-04-22T19:14:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56ba5453-8299-4819-9517-bdad25dacf90.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6324f09c-71ad-425a-ad2e-a12eab8a9c3d.jsonl`
- `/ll:wire-issue` - 2026-04-22T19:11:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b0ed8ec-c60d-49ad-8b1c-2515cfc3651e.jsonl`
- `/ll:refine-issue` - 2026-04-22T19:06:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da246113-514f-44d1-a1e3-e9c81b927749.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
