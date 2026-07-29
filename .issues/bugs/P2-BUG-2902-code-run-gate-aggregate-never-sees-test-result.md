---
id: BUG-2902
type: BUG
priority: P2
status: done
captured_at: '2026-07-28T23:25:00Z'
completed_at: '2026-07-29T01:02:05Z'
discovered_date: 2026-07-28
discovered_by: audit-issue-conflicts
relates_to:
- BUG-2894
- ENH-2895
- ENH-2896
- ENH-2905
confidence_score: 98
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 18
---

# BUG-2902: code-run-gate's `aggregate` never sees the test result — a failing suite yields GATE_PASS

> **REDIAGNOSED 2026-07-29.** This issue was originally filed as "the pass-rate
> `no` verdict is discarded by shared `on_no`/`on_error` routing", with a
> proposed fix that routed `on_no` to a new gate-failure state. **That diagnosis
> was wrong and the proposed fix would have been harmful** — see Rejected
> Approach below. The shared routing is deliberate and uniform across all five
> gate states. The real defect is in `aggregate`, and it is strictly worse than
> what was originally described: the oracle cannot fail on test results at all,
> by any mechanism, including today.

## Summary

`aggregate` (`scripts/little_loops/loops/oracles/code-run-gate.yaml:366`) is the
sole owner of the oracle's verdict. It computes `ANY_FAIL` by grepping each
sidecar file for an exit-code line:

```bash
for f in build.txt test-results.txt typecheck.txt lint.txt health.txt; do
  ...
  if grep -q "^exit_code=[1-9]" "$f" 2>/dev/null; then
    ANY_FAIL=true
  fi
```

`run_build`, `run_typecheck`, and `run_lint` each append `exit_code=$RC` **into**
their sidecar file:

```bash
bash -c "$BUILD_CMD" > "$${ABS_DIR}/build.txt" 2>&1
RC=$?
echo "exit_code=$RC" >> "$${ABS_DIR}/build.txt"   # <-- into the file
echo "exit_code=$RC"                              # <-- and to stdout
```

**`run_test` does not.** It appends only `pass_rate=<n>` to `test-results.txt`;
its `exit_code=$RC` goes to stdout alone, which `aggregate` never reads. So
`grep "^exit_code=[1-9]" test-results.txt` never matches, `ANY_FAIL` is never set
by the test gate, and a failing test suite produces `GATE_PASS`.

`pass_rate` is not consulted by `aggregate` either — under any name, at any
threshold. The `min_pass_rate` parameter the loop advertises (lines 40-45) is
therefore *still* inert post-`e2ea3c56`, contrary to what this issue and BUG-2894
previously assumed.

## Steps to Reproduce

1. Check out `main`.
2. Run the oracle against a project whose test suite fails:
   `ll-loop run oracles/code-run-gate --context issue_id=X`
3. Observe `${run_dir}/test-results.txt` — it contains the raw test output plus a
   trailing `pass_rate=0.0` line, and **no `exit_code=` line**.
4. Observe the aggregate verdict is `GATE_PASS`.
5. Contrast with a failing *build*: `build.txt` ends with `exit_code=1`, `grep`
   matches, and the verdict is correctly `GATE_FAILED`.

## Current Behavior

A failing test suite is invisible to the verdict. Build, typecheck, and lint
failures are correctly detected; only the test gate is blind. `GATE_PASS` is
returned to every consumer regardless of test outcome.

## Expected Behavior

`test-results.txt` carries an `exit_code=` line with the same shape its three
sibling gates use, so `aggregate`'s existing grep detects a failing suite without
modification.

**Decided 2026-07-29** (see Open Questions, now resolved): this issue implements
*only* the `exit_code=` sidecar fix. Honoring `min_pass_rate` independently of
exit code is split out to [ENH-2905] and is explicitly out of scope here —
`aggregate` gains no `pass_rate` detector as part of this issue.

