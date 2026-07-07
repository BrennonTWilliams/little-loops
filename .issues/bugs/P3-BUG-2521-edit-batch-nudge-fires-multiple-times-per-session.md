---
id: BUG-2521
title: "edit-batch-nudge hook fires more than once per session despite \"at most once\" contract"
type: BUG
priority: P3
status: open
captured_at: '2026-07-07T16:44:51Z'
discovered_date: 2026-07-07
discovered_by: capture-issue
labels:
- hooks
- edit-batch-nudge
- regression
- post-tool-use
---

# BUG-2521: edit-batch-nudge hook fires more than once per session despite "at most once" contract

## Summary

The `edit_batch_nudge` PostToolUse hook (`scripts/little_loops/hooks/edit_batch_nudge.py`)
fires its reminder text **more than once per session** despite the explicit contract
that it should fire **at most once per session** via a sticky `nudged` latch in
`.ll/ll-edit-batch-state.json`. Observed twice during a single ENH-2518 review session
(2026-07-07). The state file after the firings shows `nudged: false, run: 1` —
meaning the latch either was never persisted, was silently lost on write, or was
cleared by a session-id mismatch between hook invocations.

## Current Behavior

After 3 consecutive unbatched `Edit` tool calls, the hook correctly fires once
(`exit_code=2`, feedback injected into model context). On the next unbatched
Edit in the **same session**, the hook fires again — violating the documented
once-per-session contract. State file inspection shows the `nudged` latch is
NOT set after the first fire.

## Expected Behavior

After the first nudge fires in a session, every subsequent `Edit`/`Write`/`MultiEdit`
in that same session must exit 0 (no feedback) regardless of timing, run counter, or
how many unbatched edits accumulate. The latch must persist reliably across the
session lifetime, and a session-id change must be the only thing that re-arms the
hook.

## Motivation

The hook exists to nudge the model into batching independent edits — a token-cost
optimization (the FEAT-2470 wozcode P1 work). The "at most once per session" cap
exists because:

1. A reminder the model already saw once is unlikely to land harder on repetition;
   re-injecting it just adds tokens without changing behavior (per the hook
   docstring `edit_batch_nudge.py:17`).
2. Each fire injects ~50 tokens of reminder text into the model's context.

A user-visible double-fire is therefore a **silent budget leak** — exactly the kind
of waste the hook is supposed to prevent in the first place. It's also a contract
violation that erodes trust in the hook's other guarantees (threshold, batch-window
detection).

## Steps to Reproduce

1. Run any Claude Code session in this repo (`pip install -e "./scripts[dev]"`).
2. Make 3 consecutive `Edit` tool calls on the same file (one per assistant turn,
   no parallelism) — wait long enough between each that the
   `_BATCH_WINDOW_SECONDS` (3.0s) gap trips. The first nudge fires correctly.
3. Make 1 more `Edit` tool call (long-gap, unbatched).
4. **Observe**: the nudge fires AGAIN (visible as a `<system-reminder>` from
   `edit-batch-nudge.sh`).
5. Inspect `.ll/ll-edit-batch-state.json`:
   ```json
   {"session_id": "<id>", "run": 1, "last_ts": ..., "nudged": false}
   ```
   The `nudged: false` is the smoking gun — the latch either didn't persist,
   was overwritten, or was reset by a session-id change.

A reproducible reproduction script is provided in the **Implementation Steps**
section.

## Root Cause

Three candidates, in order of suspicion. **All three need investigation.**

### Candidate 1: `session_id` payload varied between fires

The docstring at `edit_batch_nudge.py:30-31` says:
> "a changed `session_id` resets the run *and* clears `nudged`."

If Claude Code's PostToolUse payload passed different `session_id` values to
different `Edit` hook invocations within the same conversation (e.g., due to a
harness quirk, sub-agent invocation, or payload-format variance), the latch
would be cleared on every fire. Need to log `event.payload.get("session_id")`
across consecutive fires to confirm/deny.

### Candidate 2: `_persist_state` silently failed

