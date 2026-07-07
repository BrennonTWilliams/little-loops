---
id: BUG-2523
title: SIGINT subprocess test flakes under xdist parallel load
type: BUG
priority: P2
status: open
discovered_date: 2026-07-07
discovered_by: capture-issue
testable: false
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

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_signal_integration.py` — add the no-parallel marker
- `scripts/pyproject.toml` — register the marker in `[tool.pytest.ini_options].markers` (if not present)

### Dependent Files (Callers/Importers)
- `scripts/tests/conftest.py` — may need a hook to interpret the marker for xdist

### Tests
- The marker test itself: run full suite, confirm the test still passes

### Documentation
- `docs/development/TROUBLESHOOTING.md` — note the marker for future signal-handling tests

## Impact

Low-severity flake (test only, not production) but high CI-noise: every full-suite run has a 1-in-N chance of false-positive failure, requiring re-runs. Marking the test as no-parallel is a 1-line fix.

## Related Key Documentation

- `.claude/CLAUDE.md` — Testing & CI Policy section
- `docs/development/TROUBLESHOOTING.md`

## Status

open

## Session Log

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
