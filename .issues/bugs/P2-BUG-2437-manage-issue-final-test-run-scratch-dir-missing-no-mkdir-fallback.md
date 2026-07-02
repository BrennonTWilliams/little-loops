---
captured_at: '2026-07-02T03:54:24Z'
completed_at: '2026-07-02T03:54:24Z'
discovered_date: 2026-07-02
discovered_by: user-report
status: done
priority: P2
type: BUG
relates_to:
- BUG-2420
- BUG-2438
labels:
- hooks
- scratch-pad
- automation
- fsm
---

# BUG-2437: manage-issue final test run loses its scratch directory when the redirect hook doesn't fire; FSM spawn continuations lose automation permission_mode

## Summary

`/ll:manage-issue`'s final verification step regularly fails with "the scratch
subdirectory doesn't exist" because its authored redirect command has no
`mkdir -p` fallback and depends entirely on a hook that silently no-ops
whenever the session's `permission_mode` isn't `bypassPermissions` — a state
that spawned FSM loop continuations (`on_handoff: spawn`) always land in
because `_spawn_continuation` explicitly stripped the CLI flag that would have
set it.

## Current Behavior

`skills/manage-issue/SKILL.md`'s Phase 4 "Headless-Safe Final Test Run"
authored the final-test-run command literally as:

```
{{config.project.test_cmd}} > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 .loops/tmp/scratch/test-results.txt
```

with no `mkdir -p` of its own. It relied entirely on the `scratch-pad-redirect.sh`
PreToolUse hook to create `.loops/tmp/scratch/` first. That hook only rewrites
(and thus only `mkdir -p`s) a Bash command when `scratch_pad.automation_contexts_only`
is true (default) **and** the hook event's `permission_mode == "bypassPermissions"`
— any other permission mode passes the command through completely unmodified,
performing no directory creation at all.

Separately, `scripts/little_loops/fsm/handoff_handler.py`'s `_spawn_continuation`
(used whenever an FSM loop's `on_handoff: spawn` behavior — the default across
most built-in loops — hands off to a new Claude process, e.g. after a
backgrounded command outlives the turn) built its invocation via
`resolve_host().build_detached()`, which *does* include
`--dangerously-skip-permissions` in argv by default, matching every other
automation invocation path (`build_streaming`/`build_blocking_json`, used by
`ll-auto`/`ll-parallel`/`ll-sprint`). But the very next line stripped that flag
back out:

```python
# Legacy argv had no perm-skip; strip it for no-behavior-change refactor.
args = [a for a in invocation.args if a != "--dangerously-skip-permissions"]
```

`build_detached()` does still pass `DANGEROUSLY_SKIP_PERMISSIONS=1` via `env`
(added for BUG-2110), so the spawned process itself skips permission prompts —
but dropping the flag from argv means the spawned session's hook events report
a `permission_mode` other than `"bypassPermissions"`. Any loop wrapping
`/ll:manage-issue` that hits a `CONTEXT_HANDOFF` mid-verification therefore
resumes in a session where the scratch-pad hook's automation gate silently
fails, `mkdir -p .loops/tmp/scratch` never runs, and the un-rewritten,
`mkdir`-less command from `SKILL.md` fails outright with
"No such file or directory."

## Expected Behavior

The final-test-run command creates its own scratch directory unconditionally,
independent of whether the PreToolUse hook fires. Spawned FSM loop
continuations report the same `permission_mode` as every other automation
invocation path in the fleet, so `automation_contexts_only`-gated hook
behavior (not just scratch-pad) works consistently for `on_handoff: spawn`
loops.

## Root Cause

- **File**: `skills/manage-issue/SKILL.md` (Phase 4, "Headless-Safe Final Test
  Run") and `.claude/CLAUDE.md` ("Automation: Scratch Pad")
- **Anchor**: the literal `{{config.project.test_cmd}} > .loops/tmp/scratch/...`
  example command
- **Cause**: no `mkdir -p` prefix; directory creation was entirely delegated to
  a conditionally-gated PreToolUse hook rewrite.
- **File**: `scripts/little_loops/fsm/handoff_handler.py`
- **Anchor**: `_spawn_continuation()`
- **Cause**: explicitly filtered `--dangerously-skip-permissions` out of the
  spawned process's argv ("no-behavior-change refactor" for legacy argv
  shape), which predates the `automation_contexts_only` permission-mode
  detection design added later and was never reconciled with it.