The persistence path at `edit_batch_nudge.py:95-105` has three layers of
`except: pass`:

```python
def _persist_state(state: dict[str, Any]) -> None:
    lock = _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".lock")
    try:
        with acquire_lock(lock, timeout=3.0):
            atomic_write_json(_STATE_PATH, state)
    except TimeoutError:
        with contextlib.suppress(OSError, ValueError):
            atomic_write_json(_STATE_PATH, state)  # best-effort fallback
    except (OSError, ValueError):
        pass
```

If `acquire_lock` timed out (lock contention from a parallel write) or
`atomic_write_json` raised (disk full, permission denied, NaN/Infinity in
serialized payload), the `nudged: true` write would be silently swallowed.
**No test asserts the post-nudge state was actually persisted** —
`test_dispatch_edit_batch_nudge_happy_path` (at
`scripts/tests/test_hook_intents.py:380-407`) only checks `returncode=2` and
that "batch" appears in stderr, not that the state file was updated.

### Candidate 3: Test gap masks either of the above

The Python-direct tests at `scripts/tests/test_edit_batch_hook.py` (including
`test_nudge_only_fires_once_per_session` at line 140-156) **do** assert
once-per-session behavior, but they use:
- `monkeypatch.chdir(tmp_path)` — isolated cwd → isolated state file
- A monkeypatched `_now` clock — fully deterministic timing

These tests cannot reproduce whatever race or persistence failure occurred in
production, because production shares the real `.ll/` directory across hook
fires and uses wall-clock time.

## Proposed Solution

Three layered defenses — each addresses one of the candidates above. All three
are worth landing, since the root cause isn't isolated:

### Fix 1: Add a regression test that asserts post-nudge state

In `scripts/tests/test_edit_batch_hook.py`, add a new test class `TestLatched`
that:
1. Drives 3 unbatched `Edit` events through `handle()`.
2. Reads `.ll/ll-edit-batch-state.json` directly.
3. Asserts `state["nudged"] is True` and `state["run"] == 0`.
4. Drives 4 more unbatched `Edit` events.
5. Asserts every one returns `exit_code=0` (no re-nudge).

This catches **Candidate 2** (silent persistence failure) and would have caught
the bug at PR time. Place it alongside `test_nudge_only_fires_once_per_session`.

### Fix 2: Log session_id and persistence status on each fire

Modify `handle()` to log (via `logging.warning` or stderr-on-debug) when:
- `_persist_state` returns without raising but the subsequent state file read
  doesn't match the just-written state (covers Candidate 2 post-mortem)
- `event.payload.get("session_id")` is empty/`None` (covers Candidate 1)

Both log lines should be no-ops in production (stderr-only, gated on
`LL_DEBUG` or similar) so they don't add token cost.

### Fix 3: Make the latch non-resettable in-process

Add a module-level `_latched_in_this_process: set[str]` (session_id → bool)
alongside the on-disk latch. The in-process check fires first; if the session
has nudged in *this* Python process, never re-nudge regardless of disk state.
This catches Candidate 1 (session_id churn within a process) and Candidate 2
(persistence failure) without paying for a disk read on every Edit.

**Trade-off**: the in-process latch is per-process, not per-session, so it
over-suppresses if the same Python process hosts multiple sessions. That's the
correct trade for a token-cost hook — false negatives (over-suppress) cost zero
tokens, false positives (re-nudge) cost ~50 tokens each.

## Error Messages

None — the bug is silent (extra context injection, no exit-code change visible
to the user).

## Environment

- **Repo**: `brentech/little-loops` (this project)
- **Host CLI**: Claude Code (claude-code adapter at
  `hooks/adapters/claude-code/edit-batch-nudge.sh`)
- **OS**: macOS Darwin 25.5.0
- **First observed**: 2026-07-07, during ENH-2518 `/ll:ready-issue` review
- **Reproducible**: yes — observed twice in one session; production state
  file confirms latch not set

## Frequency