The SKIP path must stay unaffected: `run_test` writes `SKIP test_cmd=null` as the
first line when no test command is configured, and `aggregate`'s `case
"$FIRST" in SKIP*)` branch skips the file entirely before reaching the grep.

## Root Cause

Sidecar-write asymmetry. `run_test` was written to emit a pass-rate line rather
than an exit-code line, and `aggregate`'s detector only ever keyed on
`^exit_code=[1-9]`. The two halves were never reconciled. Neither
`ll-loop validate` nor MR-1 can see this: the state *has* a non-LLM evaluator, it
just writes a file whose contract the consumer doesn't share.

## Rejected Approach: splitting `on_no` / `on_error`

The original proposal — route `on_no` to a new gate-failure state — must **not**
be implemented. All five gate states share the same converging routing by design:

| State | `on_yes` / `on_no` / `on_error` | Line |
|---|---|---|
| `run_build` | all → `run_test` | 197-199 |
| `run_test` | all → `run_typecheck` | 247-249 |
| `run_typecheck` | all → `run_lint` | 277-279 |
| `run_lint` | all → `service_health` | 304-306 |
| `service_health` | all → `aggregate` | 362-364 |

`run_build`'s own comment states the rationale:

> All three routing outcomes (on_yes / on_no / on_error) → aggregate so a single
> failed gate still produces an aggregated verdict (no MR-4 partial-route
> dead-end).

The oracle is chain-all-gates-then-aggregate. Short-circuiting `run_test`'s
`on_no` to a failure terminal would skip typecheck, lint, and health entirely,
discarding their diagnostics on exactly the runs where they are most useful, and
would make `run_test` inconsistent with its four siblings for no gain — the
verdict is not derived from routing in this loop.

## Proposed Solution

1. Append the exit code into the sidecar in `run_test`, matching its siblings:

   ```bash
   bash -c "$TEST_CMD" > "$${ABS_DIR}/test-results.txt" 2>&1
   RC=$?
   ...
   echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"
   ```

   Note ordering: the `pass_rate=` line is currently appended after the test
   output and read back via `tail -1`. Appending `exit_code=` after it breaks
   that `tail -1`. Either append `exit_code=` *before* the pass-rate block, or
   replace the `tail -1` read with a `grep '^pass_rate='` extraction. The latter
   is more robust and pairs with BUG-2894's echo cleanup.

2. Leave all five states' routing exactly as-is.

3. Do not touch `aggregate`'s detector logic beyond what fix (1) requires — no
   `pass_rate` parsing. That half is [ENH-2905].

## Open Questions

None — resolved 2026-07-29. This issue implements the `exit_code=` sidecar fix
only; honoring `min_pass_rate` independently of exit code is tracked separately
as [ENH-2905].

## Integration Map

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_test` (sidecar
  write), `aggregate` (detector, only if the pass-rate half is adopted)
