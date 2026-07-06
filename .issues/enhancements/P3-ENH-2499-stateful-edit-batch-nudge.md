---
id: ENH-2499
title: Make the edit-batching nudge stateful (fire only after a run of unbatched single edits)
priority: P3
type: ENH
status: done
discovered_date: 2026-07-05
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 90
completed_at: 2026-07-06T04:22:16Z
parent: EPIC-2456
relates_to: [FEAT-2470, ENH-2471]
labels: [token-cost, hooks, tier-0]
---

# ENH-2499: Make the edit-batching nudge stateful (fire only after a run of unbatched single edits)

## Summary

Rewrote the `edit_batch_nudge` PostToolUse hook (FEAT-2470, EPIC-2456 token-cost
quick-win) from an unconditional per-edit nudge into a stateful one that fires
only after a run of consecutive *unbatched* single edits reaches a threshold
(default 3), then resets.

## Current Behavior

`edit_batch_nudge.handle` returned `exit_code=2` and injected a ~60-token
reminder on **every** `Edit`/`Write`/`MultiEdit` call, unconditionally. This was
self-defeating for a token-cost hook (it spent tokens on every edit) and it fired
precisely when its own advice said "skip" — during unavoidable sequential
dependent edits to the same file — as well as false-firing on the first edit of a
turn, when there is nothing yet to batch.

## Motivation

The nudge exists to reduce avoidable token cost from one-edit-per-turn round
trips. Firing on every edit both burns tokens and trains the model to ignore the
reminder (it appears even when batching is impossible). The hook should fire only
when the model is actually failing to batch — a *run* of single edits — and stay
silent during batched work and dependent-edit sequences.

## Key Constraint

`PostToolUse` fires once per tool call with no turn id, so two edits batched in
one assistant turn are indistinguishable from two edits across turns **except by
the wall-clock gap** between hook fires. Batched edits (parallel `Edit` calls, or
several `tool_use` blocks in one message) execute sub-second apart; a genuine
one-edit-per-turn cadence is separated by full model-generation time (seconds+).
The dispatcher (`hooks/__init__.py`) does not populate `event.session_id` or
`event.timestamp`, so the handler reads `session_id` from `event.payload` and the
clock via `time.time()`.

## Expected Behavior

- A per-session counter is kept in `.ll/ll-edit-batch-state.json` as a single
  record `{session_id, run, last_ts}`; a changed `session_id` resets the run.
- Non-edit tools pass through (exit 0) and never touch state.
- `MultiEdit` is inherently batched → resets the run, never nudges.
- `Edit`/`Write`: if the fire lands within `_BATCH_WINDOW_SECONDS` (3s) of the
  previous edit it is treated as batched → run reset, no nudge; otherwise the
  unbatched run increments. On reaching `_NUDGE_THRESHOLD` (3) it nudges once
  (exit 2 + reminder) and resets, so it fires every Nth unbatched edit, not
  continuously.
- All state I/O is best-effort (reuses `atomic_write_json`/`acquire_lock` from
  `file_utils`) and degrades to a silent pass-through (exit 0) on any failure —
  the hook never raises and never reverts to spamming.

## Files Changed

- `scripts/little_loops/hooks/edit_batch_nudge.py` — stateful `handle()`, `_now()`
  clock wrapper, state constants/helpers, updated module docstring.
- `scripts/tests/test_edit_batch_hook.py` — rewritten for stateful behavior
  (threshold firing, reset-after-fire, batched-never-nudges, MultiEdit reset,
  session-change reset, write-failure pass-through).
- `scripts/tests/test_hook_intents.py` — updated CLI-dispatch test (single Edit
  no longer nudges; seed the counter to prove the nudge path) plus a new
  silent-single-edit case.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — summary-table row and section describe
  the stateful, time-gap behavior.

## Acceptance Criteria

- [x] A single `Edit` no longer nudges; the 3rd consecutive unbatched single edit
      does (verified via unit tests and a CLI smoke test).
- [x] Batched edits (within the window) and `MultiEdit` never nudge.
- [x] Counter resets after firing and on session change.
- [x] State-write failure degrades to exit 0 without raising.
- [x] `test_edit_batch_hook.py` (11) and the edit-batch dispatch tests pass;
      ruff check, ruff format --check, and mypy are clean.

## Impact

Eliminates per-edit nudge spam on a token-cost hook. The reminder now fires at
most once per run of unbatched single edits (default every 3rd), staying silent
during batched work and unavoidable sequential dependent edits — so it costs
tokens only when it has actionable signal, and the model stops learning to
ignore it.

## Scope Boundaries

- No new `ll-config.json` keys; the window/threshold are in-code constants
  (`_BATCH_WINDOW_SECONDS`, `_NUDGE_THRESHOLD`) that a follow-up can surface to
  config if desired.
- No changes to the hook wiring (`hooks/hooks.json`, adapters) — the matcher and
  exit-code contract are unchanged; only the handler's firing logic changed.
- The 4 pre-existing `test_ll_logs.py::TestEvalExport` failures are out of scope
  (unrelated, environmental).

## Status

Done — implemented, tested, and documented this session
(2026-07-06). `test_edit_batch_hook.py` (11) and the edit-batch dispatch tests
pass; ruff/format/mypy clean.

## Notes

Full suite otherwise green; 4 pre-existing `test_ll_logs.py::TestEvalExport`
failures are unrelated (environmental "No session project folder found" — they
fail identically with this change stashed).


## Session Log
- `hook:posttooluse-status-done` - 2026-07-06T04:22:50 - `24d52920-f9e2-42c9-8a94-41c54da2192d.jsonl`
