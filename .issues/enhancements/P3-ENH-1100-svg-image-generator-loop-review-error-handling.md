---
id: ENH-1100
type: ENH
priority: P3
status: completed
discovered_date: 2026-04-13
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-1100: svg-image-generator loop review — add error routing and failure terminal

## Summary

Ran `/ll:review-loop svg-image-generator` to audit the GAN-style SVG harness loop.
Three warnings were identified and all were resolved: missing `on_error` routing in
the `evaluate` and `score` states, and no explicit failure terminal state. The loop
now has full error coverage across its shell and LLM evaluator states.

## Problem

The `svg-image-generator` loop (6 states, max_iterations=20) passed schema validation
but had three quality gaps found during the review skill's QC/FA checks:

**QC-2 — `evaluate` state**: The Playwright screenshot shell state had an `evaluate`
block (`output_contains: CAPTURED`) with `on_yes → score` and `on_no → generate`, but
no `on_error`. A Playwright crash (not just a non-zero exit — a genuine shell failure)
had no defined recovery path.

**QC-2 — `score` state**: The LLM evaluator state had `on_yes → done` and
`on_no → generate` but no `on_error`. A transient LLM call failure left the FSM
with no next step.

**FA-2 — No failure terminal**: All 6 states only included `done` as a terminal.
When the loop hit `max_iterations` on a persistent failure path, it stopped silently
with no signal distinguishable from a timeout — making failure invisible in
`ll-loop history`.

## Solution

Three targeted edits to `scripts/little_loops/loops/svg-image-generator.yaml`:

**1. `evaluate` state — soft fallback:**
```yaml
on_yes: score
on_no: generate
on_error: generate    # added — Playwright crash falls back to LLM-only path
```
Consistent with the loop's existing graceful-degradation design: `evaluate` already
routes `no → generate` so Playwright is not a hard requirement.

**2. `score` state — hard stop on scoring failure:**
```yaml
on_yes: done
on_no: generate
on_error: failed      # added — LLM scoring failure routes to explicit terminal
```
A scoring error is less transient than a screenshot failure, so routing to `failed`
provides a clear signal rather than silently retrying.

**3. `failed` terminal state — added:**
```yaml
failed:
  # HARNESS: Explicit failure terminal — reached when an unrecoverable error occurs
  # (e.g. LLM failure in score state). Provides a clear signal distinct from a
  # max_iterations timeout, making failure mode visible in ll-loop history.
  terminal: true
```

## Validation

`ll-loop validate svg-image-generator` passed after all three changes, reporting
7 states (init, plan, generate, evaluate, score, done, failed).

## Files Changed

- `scripts/little_loops/loops/svg-image-generator.yaml` — `evaluate` state (added `on_error: generate`), `score` state (added `on_error: failed`), new `failed` terminal state
