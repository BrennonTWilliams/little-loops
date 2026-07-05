---
id: BUG-2484
title: Full test suite CPU-spikes from nested parallelism in test_hooks_integration.py
type: BUG
priority: P2
status: done
discovered_date: '2026-07-05'
discovered_by: user-report
captured_at: '2026-07-05T16:28:51Z'
completed_at: '2026-07-05T16:28:51Z'
labels:
- testing
- pytest
- performance
- ci
---

# BUG-2484: Full test suite CPU-spikes from nested parallelism in test_hooks_integration.py

## Summary

Running the full suite (`python -m pytest scripts/tests/`, the project's literal
CI gate per `.claude/CLAUDE.md`) pegs/spikes CPU hard enough to feel like it
"kills the CPU." The sustained ~14-core load from `-n logical` xdist is
expected and by design (already tuned for hyperthreaded hosts in commit
`28f22480`, one day prior). The unexpected part is periodic oversubscription
spikes on top of that baseline, caused by nested parallelism: several tests
spawn their own `ThreadPoolExecutor` pools of real `subprocess.run()` calls
(actual shell/hook script invocations, not mocked) from inside a test that is
already running under one of the 14 outer xdist worker processes.

## Root Cause

- **File**: `scripts/tests/test_hooks_integration.py`
- **Cause**: Despite its docstring ("Integration tests for hooks system
  robustness... concurrent access... race conditions"), the file carried
  **zero** `@pytest.mark.integration` markers — violating the project's own
  documented convention for real-threading tests (see
  `.issues/features/P2-FEAT-1205-*`, `P2-FEAT-1203-*`, `P2-FEAT-1208-*`).
  It contained four real-subprocess `ThreadPoolExecutor` blocks with
  oversized worker counts:
  - `test_hooks_integration.py:69` (was `max_workers=10`)
  - `test_hooks_integration.py:1612` (was `max_workers=5`)
  - `test_hooks_integration.py:2169` (was `max_workers=5`)
  - `test_hooks_integration.py:3783` (was `max_workers=10`)
  When several of these tests land on different xdist workers at the same
  moment, the machine briefly runs 14 (outer) + N×(inner pool size)
  processes concurrently — a real oversubscription spike on an
  already-saturated system.
- Compare with `scripts/tests/test_worktree_concurrency.py:70` (`K = 4`,
  correctly marked `pytestmark = pytest.mark.integration`), which documents
  that the concurrency factor only needs to be large enough to trigger the
  race under test, not to stampede the host.
- `test_pre_compact.py:232` and `test_state.py:426` also use
  `ThreadPoolExecutor(max_workers=5)` but call in-process Python functions
  (no subprocess spawn) — ruled out as CPU contributors.
- Marking the file `integration` alone does not reduce default-run CPU,
  since the `integration` marker is intentionally *not* excluded from the
  default `addopts` (integration tests are meant to run in the default/CI
  invocation to catch real OS-scheduling races). The actual lever is
  trimming worker counts down to the minimum needed to still exercise the
  race.

## Steps to Reproduce

1. Run `python -m pytest scripts/tests/` on a multi-core host.
2. Watch CPU load during the run — brief spikes beyond the steady ~14-core
   xdist baseline coincide with `test_hooks_integration.py` tests that use
   `ThreadPoolExecutor(max_workers=10)`.

## Expected Behavior

The full suite saturates all cores at a roughly steady level (the expected
cost of `-n logical`), without additional bursts from nested in-test
concurrency layered on top.

## Current Behavior

Four tests in `test_hooks_integration.py` each fan out 5-10 concurrent real
subprocess invocations from inside a single xdist worker, on top of the
14-way outer parallelism, producing intermittent CPU spikes/freezes.

## Impact

- **Priority**: P2 - Degrades local developer experience (machine
  unresponsiveness during routine test runs) but does not affect production
  behavior or correctness.
- **Effort**: Small - Confined to one test file; no production code touched.
- **Risk**: Low - Reduced concurrency factors still exceed the minimum needed
  to trigger the races under test (verified: all 108 tests in the file still
  pass).
- **Breaking Change**: No

## Resolution

- **`scripts/tests/test_hooks_integration.py`**
  - Added `pytestmark = pytest.mark.integration` at module level, aligning
    with `test_worktree_concurrency.py` / `test_git_lock.py`.
  - Reduced the two `max_workers=10` pools and two `max_workers=5` pools to
    `max_workers=4` (matching the `K = 4` precedent), updating `range(...)`
    calls and the dependent assertions/comments (`test_concurrent_updates`,
    `test_concurrent_duplicate_and_new_issue_creation`,
    `test_concurrent_precompact_writes`, `test_concurrent_writes_no_corruption`)
    so the tests still exercise concurrent-write/race behavior at the lower
    fan-out. Left the existing `max_workers=3` pool unchanged (already at/below
    the new ceiling).
- No changes needed to `test_pre_compact.py`, `test_state.py`, or
  `test_worktree_concurrency.py`.

### Files Changed
- `scripts/tests/test_hooks_integration.py`

### Verification Results
- `python -m pytest scripts/tests/test_hooks_integration.py -q` — 108 passed.
- `python -m pytest scripts/tests/test_hooks_integration.py -m "not integration" -q` —
  0 tests selected, confirming the documented fast dev-loop path
  (`pytest -m "not integration"`, per CONTRIBUTING.md /
  docs/development/TESTING.md) now correctly excludes this file.
- `ruff check scripts/tests/test_hooks_integration.py` — all checks passed.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-05T16:30:04 - `ed0af048-0f6a-4637-a24d-a7563d4c8d1a.jsonl`
- Investigated and fixed interactively in this session (plan-mode
  investigation → user-approved fix → applied and verified).

## Status

**Completed** | Created: 2026-07-05 | Completed: 2026-07-05 | Priority: P2
