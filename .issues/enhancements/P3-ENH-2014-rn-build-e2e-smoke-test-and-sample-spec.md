---
id: ENH-2014
title: "rn-build \u2014 E2E smoke test and sample spec for integration validation"
type: ENH
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-08T01:29:25Z'
completed_at: '2026-06-08T02:49:03Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Medium
blocked_by:
- FEAT-1992
- ENH-2012
relates_to:
- FEAT-1990
- FEAT-1992
- ENH-2012
labels:
- loops
- testing
- rn-build
confidence_score: 96
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 25
---

# ENH-2014: `rn-build` — E2E smoke test and sample spec for integration validation

## Summary

FEAT-1992's acceptance criteria required: *"End-to-end smoke: `ll-loop run rn-build
specs/sample.md` completes with harness eval exit 0 and no `eval-driven-development`
in the dispatch log."* That test was never run — the `specs/` directory does not
exist and no sample spec was created. `rn-build` is structurally validated by
`test_rn_build.py` but has never been exercised end-to-end. This ENH fulfils
the outstanding FEAT-1992 acceptance criterion.

## Current Behavior

- `specs/` directory does not exist in the repository.
- No sample spec file (`specs/sample.md`) has been created.
- `rn-build` has structural unit-test coverage (`test_rn_build.py`) but has never
  been executed end-to-end against a real spec.
- The `goal-cluster → rn-implement` handoff contract, the `eval_gate` re-entry path,
  and the `synthesize_result` JSON output are all untested at runtime.
- FEAT-1992's acceptance criterion (E2E smoke passes, no `eval-driven-development` in
  dispatch log) remains unfulfilled.

## Expected Behavior

- `specs/sample.md` exists as a minimal, realistic project spec (4–6 core features,
  2–3 observable acceptance criteria).
- `ll-loop run rn-build --context spec=specs/sample.md` completes without an FSM
  executor crash.
- The dispatch log contains `goal-cluster` and `rn-implement`; does **not** contain
  `eval-driven-development`.
- `${run_dir}/epic-id.txt` is written (confirming `scope_project` completed).
- `TestE2E` class in `scripts/tests/test_rn_build.py` passes when
  `PYTEST_INTEGRATION=1` is set.

## Motivation

A loop that has never run end-to-end is not a shipped feature — it is a
structurally-valid YAML file. The `goal-cluster → rn-implement` handoff contract,
the `eval_gate` re-entry path, and the `synthesize_result` JSON output are all
untested at runtime. An E2E smoke test also serves as a regression guard for any
future change to `rn-build`, `goal-cluster`, or `rn-implement`.

## Proposed Solution

### 1. Sample spec (shared with ENH-2012)

`specs/sample.md` should be a minimal but realistic project spec — small enough
that `rn-build` can process it in a single session, realistic enough that all
pipeline phases produce meaningful output. Suggested project: a CLI tool (e.g.,
a Markdown link checker) with:
- 4-6 Core Features
- 2-3 Acceptance Criteria (concrete, observable)
- No hard tech constraints (lets rn-build pick the stack)

If ENH-2012 creates `specs/sample.md` first, this ENH reuses it as the fixture.

### 2. Smoke test procedure

A documented manual smoke test (and optionally a `pytest` integration test marked
`@pytest.mark.integration`) that:

1. Runs `ll-loop run rn-build --context spec=specs/sample.md --context max_eval_retries=0`
   (skip eval gate re-entry for speed)
2. Waits for completion (or `--foreground` mode)
3. Asserts: the run directory `${run_dir}` exists and contains `epic-id.txt`
4. Asserts: the dispatch log does NOT contain `eval-driven-development`
5. Asserts: `goal-cluster` was dispatched (grep loop events for `goal-cluster`)
6. Asserts: `rn-implement` was dispatched with `schedule_mode=value_ranked`
7. Asserts: `synthesize_result` JSON is well-formed

### 3. Test registration

Add the integration test to `scripts/tests/test_rn_build.py` under a
`TestE2E` class, marked `@pytest.mark.integration` and `@pytest.mark.slow`
so it is excluded from the default `pytest` run but included in CI when
`PYTEST_INTEGRATION=1` is set.

## Implementation Steps

1. Confirm `specs/sample.md` exists (create if ENH-2012 hasn't landed yet)
2. Run `ll-loop run rn-build --context spec=specs/sample.md --context max_eval_retries=0` manually and record observed behavior
3. Verify dispatch log shows `goal-cluster` → `rn-implement` with no `eval-driven-development`
4. Capture any failures found during the run as follow-up issues
5. Write `TestE2E` class in `scripts/tests/test_rn_build.py` with the 6 assertions above
6. Document the manual smoke-test procedure in `docs/guides/LOOPS_GUIDE.md` under `rn-build`

## Integration Map

### Files to Create
- `specs/sample.md` — if ENH-2012 hasn't created it yet

### Files to Modify
- `scripts/tests/test_rn_build.py` — add `TestE2E` integration test class
- `docs/guides/LOOPS_GUIDE.md` — document smoke-test procedure under `rn-build`

### Dependent Files (Callers/Importers)
- N/A — test files and documentation additions; no exported APIs

### Similar Patterns
- `scripts/tests/test_rn_build.py` — existing `TestRnBuild` and `TestRnBuildYaml` classes show pytest patterns to follow
- Other `@pytest.mark.integration` tests in the test suite (if any) for slow-test gating conventions

### Tests
- `scripts/tests/test_rn_build.py` — primary file being modified; existing tests remain unchanged

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — smoke-test procedure added under `rn-build` section

### Configuration
- N/A — no new config keys; `PYTEST_INTEGRATION=1` env var is already a project convention

## Acceptance Criteria

- `specs/sample.md` exists and is a valid rn-build input.
- Running `ll-loop run rn-build --context spec=specs/sample.md` completes without
  an FSM executor crash.
- Dispatch log contains `goal-cluster` and `rn-implement`; does NOT contain
  `eval-driven-development`.
- `${run_dir}/epic-id.txt` is written (scope_project completed).
- `TestE2E` class in `test_rn_build.py` passes when `PYTEST_INTEGRATION=1`.

## Scope Boundaries

- **Not in scope**: Validating the quality of the generated React Native app (only the
  pipeline's dispatch behavior is tested).
- **Not in scope**: A full E2E test suite covering all `rn-build` scenarios (single smoke
  path only).
- **Not in scope**: Modifying `rn-build.yaml` or any pipeline loop YAML files.
- **Not in scope**: Deep testing of the `eval_gate` retry path — `max_eval_retries=0`
  is passed explicitly to skip it for speed.
- **Not in scope**: Wiring the integration test into CI automatically; the
  `@pytest.mark.slow` / `PYTEST_INTEGRATION=1` convention keeps it opt-in.

## Impact

- **Priority**: P3 — outstanding FEAT-1992 AC; also the only way to catch
  runtime regressions across the goal-cluster → rn-implement handoff
- **Effort**: Medium — running the loop end-to-end takes significant wall time;
  test authoring is straightforward once the run completes
- **Risk**: Low — additive; no loop YAML changes
- **Breaking Change**: No

## Resolution

Implemented `TestE2E` class in `scripts/tests/test_rn_build.py` with 6 assertions:
exit-0, `epic-id.txt` exists, no `eval-driven-development` in dispatch log, `goal-cluster`
dispatched, `rn-implement` dispatched, `SYNTHESIS_RESULT:` JSON well-formed.
`specs/sample.md` was already created by ENH-2012. Smoke-test procedure documented in
`docs/guides/LOOPS_GUIDE.md` under the `rn-build` section.

## Status

**Done** | Created: 2026-06-08 | Completed: 2026-06-08

## Session Log
- `/ll:ready-issue` - 2026-06-08T02:40:33 - `e4b624a8-cfdf-44d3-8a76-379e9c661941.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:format-issue` - 2026-06-08T01:36:06 - `b59e4b87-6e2b-4690-bb43-64f1327b0c7e.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:29:25Z - `00fefddf-56f7-43f8-8a57-dd53f6c3526d.jsonl`
