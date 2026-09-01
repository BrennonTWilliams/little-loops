---
id: BUG-3373
type: BUG
title: shared epic worktree deleted mid-run by session-cleanup.sh Stop hook race
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T04:10:53Z'
relates_to:
- ENH-3374
- BUG-3375
- ENH-3376
- ENH-3378
depends_on:
- ENH-3376
- ENH-3378
program_design_not_applicable: true
confidence_score: 75
outcome_confidence: 46
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 0
score_change_surface: 10
---

# BUG-3373: shared epic worktree deleted mid-run by session-cleanup.sh Stop hook race

## Summary

During `ll-loop run sprint-refine-and-implement EPIC-1463`, the shared epic
worktree (`.worktrees/20260831-221633-subloop-epic-epic-1463-...`) was
deleted out from under a live `/ll:refine-issue FEAT-2122 --auto` session,
mid-run. The deleter has not been identified. An earlier version of this
issue attributed the deletion to `_execute_sub_loop`'s `finally`-block
`detach_worktree()` in `scripts/little_loops/fsm/executor.py`; the run's own
`events.jsonl` disproves that attribution (see Root Cause), so this issue is
now an investigation: identify the actual deleter and fix it at the source.

Downstream hardening has been split off:
- ENH-3374 — make the `.ll-session-<pid>` liveness marker resilient so an
  active sub-loop worktree can never be classified orphaned.
- BUG-3375 — autodev cascades `[Errno 2]` into a clean terminal exit and
  silently abandons its queue when its worktree vanishes.

## Current Behavior

Something removed the shared epic worktree cleanly (`git worktree list` no
longer showed it — a `git worktree remove`-style removal, not a stray
`rm -rf`) between `03:54:58Z` and `03:57:14Z` on 2026-09-01, while:

- the owning `ll-loop run` process was alive (it kept executing states
  until `03:57:15Z`), and
- a dispatched `/ll:refine-issue FEAT-2122 --auto` subprocess was actively
  using the worktree as its cwd.

No component in the run's own call path performed the deletion in that
window (see Root Cause), so the deleter is external to the
`sprint-refine-and-implement` lifecycle: another session, a cleanup pass, or
a tool invoked from inside one of the dispatched Claude sessions.

## Expected Behavior

Nothing deletes a worktree that is (a) registered to a live `ll-loop`/
`ll-parallel` process or (b) the cwd of a live dispatched subprocess. Any
cleanup path that can remove `.worktrees/*` must positively verify
non-liveness first, and the deleter responsible for this incident is
identified and fixed (or, if it was a manual/external action, documented as
out of scope and this issue closed with ENH-3374/BUG-3375 carrying the
hardening).

## Motivation

An active-worktree deletion silently truncates a batch run: in the observed
incident it killed the FEAT-2122 refine mid-flight and left ENH-1722
undequeued, with the run reporting `verdict=incomplete-abandoned` and no
error pointing at the real cause. Until the deleter is identified, every
long `auto-refine-and-implement` / `sprint-refine-and-implement` run is
exposed to a recurrence, and any fix aimed at the wrong component (as the
original version of this issue was) leaves the actual hole open.

## Proposed Solution

Root cause is now confirmed (see Root Cause) — no further investigation
needed. The fix is already fully scoped as descendants of ENH-3374
(decomposed 2026-09-01, see its Resolution):

- **ENH-3376** — introduces a registry-based worktree liveness record that
  survives in-tree marker deletion. Addresses the underlying reason the
  `.ll-session-<pid>` marker was missing/stale in this incident.
