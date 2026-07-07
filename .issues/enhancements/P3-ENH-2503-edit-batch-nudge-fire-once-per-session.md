---
id: ENH-2503
title: "Edit-batch nudge: fire at most once per session"
type: ENH
priority: P3
status: done
size: Small
captured_at: '2026-07-07T03:45:51+00:00'
completed_at: 2026-07-07T03:45:51+00:00
discovered_date: 2026-07-06
discovered_by: session-investigation
relates_to:
- FEAT-2470
- ENH-2499
labels:
- enhancement
- hooks
- token-cost
- edit-batch-nudge
decision_needed: false
---

# ENH-2503: Edit-batch nudge: fire at most once per session

## Summary

Convert the edit-batch nudge hook from "fire every N consecutive unbatched
edits" to "fire at most once per session". After the first nudge fires, a
sticky `nudged: bool` latch in `.ll/ll-edit-batch-state.json` suppresses every
subsequent nudge for the lifetime of the `session_id`; a new session re-arms
the hook. Behavior change is observable in the hook transcript: long
edit-heavy sessions previously saw 3–4+ redundant reminders; now they see one.

## Motivation

The hook (FEAT-2470 + ENH-2499) was designed to nudge the model when it falls
into a one-edit-per-turn cadence. In practice during a long
`/ll:manage-issue` refactor across 9 test files, the hook fired **multiple
times in a single session** even though the model hadn't changed its
edit-batching behavior — the first reminder didn't land, so 3 more unbatched
edits later it fired again, and again after that. Each fire injects ~80 tokens
of feedback into context for the remainder of the session; re-firing is pure
dead weight on a hook whose entire purpose is reducing token waste from
avoidable round-trips.

The first nudge (at the threshold of 3 consecutive unbatched edits) still has
attention weight — the model is mid-edit, the reminder reaches foreground
context, and it has the best chance of changing behavior. Subsequent nudges
are habituated away and add no value. Empirically, in the session that
surfaced this issue, the model continued single-editing after the first
nudge, so a 2nd/3rd/4th reminder would have changed nothing.

## Current Behavior

`_NUDGE_THRESHOLD = 3`. Each time `run >= 3` fires, `run` resets to 0 — so the
*next* 3 consecutive unbatched edits trigger another nudge. In a session with
12 consecutive unbatched edits, the hook fires 4 times. State file
`.ll/ll-edit-batch-state.json` records `{session_id, run, last_ts}` only.

## Expected Behavior

- The first time a run of `_NUDGE_THRESHOLD` consecutive unbatched edits is
  detected, the nudge fires as before (`exit_code=2` + feedback).
- Once fired, a sticky `nudged: true` flag is persisted to the state file.
  Every subsequent edit in the same `session_id` passes through silently with
  `exit_code=0`, regardless of the run counter or batch-window state.
- A new `session_id` resets both `run` and `nudged`, so the hook re-arms for
  the new session.
- The state schema becomes `{session_id, run, last_ts, nudged}`. `nudged` is
  always present (explicit `false` before first fire), not implicit — so a
  future code path can read it without a `state.get(..., default)` dance.

## Proposed Solution

### Code change

`scripts/little_loops/hooks/edit_batch_nudge.py`:

1. Add `nudged: bool` to the persisted state schema. Update the docstring's
   State paragraph to mention the new field and the once-per-session invariant.
2. After loading state, compute `same_session = state.get("session_id") ==
   session`. If `same_session and state.get("nudged")`, return
   `LLHookResult(exit_code=0)` immediately — no state update needed (the
   session is already in its "done nudging" terminal state).
3. When a nudge fires, persist `{"nudged": True}` alongside the existing
   fields. Otherwise, persist the prior `nudged` value (so an explicit
   `false` doesn't get lost when `run` resets after a MultiEdit / batched
   edit).

### Test additions

`scripts/tests/test_edit_batch_hook.py` (existing tests unaffected; new tests
pin down the new invariants):

- `test_nudge_only_fires_once_per_session` — fire the threshold once, then
  drive `4×_NUDGE_THRESHOLD` more unbatched edits through; assert none
  re-nudge.
- `test_nudge_only_fires_once_even_across_batched_resets` — MultiEdit + fast
  batched pair + long unbatched stretch after the first nudge; assert none
  of them re-arm the hook.
