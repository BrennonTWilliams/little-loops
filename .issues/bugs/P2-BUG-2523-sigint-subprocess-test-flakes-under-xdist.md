---
id: BUG-2523
title: SIGINT subprocess test flakes under xdist parallel load
type: BUG
priority: P2
status: done
discovered_date: 2026-07-07
discovered_by: capture-issue
testable: false
decision_needed: true
confidence_score: 100
outcome_confidence: 88
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
completed_at: 2026-07-07 18:55:53+00:00
---

## Summary

`test_fsm_signal_integration.py::TestSubprocessSignalIntegration::test_sigint_archives_audit_trail` raises `subprocess.TimeoutExpired` when the full pytest suite runs in parallel via `xdist`, but passes in 1.25s when run in isolation. The test spawns a subprocess running `ll-loop run sigint-test-loop --foreground-internal ...` and waits up to 10s for it to exit after sending SIGINT. Under xdist load the subprocess fails to terminate in time, leaving the test to fail with `subprocess did not exit within 10s of SIGINT`.

## Current Behavior

Running `python -m pytest scripts/tests/ -n auto` (the project's CI gate) fails with:

```
FAILED scripts/tests/test_fsm_signal_integration.py::TestSubprocessSignalIntegration::test_sigint_archives_audit_trail
subprocess.TimeoutExpired: Command '['/Users/brennon/miniforge3/bin/python', '-m', 'little_loops.cli.loop', 'run', 'sigint-test-loop', '--foreground-internal', '--instance-id', 'sigint-single', '--no-llm', '--no-lock']' timed out after 10.0 seconds
```

Same command in isolation (`pytest scripts/tests/test_fsm_signal_integration.py::TestSubprocessSignalIntegration::test_sigint_archives_audit_trail`) passes in 1.25s. Signal-handling subprocess tests with hard timeouts are inherently timing-sensitive and should not be in the default parallel pool.

## Expected Behavior

The test should pass deterministically regardless of parallel worker load, OR be excluded from the default parallel pool so it runs serially in a dedicated worker.

## Motivation

This is a flake that intermittently breaks `python -m pytest scripts/tests/` — the project's only enforced CI gate (CLAUDE.md: "There is no hosted/paid CI in this project — do not add GitHub Actions. The single enforced, cost-free gate is the local test suite"). A flaky CI gate erodes trust and forces developers to re-run locally to distinguish real failures from xdist noise.

## Proposed Solution

Apply `@pytest.mark.no_parallel` (or the project's existing single-worker marker) to the test so xdist routes it to a dedicated worker. Alternatively, raise the 10s subprocess timeout and add a graceful `SIGTERM`-then-`SIGKILL` escalation in the test to handle stuck-loop cases. The xdist-load signal here is that the subprocess is slow to handle SIGINT under contention; raising the timeout alone is a band-aid — the marker is the structural fix.

## Steps to Reproduce

1. From repo root, run `python -m pytest scripts/tests/ -n auto` (full suite in parallel).
2. Observe 1 failure in `test_fsm_signal_integration.py::TestSubprocessSignalIntegration::test_sigint_archives_audit_trail`.
3. Re-run the failing test in isolation: `python -m pytest scripts/tests/test_fsm_signal_integration.py::TestSubprocessSignalIntegration::test_sigint_archives_audit_trail`.
4. Observe: passes in 1.25s.

## Root Cause

- **File**: `scripts/tests/test_fsm_signal_integration.py`
- **Anchor**: `TestSubprocessSignalIntegration.test_sigint_archives_audit_trail` (line ~212: `proc.wait(timeout=10.0)`)
- **Cause**: Subprocess signal handling competes with the 7 xdist workers for scheduler attention; under contention the loop subprocess's SIGINT handler doesn't preempt its current work within 10s.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Module marker**: `scripts/tests/test_fsm_signal_integration.py:37` carries only `pytestmark = pytest.mark.integration` — no `@pytest.mark.no_parallel`, `@pytest.mark.serial`, or `@pytest.mark.timeout` annotation exists.
- **Sibling test affected**: `TestSubprocessSignalIntegration.test_second_signal_force_exit_archives` at `scripts/tests/test_fsm_signal_integration.py:253-329` shares the same `subprocess.Popen(start_new_session=True)` + `os.kill(pid, SIGINT)` + hard `proc.wait(timeout=10.0)` pattern (lines 293-298). It is a parallel flake risk via the same mechanism and should receive the same treatment.
- **xdist scheduling pressure**:
  - `addopts` at `scripts/pyproject.toml:171-178` sets `-n logical` with no `--dist=` flag → xdist defaults to `load` scheduling (tests land on whichever worker is free, no file pinning). `--dist=loadfile` would only pin per-file, not per-test.
  - `pytest_xdist_auto_num_workers` at `scripts/tests/conftest.py:30-53` caps workers to `cpus // 2` (floor 2). On a 14-core host, ~7 workers; on the dev Mac (per the `BUG-2488` root-cause notes), typically 7.
  - `pytest_configure` at `scripts/tests/conftest.py:56-74` calls `os.nice(10)` on pytest workers; the spawned loop subprocess inherits a fresh session via `start_new_session=True` (line 111) and runs at default priority but competes for the same cores.
- **Production handler context**: The subprocess's signal-handling contract under test is `_loop_signal_handler` at `scripts/little_loops/cli/loop/_helpers.py:82-133` (first-signal path lines 84-88; second-signal force-exit path lines 90-112 invoking `archive_run_only` and `sys.exit(1)`). `PersistentExecutor.archive_run_only` at `scripts/little_loops/fsm/persistence.py:838-894` is the ENH-2516 force-exit archive hook that makes the audit trail survive a second-signal shutdown.
- **Why real subprocess**: This test deliberately avoids mocks (per its module docstring, `test_fsm_signal_integration.py:1-22`) — the contract under test is the kernel-vs-Python signal-delivery latency, not Python-level handler logic. A mocked test (cf. `test_cli_loop_lifecycle.py:438-471`) does not exercise this failure surface.

## Location

- **File**: `scripts/tests/test_fsm_signal_integration.py`
- **Line(s)**: ~212 (the `proc.wait(timeout=10.0)` call)
- **Anchor**: `TestSubprocessSignalIntegration.test_sigint_archives_audit_trail`

## Implementation Steps

1. Identify the project's existing single-worker / no-parallel marker convention (check `scripts/pyproject.toml` pytest section, `conftest.py`).
2. If no such marker exists, add one that maps to `pytest-xdist`'s `--dist=loadfile` or a worker-level skip pattern.
3. Annotate `TestSubprocessSignalIntegration` (or the specific test) with the marker.
4. Verify the test passes in the full suite (`python -m pytest scripts/tests/ -n auto`).
5. Add a regression test or comment that the test must not be parallelized.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references and ordering:_

1. **Confirm absence** — `grep -rn "no_parallel\|serial\|single_worker" scripts/pyproject.toml scripts/tests/` returns nothing (research-verified). The marker does not exist; this is net-new ground.
2. **Register the marker** — Add to `[tool.pytest.ini_options].markers` at `scripts/pyproject.toml:179-183`:
   ```toml
   "no_parallel: marks tests that must not run on xdist workers (use pytest_collection_modifyitems to skip on parallel runs or route to a dedicated worker)",
   ```
   The order/position matches the existing `integration`/`slow`/`conformance` triple. `--strict-markers` will then accept the annotation.
3. **Implement the routing hook** — Add to `scripts/tests/conftest.py` (next to `pytest_xdist_auto_num_workers` at L30-53 is the natural neighbor). Pattern (option A — simplest, test still runs on controller):
   ```python
   def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
       """Skip `no_parallel`-marked tests on xdist workers."""
       if not (hasattr(config, "workerinput") and config.workerinput):
           return  # controller (or single-process run) — let them run
       skip_marker = pytest.mark.skip(reason="no_parallel: cannot run on xdist workers")
       for item in items:
           if "no_parallel" in item.keywords:
               item.add_marker(skip_marker)
   ```
   This matches the established xdist-worker-detection idiom at `scripts/little_loops/pytest_history_plugin.py:147` (covered by `scripts/tests/test_pytest_history_plugin.py:62-71`).
4. **Apply the marker** — Add to `scripts/tests/test_fsm_signal_integration.py:37` alongside the existing `pytest.mark.integration`:
   ```python
   pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]
   ```
   Applying at module scope covers BOTH `test_sigint_archives_audit_trail` (L180-251) and `test_second_signal_force_exit_archives` (L253-329), which share the timing-sensitive subprocess machinery.
5. **Unit-test the hook** — Add to `scripts/tests/test_conftest_cap.py` (extending the existing `TestWorkerCount` class at L36-82): a test that constructs a `MagicMock()` config with `workerinput={"workerid": "gw0"}`, builds a fake item with `keywords={"no_parallel"}`, runs `pytest_collection_modifyitems`, and asserts the item received a skip marker. Mirror the env-var override pattern at `test_conftest_cap.py:47`.
6. **Update docs** — Add `no_parallel` row to the marker table at `docs/development/TESTING.md:1028-1034` (matching the `integration`/`slow`/`conformance` shape). Add a short note to `docs/development/TROUBLESHOOTING.md` under the existing xdist / mac-beachball guidance (see `BUG-2488` notes referenced in `MEMORY.md`).
7. **Coordinate with BUG-2524** — Sister issue `.issues/bugs/P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md` proposes the same marker for `TestRateLimitCircuitIntegration` at `scripts/tests/test_fsm_executor.py:6478`. Consider landing both with a single PR: marker registration + hook + two applications.
8. **Verify** — `python -m pytest scripts/tests/ -n logical` must exit 0 with no `subprocess.TimeoutExpired` from `test_fsm_signal_integration.py`. The hook should skip both subprocess tests on workers (they still run on the controller under `-n logical` xdist scheduling). For a stricter "dedicated serial worker" verification: `python -m pytest scripts/tests/ -n 0` runs the full suite serially and must also pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Register marker — extend `[tool.pytest.ini_options].markers` at `scripts/pyproject.toml:179-183` with a `no_parallel: ...` entry (in the existing alphabetical/conformance order); `--strict-markers` at addopts line 172 will reject any test that applies the marker before this registration lands [Agent 2 finding]
10. Add conftest hook — `scripts/tests/conftest.py`: new `pytest_collection_modifyitems(config, items)` hook co-located with the existing `pytest_xdist_auto_num_workers` (L30-53) and `pytest_configure` (L56-74) hooks; mirror the `hasattr(config, "workerinput") and config.workerinput` detection idiom from `scripts/little_loops/pytest_history_plugin.py:147-150` (proven correct by `scripts/tests/test_pytest_history_plugin.py:62-81`) [Agent 1 + Agent 3 finding]
11. Apply marker — `scripts/tests/test_fsm_signal_integration.py:37`: change `pytestmark = pytest.mark.integration` to `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]` (list-form; covers BOTH `test_sigint_archives_audit_trail` AND `test_second_signal_force_exit_archives` which shares the timing-sensitive subprocess machinery) [Agent 1 finding]
12. Unit-test the hook — `scripts/tests/test_conftest_cap.py`: add a `TestNoParallelMarkerRouting` class next to `TestWorkerCount` (L36-82); build `MagicMock()` config with `workerinput={"workerid": "gw0"}`, synthetic item with `keywords={"no_parallel"}`, assert `add_marker(pytest.mark.skip(reason=...))` was called; add a controller-path test (`MagicMock(spec=[...])`, no `workerinput`) asserting `add_marker` was NOT called [Agent 3 finding]
13. Document the marker — `docs/development/TESTING.md:1028-1034`: add a `no_parallel` row to the `### Test Markers` table matching the existing `integration`/`slow`/`conformance` shape [Agent 2 finding]
14. Cross-link TROUBLESHOOTING note — `docs/development/TROUBLESHOOTING.md`: add a short paragraph under the existing xdist / mac-beachball section pointing at the new marker for future signal-handling subprocess tests [Agent 2 finding]
15. Coordinate with BUG-2524 — consider landing `scripts/tests/test_fsm_executor.py:6478` (`TestRateLimitCircuitIntegration`) marker application in the same PR; the marker + hook infrastructure is the only shared work, and a coordinated landing keeps the rollout atomic (per `.issues/bugs/P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md`) [Agent 1 finding]
16. No `--dist=` flag change required — `addopts` at `scripts/pyproject.toml:171-178` defaults xdist to `load` scheduling, which is fine; the marker-driven hook replaces the need for a `--dist=` switch [Agent 1 finding]

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_signal_integration.py` — add the no-parallel marker
- `scripts/pyproject.toml` — register the marker in `[tool.pytest.ini_options].markers` (if not present)
- `scripts/tests/conftest.py` — add `pytest_collection_modifyitems` hook to skip marked tests on xdist workers [refined plan §1-4]

### Dependent Files (Callers/Importers)
- `scripts/tests/conftest.py` — may need a hook to interpret the marker for xdist

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `TestSubprocessSignalIntegration` test methods under the `--foreground-internal` flow; cross-reference only (no edit required since the marker is collection-time, not a behavior change) [Agent 1 finding]
- `.issues/enhancements/P2-ENH-2517-subprocess-sigint-test-and-docs.md` — introduced the test class; coordinate if ENH-2517 evolves to add more SIGINT integration tests (they should also receive the marker) [Agent 1 finding]
- `scripts/little_loops/pytest_history_plugin.py:147-150` — production-side xdist-worker detection idiom that the new conftest hook must mirror exactly (`hasattr(config, "workerinput") and config.workerinput`); cross-reference only [Agent 2 finding]
- `scripts/little_loops/cli/loop/_helpers.py:82-133` (`_loop_signal_handler`) and `:166-190` (`register_loop_signal_handlers`) — production handlers under test; no modification, but the test's contract anchors here [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py:838-894` (`PersistentExecutor.archive_run_only`) — ENH-2516 force-exit archive hook exercised by `test_second_signal_force_exit_archives`; no modification [Agent 1 finding]
- `scripts/little_loops/parallel/tasks/test-suite.yaml:53-58, 175-176` — defines an `inputs.markers` knob (`pytest -m "not slow"`); no edit required for this PR, but the marker becomes a valid filter expression for future loop YAMLs that opt into `-m no_parallel` [Agent 2 finding]
- `.issues/bugs/P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md` — sister issue proposing the same marker for `TestRateLimitCircuitIntegration` at `scripts/tests/test_fsm_executor.py:6478`; coordinated-PR opportunity noted at Implementation Step 7 [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_conftest_cap.py` — extend `TestWorkerCount` (L36-82) with a new `TestNoParallelMarkerRouting` class that exercises `pytest_collection_modifyitems` via `MagicMock()` config + `workerinput={"workerid": "gw0"}` + synthetic items with `keywords={"no_parallel"}`; mirror the `MagicMock(spec=["pluginmanager"])` controller-path pattern from `scripts/tests/test_pytest_history_plugin.py:73-81` [Agent 3 finding]
- `scripts/tests/test_pytest_history_plugin.py:62-81` — existing xdist-worker-detection idiom coverage; the new conftest hook test should mirror this exact pattern (no edits required here) [Agent 3 finding]
- No existing test asserts on the registered-marker set in `[tool.pytest.ini_options].markers` or on the `pytestmark` value of `test_fsm_signal_integration.py`; the list-form `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]` change at line 37 is non-breaking for the 22 other test files using `pytestmark = pytest.mark.integration` [Agent 3 finding]
- The marker test itself: run full suite, confirm the test still passes

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:1028-1034` — `### Test Markers` table currently lists `integration`/`slow`/`conformance`; add a `no_parallel` row matching the existing shape (the row was NOT in the original Integration Map above; BUG-2523 Implementation Step 6 already calls for this but the section was missing from `Documentation`) [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — add a short note under the existing xdist / mac-beachball section explaining the marker for future signal-handling tests (already in original Integration Map)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Marker registry location**: `[tool.pytest.ini_options].markers` at `scripts/pyproject.toml:179-183` currently lists only `integration`, `slow`, `conformance`. `--strict-markers` (in `addopts` line 172) rejects unknown markers, so the new `no_parallel` marker MUST be registered before use.
- **No existing xdist scheduler hook**: `scripts/tests/conftest.py` defines only `pytest_xdist_auto_num_workers` (L30-53) and `pytest_configure` (L56-74). There is NO `pytest_collection_modifyitems`, NO `pytest_xdist_make_scheduler`, NO marker-driven worker routing. The marker must be paired with one of:
  1. A `pytest_collection_modifyitems` hook that calls `item.add_marker(pytest.mark.skipif(...))` when `hasattr(config, "workerinput") and config.workerinput` is set (the established xdist-worker-detection idiom — see `scripts/little_loops/pytest_history_plugin.py:147` and its unit test at `scripts/tests/test_pytest_history_plugin.py:62-71`), OR
  2. A `pytest_xdist_make_scheduler` override that reserves a `loadfile`-style scope for marked tests, OR
  3. A simpler `--dist=loadfile` switch + `pytest_collection_modifyitems` to skip marked tests on parallel workers (test would still run on the controller in a `-n 0` invocation or on a single-worker pool).
- **Sibling-flake precedent (BUG-2524)**: `.issues/bugs/P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md` proposes the same `@pytest.mark.no_parallel` marker. One marker definition + a shared conftest hook can solve both bugs at once. Worth considering a coordinated PR that adds the marker + hook once and applies it to both flaky tests.
- **Documentation target**: The project's marker table lives at `docs/development/TESTING.md` L1028-1034 (`### Test Markers` section). Adding `no_parallel` there matches the existing `integration`/`slow`/`conformance` documentation shape.
- **Test for the marker itself**: `scripts/tests/test_conftest_cap.py:36-82` (`TestWorkerCount`) is the established pattern for unit-testing conftest hooks via `MagicMock()` config + `monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "3")`. Any new conftest hook interpreting the marker should follow this pattern.
- **Production signal-handler anchors (cross-reference, not modification)**:
  - `scripts/little_loops/cli/loop/_helpers.py:82-133` — `_loop_signal_handler` (SIGINT+SIGTERM dispatch)
  - `scripts/little_loops/cli/loop/_helpers.py:166-190` — `register_loop_signal_handlers` (registration at 189-190)
  - `scripts/little_loops/cli/loop/run.py:170-173, 311-313` — `--foreground-internal` flag consumption
  - `scripts/little_loops/fsm/persistence.py:486` — `archive_run` (graceful exit)
  - `scripts/little_loops/fsm/persistence.py:838-894` — `archive_run_only` (force-exit archive, ENH-2516)
- **Related test files with similar `subprocess.Popen` patterns (audit candidates)**: `scripts/tests/test_hooks_integration.py` (25+ `subprocess.run()` calls — shell-script invocations, not signal-sensitive); `scripts/tests/test_fsm_executor.py:6478` `TestRateLimitCircuitIntegration` (27.48s, the BUG-2524 sibling).

## Impact

Low-severity flake (test only, not production) but high CI-noise: every full-suite run has a 1-in-N chance of false-positive failure, requiring re-runs. Marking the test as no-parallel is a 1-line fix.

## Related Key Documentation

- `.claude/CLAUDE.md` — Testing & CI Policy section
- `docs/development/TROUBLESHOOTING.md`

## Status

done

## Resolution

Added the `@pytest.mark.no_parallel` marker plus a `pytest_collection_modifyitems` conftest hook that skips marked tests on xdist workers. Both `TestSubprocessSignalIntegration` tests now skip cleanly on workers (no more `subprocess.TimeoutExpired`) and continue to pass in serial mode (`pytest -n 0`). The full suite went from `subprocess.TimeoutExpired` under `-n logical` to `14154 passed, 29 skipped` (was 27 + 2 no_parallel skips) in 82s. Marker is also registered in `pyproject.toml`, documented in `docs/development/TESTING.md` (Test Markers table) and `docs/development/TROUBLESHOOTING.md` (new "xdist flake: subprocess signal-handling test times out" section), and unit-tested in `scripts/tests/test_conftest_cap.py::TestNoParallelMarkerRouting` (4 tests, all pass).

## Session Log
- `/ll:ready-issue` - 2026-07-07T18:39:15 - `7e9140a6-16cc-4a26-9a6b-331569bdc583.jsonl`
- `/ll:decide-issue` - 2026-07-07T18:33:13 - `059f5105-9864-4f29-bdeb-5d1bedafbc12.jsonl`
- `/ll:confidence-check` - 2026-07-07T19:45:00 - `e6221f31-839f-47c6-8936-53a457705e36.jsonl`
- `/ll:wire-issue` - 2026-07-07T18:26:35 - `95e936fa-d5c6-493c-acde-02d3bd556130.jsonl`
- `/ll:refine-issue` - 2026-07-07T18:21:52 - `29bca948-1a4a-4817-b1e1-ceee098b42f5.jsonl`

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
- `/ll:manage-issue` - 2026-07-07T18:55:53Z - `e40aeffb-a408-4dad-94f3-6726581e3f59.jsonl`
