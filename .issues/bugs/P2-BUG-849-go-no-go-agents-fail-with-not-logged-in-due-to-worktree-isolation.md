---
discovered_date: 2026-03-20
discovered_by: user_report
---

# BUG-849: go-no-go agents fail with "Not logged in" due to worktree isolation

## Summary

`/ll:go-no-go` background agents consistently fail with "Not logged in · Please run /login" immediately after launch, even when the parent session is authenticated. The pro and con adversarial agents never complete their research.

## Location

- **File**: `skills/go-no-go/SKILL.md`
- **Line**: 143
- **Anchor**: Step 3b — adversarial agent launch instruction

## Current Behavior

Both background agents are launched with `isolation: "worktree"`. This causes Claude Code to spawn a new subprocess in a temporary git worktree. That subprocess boots cold with no inherited session context, immediately hitting the auth wall:

```
Not logged in · Please run /login
```

The agents exit without performing any research. The judge agent never receives input and the verdict is never produced.

## Root Cause

`isolation: "worktree"` in the `Agent` tool call spawns a fresh Claude Code subprocess rather than a lightweight in-process agent. The fresh subprocess cannot inherit the parent's authenticated session, so it fails on startup.

The judge agent (Step 3d) runs without `isolation: "worktree"` (foreground, no isolation) and works correctly — confirming the isolation parameter is the cause.

## Expected Behavior

Both adversarial agents should run in-process (sharing the parent session context), complete their codebase research, and return their arguments to the judge agent.

## Proposed Solution

Remove `isolation: "worktree"` from the Step 3b agent launch instruction. The pro and con agents are purely read-only (allowed tools: Read, Glob, Grep, Bash(find/ls/cat/git)) — they never write files, so worktree isolation provides no benefit.

## Impact

- **Severity**: High — skill is completely non-functional; every run fails
- **Effort**: Trivial (one-line fix)
- **Risk**: None

## Labels

`bug`, `priority-p2`

---

## Status
**Completed** | Created: 2026-03-20 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-03-20
- **Status**: Completed

### Changes Made
- `skills/go-no-go/SKILL.md:143`: Removed `isolation: "worktree"` from Step 3b agent launch instruction. Changed from:
  ```
  launch both agents concurrently using the `Agent` tool with `run_in_background: true` and `isolation: "worktree"`.
  ```
  to:
  ```
  launch both agents concurrently using the `Agent` tool with `run_in_background: true`.
  ```

### Verification
Run `/ll:go-no-go` against any open issue and confirm both adversarial agents complete their research without the login error.
