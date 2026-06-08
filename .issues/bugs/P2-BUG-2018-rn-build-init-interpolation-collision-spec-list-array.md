---
id: BUG-2018
title: "rn-build — init fails for every spec due to ${SPEC_LIST[@]} interpolation collision (port regression)"
type: BUG
priority: P2
status: done
parent: EPIC-1811
captured_at: '2026-06-08T00:00:00Z'
completed_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: manual-investigation
size: Small
relates_to:
- BUG-2013
labels:
- loops
- rn-build
- interpolation
- bug
confidence_score: 100
---

# BUG-2018: `rn-build` — `init` fails for every spec due to `${SPEC_LIST[@]}` interpolation collision

## Summary

`rn-build`'s `init` state used an unescaped bash array expansion `"${SPEC_LIST[@]}"`
(`rn-build.yaml:71` and `:102`). The FSM interpolation engine matches **any** `${...}`
and raises `InterpolationError: Invalid variable: ${SPEC_LIST[@]} (expected
namespace.path)` for any `${...}` lacking a `namespace.path` dot. As a result `init`
errored at interpolation time and routed `on_error → failed` **before its shell ever
ran** — so `rn-build` failed instantly (`init → failed`, 1 iteration, 0.0s) for *every*
spec, regardless of contents or path.

A second, compounding defect made the failure totally opaque: the runner surfaced no
reason at all (only `Loop completed: failed`), which is how the bug went unnoticed.

## Current Behavior (before fix)

```
ll-loop run rn-build "PROJECT-SPEC.md" --clear --show-diagrams clean
...
Loop completed: failed (1 iterations, 0.0s)
```

No indication of *why*. Event-stream tracing revealed:

```
action_error  state=init  route=on_error
  error: Invalid variable: ${SPEC_LIST[@]} (expected namespace.path)
```

`init` never executed its shell body, never checked the spec file. `prev_result` and
`captured` were both empty (the on_error route returns before either is set), so the
reason existed *only* in the event stream — which nothing re-surfaced. Under
`--clear --show-diagrams` the alternate screen buffer also wiped all per-state output on
teardown, leaving only the one-line summary. The summary additionally coloured the
`failed` terminal **green** (success colour).

## Steps to Reproduce

1. `ll-loop run rn-build <any-spec.md>` (with or without `--clear --show-diagrams`).
2. Observe `init → failed` in 1 iteration, ~0.0s, with no error reason shown.

## Root Cause

**File**: `scripts/little_loops/loops/rn-build.yaml` (states `init`, `check_structure`)

The interpolation engine (`scripts/little_loops/fsm/interpolation.py:27`,
`VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")`) consumes every `${...}` in a shell
`action:` body. Any match without a `namespace.path` dot raises at
`interpolation.py:246-249`. Bash brace-expansion (`${ARR[@]}`, `${VAR}`, `${VAR:-x}`)
has no dot, so it collides.

The escape mechanism is `$${...}` → literal `${...}` (`interpolation.py:28`).

**Port regression**: `rn-build`'s front half was ported from `greenfield-builder.yaml`,
whose line 31 correctly escapes this as `for S in "$${SPEC_LIST[@]}"; do`. The `$$`
escape was dropped during the port to `rn-build.yaml`, so lines 71 and 102 used the
unescaped form.

Secondary (visibility) root cause in `scripts/little_loops/cli/loop/_helpers.py`
(`run_foreground`): the completion summary never re-surfaced a failing state's output.
On `on_error`/exception routes `prev_result`/`captured` are empty; the only record is
the event stream (`action_error`, non-zero `action_complete`). The alt-screen wipes
live output on teardown, and non-verbose mode never prints per-state stdout inline.

## Expected Behavior

- `init` runs its shell, iterating the comma-split spec list correctly, and reaching the
  genuine `[ ! -f "$S" ]` spec-existence check.
- When any loop fails, the runner surfaces the failing state's reason on the normal
  screen after alt-screen teardown.
- A non-`done` terminal is coloured as failure (orange), not success-green.

## Resolution (implemented)

### Loop fix — `scripts/little_loops/loops/rn-build.yaml`
- `${SPEC_LIST[@]}` → `$${SPEC_LIST[@]}` at lines 71 and 102 (escape the bash array
  expansion so interpolation passes it through literally).

### Harness visibility fix — `scripts/little_loops/cli/loop/_helpers.py`
- Register an event-stream capture in `run_foreground` that records the last
  failure-relevant message (`action_error` reason, or non-zero `action_complete`
  stdout).
- After alt-screen teardown, print a `Failure reason:` block sourcing
  `action_error → failing stdout → result.error`, gated on
  `not _is_success and (_was_alt_screen or not verbose)` (skip the verbose
  non-alt-screen case where the live renderer already echoed it).
- Replace the summary's `terminated_by == "terminal"` green-colour test with an
  `_is_success` predicate (`terminal && final_state == "done"`), so a `failed` terminal
  renders orange.

### Tests — `scripts/tests/test_ll_loop_display.py`
- 7 new tests: failure reason surfaced after alt-screen teardown; surfaced in
  non-verbose without alt-screen; surfaced for an `action_error` (interpolation) route;
  not double-printed in verbose; no block on a `done` terminal; `failed` terminal
  coloured orange not green.

## Verification

- `ll-loop validate rn-build` → valid.
- Missing spec: `init` now reaches the real check and the run prints
  `Failure reason: │ ERROR: Spec file not found: …`.
- Valid (well-formed) spec: `init` advances past interpolation **and** the file check to
  `check_structure` — pipeline unblocked.
- `pytest scripts/tests/test_ll_loop_display.py` → 236 passed (incl. 7 new); broader
  loop/interpolation suites → 487 passed. `ruff` + `ruff format` clean.

## Impact

- **Priority**: P2 — `rn-build` was completely unusable (every invocation failed at
  `init`), and the failure was silent. Self-contained to one loop plus a general runner
  visibility improvement.
- **Effort**: Small — two-character escape on two lines, plus an additive runner change.
- **Risk**: Low — loop fix is a literal-escape; runner change is additive (failure path
  only) and gated to avoid double-printing.
- **Breaking Change**: No.

## Notes / Follow-ups

- The visibility fix is general: any loop's interpolation or shell failure now surfaces a
  reason instead of a bare `failed`. This shifts a whole class of opaque failures left.
- A reference note on the `$${...}` escape requirement was added to project memory to
  prevent re-introduction during future loop ports.

## Status

**Done** | Created: 2026-06-08 | Completed: 2026-06-08

## Session Log
- `hook:posttooluse-status-done` - 2026-06-08T15:36:32 - `f725b177-47f8-4f6b-9f29-4b0af6727c9e.jsonl`
- manual-investigation + fix - 2026-06-08 - rn-build init interpolation collision; runner failure-reason surfacing
