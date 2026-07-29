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
- BUG-2902
depends_on:
- BUG-2902
---

# BUG-2894: code-run-gate `run_test` evaluator returns error on every invocation

## Summary

> **RESCOPED 2026-07-28** by `/ll:audit-issue-conflicts`. **Cause 1 is fixed on
> main** by commit `e2ea3c56` (ENH-2895), which added `EvaluateConfig.key` and
> wired it into `from_dict`. Verified live against this state's exact stdout:
> `evaluate_output_numeric('exit_code=1 pass_rate=pass_rate=0.40', 'ge', 0.95,
> key='pass_rate')` now returns `verdict='no' value=0.40` — the regex extractor
> takes the **last** match, so it absorbs the double-prefix and the gate
> discriminates correctly.
>
> **The stale `depends_on: ENH-2895` has been dropped** — that issue is `done`.
>
> **DE-SCOPED 2026-07-28** by a second `/ll:audit-issue-conflicts` pass. The
> `on_no`/`on_error` routing split **and** the `${captured.pass_rate.*}` →
> `aggregate` consumer audit are now owned solely by **BUG-2902** (P2). They
> were left duplicated here after BUG-2902 was split out; steps 4 and 6 have
> been removed accordingly.
>
> **What remains in scope:** the cosmetic double-prefix cleanup only — the
> final `echo`'s `pass_rate=pass_rate=` emission and the shape of the
> `capture: pass_rate` value. Both are cosmetic post-`e2ea3c56`, which is why
> this stays P3.

`oracles/code-run-gate.yaml`'s `run_test` state never evaluates its pass-rate threshold.
Two independent defects combine:

1. ~~`evaluate.key: pass_rate` is not a field on `EvaluateConfig` and is silently dropped
   at load time, so `evaluate_output_numeric` parses the whole stdout line.~~
   **FIXED by `e2ea3c56` (ENH-2895).**
2. The state's final `echo` double-prefixes the value — it emits
   `exit_code=0 pass_rate=pass_rate=0.99`, because `tail -1` on the results file already
   returns a `pass_rate=`-prefixed line.

The result is a `ValueError` in `float()` and a permanent `verdict="error"`. The
`min_pass_rate` parameter and the `operator: ge` / `target: 0.95` comparison are
entirely inert.

~~This is currently **benign** only because `on_no` and `on_error` both route to
`run_typecheck`.~~ **No longer true post-`e2ea3c56`**: the evaluator now
discriminates correctly and emits real `no` verdicts, which the shared
`on_no`/`on_error` → `run_typecheck` routing then discards. That routing defect
is **BUG-2902's** and is not addressed here.

## Steps to Reproduce

1. Check out `main`.
2. Run the oracle against a project with a configured `test_cmd`:
   `ll-loop run oracles/code-run-gate --context issue_id=X`
3. Inspect the `run_test` action's stdout in the run's event stream — observe
   `exit_code=0 pass_rate=pass_rate=0.99`, with `pass_rate=` emitted twice.
4. Confirm the cause: `${run_dir}/test-results.txt`'s last line is itself
   `pass_rate=<n>`, and the action's final `echo` prefixes it a second time via
   `pass_rate=$(tail -1 ...)`.
5. Inspect `${captured.pass_rate.output}` — it holds the doubly-prefixed blob
   rather than a clean labelled line.

Note the evaluator itself still returns the correct verdict: `output_numeric`'s
regex takes the **last** match, so it absorbs the double prefix. This is why the
defect is cosmetic and P3 rather than a live wrong answer.

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

ENH-2895 is `done`, so `key: pass_rate` stays and the evaluator extracts the
labelled field. Emit the pass-rate line once, preserving the exit code:

```yaml
      RATE_LINE=$(grep '^pass_rate=' "$${ABS_DIR}/test-results.txt" | tail -1)  # pass_rate=<n>
      echo "exit_code=$RC $${RATE_LINE}"
```

Note this **keeps** `exit_code=$RC` on stdout. An earlier draft of this issue
proposed `echo "$${RATE_LINE#pass_rate=}"`, which strips the label *and* drops
the exit code entirely — wrong on both counts now that `key:` is live and
BUG-2902 depends on the exit code being present.