Rare (only fires after 3+ unbatched edits), but every long editing session
hits it eventually. With ~10-20 unbatched edits per session typical, probability
of at least one double-fire approaches 100% over time.

## Location

- **Primary**: `scripts/little_loops/hooks/edit_batch_nudge.py:108-150`
  (`handle()` — the latch logic and persistence call)
- **Persistence**: `scripts/little_loops/hooks/edit_batch_nudge.py:95-105`
  (`_persist_state` — silent exception swallowing)
- **Tests**: `scripts/tests/test_edit_batch_hook.py:140-156`
  (existing once-per-session test) and `scripts/tests/test_hook_intents.py:380-407`
  (dispatch test that lacks post-state assertion)
- **State file**: `.ll/ll-edit-batch-state.json` (cwd-relative; per-project)

## Proposed Fix

See **Proposed Solution** above. Summary: add a post-state assertion test, log
diagnostics on suspect fires, and add an in-process latch that survives disk
or session-id churn.

## Implementation Steps

1. **Reproduce the bug in a controlled test.** Add
   `test_dispatch_edit_batch_nudge_persists_latch` to
   `scripts/tests/test_hook_intents.py` after the happy-path test (line 380).
   The test should:
   - Seed `.ll/ll-edit-batch-state.json` with `run: 2, last_ts: 0`
   - Run one Edit via the subprocess dispatcher
   - Assert the state file on disk has `nudged: true` after the call
   - If this test fails: confirms Candidate 2 (silent persist failure)
   - If this test passes: candidates 1 or 3 are more likely
2. **Instrument the hook** with optional debug logging of `session_id`,
   `_persist_state` outcome, and the post-write state-file readback. Gate on
   `LL_DEBUG=1` so it stays silent in production.
3. **Capture a real session trace.** Run a Claude Code session that triggers
   a double-fire; dump the payload `session_id` for every Edit-hook invocation
   to determine whether Candidate 1 is the cause.
4. **Implement Fix 3** (in-process latch) as the defensive default — it's the
   only fix that catches both Candidate 1 and Candidate 2 without a runtime
   cost.
5. **Add Fix 1** (regression test) regardless of which candidate wins.
6. **Verify**: `python -m pytest scripts/tests/test_edit_batch_hook.py
   scripts/tests/test_hook_intents.py -v` passes; manually run a Claude Code
   session and confirm only one nudge fires across many unbatched edits.

## Impact

- **Priority**: P3 — not a correctness or safety bug, but a self-defeating
  token-cost leak (the hook wastes tokens on itself).
- **Effort**: Small — ~30-50 LOC across one production file and two test
  files.
- **Risk**: Low — the in-process latch is purely additive (over-suppresses,
  which is the safe direction); the regression test catches the persistence
  failure path; both are independent of the existing happy-path tests.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `scripts/little_loops/hooks/edit_batch_nudge.py:1-48` | Hook docstring explicitly states "at most once per session" contract |
| `scripts/little_loops/hooks/edit_batch_nudge.py:95-105` | `_persist_state` — three silent exception handlers |
| `scripts/little_loops/hooks/edit_batch_nudge.py:126-127` | The `nudged` latch check that should suppress |
| `scripts/tests/test_edit_batch_hook.py:140-156` | Existing once-per-session test (uses monkeypatched clock + isolated cwd) |
| `scripts/tests/test_hook_intents.py:380-407` | Dispatch test that lacks post-state assertion |
| `.ll/ll-edit-batch-state.json` | State file — current observation shows `nudged: false` |
| `scripts/little_loops/file_utils.py:35-57` | `atomic_write_json` — raises on OSError (caught and swallowed by hook) |
| `scripts/little_loops/file_utils.py:60-90` | `acquire_lock` — fcntl-based, raises TimeoutError (caught and swallowed by hook) |

## Status

**Open** | Created: 2026-07-07 | Priority: P3 | Captured from ENH-2518 review session

## Session Log
- `/ll:capture-issue` - 2026-07-07T16:44:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d6a4cb1-d0a9-4055-9756-6b047ca62f08.jsonl`