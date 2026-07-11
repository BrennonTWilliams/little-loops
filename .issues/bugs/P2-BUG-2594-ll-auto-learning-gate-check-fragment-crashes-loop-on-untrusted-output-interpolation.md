---
id: BUG-2594
title: ll_auto_learning_gate_check fragment crashes loop on untrusted ll-auto output interpolation
type: BUG
priority: P2
status: open
captured_at: '2026-07-10T00:00:00Z'
discovered_date: '2026-07-10'
discovered_by: audit-loop-run
source_loop: autodev
source_state: check_learning_gate
relates_to:
- BUG-2595
labels:
- loops
- fsm
- autodev
- rn-remediate
- shell-safety
- learning-gate
---

# BUG-2594: `ll_auto_learning_gate_check` fragment crashes the loop on untrusted ll-auto output interpolation

## Summary

The shared `ll_auto_learning_gate_check` fragment
(`scripts/little_loops/loops/lib/common.yaml`) inlines the captured multi-KB
`ll-auto` output directly into a double-quoted shell `echo`, and supplies **no
`on_error` route**. When `ll-auto`'s output contains shell-breaking characters
(backticks, `$`, unbalanced quotes, code fences — routine in Markdown output),
the interpolated `echo` fails to parse, the shell action exits non-zero for a
*reason unrelated to the gate*, the `output_contains` evaluator returns
`verdict=error`, and — because no `on_error` is defined — the FSM terminates
with `No valid transition`. The loop dies with no `summary.json`, so the run's
real outcome is lost. The fragment is used by both `autodev` and `rn-remediate`.

## Current Behavior

Observed in run `2026-07-11T011831-autodev` (single issue BUG-2588):

1. `implement_current` ran `ll-auto --only BUG-2588`, which halted at
   manage-issue's decision gate and exited 1 (verdict=no). Its output — a
   multi-KB Markdown block full of backticks, `$`, and fenced code — was
   captured as `ll_auto_output`.
2. `implement_current.on_no` routed to `check_learning_gate`.
3. `check_learning_gate` (fragment `ll_auto_learning_gate_check`) ran:
   ```
   if echo "${captured.ll_auto_output.output}" | grep -qF 'LEARNING_GATE_BLOCKED'; then ...
   ```
   The raw capture was substituted into the double-quoted `echo`, breaking shell
   parsing → `action_complete exit=2` with empty output.
4. `evaluate` (`output_contains: GATE_BLOCKED`) returned `verdict=error`.
5. The state has no `on_error` → `loop_complete terminated_by=error error="No
   valid transition" iterations=10`. No `summary.json` was written.

Verbatim from `events.jsonl` (final events):
```
action_complete   exit=2   (empty output)
evaluate          verdict=error
loop_complete     terminated_by=error  error="No valid transition"  iterations=10
```

Fragment source (`lib/common.yaml:337-346`) — note the absence of `on_error`,
and that the fragment's own guidance only requires callers to supply
`on_yes`/`on_no`:
```yaml
  ll_auto_learning_gate_check:
    action_type: shell
    action: |
      if echo "${captured.ll_auto_output.output}" | grep -qF 'LEARNING_GATE_BLOCKED'; then
        echo "GATE_BLOCKED"
      else
        echo "OK"
      fi
    evaluate:
      type: output_contains
      pattern: "GATE_BLOCKED"
```

## Expected Behavior

A shell fault while scanning `ll-auto` output must never terminate the loop, and
the gate detection must not depend on interpolating untrusted capture text into
a shell command string:

1. The gate check reads `ll-auto` output from a **file** rather than an inlined
   interpolation, so arbitrary output content cannot break shell parsing.
2. The fragment (or every caller) defines an `on_error` route so a shell fault
   degrades to the next check (`check_impl_auth`) instead of `No valid
   transition`.

## Root Cause

- **File**: `scripts/little_loops/loops/lib/common.yaml`
- **Anchor**: fragment `ll_auto_learning_gate_check` (and its callers
  `autodev.yaml:check_learning_gate`, `rn-remediate.yaml`)
