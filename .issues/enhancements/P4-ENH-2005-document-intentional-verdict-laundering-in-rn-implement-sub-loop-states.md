---
id: ENH-2005
title: 'rn-implement: annotate intentional verdict laundering in run_remediation and
  run_decomposition'
type: ENH
priority: P4
status: done
captured_at: '2026-06-07T00:00:00Z'
completed_at: 2026-06-07 22:06:00+00:00
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
respectively. The LLM-driven `/ll:audit-loop-run` skill (Step 8, "Sub-Loop Verdict Laundering
Check") can flag this collapse as verdict laundering. (`ll-loop validate` does **not** check for
laundering — confirmed: no laundering rule exists in the validator, and `ll-loop validate
rn-implement` currently passes clean. The audit-loop-run check as written reads `on_yes`/`on_no`;
these states use `on_success`/`on_failure`, so the flag arises from the LLM auditor recognizing the
collapsed-route shape, not from a machine gate.)

**Only `on_success == on_failure` is intentional.** The sub-loop's real outcome is passed via a
sidecar file (`subloop_outcome_<ID>.txt`), and the classify states read that file to route — so
collapsing the `done`/`failed` *verdict* is by design. **`on_error` is a different case.** An
`on_error` (sub-loop crash, timeout, context-resolution failure) can occur **before** the child
writes its outcome token. Routing `on_error` into `classify_*` then hits the `|| echo
"IMPLEMENT_FAILED"` fallback, so an infrastructure crash is silently **mislabeled as an
implementation failure** — losing the distinction the operator needs to triage.

This issue therefore does two things: (1) add a self-documenting comment marking
`on_success`/`on_failure` as intentional sidecar routing so the LLM auditor (and humans) recognize
the collapse as by-design, and (2) split `on_error` out to a distinct `record_sub_loop_crash` state
so genuine infrastructure failures are attributed correctly. (1) is documentation-only; (2) is the
recommended structural fix.

## Current Behavior

```yaml
run_remediation:
  loop: rn-remediate
  on_success: classify_remediation
  on_failure: classify_remediation
  on_error: classify_remediation
```

An LLM auditor reading this YAML sees `on_success == on_failure == on_error` all pointing to
`classify_*` and can flag the collapse. There is no inline marker distinguishing intentional
sidecar-based routing from accidental verdict discard, and (for `on_error`) part of the collapse is
in fact a genuine defect.

## Expected Behavior

- `/ll:audit-loop-run rn-implement` does not flag `run_remediation` / `run_decomposition`
  `on_success`/`on_failure` collapse as a structural defect (the inline comment documents it as
  intentional sidecar routing)
- The design intent (sidecar-based routing via `subloop_outcome_<ID>.txt`) is self-documenting in the loop YAML
- Note: `ll-loop validate` has no laundering check, so it is unaffected by this change (no validate
  warning exists to suppress)

## Motivation

This enhancement would:
- Stop false-positive `verdict_laundering` flags in `/ll:audit-loop-run` (the LLM auditor) for states that intentionally use sidecar-based routing — reducing audit noise for operators (`ll-loop validate` has no laundering check, so it is not a source of these warnings)
- Improve infrastructure failure attribution: sub-loop crashes and timeouts are currently laundered as `IMPLEMENT_FAILED`, losing the distinction needed for operator triage
- Make the sidecar routing pattern self-documenting in the loop YAML rather than requiring institutional knowledge of the design intent

## Proposed Solution

### Part 1 — document the intentional `on_success`/`on_failure` collapse

Add a per-state comment so the `done`/`failed` verdict collapse reads as intentional to the LLM
auditor and to humans:

```yaml
run_remediation:
  # on_success == on_failure is intentional: the real outcome is read from
  # subloop_outcome_<ID>.txt by classify_remediation (sidecar routing). on_error is NOT
  # collapsed here — see Part 2.
  loop: rn-remediate
  on_success: classify_remediation
  on_failure: classify_remediation
  on_error: record_sub_loop_crash   # CHANGED — see Part 2
```

Note: there is **no** `verdict_laundering_ok` (or equivalent) suppression flag in `ll-loop validate`
today, and validate does not check for laundering at all, so no machine flag is needed or available.
The laundering signal comes only from the LLM-driven `/ll:audit-loop-run` (Step 8), which the inline
comment addresses. Adding a machine-readable suppression flag to the validator/audit would be a
separate enhancement and is out of scope here.

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

1. Add a clarifying comment to `run_remediation` and `run_decomposition` explaining the sidecar
   routing pattern (`on_success == on_failure` is intentional). No suppression flag — none exists.
