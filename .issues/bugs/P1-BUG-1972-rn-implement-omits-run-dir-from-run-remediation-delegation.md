---
id: BUG-1972
type: BUG
priority: P1
status: done
title: rn-implement omits run_dir from run_remediation sub-loop delegation
confidence_score: 100
outcome_confidence: 95
score_complexity: 8
score_test_coverage: 15
score_ambiguity: 10
score_change_surface: 8
completed_at: 2026-06-05T22:12:00Z
---

# BUG-1972: rn-implement omits `run_dir` from `run_remediation` sub-loop delegation

## Summary

The `rn-implement` queue orchestrator delegated to the `rn-remediate` sub-loop without
passing `run_dir` in its `with:` block, even though `rn-remediate` references
`${context.run_dir}` in 9 places. The first reference (`verify_scores_persisted`)
crashed with `Path 'run_dir' not found in context`, terminating the remediation
sub-loop at iteration 2 and cascading into a wasted decomposition run and a skip — so
the loop reached its terminal `done` state but implemented/decomposed zero issues.

Discovered via a run audit from a downstream project (run `2026-06-06T024719`, input
ENH-322): readiness 65 < 85, outcome 48 < 75, `{"implemented": 0, "decomposed": 0,
"skipped": 1}`.

## Current Behavior (before fix)

`run_remediation.with` passed only `{issue_id, readiness_threshold, outcome_threshold,
max_remediation_passes}`. The sibling state `run_decomposition` correctly passed
`run_dir: "${captured.run_dir.output}"`, but `run_remediation` did not. On the first
sub-loop action touching `${context.run_dir}`, the FSM raised
`Path 'run_dir' not found in context` and routed to the terminal `failed` state.

Beyond the crash, the missing key also broke the parent's counter coupling:
`rn-remediate` increments `${context.run_dir}/implemented_count.txt` and appends to
`failures.txt` in the **parent's** run directory. Without `run_dir`, even a
crash-free run would have written counts to the wrong location and reported `0`.

## Expected Behavior

`run_remediation` passes the parent run directory so the remediation sub-loop can
persist score snapshots, increment the parent's `implemented_count.txt`, and reach its
proper convergence/routing decision instead of crashing.

## Root Cause

Context-wiring defect in `scripts/little_loops/loops/rn-implement.yaml`,
state `run_remediation`: the `with:` block omitted `run_dir`. Compounded by
`rn-remediate.yaml` not declaring `run_dir` in its `parameters:` block (so the
contract was implicit and unenforced on the child-delegation path).

## Fix

1. **`scripts/little_loops/loops/rn-implement.yaml`** — added
   `run_dir: "${captured.run_dir.output}"` to `run_remediation.with`, matching the
   sibling `run_decomposition` delegation.

2. **`scripts/little_loops/loops/rn-remediate.yaml`** — declared `run_dir` in the
   `parameters:` block (`type: path`, `required: true`), matching the `rn-decompose`
   convention. This makes the required-parameter check in `executor.py:538` enforce
   the contract on the child-delegation path, so a future regression fails loudly at
   validation rather than mid-run.

### Proposals NOT actioned (from the audit)

- **`on_error: skip_issue` on `run_remediation`** — already present in the current
  loop; the audited run was an older forked copy.
- **Fallback `run_dir` default in `verify_scores_persisted`** — deliberately skipped.
  A `:-/tmp/...` default would silently scatter score snapshots and break the parent
  counter coupling. With `run_dir` now contractually guaranteed, fail-loud is correct.

## Verification

- `ll-loop validate rn-implement` → valid.
- `ll-loop validate rn-remediate` → valid.
- Confirmed no standalone regression: `run.py:160-163` injects `run_dir` into context
  before validation for top-level `ll-loop run rn-remediate "<id>"`, and the
  required-parameter check only fires on the child `loop:` delegation path (now
  satisfied by fix #1).

## Affected Files

- `scripts/little_loops/loops/rn-implement.yaml`
- `scripts/little_loops/loops/rn-remediate.yaml`


## Session Log
- `hook:posttooluse-status-done` - 2026-06-06T03:11:27 - `9191964a-4c79-4687-bcb3-51564a9ace83.jsonl`
