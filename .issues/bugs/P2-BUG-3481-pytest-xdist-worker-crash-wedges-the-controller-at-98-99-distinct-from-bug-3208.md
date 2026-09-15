---
id: BUG-3481
type: BUG
title: pytest-xdist worker crash wedges the controller at 98-99%, distinct from BUG-3208
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T21:54:42Z'
program_design_not_applicable: true
---

# BUG-3481: pytest-xdist worker crash wedges the controller at 98-99%, distinct from BUG-3208

## Summary

`python -m pytest scripts/tests/` can wedge permanently, not just hang under
load: when a per-test `--timeout=120 --timeout-method=thread` watchdog fires
and kills an entire xdist worker process (`[gwN] node down: Not properly
terminated`), the surviving workers and controller go fully idle (0% CPU) and
never return an exit code. Observed live during `ll-auto --only ENH-3480`
(2026-09-15): PID 54510 + 6 xdist children sat idle for 20+ minutes with zero
progress before being killed manually. This blocks the `ready-issue` /
`manage-issue` / epic-verify gate, which all read the suite's exit code, the
same way BUG-3208 did — but BUG-3208 is closed and describes a different
signature (idle workers busy-spinning at 97-99% CPU from a stale pytest 9
resolving into the miniforge interpreter). This machine already has the
BUG-3208-safe pins installed (`pytest==8.4.2`, `pytest-xdist==3.7.0`) and the
wedge still occurred, with workers truly idle at 0% CPU rather than
busy-spinning — a distinct, still-open failure mode in the same
"suite wedges at the tail" family.

## Current Behavior

Tail of `.loops/tmp/scratch/enh3480-test-results.txt` from the run:

```
ssssssssss.............................................................. [ 96%]
...
....[gw4] node down: Not properly terminated
F<site-packages>/pytest_benchmark/logger.py:44: PytestBenchmarkWarning...
```

After that line, `ps aux` showed the controller (PID 54510) and all 6
`[pytest-xdist idle]` workers alive but at 0% CPU (`SN` state), unchanged for
20+ minutes. No further test output was ever written. `vm_stat`/`top` showed
no memory pressure (38G unused) and no OOM/jetsam kill in `log show` for the
window, ruling out the machine running out of resources — the crash was
test-timeout-driven, not environmental.

## Expected Behavior

A worker crash mid-run should not silently wedge the whole session. Either:
- pytest-xdist reschedules the crashed worker's remaining queued file(s) to a
  surviving worker and the run completes (reporting the timed-out test as a
  failure), or
- the controller detects the dead worker and fails fast with a non-zero exit
  and a clear error, within a bounded time.

Either outcome returns an exit code so `ll-auto`'s Phase 3 finalization does
not stall indefinitely waiting on a background task that will never notify.

## Motivation

