---
id: BUG-2294
title: openscad-model-generator generate.on_error dead-ends at failed with no diagnostic
type: BUG
priority: P3
status: done
discovered_date: '2026-06-25'
discovered_by: audit-loop-run
captured_at: '2026-06-25T16:49:07Z'
labels:
- loops
- openscad-model-generator
- fsm
- resilience
completed_at: '2026-06-25T16:49:07Z'
---

# BUG-2294: openscad-model-generator generate.on_error dead-ends at failed with no diagnostic

## Summary

In `scripts/little_loops/loops/openscad-model-generator.yaml`, the `generate` state
routed `on_error: failed` — a bare terminal with no breadcrumb. When the generation
prompt subprocess was killed (exit `-9` / SIGKILL, typically an OS out-of-memory kill
on a complex multi-part model) it wrote no `model.scad` and the loop ended at `failed`
with nothing the operator could act on. The render path already routed its failures to
a human-readable `diagnose` state; the generate path did not. This was surfaced by a
loop audit of run `2026-06-25T163529` ("Lowpoly astronaut character"), where `generate`
was SIGKILLed after 61s with zero output and `terminated_by: "signal"`.

## Root Cause

- **File**: `scripts/little_loops/loops/openscad-model-generator.yaml`
- **Anchor**: `generate` state — `on_error: failed`
- **Cause**: Generate-side failures (subprocess kill, transient API error) had no
  diagnostic path. The `diagnose` state existed but its prompt was render-failure-only
  (openscad missing / model does not compile), so even reaching it would have produced
  a misleading render-centric diagnosis for a generate-phase kill.

## Fix

1. `generate.on_error`: `failed` → `diagnose`.
2. Made `diagnose` branch on whether `model.scad` exists:
   - **Missing/empty** → generate-phase failure. Diagnoses the SIGKILL/-9 (OOM) case,
     notes `brief.md` survived for re-run, and flags oversized multi-part briefs as a
     likely cause.
   - **Exists** → original render-phase diagnostics (syntax errors, `OPENSCAD_MISSING`,
     install instructions).

Net effect: a generate-side kill now yields an operator-readable diagnostic artifact
instead of a bare `failed` terminal. No new LLM gates, magic thresholds, or undefined
route targets were added; the change composes with the executor-level
`retryable_exit_codes` mechanism (ENH-2293) if transient codes should later retry
rather than diagnose.

## Rejected Alternatives

An audit doc (`audit-openscad-model-generator-2026-06-25.md`) proposed three heavier
fixes: an LLM `complexity_gate`, a hand-rolled `.gen_retries` backoff counter, and a
`wc -l` brief-size estimator. All three were rejected:

- **Misdiagnosis**: SIGKILL `-9` is an external/OS kill, not proof the model exceeded a
  single-pass budget (which would surface as an API/context error, not signal 9). One
  interrupted run is not a pattern.
- **Broken FSM**: Proposals 1 and 3 route to `generate_multi_pass` / `complexity_gate`
  states that don't exist — applying them as-is fails `ll-loop validate`.
- **Wrong altitude**: OOM/SIGKILL resilience is an executor concern already handled
  generically by ENH-2293 (`retryable_exit_codes` + exit `-9` post-mortem in
  general-task). Per-loop retry counters reinvent it worse and can't fire if the kill
  takes down the executor process itself.

## Verification

- `ll-loop validate openscad-model-generator` → valid (12 states, no dangling routes).

## Acceptance Criteria

- [x] `generate.on_error` routes to a diagnostic state, not a bare terminal.
- [x] `diagnose` distinguishes generate-phase failure (no `model.scad`) from
      render-phase failure (model exists but render failed).
- [x] Loop passes `ll-loop validate`.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-25T16:49:33 - `22da4e09-89f3-40a1-8688-ad111f996aee.jsonl`
