---
id: ENH-2005
title: "rn-implement: annotate intentional verdict laundering in run_remediation and run_decomposition"
type: ENH
priority: P4
status: open
captured_at: '2026-06-07T00:00:00Z'
discovered_date: '2026-06-07'
discovered_by: audit-loop-run
relates_to:
- ENH-1679
- ENH-1977
labels:
- rn-implement
- loop-defect
- documentation
---

# ENH-2005: Annotate intentional verdict laundering in rn-implement sub-loop states

## Summary

`run_remediation` and `run_decomposition` in `rn-implement` are `loop:` delegations, so their
terminal routes are `on_success` / `on_failure` / `on_error` (not `on_yes` / `on_no`). Both have
`on_success == on_failure == on_error` pointing to `classify_remediation` / `classify_decomposition`
respectively. `/ll:audit-loop-run` and `ll-loop validate` flag this as verdict laundering.

**Only `on_success == on_failure` is intentional.** The sub-loop's real outcome is passed via a
sidecar file (`subloop_outcome_<ID>.txt`), and the classify states read that file to route — so
collapsing the `done`/`failed` *verdict* is by design. **`on_error` is a different case.** Per the audit
(`rn-implement-audit-2026-06-07.md`, Proposals 2 & 3), an `on_error` (sub-loop crash, timeout,
context-resolution failure) can occur **before** the child writes its outcome token. Routing
`on_error` into `classify_*` then hits the `|| echo "IMPLEMENT_FAILED"` fallback, so an
infrastructure crash is silently **mislabeled as an implementation failure** — losing the
distinction the operator needs to triage.

This issue therefore does two things: (1) annotate `on_success`/`on_failure` as intentional sidecar
routing to stop the false-positive laundering flag, and (2) split `on_error` out to a distinct
`record_sub_loop_crash` state so genuine infrastructure failures are attributed correctly. (1) is a
pure annotation; (2) is the audit's recommended structural fix.

## Current Behavior

```yaml
run_remediation:
  loop: rn-remediate
  on_success: classify_remediation
  on_failure: classify_remediation
  on_error: classify_remediation
```

The FSM validator sees `on_success == on_failure` and emits a laundering warning. There is no way
to distinguish intentional sidecar-based routing from accidental verdict discard.

## Expected Behavior

- `ll-loop validate rn-implement` does not emit laundering warnings for `run_remediation` or `run_decomposition`
- `/ll:audit-loop-run rn-implement` does not flag these states as structural defects
- The design intent (sidecar-based routing via `subloop_outcome_<ID>.txt`) is self-documenting in the loop YAML

## Motivation

This enhancement would:
- Stop false-positive `verdict_laundering` warnings in `ll-loop validate` and `/ll:audit-loop-run` for states that intentionally use sidecar-based routing — reducing audit noise for operators
- Improve infrastructure failure attribution: sub-loop crashes and timeouts are currently laundered as `IMPLEMENT_FAILED`, losing the distinction needed for operator triage
- Make the sidecar routing pattern self-documenting in the loop YAML rather than requiring institutional knowledge of the design intent

## Proposed Solution

### Part 1 — annotate the intentional `on_success`/`on_failure` collapse

Add a per-state comment plus a suppression flag so the `done`/`failed` verdict collapse stops
tripping the laundering check:

```yaml
run_remediation:
  # on_success == on_failure is intentional: the real outcome is read from
  # subloop_outcome_<ID>.txt by classify_remediation (sidecar routing). on_error is NOT
  # collapsed here — see Part 2.
  verdict_laundering_ok: true   # if ll-loop validate supports per-state suppression
  loop: rn-remediate
  on_success: classify_remediation
  on_failure: classify_remediation
  on_error: record_sub_loop_crash   # CHANGED — see Part 2
```

If `ll-loop validate` has no per-state suppression mechanism, add a top-level
`verdict_laundering_intentional: true` flag instead (or extend the validator to recognize the
sidecar pattern — track as a separate enhancement).

