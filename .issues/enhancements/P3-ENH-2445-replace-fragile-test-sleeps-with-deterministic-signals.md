---
id: ENH-2445
title: Replace fragile test sleeps with deterministic signals and parallelize via pytest-xdist
type: ENH
status: done
priority: P3
captured_at: '2026-07-02T20:35:05Z'
completed_at: 2026-07-02 20:35:05+00:00
discovered_date: 2026-07-02
discovered_by: manual
labels:
- enhancement
- tests
- performance
- infrastructure
- deterministic-testing
- pytest-xdist
relates_to:
- ENH-2404
- ENH-2405
decision_needed: false
confidence_score: 95
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 22
---

# ENH-2445: Replace fragile test sleeps with deterministic signals and parallelize via pytest-xdist

## Summary

Three classes of fragile `time.sleep()` waits in the test suite masked flakiness
and added ~2-3 seconds of dead time per run:

1. **`TestMakeInstanceId::test_successive_calls_are_unique`** — `time.sleep(1.05)`
   to cross a one-second timestamp boundary. Replaced by monkeypatching
   `datetime.now()` to return two frozen instants. The test now completes in
   microseconds and is fully deterministic.
2. **`TestContextMonitor`** — `time.sleep(1.1)` to let the transcript file's
   mtime advance past filesystem resolution. Replaced by writing the
   transcript then forcing `st_mtime` forward with `os.utime`. Instant and
   deterministic.
3. **`TestUnixSocketTransport`** — six fixed `time.sleep()` calls (200-300ms
   each) waiting on the background accept loop to register / unregister
   clients. Replaced with a `_wait_until(predicate, timeout, interval)`
   helper plus a `_client_count(t)` accessor under the existing
   `_clients_lock`. Tests now return as soon as the accept loop catches up
   (typically single-digit ms) and fail loudly instead of silently racing the
   timeout.

## Current Behavior

- `time.sleep(1.05)` and `time.sleep(1.1)` in two unrelated tests burned
  ~2.15s per full run purely to cross a calendar/FS-resolution boundary —
  slow AND environment-dependent.
- `TestUnixSocketTransport` had six `time.sleep(0.2|0.3|0.08)` calls that
  were either too short (race) or too long (dead time). Either failure mode
  is invisible until CI load drifts.
- The suite ran serially under `[tool.pytest.ini_options].addopts` with
  `--cov=little_loops` + `--cov-report=term-missing:skip-covered` +
  `--cov-report=html` always on, adding 30-100% instrumentation overhead
  to every invocation including `pytest -x -k some_test`.

## Expected Behavior

- All three sleep patterns replaced by deterministic signals (frozen clock,
  `os.utime` mtime bump, polling predicate with explicit timeout).
- `pytest-xdist` enabled via `-n auto` — the suite fans out across CPU cores
  by default.
- Coverage is opt-in; the `addopts` block carries an inline comment with the
  invocation recipe for contributors who want a coverage report.
- `[tool.mutmut.pytest_add_cli_args]` adds `-n0` so per-mutant runs stay
  serial (mutant subsets are tiny; worker spawn would dominate).
- The latent test bug — the post-close wait predicate in
  `test_client_disconnect_does_not_affect_other_clients` — is fixed by
  reordering: the send that triggers cleanup now precedes the wait.

## Impact

- ~2-3 seconds of dead time removed from the deterministic tests; the
  broader wall-clock win comes from `-n auto` (full serial suite was 7m27s).
- Pre-existing `test_cli_ctx_stats.py::TestLearningTestsSection` failures
  are unrelated and remain in their pre-fix state.
- No production code changed; only `scripts/pyproject.toml` (test infra
  config) and three test files.

## Scope Boundaries

- In scope: `time.sleep()` waits in `test_cli_loop_background.py`,
  `test_hooks_integration.py`, `test_transport.py`; `[tool.pytest.ini_options]` and
  `[tool.mutmut]` config in `pyproject.toml`; new `_wait_until` /
  `_client_count` helpers in `test_transport.py`.