- **Cause**: `${captured.ll_auto_output.output}` is textually substituted into a
  double-quoted `echo` before shell execution. `ll-auto`'s Markdown output
  routinely contains backticks, `$`, and quotes that break the shell, producing
  a non-gate exit code. The `output_contains` evaluator maps that to
  `verdict=error`, and the fragment defines no `on_error`, so the FSM has no
  valid transition and dies.

## Steps to Reproduce

1. Run `autodev` (or `rn-remediate`) on an issue where `ll-auto --only <ID>`
   exits non-zero and prints Markdown containing backticks/`$`/quotes (e.g. a
   decision-gate halt, which emits a fenced "To clear the gate" block).
2. Observe `check_learning_gate` `action_complete exit=2` with empty output.
3. Observe `evaluate verdict=error`, then `loop_complete terminated_by=error
   error="No valid transition"`, and no `summary.json`.

## Proposed Solution

Do not route the multi-KB capture through a shell string at all. Have the
`ll-auto` call site tee stdout to a run-dir file, and have the gate `grep` that
file:

```yaml
# implement_current (and rn-remediate's ll-auto state): tee output to a file
    action: |
      ...
      ll-auto --only "$CURRENT" $SKIP_FLAG 2>&1 | tee "${context.run_dir}/ll_auto_last.txt"
      exit ${PIPESTATUS[0]}
```

```yaml
# ll_auto_learning_gate_check fragment: grep the file, add on_error
    action: |
      if grep -qF 'LEARNING_GATE_BLOCKED' "${context.run_dir}/ll_auto_last.txt" 2>/dev/null; then
        echo "GATE_BLOCKED"
      else
        echo "OK"
      fi
    evaluate:
      type: output_contains
      pattern: "GATE_BLOCKED"
```

Additionally, require `on_error` on every state that uses this fragment (route
to the next check, e.g. `check_impl_auth`), and update the fragment's
`description` contract to state that callers MUST supply `on_error`. Consider a
`ll-loop validate` rule flagging any `output_contains`/`exit_code` state that
interpolates a `${captured.*.output}` value into a shell string without an
`on_error` route.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — `ll_auto_learning_gate_check`
  fragment (grep a file; document `on_error` requirement)
- `scripts/little_loops/loops/autodev.yaml` — `implement_current` (tee output),
  `check_learning_gate` (add `on_error: check_impl_auth`)
- `scripts/little_loops/loops/rn-remediate.yaml` — matching `ll-auto` call site
  + learning-gate state

### Dependent Files (Callers/Importers)
- `grep -rln ll_auto_learning_gate_check scripts/little_loops/loops/` →
  `autodev.yaml`, `rn-remediate.yaml` (both affected)

### Similar Patterns
- `ll_auto_auth_check` fragment (`check_impl_auth`) and any other state reading
  `${captured.ll_auto_output.output}` via inlined shell — audit for the same
  interpolation hazard.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a case feeding `ll-auto` output
  containing backticks/`$`/quotes through the gate and asserting the loop does
  not terminate with `No valid transition`.
- FSM validation test if a lint rule is added.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — learning-gate section (note the
  file-based, non-interpolating pattern).

### Configuration
- N/A

## Motivation

This defect silently destroys run outcomes: the loop crashes before writing
`summary.json`, so an operator (or `audit-loop-run`) sees only `No valid
transition` with no honest failure record. Because the trigger — non-zero
`ll-auto` exit with Markdown output — is common (every decision-gate halt,
learning-gate block, or implementation error prints fenced Markdown), the crash
is easy to hit, and it affects two production loops via the shared fragment.

## Impact

- **Priority**: P2 — crashes the loop and discards the run summary on a common
  input (any `ll-auto` non-zero exit whose output contains shell metacharacters);
  shared across `autodev` and `rn-remediate`. Borderline P1 given the loss of
  outcome data, but downstream issue state is not corrupted.
- **Effort**: Small — file-based grep + `on_error` route; mirrors existing
  run-dir file patterns already used in the loop.
- **Risk**: Low — the fix removes an interpolation hazard and adds a strictly
  safer route; behavior on the happy path is unchanged.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-10 | Priority: P2
