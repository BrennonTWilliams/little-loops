---
id: BUG-3363
type: BUG
title: scratch-cleanup.sh SessionEnd hook intermittently cancelled on session exit
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-30'
captured_at: '2026-08-30T19:48:39Z'
completed_at: '2026-08-30T21:11:19Z'
program_design_not_applicable: true
confidence_score: 98
outcome_confidence: 87
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 20
---

# BUG-3363: scratch-cleanup.sh SessionEnd hook intermittently cancelled on session exit

## Summary

Every so often, exiting a Claude Code session in this repo (Ctrl+C, Ctrl+D, or
`/exit`) prints:

```
SessionEnd hook [bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-cleanup.sh] failed: Hook cancelled
```

This is the same class of upstream Claude Code bug documented in BUG-2483
(anthropics/claude-code#32712, #41577: `SessionEnd` hooks get forcibly killed
around a ~1.5s ceiling regardless of configured `timeout`, independent of
interrupt vs. clean exit). BUG-2483 fixed this for `session-end.sh` (the
stale-cross-issue-ref sweep, ~1.6s runtime) by re-homing it to `SessionStart`,
but deliberately left `scratch-cleanup.sh` on `SessionEnd` because its own
runtime (~0.07s) sits nowhere near that ceiling.

`scratch-cleanup.sh` being cancelled anyway suggests the kill isn't purely a
function of the hook's own wall-clock cost — process-teardown timing on
interrupt-style exits (Ctrl+C/Ctrl+D) appears able to trip the same ceiling
even for a fast hook, likely because multiple `SessionEnd` hooks queue behind
each other and/or session teardown itself competes for the deadline window.

## Current Behavior

`hooks/hooks.json` binds `scratch-cleanup.sh` to `SessionEnd`. On exit, the
hook is occasionally killed before completion, printing "Hook cancelled" to
the terminal.

## Expected Behavior

Session exit should not print a hook-failure error on ordinary use.

## Steps to Reproduce

1. Start a Claude Code session in this repo (with `scratch-cleanup.sh` wired
   to `SessionEnd` per `hooks/hooks.json`).
2. End the session via Ctrl+C, Ctrl+D, or `/exit`.
3. Observe (intermittently, not on every exit): `SessionEnd hook [bash
   ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-cleanup.sh] failed: Hook
   cancelled` printed to the terminal.

## Motivation

Purely cosmetic, but it erodes trust in the hook system: a user seeing a
`failed` message for a hook that always `exit 0`s and only prunes files it
owns (BUG-2525) has no way to distinguish this from a real failure without
digging into the issue tracker. Fixing it removes a recurring, unexplained
warning from ordinary session exits in this repo and its `local-editable`
consumers.

## Proposed Solution

Apply the same pattern as BUG-2483: move `scratch-cleanup.sh`'s sweep off the
`SessionEnd` event (e.g., run it at the next `SessionStart` instead, alongside
`session-start.sh`) so it no longer races session-exit teardown. Needs
confirmation this doesn't reintroduce the concurrent-session race
`scratch-cleanup.sh`'s own header docs warn about for `Stop`-based cleanup
(BUG-2420) — `SessionStart` for one session could run while another
session's backgrounded, scratch-pad-redirected command is still writing.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — move the `scratch-cleanup.sh` command entry from the
  `SessionEnd` array to the `SessionStart` array (mirroring the
  `session-end.sh` entry already re-homed there for BUG-2483).
- `hooks/scripts/scratch-cleanup.sh` — update the header comment describing
  it as a "SessionEnd hook" once re-homed.

_Wiring pass added by `/ll:wire-issue`; decisions resolved in review 2026-08-30:_
- `hooks/hooks.json` — **drop** (do not move) the paired telemetry entry
  `record-hook-event.sh SessionEnd hooks/scripts/scratch-cleanup.sh`
  (`hooks/hooks.json:253-260`). The shim's documented purpose is covering
  *bash-only* events with no Python dispatch (`Stop`/`SessionEnd`,
  `docs/guides/BUILTIN_HOOKS_GUIDE.md:422-435`); `SessionStart` already flows
  through `session-start.sh` → Python dispatch, and BUG-2483's own precedent
  left no `record-hook-event` pairing behind when `session-end.sh` moved to
  `SessionStart`. Moving the shim would also add a third startup
  `statusMessage`; dropping it matches precedent and keeps startup lean.
