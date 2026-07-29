---
id: ENH-2905
type: ENH
priority: P3
status: done
captured_at: '2026-07-29T00:00:00Z'
completed_at: '2026-07-29T03:36:54Z'
discovered_date: 2026-07-29
discovered_by: manual
relates_to:
- BUG-2902
- BUG-2894
- ENH-2896
depends_on:
- BUG-2894
confidence_score: 100
outcome_confidence: 96
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 4's open question is resolved — interpolation works.** Traced the
  exact code path: `EvaluateConfig.target` (`scripts/little_loops/fsm/schema.py:95`,
  typed `int | float | str | None`) passes an unresolved
  `"${context.min_pass_rate}"` string through `from_dict` unchanged. The
  `output_numeric` branch of `evaluate()`
  (`scripts/little_loops/fsm/evaluators.py:1849-1861`) then does
  `resolved = interpolate(config.target, context)` followed by
  `numeric_target = float(resolved)` before calling `evaluate_output_numeric`.
  This is a dedicated per-field lazy-interpolation step inside the evaluator
  dispatcher itself (distinct from the whole-action-string interpolation pass
  the executor runs on shell `action:` bodies — see
  `[[reference_fsm_action_interpolated_before_bash]]`). So
  `target: "${context.min_pass_rate}"` (quoted YAML string) will correctly
  resolve to a float at evaluation time — sub-step 4 can be implemented
  directly, not gated behind further investigation.
- **Direct precedent for this exact pattern already exists**: `rn-build.yaml:1061`
  uses `target: "${context.min_acceptance_pass_rate}"` on an `output_numeric`
  evaluator — same shape as what step 4 proposes here. Other precedents:
  `rn-remediate.yaml:899`, `canvas-sketch-generator.yaml:322`,
  `test-coverage-improvement.yaml:81`, `dataset-curation.yaml:88`.
- **Confirmed exact current line numbers** (file:
  `scripts/little_loops/loops/oracles/code-run-gate.yaml`, current as of this
  refine pass):
  - `min_pass_rate` parameter declaration: lines 40-45; context default
    (`min_pass_rate: 0.95`): line 81.
  - Stale comment claiming the operator is honored: lines 202-204 (state
    comment) and 205-208 (`description:` field) — both describe intended
    behavior that doesn't match the literal on line 248.
  - `run_test`'s hardcoded evaluator: lines 244-248, target literal is on
    line 248 specifically (`target: 0.95`).
  - `run_test`'s existing `pass_rate=` sidecar write (already correct,
    BUG-2894 fixed the double-prefix): line 238 (fallback) / lines 226-234
    (pytest.json branch) / line 241 (`RATE_LINE` read-back, unused for
    control flow).
  - `aggregate`'s per-sidecar-file loop: lines 393-407; the existing
    `exit_code=[1-9]` grep is line 401; a `pass_rate` check on
    `test-results.txt` needs to sit in this same loop, scoped only to that
    filename (the other four sidecars — `build.txt`, `typecheck.txt`,
    `lint.txt`, `health.txt` — never write a `pass_rate=` line, so an
    unscoped grep would silently no-op on them, which is harmless but wasted
    work; scoping to `test-results.txt` is still cleaner and matches the
    issue's Proposed Solution).
- **No existing shared helper for `key=value` sidecar parsing** — every state
  that reads one hand-rolls `grep '^key=' file | tail -1` inline (e.g.
  `run_test` line 241). There's nothing to reuse; the proposed
  `grep '^pass_rate=' test-results.txt | cut -d= -f2` in `aggregate` will be a
  new, self-contained snippet consistent with this file's existing style.
- **No existing example of a raw `python3 -c` float-threshold *comparison*
  used for pass/fail branching in bash** — every other pass-rate-vs-threshold
  check in this codebase routes through the FSM's `output_numeric` evaluator
  rather than an inline bash/python conditional (e.g. `rl-coding-agent.yaml:86`
  uses `python3 -c` only for clamping a value, not for a pass/fail decision).
  The `aggregate` state is a plain shell action with no `evaluate:` gate
  mid-loop, so the issue's own Proposed Solution (compare via `python3 -c` and
  set `ANY_FAIL=true`) is the only viable approach here — flagging this as a
  deliberate, first-of-its-kind pattern in this file rather than an existing
  convention to copy.
