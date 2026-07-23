---
id: ENH-2748
title: Suppress flag for capture-reachability validator warning
type: ENH
priority: P3
status: open
captured_at: '2026-07-22T00:00:00Z'
discovered_date: '2026-07-22'
discovered_by: capture-issue
relates_to:
- ENH-1961
- BUG-1997
- ENH-2128
- BUG-2744
labels:
- fsm
- validation
- dx
---

# ENH-2748: Suppress flag for capture-reachability validator warning

## Summary

`_validate_capture_reachability()` (`scripts/little_loops/fsm/validation.py`,
ENH-1961) does pure state-graph dominance analysis on `${captured.*}`
references and has no way for a loop author to mark a flagged reference as
intentionally safe. When a loop closes a stale-capture gap with a *runtime*
guard the validator can't model (e.g. a marker file written/checked by shell
actions), the WARNING keeps firing on every `ll-loop run`/`ll-loop validate`
forever, even though the case is understood and already fixed.

This is unlike the MR-1 through MR-11 meta-loop rules (`fsm/validation.py`),
each of which supports a top-level per-rule suppress flag (`meta_self_eval_ok`,
`shared_state_ok`, `bash_default_ok`, etc.) so an author can silence a
specific, reviewed false positive without losing the check for everything
else. The capture-reachability check has no equivalent.

## Current Behavior

The only existing mitigation is `TestValidatorWarningBudget.ALLOWLIST` in
`scripts/tests/test_builtin_loops.py` (~line 11068) — a test-code map of
`(loop stem, category) -> allowed warning paths` that keeps CI from failing on
known false positives and ratchets bidirectionally (fails if a "fixed" entry
stops producing its warning). This works for CI but does nothing for the
interactive/automation path: every `ll-loop run` still prints the WARNING to
stderr.

Concretely, `autodev.yaml`'s `check_guard2_verdict` state references
`${captured.size_review_output.output}`. `check_broke_down`'s `on_no`
shortcut can statically reach it without `run_size_review` (the capturing
state) ever running. BUG-2744 closed the actual correctness gap by adding
`check_size_review_ran_this_pass`, a runtime marker-file gate
(`autodev-size-review-skipped-this-pass`) that reroutes that path away from
`check_guard2_verdict` before it ever reads a stale capture. The validator
can't see the marker file's runtime semantics, so it still flags the state as
statically reachable via the bypass path — correctly, from a pure graph
standpoint, but the case is already handled. The warning is allowlisted in
`TestValidatorWarningBudget.ALLOWLIST` (`("autodev", "capture-ordering")` ->
`"states.check_guard2_verdict.action"`) but still prints on every real run.

## Expected Behavior

A loop author who has reviewed a capture-reachability warning and confirmed
the bypass path is runtime-guarded can suppress it explicitly in the loop
YAML — mirroring the MR-* pattern (e.g. a top-level
`capture_reachability_ok: true`, or a narrower per-state/per-var suppress list
if blanket-loop suppression is judged too coarse). Suppressed warnings should
still be validated for staleness (analogous to
`test_allowlist_entries_are_not_stale`) so a suppress flag doesn't silently
outlive the condition that justified it.

## Motivation

Loop authors currently have no way to acknowledge-and-silence a reviewed
capture-reachability false positive at the source; the only lever is a
test-file allowlist that a runtime `ll-loop run` never consults. This is
recurring noise (`autodev`, `adopt-third-party-api`, `examples-miner`,
`goal-cluster`, `integrate-sdk` all currently carry allowlisted
`capture-ordering` warnings) that trains users to ignore validator output —
undermining the check's value for genuinely new bypass bugs.

## Proposed Solution

- Add a suppress mechanism to `_validate_capture_reachability()` analogous to
  the MR-* `top-level flag` convention already documented in
  `.claude/CLAUDE.md` § Loop Authoring (e.g. `capture_reachability_ok: true`
  at loop top level, or scoped to specific `state.path` entries if that's
  too coarse for multi-warning loops).
- When set, downgrade or drop the corresponding WARNING(s) at both
  `ll-loop validate` and `ll-loop run` time.
- Once implemented, migrate the existing `TestValidatorWarningBudget.ALLOWLIST`
  `capture-ordering` entries (Bucket A: sub-loop-injected captures, plus the
  `autodev`/`check_guard2_verdict` runtime-guard case) to the new in-YAML
  flag, and consider whether the test-level ratchet can be simplified once
  the suppress reason lives next to the state it protects.

## Impact

- **Priority**: P3 - Cosmetic/DX noise, not a correctness bug; all currently
  known cases are already tracked via the test allowlist.
- **Effort**: Small - one new validator suppress-flag check plus config
  plumbing, following the existing MR-* flag pattern closely.
- **Risk**: Low - purely additive; existing unsuppressed loops are unaffected.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-23T02:34:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d2bccef-f831-463f-83a5-6b0e317afe52.jsonl`

---

**Open** | Created: 2026-07-22 | Priority: P3