- `hooks/hooks.json` — with both groups gone, **drop the `SessionEnd` key
  entirely** (decided; do not leave `"SessionEnd": []`, which invites
  confusion about accidental removal). The docs updates below already assume
  the zero-hooks outcome — TROUBLESHOOTING/ARCHITECTURE prose becomes "the
  shim is needed for `Stop` only."
- The moved command group keeps `"matcher": "*"` per `SessionStart`
  convention. Note the semantics: `SessionStart` with `*` fires on startup,
  `/clear`, resume, and post-compact — the sweep runs *more* often than once
  per session, not less. That's harmless (the `kill -0` PID-liveness guard
  protects live writers, including the current session's own backgrounded
  redirects) and improves cleanup frequency. Do **not** narrow the matcher to
  `"startup"` thinking it's more faithful to "run at next session start."
- The moved entry's `statusMessage` ("Cleaning up scratch pad...") will flash
  at session start alongside "Loading ll config..." — acceptable as-is now
  that the telemetry shim (a third message) is dropped rather than moved.
- `hooks/scripts/session-cleanup.sh` — line 19 comment ("Scratch cleanup now
  lives in scratch-cleanup.sh, wired to SessionEnd.") needs updating to say
  SessionStart.
- `.claude/CLAUDE.md` — line 218 states "`SessionEnd` `scratch-cleanup.sh`
  only prunes files..."; update to SessionStart.
- `docs/development/TROUBLESHOOTING.md` — lines 1041-1043 claim `Stop`/
  `SessionEnd` are the bash-only events needing the `record-hook-event.sh`
  shim; stale once `SessionEnd` ends up with zero registered hooks.
- `docs/ARCHITECTURE.md` — line 656 (`v30 hook_events` schema table row)
  makes the same `Stop`/`SessionEnd` claim; same staleness risk.

### Dependent Files (Callers/Importers)
- `hooks/adapters/claude-code/session-start.sh` — already runs at
  `SessionStart`; the new binding runs alongside it as its own hook entry,
  not by editing this script.

### Similar Patterns
- BUG-2483 (`1f788f51b`) re-homed `session-end.sh`'s sweep from `SessionEnd`
  to `SessionStart` in `hooks/hooks.json` for the identical upstream-deadline
  reason; this issue applies the same rebinding pattern to
  `scratch-cleanup.sh`.

### Tests
- `scripts/tests/test_claude_code_adapter.py` — asserts `scratch-cleanup.sh`
  stays on `SessionEnd` (written for BUG-2483's `session-end.sh` move); needs
  updating once this hook also moves.
- `scripts/tests/test_hooks_integration.py::TestScratchCleanupSessionEnd` —
  BUG-2420 tests currently assume `SessionEnd` binding; assertions about
  *event binding* need updating, execution-behavior assertions (PID-suffix
  ownership, no blind `rm -rf`) are unaffected by which event triggers the
  script.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_claude_code_adapter.py:130-147`
  (`test_hooks_json_session_end_no_longer_references_sweep`) — its docstring
  (line 134) reads "The other SessionEnd handler (scratch-cleanup.sh)
  remains untouched." This won't fail the assertion but becomes stale prose
  once `scratch-cleanup.sh` also moves; update it.
- `scripts/tests/test_claude_code_adapter.py:92-114`
  (`test_hooks_json_registers_sweep_under_session_start`) — exact template
  to mirror for a new `test_hooks_json_registers_scratch_cleanup_under_session_start`.
- `scripts/tests/test_hooks_integration.py:2975-2986`
  (`test_hooks_json_registers_session_end_scratch_cleanup`) — confirmed
  exact current assertion; convert to a presence(`SessionStart`) +
  absence(`SessionEnd`) pair mirroring
  `test_claude_code_adapter.py:92-147`'s pattern for `session-end.sh`.
- New test needed: assert the `record-hook-event.sh` telemetry-pairing
  entry is gone (dropped, not moved — see Files to Modify) and that
  `hooks.json` no longer has a `SessionEnd` key.

### Documentation
- Any doc referencing `scratch-cleanup.sh` as a `SessionEnd` hook (e.g.
  `docs/guides/BUILTIN_HOOKS_GUIDE.md`) needs updating to reflect the new
  binding.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — this touches more than one mention:
  - Lifecycle table rows for `scratch-cleanup` and `record-hook-event`
    (lines 73-74) move up into the `SessionStart` rows (lines 52-54).
  - The `## SessionEnd` section (lines 460-475) documents only these two
    hooks. Relocate its `### Scratch-pad cleanup` subsection under
    `## SessionStart` (mirroring the `### Sweep stale cross-issue
    references` subsection BUG-2483 added there, lines 157-170); the
    `### Hook-event telemetry shim` subsection for this pairing is removed
    (the shim entry is dropped, not moved). Remove or repurpose the
    now-orphaned `## SessionEnd` heading and its deadline warning (line
    474).
  - The "Session from Hook's Perspective" ASCII diagram shows scratch
    cleanup under the "Session ends" block (lines 116-118); move it to the
    "You start a session" block (lines 87-90).
  - The `Stop` section's parenthetical (line 420: "Scratch cleanup now
    lives in `scratch-cleanup.sh` on SessionEnd") and its telemetry writeup
    (lines 426-431: "Registered on `Stop` and `SessionEnd` only...") both
    need updating to say `SessionStart`.
- `hooks/scripts/session-cleanup.sh:19` — see Files to Modify.
- `.claude/CLAUDE.md:218` — see Files to Modify.
- `docs/development/TROUBLESHOOTING.md:1041-1043`,
  `docs/ARCHITECTURE.md:656` — see Files to Modify.

### Configuration
- `hooks/hooks.json` (see Files to Modify above).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- BUG-2483's `hooks.json` move added a `"matcher": "*"` key to the relocated
  group (every `SessionStart` group carries one). The current `scratch-cleanup.sh`
  group under `SessionEnd` (`hooks/hooks.json:242-263`) lacks a `"matcher"` key —
  the move needs to add one to match the target array's convention.
- `hooks/hooks.json:257` binds a second `SessionEnd` group:
  `record-hook-event.sh SessionEnd hooks/scripts/scratch-cleanup.sh`.
  `record-hook-event.sh` is paired only with pure-bash `SessionEnd`/`Stop`
  handlers (`docs/guides/BUILTIN_HOOKS_GUIDE.md:422-435`); BUG-2483's
  precedent did not carry the analogous telemetry pairing into the
  `SessionStart` array when `session-end.sh` was re-homed. This issue's Files
  to Modify does not yet say what happens to this second `SessionEnd` group.
- BUG-2483's changed-file set beyond `hooks.json` and the two test files
  already listed here also included `docs/reference/HOST_COMPATIBILITY.md`
  (updated a `session_end` parity row/footnote) — worth checking for an
  analogous `scratch-cleanup.sh` row. `.ll/decisions.yaml` rule `ARCH-174`
  already records the general "don't bind expensive work to SessionEnd" rule
  from BUG-2483 and needs no new per-hook entry.
- `scratch-cleanup.sh` (`hooks/scripts/scratch-cleanup.sh:38-54`) does not use
  `flock`/`acquire_lock` (the `lib/common.sh:5-54` convention used by
  `context-monitor.sh`, `session-capture.sh`, `check-duplicate-issue-id.sh`,
  `precompact-state.sh`). Its BUG-2420 race protection is a per-file `kill -0`
  PID-liveness check, which is independent of which event triggers the sweep —
  this is the existing answer to Implementation Steps item 1's open
  confirmation: the guard already generalizes to a `SessionStart` trigger
  since it checks the writing process's liveness, not the triggering event.
- Test convention for hook-to-event binding (`test_claude_code_adapter.py:92-147`,
  BUG-2483's `session-end.sh` precedent): a presence assertion in the new
  event's array is paired with an absence/regression assertion in the old
  event's array, both matching substring-in-command filtered to
  `type == "command"`. `test_hooks_integration.py::TestScratchCleanupSessionEnd`'s
  current `SessionEnd`-binding assertion (`test_hooks_json_registers_session_end_scratch_cleanup`,
  lines 2975-2986) would need to mirror this presence+absence shape; the
  class's other 5 tests (lines 2881-2974) invoke the script directly and
  assert on filesystem state, unaffected by which event triggers it.

## Implementation Steps

1. Confirm re-homing to `SessionStart` doesn't reintroduce the BUG-2420
   concurrent-session race (a `SessionStart` sweep running while another
   session's backgrounded, scratch-pad-redirected write is still in flight).
2. Move the `scratch-cleanup.sh` command entry in `hooks/hooks.json` from
   `SessionEnd` to `SessionStart`, alongside `session-start.sh`.
3. Update `scratch-cleanup.sh`'s header comment and any docs describing it as
   a `SessionEnd` hook.
4. Update `test_claude_code_adapter.py` and
   `test_hooks_integration.py::TestScratchCleanupSessionEnd` event-binding
   assertions to match the new `SessionStart` wiring.
5. Verify structurally, not by chasing an intermittent symptom: the gate is
   the test assertions that `hooks.json` registers `scratch-cleanup.sh`
   under `SessionStart` and has no `SessionEnd` key — with zero hooks on
   `SessionEnd`, nothing can be cancelled. Then smoke-check: (a) a few
   manual exits (Ctrl+C, Ctrl+D, `/exit`) print no hook-failure message;
   (b) pruning fires on next start — plant a stale PID-suffixed file in
   `.loops/tmp/scratch/` (dead PID), start a session, confirm it's gone.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Drop the paired `record-hook-event.sh SessionEnd
  hooks/scripts/scratch-cleanup.sh` telemetry entry (decided — see Files to
  Modify: shim exists for bash-only events; `SessionStart` has Python
  dispatch, and BUG-2483 left no pairing behind), and drop the `SessionEnd`
  key entirely from `hooks.json` (decided — no empty `"SessionEnd": []`).
- Update `hooks/scripts/session-cleanup.sh:19` comment.
- Update `.claude/CLAUDE.md:218`.
- Update `docs/development/TROUBLESHOOTING.md:1041-1043` and
  `docs/ARCHITECTURE.md:656` — `SessionEnd` now has zero hooks, so the
  shim claim becomes "`Stop` only".
- Restructure `docs/guides/BUILTIN_HOOKS_GUIDE.md`'s `## SessionEnd`
  section, lifecycle table, ASCII diagram, and `Stop`-section prose per the
  specifics in Documentation above.
- Add new tests mirroring `test_claude_code_adapter.py:92-147`'s
  presence/absence pattern for `scratch-cleanup.sh`, update
  `test_hooks_integration.py:2975-2986`, and fix the stale docstring at
  `test_claude_code_adapter.py:134`.

## Impact

- **Priority**: P4 — purely cosmetic. The script always `exit 0`s and only
  prunes scratch files it owns (PID-suffixed, per the BUG-2525 contract);
  being cancelled mid-sweep just means some stale files linger for the next
  session's cleanup pass, not a correctness or data-loss issue.
- Noisy on exit, which is the sole reported symptom (analogous to BUG-2483
  before its fix).

## Out of Scope

- Fixing the upstream Claude Code `SessionEnd` hard-deadline bug itself
  (tracked upstream at anthropics/claude-code#32712 / #41577).

## Related Issues

- **BUG-2483** — first observed and fixed this class of bug for
  `session-end.sh`; this issue is the analogous case for `scratch-cleanup.sh`.
- **BUG-2420** — established `scratch-cleanup.sh`'s `SessionEnd` binding and
  the concurrent-session race rationale for staying off `Stop`.
- **BUG-2525** — the PID-suffix ownership contract `scratch-cleanup.sh`
  enforces, relevant to any re-homing fix.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-30 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-08-30T21:11:03 - `f4a71a24-6e8c-4fe8-b605-9397e7b59dac.jsonl`
- `/ll:ready-issue` - 2026-08-30T21:01:05 - `0d3ac98c-1bf3-4d62-ba46-1c4c2d95622b.jsonl`
- `/ll:confidence-check` - 2026-08-30T20:51:16 - `c0383600-4aba-41a2-bb58-b8d027178e96.jsonl`
- `/ll:wire-issue` - 2026-08-30T20:27:44 - `f157be7e-42d9-436b-aab4-68974045eabd.jsonl`
- `/ll:refine-issue` - 2026-08-30T20:16:05 - `0689d759-b3b6-42ca-983c-618fccd6cc96.jsonl`
- `/ll:format-issue` - 2026-08-30T19:53:31 - `a1ad8a57-f920-432c-8aa4-c8eaf847f8b7.jsonl`
- `/ll:capture-issue` - 2026-08-30T19:48:45 - `4bd95ca5-4fb0-45b7-a04a-49fb27f13423.jsonl`