- `scripts/tests/test_builtin_loops.py` — regression coverage
- `rn-implement` / `rn-remediate` — downstream delegating loops whose gate
  behaviour changes once test failures are honoured (FEAT-2551/FEAT-2552)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-refine.yaml` — `verify_leaf` state delegates
  per-leaf verification to `loop: oracles/code-run-gate` (`on_success:
  check_leaf_deviation`, `on_failure`/`on_error: check_leaf_repair_budget`).
  This is a third production consumer beyond `rn-implement`/`rn-remediate` not
  previously listed. Today a genuine test failure during a recursive-refine
  leaf never trips `ANY_FAIL`, so `verify_leaf` never routes to
  `check_leaf_repair_budget` on test failure alone — after this fix it will,
  which can newly trigger `revert_leaf_failed` cycles that were previously
  silent. [Agent 1/2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_refine.py::test_verify_leaf_delegates_to_code_run_gate`
  — asserts only static wiring (`state.loop == "oracles/code-run-gate"`), not
  runtime verdict behavior; does not need code changes for this fix, but its
  assumption (leaf-level gate failures are rare) becomes truer once test
  failures are actually detected — worth a read-through, no edit expected.
  [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` § `oracles/code-run-gate` (~line 730-787) —
  describes the oracle's `GATE_PASS`/`GATE_FAILED`/`GATE_SKIP` verdicts and
  lists `test-results.txt` as a sidecar artifact; the text is already
  consistent with the *intended* (post-fix) behavior, so no edit is required,
  but confirm during review that nothing there implies the test gate already
  worked. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — confirmed against current `main` (2026-07-28):_

- Verified the `run_test` state body in the current file matches this issue's
  quoted excerpts exactly: `evaluate.key: pass_rate`, `target: 0.95` hardcoded
  (not `${context.min_pass_rate}` — that inertness is real and correctly
  scoped to [ENH-2905], not this issue), and no `exit_code=` line written to
  `test-results.txt`.
- `test_run_test_key_dispatches_correctly`
  (`scripts/tests/test_builtin_loops.py:10176`) already covers ENH-2895's
  `evaluate.key: pass_rate` dispatch path directly against
  `little_loops.fsm.evaluators.evaluate` — this is a **separate** code path
  from `aggregate`'s own `grep "^exit_code=" test-results.txt` file scan, and
  does not exercise or cover this issue's defect. Confirmed by grep: no
  existing test in `test_builtin_loops.py` asserts `test-results.txt`
  contains an `exit_code=` line, and no existing test drives `aggregate`
  end-to-end with a failing test command to assert `GATE_FAILED`. Both gaps
  match Implementation Steps 1–2 as genuinely unaddressed, not
  already-covered-elsewhere.
- Related existing tests to model new coverage after: `test_aggregate_uses_classify_with_default_route`
  (`test_builtin_loops.py:10124`) and `test_run_states_chain_forward_and_terminate_at_aggregate`
  (`test_builtin_loops.py:10145`) are the nearest structural precedents for
  asserting routing/shape; `test_code_run_gate_oracle_exists`
  (`test_builtin_loops.py:13139`) is the oracle's top-level fixture entry
  point a new end-to-end `GATE_FAILED`-on-test-failure test would extend.

## Implementation Steps

1. Add a failing test: an oracle run whose test command exits non-zero must yield
   `GATE_FAILED`. Confirm it fails against current code.
2. Add a test asserting `test-results.txt` contains an `^exit_code=` line, i.e.
   sidecar-shape parity with `build.txt` / `typecheck.txt` / `lint.txt`.
3. Append `exit_code=$RC` into `test-results.txt`, adjusting the `tail -1`
   pass-rate read so it still resolves (see Proposed Solution step 1).
4. Confirm the SKIP path still yields `GATE_SKIP` and is not caught by the new
   detector.
5. Confirm `aggregate` is otherwise untouched — no `pass_rate` detector added
   (that is [ENH-2905]'s scope, not this issue's).
6. Add a regression test asserting all five gate states retain converging
   routing, so the rejected approach is not reintroduced.
7. Confirm `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P2, arguably P1 — a Tier-1 deterministic oracle returns
  `GATE_PASS` for a project whose test suite is failing. Every consumer relying
  on `code-run-gate` as their MR-1 non-LLM backstop has a test gate that has
  never been able to fail, and still cannot today. This is worse than the
  originally-filed diagnosis, which assumed a correct verdict was merely being
  discarded downstream.
- **Blast radius**: `rn-implement` and `rn-remediate` delegations, plus direct
  `ll-loop run oracles/code-run-gate` callers.
- **Risk of fix**: Medium — this genuinely enables a gate that has never failed a
  run. Expect previously-green automation to start failing where the test suite
  fails. That is the intended behaviour, but it should land deliberately rather
  than as a surprise.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-1 non-LLM evaluator requirement; toothless-evaluator taxonomy |
| `.claude/CLAUDE.md` | `ll-loop diagnose-evaluators`; Loop Authoring rules |

## Session Log
- `/ll:manage-issue` - 2026-07-29T01:01:19 - `ae1640d4-5ac7-48dc-b9b1-559d5c0f88b3.jsonl`
- `/ll:ready-issue` - 2026-07-29T00:56:28 - `86a9d028-05cc-447a-b23c-b439e7234980.jsonl`
- `/ll:confidence-check` - 2026-07-28T00:00:00 - `69c120e8-6353-42c7-8c9e-8854af725fcc.jsonl`
- `/ll:wire-issue` - 2026-07-29T00:54:05 - `f74aa2ac-43ca-4068-bba2-0296d720a971.jsonl`
- `/ll:refine-issue` - 2026-07-29T00:50:01 - `9713cc39-3871-483d-8a84-1cbbd4481f2a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-29T00:04:13 - `00aa385f-3c68-486e-aadc-2dadfb4a2e42.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:25:00 - conflict-resolution split from BUG-2894 step 6

---

## Scope Boundary

**Note** (revised 2026-07-29 after rediagnosis): This issue owns the
**`run_test` → `aggregate` verdict path** — the sidecar `exit_code=` write, and
the `aggregate` detector (including the `pass_rate` Open Question).

The `on_no`/`on_error` routing split this issue previously owned has been
**withdrawn**, not reassigned — see Rejected Approach. No issue should implement
it. The `${captured.pass_rate.*}` consumer audit is likewise moot: `aggregate`
reads sidecar *files*, not `${captured.*}`, so the capture's value shape does not
reach the verdict at all.

Related issue [BUG-2894] owns the cosmetic `pass_rate=pass_rate=` echo
double-prefix and the `capture: pass_rate` value shape. Both issues edit the same
`run_test` block. This issue is P2 and should land first; BUG-2894's echo fix
rebases on top and interacts with this issue's step 3 (the `tail -1` adjustment).

---

## Resolution

Fixed in `run_test` (`scripts/little_loops/loops/oracles/code-run-gate.yaml`):

1. Appended `echo "exit_code=$RC" >> "$${ABS_DIR}/test-results.txt"` after the
   pass-rate block, matching the sidecar shape of `build.txt`/`typecheck.txt`/
   `lint.txt`.
2. Replaced the `tail -1` pass-rate read on the stdout `echo` line with
   `grep '^pass_rate=' ... | tail -1`, so appending the `exit_code=` line
   doesn't break pass-rate extraction (per the Proposed Solution's step-1
   note).
3. `aggregate`'s detector, the SKIP path, and all five gates' converging
   routing were left untouched, as scoped.

Added regression coverage in `scripts/tests/test_builtin_loops.py`
(`TestCodeRunGateOracle`):
- `test_run_test_sidecar_declares_exit_code` — static assertion the action
  writes `exit_code=$RC` into the sidecar.
- `test_run_test_sidecar_exit_code_actually_detects_failure` — runs the real
  `run_test` shell action against a failing `test_cmd` in a tmp dir, then
  reproduces `aggregate`'s exact `grep` detector against the resulting
  sidecar and asserts it fires.
- `test_run_test_sidecar_skip_path_unaffected` — confirms the SKIP path still
  writes no `exit_code=` line.
- `test_run_states_converging_routing_not_regressed` — guards against
  reintroducing the Rejected Approach (on_no/on_error forking away from the
  shared aggregate chain).

`python -m pytest scripts/tests/` — 16949 passed, 42 skipped.

## Status

done