2. Add `record_sub_loop_crash` shell state that writes `SUB_LOOP_CRASH` to `failures.txt` (mirror
   the existing `record_failure` state's `$${ID}` escaping and `failures.txt` append idiom)
3. Repoint `run_remediation.on_error` and `run_decomposition.on_error` to `record_sub_loop_crash`
4. Optionally extend the `report` state to tally `sub_loop_crashes` separately from `failed`
5. Run `ll-loop validate rn-implement` and confirm it still passes (no regression; validate has no
   laundering check, so this is a structural sanity check, not a laundering check)

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
- Manual: `ll-loop validate rn-implement` should still pass after the edits (structural sanity check; validate does not check laundering)
- Manual: trigger a sub-loop timeout/crash; verify `failures.txt` records `SUB_LOOP_CRASH` distinct from `IMPLEMENT_FAILED` (Part 2)

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop validate rn-implement` still passes (no structural regression from the new state /
  rerouted `on_error`)
- A future `/ll:audit-loop-run rn-implement` does not flag the `on_success`/`on_failure` collapse as
  a structural defect (the inline comment documents it as intentional sidecar routing)
- A sub-loop crash/timeout (no outcome token written) is recorded as `SUB_LOOP_CRASH` in
  `failures.txt` — distinguishable from a clean `IMPLEMENT_FAILED`/`SCORES_MISSING` outcome
- `on_error` is no longer routed through `classify_*` (so the `|| echo "IMPLEMENT_FAILED"` fallback
  no longer masks infrastructure failures)

## Scope Boundaries

- Part 1 is documentation-only (an inline comment); Part 2 changes routing for the error path only —
  neither alters the happy-path (`on_success`/`on_failure`) runtime behavior
- Does not add a machine-readable laundering-suppression flag to `ll-loop validate` or
  `/ll:audit-loop-run` (none exists today; track that as a separate enhancement)
- Does not modify other loops that may have similar sidecar-routing patterns

## Impact

- **Priority**: P4 — Part 1 (annotation) is cosmetic noise reduction; Part 2 (crash attribution)
  is a low-severity observability fix. Neither blocks the loop's primary function, so P4 holds.
- **Effort**: Small — annotation + one new shell state + repointing two `on_error` routes in one
  file; no Python code changes
- **Risk**: Low — happy-path routing (`on_success`/`on_failure`) is unchanged; only the error path moves,
  from a laundered fallback to an explicit record. Worst case is an extra `failures.txt` line
- **Breaking Change**: No

## Status

**Done** | Created: 2026-06-07 | Completed: 2026-06-07 | Priority: P4

## Resolution

Implemented both parts in `scripts/little_loops/loops/rn-implement.yaml`:

- **Part 1 (documentation).** Added inline comments to `run_remediation` and
  `run_decomposition` marking the `on_success == on_failure` collapse as
  intentional sidecar routing (the real outcome is read from
  `subloop_outcome_<ID>.txt` by the `classify_*` states). The comments explain
  why this is by-design so the `/ll:audit-loop-run` LLM auditor (Step 8) and
  human readers no longer read it as verdict laundering.
- **Part 2 (crash attribution).** Added a `record_sub_loop_crash` shell state
  (mirroring `record_failure`'s `$${ID}` escaping / `failures.txt` append idiom)
  that writes a `SUB_LOOP_CRASH`-tagged line. Repointed both
  `run_remediation.on_error` and `run_decomposition.on_error` to it, so an
  infrastructure crash/timeout (fired before the child writes its outcome token)
  is no longer laundered into `IMPLEMENT_FAILED` / `SIZE_REVIEW_FAILED` by the
  classifier's `|| echo` fallback.
- **Report tally.** Extended the `report` state to count `sub_loop_crashes`
  separately (`grep -c SUB_LOOP_CRASH`) and subtract them from `failed`, so
  `summary.json` distinguishes genuine implementation failures from
  infrastructure crashes.

Verification:
- `ll-loop validate rn-implement` passes clean (25 states, `record_sub_loop_crash`
  present; no laundering check exists in the validator, so no regression).
- `scripts/tests/test_rn_implement.py` — 86 passed (updated the two `on_error`
  route tests + the `test_loop_states_route_to_classifiers`/`test_classifier_states_exist`
  inventory; added `test_record_sub_loop_crash_records_distinct_marker` and
  `test_report_tallies_sub_loop_crashes_distinctly`).
- Broader loop suites (`test_builtin_loops`, `test_fsm_validation`, `test_rn_build`)
  — 893 passed. `ruff check` clean.

## Session Log
- `/ll:manage-issue` - 2026-06-07T22:06:00 - `7341848a-d8b4-4e35-a711-40293ac5fb20.jsonl`
- `/ll:ready-issue` - 2026-06-07T22:00:31 - `0be0c1f1-5dbb-40f4-9959-1389fdf69b92.jsonl`
- `/ll:format-issue` - 2026-06-07T20:55:24 - `a5956258-4fc8-4113-91bc-8549df3f7bb9.jsonl`
- `/ll:format-issue` - 2026-06-07T20:47:20 - `57f27ab7-f753-43a9-be87-54b2970f859d.jsonl`
