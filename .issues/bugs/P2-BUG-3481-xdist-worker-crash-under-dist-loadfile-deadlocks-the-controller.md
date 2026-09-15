---
id: BUG-3481
type: BUG
title: xdist worker crash under --dist loadfile deadlocks the controller (replacement
  worker gets empty runtests)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T21:54:42Z'
program_design_not_applicable: true
confidence_score: 98
outcome_confidence: 91
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 22
---

# BUG-3481: xdist worker crash under --dist loadfile deadlocks the controller (replacement worker gets empty runtests)

## Summary

`python -m pytest scripts/tests/` can wedge permanently: when any xdist worker
process dies mid-run (`[gwN] node down: Not properly terminated`), the
controller spawns a replacement worker, hands it an already-completed work
unit, and then both sides wait on each other forever at 0% CPU with no exit
code. Observed live during `ll-auto --only ENH-3480` (2026-09-15): PID 54510 +
6 xdist children sat idle for 20+ minutes before being killed manually.

This is distinct from the closed BUG-3208 (stale pytest 9 + xdist 3.8.0,
workers busy-spinning at 97-99% CPU). This machine has the BUG-3208-safe pins
(`pytest==8.4.2`, `pytest-xdist==3.7.0`) and the wedge still occurs, with
workers truly idle. The two are told apart by CPU state: idle-0% here,
busy-spin-97-99% there.

The root cause is an upstream `pytest-xdist` scheduler bug in
`LoadScopeScheduling` (the class behind `--dist loadfile`, `loadscope`, and
`loadgroup`), reproduced deterministically in ~3 seconds with a 34-test
synthetic tree (see Steps to Reproduce). It is not caused by a slow test, by
`-x`, or by the `--timeout=120` value.

## Current Behavior

Tail of `.loops/tmp/scratch/enh3480-test-results.txt` from the wedged run:

```
...................................................ss................... [ 99%]
....[gw4] node down: Not properly terminated
F<site-packages>/pytest_benchmark/logger.py:44: PytestBenchmarkWarning: ...
.................. <site-packages>/_pytest/main.py:324: PluggyTeardownRaisedWarning: A plugin raised an exception during an old-style hookwrapper teardown.
Plugin: 4830002544, Hook: pytest_sessionfinish
OSError: cannot send (already closed?)
```

Reading that trace against the xdist 3.7.0 source: the `F` is the crash item
reported failed; the second `PytestBenchmarkWarning` is the replacement worker
starting up; the 18 dots are it running a re-queued unit; then nothing. `ps`
showed the controller and all 6 `[pytest-xdist idle]` workers alive at 0% CPU
(`SN` state) for 20+ minutes. No memory pressure, no OOM/jetsam kill in
`log show` for the window.

Note: under xdist, worker fd 1 is redirected to `/dev/null` by execnet, so
pytest-timeout's `+++ Timeout +++` stack dump from `--timeout-method=thread`
is never visible in the output. The absence of a dump in the scratch file does
not tell us whether the 120s watchdog fired; the specific test that killed
`gw4` in the ENH-3480 run is unknown and cannot be recovered from that log.

## Expected Behavior

A worker crash mid-run must not silently wedge the whole session. The run
must return a non-zero exit code within a bounded time, and the failure
report must name the test the worker was running when it died, so the
`ready-issue` / `manage-issue` / epic-verify gates (which all read the suite's
exit code) fail loudly instead of stalling until `run_claude_command`'s
`timeout=7200` default kills the host session two hours later.

## Motivation

