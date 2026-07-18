---
id: BUG-2662
type: BUG
priority: P2
status: done
captured_at: '2026-07-18T00:55:49Z'
completed_at: '2026-07-18T00:55:49Z'
discovered_date: 2026-07-18
discovered_by: manage-issue
discovered_source: rn-implement run rn-implement-20260717T165621
relates_to:
- BUG-2649
decision_needed: false
confidence_score: 96
outcome_confidence: 88
score_complexity: 6
score_test_coverage: 25
score_ambiguity: 8
score_change_surface: 8
size: Small
labels: loops, fsm, oracles, false-negative, gate
parent: EPIC-2457
---

# BUG-2662: code-run-gate interpolation crash falsely tags committed work GATE_FAILED_INFRA

## Summary

`oracles/code-run-gate.yaml` `resolve_commands` referenced each of the six
`*_cmd` override parameters **twice** — with `:default=` on the bash guard but
**not** on the assignment RHS:

```bash
[ -n "${context.build_cmd:default=}" ] && BUILD_CMD="${context.build_cmd}"
```

The FSM interpolates the **entire** action string *before* bash runs, so the
bash `&&` short-circuit never protects the RHS. When a caller omits the `*_cmd`
overrides — which `rn-remediate`'s `run_code_gate` always does, since it binds
only `issue_id` / `run_dir` / `min_pass_rate` and expects the oracle to resolve
commands from `.ll/ll-config.json` — the unguarded `${context.build_cmd}` raised
`InterpolationError: Path 'build_cmd' not found in context`. The child FSM
terminated with an `error` verdict, `record_gate_error` caught it, and the gate
was tagged **`GATE_FAILED_INFRA`**.

This was **100% deterministic for every gate-reaching issue** and had been latent
since the oracle shipped (FEAT-2551, 2026-07-08): existing tests only exercised
the override path (all commands supplied), never the config-resolution path
`rn-remediate` uses in production.

## Current Behavior

In run `rn-implement-20260717T165621` (5 issues: ENH-2464/2465/2466/2497/2511),
both issues that reached the gate — **ENH-2497** and **ENH-2511** — were tagged
`GATE_FAILED_INFRA` and recorded in `failures.txt`, at the *exact second* their
inner `ll-auto` run reported the work committed, the full suite green (15197
passed), and the issue set to `done`. The gate crashed *after* the work was
already landed (`cfe6a938`, `9b0181a4`) and merely mislabeled it. No
`code-run-gate` run dir and no `commands.json` were ever written — proof the
crash occurred in the first state before any test ran (not a test-timeout).

## Expected Behavior

When `run_code_gate` is invoked without `*_cmd` overrides, `resolve_commands`
resolves the command matrix from `.ll/ll-config.json` and proceeds to run the
gate. Absent optional parameters interpolate to empty, not a crash. A gate that
genuinely fails tests yields `GATE_FAILED`; only a true infrastructure crash
yields `GATE_FAILED_INFRA`.

## Steps to Reproduce

```python
from pathlib import Path
from little_loops.fsm.validation import load_and_validate
from little_loops.fsm.interpolation import interpolate, InterpolationContext
fsm, _ = load_and_validate(Path("scripts/little_loops/loops/oracles/code-run-gate.yaml"))
action = fsm.states["resolve_commands"].action
ctx = InterpolationContext(
    context={**fsm.context, "issue_id": "ENH-1", "run_dir": "/t", "min_pass_rate": 0.95},
    captured={}, prev=None)
interpolate(action, ctx)   # pre-fix: InterpolationError: Path 'build_cmd' not found in context
```

## Root Cause

The FSM interpolates a `shell` state's whole action string (comments included)
before handing it to bash — see [reference: FSM action interpolated before bash].
Two authoring gotchas fall out of this and both bit here:

1. **Bash guards do not protect interpolation.** `[ -n "${x:default=}" ] &&
   VAR="${x}"` still crashes when `x` is absent, because the RHS `${x}` is
   resolved at interpolation time regardless of the `&&`. Both references need
   `:default=`.
2. **`${...}` in a comment is also interpolated** (surfaced while fixing: an
   explanatory comment containing a literal `${context.build_cmd}` — and later a
   bare `${...}` placeholder → empty namespace — re-crashed the state).

The `on_error → record_gate_error → GATE_FAILED_INFRA` path is *correct* for a
real infra crash; the defect was that a benign missing-override was being turned
into an infra crash.

## Resolution

