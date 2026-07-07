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

### Candidate 4: `_STATE_PATH` is cwd-relative and may resolve to a different file

_Added by `/ll:refine-issue` — based on codebase analysis:_

The state path is defined at `edit_batch_nudge.py:70` as:

```python
_STATE_PATH = Path(".ll/ll-edit-batch-state.json")
```

This is a **relative `Path` object**, not absolute. `Path` operations resolve
against `Path.cwd()` at the time of the call, not at import time.

- The dispatcher (`scripts/little_loops/hooks/__init__.py:136`) captures
  `cwd=os.getcwd()` into `event.cwd` but `edit_batch_nudge` does **not** use
  it — it uses `Path.cwd()` indirectly via the relative `_STATE_PATH`.
- If the Python process's cwd changes between two consecutive PostToolUse
  invocations (e.g., the user ran a `Bash` tool call with `cd subdir` between
  two `Edit` calls), the second hook reads from a **different file** (or no
  file at all). A clean `.ll/ll-edit-batch-state.json` in the new cwd →
  `nudged` latch not present → handler treats it as a fresh session → re-nudges.

This is a third pathway by which the `nudged: true` write can fail to "stick"
across hook invocations, independent of the persistence and session-id paths
in Candidates 1–2. Same `Bash` → `Edit` sequence was almost certainly part of
the ENH-2518 review session that captured this bug.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The three proposed fixes are not greenfield; each maps to an existing pattern
already in the codebase. Implementation should follow these anchors, not invent
new shapes:

**Fix 1 (regression test) — model after `test_dispatch_pre_compact_happy_path`**

The existing dispatch happy-path test for `edit_batch_nudge` at
`scripts/tests/test_hook_intents.py:380-407` asserts `returncode == 2` and
`"batch" in stderr.lower()` but never reads the state file afterward — the
exact gap the issue calls out.

The template to follow is **`test_dispatch_pre_compact_happy_path`** at
`scripts/tests/test_hook_intents.py:273-285`, which asserts:

```python
assert (tmp_path / ".ll" / "ll-precompact-state.json").is_file()
```

For the new test, follow this pattern but assert `nudged: True` is in the JSON
content (not just that the file exists). Also relevant: the in-process test
`test_state_records_nudged_flag` at `scripts/tests/test_edit_batch_hook.py:195-206`
already asserts `_load_state()["nudged"] is True` post-fire, but only under
monkeypatched isolation — the dispatch version is the missing piece.

**Fix 2 (debug logging) — use the existing `logging.getLogger(__name__)` convention**

`LL_DEBUG` is **not** an env var that exists in the codebase. The only
references to it are inside this BUG-2521 issue itself. Implementing a new
env var would be inconsistent.

The established convention in `scripts/little_loops/hooks/` is the standard
`logging` module. Only one hook currently uses it:
`scripts/little_loops/hooks/session_start.py:33-44`:

```python
import logging
...
logger = logging.getLogger(__name__)
```

