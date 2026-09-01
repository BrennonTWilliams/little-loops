---
id: ENH-3378
type: ENH
title: harden session-cleanup.sh to consult the liveness registry before deleting
priority: P2
status: open
parent: ENH-3374
depends_on:
- ENH-3376
---

# ENH-3378: harden session-cleanup.sh to consult the liveness registry before deleting

## Summary

`hooks/scripts/session-cleanup.sh` (`cleanup()`, wired as a Claude Code Stop
hook) is a third, independent reimplementation of worktree liveness checking.
Its zero-marker path is stricter than the Python orchestrator's: it falls
straight through to an unconditional `git worktree remove --force` with no
registry/marker cross-check, no dry-run, and no logging gate. Once
ENH-3376 introduces an out-of-tree liveness registry, this
script must consult it before deleting, or it remains an unfixed instance of
the same BUG-3373 failure mode.

## Parent Issue

Decomposed from ENH-3374: make worktree liveness marker resilient so active
worktrees cannot be classified orphaned. Covers the parent's Wiring Phase
items "harden `hooks/scripts/session-cleanup.sh`'s `cleanup()`" and "rewrite
`test_session_cleanup_removes_worktree_with_no_marker`", plus the
`docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" doc update (and its
`ll-adapt` mirrors) since that doc describes this script's behavior
specifically. Split from ENH-3376 because it is a separate
language/tool (bash vs. Python) with its own independent test suite
(`test_hooks_integration.py`), and from ENH-3377 because it
only needs the registry, not the process-cwd fallback.

## Current Behavior

`hooks/scripts/session-cleanup.sh::cleanup()` (lines 44-52): if
`.ll-session-*` is present and the pid is alive, skip; otherwise (dead pid, or
no marker found at all) fall through unconditionally to
`git worktree remove --force "$w"` (line 52), with `cleanup || true` (line 61)
ensuring the hook never fails — but also never surfaces this as a warning.

## Expected Behavior

Before the unconditional `git worktree remove --force` on the no-live-marker
path (which covers both "no marker" and "marker present, pid dead"),
`cleanup()` reads the same out-of-tree registry entry that ENH-3376
introduces under `<worktree_base>/.registry/` (pid + run id; exact file
format decided in ENH-3376 with this bash consumer in mind). If the registry
entry exists and its pid is alive, skip the worktree instead of deleting it;
if it exists but cannot be parsed, also skip. Preserve the "must never
fail" invariant (`cleanup() || true`) — a registry read error must not raise
out of the hook.

## Motivation

A registry-only fix scoped to `_cleanup_orphaned_worktrees()` in
`orchestrator.py` leaves this second, independently-triggered deletion path
(fired on every Claude Code session Stop event, not just `ll-parallel
--cleanup-orphans`) exposed to the identical failure mode. Any worktree this
hook considers "marker-less" — including one whose registry entry says it's
still live — is deleted with no cross-check today.

## Proposed Solution

1. In `hooks/scripts/session-cleanup.sh::cleanup()`, before the fallthrough at
   line 52, add a registry read for the worktree's entry under
   `<worktree_base>/.registry/`, extract the pid, and `kill -0 "$PID"` it —
   mirroring the existing marker-check pattern (lines 44-51). Placing the
   check before line 52 means it covers **both** fallthrough paths: no marker
   found at all, **and** marker present but its pid dead (the parent flagged
   the dead-pid path UNSPECIFIED — it is explicitly in scope here).
2. Registry parsing follows the format ENH-3376 lands, which is being chosen
   for bash readability (pid encoded in the entry filename, or plain-text
   `pid` on line 1 — see ENH-3376 Proposed Solution step 1). The existing
   "jq-optional" pattern (`command -v jq`, line 24) is **not** sufficient on
   its own: it only substitutes a default config value and cannot extract a
   field from JSON. If ENH-3376 nonetheless lands JSON content, add a
   grep/sed extraction fallback for the no-jq case.
3. If the registry entry's pid is alive, skip (log + `continue`), matching the
   marker-present-and-alive behavior at lines 44-51. If a registry entry
   exists but cannot be parsed (no jq and no working fallback, corrupt file),
   **skip the worktree** — per the "never delete when liveness cannot be
   positively excluded" principle — rather than falling through to deletion.
   Only a genuinely absent registry entry falls through. All of this must
   preserve the "must never fail" invariant (`cleanup || true`).
4. Rewrite `test_session_cleanup_removes_worktree_with_no_marker`
   (`scripts/tests/test_hooks_integration.py:3261`) — it currently asserts the
   unsafe no-marker-means-delete behavior as *correct*; it must instead assert
   that a worktree with a live registry entry (but no marker) is skipped, and
   that a worktree with neither is still deleted (preserving the original
   BUG-579 regression coverage for the genuinely-orphaned case). Add a
   sibling test for the dead-pid-marker path: marker present with a dead pid
   but a live registry entry → skipped, not deleted.
5. Optional (cheap while in the file): add an `_is_ll_worktree()`-equivalent
   name filter to the deletion loop. Today the script reaps anything under
   `<worktree_base>/` that `git worktree list` reports, including shapes the
   Python orphan path deliberately refuses to touch (e.g. `epic-refresh-*`
   worktrees, which do not match `_is_ll_worktree()` in
   `worktree_utils.py:419-430`). If skipped, that asymmetry stays open —
   note it in the doc update either way.

### Documentation

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" — update the
  liveness semantics prose ("skipping any worktree owned by a live parallel
  worker") to mention the registry check; confirm during implementation
  whether `automation.worktree_base` (`Config.get_worktree_base()`) consumers
  (ll-auto/FSM sub-loop worktrees) also need registry consultation here.
- `.qwen/commands/ll/cleanup-worktrees.md`,
  `.gemini/commands/cleanup-worktrees.toml` — update if
  `commands/cleanup-worktrees.md`'s liveness prose changes as part of this
  work (these mirror it verbatim with no drift test, per ENH-2968).

## Files to Modify

- `hooks/scripts/session-cleanup.sh`
- `scripts/tests/test_hooks_integration.py` (`TestSessionCleanupWorktrees::test_session_cleanup_removes_worktree_with_no_marker`)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md`

## Impact

Closes the second, hook-triggered instance of the BUG-3373 misclassification
mechanism, so a dispatched Claude Code session's own Stop hook cannot delete
its sibling worktrees out from under still-running work.

## Related Key Documentation

- `hooks/hooks.json:225,235` (Stop hook wiring for `session-cleanup.sh`)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup"

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-01T15:20:23 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
