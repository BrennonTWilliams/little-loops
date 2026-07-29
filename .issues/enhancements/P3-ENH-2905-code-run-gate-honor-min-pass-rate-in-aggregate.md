---
id: ENH-2905
type: ENH
priority: P3
status: open
captured_at: '2026-07-29T00:00:00Z'
discovered_date: 2026-07-29
discovered_by: manual
relates_to:
- BUG-2902
- BUG-2894
- ENH-2896
depends_on:
- BUG-2894
---

# ENH-2905: code-run-gate's `aggregate` should honor `min_pass_rate` independently of exit code

## Summary

[BUG-2902] fixes `code-run-gate`'s `aggregate` state
(`scripts/little_loops/loops/oracles/code-run-gate.yaml:366`) so a non-zero
test-command exit code is finally detected (it appends `exit_code=$RC` into
`test-results.txt`, matching `build.txt`/`typecheck.txt`/`lint.txt`). That fix
covers the common case — a failing suite that exits non-zero.

It deliberately does **not** make `aggregate` read the `pass_rate=` line that
`run_test` already writes to the sidecar. The `min_pass_rate` parameter the
loop advertises (lines 40-45) therefore remains decorative: a test runner that
exits 0 while reporting a pass rate below the configured threshold (e.g. a
wrapper script that swallows the real exit status, or a `min_pass_rate` set
below 1.0 to tolerate some flakiness) will still yield `GATE_PASS`.

This issue tracks implementing that second detector.

> **SCOPE EXPANDED 2026-07-29** (pre-implementation review). `min_pass_rate` is
> inert in **two** places, not one. Beyond `aggregate`, `run_test`'s own
> evaluator hardcodes `target: 0.95` — grepping the loop,
> `${context.min_pass_rate}` is *never referenced anywhere*: it is only declared
> (line 40), defaulted (line 81), and described in two comments (lines 204, 207)
> that claim it is wired up. Fixing only `aggregate` would leave the parameter
> half-decorative and both comments still inaccurate. The `target:` wiring is
> now in scope here.
>
> Also corrected: **Implementation step 1 as originally written cannot produce a
> failing test.** See the note under Implementation Steps.

## Current Behavior

`aggregate` only greps sidecar files for `^exit_code=[1-9]`. It never parses or
compares the `pass_rate=<n>` line `run_test` writes.

`run_test`'s evaluator (`code-run-gate.yaml:243-247`) compares against a literal:

```yaml
    evaluate:
      type: output_numeric
      key: pass_rate
      operator: "ge"
      target: 0.95        # <-- literal, not ${context.min_pass_rate}
```

So `min_pass_rate` is accepted as a context parameter and has no effect on
either the per-state verdict or the aggregate verdict. Setting it to `0.80` or
`1.0` changes nothing.

## Expected Behavior

`aggregate` parses the `pass_rate=` line from `test-results.txt` (via
`grep '^pass_rate='`, not the fragile `tail -1` BUG-2902 replaces it with) and
sets `ANY_FAIL` when the parsed value is below `${context.min_pass_rate}`, in
addition to the exit-code check. The SKIP path (`SKIP test_cmd=null`) must
remain unaffected — `aggregate`'s existing `case "$FIRST" in SKIP*)` branch
short-circuits before either detector runs.

## Root Cause

Sidecar-write/consumer asymmetry, same root as BUG-2902, but for the
`pass_rate` field specifically rather than `exit_code`. Never implemented
because BUG-2902/BUG-2894 (and the earlier mis-diagnosed version of BUG-2902)
were focused on the exit-code half; this is the leftover second half, split out
so BUG-2902 could land the higher-value, lower-risk fix first.

## Proposed Solution

1. In `aggregate`, alongside the existing exit-code grep loop, add a
   `pass_rate` check specific to `test-results.txt`:
   - Extract the value with `grep '^pass_rate=' test-results.txt | cut -d= -f2`
     (or equivalent).
   - Compare against `${context.min_pass_rate}` using `python3 -c` (POSIX `[ ]`
     has no float comparison — flagged as a risk in BUG-2902's Open Questions).
   - Set `ANY_FAIL=true` if below threshold.
2. Skip the check entirely when the sidecar's first line is `SKIP*` (no test
   command configured) — mirror the existing per-file SKIP handling.