- **ENH-3378** — hardens `hooks/scripts/session-cleanup.sh::cleanup()` (this
  issue's confirmed deleter) to consult that registry before its
  unconditional zero-marker `git worktree remove --force`. This is the
  direct fix for the mechanism identified below.
- ENH-3377 (process-cwd fallback) is not required to close this specific
  incident's mechanism — ENH-3376 + ENH-3378 alone close the registry-consult
  gap this deletion exploited.

BUG-3373 owns no separate code change: its remaining scope was the
diagnosis above (`program_design_not_applicable: true`, `depends_on:
[ENH-3376, ENH-3378]`). Close this issue once those land, or close it now
with the fix tracked entirely on those issues.

## Impact

Silent batch truncation for epic/sprint automation runs: 1 of 3 issues
completed, 1 killed mid-refine, 1 abandoned untouched
(`verdict=incomplete-abandoned, closed=1, inflight_unresolved=1,
abandoned=1, parked_rate=0.6667`). No data loss in the observed instance
(the refine session had not yet written changes), but only by luck of
timing — the same deletion during a manage-issue implementation phase would
destroy uncommitted work.

## Steps to Reproduce

Not deterministically reproducible until the deleter is identified.
Observed during `ll-loop run sprint-refine-and-implement EPIC-1463`:

- Run dir: `.loops/runs/sprint-refine-and-implement-20260831T221623/`
- History: `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`

Verified timeline (all timestamps from `events.jsonl`, UTC):

1. `03:16:34.994` — `sub_loop_worktree_attached` (auto-refine-and-implement
   attaches the shared epic worktree for the autodev sub-loop; the only
   attach event in the run).
2. `03:54:47` — FEAT-2123 completes inside the worktree (`ll-auto` summary,
   commit `46ef469e0` on the epic branch).
3. `03:54:58.712` — `refine-to-ready-issue` sub-loop starts
   `/ll:refine-issue FEAT-2122 --auto` in the same worktree.
4. **`03:54:58`–`03:57:14` — the worktree is deleted mid-action.** The
   refine session reports "the working directory vanished... cleanly
   removed (not just orphaned)... `git worktree list` no longer shows it"
   and exits 0 at `03:57:14.917`.
5. `03:57:14.937`–`03:57:15.36` — `refine-to-ready-issue` then autodev
   states (`skip_inflight`, `dequeue_next`, `finalize_done`) cascade
   `[Errno 2] No such file or directory` on the missing cwd; autodev
   reaches `loop_complete` at `03:57:15.369` (see BUG-3375).
6. `03:57:15.371` — `sub_loop_worktree_detached`: `_execute_sub_loop`'s
   `finally` block runs its normal teardown against the already-deleted
   path (a no-op removal), then the run finalizes as
   `incomplete-abandoned` with ENH-1722 never dequeued.

## Root Cause

**Confirmed.** The deleter is `hooks/scripts/session-cleanup.sh::cleanup()`
— wired as a Claude Code `Stop` hook (`hooks/hooks.json:225,235`) — fired by
an unrelated, ordinary interactive session that happened to end a turn
inside the deletion window.

Evidence from `.ll/history.db`'s `hook_events` table (Stop-hook telemetry,
ENH-2506), for `03:52:00`–`03:58:00Z` on 2026-09-01:

| ts (UTC) | session_id | script | notes |
|---|---|---|---|
| `03:54:47Z` | `f311a645-…` | `session-cleanup.sh` | FEAT-2123's own session ending. No commands from this session appear under the project's default cwd via `ll-messages` (which resolves sessions by cwd) — consistent with it running with cwd = the shared epic worktree itself. `cleanup()` self-excludes when `git-dir != git-common-dir` (script lines 33-37), so this firing almost certainly did **not** touch worktree cleanup. |
| **`03:56:11Z`** | **`54b7abda-…`** | **`session-cleanup.sh`** | **Squarely inside the `03:54:58`–`03:57:14` deletion window.** cwd = true project root (confirmed via `ll-messages`). This session had no connection to EPIC-1463 — it was an ordinary session capturing/committing **FEAT-3372**, whose commands and commit bracket this timestamp. Its Stop hook firing is the only other worktree-scanning event in the window. |

`cleanup()` runs on **every turn-end** of any project-root session (per its
own comment, it "fires at every turn end," not just session-end). On each
firing it globs `git worktree list` for **all** worktrees under
`parallel.worktree_base` and, for any whose `.ll-session-<pid>` marker is
missing or names a dead pid, runs `git worktree remove --force`
unconditionally (script lines 42-54) — with no check for a live subprocess
using the worktree as its cwd, no dry-run, and no logging of what was
removed. This is a third, independent reimplementation of the liveness
check that ENH-3374's descendants (ENH-3376, ENH-3377, ENH-3378) already
identified as fragile; ENH-3378 specifically scopes hardening this exact
script.

