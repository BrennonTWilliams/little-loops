---
id: BUG-3208
type: BUG
title: Uncapped pytest pin let pytest 9 into a second interpreter, hanging the full
  suite at 98-99%
priority: P2
status: done
testable: true
discovered_by: manual
relates_to:
- BUG-3192
discovered_date: '2026-08-15'
captured_at: '2026-08-16T02:08:30Z'
completed_at: '2026-08-16T02:08:30Z'
---

# BUG-3208: Uncapped pytest pin let pytest 9 into a second interpreter, hanging the full suite at 98-99%

## Summary

`python -m pytest scripts/tests/` reproducibly hung near 98-99% completion,
blocking the full-suite verification gate that `ready-issue` / `manage-issue` /
`ll-auto` depend on. Root cause was environmental, not a test defect: the dev
extra pinned `pytest>=7.0` with no upper bound, which resolved to **pytest
9.0.1** — but only in the miniforge interpreter, which is the one `python -m
pytest` actually runs. pytest 9 + pytest-xdist 3.8.0 + `--timeout-method=thread`
leaves watchdog threads busy-spinning on idle workers at the tail of a run.

The diagnosis was slow because two interpreters both carried the editable
install, so `pip show pytest` described a *different* Python than the one under
test.

## Current Behavior

### The hang

Four separate attempts (default workers, `-n4`, `--timeout=60`, fresh process
each, orphans reaped between) stalled at ~98-99%. `ps aux` during the hang
showed 6 workers labeled `[pytest-xdist idle]` each pinned at ~97-99% CPU — a
busy-spin, not a blocked wait. A prior bisect had localized it to a 50-file
`test_session_log*`/`test_session_store_*` slice and filed it as a latent
sqlite/fs-churn issue; that attribution was wrong — the slice was just where the
tail happened to land.

### The interpreter split

Two interpreters on this machine both import `little_loops` from this checkout
(an editable install pins an absolute source path), while holding different
dependency versions:

| PATH name | Resolves to | pytest | little-loops |
|---|---|---|---|
| `pip` | pyenv 3.11.11 | 8.4.2 | 1.155.0 |
| `python` | **miniforge3 3.12** | **9.0.1** | **1.154.0** (stale) |

`project.test_cmd` is `python -m pytest scripts/tests/` — the miniforge one. So:

- `pip install -e "./scripts[dev]"` installed into **pyenv**, leaving the
  environment actually under test untouched. The reinstall appeared to succeed
  and changed nothing.
- `pip show pytest` reported **8.4.2**, describing an interpreter that was not
  running the tests. The earlier investigation recorded this reading and
  concluded the pytest version was not implicated.

### Why pytest 9 got in

`scripts/pyproject.toml`'s dev extra pinned `pytest>=7.0` with no upper bound.
pytest 9.0.1 (Nov 2025) satisfied it silently. The relevant upstream
interaction, against the `addopts` this repo already sets
(`-n logical --dist loadfile --timeout=120 --timeout-method=thread`):

- pytest-xdist #1094, #117 — idle workers spin rather than terminating cleanly
- pytest-timeout #72, #137 — leftover thread watchdogs on idle workers

The `--timeout-method=thread` choice is itself deliberate (signal-based timeouts
race with xdist worker process management), so the fix belongs on the version
axis, not the timeout-method axis.

## Expected Behavior

1. The dev extra carries an upper bound so a new pytest major cannot enter the
   environment without a deliberate bump.
2. The full suite completes end-to-end under the pinned version.
3. The interpreter-drift trap is written down, since it is the thing that made
   this cost multiple sessions.

## Acceptance Criteria

- [x] `scripts/pyproject.toml`'s dev extra pins `pytest>=7.0,<9`.
- [x] The pin carries a comment naming the symptom (tail hang under xdist), the
      upstream issues, and the condition for lifting it (a verified clean
      full-suite run on the newer major) — matching the established
      justify-the-pin convention (cf. the `ruff==0.14.10` and `mcp==2.0.0` pins).
- [x] The capped extra is installed into the interpreter that `python -m pytest`
      resolves to, not merely into whichever Python owns `pip`.
- [x] A full `python -m pytest scripts/tests/` run completes with exit 0:
      **19409 passed, 46 skipped, 804.17s**, walking through 98% → 99% → 100%
      with no stall.
- [x] The prior "root cause not yet identified" record is corrected
      (`project_test_suite_beachball_fix` memory), including the retraction of
      the `test_session_store_*` attribution.
- [x] The `pip`-vs-`python` divergence is recorded as its own durable note
      (`reference_python_interpreter_drift_pip_vs_python`).

## Motivation