### Part 2 — split `on_error` to a distinct crash-recording state (audit Proposals 2 & 3)

Repoint both sub-loop delegations' `on_error` to a new `record_sub_loop_crash` state so an
infrastructure failure is attributed as a crash, not laundered into `IMPLEMENT_FAILED`:

```yaml
record_sub_loop_crash:
  action_type: shell
  action: |
    ID="${captured.input.output}"
    echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") ${ID} SUB_LOOP_CRASH" \
      >> "${captured.run_dir.output}/failures.txt"
    echo "[SUB_LOOP_CRASH] $ID — sub-loop infrastructure failure (crash/timeout/context error)"
  next: dequeue_next
```

`run_remediation.on_error` and `run_decomposition.on_error` both target this state. Optionally
add a `sub_loop_crashes` tally to the `report` summary (distinct from `failed`).

## Implementation Steps

1. Annotate `run_remediation` and `run_decomposition` states with `verdict_laundering_ok: true` (or top-level flag) and a clarifying comment explaining the sidecar routing pattern
2. Add `record_sub_loop_crash` shell state that writes `SUB_LOOP_CRASH` to `failures.txt`
3. Repoint `run_remediation.on_error` and `run_decomposition.on_error` to `record_sub_loop_crash`
4. Optionally extend the `report` state to tally `sub_loop_crashes` separately from `failed`
5. Run `ll-loop validate rn-implement` and confirm no laundering warnings remain

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — annotate `run_remediation` / `run_decomposition`
  (`on_success`/`on_failure`); add `record_sub_loop_crash` state; repoint both `on_error` routes to it;
  optionally update `report` to tally sub-loop crashes

### Dependent Files (Callers/Importers)
- TBD — `grep -r "rn-implement" loops/` to find any orchestrating loops that invoke it

### Similar Patterns
- TBD — `grep -r "subloop_outcome" loops/` to find other sidecar-routing states that may warrant the same annotation

### Tests
- Manual: `ll-loop validate rn-implement` should pass with no laundering warnings (Part 1)
- Manual: trigger a sub-loop timeout/crash; verify `failures.txt` records `SUB_LOOP_CRASH` distinct from `IMPLEMENT_FAILED` (Part 2)

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop validate rn-implement` does not emit laundering warnings for `run_remediation` /
  `run_decomposition` (the `on_success == on_failure` collapse is recognized as intentional)
- A future `/ll:audit-loop-run rn-implement` does not flag `on_success`/`on_failure` as structural defects
- A sub-loop crash/timeout (no outcome token written) is recorded as `SUB_LOOP_CRASH` in
  `failures.txt` — distinguishable from a clean `IMPLEMENT_FAILED`/`SCORES_MISSING` outcome
- `on_error` is no longer routed through `classify_*` (so the `|| echo "IMPLEMENT_FAILED"` fallback
  no longer masks infrastructure failures)

## Scope Boundaries

- Part 1 is annotation-only; Part 2 changes routing for the error path only — neither alters the
  happy-path (`on_yes`/`on_no`) runtime behavior
- Does not implement a new per-state suppression mechanism in `ll-loop validate` if one does not yet
  exist (track that as a separate enhancement; fall back to the top-level flag)
- Does not modify other loops that may have similar sidecar-routing patterns

## Impact

- **Priority**: P4 — Part 1 (annotation) is cosmetic noise reduction; Part 2 (crash attribution)
  is a low-severity observability fix. Neither blocks the loop's primary function, so P4 holds.
- **Effort**: Small — annotation + one new shell state + repointing two `on_error` routes in one
  file; no Python code changes
- **Risk**: Low — happy-path routing (`on_yes`/`on_no`) is unchanged; only the error path moves,
  from a laundered fallback to an explicit record. Worst case is an extra `failures.txt` line
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-07 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-07T20:55:24 - `a5956258-4fc8-4113-91bc-8549df3f7bb9.jsonl`
- `/ll:format-issue` - 2026-06-07T20:47:20 - `57f27ab7-f753-43a9-be87-54b2970f859d.jsonl`