- **Test file to extend**: `scripts/tests/test_builtin_loops.py`, class
  `TestCodeRunGateOracle` (lines ~10002-10429). Relevant existing tests to
  model the four new tests after:
  - `test_run_test_sidecar_exit_code_actually_detects_failure` (~line 10218)
    — the closest existing shape: extracts the real `run_test`/`aggregate`
    action strings from the parsed YAML, de-escapes `$${` → `${`, substitutes
    `${context.run_dir}`, and runs via `subprocess.run(["bash", "-c", ...])`
    against a staged sidecar directory. The four new tests in this issue's
    Implementation Steps should follow this exact harness pattern rather than
    inventing a new one.
  - `test_run_test_sidecar_skip_path_unaffected` (~line 10266) — SKIP-path
    staging pattern to reuse for Implementation Step 3.
  - `test_oracle_min_pass_rate_has_default` (~line 13326) and
    `test_rn_remediate_min_pass_rate_default_is_one` (~line 13360) — existing
    `min_pass_rate` default-wiring assertions; a non-default-value regression
    test (Implementation Step 4) is a natural sibling to these.
- **Downstream blast radius, concretely**: `rn-implement.yaml`, `rn-remediate.yaml`,
  and `rn-refine.yaml` (its `verify_leaf` state) all delegate to
  `loop: oracles/code-run-gate` — these are the callers that will newly see
  `GATE_FAILED` for pytest-json-report runs with fractional pass rates once
  this lands, consistent with the issue's existing Impact section.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:740` — the `min_pass_rate` parameter table row for
  `oracles/code-run-gate` currently describes only `run_test`'s
  `output_numeric` evaluator ("Pass-rate threshold for `run_test`'s
  `output_numeric` evaluator"). Once this issue lands, the parameter also
  governs `aggregate`'s independent detector — tighten the wording so it
  doesn't undersell the fix.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py:2079-2082` — `test_run_code_gate_has_with_bindings`'s
  docstring asserts "The oracle's evaluator target is hardcoded 0.95; the
  binding is passed for forward-compatibility and per-issue override." This
  becomes stale prose once `run_test`'s `target:` is wired to
  `${context.min_pass_rate}` (Implementation Step 5) — the binding is no
  longer forward-compatibility-only, it's live. Update the docstring; the
  assertions themselves don't need to change.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/loops.md:740` — tighten the `min_pass_rate`
   parameter description to cover `aggregate`'s new detector, not just
   `run_test`'s evaluator.
9. Update the stale docstring in
   `test_rn_remediate.py::test_run_code_gate_has_with_bindings` (~lines
   2079-2082) — it currently claims the oracle's evaluator target is
   hardcoded; this issue makes that no longer true.

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
- `/ll:manage-issue` - 2026-07-29T03:36:26 - `38399bf0-562e-4769-a6ae-87bf16503216.jsonl`
- `/ll:ready-issue` - 2026-07-29T03:29:17 - `fc2fa33f-9188-49d7-a7b0-f6181a446a47.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `4c417210-a37e-48b8-a806-88c6bfb984d0.jsonl`
- `/ll:wire-issue` - 2026-07-29T03:26:30 - `614ea9f5-f4f0-404d-abfe-2eb7c4fd5aef.jsonl`
- `/ll:refine-issue` - 2026-07-29T03:21:02 - `14425db7-0a90-4da0-a21e-2434d0f81fee.jsonl`
- manual - 2026-07-29 - split from BUG-2902's Open Questions per user request

---

## Status

open
