---
id: BUG-3375
type: BUG
title: autodev cascades Errno 2 into clean terminal exit and silently abandons
  queue when worktree vanishes
priority: P2
status: open
discovered_by: claude-code-review
discovered_date: '2026-09-01'
relates_to: [BUG-3373, ENH-3374]
---

# BUG-3375: autodev cascades Errno 2 into clean terminal exit and silently abandons queue when worktree vanishes

## Summary

When the shared worktree a sub-loop is running in disappears mid-run, the
FSM has no notion of "my working directory is gone": every subsequent shell
action fails with `[Errno 2] No such file or directory` at `Popen`
(`cwd=worktree`), each failure is routed through the loop's ordinary
`on_error` edges, and the loop walks — erroring state by erroring state —
to a *clean* terminal exit. In the BUG-3373 incident, `refine-to-ready-issue`
and then `autodev` cascaded ~12 such errors in under a second, autodev
exited via its normal terminal state, the remaining queued issue (ENH-1722)
was never dequeued, and the run's only verdict was a generic
`incomplete-abandoned` — nothing surfaced "the worktree vanished" as the
cause.

## Current Behavior

From `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`
(`03:57:14.937`–`03:57:15.369`): `check_decision_mid_refine`,
`check_wire_done`, `normalize_structure`, `check_verify_verdict`, … then
autodev's `skip_inflight`, `dequeue_next`, `finalize_done` each raise
`action_error` `[Errno 2] No such file or directory: PosixPath('...')`,
each routes onward via `on_error`, and both loops reach `loop_complete`
normally. The operator-facing result is an `incomplete-abandoned` verdict
indistinguishable from an ordinary partial drain; the abandoned issue is
reported only as a count.

## Expected Behavior

A vanished working directory is an unrecoverable infrastructure failure,
not a per-state error to be routed around. When an action fails because the
executor's `working_dir` no longer exists, the executor should:

1. detect it (a `FileNotFoundError` from `Popen` whose `cwd` no longer
   exists, confirmed by an explicit `working_dir` existence check),
2. abort the loop immediately with a distinct infrastructure-failure
   terminal (analogous to the existing infra-retry classification), rather
   than dispatching further states that can only fail the same way, and
3. surface the cause explicitly in events and the finalize verdict (e.g.
   `verdict=infra-worktree-vanished`, naming the missing path), so the
   operator sees "worktree deleted mid-run", not a generic abandonment.

## Motivation

The silent-clean-exit behavior is what turned the BUG-3373 deletion into an
invisible batch truncation: one issue killed mid-refine, one abandoned
untouched, and a verdict that reads like a routine timeout. Whatever the
upstream deleter turns out to be (BUG-3373) and however cleanup is hardened
(ENH-3374), the executor should fail loudly and immediately when the ground
disappears from under it — both for operators and so future incidents are
diagnosable from the verdict instead of a full events.jsonl replay.

## Proposed Solution

In `scripts/little_loops/fsm/executor.py`:

1. In the subprocess-launch path(s) (`_run_subprocess_direct` and the
   action-runner shell branch), catch the `Popen` failure when
   `self.working_dir` no longer exists and classify it as a new
   infrastructure failure kind (e.g. `workdir_vanished`) instead of a
   generic action error.
2. On that classification, stop routing via the state's `on_error` edge:
   terminate the loop with a distinct failure terminal, emitting a new
   event (e.g. `workdir_vanished`) carrying the missing path and current
   state. Follow the established event-registration procedure
   (CONTRIBUTING.md § "Event Schema Maintenance": EVENT-SCHEMA.md →
   `SCHEMA_DEFINITIONS` in `generate_schemas.py` → regenerate → commit
   `.json` → `DESVariant` in `observability/schema.py`; update the
   `test_generate_schemas.py` count literals and
   `test_des_schema.py`/`test_des_audit.py` expectations).
3. Let parent sub-loops observe the child's distinct terminal
   (`terminated_by`/verdict plumbing already read by
   `auto-refine-and-implement`'s `delegate_failed` state) so the sprint
   verdict names the real cause.
4. Tests in `scripts/tests/test_fsm_executor.py`: delete the executor's
   working dir mid-run (after the first state) and assert the loop
   terminates with the new failure terminal after at most one further
   dispatch attempt, with the new event emitted — instead of walking its
   remaining states.

## Impact

Without this, any mid-run loss of a worktree (BUG-3373's actor, manual
deletion, disk issues) converts into a plausible-looking partial-drain
verdict; queued issues are abandoned with no signal. Affects all sub-loop
based automation (`autodev`, `auto-refine-and-implement`,
`sprint-refine-and-implement`, `refine-to-ready-issue`).

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md`
- `CONTRIBUTING.md` § Event Schema Maintenance
- `docs/reference/DEFERRAL_CODES.md`

## Status

**Open** | Created: 2026-09-01 | Priority: P2