**Changed:**
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — added `:default=` to
  all six `*_cmd` assignment RHS references in `resolve_commands`; added an
  authoring-note comment (written without any literal `${` to avoid
  self-interpolation).
- `scripts/tests/test_builtin_loops.py` — new `TestCodeRunGateOptionalParams`
  with two cases: (a) config-resolution path (no `*_cmd` bound) interpolates
  cleanly — the exact regression; (b) override path still renders
  `BUILD_CMD="make build"`. Prior tests only covered (b), which is why this
  regressed silently.

**Verified:** reproduction now passes both paths; `ll-loop validate
oracles/code-run-gate` clean; 1519 passed across
`test_builtin_loops.py` + `test_rn_remediate.py` + `test_rn_implement.py`; ruff
clean.

## Impact

Any `rn-implement` / `rn-remediate` run relying on config-resolved commands (the
default; no `*_cmd` overrides) had its code-run gate crash on the *first* state,
turning every gate-reaching issue into a false `GATE_FAILED_INFRA`. Operators
reading `failures.txt` / `summary.json` would see committed, test-green work
reported as failed — eroding trust in the loop's outcome accounting and masking
whether the gate ever actually ran (it never did). Latent since 2026-07-08
(FEAT-2551). Fix is low-risk (add `:default=` to six RHS refs) and restores the
gate to actually executing the build/test/typecheck/lint matrix.

## Related findings (this session, not part of this fix)

- **ENH-2497 / ENH-2511 were never broken** — they were implemented, tested, and
  committed; the `failures.txt` / summary `gate_failed_infra: 2` tallies are
  false negatives caused by this bug. Their `status: done` is accurate.
- **ENH-2466** genuinely did not implement, but *not* due to a code fault: it
  carries `decision_needed: true` with an enumerable Approach A/B/C producer-wiring
  fork and fast-failed (~3 min) at the decision gate before reaching the code-run
  gate. The outcome was laundered into the generic `failed` / `IMPLEMENT_FAILED`
  bucket rather than surfacing as "needs decision." Remedy: `/ll:decide-issue
  ENH-2466` (recommendation B+C) then re-run. A separate reporting-clarity
  follow-up (decision-blocked issues counting as `failed`) may be worth filing.
- **ENH-2464 / ENH-2465** deferred: remediation scores did not converge (Δ0
  across passes) and decomposition declined to split — parked as un-actionable by
  automation, awaiting a human refinement pass.

## Acceptance Criteria

- [x] `resolve_commands` interpolates without a crash when no `*_cmd` overrides
  are bound (config-resolution path).
- [x] The `*_cmd` override path still applies caller-supplied commands.
- [x] Regression test covering the no-override path added and passing.
- [x] `ll-loop validate oracles/code-run-gate` reports no errors.
- [x] Loop test suite green (`test_builtin_loops`, `test_rn_remediate`,
  `test_rn_implement`).

## References

- Run: `.loops/runs/rn-implement-20260717T165621/` (`failures.txt`,
  `summary.json` `gate_failed_infra: 2`)
- Captured error: `.loops/.history/2026-07-17T215621-rn-implement/state.json`
  → `captured.run_remediation.run_code_gate.error`
- Emitter: `scripts/little_loops/loops/rn-remediate.yaml:572` (`record_gate_error`)
- Sub-loop launch / on_error routing: `scripts/little_loops/fsm/executor.py:741-962`

## Status

Done — fixed and verified 2026-07-18. Not yet committed at time of writing
(working tree carries the oracle fix + test alongside pre-existing `.issues/`
edits).

## Session Log
- `hook:posttooluse-status-done` - 2026-07-18T00:57:06 - `d3bcbabe-914d-4e6b-a59d-f82774366780.jsonl`

- 2026-07-18 — Diagnosed rn-implement run `rn-implement-20260717T165621`.
  Reconciled the misleading "Loop completed: done" banner: 0 clean loop
  successes, but 2 issues (ENH-2497, ENH-2511) actually implemented + committed
  and falsely gate-flagged, 1 genuine needs-decision (ENH-2466), 2 deferred
  (ENH-2464/2465). Root-caused `GATE_FAILED_INFRA` to the double-reference
  interpolation crash in `code-run-gate.yaml resolve_commands`. Applied the
  `:default=` fix, added `TestCodeRunGateOptionalParams`, verified (1519 passed,
  ruff clean, loop validates). Recorded the "FSM interpolates action before bash"
  gotcha to memory.