## Proposed Solution (applied)

1. Prefix the authored redirect commands with `mkdir -p .loops/tmp/scratch &&`
   in both `skills/manage-issue/SKILL.md:374` and `.claude/CLAUDE.md`'s
   "Automation: Scratch Pad" section, so the command is self-sufficient
   regardless of hook/permission-mode state.
2. Remove the `--dangerously-skip-permissions` stripping in
   `handoff_handler.py:_spawn_continuation`, so spawned continuations keep the
   flag `build_detached()` already puts in argv, matching
   `build_streaming`/`build_blocking_json`.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` - add `mkdir -p .loops/tmp/scratch &&` prefix
- `.claude/CLAUDE.md` - same prefix in the "Automation: Scratch Pad" example
- `scripts/little_loops/fsm/handoff_handler.py` - stop stripping the perm flag

### Dependent Files (Callers/Importers)
- N/A - `_spawn_continuation` has a single call site (`HandoffHandler.handle`,
  `SPAWN` branch); no other caller depends on the stripped-flag behavior.

### Tests
- `scripts/tests/test_handoff_handler.py` - `test_spawn_behavior` now asserts
  `--dangerously-skip-permissions` is present in the spawned argv.

### Documentation
- N/A - `SKILL.md`/`CLAUDE.md` changes are themselves the documentation.

### Configuration
- N/A - no config schema changes.

## Steps to Reproduce

1. Enable `scratch_pad.enabled: true` with `automation_contexts_only: true`
   (default).
2. Run `/ll:manage-issue` on an issue from within an FSM loop using
   `on_handoff: spawn` (the default handoff behavior for most built-in loops).
3. Let the final test suite run long enough to trigger a `CONTEXT_HANDOFF`
   mid-run.
4. Observe the spawned continuation session's re-run of the final test suite
   fail with "No such file or directory" against `.loops/tmp/scratch/...`.

## Actual Behavior

The redirect command fails because `.loops/tmp/scratch` doesn't exist and
nothing in the resumed session recreates it; Claude then manually runs `mkdir`
and retries.

## Impact

- **Priority**: P2 - Recurring automation-reliability nuisance in a
  frequently-run skill (`/ll:manage-issue`'s final verification phase),
  forcing manual recovery and burning turns/tokens on every occurrence.
- **Effort**: Small - three targeted edits (two doc/skill prefixes, one
  deleted line + comment in `handoff_handler.py`), plus one test assertion
  update.
- **Risk**: Low - the `mkdir -p` prefix is additive and idempotent; restoring
  the permission flag in spawn argv brings that path in line with the rest of
  the already-`--dangerously-skip-permissions` automation fleet.
- **Breaking Change**: No.

## Related Issues

- **BUG-2420** — fixed the same-session `Stop`-hook cleanup race for scratch-pad;
  this issue's `on_handoff: spawn` finding is a separate, cross-session gap in
  the same subsystem.
- **BUG-2438** — a second, independently-discovered defect in the same area,
  found while verifying this fix: `scratch-cleanup.sh`'s `SessionEnd` handler
  raced *other concurrent sessions* sharing the same scratch path.

## Resolution

Fixed both defects (2026-07-02).

- Added `mkdir -p .loops/tmp/scratch &&` to the authored redirect commands in
  `skills/manage-issue/SKILL.md` and `.claude/CLAUDE.md`.
- Removed the `--dangerously-skip-permissions` strip in
  `handoff_handler.py:_spawn_continuation`; spawned continuations now carry
  the flag in argv, matching `env`.
- Updated `scripts/tests/test_handoff_handler.py::test_spawn_behavior` to
  assert the flag is present.

Full suite: 13386 passed, 23 skipped.

## Status

**Current Status**: done


## Session Log
- `hook:posttooluse-status-done` - 2026-07-02T03:55:21 - `108b6549-24ca-4d55-a125-5edfe54155dc.jsonl`