This resolves the "unidentified external actor" framing: the deleter is not
external, malicious, or a deliberate cleanup invocation — it is this
project's own Stop-hook automation, triggered incidentally by an unrelated
session that finished an ordinary turn during the ~2-minute window in which
the shared epic worktree's `.ll-session-<pid>` marker was apparently
missing or stale. (The mechanism for *why* the marker was missing —most
likely a `git clean -fdx` run by FEAT-2123 inside the worktree minutes
earlier — remains ENH-3374/ENH-3376's scope, not re-litigated here.)

This also explains why the original transcript-grep leads found nothing:
the deleting command never appears as a Bash tool call in any session's
transcript — it runs inside a harness-triggered hook script the model never
sees or invokes directly, so no amount of grepping session transcripts for
`worktree remove` / `cleanup-orphans` could have surfaced it.

Ruled out: `FSMExecutor._execute_sub_loop`'s `finally`-block
`detach_worktree()` (`scripts/little_loops/fsm/executor.py:1125-1127`),
which the original version of this issue blamed. That block cannot run
before `child_executor.run()` returns, and `events.jsonl` shows the child
(autodev) executing states until `03:57:15.369` — up to two minutes *after*
the deletion and ~800ms after the refine subprocess reported the worktree
gone. The `sub_loop_worktree_detached` event at `03:57:15.371` is downstream
fallout (teardown of an already-deleted tree), not the cause. Gating that
teardown on autodev's `autodev-inflight` sentinel (the originally proposed
fix) would not have prevented this incident, and could not work as designed
anyway: every site that clears the sentinel is an autodev FSM state, so
nothing clears it after autodev's FSM has returned.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-parallel --cleanup-orphans`
- `scripts/little_loops/worktree_utils.py` — session-marker write (BUG-579)
- `hooks/scripts/session-cleanup.sh` — confirmed deleter (`cleanup()`,
  lines 42-54); wired as a Claude Code `Stop` hook at `hooks/hooks.json:225,235`
- `.ll/history.db` `hook_events` table (ENH-2506 telemetry) — forensic
  evidence for the confirmed root cause above

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-01_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 46/100 → LOW

### Concerns
- Root cause is explicitly unidentified ("Unknown — under investigation"); three ranked candidate mechanisms are proposed but none confirmed (Criterion 3: 10/20).
- Ambiguity is high: which of the three leads is the actual deleter is unresolved, and the fix site depends entirely on that finding (Criterion C: 0/25).

### Gaps to Address
- `## Program Design` section is missing entirely (not present, not just non-specific) — `ll-issues check-design` fails. Populate it once the deleter is identified (run `/ll:refine-issue` or `/ll:reconcile-issue`), or set `program_design_not_applicable: true` if this issue is intentionally scoped as investigation-only ahead of a follow-up fix issue.

### Outcome Risk Factors
- Change surface is not yet bounded — the actual fix site is unknown until one of the three leads is confirmed, and cleanup logic spans multiple call paths (`ll-parallel --cleanup-orphans`, `/ll:cleanup-worktrees`, dispatched-session tooling) (Criterion D: 10/25).
- Multiple competing root-cause hypotheses remain open; effort could be spent investigating a lead that turns out to be a dead end (Criterion C: 0/25).

## Status

**Open** | Created: 2026-09-01 | Priority: P2

## Session Log
- Root cause confirmed 2026-09-01 via `.ll/history.db` `hook_events` forensic
  query: deleter is `hooks/scripts/session-cleanup.sh`'s Stop hook, fired by
  session `54b7abda-af7a-4b45-bfa4-e6f3cd9335a3` (unrelated FEAT-3372
  capture) at `03:56:11Z`. Fix delegated to ENH-3376/ENH-3378 (already
  scoped as ENH-3374 descendants); `program_design_not_applicable: true`
  set since this issue owns no separate code change.
- `/ll:confidence-check` - 2026-09-01T17:01:32 - `98f877f4-d015-4e8b-adfe-7dbdd68338b7.jsonl`
- Rewritten 2026-09-01 after events.jsonl replay disproved the original root cause; hardening split to ENH-3374 / BUG-3375.
- `/ll:confidence-check` - 2026-09-01T05:03:18 - `cb6b213f-3d5d-4d43-865a-115ce8e42c87.jsonl` (against superseded content)
- `/ll:verify-issues` - 2026-09-01T05:00:57 - `59d87293-a76b-4fa5-956d-fafc8b453dfc.jsonl` (against superseded content)
- `/ll:wire-issue` - 2026-09-01T04:58:50 - `f09f6f25-9595-48be-95b3-0d16ac1ab171.jsonl` (against superseded content)
- `/ll:refine-issue` - 2026-09-01T04:50:45 - `b9117cb4-7742-4681-b184-d660daf97ebc.jsonl` (against superseded content)
- `/ll:format-issue` - 2026-09-01T04:17:10 - `6ed91f4a-37bf-454d-8c78-490c7b5f663f.jsonl`
- `/ll:capture-issue` - 2026-09-01T04:11:01 - `619baadf-ddf4-410d-b209-baf9424402fe.jsonl`
