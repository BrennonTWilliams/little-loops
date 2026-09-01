---
id: ENH-3377
type: ENH
title: process-cwd fallback liveness check for marker-less and registry-less worktrees
priority: P2
status: open
parent: ENH-3374
depends_on:
- ENH-3376
unproven_mechanism: true
learning_tests_required:
- psutil
---

# ENH-3377: process-cwd fallback liveness check for marker-less and registry-less worktrees

## Summary

For worktrees with neither a live registry entry (ENH-3376)
nor a live in-tree marker, add a conservative fallback liveness check — a live
process whose cwd is inside the worktree path — before deleting it as
orphaned. When the check is unavailable (e.g. `psutil` not installed), skip
the worktree with a warning rather than deleting it.

## Parent Issue

Decomposed from ENH-3374: make worktree liveness marker resilient so active
worktrees cannot be classified orphaned. Covers Proposed Solution step 3 and
the third Phase-4 test bullet ("marker-less + registry-less worktree still
cleaned" — this issue changes that path to consult the fallback first, so the
regression test moves here). The parent flagged this exact mechanism
`unproven_mechanism: true` with `learning_tests_required: psutil` — no
`psutil` or `lsof` usage exists anywhere in the current worktree-liveness code
path, and no cwd-based liveness precedent exists in the codebase (the closest
prior art, `scripts/little_loops/cli/queue.py::_verify_owner_alive`, is
cmdline-identity based, not cwd based).

## Current Behavior

After ENH-3376 lands: a worktree with no live registry entry
and no live in-tree marker is deleted immediately by
`_cleanup_orphaned_worktrees()` — no further check is performed.

## Expected Behavior

Before deleting a worktree with neither a live registry entry nor a live
marker, check whether any live process has its cwd inside the worktree path.
If such a process exists, skip the worktree with a warning instead of
deleting it. If the check cannot be performed (e.g. `psutil` unavailable),
also skip with a warning rather than deleting — absence of a marker/registry
is never, by itself, treated as proof of orphanhood.

## Motivation

The registry (ENH-3376) covers worktrees created after this
feature ships. Worktrees whose registry entry was itself lost (e.g. process
crash during a non-atomic partial write, or a worktree created by
older/external tooling) still rely on marker-or-nothing. This fallback is a
last-resort safety net for that residual gap — lower priority than the
registry fix since it only matters when both prior signals are already
absent.

## Proposed Solution

1. **Spike first** (required — `unproven_mechanism: true`): prove a
   `psutil`-based (or `lsof`-based, if `psutil` proves unsuitable) mechanism
   for "does any live process have its cwd inside path X" works reliably
   across the platforms this codebase targets, before wiring it into
   `_cleanup_orphaned_worktrees()`. Record the proof per the Learning Test
   Registry conventions (see `/ll:explore-api`).

   Note: `psutil` is already a **required** dependency
   (`scripts/pyproject.toml:58`, moved from optional in FEAT-2930), so the
   "psutil unavailable" branch is defensive-only. The spike's real questions
   are:
   - **macOS path aliasing**: `psutil.Process.cwd()` returns
     `/private/tmp/...` where the worktree path may read `/tmp/...` — the
     prefix comparison must `Path.resolve()` both sides or live processes
     produce false negatives (i.e. deletions).
   - **`AccessDenied` decision rule**: on macOS, `cwd()` raises
     `AccessDenied` for many system/other-user processes as a matter of
     course. A literal "cannot positively exclude → skip" rule would block
     all cleanup forever. Rule to prove/adopt: per-process `AccessDenied`
     (and `NoSuchProcess`/zombie races) is ignored and the scan continues;
     only a wholesale scan failure (e.g. `process_iter` itself raising)
     triggers the skip-with-warning path.
   - **Cost**: `process_iter` + per-process `cwd()` on every cleanup pass —
     measure, and iterate once per pass (checking all candidate worktrees in
     one sweep), not once per worktree.
2. Add the fallback check to `_cleanup_orphaned_worktrees()`
   (`scripts/little_loops/parallel/orchestrator.py:317`), gated after the
   registry and marker checks from ENH-3376: for a worktree
   with neither a live registry entry nor a live marker, run the process-cwd
   check before deleting.
3. If the check raises or the required dependency is unavailable, skip the
   worktree with a warning (log entry), matching the "never delete when
   liveness cannot be positively excluded" principle — do not fall through to
   deletion on error.

### Tests

- A live process with cwd inside a marker-less, registry-less worktree ->
  worktree is skipped with a warning, not deleted.
- The check being unavailable (mock ImportError / mock the check raising) ->
  worktree is skipped with a warning, not deleted.
- A marker-less, registry-less worktree with no live process anywhere inside
  it -> still deleted (this is the BUG-579 regression test, moved from the
  parent's Phase-4 test list to reflect the new gating).

## Program Design

### Types

- None new — consumes `psutil.Process.cwd()` (existing third-party API).

### Signatures

- `_process_cwd_liveness_check(worktree_path: Path) -> bool` — iterates
  `psutil.process_iter()` once per cleanup pass, `Path.resolve()`s both sides
  before the prefix comparison, ignores per-process `AccessDenied`/
  `NoSuchProcess`, and returns `False` only on a wholesale scan failure
  (`process_iter` itself raising) or when `psutil` is unavailable

### Call Path

`ParallelOrchestrator.run` -> `_cleanup_orphaned_worktrees` -> (registry check,
marker check — ENH-3376) -> `_process_cwd_liveness_check` -> skip-with-warning
or delete

## Scope Boundaries

- The registry itself (write/remove/consult) is out of scope — that's
  ENH-3376, a hard dependency of this issue (this issue's fallback only fires
  when ENH-3376's checks find no live entry).
- `hooks/scripts/session-cleanup.sh` hardening is out of scope — bash has no
  `psutil` equivalent; that path is handled independently in ENH-3378.
- An `lsof`-based fallback is out of scope unless the spike (Proposed Solution
  step 1) finds `psutil` unsuitable.
- Liveness checking for worktrees outside `_cleanup_orphaned_worktrees()`'s
  existing candidate enumeration is out of scope.

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` (`_cleanup_orphaned_worktrees`)

## Dependent Files / Precedent

- `scripts/little_loops/cli/queue.py::_verify_owner_alive` and
  `scripts/tests/test_cli_queue_run.py:609-692` — closest existing shape
  (`patch("<module>.psutil.Process", ...)`) for mocking a `psutil`-based
  liveness check in tests, though it checks cmdline identity, not cwd.

## Impact

Closes the residual liveness gap for worktrees whose registry entry is itself
missing or lost, without weakening ENH-3376's registry-based
fix (which already closes the primary BUG-3373 mechanism on its own).

## Related Key Documentation

- `scripts/little_loops/parallel/orchestrator.py` (orphan detection)
- `scripts/little_loops/cli/queue.py` (`_verify_owner_alive`, closest psutil precedent)

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-01T18:11:45 - `a022c67c-3828-4e2e-96d1-3bcdf7adfc60.jsonl`
- `/ll:issue-size-review` - 2026-09-01T15:20:22 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
