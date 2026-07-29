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

> **UNBLOCKED / RESCOPED AGAIN 2026-07-29** (pre-implementation review). BUG-2902
> is `done` and **already landed half of this issue's Proposed Solution**. The
> `run_test` action on main now reads:
>
> ```bash
> echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"
> echo "exit_code=$RC pass_rate=$(grep '^pass_rate=' $${ABS_DIR}/test-results.txt | tail -1)"
> ```
>
> So the `tail -1` → `grep '^pass_rate='` swap and the sidecar `exit_code=`
> append are both in. Consequences for this issue:
>
> - `depends_on: BUG-2902` is **dropped** — satisfied; this is ready to implement.
> - The remaining code delta is **deleting one literal `pass_rate=` prefix** from
>   the final `echo`. Nothing else.
> - Two defects not previously captured are folded in below: an **unquoted path**
>   in the surviving `grep`, and the **SKIP branch's** bare `echo "SKIP"`, which
>   makes this issue's stated Expected Behavior unachievable as originally
>   worded.

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

**As of 2026-07-29, post-BUG-2902** — `scripts/little_loops/loops/oracles/code-run-gate.yaml`,
`run_test` state (lines ~239-250):

```yaml
      echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"
      echo "exit_code=$RC pass_rate=$(grep '^pass_rate=' $${ABS_DIR}/test-results.txt | tail -1)"
    capture: pass_rate
    evaluate:
      type: output_numeric
      key: pass_rate          # live since e2ea3c56 (ENH-2895)
      operator: "ge"
      target: 0.95
    on_yes: run_typecheck
    on_no: run_typecheck
    on_error: run_typecheck
```

The `grep` already returns a `pass_rate=`-prefixed line, so the literal
`pass_rate=` in the `echo` prefixes it a second time: stdout is
`exit_code=0 pass_rate=pass_rate=0.99`. (The original `tail -1` form is gone;
only the redundant literal prefix survives.)

Consequences:

- `capture: pass_rate` captures the doubly-prefixed blob rather than a clean
  labelled line. No verdict depends on it — `aggregate` reads sidecar *files*,
  not `${captured.pass_rate.*}` — which is why this is cosmetic and P3.
- The evaluator itself is correct: `output_numeric`'s regex takes the **last**
  match, absorbing the double prefix.

Two further defects in the same block, found during the 2026-07-29 review:

- **Unquoted path.** `grep '^pass_rate=' $${ABS_DIR}/test-results.txt` is
  unquoted and breaks on a `run_dir` containing spaces. Every other path
  reference in this file is quoted; this one was missed when BUG-2902 replaced
  the `tail -1`.
- **SKIP branch emits no `pass_rate` key.** When `test_cmd` is null the action
  `exit 0`s after a bare `echo "SKIP"`. With `key: pass_rate` live, the
  evaluator finds no match and returns `verdict="error"` on *every* skipped
  run. Harmless today (all three routes converge on `run_typecheck`), but it
  contradicts the Expected Behavior below.

## Expected Behavior

`run_test` extracts the numeric pass rate, compares it against the threshold
with `operator: ge`, and yields `yes`/`no` accordingly. The oracle's aggregate
verdict reflects whether the test suite actually met the threshold.

`on_error` should fire only on genuine evaluation failure. **This does not hold
today for the SKIP path** (see above). Pick one when implementing:

- have the SKIP branch emit `echo "SKIP pass_rate=1.0"` so the evaluator has a
  key to extract and returns `yes` (preferred — cheap, and makes the skip
  honest); or
- explicitly document the SKIP path as an accepted `error`-verdict case and
  drop the "only on genuine failure" claim.

Note the threshold itself is currently the hardcoded `target: 0.95`, **not**
`${context.min_pass_rate}` — wiring the parameter through is **ENH-2905's**
scope, not this issue's.

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
labelled field. Emit the pass-rate line once, preserving the exit code, and
quote the path:

```yaml
      RATE_LINE=$(grep '^pass_rate=' "$${ABS_DIR}/test-results.txt" | tail -1)  # pass_rate=<n>
      echo "exit_code=$RC $${RATE_LINE}"
```

That single change fixes both the double prefix (the literal `pass_rate=` is
gone; the label now comes only from the grepped line) and the unquoted path.

Note this **keeps** `exit_code=$RC` on stdout. An earlier draft of this issue
proposed `echo "$${RATE_LINE#pass_rate=}"`, which strips the label *and* drops
the exit code entirely — wrong on both counts now that `key:` is live and
BUG-2902 depends on the exit code being present.

The `grep '^pass_rate=' | tail -1` form (rather than a bare `tail -1`) is
already on main — BUG-2902 landed it when it started appending an `exit_code=`
line to the same file, which would break a positional read. Only the redundant
literal prefix and the missing quotes remain.

Separately, decide the SKIP-branch question raised under Expected Behavior. The
recommended form:

```bash
        echo "SKIP pass_rate=1.0"
```

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
2. Fix the double-prefix in the final `echo`, and quote `"$${ABS_DIR}/test-results.txt"`
   in the surviving `grep`. Add a test covering a `run_dir` path containing a
   space, which the unquoted form silently breaks on.
3. Resolve the SKIP branch: emit `echo "SKIP pass_rate=1.0"` so a skipped gate
   yields `yes` rather than `error`, and assert it. (If instead accepting the
   `error` verdict, update Expected Behavior and skip this step.)
4. Assert the state's own evaluator verdict is honoured: a run at 0.5 with
   threshold 0.95 must yield `no` from `evaluate_output_numeric`. Do **not**
   assert this reaches the aggregate verdict — that path is BUG-2902's (`done`).
5. Confirm `ll-loop validate oracles/code-run-gate` passes.
6. Confirm `python -m pytest scripts/tests/` exits 0.

Note the previous step 3 ("resolve the `capture: pass_rate` value shape") has
been removed as redundant — the capture holds whatever the final `echo` emits,
so step 2 satisfies it automatically.

**Out of scope** (BUG-2902's, now `done`): the sidecar `exit_code=` write and the
`aggregate` exit-code detector. **Out of scope** (ENH-2905's): wiring
`target:` to `${context.min_pass_rate}`, and the `aggregate` pass-rate detector.
**Out of scope entirely** (withdrawn, see BUG-2902's Rejected Approach): the
`on_no`/`on_error` routing split.

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

Both issues edit the same `run_test` block, so BUG-2902 (P2) landed first — it
is now `done`, and in the process it already applied the `grep '^pass_rate='`
extraction this issue had proposed. Only the redundant literal `pass_rate=`
prefix, the unquoted path, and the SKIP-branch key remain.

[ENH-2905] owns the other half of the `min_pass_rate` story: wiring
`run_test`'s hardcoded `target: 0.95` to `${context.min_pass_rate}`, and adding
a pass-rate detector to `aggregate`. It touches the same `evaluate:` block, so
land this issue first (it is a strictly smaller edit).

---

## Status

open
