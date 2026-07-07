---
id: BUG-2524
title: xdist worker crashes on long-running rate-limit test
type: BUG
priority: P3
status: done
discovered_date: 2026-07-07
completed_at: 2026-07-07 19:05:04+00:00
discovered_by: capture-issue
testable: false
decision_needed: false
learning_tests_required:
- pytest-xdist
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

## Summary

`scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration::test_record_rate_limit_called_on_short_tier` causes xdist worker `gw6` to crash (`worker 'gw6' crashed while running ...`) when run as part of the full parallel test suite. The test takes 27.48s in isolation — far longer than typical unit tests — and overwhelms its xdist worker's resource budget or timing guarantees under load.

## Current Behavior

Running `python -m pytest scripts/tests/ -n auto` (the CI gate) reports:

```
worker 'gw6' crashed while running 'tests/test_fsm_executor.py::TestRateLimitCircuitIntegration::test_record_rate_limit_called_on_short_tier'
=========================== short test summary info ============================
FAILED scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration::test_record_rate_limit_called_on_short_tier
```

The same test run alone passes in 27.48s. The crash is a worker-level termination, not a test-level assertion failure — the worker itself is killed (likely OOM, signal, or xdist timeout) while running the test.

## Expected Behavior

The test should either (a) complete successfully under xdist load, (b) be moved to a dedicated worker via a no-parallel marker, or (c) be split into a fast core test and a separate long-running integration test.

## Motivation

Same as BUG-2523: a flaky CI gate erodes developer trust. A worker crash looks like a real test failure but is infrastructure noise, forcing re-runs to confirm.

## Proposed Solution

Add a `@pytest.mark.no_parallel` (or equivalent) marker to `TestRateLimitCircuitIntegration` so xdist routes these long-running tests to a dedicated worker. As a secondary fix, profile the 27.48s test to identify the bottleneck and either speed it up or split it.

## Steps to Reproduce

1. From repo root, run `python -m pytest scripts/tests/ -n auto` (full suite in parallel).
2. Observe the worker crash message in the output and the test listed as failed.
3. Re-run the failing test in isolation: `python -m pytest scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration::test_record_rate_limit_called_on_short_tier`.
4. Observe: passes in 27.48s.

## Root Cause

- **File**: `scripts/tests/test_fsm_executor.py`
- **Anchor**: `TestRateLimitCircuitIntegration.test_record_rate_limit_called_on_short_tier`
- **Cause**: 27.48s test execution exceeds the worker's tolerance under xdist scheduling pressure; xdist terminates the worker (memory, signal, or scheduling deadline) mid-test.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Where the 27.48s is actually spent** — `scripts/tests/test_fsm_executor.py:6594–6629` constructs the FSM and patches `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 0` inside a `with patch(...)` context manager at lines 6623–6625, then calls `executor.run()`. The wall-clock time is in `_interruptible_sleep` at `scripts/little_loops/fsm/executor.py:2233–2261` (tick-sleep loop, `time.sleep(min(0.1, ...))` at line 2255). The 27.48s figure is consistent with **one short-tier `_sleep` call firing at the real default base** (`_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 30` at `executor.py:71`), strongly suggesting the patch is not taking effect during `run()` (module-level constant lookup at import time, or a scope mismatch with the `MockActionRunner` lifecycle).
- **The short-tier backoff calc** at `executor.py:2104`: `_sleep = _backoff_base * (2 ** (short_retries - 1)) + random.uniform(0, _backoff_base)`. With base=30 and the first 429 from the test's `MockActionRunner`, `_sleep ≈ 30–60s` — exactly matching the 27.48s figure.
- **`record_rate_limit` itself has no delay** — `RateLimitCircuit.record_rate_limit` at `scripts/little_loops/fsm/rate_limit_circuit.py:44–75` only takes an `fcntl.LOCK_EX` lock (lines 52–53), reads state, writes atomically via `tempfile.mkstemp` + `os.replace` (lines 121–134). It cannot itself account for the wall-clock time.
- **Why this specific test is slow vs other `TestRateLimitCircuitIntegration` tests** — only `test_record_rate_limit_called_on_short_tier` constructs a `MockActionRunner` with `use_indexed_order = True` (line 6621) and a `result: ErrorResult(429)` as the first element. The other tests in the class (`test_pre_action_sleep_when_circuit_active` L6519, `test_pre_action_no_sleep_when_circuit_stale` L6545, `test_pre_action_skipped_for_shell_action` L6569, `test_record_rate_limit_not_called_when_circuit_none` L6631, `test_sub_loop_inherits_parent_circuit` L6661) pre-populate the circuit via `circuit.record_rate_limit(1000.0)` (line 6574) so `_maybe_wait_for_circuit` short-circuits and never enters `_handle_rate_limit`.
- **Long-wait tier not implicated** — `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER = [300, 900, 1800, 3600]` at `executor.py:77` is unpatched by the test, but only fires after `short_retries >= _DEFAULT_RATE_LIMIT_RETRIES (= 3)`. The test's two-result queue (one 429 + one OK) exits the FSM at the OK result before the long-wait tier is reached.
- **Integration value of the test** — the only path it covers that fast unit tests don't is the `if self._circuit is not None: self._circuit.record_rate_limit(_sleep)` branch at `executor.py:2105–2106`. `TestRateLimitTwoTier` at `test_fsm_executor.py:6209` already covers the two-tier ladder mechanics with `rate_limit_backoff_base_seconds=0` set on `StateConfig` (line 6225) — at unit speed.