3. Skip the check when no `pass_rate=` line is present (e.g. a test runner that
   doesn't report one) rather than treating absence as a failure.
4. Wire `run_test`'s evaluator to the parameter:
   `target: "${context.min_pass_rate}"` in place of the literal `0.95`.
   **Verify this first** — `EvaluateConfig.target` is typed
   `int | float | str | None` (`scripts/little_loops/fsm/schema.py:95`) and is
   passed through to `evaluate()` from the raw config; whether an interpolated
   `"${context.min_pass_rate}"` reaches `evaluate_output_numeric` as a number
   rather than the literal string is an open question, not an assumption. If
   `target` turns out not to be interpolated, either add that support or drop
   this sub-step and record the limitation — do not ship a `target:` that
   silently compares against a string.
5. Update the two stale comments (lines 204, 207) that already claim
   `min_pass_rate` is honored.

## Implementation Steps

> **Correction 2026-07-29:** step 1 as previously written could not fail. It
> asked for "a test command that exits 0 but whose `pass_rate` is below
> `min_pass_rate`" — but under `run_test`'s current fallback
> (`RATE="1.0"; [ "$RC" -ne 0 ] && RATE="0.0"`), an exit-0 command *always*
> yields exactly `1.0`. The only path producing a fractional rate is the
> `pytest.json` branch. Step 1 is restated accordingly.
>
> Corollary worth knowing before building this: outside the
> pytest-json-report scenario, the new detector is **fully redundant** with the
> existing exit-code detector, because the fallback already maps non-zero exit
> to `pass_rate=0.0`. That narrows the real value of this issue to
> pytest-json-report runs and exit-status-swallowing wrappers. Do not
> over-build it.

1. Add a test: stage a `pytest.json` with `summary: {total: 10, passed: 6}`
   alongside a test command that exits 0, so `run_test` computes
   `pass_rate=0.6`. With `min_pass_rate` at its 0.95 default this must yield
   `GATE_FAILED`.
2. Add a test: a `pass_rate` at or above `min_pass_rate` (exit 0) still yields
   `GATE_PASS`.
3. Add a test: the SKIP path (no test command) is unaffected by the new
   detector. Note `run_test`'s SKIP branch writes `pass_rate=1.0` into the
   sidecar, so this must be guarded by the `SKIP*` first-line check rather than
   relying on the value.
4. Add a test: `min_pass_rate` set to a non-default value (e.g. `0.5`) actually
   changes the verdict — this is the regression guard for the `target:` wiring
   and would fail on main today.
5. Implement the `aggregate` pass-rate detector and the `target:` wiring per
   Proposed Solution.
6. Confirm `ll-loop validate oracles/code-run-gate` passes.
7. Confirm `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

In scope: making `${context.min_pass_rate}` actually govern the verdict — both
`run_test`'s `target:` (currently the literal `0.95`) and a new pass-rate
detector in `aggregate` — plus the two stale comments that already claim this
works.

Out of scope:

- The `run_test` echo shape, sidecar path quoting, and SKIP-branch `pass_rate`
  key — all [BUG-2894]'s, which lands first.
- The `aggregate` **exit-code** detector — [BUG-2902]'s, already `done`.
- The `on_no`/`on_error` routing split — withdrawn as harmful per BUG-2902's
  Rejected Approach; the converging routing across all five gate states is
  deliberate. Neither this issue nor BUG-2894 should implement it.
- Changing the `0.95` **default**. This issue makes the parameter effective; it
  does not retune it.

## Dependencies

Land [BUG-2894] first. It edits the same `run_test` block (removing the
`pass_rate=pass_rate=` double prefix, quoting the sidecar path, and fixing the
SKIP branch's missing `pass_rate` key) and is a strictly smaller change.

## Impact

- **Severity**: P3 — the common failure mode (non-zero exit) is already fixed
  by BUG-2902; this closes a narrower gap (exit-0-but-below-threshold or
  thresholds below 1.0). The `target:` wiring added in the 2026-07-29 rescope
  is the higher-value half: without it, `min_pass_rate` is a documented
  parameter that provably does nothing.
- **Blast radius**: same as BUG-2902 — `rn-implement`/`rn-remediate`
  delegations and direct `ll-loop run oracles/code-run-gate` callers, only for
  configs that set `min_pass_rate < 1.0` or use exit-status-swallowing test
  wrappers.
- **Risk of fix**: Low-medium — enables a previously-decorative parameter;
  expect it to newly fail runs where `min_pass_rate` was set but never
  actually enforced.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement |
| `.claude/CLAUDE.md` | Loop Authoring rules |

## Session Log
- manual - 2026-07-29 - split from BUG-2902's Open Questions per user request

---

## Status

open