The `grep '^pass_rate=' | tail -1` form replaces the bare `tail -1` deliberately:
BUG-2902 appends an `exit_code=` line into the same file, which would break a
positional `tail -1` read. Coordinate with that issue's step 3.

An earlier "Without ENH-2895 — echo the bare number and drop `key:`" branch has
been deleted; that issue is closed and the branch is dead.

Verifying what `aggregate` does with the test result is **BUG-2902's** scope, not
this issue's. Note that `aggregate` reads sidecar *files*, not
`${captured.pass_rate.*}` — so the capture's value shape is cosmetic in the
strict sense that no verdict depends on it.

## Integration Map

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` state only
  (the `aggregate` state is BUG-2902's)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig`
- `scripts/tests/test_builtin_loops.py` — regression coverage

## Implementation Steps

1. Add a failing test asserting the final `echo` emits a single-prefixed
   `pass_rate=<n>` (today it emits `pass_rate=pass_rate=<n>`).
2. Fix the double-prefix in the final `echo`.
3. Resolve the `capture: pass_rate` value shape so it holds the labelled line,
   not the malformed blob. **Do not** modify the `aggregate` consumer — that is
   BUG-2902's (see Scope Boundary).
4. Assert the state's own evaluator verdict is honoured: a run at 0.5 with
   threshold 0.95 must yield `no` from `evaluate_output_numeric`. Do **not**
   assert this reaches the aggregate verdict — that path is BUG-2902's.
5. Confirm `python -m pytest scripts/tests/` exits 0.

**Out of scope** (BUG-2902's): the sidecar `exit_code=` write and the `aggregate`
detector. **Out of scope entirely** (withdrawn, see BUG-2902's Rejected
Approach): the `on_no`/`on_error` routing split.

## Impact

- **Severity**: Medium — ~~no incorrect behaviour today (shared routing target), but the
  advertised gate provides no signal~~ **superseded post-`e2ea3c56`**: the gate now
  emits correct `yes`/`no` verdicts, but the shared `on_no`/`on_error` →
  `run_typecheck` routing discards every `no`. The oracle went from
  "toothless but honest" to "discriminating correctly and then throwing the
  answer away" — a behaviour change that shipped on main unreviewed. See
  BUG-2902.
- **Blast radius**: `rn-implement` and `rn-remediate` delegations, plus direct
  `ll-loop run oracles/code-run-gate` callers.
- **Risk of fix**: Low — this issue's remaining scope is cosmetic (echo shape).
  The risky half, enabling a previously-inert gate that may start failing runs
  which silently passed, moved to BUG-2902 along with the routing split.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement; toothless-evaluator taxonomy |
| `docs/ARCHITECTURE.md` | Oracle sub-loop token channel and delegation |
| `.claude/CLAUDE.md` | `ll-loop diagnose-evaluators`; Loop Authoring rules |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-29T00:04:13 - `00aa385f-3c68-486e-aadc-2dadfb4a2e42.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:20:23 - `c53b272d-061d-4930-bc4e-fede59dd7ae2.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T22:30:33 - `0c009821-2287-4712-ab12-876baba4cf48.jsonl`
- `/ll:verify-issues` - 2026-07-28T22:25:20 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Scope Boundary

**Note** (revised 2026-07-29): This issue covers the `run_test` state's
**cosmetic output shape only** — the `pass_rate=pass_rate=` double-prefix in the
final `echo`, and the resulting `capture: pass_rate` value shape.

Related issue [BUG-2902] covers the `run_test` → `aggregate` verdict path (the
missing sidecar `exit_code=` write). Note that BUG-2902 was **rediagnosed** on
2026-07-29: the `on_no`/`on_error` routing split it previously owned has been
withdrawn as harmful, not reassigned — the converging routing is deliberate and
uniform across all five gate states. Neither issue should implement it.

Both issues edit the same `run_test` block, so BUG-2902 (P2) should land first.
They interact directly: BUG-2902 appends an `exit_code=` line to
`test-results.txt`, which breaks the positional `tail -1` pass-rate read this
issue's fix replaces with a `grep '^pass_rate='` extraction.

---

## Status

open
