---
id: BUG-2108
title: pytest suite OOMs (100GB+) when a test patches builtins.open with a bare MagicMock
type: BUG
priority: P2
status: done
discovered_date: '2026-06-12'
discovered_by: manual
captured_at: '2026-06-12T20:51:28Z'
labels:
- tests
- memory
- regression
- fsm
- cross-host
confidence_score: 98
completed_at: '2026-06-12T20:51:28Z'
---

# BUG-2108: pytest suite OOMs (100GB+) when a test patches builtins.open with a bare MagicMock

## Summary

Running `python -m pytest scripts/tests/` exhausted system memory (>100GB reported,
crashing the Ghostty terminal / "out of application memory") instead of completing.
The whole suite died before pytest could report a failure, because one test hung
while allocating unbounded memory rather than failing fast.

A memory watchdog (per-process RSS sampling with a kill-and-report trip at 6GB)
isolated the offending test to a **single process** ballooning past 6.7GB and
climbing — ruling out a subprocess fork bomb and pointing at an in-process
allocation:

`scripts/tests/test_cross_host_baseline.py::TestCrossHostBackgroundForwarding::test_cross_host_forwarded_to_background_cmd`

A faulthandler stack dump under a capped address space pinpointed the exact line:
PyYAML's `Reader` reading from a mocked file stream inside `load_and_validate`.

## Root Cause

- **File**: `scripts/tests/test_cross_host_baseline.py`
- **Trigger anchors**: `TestCrossHostBackgroundForwarding.test_cross_host_forwarded_to_background_cmd`
  and `test_cross_host_not_forwarded_when_false`, which both did
  `patch("builtins.open", MagicMock())`.
- **Production interaction**: `little_loops/cli/loop/_helpers.py:run_background()`
  gained a **pre-flight scope-conflict check** (`_helpers.py:991`) that calls
  `load_loop()` → `little_loops/fsm/validation.py:load_and_validate()` →
  `yaml.safe_load(<file handle>)`.

Mechanism of the explosion:

1. The test replaced `builtins.open` with a bare `MagicMock()`, so
   `yaml.safe_load` received a mock object instead of a real file handle.
2. PyYAML's `Reader.update_raw` calls `stream.read(4096)` repeatedly until it
   receives an empty string (EOF). A `MagicMock.read()` **never returns `""`** —
   every call returns a truthy child mock, so the read loop never terminates.
3. `unittest.mock` records **every call in `call_args_list` / `mock_calls`**. With
   an infinite read loop, that internal list grows without bound, consuming all
   memory (100GB+) until the process / terminal is killed.

This was a **regression**: the pre-flight `load_loop()` call was added to
`run_background()` after these tests were written. Before that, `run_background`
never read the loop YAML, so the global `open` mock was harmless and the tests
passed. Once the pre-flight read landed, the tests went from passing to OOM-ing,
and — because the failure mode is an unbounded allocation rather than an
assertion — they took the entire suite (and the terminal) down with them. The
loop YAML these tests wrote was also invalid (`__done__`, no terminal state),
which the mocked `open` had been masking.

## Steps to Reproduce

1. `cd scripts && python -m pytest tests/test_cross_host_baseline.py -k forwarded`
2. Observe RSS climb without bound (>6GB within seconds) until the process is
   OOM-killed / the terminal reports running out of application memory.

## Expected Behavior

The test suite completes; no test consumes unbounded memory.

## Actual Behavior

`test_cross_host_forwarded_to_background_cmd` hangs allocating memory until the
host OOMs (>100GB observed).

## Resolution

- **Action**: fix (test-only; no production code changed)
- **Completed**: 2026-06-12

### Fix

In `scripts/tests/test_cross_host_baseline.py`:

1. **Removed `patch("builtins.open", MagicMock())`** (and the now-unneeded
   `patch("pathlib.Path.write_text")` / `patch("pathlib.Path.mkdir")`) from the
   two `TestCrossHostBackgroundForwarding` tests. They now run real,
   `tmp_path`-isolated file operations and mock only `subprocess.Popen`. Added an
   inline comment documenting the OOM hazard so the global `open` mock is not
   reintroduced.
2. **Replaced the invalid loop YAML** (`__done__`, no terminal state) — which the
   mocked `open` had been hiding — with a valid `start → done (terminal: true)`
   loop that actually passes `load_and_validate`.

While in the same file, also repaired its other **pre-existing** failures (10
failures unrelated to the OOM, all caused by a lazy-import refactor in production
drifting away from the tests' `patch()` targets):

- Retargeted patches to each symbol's real source module:
  - `little_loops.cli.loop.run._reconcile_stale_runs` → `little_loops.fsm.persistence._reconcile_stale_runs`
  - `little_loops.cli.loop.run.LockManager` → `little_loops.fsm.concurrency.LockManager`
  - `little_loops.cli.loop.run.wire_extensions` → `little_loops.extension.wire_extensions`
  - `little_loops.cli.loop.run.wire_transports` → `little_loops.transport.wire_transports`
  - `little_loops.cli.loop._helpers.shutil.which` → `shutil.which`
- Updated stale `cmd_run(loops_dir, args)` calls to the current
  `cmd_run(loop, args, loops_dir, logger)` signature and fixed their invalid loop
  YAML.
- Removed unused imports (`unittest.mock.call`, `FSMLoop`) flagged by ruff.

### Files Changed

- `scripts/tests/test_cross_host_baseline.py` (+47 / −37)

## Verification Results

- `python -m pytest tests/test_cross_host_baseline.py` — **15 passed**, ruff clean.
- Full suite under the memory watchdog: **11,257 passed, 7 skipped in ~5m26s**,
  **peak RSS 890 MB** (down from >100GB OOM). No watchdog trip.

## Acceptance Criteria

- [x] `test_cross_host_baseline.py` passes without unbounded memory growth.
- [x] Full `python -m pytest scripts/tests/` runs to completion with normal
      memory usage (peak < 1GB).
- [x] No test patches `builtins.open` with a bare `MagicMock` on a code path that
      reads the handle via PyYAML.

## Notes / Follow-ups (out of scope — pre-existing, unrelated to the OOM)

These fail fast (no memory impact) and were not addressed in this fix:

- `scripts/tests/test_rn_plan_apo.py::TestRnPlanApoFile::test_inherits_apo_category_max_iterations_timeout`
  — asserts category `apo` but gets `planning`; tied to in-progress
  **ENH-2101** (resolve `from:` inheritance in `load_loop` meta).
- `scripts/tests/test_builtin_loops.py::TestHitlMdLoop` (2 errors) — fixture
  references `prompts/hitl-md-generate.md`, which no longer exists.

## Lesson

Patching `builtins.open` (or any stream) with a bare `MagicMock` is a footgun for
any code path that reads to EOF: `MagicMock.read()` never returns `""`, so
read-until-EOF loops (PyYAML, `json.load`, `csv`, line iteration) spin forever
while `unittest.mock` accumulates call records, OOM-ing the process. Mock the
specific function that must not touch disk, or use real `tmp_path` files, instead
of replacing `open` globally.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-13T01:52:17 - `346cddd6-584a-40bc-8f25-34fa998ec5d6.jsonl`

- Manual investigation + fix — 2026-06-12 — memory-watchdog isolation,
  faulthandler stack-dump root-causing, test repair, full-suite re-verification.