- `test_session_change_rearms_nudge` — fires in `s1`, switches to `s2`,
  confirms `s2` can nudge again.
- `test_state_records_nudged_flag` — reads state file post-fire, asserts
  `nudged is True`.
- `test_state_omits_nudged_until_first_fire` — reads state pre-fire, asserts
  `nudged is False` (explicit, not implicit).

Update `test_counter_resets_after_firing`'s comment to reflect the new latch
semantics (assertion unchanged).

## Acceptance Criteria

- `python -m pytest scripts/tests/test_edit_batch_hook.py -v` passes (16
  tests: 11 prior + 5 new).
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/
  test_hook_post_tool_use.py scripts/tests/test_hook_user_prompt_submit.py -v`
  passes (84 prior dispatch + post-tool-use tests; no regressions).
- Manual transcript observation: in a long session making 6+ consecutive
  unbatched edits, only one nudge fires.
- State file schema adds `nudged: bool`; pre-fire `nudged: false`, post-fire
  `nudged: true`.
- Behavior verified in the live session in which the issue was discovered:
  this session's `.ll/ll-edit-batch-state.json` was updated by the live hook
  during the implementation, and the change took effect on the same session.

## Files Touched

**Modified**:
- `scripts/little_loops/hooks/edit_batch_nudge.py` — added `nudged` latch
  (~12 lines), updated docstring.
- `scripts/tests/test_edit_batch_hook.py` — added 5 new tests (~95 lines),
  updated one comment.

## Dependencies

- `scripts/little_loops/hooks/edit_batch_nudge.py:_STATE_PATH =
  Path(".ll/ll-edit-batch-state.json")` — the only persistent state surface.
- `scripts/little_loops/hooks/edit_batch_nudge.py:_BATCH_WINDOW_SECONDS =
  3.0` — unchanged; the once-per-session latch composes cleanly with the
  existing time-gap heuristic.
- `scripts/little_loops/hooks/edit_batch_nudge.py:_NUDGE_THRESHOLD = 3` —
  unchanged; the latch fires at the same threshold as before, just once per
  session instead of every threshold edits.
- No new config keys, no schema changes, no downstream consumer changes.

## Impact

- **Priority**: P3 — small behavior tweak with no functional risk; addresses
  user-visible "nag" complaint about the hook's own firing cadence.
- **Effort**: Small — single-file code change + 5 new tests.
- **Risk**: Low — additive invariant on top of existing state machine; the
  latch is opt-out by exiting the session (no other escape hatch, by design).
- **Breaking Change**: No. Hook callers (Claude Code adapter at
  `hooks/adapters/claude-code/edit-batch-nudge.sh`) only care about exit code
  and stderr; the `exit_code=2` behavior on the first fire is preserved.

## Labels

`enhancement`, `hooks`, `token-cost`, `edit-batch-nudge`

## Status

**Done** | Created: 2026-07-06 | Completed: 2026-07-07 | Priority: P3

## Resolution

Implemented the once-per-session latch in
`scripts/little_loops/hooks/edit_batch_nudge.py`. Five new tests pin down the
new invariants in `scripts/tests/test_edit_batch_hook.py`. All 16 tests in
the file pass; the broader hook test suite (100 tests across
`test_edit_batch_hook.py`, `test_hook_intents.py`,
`test_hook_post_tool_use.py`, `test_hook_user_prompt_submit.py`) passes
without regression.

The 8 unrelated failures in `test_hooks_integration.py` (all `NameError:
name 'monkeypatch' is not defined`) are pre-existing: confirmed they reproduce
on clean tree (via `git stash`); caused by missing `monkeypatch` fixture
parameters in tests modified by the in-progress BUG-2501 conftest refactor.
Out of scope for this change.

User-visible effect: in long edit-heavy sessions, only one nudge fires (at
edit #3 of the unbatched run); subsequent edits pass through silently.
Habituation cost reduced; first-nudge attention weight preserved.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-07T03:46:22 - `3460793f-ad9f-4d19-a57b-76f4c58e0f32.jsonl`

- 2026-07-07T03:45:51+00:00 - Investigation → analysis → code change → test
  additions → verification (current session). Investigation triggered by user
  noting that the edit-batch reminder nudge hook fired more than once during
  a `/ll:manage-issue bug fix BUG-2501` run across 9 test files.