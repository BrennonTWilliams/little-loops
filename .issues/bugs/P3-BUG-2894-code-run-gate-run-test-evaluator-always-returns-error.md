---
id: BUG-2894
type: BUG
priority: P3
status: open
captured_at: '2026-07-28T22:13:33Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2893
- ENH-2895
- ENH-2896
depends_on:
- ENH-2895
---

# BUG-2894: code-run-gate `run_test` evaluator returns error on every invocation

## Summary

`oracles/code-run-gate.yaml`'s `run_test` state never evaluates its pass-rate threshold.
Two independent defects combine:

1. `evaluate.key: pass_rate` is not a field on `EvaluateConfig` and is silently dropped
   at load time, so `evaluate_output_numeric` parses the whole stdout line.
2. The state's final `echo` double-prefixes the value — it emits
   `exit_code=0 pass_rate=pass_rate=0.99`, because `tail -1` on the results file already
   returns a `pass_rate=`-prefixed line.

The result is a `ValueError` in `float()` and a permanent `verdict="error"`. The
`min_pass_rate` parameter and the `operator: ge` / `target: 0.95` comparison are
entirely inert.

This is currently **benign** only because `on_no` and `on_error` both route to
`run_typecheck` — the loop proceeds, but a test run at 40% pass rate is indistinguishable
from one at 100%.

## Current Behavior

`scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` state:

```yaml
      echo "exit_code=$RC pass_rate=$(tail -1 $${ABS_DIR}/test-results.txt)"
    capture: pass_rate
    evaluate:
      type: output_numeric
      key: pass_rate          # <-- silently dropped by EvaluateConfig.from_dict
      operator: "ge"
      target: 0.95
    on_yes: run_typecheck
    on_no: run_typecheck
    on_error: run_typecheck
```

The preceding shell writes `pass_rate=<rate>` as the last line of
`${ABS_DIR}/test-results.txt`, so `$(tail -1 ...)` expands to `pass_rate=0.99`, giving
stdout `exit_code=0 pass_rate=pass_rate=0.99`.

Consequences:

- `evaluate_output_numeric` → `verdict="error"` on every run.
- The pass-rate gate is unenforced; the oracle's `GATE_PASS`/`GATE_FAILED` verdict does
  not reflect test pass rate at all.
- `capture: pass_rate` captures the malformed blob, not the number, so any downstream
  consumer (notably `aggregate`) reading `${captured.pass_rate.output}` gets a string.
- The loop's `description` block advertises a `min_pass_rate` parameter (lines 40-45)
  that has no effect.

## Expected Behavior

`run_test` extracts the numeric pass rate, compares it to `min_pass_rate` (default 0.95)
with `operator: ge`, and yields `yes`/`no` accordingly. `on_error` fires only on genuine
evaluation failure. The oracle's aggregate verdict reflects whether the test suite
actually met the threshold.

## Motivation

`code-run-gate` is the reusable Tier-1 deterministic oracle wired into `rn-implement` and
`rn-remediate` (FEAT-2551/FEAT-2552). Its entire purpose is to be the trustworthy
non-LLM signal that MR-1 requires as a backstop for LLM-judged states. An oracle whose
test gate silently always errors is a toothless evaluator in exactly the sense
`ll-loop diagnose-evaluators` is designed to catch — the verdict never varies with the
underlying reality.

## Root Cause

Two independent causes:

1. **Silent unknown-key drop** — `EvaluateConfig.from_dict`
   (`scripts/little_loops/fsm/schema.py`) enumerates known fields via `data.get(...)`;
   unknown keys vanish without error or validation warning. See ENH-2896.
2. **Shell double-prefix** — `echo "... pass_rate=$(tail -1 ...)"` where the tailed line
   is itself `pass_rate=<n>`.

Note that cause 1 is shared with BUG-2893; cause 2 is unique to this file. Even if
`key` were implemented (ENH-2895), a `pass_rate=pass_rate=0.99` line would still need
the echo fixed, since the value after the first `=` is not numeric.

## Proposed Solution

Fix the echo regardless of how ENH-2895 is resolved:

```yaml
      RATE_LINE=$(tail -1 "$${ABS_DIR}/test-results.txt")   # pass_rate=<n>
      echo "$${RATE_LINE#pass_rate=}"
```

Then either:

- **With ENH-2895**: keep `key: pass_rate` and echo the labelled line
  (`echo "$RATE_LINE"`), letting the evaluator extract the field.
- **Without ENH-2895**: echo the bare number as above and drop `key:`.

Separately, verify what `aggregate` does with `${captured.pass_rate.*}` and correct it
to consume the numeric value.

## Integration Map

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test`, `aggregate` states
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig`
- `scripts/tests/test_builtin_loops.py` — regression coverage

## Implementation Steps

1. Add a failing test: feed `run_test`'s literal stdout to the evaluator and assert the
   current verdict is `error`.
2. Fix the double-prefix in the final `echo`.
3. Resolve `key:` per ENH-2895 (implement) or drop it (bare number).
4. Trace `${captured.pass_rate.*}` into `aggregate` and fix any consumer expecting a number.
5. Assert `min_pass_rate` is honoured: a run at 0.5 with threshold 0.95 must yield `no`.
6. Consider whether `on_no` and `on_error` should still share `run_typecheck` once the
   gate is live — the shared target is what masked this defect.
7. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: Medium — no incorrect behaviour today (shared routing target), but the
  advertised gate provides no signal, which is worse than an absent gate because
  downstream MR-1 reasoning treats it as a real non-LLM evaluator.
- **Blast radius**: `rn-implement` and `rn-remediate` delegations, plus direct
  `ll-loop run oracles/code-run-gate` callers.
- **Risk of fix**: Low-to-medium — enabling a previously-inert gate may start failing
  runs that silently passed. Worth a deliberate look at step 6.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement; toothless-evaluator taxonomy |
| `docs/ARCHITECTURE.md` | Oracle sub-loop token channel and delegation |
| `.claude/CLAUDE.md` | `ll-loop diagnose-evaluators`; Loop Authoring rules |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-28T22:30:33 - `0c009821-2287-4712-ab12-876baba4cf48.jsonl`
- `/ll:verify-issues` - 2026-07-28T22:25:20 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open