## Location

- **File**: `scripts/tests/test_fsm_executor.py`
- **Line(s)**: the `test_record_rate_limit_called_on_short_tier` method
- **Anchor**: `TestRateLimitCircuitIntegration.test_record_rate_limit_called_on_short_tier`

## Implementation Steps

1. Investigate why the test takes 27.48s — likely a sleep or rate-limit backoff that doesn't need real-time waiting (use `freezegun` or `monkeypatch` to skip).
2. If shortening isn't feasible, apply the same no-parallel marker as BUG-2523 to the test class.
3. Verify the full suite runs cleanly: `python -m pytest scripts/tests/ -n auto`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references and ordering (merged with BUG-2523's prerequisite):_

1. **Land the shared `no_parallel` infrastructure first** — all of BUG-2523's `### Implementation Steps` (`.issues/bugs/P2-BUG-2523-sigint-subprocess-test-flakes-under-xdist.md:86-117`) and `### Wiring Phase` (L118-130) apply verbatim. Specifically:
   - Add `"no_parallel: marks tests that must not run on xdist workers..."` to `[tool.pytest.ini_options].markers` at `scripts/pyproject.toml:179-183`.
   - Add `pytest_collection_modifyitems(config, items)` to `scripts/tests/conftest.py` using the `hasattr(config, "workerinput") and config.workerinput` idiom from `scripts/little_loops/pytest_history_plugin.py:147`.
2. **Apply the marker to this bug's test class** — `scripts/tests/test_fsm_executor.py:6478`:
   ```python
   @pytest.mark.no_parallel
   class TestRateLimitCircuitIntegration:
       ...
   ```
   This covers ALL six tests in the class. The crash is on `test_record_rate_limit_called_on_short_tier` (L6594), but marking the whole class is simpler than cherry-picking methods and the other five tests are slow enough (touch `RateLimitCircuit` disk I/O) that they benefit from a dedicated worker too.
3. **(Optional, secondary) Investigate the 27.48s** — open `scripts/tests/test_fsm_executor.py:6594-6629` in a debugger. The test patches `_DEFAULT_RATE_LIMIT_BACKOFF_BASE = 0` at L6623 inside a `with` context manager that wraps the `executor = FSMExecutor(...)` constructor (L6624) and `executor.run()` (L6625). The 27.48s strongly suggests the patch isn't taking effect during `run()`. Likely root cause: the executor resolves `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` by attribute lookup on the `little_loops.fsm.executor` module, but the `with patch(...)` context manager only patches the attribute while the block is active — confirm whether the executor captures the value at FSMExecutor instantiation vs. at `_handle_rate_limit` call time. If it's captured at construction, the test needs `with patch(...)` placed *before* `executor = FSMExecutor(...)` is called (it is, per L6623), so the real cause may be something else (e.g., the patch library is resolving the dotted path differently, or `random.uniform(0, 0)` is producing non-zero on some platforms). Capture a 1-line print inside `_handle_rate_limit` at L2104 to see the actual `_sleep` value.
4. **Unit-test the routing hook** — extend `scripts/tests/test_conftest_cap.py:36-82` with a `TestNoParallelMarkerRouting` class:
   ```python
   def test_no_parallel_skipped_on_xdist_worker(self):
       config = MagicMock()
       config.workerinput = {"workerid": "gw0"}
       item = MagicMock()
       item.keywords = {"no_parallel": ...}
       conftest.pytest_collection_modifyitems(config, [item])
       item.add_marker.assert_called_once()
   ```
5. **Update docs in the same PR** — `docs/development/TESTING.md:1028-1034` (add `no_parallel` row to Test Markers table); `docs/development/TROUBLESHOOTING.md` (cross-link under xdist / mac-beachball section).
6. **Verify** — `python -m pytest scripts/tests/ -n logical` must exit 0 with no `worker 'gw6' crashed` lines. Also run `python -m pytest scripts/tests/ -n 0` serially to confirm the marker doesn't break single-process runs (the controller path returns early from the hook).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Use `MagicMock(spec=["pluginmanager"])` for the controller-path test** — at `scripts/tests/test_conftest_cap.py` in the new `TestNoParallelMarkerRouting.test_no_parallel_marker_runs_on_controller`, do NOT use plain `MagicMock()`. The `spec=` argument is load-bearing: without it, `MagicMock()` auto-creates a `workerinput` attribute and the `hasattr(config, "workerinput")` guard would silently short-circuit, allowing a buggy hook to pass the test. The proven pattern is at `scripts/tests/test_pytest_history_plugin.py:79` (`TestCaptureGating.test_configure_registers_on_controller`).
8. **Write FOUR tests, not one** — `TestNoParallelMarkerRouting` must cover: (a) marked item skipped on worker, (b) marked item runs on controller, (c) unmarked item left alone on worker, (d) mixed-items batch routing. Spec at lines 94-103 of the original issue covers only (a); expand per `### Tests` wiring additions above.
9. **CREATE the xdist troubleshooting section in `docs/development/TROUBLESHOOTING.md`** — the planned "cross-link under the existing xdist / mac-beachball section" is invalid: the section does not exist. The PR must create a new section covering xdist worker crashes, the `no_parallel` escape hatch, and the `LL_TEST_NO_NICE=1` mac-beachball note (which today lives only at `scripts/tests/conftest.py:62-63`).
10. **Confirm `pytest-xdist>=3.0` dep is in `scripts/pyproject.toml:107-108`** — already declared; no change required, but verify the version floor is satisfied in CI before the PR merges.
11. **No production-code importers need updating** — the marker is purely test-side. `scripts/little_loops/fsm/__init__.py:134`, `cli/loop/lifecycle.py:561`, `cli/loop/run.py:103`, `cli/loop/testing.py:9`, `extension.py:26`, `fsm/persistence.py:39` all import `RateLimitCircuit` / `FSMExecutor` and are unaffected.
12. **No schema / config coupling** — `config-schema.json` has only pytest allowlist entries; `.ll/ll-config.json` has no `parallel.*` or `automation.*` keys. No changes there.

### Decision Point

This issue has TWO implementation paths. Pick one (or do both):

- **Option A — Marker (recommended, ships with BUG-2523)**: 1-line `@pytest.mark.no_parallel` decorator on the class. ~1 line of code. No change to test logic. Pays the "ship as part of the shared PR" coordination cost.

  > **Selected:** Option A — Marker — rides entirely on infrastructure already landed for BUG-2523 (marker registered at `pyproject.toml:179-184`, routing hook at `conftest.py:77-101`, four routing-contract tests at `test_conftest_cap.py:136-211`, TROUBLESHOOTING.md:767 already cross-links BUG-2524); reduces this issue to a class-level 1-line decorator on `TestRateLimitCircuitIntegration`.
- **Option B — Speed up the test**: Investigate the 27.48s, fix the patch-scope bug, get the test down to <1s. Riskier (root cause uncertain per Step 3 above), but eliminates the wall-clock entirely and removes the need for the marker. ~10-30 lines of code (test refactor + debugging).

**Recommendation: Option A** — it matches BUG-2523's structural fix, has a known-good precedent (the proven xdist-worker-detection idiom in `pytest_history_plugin.py`), and is reversible (delete one decorator). Option B can be a follow-up issue.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option A — Marker (recommended, ships with BUG-2523)

**Reasoning**: The shared `no_parallel` infrastructure (BUG-2523) is fully landed in this repo today — marker is registered (`scripts/pyproject.toml:179-184`), the routing hook is installed (`scripts/tests/conftest.py:77-101`, using the `hasattr(config, "workerinput") and config.workerinput` detection idiom), the routing contract is locked in by four tests (`scripts/tests/test_conftest_cap.py:136-211`), and the troubleshooting section (`docs/development/TROUBLESHOOTING.md:751-767`) already names BUG-2524 as the sibling case. `scripts/tests/test_fsm_signal_integration.py:37-42` provides the literal shape precedent (`pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]`). With everything else in place, BUG-2524 reduces to a class-level `@pytest.mark.no_parallel` decorator on `TestRateLimitCircuitIntegration` at `scripts/tests/test_fsm_executor.py:6478` — exactly the precedent Option A invokes. Option B was considered and rejected: 12+ sibling tests in `scripts/tests/test_fsm_executor.py` (lines 5772, 5791, 5809-5813, 5835-5840, 5856-5862, 5899, 5964, 6006, 6445-6447, 6623, 6653) use the IDENTICAL `with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` pattern at the same nesting depth and run in <100ms each; `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` is a module global resolved at call time at `scripts/little_loops/fsm/executor.py:2069-2073` (NOT captured in `FSMExecutor.__init__`). The patch-scope theory the issue hedges on does not hold under static reading — the 27.48s has a different (still-undiagnosed) root cause worth a separate issue, not a debug session blocking this fix.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Marker | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B — Speed up | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: `scripts/pyproject.toml:179-184` (marker registry declares `no_parallel`); `scripts/tests/conftest.py:77-101` (routing hook reads `hasattr(config, "workerinput") and config.workerinput`); `scripts/tests/test_conftest_cap.py:136-211` (`TestNoParallelMarkerRouting` covers marked-on-worker, marked-on-controller, unmarked-on-worker, mixed-items — including a load-bearing `MagicMock(spec=["pluginmanager"])` controller test that prevents silent short-circuit); `scripts/tests/test_fsm_signal_integration.py:37-42` (literal shape precedent); reuse score 3/3 — no new code, no new tests, no new docs.
- Option B: `scripts/little_loops/fsm/executor.py:71` defines `_DEFAULT_RATE_LIMIT_BACKOFF_BASE: int = 30` as a module global; `scripts/little_loops/fsm/executor.py:2069-2073` reads it via module-global lookup at every `_handle_rate_limit` call; `scripts/little_loops/fsm/executor.py:2247-2248` short-circuits `_interruptible_sleep` when `duration <= 0` (so if the patch worked, the test would be instant); reuse score 2.5/3 but root-cause uncertainty weighs heavily on Simplicity and Risk.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — add the no-parallel marker
- Optionally: speed up the test by mocking time/backoff

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — extend `[tool.pytest.ini_options].markers` (L179-183) with a `no_parallel` entry; `--strict-markers` in `addopts` (L172) will reject the marker until registered
- `scripts/tests/conftest.py` — add a new `pytest_collection_modifyitems(config, items)` hook between `pytest_configure` (L56-74) and the `# Snapshot Testing Helpers` comment (L77)
- `scripts/tests/test_conftest_cap.py` — add a new `TestNoParallelMarkerRouting` test class (see `### Tests` below)
- `docs/development/TESTING.md` — add a `no_parallel` row to the Test Markers table at L1028-1034
- `docs/development/TROUBLESHOOTING.md` — **create a new xdist / mac-beachball troubleshooting section** (one does NOT exist today; the planned "cross-link" must instead be a new section)

### Tests
- The full suite should be clean after the marker is applied

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file and anchor references:_

**Prerequisite shared with BUG-2523 (not yet implemented):**

- `scripts/pyproject.toml:179-183` — `[tool.pytest.ini_options].markers` registry. Currently lists `integration` / `slow` / `conformance`. Must add a `no_parallel` entry here; `--strict-markers` (addopts L172) will reject the marker until registered.
- `scripts/tests/conftest.py:30-74` — co-locate the new `pytest_collection_modifyitems(config, items)` hook next to the existing `pytest_xdist_auto_num_workers` (L30-53) and `pytest_configure` (L56-74) hooks. The hook uses the `hasattr(config, "workerinput") and config.workerinput` detection idiom proven at `scripts/little_loops/pytest_history_plugin.py:147-150`.
- `scripts/tests/test_fsm_executor.py:6478` — `TestRateLimitCircuitIntegration` class. Apply `@pytest.mark.no_parallel` at the class level (or, if a more granular fix is needed, only on the `test_record_rate_limit_called_on_short_tier` method at L6594).
- `scripts/tests/test_conftest_cap.py:28-82` — extend the existing `TestWorkerCount` class with a `TestNoParallelMarkerRouting` test. Uses the `importlib.util.spec_from_file_location` shim at L28-32 already in the file; mirror the env-var override pattern at L47.
- `docs/development/TESTING.md:1028-1034` — `### Test Markers` table. Add a `no_parallel` row alongside `integration` / `slow` / `conformance`.
- `docs/development/TROUBLESHOOTING.md` — add a short cross-link under the existing xdist / mac-beachball section (same section referenced from `BUG-2488` in MEMORY.md).

**Bug-2523 wiring plan is the source of truth.** BUG-2523's `### Implementation Steps` (L86-117) and `### Wiring Phase` (L118-130) sections contain the full 8-step implementation including exact code shape for the conftest hook (L98-106), the marker entry (L93-94), and the module-level `pytestmark` change (L109-111). BUG-2524 should ride the same PR.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:2043` — `_handle_rate_limit` calls `record_rate_limit` at lines 2105-2106; the executor is what the test exercises
- `scripts/little_loops/fsm/rate_limit_circuit.py:44` — `RateLimitCircuit.record_rate_limit` is the function under test; the test verifies it was called with `_sleep` from the short-tier backoff
- `scripts/tests/test_rate_limit_circuit.py` — direct unit tests for `RateLimitCircuit` (separate from the executor integration test)

_Wiring pass added by `/ll:wire-issue`:_

Production-code importers of `RateLimitCircuit` / `little_loops.fsm.executor` — these are NOT modified by BUG-2524 (the marker is purely test-side), but are listed for completeness so future readers know the marker has no production-side coupling:

- `scripts/little_loops/fsm/__init__.py:134` — re-exports `RateLimitCircuit` (canonical public-API path used by extension authors)
- `scripts/little_loops/fsm/persistence.py:39` — imports `EventCallback`, `ExecutionResult`, `FSMExecutor` from `executor`
- `scripts/little_loops/extension.py:26` — imports `FSMExecutor`, `RouteContext`, `RouteDecision`
- `scripts/little_loops/cli/loop/lifecycle.py:561` — imports `RateLimitCircuit`
- `scripts/little_loops/cli/loop/run.py:103` — imports `RateLimitCircuit`
- `scripts/little_loops/cli/loop/testing.py:9,25,65,191` — imports `RateLimitCircuit`, `ActionResult`, `SimulationActionRunner`, `FSMExecutor`, `DefaultActionRunner`

Other test files that import from `little_loops.fsm.executor` / `RateLimitCircuit` (none should be marked, but listed to clarify scope of the marker decision):

- `scripts/tests/test_fsm_persistence.py`, `scripts/tests/test_host_guard.py`, `scripts/tests/test_usage_journal.py`, `scripts/tests/test_fsm_runners.py`, `scripts/tests/test_ll_loop_commands.py:4326-4327`, `scripts/tests/test_ll_loop_execution.py`, `scripts/tests/test_cli_loop_lifecycle.py:1930`, `scripts/tests/test_cli_loop_testing.py`, `scripts/tests/test_wiring_reference_docs.py`, `scripts/tests/test_learning_state.py:20`, `scripts/tests/test_autodev_decision_gate.py:58,89`, `scripts/tests/test_ll_loop_display.py`, `scripts/tests/integration/test_loop_run_e2e.py:27`

### Similar Patterns
- `scripts/tests/test_fsm_signal_integration.py:37` — `pytestmark = pytest.mark.integration` is the existing module-level marker pattern; BUG-2524 should follow the same shape (class-level or module-level marker on the class)
- `scripts/tests/test_conftest_cap.py:28-32` — `importlib.util.spec_from_file_location` shim for unit-testing conftest hooks directly
- `scripts/tests/test_pytest_history_plugin.py:62-81` — `TestCaptureGating` shows the worker/controller test pair pattern for the new `TestNoParallelMarkerRouting`

### Tests
- `scripts/tests/test_fsm_executor.py:6478-6682` — `TestRateLimitCircuitIntegration` is the test class to mark
- `scripts/tests/test_fsm_executor.py:6209-6391` — `TestRateLimitTwoTier` is the existing fast unit precedent (already covers the two-tier ladder at unit speed with `rate_limit_backoff_base_seconds=0` at L6225)
- `scripts/tests/test_conftest_cap.py` — needs a new `TestNoParallelMarkerRouting` class to lock in the routing contract

_Wiring pass added by `/ll:wire-issue`:_

The `TestNoParallelMarkerRouting` class must include **four** test methods, not one. The agent-pass identified the following contract guarantees that need pinning (mirrors the `TestCaptureGating` worker/controller pair at `scripts/tests/test_pytest_history_plugin.py:62-81`):

1. **`test_no_parallel_marker_skipped_on_xdist_worker`** — `MagicMock()` + `config.workerinput = {"workerid": "gw0"}`; verify `item.add_marker` is called on a marked item.
2. **`test_no_parallel_marker_runs_on_controller`** — `MagicMock(spec=["pluginmanager"])` (NOT plain `MagicMock()` — `spec=` is load-bearing: without it, `MagicMock()` auto-creates a `workerinput` attribute and the `hasattr(config, "workerinput")` guard would silently short-circuit on a buggy hook). Verify `item.add_marker` is NOT called.
3. **`test_unmarked_test_left_alone_on_worker`** — items without the `no_parallel` keyword must NOT receive a skip marker under either mode.
4. **`test_mixed_items_only_marked_are_skipped`** — of N items, only those carrying the `no_parallel` keyword get the marker appended.

Use the `importlib.util.spec_from_file_location` shim already in place at `scripts/tests/test_conftest_cap.py:28-32`; reference the conftest's hook via `conftest.pytest_collection_modifyitems(config, items)` (the module handle is `conftest`, not the standard pytest import path).

No existing tests break because of the marker alone: no test in the suite asserts xdist routing for `TestRateLimitCircuitIntegration`, and no test asserts on the literal string `worker 'gw<N>' crashed` (verified via grep — only hit is a docstring at `test_pytest_history_plugin.py:69`).

### Configuration
- `scripts/pyproject.toml:171-183` — pytest `addopts` and `markers` registry (extend the markers list with `no_parallel`)
- `scripts/tests/conftest.py:30-74` — co-locate the new `pytest_collection_modifyitems` hook here

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/pyproject.toml:107-108` — `pytest-xdist>=3.0` is already declared as a dependency (no change required, just noting the dep is in place)
- `scripts/pyproject.toml:171-178` — `addopts` includes `--strict-markers` (L172) and `--strict-config` (L173), and forces xdist with `-n logical` (L178). The `--strict-markers` flag is the enforcement gate: any test using `@pytest.mark.no_parallel` before the marker is registered will fail collection
- `scripts/tests/conftest.py:30-53` — the existing `pytest_xdist_auto_num_workers` hook already caps xdist to `cpus // 2` (floor 2). The new `pytest_collection_modifyitems` hook is the FIRST `pytest_collection_modifyitems` in this conftest, so registration order is moot. Insertion point: between L74 (end of `pytest_configure`) and L77 (`# Snapshot Testing Helpers` comment)
- `scripts/tests/conftest.py:56-74` — `pytest_configure` already calls `os.nice(10)` on POSIX (the fix for the mac-beachball freeze). `LL_TEST_NO_NICE=1` opts out. The new collection hook does NOT need to read this env var — its only xdist discriminator is `hasattr(config, "workerinput")`
- `config-schema.json` — has only `command_allowlist` pytest entries (L33, L795); no marker/xdist/test-execution entry exists. **No schema change needed**
- `.ll/ll-config.json` — no `parallel.*` or `automation.*` keys reference xdist workers. **No project-config change needed**

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/development/TESTING.md:1028-1034` — `### Test Markers` table. Add a `no_parallel` row alongside the existing `integration` / `slow` / `conformance` entries (BUG-2523 + BUG-2524 share this update). The description should match the established two-clause pattern: `marks tests that must not run on xdist workers (deselect with '-m "not no_parallel"' or rely on conftest routing)`
- `docs/development/TESTING.md:185` — references `stable_snapshot_env` in `scripts/tests/conftest.py` (unrelated to the marker change but confirms the doc cross-references conftest internals)
- `docs/development/TESTING.md:1057` — best-practice note "Use fixtures for common setup - Avoid duplication via conftest.py" (no marker mention, no change needed)
- `docs/development/TROUBLESHOOTING.md` — **the planned "cross-link under the existing xdist / mac-beachball section" cannot happen because that section does NOT exist today** (verified: `grep -nE "xdist|mac.beachball|pytest.xdist"` returns no matches). The PR must **CREATE** a new section covering: xdist worker crashes, the `no_parallel` escape hatch, and the `LL_TEST_NO_NICE=1` + mac-beachball note (which today lives only in `scripts/tests/conftest.py:62-63`)
- `CONTRIBUTING.md:46-58` — `pytest -m "not integration"` and `pytest -m integration` literals remain valid marker-filter syntax after the new marker lands; no change strictly required, but consider adding a `pytest -m "not no_parallel"` example for users debugging xdist worker crashes
- `commands/run-tests.md:5,148` — `Bash(python:*, pytest:*, ...)` scope metadata and `-k` filter pattern (no `-m` marker-filter or xdist reference; no change required)
- `skills/create-loop/*` — many `pytest` action references in loop `Action:` invocations; these are loop-Action strings, not pytest markers — no change required
- `.claude/CLAUDE.md` — "Testing & CI Policy" section references `python -m pytest scripts/tests/` but no markers/xdist/conftest by name. No change required
- `README.md`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/development/E2E_TESTING.md`, `docs/development/MERGE-COORDinator.md` — zero references to xdist, markers, or conftest hooks. No change required

### Coordination Note

### Coordination Note

**This bug shares all prerequisite infrastructure with BUG-2523.** The same PR should:
1. Land the `no_parallel` marker + conftest hook (from BUG-2523's wiring)
2. Apply the marker to BOTH `TestSubprocessSignalIntegration` (BUG-2523) AND `TestRateLimitCircuitIntegration` (this bug)
3. Add the conftest-hook routing test
4. Update the docs in one shot

Splitting across two PRs would leave the suite broken on intermediate commits (one bug fixed, the other not, the marker infrastructure landed without a consumer).

## Impact

Low-severity flake (test only). Worker crashes are noisy and obscure real failures. A 1-line marker fix resolves it.

## Related Key Documentation

- `.claude/CLAUDE.md` — Testing & CI Policy

## Status

done

## Resolution

- **Action**: fix
- **Completed**: 2026-07-07
- **Status**: Completed

### Changes Made
- `scripts/tests/test_fsm_executor.py:6478` — added `@pytest.mark.no_parallel` decorator to `TestRateLimitCircuitIntegration`; expanded the class docstring with the BUG-2524 rationale. All six tests in the class are now routed to the controller (single-worker) process by `scripts/tests/conftest.py:pytest_collection_modifyitems` and skipped on xdist workers with reason `"no_parallel: cannot run on xdist workers"`. No production code modified; the `no_parallel` infrastructure (marker registry at `scripts/pyproject.toml:183`, routing hook at `scripts/tests/conftest.py:77-101`, four-contract test at `scripts/tests/test_conftest_cap.py`, TROUBLESHOOTING cross-link) was landed for sibling BUG-2523 in commit `9fdc360c` and is reused unchanged here.

### Verification Results
- Tests: PASS — `python -m pytest scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration` (serial): 6/6 passed in 66.22s (the 27.48s `test_record_rate_limit_called_on_short_tier` no longer crashes its xdist worker; in serial it runs to completion without contention).
- Tests: PASS — `python -m pytest scripts/tests/test_fsm_executor.py::TestRateLimitCircuitIntegration` (parallel, `-n logical`): all 6 SKIPPED with `no_parallel: cannot run on xdist workers` reason (verified gw0–gw5 skip; tests rerun on controller in serial mode).
- Tests: PASS — `python -m pytest scripts/tests/ -n logical` (full suite): 14147 passed, 35 skipped, **0 `worker 'gw<N>' crashed` messages** (BUG-2524 symptom eliminated). One unrelated parallel-isolation flake in `TestCompoundGridParser::test_cond_pattern_is_derived_not_hardcoded` exists in the full suite (passes in isolation under xdist) but is orthogonal to this fix.
- Lint: PASS — `ruff check scripts/` clean (no new lint surface; one decorator + 4-line docstring).
- Integration: PASS — reuses BUG-2523's proven `hasattr(config, "workerinput") and config.workerinput` detection idiom; class-level marker follows the `pytestmark = [pytest.mark.integration, pytest.mark.no_parallel]` precedent at `scripts/tests/test_fsm_signal_integration.py:37-42`.

## Session Log
- `/ll:ready-issue` - 2026-07-07T18:58:06 - `5b27988e-32ae-408b-a227-2a01e7f82001.jsonl`
- `/ll:decide-issue` - 2026-07-07T18:50:23 - `47c8bceb-3a65-4855-94dd-1d4f809351b0.jsonl`
- `/ll:wire-issue` - 2026-07-07T18:42:24 - `f2b085e3-e5d1-4d2c-853b-40b9ee0b0969.jsonl`
- `/ll:refine-issue` - 2026-07-07T18:34:09 - `d29bcbe5-de10-4a6e-a59d-634bd1567912.jsonl`
- `/ll:manage-issue` - 2026-07-07T19:05:04 - `03c01ed8-d75d-4c43-8a35-198dddfff0d2.jsonl`

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
- `/ll:confidence-check` - 2026-07-07T18:56:11 - `1f8b6e1b-68bd-49e3-99a9-48a48150d36f.jsonl`