Same motivation as BUG-3208: the full suite *is* this project's CI (no hosted
runner per `.claude/CLAUDE.md` § Testing & CI Policy), so a wedge here is a
silent total outage of the merge gate. This is the second distinct root cause
to produce the identical externally-visible symptom (a session "waiting for
the background test run" forever), so without a fix it will keep recurring
and keep being misdiagnosed as BUG-3208.

## Root Cause

- **File**: `<site-packages>/xdist/scheduler/loadscope.py` (`pytest-xdist` 3.7.0),
  `LoadScopeScheduling.remove_node` and `LoadScopeScheduling._assign_work_unit`;
  driven from `<site-packages>/xdist/dsession.py` `DSession.worker_errordown`.
- **Anchor**: `remove_node` (loadscope.py:166-204) re-queues the crashed
  worker's **entire** `assigned_work` workload with `self.workqueue.update(workload)`
  (loadscope.py:200), including work units (files) the worker had already
  fully completed. `mark_test_complete` only flips items to `True`; it never
  pops a finished unit out of `assigned_work`.
- **Cause**: `worker_errordown` (dsession.py:238-267) clones a replacement
  worker. When it finishes collecting, `_reschedule` pops the first re-queued
  unit, which is a fully-completed file, and `_assign_work_unit`
  (loadscope.py:263-282) computes `nodeids_indexes = []` and sends
  `runtests(indices=[])`. The worker's `torun` queue receives no items, so it
  never emits `runtest_protocol_complete`; the controller therefore never
  calls `mark_test_complete` → `_reschedule` again, the real pending unit is
  never assigned, and `tests_finished` stays `False` (non-empty `workqueue`).
  Controller spins in `queue.get(timeout=2.0)`, worker spins in its main
  loop, both idle. Confirmed with `--debug`: the last controller event is
  `[workerctl-gw1] sending command runtests(**{'indices': []})`.
- **Trigger condition**: any worker process death (thread-method timeout
  `os._exit(1)`, a test calling `os._exit`, a segfault) after that worker has
  completed at least one file, which under `--dist loadfile` is nearly
  always. `--dist load` (`LoadScheduling`) is unaffected because its
  `remove_node` re-queues only pending indices.
- **Upstream**: pytest-dev/pytest-xdist issues #784 and #1327; fixed by
  PRs #1328 and #1371 on master. Not in any release through 3.8.0
  (2025-06-30), so lifting the `pytest-xdist<3.8` pin does not help.

## Steps to Reproduce

Deterministic, ~3 seconds, no project conftest involved:

```bash
mkdir -p /tmp/xrepro && cd /tmp/xrepro
printf '[pytest]\naddopts = -p no:cacheprovider -p no:benchmark\n' > pytest.ini
for i in 1 2 3; do printf 'import pytest\n@pytest.mark.parametrize("n", range(10))\ndef test_fast(n): assert True\n' > test_fast$i.py; done
cat > test_crash_exit.py <<'EOF'
import os, time
def test_a(): pass
def test_b():
    time.sleep(2); os._exit(1)
def test_c(): pass
def test_d(): pass
EOF
timeout 60 python -m pytest -c pytest.ini --rootdir=. test_fast*.py test_crash_exit.py \
  -n 3 --dist loadfile --timeout=5 --timeout-method=thread -q
echo "exit=$?"   # 124 = wedged and killed by timeout
```

Replacing `os._exit(1)` with `time.sleep(30)` (a real thread-method timeout
kill) wedges identically. Results of the mitigation matrix on this repro:

| Variant | Result |
|---|---|
| baseline `--dist loadfile`, `os._exit` or thread-timeout | wedge |
| `+ -x` | wedge |
| `-n 1` | wedge |
| crash mid-run with 30 files still pending | wedge (at tail, after the clone re-crashes) |
| `--dist load` | recovers, 1 failed / 33 passed, 3s |
| `--timeout-method=signal` | recovers, 1 failed / 33 passed, 6s |
| `--max-worker-restart=0` | fails fast in 3s: `worker 'gw2' crashed while running 'test_crash_exit.py::test_b'` |

## Proposed Solution

Add `--max-worker-restart=0` to the pytest addopts. With restarts disabled,
`worker_errordown` takes the `maximum_reached` branch (dsession.py:255-262):
it reports `worker gwN crashed and worker restarting disabled`, calls
`triggershutdown()`, and the session finishes with a non-zero exit and a
failure entry naming the exact test the worker died on. This never enters the
buggy clone/re-queue path.

Known side effect (inherent to fail-fast, not a defect): the session stops at
the crash. Tests after the crash point in the same file and any work units
still queued are never run or reported, so the summary count is below the
collected count. On the repro: `1 failed, 31 passed` of 34 collected
(`test_c`/`test_d` unreported). The exit code is still `1`, so every gate that
reads it fails correctly; document the count gap in TROUBLESHOOTING so it is
not misread as lost tests.

Why this over the alternatives:

- `--dist load` would lose per-file worker affinity, which the pyproject
  comment justifies for scheduling round-trips and per-file fixtures (git
  repos, subprocess envs) on a ~24.5k-test suite.
- `--timeout-method=signal` is explicitly avoided ("signal-based timeouts race
  with xdist worker process management", pyproject comment) and only covers
  the timeout trigger, not `os._exit`/segfault crashes.
- A `pytest_xdist_make_scheduler` hook in conftest returning a patched
  scheduler would fix the re-queue bug locally but is a monkeypatch of
  upstream internals; revisit only if a crashed-worker *retry* turns out to
  be needed.
- Crash retries are not wanted here anyway: a worker death is always a test
  bug, and BUG-2524's precedent routes crash-prone tests via
  `@pytest.mark.no_parallel` rather than relying on restart.

Keep a comment next to the flag citing xdist #784/#1327 and PRs #1328/#1371,
so it can be dropped once a fixed `pytest-xdist` release is pinned.

## Integration Map

### Files to Modify
- `scripts/pyproject.toml` (`[tool.pytest.ini_options]` addopts) — add
  `--max-worker-restart=0` with rationale comment
- `pytest.ini` (repo root) — mirror the addopts change; this stub duplicates
  the pyproject addopts and says to keep the two in sync
- `docs/development/TROUBLESHOOTING.md` — add a third "suite wedges at the
  tail" entry next to § "xdist flake: subprocess signal-handling test times
  out" (`:821-835`) and § "Full-suite run makes macOS sluggish (beachball)"
  (`:837-846`), with the idle-0% vs busy-spin-97-99% discriminator and the
  post-fix "passed+failed < collected after a worker crash" count gap
- `docs/development/TESTING.md` § "Live Host-CLI Spawn Guard" (~lines
  1105-1109) — currently conflates the un-killable BUG-3208 hang with the
  busy-spin signature only; mention this idle-wedge signature and the
  `--max-worker-restart=0` behavior

### Dependent Files (Callers/Importers)
- `.ll/ll-config.json` (`project.test_cmd`, bare `python -m pytest scripts/tests/`)
  — picks up the addopts change automatically; no edit
- `scripts/tests/conftest.py` (`pytest_xdist_auto_num_workers`,
  `pytest_configure` renice, `_collapse_rate_limit_ladder`) — unchanged;
  `pytest_xdist_auto_num_workers` still resolves `numprocesses`, which is only
  used by `get_default_max_worker_restart` when the flag is absent
- `scripts/little_loops/issue_manager.py:97-115` (`FINALIZE_RETRY_PROMPT`)
  and `:144-206` (`run_claude_command`, `timeout=7200`) — the `ll-auto`
  re-drive path that blocks on the suite; benefits automatically. Note the
  prompt does **not** inject `-x`; an earlier draft of this issue said it did
- `scripts/little_loops/worktree_utils.py:755` (`verify_epic_branch_before_merge`)
  — `subprocess.run(project.test_cmd)` with no `timeout=` kwarg; benefits
  automatically from the fail-fast, but is still unbounded against any
  *other* hang. Optional hardening, not required for this fix
- `.github/workflows/ci.yml:81-88` (pin-assertion step) — greps for the
  literal `pytest-xdist.*<3.8` string; the pin is not touched by this fix, so
  this stays green

### Similar Patterns
- BUG-3208 (closed) — same externally-visible "suite wedges near the end"
  symptom, different root cause (stale pytest 9 / xdist 3.8.0 busy-spin).
  Preserve its pin rationale in `scripts/pyproject.toml`.
- BUG-2524 (closed, `P3-BUG-2524-xdist-worker-crash-on-rate-limit-test.md`)
  — a prior "xdist worker crashed" bug fixed by `@pytest.mark.no_parallel`
  rerouting; its findings note no regression test asserted on the literal
  `worker 'gw<N>' crashed` string. This issue adds that test.

### Tests
- `scripts/tests/test_xdist_crash_fail_fast.py` (new) — subprocess-based
  regression test modeled on
  `scripts/tests/test_hook_session_start.py:712-765`
  (`TestAmbientAutomationEnvHermeticity.test_suite_passes_with_ambient_ll_automation`):
  write the synthetic tree from Steps to Reproduce into `tmp_path`, run
  `python -m pytest` on it as a real subprocess, `timeout=60`, and assert
  `returncode != 0` and that stdout contains the full xdist 3.7.0 line
  `worker 'gw<N>' crashed while running 'test_crash_exit.py::test_b'`
  (match on `"crashed while running 'test_crash_exit.py::test_b'"`).
  Two constraints that differ from a naive port of the template:
  - **Guard the project config, not xdist.** Do not pass
    `--max-worker-restart=0` explicitly; the test must fail if someone
    deletes the flag from the config. Load
    `[tool.pytest.ini_options].addopts` from `scripts/pyproject.toml` with
    `tomllib`, pass that list through, and append `-n 2` (a later `-n`
    overrides the addopts' `-n logical`) plus the tmp tree's own
    `-c pytest.ini --rootdir=<tmp_path>`. Also assert the root `pytest.ini`
    stub's `addopts` contains `--max-worker-restart=0`; no test currently
    checks the two config files stay in sync.
  - **Do NOT mark `no_parallel`.** Under the default `-n logical` addopts
    a `no_parallel` test is skipped outright (the controller never runs
    tests; see `conftest.py::pytest_collection_modifyitems` docstring), so
    the regression test would never execute in the normal suite. A nested
    `-n 2 --dist loadfile` pytest run works from inside an xdist worker
    (verified 2026-09-15: outer `-n 2` worker → inner `-n 2` repro, passes
    in ~4s). Keep only the recursion sentinel env var, exactly as the
    template does.
- `scripts/tests/test_conftest_cap.py` — no change expected; only touch if
  the flag is wired through `pytest_xdist_auto_num_workers` instead of addopts

### Documentation
- `docs/development/TROUBLESHOOTING.md` and `docs/development/TESTING.md` as
  listed under Files to Modify
- `docs/observability/streaming-parity-traces.md:73` — mentions the
  `--timeout=120` value only; unaffected

### Configuration
- `.ll/learning-tests/pytest-timeout.md` (2026-09-12) — asserts that
  `--timeout-method=thread` calls `os._exit(1)` and orphans in-flight
  subprocess children; still accurate, `--timeout-method` does not change.
  Worth appending the fact that the thread-method stack dump goes to
  `/dev/null` under xdist workers

## Implementation Steps

1. Add `--max-worker-restart=0` to `scripts/pyproject.toml` addopts with a
   comment citing this issue and xdist #784/#1327 (fix PRs #1328/#1371,
   unreleased as of 3.8.0). Mirror in root `pytest.ini`.
2. Add `scripts/tests/test_xdist_crash_fail_fast.py` (new) per the Tests section
   (addopts read from `scripts/pyproject.toml`, no `no_parallel` marker).
   Confirm it fails (wedge → `TimeoutExpired`) with the flag removed from
   pyproject and passes with it; confirm it actually runs (not skipped) under
   the default `-n logical` invocation.
3. Add the TROUBLESHOOTING.md entry and the TESTING.md clarification.
4. Run the full suite once to confirm the flag does not change a clean
   run's outcome.

Not in scope: identifying which test killed `gw4` in the ENH-3480 run. The
log cannot recover it (see Current Behavior). With the flag in place the next
occurrence reports the nodeid directly.

## Impact

- **Priority**: P2 - silent, total outage of the only merge gate when it
  triggers; observed live blocking an active `ll-auto` run.
- **Effort**: Small. Two addopts lines, one subprocess test, two doc entries.
- **Risk**: Low. Behavior change is limited to runs where a worker already
  died; such runs currently wedge, so any bounded failure is an improvement.
  The only case where restart previously *worked* under `--dist loadfile` is
  a worker crashing on its very first file (no completed unit to re-queue);
  every later crash already wedged, so the practical regression surface is
  near zero. A first-file crash now fails the run instead of being retried;
  BUG-2524's `no_parallel` routing is the intended handling for such tests.
  Remaining tests after the crash are not run (see Proposed Solution).
- **Breaking Change**: No.

## Related Key Documentation

- `docs/development/TROUBLESHOOTING.md` § "xdist flake" and § "beachball" entries
- `docs/development/TESTING.md` § "Live Host-CLI Spawn Guard"
- `.claude/CLAUDE.md` § Testing & CI Policy

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections applied in this pass).

- Root cause, repro, and mitigation matrix were established by running the
  synthetic tree above against the installed `pytest-xdist==3.7.0` /
  `pytest==8.4.2` / `pytest-timeout` in the miniforge interpreter, and by
  tracing the controller with `--debug`. Line numbers for `loadscope.py` and
  `dsession.py` refer to the installed 3.7.0 copy.
- Removed the claim that `FINALIZE_RETRY_PROMPT` injects `-x`; the prompt text
  at `issue_manager.py:97-115` contains no such flag. Removed the `-x`
  candidate direction; the repro shows `-x` neither causes nor prevents the
  wedge.
- Removed the "find the >120s test with `--durations=0`" step: `--durations`
  reports only tests that completed, so it cannot locate a test that killed
  its worker; and the 120s trigger itself is unverified for the ENH-3480 run.
- Corrected "ll-auto stalls indefinitely": `run_claude_command` defaults
  `timeout=7200`, so the stall is bounded at two hours.
- Trimmed the Integration Map: the twelve loop YAMLs and
  `streaming-parity-traces.md` previously listed are consumers of
  `project.test_cmd` and need no edit.
- Earlier citation correction retained: `TestAmbientAutomationEnvHermeticity`
  spans `test_hook_session_start.py:712-765`.
- 2026-09-15 pre-implementation review: re-ran the repro (baseline wedge;
  `--max-worker-restart=0` → exit 1, `1 failed, 31 passed`, ~2.7s) and a
  nested run of the repro from inside an xdist worker (passes). Dropped the
  `no_parallel` marker from the test plan (it would skip the test under the
  default addopts), made the test load addopts from pyproject so it guards
  the config rather than xdist, added the pytest.ini sync assertion, and
  documented the post-crash unreported-test count gap. Confirmed neither
  config file contains `max-worker-restart` today and all cited line ranges
  (pyproject, pytest.ini, TESTING.md, TROUBLESHOOTING.md, ci.yml) resolve.

## Status

**Open** | Created: 2026-09-15 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-15T23:25:38 - `327c38c3-cd69-4287-90f2-4d0c76733f97.jsonl`
- `/ll:verify-issues` - 2026-09-15T23:20:02 - `4aed0df2-a263-4d28-ae34-d555931852b6.jsonl`
- `/ll:verify-issues` - 2026-09-15T22:29:03 - `74d0e714-5fa8-4d36-8d26-f70b1e11f439.jsonl`
- `/ll:wire-issue` - 2026-09-15T22:22:26 - `d2ee88e4-436e-400b-a42b-568c16a51760.jsonl`
- `/ll:refine-issue` - 2026-09-15T22:12:30 - `1daaf7af-e74b-4b5d-b1aa-a57797ab5fda.jsonl`
- `/ll:format-issue` - 2026-09-15T22:08:41 - `4ed27b03-8e1c-4cb5-ad0c-8aea21116e0d.jsonl`