Fix 2 should follow this same pattern: add the import, get a logger, and use
`logger.warning(...)` for suspect-fire diagnostics. The level is controlled by
the standard logging machinery (effective level set by root config or by the
host adapter's logging setup), no new env var needed. If a stderr-only opt-in
is desired, gate the calls on `logger.isEnabledFor(logging.DEBUG)`.

**Fix 3 (in-process latch) — the pattern already exists**

The exact shape proposed (`_SESSION_CACHE` as a module-level `dict[str, bool]`)
is already in use at two sites:

- `scripts/little_loops/hooks/learning_tests_gate.py:40-42`
  ```python
  # Session-level cache: package name → True (proven) / False (no record or refuted/stale).
  # Avoids repeated registry lookups for the same package within a session.
  _SESSION_CACHE: dict[str, bool] = {}
  ```
- `scripts/little_loops/hooks/install_learning_gate.py:43-46`
  (same pattern, same docstring shape)

Usage example in `install_learning_gate.py:112-116`:

```python
# Session cache hit
if pkg in _SESSION_CACHE:
    if _SESSION_CACHE[pkg]:
        return LLHookResult(exit_code=0)
    return LLHookResult(exit_code=0, feedback=format_nudge_message(pkg, stale=False))
```

For BUG-2521 the analogous shape is `_NUDGED_IN_THIS_PROCESS: set[str] = set()`
keyed on `session_id` (or `""` for missing). Check membership first; only fall
through to the on-disk state if the session hasn't nudged *in this process*.
This catches Candidates 1, 2, **and** 4 (cwd drift) because all of them
happen between processes, not within one.

A second, related instance-level pattern lives at
`scripts/little_loops/fsm/host_guard.py:344-349` and `:397-417`:
`HostGuard._budget_fired` (instance boolean) flips to `True` on first
threshold crossing and is never reset — same semantics, scoped to one
executor instance instead of one Python process.

**Additional fix for Candidate 4 — anchor `_STATE_PATH` to `event.cwd`**

Candidate 4 is independent of the three listed fixes. The minimum fix is to
change `edit_batch_nudge.py:70` from:

```python
_STATE_PATH = Path(".ll/ll-edit-batch-state.json")
```

to an absolute path resolved from `event.cwd` at handler-entry (the dispatcher
already captures it at `__init__.py:136`). Without this, the in-process latch
of Fix 3 will still mask the symptom, but the underlying state file remains
per-cwd-fragment, which is a latent footgun for any future host that runs
hooks from multiple cwds in one process.

**Sibling `session_id` resolution divergence to fix in passing**

`edit_batch_nudge.py:118` reads only `event.payload.get("session_id") or ""`,
while the sibling code at `user_prompt_submit.py:82,90` uses
`event.payload.get("session_id") or event.session_id` (broader fallback).
The top-level `event.session_id` field lives on `LLHookEvent` at
`scripts/little_loops/hooks/types.py:44`. Aligning the resolution path is
a low-risk extra hardening that closes another vector for Candidate 1.

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
- **State path declaration**: `scripts/little_loops/hooks/edit_batch_nudge.py:70`
  (`_STATE_PATH = Path(".ll/ll-edit-batch-state.json")` — cwd-relative; Candidate 4)
- **session_id resolution**: `scripts/little_loops/hooks/edit_batch_nudge.py:118`
  (reads only `event.payload.get("session_id") or ""` — diverges from sibling
  `user_prompt_submit.py:82,90` which falls back to `event.session_id`)
- **Dispatcher (provides `event.cwd`)**: `scripts/little_loops/hooks/__init__.py:136`
  (handler currently ignores this — Candidate 4 root cause)
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
   - If this test passes: candidates 1, 4, or test-gap are more likely
   - **Model the assertion after `test_dispatch_pre_compact_happy_path` at
     `scripts/tests/test_hook_intents.py:273-285`** — read the JSON file back
     and assert specific fields, not just file existence.
2. **Instrument the hook** with debug logging of `session_id`,
   `_persist_state` outcome, and the post-write state-file readback. Use the
   established `logging.getLogger(__name__)` convention from
   `scripts/little_loops/hooks/session_start.py:33-44` (NOT a new `LL_DEBUG`
   env var — no such env var exists in the codebase). Gate `logger.warning(...)`
   calls on `logger.isEnabledFor(logging.DEBUG)` to stay silent in production.
3. **Capture a real session trace.** Run a Claude Code session that triggers
   a double-fire; dump the payload `session_id` for every Edit-hook invocation
   to determine whether Candidate 1 is the cause. Capture `os.getcwd()` at the
   same time to evaluate Candidate 4 (cwd drift).
4. **Implement Fix 3** (in-process latch) as the defensive default — it's the
   only fix that catches Candidates 1, 2, AND 4 without a runtime cost.
   Use the existing pattern: add
   `_NUDGED_IN_THIS_PROCESS: set[str] = set()` at module scope (modeled on
   `_SESSION_CACHE` in `scripts/little_loops/hooks/learning_tests_gate.py:40-42`
   and `scripts/little_loops/hooks/install_learning_gate.py:43-46`).
   Membership check must run **before** the on-disk state read.
5. **Anchor `_STATE_PATH` to `event.cwd`.** Change `edit_batch_nudge.py:70`
   from a module-level relative `Path` to a per-call absolute path resolved
   from `event.cwd` (already captured by the dispatcher at
   `scripts/little_loops/hooks/__init__.py:136`). This addresses Candidate 4
   directly; without it, the in-process latch masks the symptom but the
   underlying per-cwd state-file footgun remains.
6. **Align `session_id` resolution** with sibling code. Change
   `edit_batch_nudge.py:118` from `event.payload.get("session_id") or ""` to
   `event.payload.get("session_id") or event.session_id or ""`, matching
   `user_prompt_submit.py:82,90`. The top-level `event.session_id` field is
   declared on `LLHookEvent` at `scripts/little_loops/hooks/types.py:44`.
7. **Add Fix 1** (regression test) regardless of which candidate wins —
   use the pattern in step 1, anchored to `test_dispatch_pre_compact_happy_path`.
8. **Verify**: `python -m pytest scripts/tests/test_edit_batch_hook.py
   scripts/tests/test_hook_intents.py -v` passes; manually run a Claude Code
   session and confirm only one nudge fires across many unbatched edits; also
   `python -m pytest scripts/tests/` to confirm no hook-adjacent regression
   (the dispatch change at step 5 may surface a stray assertion elsewhere).

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