The full suite *is* this project's CI (`.claude/CLAUDE.md` § Testing & CI
Policy) — there is no hosted runner. A suite that cannot finish is therefore a
total loss of the merge gate, not an inconvenience: `ready-issue`,
`manage-issue`, and the epic-branch verify gate all read its exit code. The
in-flight `ll-auto --only "BUG-3192,BUG-3194,BUG-3193,ENH-3206,ENH-3185,
ENH-3200"` run was blocked on exactly this.

Raised to P2 over the P3 the symptom alone would suggest, because the failure
mode is a *silent* gate outage — the run never returns a verdict at all.

## Program Design

One pin change plus an environment correction; no product code.

**1. Cap the pin** (`scripts/pyproject.toml`, dev extra) — `pytest>=7.0` becomes
`pytest>=7.0,<9`, with the rationale comment above it.

**2. Install into the correct interpreter** — invoke the target interpreter
directly rather than relying on the `pip` on `PATH`:
`~/miniforge3/bin/python -m pip install -e "./scripts[dev]"`.
This downgraded pytest 9.0.1 → 8.4.2 and simultaneously refreshed the stale
little-loops 1.154.0 → 1.155.0 in that environment.

**3. Record the trap** — the two memories named in the acceptance criteria.

No function signatures change. The only repo-side edit is the dependency
specifier; the hooks below are the existing, unmodified code the resolved pytest
version flows through, and are listed to locate the failure rather than to
propose edits to them.

### Call Path

`project.test_cmd` (`.ll/ll-config.json`) -> `python -m pytest scripts/tests/`
-> the **miniforge** interpreter's `pytest` distribution (the resolution step
that silently selected 9.0.1 — the defect) -> `addopts` from
`[tool.pytest.ini_options]` (`scripts/pyproject.toml`) applies
`-n logical --dist loadfile --timeout=120 --timeout-method=thread` ->

- `pytest_xdist_auto_num_workers(config) -> int` — caps workers to ~cpus//2 (`scripts/tests/conftest.py`)
- `pytest_configure(config) -> None` — renices the pytest processes so the OS preempts them for the UI (`scripts/tests/conftest.py`)

-> pytest-xdist controller distributes files to workers -> at the tail, drained
workers enter `[pytest-xdist idle]` and **spin at ~97-99% CPU instead of
terminating** (the failing step) -> the run never returns an exit code -> the
`ready-issue` / `manage-issue` / epic-verify gate that reads that exit code
blocks indefinitely.

Both conftest hooks behave correctly here and are not implicated — they bound
CPU saturation, which is why the hang degraded into an unfinished run rather
than a repeat of the earlier machine-freeze beachball.

### Attribution caveat

The verifying run is a strong signal but **not a fully isolated one**, and this
is deliberately recorded rather than smoothed over:

- It changed two things at once — pytest 9→8 *and* the stale package refresh.
- It ran in a plain shell, not under `ll-auto`, where the hang was first seen.

The pytest-major hypothesis is the one supported by the upstream issues and by
the busy-spin signature, but a residual recurrence should re-examine the stale
install rather than assume the pin settled it.

### Out of scope

- `--dist worksteal` and `pytest-forked` process isolation were the queued
  fallbacks if the pin failed. It did not, so they stay unapplied.
- Consolidating the two interpreters. Real, larger than this fix, and not
  required — targeting the interpreter explicitly is sufficient.
- The `orchestration.disable_background_tasks` behavior this was originally
  conflated with. Confirmed unrelated: it gates tool-level backgrounding for
  spawned automation children and never touches `project.test_cmd`, which runs
  synchronously and is gated on its exit code. (Tracked separately as ENH-3207.)

## Steps to Reproduce

1. `which pip` → a pyenv shim; `which python` → a miniforge3 path. Different interpreters.
2. `pip show pytest` → 8.4.2 — the misleading reading.
3. `python -c "import pytest; print(pytest.__version__)"` → 9.0.1 — the version actually under test.
4. `python -m pytest scripts/tests/` → stalls at ~98-99%.
5. `ps aux | grep pytest` during the stall → workers marked `[pytest-xdist idle]` at ~97-99% CPU.

## Impact

- **Priority**: P2 — silent, total outage of the only merge gate; blocked an active multi-issue automation run.
- **Effort**: Small — a one-line pin plus a reinstall; the cost was diagnosis, not repair.
- **Risk**: Low. Pinning below a major already-not-in-use in the pyenv environment; the suite passes clean on 8.4.2.
- **Breaking Change**: No. Anyone resolving to pytest 9 gets 8.x on next install, which is the version the suite is verified against.

## Status

**Done** | Created: 2026-08-15 | Completed: 2026-08-16 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-08-16T02:09:56 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
