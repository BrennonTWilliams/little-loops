---
id: BUG-2524
title: xdist worker crashes on long-running rate-limit test
type: BUG
priority: P3
status: open
discovered_date: 2026-07-07
discovered_by: capture-issue
testable: false
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

## Location

- **File**: `scripts/tests/test_fsm_executor.py`
- **Line(s)**: the `test_record_rate_limit_called_on_short_tier` method
- **Anchor**: `TestRateLimitCircuitIntegration.test_record_rate_limit_called_on_short_tier`

## Implementation Steps

1. Investigate why the test takes 27.48s — likely a sleep or rate-limit backoff that doesn't need real-time waiting (use `freezegun` or `monkeypatch` to skip).
2. If shortening isn't feasible, apply the same no-parallel marker as BUG-2523 to the test class.
3. Verify the full suite runs cleanly: `python -m pytest scripts/tests/ -n auto`.

## Integration Map

### Files to Modify
- `scripts/tests/test_fsm_executor.py` — add the no-parallel marker
- Optionally: speed up the test by mocking time/backoff

### Tests
- The full suite should be clean after the marker is applied

## Impact

Low-severity flake (test only). Worker crashes are noisy and obscure real failures. A 1-line marker fix resolves it.

## Related Key Documentation

- `.claude/CLAUDE.md` — Testing & CI Policy

## Status

open

## Session Log

- `/ll:capture-issue` - 2026-07-07T00:00:00Z - `agents:session-log-placeholder`
