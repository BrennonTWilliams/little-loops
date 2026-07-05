---
id: BUG-2489
title: Event-bus lifecycle test fails under some xdist shardings (test-isolation leak)
type: BUG
priority: P2
status: open
discovered_date: '2026-07-05'
discovered_by: capture-issue
captured_at: '2026-07-05T23:16:24Z'
labels:
- testing
- pytest
- flaky
- test-isolation
---

# BUG-2489: Event-bus lifecycle test fails under some xdist shardings (test-isolation leak)

## Summary

`scripts/tests/test_issue_lifecycle.py::TestEventBusEmission::test_complete_issue_lifecycle_emits_event`
fails **nondeterministically** in a full-suite run depending on how pytest-xdist
shards tests across workers. It **passes 100% in isolation** (3/3) and under
serial `-n 0`. Because the full suite is the project's literal CI gate
(`python -m pytest scripts/tests/`), an intermittent failure here poisons the
green-suite signal developers rely on.

The failure was surfaced (not caused) while tuning the xdist worker count to fix
the macOS "beachball" freeze: the suite passed at 10 workers and at 4 workers,
then this test failed once at 7 workers. Changing the worker count only reshards
which tests co-locate in a worker — so a different worker layout exposes a
pre-existing cross-test state leak.

## Root Cause

Not yet fully isolated — to be pinned during the fix. The signature is a classic
**test-isolation leak**: the test constructs its **own** local `EventBus()` (see
`test_issue_lifecycle.py:1320` `TestEventBusEmission`), so the defect is not in
`little_loops.events.EventBus` itself. The likely culprits, in order:

- An **unrestored patch / monkeypatch** from another test file that lands in the
  same xdist worker (e.g. a `patch("subprocess.run", ...)` or a module attribute
  left mutated), altering `close_issue` / `complete_issue` behavior or the
  emitted payload.
- A **frozen/fixed-time or env leak**: the sibling test
  `test_close_issue_emits_event` asserts `event["captured_at"] == "2026-05-20T10:00:00Z"`,
  implying a pinned timestamp source that another test could perturb.
- A leaked global consumed by `state.py:106-107` (`self._event_bus.emit(...)`)
  or the lifecycle helpers.

Confirm by reproducing with a fixed shard layout, e.g.
`pytest scripts/tests/ -p xdist -n 7` repeatedly, or
`pytest --dist=loadfile ...` vs `--dist=load ...`, and by bisecting which sibling
test file, when co-located, triggers the failure.

## Current Behavior

Full-suite run intermittently reports:
```
FAILED scripts/tests/test_issue_lifecycle.py::TestEventBusEmission::test_complete_issue_lifecycle_emits_event
1 failed, 13738 passed, 27 skipped
```
The same test passes deterministically when run alone or serially.

## Expected Behavior

The test passes deterministically regardless of xdist worker count or which
tests share its worker. Each test fully sets up and tears down its own state
(patches restored, time/env pinned locally) with no dependence on execution
order or co-location.

## Motivation

The full suite is the sole CI gate for this project (no hosted CI, per
`.claude/CLAUDE.md`). A sharding-dependent flake means a clean branch can go
red purely from a worker-count change, eroding trust in the gate and forcing
re-runs. Fixing the leak also hardens the suite against future `-n` retuning
(the beachball fix now defaults to `cpus // 2` workers, so shard layouts will
differ from historical `-n logical`).

## Proposed Solution

1. Reproduce deterministically: run the full suite (or the offending file plus
   suspected siblings) under a fixed shard layout until it fails; capture the
   co-located file set.
2. Bisect to the leaking sibling test/file (`-p no:randomly` if applicable;
   `--dist=loadfile` groups a file onto one worker, which may make the leak
   reproducible or disappear — a useful signal).
3. Fix the leak at its source — prefer an `autouse` teardown / `monkeypatch`
   (auto-reverted) over manual `patch()` in the offending test, and pin any
   time source via a fixture rather than a module global.
4. Add a regression guard: assert the relevant global/module state is clean at
   the offending test's entry, or mark the emission tests to run isolated if a
   shared resource is genuinely required.

## Steps to Reproduce

1. `python -m pytest scripts/tests/ -q` on a 14-core host (default cap now 7
   workers via `tests/conftest.py`).
2. Observe intermittent failure of
   `TestEventBusEmission::test_complete_issue_lifecycle_emits_event`.
3. Confirm it passes in isolation: `pytest ".../test_complete_issue_lifecycle_emits_event" -n 0` → passes 3/3.

## Impact

- **Priority**: P2 — intermittently red CI gate; no production/runtime impact.
- **Effort**: Small–Medium — confined to test setup/teardown once the leaking
  sibling is identified; no production code expected to change.
- **Risk**: Low.
- **Breaking Change**: No.

## Related

- Follows the beachball fix (worker cap `cpus // 2` + `os.nice` renice in
  `scripts/tests/conftest.py`) that changed the default shard layout and exposed
  this flake.
- Related test-isolation work: BUG-1995 (pytest opened the real history DB).

## Session Log
- `/ll:capture-issue` - 2026-07-05T23:16:24Z - `2245c1db-2bf4-4e02-8b9e-f6247f6790e2.jsonl`

## Status

**Open** | Created: 2026-07-05 | Priority: P2
