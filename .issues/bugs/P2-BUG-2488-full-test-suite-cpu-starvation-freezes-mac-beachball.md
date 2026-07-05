---
id: BUG-2488
title: Full test suite CPU-starves the OS and freezes the Mac (beachball) despite BUG-2484
type: BUG
priority: P2
status: done
discovered_date: '2026-07-05'
discovered_by: user-report
captured_at: '2026-07-05T23:11:06Z'
completed_at: '2026-07-05T23:11:06Z'
relates_to:
- BUG-2484
labels:
- testing
- pytest
- performance
- macos
---

# BUG-2488: Full test suite CPU-starves the OS and freezes the Mac (beachball) despite BUG-2484

## Summary

Running the full suite (`python -m pytest scripts/tests/`, the project's literal
CI gate — e.g. during `/ll:manage-issue`) spikes CPU to 100% and freezes the M4
Mac ("beachball of death"). BUG-2484 (done 2026-07-05) trimmed nested
`ThreadPoolExecutor` pools in `test_hooks_integration.py` but explicitly declared
the `-n logical` 14-worker baseline "expected and by design" — that baseline was
the actual root cause, so the freeze persisted after BUG-2484.

## Root Cause

The suite is ~13.7k CPU-bound tests. Two compounding factors:

1. **One worker per core.** `addopts` uses `pytest-xdist` `-n logical`, which
   resolves to `psutil.cpu_count(logical=True)` = **14** on this M4 (Apple
   Silicon has no SMT, so `logical == physical`). xdist spawns a worker per
   core, pinning all 14.
2. **Normal scheduling priority.** Even below full core count, a CPU-bound run at
   normal priority never lets the macOS compositor (WindowServer) get scheduled
   → UI freeze. Individual tests also spawn their own threads/subprocesses
   (ThreadPoolExecutors, unix sockets, real `git`/`bash`), so effective load
   per worker exceeds one core (load average hit 23 at just 4 workers).

### Ruled out during investigation
- **Not a hook.** `scratch-pad-redirect.sh` fires once per Bash call (ms-scale)
  and only redirects in `bypassPermissions` mode; it runs before pytest starts.
  Beachball duration scaled with `-n` worker count, which a fixed hook would
  not.
- **Not a fork bomb.** FSM executor tests use `MockActionRunner`; background
  spawning is mocked (`test_cli_loop_background.py` patches `subprocess.Popen`);
  real subprocesses are short-lived `git`/`bash`/`python3`. All
  `ThreadPoolExecutor` pools are bounded.
- **Not memory/OOM.** Fuzz files peak ~150 MB RSS each; 64 GB RAM. It is CPU
  starvation of the OS, not swap.

## Steps to Reproduce

1. Run `python -m pytest scripts/tests/` on a many-core Mac (or during
   `/ll:manage-issue`).
2. Observe all logical cores pin at 100% and the UI beachball.

## Resolution

Defend on two axes in `scripts/tests/conftest.py`:

- **`pytest_xdist_auto_num_workers`** — caps xdist workers to `cpus // 2`
  (14 → 7), reserving half the cores. Wins over xdist's default; honors
  `PYTEST_XDIST_AUTO_NUM_WORKERS`; bypassed by explicit `-n <N>` / `-n 0`.
- **`pytest_configure`** — calls `os.nice(10)` on the controller and every xdist
  worker (each worker re-runs `pytest_configure`), lowering scheduling priority
  so the OS always preempts the tests for the UI. The decisive lever: costs ~0
  wall-clock when cores are free, yields only under contention. Opt out with
  `LL_TEST_NO_NICE=1`.

Supporting changes in `scripts/pyproject.toml`:
- Declared `psutil>=5.9` in the `dev` extra (it backs `-n logical` but was
  undeclared).
- Corrected the `addopts` comment (the old "logical excludes hyperthreads"
  rationale is false on Apple Silicon) to document the cap + renice defense.

### Files Changed
- `scripts/tests/conftest.py`
- `scripts/pyproject.toml`

## Verification Results
- Worker count: `created: 7/7 workers` (was 14/14).
- Renice active: a probe test asserting `os.nice(0) >= 10` passes inside xdist
  workers and fails under `LL_TEST_NO_NICE=1` (confirms the renice and the
  opt-out).
- Escape hatches: `PYTEST_XDIST_AUTO_NUM_WORKERS=3` → 3 workers; `-n 0` → serial.
- Full run: dropped from all 14 cores pinned to **354% CPU (~3.5 cores)** at
  **72s** wall-clock (no speed regression); ~10 cores free for the OS.
- `ruff check scripts/tests/conftest.py` — passed; `pyproject.toml` parses.

## Impact
- **Priority**: P2 — severely degrades local dev experience (machine
  unresponsiveness / freeze during the standard CI gate); no production impact.
- **Effort**: Small — two conftest hooks + two pyproject lines; no production
  code touched.
- **Risk**: Low — scheduling-only changes; test outcomes unaffected.
- **Breaking Change**: No.

## Follow-ups
- Latent, separate bug surfaced during verification:
  `test_issue_lifecycle.py::TestEventBusEmission::test_complete_issue_lifecycle_emits_event`
  passes in isolation but fails under some xdist shardings — a global event-bus
  state leak between test files exposed when a different worker count co-locates
  it with the leaking test. Not caused by this fix; warrants its own issue.
- Consider annotating/reopening BUG-2484, whose "14-core baseline is by design"
  conclusion was the unaddressed cause fixed here.

## Status

**Completed** | Created: 2026-07-05 | Completed: 2026-07-05 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-07-05T23:11:41 - `ef94654f-41ac-445a-9642-c7b758409258.jsonl`
