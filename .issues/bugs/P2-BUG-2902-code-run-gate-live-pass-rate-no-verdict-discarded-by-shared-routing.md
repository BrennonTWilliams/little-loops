---
id: BUG-2902
type: BUG
priority: P2
status: open
captured_at: '2026-07-28T23:25:00Z'
discovered_date: 2026-07-28
discovered_by: audit-issue-conflicts
relates_to:
- BUG-2894
- ENH-2895
- ENH-2896
---

# BUG-2902: code-run-gate's now-live pass-rate `no` verdict is discarded by shared `on_no`/`on_error` routing

## Summary

Commit `e2ea3c56` (ENH-2895) added `EvaluateConfig.key` and thereby **silently
armed** the previously-inert pass-rate gate in
`scripts/little_loops/loops/oracles/code-run-gate.yaml`'s `run_test` state. The
evaluator now discriminates correctly — but the state's routing was written
during the period when the gate was known-inert:

```yaml
    on_yes: run_typecheck
    on_no: run_typecheck
    on_error: run_typecheck
```

All three verdicts converge on the same successor, so a genuine `no` at pass
rate < 0.95 is computed and then thrown away. The oracle went from *toothless
but honest* to *discriminating correctly and discarding the answer* — arguably
worse, because MR-1 reasoning downstream now treats it as a real, functioning
non-LLM evaluator.

This was split out of BUG-2894 step 6 by `/ll:audit-issue-conflicts` because it
is no longer the speculative "consider whether…" item that issue filed. It is a
live behaviour change already shipped on `main`, unreviewed.

## Steps to Reproduce

1. Check out `main` at or after commit `e2ea3c56`.
2. Inspect the `run_test` state in
   `scripts/little_loops/loops/oracles/code-run-gate.yaml` — observe `on_yes`,
   `on_no`, and `on_error` all name `run_typecheck`.
3. Exercise the evaluator directly with the state's declared config and a
   sub-threshold stdout line:

   ```python
   from little_loops.fsm.evaluators import evaluate_output_numeric
   evaluate_output_numeric(
       'exit_code=1 pass_rate=pass_rate=0.40', 'ge', 0.95, key='pass_rate'
   )
   # -> verdict='no' value=0.40
   ```

4. Observe that the `no` verdict is correct — and that step 2's routing sends it
   to the identical successor as `yes`, so no downstream state can distinguish
   them.

## Current Behavior

Verified live against the evaluator, using this state's exact stdout shape:

```
evaluate_output_numeric('exit_code=0 pass_rate=pass_rate=0.99','ge',0.95,key='pass_rate')
  -> verdict='yes' value=0.99
evaluate_output_numeric('exit_code=1 pass_rate=pass_rate=0.40','ge',0.95,key='pass_rate')
  -> verdict='no'  value=0.40      # <-- correct, and then discarded by routing
evaluate_output_numeric('SKIP','ge',0.95,key='pass_rate')
  -> verdict='error'
```

A test suite at 40% pass rate and one at 99% produce identical loop behaviour and
an identical `GATE_PASS` aggregate verdict.

## Expected Behavior

`on_no` routes to a genuine gate-failure path so a sub-threshold test run is
reflected in the oracle's aggregate verdict.

`on_error` must **stay permissive** and continue to `run_typecheck`: the state's
SKIP path (`echo "SKIP"; exit 0`, used when no test command is configured) yields
`verdict='error'`, so hard-failing on `error` would break every project without a
test command. The two must be separated precisely because they mean different
things now.

## Root Cause

Routing written under the assumption the evaluator was inert, combined with an
enabling change (`e2ea3c56`) that did not audit the routing of the states it
brought to life. The shared `on_no`/`on_error` target is also exactly what masked
BUG-2894 from discovery for as long as it did.

## Proposed Solution

1. Point `on_no` at a gate-failure state that propagates a `GATE_FAILED` verdict
   into `aggregate`.
2. Leave `on_error: run_typecheck` (permissive) and add a comment explaining the
   SKIP-path rationale, so the asymmetry is not "fixed" by a future reader.
3. Verify `aggregate` actually consumes the distinction — per BUG-2894, `capture:
   pass_rate` currently captures a malformed blob rather than the number, so any
   `${captured.pass_rate.*}` consumer needs checking in the same pass.

## Integration Map

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test`,
  `aggregate` states
- `scripts/tests/test_builtin_loops.py` — routing assertions for `run_test`
- `rn-implement` / `rn-remediate` — downstream delegating loops whose gate
  behaviour changes once `no` is honoured (FEAT-2551/FEAT-2552)

## Implementation Steps

1. Add a test asserting `run_test`'s `on_no` and `on_error` are **not** the same
   target, and that `on_error` remains the permissive one.
2. Add the gate-failure successor state and route `on_no` to it.
3. Confirm the SKIP path still proceeds to `run_typecheck`.
4. Assert end-to-end: an oracle run at 0.40 pass rate yields `GATE_FAILED`.
5. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P2 — a Tier-1 deterministic oracle is producing a correct signal
  and discarding it. Every consumer relying on `code-run-gate` as their MR-1
  non-LLM backstop is currently getting a gate that cannot fail on test results.
- **Blast radius**: `rn-implement` and `rn-remediate` delegations, plus direct
  `ll-loop run oracles/code-run-gate` callers.
- **Risk of fix**: Medium — this genuinely enables a gate that has never failed a
  run. Expect previously-green automation to start failing where test pass rate
  is below 0.95. That is the intended behaviour, but it should land deliberately
  rather than as a surprise.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement; toothless-evaluator taxonomy |
| `.claude/CLAUDE.md` | `ll-loop diagnose-evaluators`; Loop Authoring rules |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-29T00:04:13 - `00aa385f-3c68-486e-aadc-2dadfb4a2e42.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:25:00 - conflict-resolution split from BUG-2894 step 6

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue is the **sole owner**
of the `run_test` `on_no`/`on_error` routing split and of the
`${captured.pass_rate.*}` → `aggregate` consumer audit (Proposed Solution step 3
/ Implementation Steps 1-4). Related issue [BUG-2894] previously duplicated both
in its own steps 4 and 6; those have been removed, and BUG-2894 is now scoped to
the cosmetic `pass_rate=pass_rate=` echo double-prefix only.

Both issues edit the same `run_test` block. This issue is P2 and should land
first; BUG-2894's cosmetic echo fix rebases trivially on top.

---

## Status

open