Same motivation as BUG-3208: the full suite *is* this project's CI (no hosted
runner per `.claude/CLAUDE.md` § Testing & CI Policy), so a wedge here is a
silent total outage of the merge gate, not an inconvenience. This is the
second distinct root cause (after BUG-3208's stale-pytest-9 busy-spin) to
produce the identical externally-visible symptom — a session that "waits for
the background test run" forever with no completion notification — so
without a fix, the same class of failure will keep recurring and keep getting
misdiagnosed as BUG-3208 (they must be told apart by CPU state: idle-0% here,
busy-spin-97-99% there).

## Proposed Solution

Not yet root-caused to a specific mitigation — this issue captures the
observation and reproduction signature; a fix requires further investigation
into why `pytest-xdist` 3.7.0's crash-recovery path doesn't reschedule or
finalize here. Candidate directions to evaluate, not yet chosen:

1. Identify and fix/mark-slow the specific test that exceeded 120s (requires
   a serial `-n0` rerun, or per-file `--durations`/verbose xdist output, to
   attribute the hang to a file — not done in this pass because a full serial
   rerun of a ~24.5k-test suite is expensive and shouldn't run unattended
   inside another automated retry).
2. Confirm/rule out whether `-x`/`--exitfirst` (injected by the `ll-auto`
   finalize/re-drive prompt, not part of `project.test_cmd` in
   `.ll/ll-config.json`, which is bare `python -m pytest scripts/tests/`) is
   required to trigger the no-recovery path, since xdist's exitfirst handling
   and its crash-requeue logic may be interacting.
3. Consider a wrapper-level watchdog (outside pytest itself) that detects a
   fully-idle xdist run past some grace period and kills+reports it, so the
   failure surfaces as "suite timed out" rather than an indefinite hang —
   mirrors the CI-side "master-side hang watchdog for BUG-3208" already built
   for the hosted-runner diagnosis effort (see `ci(diagnose): add
   master-side hang watchdog for BUG-3208` in git log), but for local/`ll-auto`
   runs which have no such watchdog today.

## Integration Map

### Files to Modify
- TBD - requires investigation per Proposed Solution above

### Dependent Files (Callers/Importers)
- `.ll/ll-config.json` (`project.test_cmd`)
- `scripts/pyproject.toml` (`[tool.pytest.ini_options]` addopts: `--timeout=120 --timeout-method=thread`, `-n logical --dist loadfile`)
- `scripts/tests/conftest.py` (`pytest_xdist_auto_num_workers`, `pytest_configure` renice, `_collapse_rate_limit_ladder`)
- Any `ll-auto`/`manage-issue` finalize/re-drive prompt path that shells out to run the test suite in the foreground

### Similar Patterns
- BUG-3208 (closed) — same externally-visible "suite wedges near 98-99%"
  symptom, different root cause (stale pytest 9 vs. worker crash). Any fix
  here should preserve BUG-3208's pin rationale in `scripts/pyproject.toml`.

### Tests
- N/A until a specific slow/hung test is identified per Proposed Solution #1

### Documentation
- N/A pending root cause

### Configuration
- N/A

## Implementation Steps

1. Reproduce deliberately: run the full suite with `-p no:cacheprovider
   --durations=0` (or a targeted subset) to find any test that legitimately
   takes close to or over 120s.
2. Once found, either speed it up, mark it `@pytest.mark.timeout(N)` with a
   larger bound, or fix whatever it's blocked on (lock, subprocess, network).
3. Separately/optionally, evaluate a local hang-watchdog for `ll-auto`'s
   foreground test-suite step so a future occurrence of this class of wedge
   fails loudly with a bounded timeout instead of hanging indefinitely.
4. Re-run the full suite to confirm a clean finish with no idle-wedge.

## Impact

- **Priority**: P2 - silent, total outage of the only merge gate when it
  triggers, identical in severity to BUG-3208; observed live blocking an
  active `ll-auto` run.
- **Effort**: Unknown until the specific slow/hung test is identified;
  likely Small once found (BUG-3208 precedent: diagnosis was the cost, not
  the fix).
- **Risk**: Low to investigate (read-only reproduction); risk of the eventual
  fix depends on what's found.
- **Breaking Change**: No.

## Steps to Reproduce

1. Run `python -m pytest scripts/tests/` (or with `-x`) to completion many
   times; this is intermittent/tail-of-suite, not deterministically
   reproducible on demand.
2. Watch `ps aux | grep pytest` during a run that reaches ~98-99%.
3. If a worker exits (visible as `[gwN] node down: Not properly terminated`
   in the pytest output), watch whether the controller and remaining workers
   drop to and stay at 0% CPU (`SN` state) rather than completing or
   busy-spinning.
4. Confirm via `ps -o pid,etime,stat -p <pids>` that elapsed time keeps
   climbing with `STAT` staying `SN`/idle and no further output is written.

## Root Cause

- **File**: `scripts/pyproject.toml` (`[tool.pytest.ini_options]` addopts:
  `--timeout=120`, `--timeout-method=thread`) interacting with pytest-xdist's
  worker-crash handling.
- **Anchor**: pytest-timeout's thread-method watchdog (kills the whole worker
  process via `os._exit()` when a test exceeds the timeout, since a
  thread-based watchdog cannot cleanly abort a hung call in the test thread —
  see `scripts/tests/conftest.py:517`'s `_collapse_rate_limit_ladder`
  docstring, which already documents this tradeoff for a different reason);
  pytest-xdist's session-finish path in the 3.7.0 controller.
- **Cause**: Not fully isolated. The immediate trigger is some test exceeding
  120s wall-clock (not yet identified — the ENH-3480 diff itself, docstring
  presence assertions in `test_wiring_skills_and_commands.py`, is trivial and
  an unlikely culprit). The trigger kills the worker outright rather than
  just failing the test. Downstream of that crash, pytest-xdist 3.7.0's
  controller does not reschedule the dead worker's remaining queued items nor
  finalize the session — it simply stops making progress. Whether `-x`
  (injected by the `ll-auto` re-drive prompt, not the project's `test_cmd`)
  is required for the no-recovery path is unconfirmed.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-15 | Priority: P2
