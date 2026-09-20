---
id: BUG-3522
type: BUG
title: policy-builder node conformance test flakes under xdist + Node 24 migration
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-20'
captured_at: '2026-09-20T05:20:00Z'
labels:
- policy-builder
- node
- xdist
- flake
- test-stability
relates_to:
- ENH-3453
- BUG-3486
- BUG-3502
---

# BUG-3522: policy-builder node conformance test flakes under xdist + Node 24 migration

## Summary

`scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` runs `node --test scripts/tests/js/*.test.mjs` against a 180s timeout. Under full-suite xdist CPU contention, the suite intermittently fails — observed as a 2-fail / 1-pass pattern across three runs on `main @ fdf6773d2`. The Node runner was forcibly migrated from 20 to 24 by GitHub Actions during v1.165.0 integration; the conformance suite appears to interact with both xdist scheduling and the Node version transition.

## Current Behavior

The test runs `node --test` against `*.test.mjs` files (per `JS_TEST_DIR`). Under xdist CI load, the suite can fail intermittently — exit code != 0 with a subtest failure listing the specific assertion. The test passes when xdist workers happen to have lower load.

Observed pattern on `main @ fdf6773d2`:
- `35490420257` (main): FAIL
- `35490447772` (PR #29 rebased on `fdf6773d2`): pass
- `35490782202` (PR #32 rebased on `fdf6773d2`): FAIL

2-fail / 1-pass is the smoking-gun signature for a flake under contention, not a deterministic code regression. If Node 24 were a deterministic break, #29 wouldn't have passed.

## Expected Behavior

The node:test conformance suite passes reliably regardless of xdist worker contention. A flaky assertion under load is a CI flake, not a real bug — the suite exists precisely to prove the JS core matches canonical Python, so it must be stable.

## Steps to Reproduce

1. Push to a branch that triggers the `unit-tests` workflow
2. Watch xdist workers run the full unit suite under contention
3. Observe `test_node_conformance_suite_passes` fail intermittently (most visible during a fast push cadence)

## Likely Root Cause

The test launches `node --test` as a subprocess with a 180-second timeout. Under xdist CPU contention, the Node process's V8 JIT compilation or test orchestration may exceed time budgets or hit timing-sensitive assertions. The Node 20 to 24 migration (GitHub Actions' deprecation cycle) may have introduced subtle timing changes in the conformance suite.

The structural fix is `BUG-2523`'s established pattern: `@pytest.mark.no_parallel` — skip on xdist workers, run on the controller (or in serial `-n 0`). The 180-second budget is safe in that mode where there's no CPU contention.

## Proposed Solution

Add `@pytest.mark.no_parallel` to `test_node_conformance_suite_passes` — same pattern PR #30 used for `test_two_producers_reach_one_client_with_distinct_producer_pid`. Run on the controller or in serial `-n 0` where CPU contention is absent and the 180s budget is safe.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Conventions in force**: a timing-sensitive or long-subprocess test is marked `no_parallel` (runs only under serial `-n 0`); tests needing more than the 120s default set `@pytest.mark.timeout(N)` strictly above any inner subprocess timeout (`test_verify_evidence.py`). The codebase disagrees on dormancy: `test_worktree_utils.py` (BUG-2650) explicitly rejects `no_parallel` because it is dormant under the default CI command, and instead runs a nested `-n 0` pytest. Which trade-off applies here — accept a dormant gate, add a serial CI invocation, or drop `no_parallel` in favor of a `timeout` marker above 180 — is an implementation decision.
- Any resolution must keep the gate exercised somewhere (CLAUDE.md § Testing & CI Policy requires other-toolchain gates to run under the pytest suite), and must keep `test_conftest_cap.py::TestNoParallelMarkerRouting` passing.

## Acceptance Criteria

- `test_node_conformance_suite_passes` passes reliably across 5+ consecutive CI runs on `main`
- The test runs on the controller or serial `-n 0` (not on xdist workers) — same pattern as BUG-3484's `test_two_producers_reach_one_client_with_distinct_producer_pid` no_parallel fix
- No regression in other JS conformance tests (`test_node_22plus_runs_ok`, `test_node_test_runner_emits_tap_v13`, etc.) — these presumably don't have the contention issue
- If a Node-version pin is also needed, add `actions/setup-node@v4` with `node-version: '22.x.y'` to the CI workflow — cheapest first probe before bisecting

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- The Program Design note that "runs on the controller" means "runs only in serial `-n 0`" makes AC 1 (5+ consecutive CI runs pass) trivially satisfiable by dormancy; a real criterion needs the gate to execute in at least one CI or documented serial invocation.

## Notes

The Node 20 to 24 runner migration is documented as "Node.js 20 deprecated... forced onto Node.js 24" by the GitHub Actions runner announcement. Pinning to a specific Node 24.x.y version in `ci.yml` is a cheaper first probe than bisecting; if pinning fixes it, the issue reduces to "CI drift"; if not, the flake is contention-driven and `no_parallel` is the right fix.

If both pinning and `no_parallel` are needed, do both — pinning reduces CI maintenance burden (Node version control), `no_parallel` eliminates xdist contention.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **Marker already landed**: `@pytest.mark.no_parallel` was added by `60358e836` (2026-09-20, `fix(tests): mark node conformance test no_parallel (BUG-3521) (#33)`), after the cited runs on `main @ fdf6773d2` (2026-09-19). The Proposed Solution's marker step is therefore complete; remaining work is the verification/coverage question below.
- **Consequence of the marker**: `scripts/tests/conftest.py:pytest_collection_modifyitems` skips `no_parallel` items on xdist workers; the controller never runs tests under `-n N`. With `pytest.ini`/`scripts/pyproject.toml` addopts `-n logical`, the gate never executes in either `.github/workflows/ci.yml` job (`unit-tests` on `ubuntu-latest`, `conformance` on self-hosted with `-m conformance`; the test has no `conformance` marker). No workflow step runs `-n 0`, so the FEAT-2390 policy-builder JS gate is currently dormant in CI.
- **Dependent/precedent files**: `scripts/tests/test_fsm_signal_integration.py` (module-level `pytestmark`, BUG-2523), `scripts/tests/test_feat3323_sse_bridge.py` (BUG-3484, stacked with `@pytest.mark.timeout(180)`), `scripts/tests/test_conftest_cap.py:TestNoParallelMarkerRouting` (hook contract), `docs/development/TESTING.md` (marker table ~L1050), `docs/development/TROUBLESHOOTING.md` (BUG-2523 section ~L825).
- **CI Node**: `.github/workflows/ci.yml` has no `actions/setup-node` and no `node-version`; Node comes from the runner image. The Node-pin acceptance criterion would be the first Node pin in the repo.
- **AC references that do not resolve**: `test_node_22plus_runs_ok` and `test_node_test_runner_emits_tap_v13` do not exist anywhere; the sibling test in the file is `test_round_trip_yaml_validates_for_each_mode` (no `no_parallel`, inner `timeout=30`).

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — § Testing & CI Policy cites `test_policy_builder_node_gate.py` as the enforced example of a wrapped other-toolchain gate; a dormant gate under default `-n logical` contradicts that claim [Agent 2 finding]
- `AGENTS.md` — mirrors the same `test_policy_builder_node_gate.py` reference; keep consistent with CLAUDE.md [Agent 2 finding]
- `scripts/tests/test_policy_builder_node_gate.py` — module docstring (L1-17) still says "no hosted CI … single enforced location is the local suite"; stale vs. `.github/workflows/ci.yml` and the `no_parallel` skip, update alongside any resolution [Agent 1 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — marker table row for `no_parallel` (~L1050) says "runs on the controller or in a serial `-n 0` invocation"; under `-n N` the controller runs no tests, so reword to "serial `-n 0` only" [Agent 2 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_conftest_cap.py` — `TestNoParallelMarkerRouting` must keep passing if the marker is changed/removed [Agent 3 finding]
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — lives in a subdir, so the gate's non-recursive `JS_TEST_DIR.glob("*.test.mjs")` never runs it; note when deciding what "the gate" covers [Agent 3 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `.github/workflows/ci.yml` — a serial `-n 0` step (or `-m` selection) running only this test is the wiring needed to un-dormant the gate; optional `actions/setup-node` pin goes in the same file [Agent 2 finding]

## Program Design

### Types

- No new types — test-marker change only.

### Signatures

- `test_node_conformance_suite_passes() -> None` — in `scripts/tests/test_policy_builder_node_gate.py`; already carries `@pytest.mark.no_parallel` at the time of formatting, so the remaining work is verification and (optionally) the Node pin
- `pytest_collection_modifyitems(config, items) -> None` — in `scripts/tests/conftest.py`; skips `no_parallel`-marked items on xdist workers (BUG-2523)

### Call Path

`test_node_conformance_suite_passes` -> `_node_major` -> `subprocess.run` (`node --test scripts/tests/js/*.test.mjs`, 180s timeout)

### Behavior Notes

- Under xdist `-n N` the controller only orchestrates and does not run tests, so a `no_parallel` skip means the test does not execute in parallel mode at all; it runs only in serial `-n 0`. The Expected/AC wording "runs on the controller" should be read as "runs in serial `-n 0`". If CI must still exercise the gate, it needs a separate serial invocation.

## Impact

- **Priority**: P3 - Intermittent CI flake on a single test; no production behavior affected
- **Effort**: Small - One marker (already present) plus an optional Node version pin in `.github/workflows/ci.yml`
- **Risk**: Low - Test-scheduling change only; skipping under xdist reduces, not adds, coverage in parallel runs
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-20 | Priority: P3


## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `.github/workflows/ci.yml` — add a serial `-n 0` invocation of `test_policy_builder_node_gate.py` (or drop `no_parallel` for `@pytest.mark.timeout(>180)`) so the gate executes in CI
- Update `scripts/tests/test_policy_builder_node_gate.py` — raise per-test timeout above inner 180s and refresh the stale module docstring
- Update `docs/development/TESTING.md` — fix "runs on the controller" wording in the `no_parallel` row
- Verify `.claude/CLAUDE.md` / `AGENTS.md` gate-example wording still holds after the change
- Re-run `scripts/tests/test_conftest_cap.py` (`TestNoParallelMarkerRouting`)

## Session Log
- `/ll:wire-issue` - 2026-09-20T21:53:51 - `80e0a309-7358-453f-8fdc-92553921aa72.jsonl`
- `/ll:refine-issue` - 2026-09-20T21:21:36 - `09272224-9351-4571-a369-7e216b7645b5.jsonl`
- `/ll:format-issue` - 2026-09-20T21:17:56 - `4117c50f-02ee-4b8b-8840-0c4b382de04b.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-20 — based on codebase analysis:_

- **File**: `scripts/tests/test_policy_builder_node_gate.py`, `test_node_conformance_suite_passes` — the inner `subprocess.run(..., timeout=180)` carries no `@pytest.mark.timeout`, so the suite-wide 120s thread-method pytest-timeout budget (`scripts/pyproject.toml` addopts) applies. Because the watchdog budget (120s) is below the inner budget (180s), a slow `node --test` under contention is killed by the thread watchdog, which hard-kills the xdist worker (`os._exit`) before `TimeoutExpired` can fire. This matches the worker-crash signature rather than an assertion flake. Convention violated: `test_verify_evidence.py` keeps the per-test cap strictly above the inner subprocess timeout (`GATE_TIMEOUT + 30`). This is a hypothesis from static reading; no failing CI log was inspected.
- The JS files in `scripts/tests/js/*.test.mjs` (5 files) use injected fake clocks (`policy_submission.test.mjs`, `policy_validator.test.mjs`), not wall-clock waits — the only real-time limit is the Python-side timeout, which supports the timeout-budget reading over a Node-24 behavioral break.
