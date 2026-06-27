---
id: ENH-2352
type: ENH
priority: P3
status: open
captured_at: '2026-06-27T21:58:52Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
labels:
- captured
- audit-loop-run
- false-positive
---

# ENH-2352: `audit-loop-run` laundering check false-positives on the ENH-2005 sidecar pattern

## Summary

The sub-loop verdict-laundering check in `/ll:audit-loop-run` flags any state
where `on_success == on_failure` (or `on_yes == on_no`). This re-fires on the
**intentional** ENH-2005 artifact-channel sidecar pattern used by `rn-implement`
(`run_remediation`, `run_decomposition`) and similar recursive loops, producing
a false positive on every `rn-*` audit.

## Motivation

In the ENH-2005 pattern the collapse is by design: the child's real verdict is
read from `subloop_outcome_<ID>.txt` by a downstream classifier, and `on_error`
is deliberately split out to a distinct crash state (`record_sub_loop_crash`) so
an infrastructure crash is never laundered into a generic failure token. The
audit acknowledges the mitigation but flags it anyway (see
`rn-implement-audit-2026-06-27.md` "Sub-Loop Verdict Laundering Check"). A check
that cries wolf on a documented, correct pattern erodes trust in the audit and
buries genuine laundering.

## Current Behavior

The laundering check matches `on_success == on_failure` literally and flags the
state, regardless of whether the parent recovers the true verdict via an
artifact channel.

## Expected Behavior

Recognize the artifact-channel sidecar signature and suppress (or downgrade to
INFO with the mitigation noted). A state matches the safe pattern when **all**
hold:

1. `on_success`/`on_yes` and `on_failure`/`on_no` route to the same next state,
   AND that state (or its immediate successor) reads `subloop_outcome_<ID>.txt`
   (a per-issue outcome artifact under `run_dir`); AND
2. `on_error` routes to a **distinct** state (not the shared classifier) — i.e.
   a crash is attributed separately, not collapsed.

When both hold, do not raise a laundering finding (or mark it INFO/mitigated).
When `on_error` is *also* collapsed into the same target, keep flagging it —
that is the genuinely unsafe case.

## Proposed Solution

In the laundering-detection step of `audit-loop-run`:

- After detecting `on_success == on_failure`, inspect the shared target's action
  for a `subloop_outcome_` (or configurable outcome-artifact) read.
- Inspect `on_error` and confirm it differs from the shared target.
- Emit `mitigated` / suppress when both conditions pass; otherwise flag as today.

Anchor references: `rn-implement.yaml` `run_remediation`/`classify_remediation`
and `run_decomposition`/`classify_decomposition`; the ENH-2005 rationale is
documented inline in those states. Relates to BUG-2351 (sibling verdict-accuracy
fix in the same skill).

## Impact

- **Severity**: Low — cosmetic/precision, but recurring on every recursive-loop
  audit.
- **Benefit**: Keeps the laundering finding meaningful so real laundering stands
  out.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:58:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09e0f30a-d9cd-4afe-a20d-1b4ab9afdd5a.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-27