- Out of scope: other test files that may still have similar fragile sleeps
  (none surfaced during this pass); production code; CI workflow files
  (none added — the project's "no hosted CI" rule holds; the local pytest
  suite *is* the gate per `.claude/CLAUDE.md`).
- Does not touch: the `coverage` package config (still in
  `[tool.coverage.*]` — applies when `--cov` is passed), the `pytest-cov`
  plugin (still installed), or the existing `scripts/tests/` discovery
  settings.

## Status

Done. Commit `fffea99d perf(tests): replace fixed sleeps with deterministic
signals + parallelize` lands all four file changes; the 76 tests in the
touched files pass; the full suite shows 13,466 passed / 23 skipped with
only the two pre-existing `TestLearningTestsSection` failures (unrelated,
predate this change).

## Also included

- **Added `pytest-xdist>=3.0` to dev deps** and switched `[tool.pytest.ini_options].addopts`
  from `--cov=...` + `--cov-report=...` to `-n auto`. The suite now runs
  across all CPU cores. Coverage is opt-in (the addopts comment shows the
  invocation: `python -m pytest scripts/tests/ --cov=little_loops ...`) —
  the 30-100% instrumentation overhead no longer hits every run.
- **`[tool.mutmut.pytest_add_cli_args]`** now passes `-n0` so per-mutant
  runs are serial. Each mutant exercises a tiny test subset where worker
  spawn cost would outweigh any parallelism gain.

## Latent bug surfaced by the swap

While converting the post-`c1.close()` sleep in
`test_client_disconnect_does_not_affect_other_clients`, the new
`_wait_until(lambda: _client_count(t) == 1)` predicate hung for the full
2.0s timeout. Root cause: `UnixSocketTransport._client_loop` only removes a
client from `_clients` when its `sendall()` raises `OSError` on the closed
socket, and that only happens on the *next* `send()` attempt. The wait
predicate is correct; it just needs to fire after the cleanup trigger.

**Fix**: reordered the test so `t.send({"event": "after-disconnect"})` runs
*before* `_wait_until(...)`. The send triggers c1's `sendall` failure, the
cleanup runs in the client thread, and the wait predicate then returns
truthy as soon as the lock is released. Net effect: the test now
deterministically verifies both (a) c2 still receives the event after c1
disconnects and (b) c1 is removed from `_clients` post-send.

## Files touched

| File | Change |
|------|--------|
| `scripts/pyproject.toml` | +`pytest-xdist` dep; `-n auto` in addopts; coverage moved to opt-in; mutmut gets `-n0` |
| `scripts/tests/test_cli_loop_background.py` | Frozen-clock `_make_instance_id` test |
| `scripts/tests/test_hooks_integration.py` | `os.utime` mtime bump in `TestContextMonitor` |
| `scripts/tests/test_transport.py` | `_wait_until` / `_client_count` helpers; conditional waits; send-then-wait reorder |

## Verification

- All 76 tests in the four changed files pass.
- Full suite: **13,466 passed, 23 skipped**, **2 failed** (both pre-existing
  in `test_cli_ctx_stats.py::TestLearningTestsSection` —
  `test_counts_shown_correctly` and `test_json_mode_includes_learning_tests`,
  reproduced on `main` without these changes; tracked separately).
- Wall-clock for the full serial run was ~7m27s; the parallel `-n auto`
  invocation is the new default and should land meaningfully under that.

## Related

- **ENH-2404 / ENH-2405** — prior passes that also touched this surface
  (deterministic-test patterns in the suite).
- The pre-existing `test_cli_ctx_stats.py::TestLearningTestsSection`
  failures are unrelated — they predate this commit.

## Commit

`fffea99d perf(tests): replace fixed sleeps with deterministic signals + parallelize`

## Session Log
- `hook:posttooluse-status-done` - 2026-07-02T20:35:28 - `12657876-3ce9-4408-aa71-8eb240d661a1.jsonl`
