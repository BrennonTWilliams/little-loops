---
id: EPIC-2455
title: fsm.host_guard — protect FSM loops from host pressure
type: EPIC
priority: P2
status: open
relates_to: [ENH-2452, ENH-2453, ENH-2454]
labels: [epic, fsm, host-guard, captured]
captured_at: "2026-07-03T02:05:57Z"
discovered_date: "2026-07-02"
discovered_by: capture-issue
---

# EPIC-2455: fsm.host_guard — protect FSM loops from host pressure

## Summary

Add an `fsm.host_guard` block to the FSM schema that gives every loop author a configurable answer to "what should this loop do when the host's memory is under pressure?" The guard has three layers, delivered as child issues: an adaptive system-memory pressure check before each prompt state (ENH-2452), a cumulative subprocess RSS budget with a route/abort ladder (ENH-2453), and re-documentation of the existing `--delay` flag as the manual override (ENH-2454). When this EPIC is done, no FSM loop will silently starve a sibling interactive session via macOS jetsam or OOM-kill on Linux.

## Goal

When this EPIC is done, the executor ships with a `fsm.host_guard` block that is default-enabled with conservative thresholds, exposes a `cool_down | route | abort` ladder consistent with the existing `circuit.repeated_failure` vocabulary, and composes cleanly with the existing `--delay` flag (which becomes the base floor). Every heavy loop (≥ 10 prompt states, or any loop running alongside an interactive Claude session) ships with a guard that reacts to measured host pressure rather than relying on the author to remember to set `--delay`.

## Motivation

On 2026-07-02 at ~20:43 local time, a 12-minute `ll-loop run brainstorm` (13 sequential prompt states, each spawning a ~500 MB `claude` subprocess) caused macOS jetsam to kill a sibling interactive Claude session. The failure was silent: the loop completed normally, but the user's interactive work died mid-recording. The user had no way to know in advance that 13 × 500 MB would exceed the jetsam threshold for their session, and the runner had no signal to react to rising pressure. This EPIC closes that gap by turning host pressure from a blind spot into a measured signal the loop can react to.

## Scope

### In scope

- The `fsm.host_guard` YAML block, with `enabled`, `cooldown_ms`, `warn_pct`, `critical_pct`, `on_pressure`, `pressure_state`, `on_abort_route`, `max_cumulative_subproc_mb`, `on_budget_exceeded`, `budget_state`.
- The `HostGuardConfig` dataclass and the `vm_stat` (macOS) / `/proc/meminfo` (Linux) probe.
- The host-pressure pre-state check in `FSMExecutor.run()`.
- The cumulative subprocess RSS accumulator and budget check.
- New events: `host_pressure`, `host_pressure_relieved`, `host_pressure_abort`, `host_cooldown`, `host_subproc_rss`, `host_budget_exceeded`.
- New CLI flags: `--no-host-guard`, `--host-guard-budget-mb`.
- The `--delay` help text update and the `backoff:` field doc update.
- New and extended tests across `test_host_guard.py`, `test_executor.py`, `test_runners.py`, `test_cli_loop.py`.
- `ll-loop doctor` integration: flag heavy loops with `host_guard: enabled: false`.
- Documentation: `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/development/TROUBLESHOOTING.md`.

### Out of scope

- `parallel:` state resource limits (ENH-1176 owns that scope).
- cgroup or `RLIMIT_RSS` enforcement (platform support gap — macOS has neither; Linux's cgroup v2 memory controller is out of scope for v1).
- Per-host auto-tuning of `warn_pct` / `critical_pct` / `max_cumulative_subproc_mb`.
- Measurement of the parent Python process's own RSS (only subprocesses spawned by the loop count).
- The `--delay` flag's existing fixed-sleep behavior (it stays as-is; the guard is the adaptive complement).
- A future `fsm.disk_guard`, `fsm.fd_guard`, etc. — those would be separate epics.

## Children

- **ENH-2452** — fsm.host_guard: adaptive memory pressure check (P2). The first layer: sample system memory before each `action_type: prompt` state; sleep extra / route / abort based on `warn_pct` / `critical_pct`. Composes with `--delay` as the base floor.
- **ENH-2453** — fsm.host_guard: cumulative subprocess RSS budget (P3). The second layer: track peak RSS per spawned subprocess (via `ps -o rss=` / `top -l 1 -pid PID` sampling), accumulate across the run, route or abort on overflow.
- **ENH-2454** — Extend `--delay` help text to mention host-pressure use case (P5). The interim mitigation: one-line help text fix and matching `backoff:` field doc update so users running heavy loops can find the manual override before the structural fix lands.

## Success Metrics

- All three children reach `status: done`.
- `ll-loop run` with the default `host_guard` enabled produces no `host_pressure_abort` events on the 2026-07-02 brainstorm replay (verified by re-running the same brief and checking the events stream).
- `ll-loop doctor` flags existing heavy loops (estimated by prompt-state count > N, default N=10) that have `host_guard: enabled: false` and recommends enabling it.
- The guard adds < 50 ms per-state overhead in the common case (no `vm_stat` invocation if disabled, or single `vm_stat` round-trip otherwise). The cumulative RSS sample adds < 100 ms per-subprocess overhead.
- `ll-verify-skill-budget` and `ll-verify-package-data` continue to pass; no new top-level deps (no `psutil`).

## Integration Map

### Files to Modify (shared across children)

- `scripts/little_loops/fsm/host_guard.py` — new module (ENH-2452 + ENH-2453 share this).
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.__init__` and `run()` gain `_host_guard` wiring (ENH-2452) and `_cumulative_subproc_mb` tracking (ENH-2453).
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` gains the post-process RSS sample hook (ENH-2453).
- `scripts/little_loops/fsm/fsm-loop-schema.json` — new `host_guard` block (ENH-2452) and cumulative-budget extensions (ENH-2453).
- `scripts/little_loops/cli/loop/__init__.py` — `--no-host-guard` (ENH-2452) and `--host-guard-budget-mb` (ENH-2453) arguments; `--delay` help text update (ENH-2454).
- `scripts/little_loops/cli/loop/run.py`, `cli/loop/lifecycle.py` — wire the new CLI flags.
- `scripts/little_loops/cli/loop/_helpers.py` — propagate `--no-host-guard` to sub-`ll-loop` invocations (mirror the existing `--delay` propagation at line 1356).

### Dependent Files (Callers/Importers)

- All loop YAMLs that declare `fsm.host_guard` are dependents; existing loops without it are unaffected.
- The `ll-loop doctor` integration (TBD) needs a new module under `cli/doctor.py` that walks the loop catalog and flags heavy loops without the guard.

### Tests (shared test infrastructure)

- `scripts/tests/test_host_guard.py` — new file. Unit tests for the probe (mocked `vm_stat` / `meminfo` output) and the `HostGuardConfig` dataclass. Extended by ENH-2453 with budget-accumulator tests.
- `scripts/tests/test_executor.py` — extend with guard integration tests.
- `scripts/tests/test_runners.py` — extend with RSS sample hook tests (ENH-2453).
- `scripts/tests/test_cli_loop.py` — extend with `--no-host-guard` and `--delay` help text tests.

### Documentation

- `docs/reference/CLI.md` — `--delay`, `--no-host-guard`, `--host-guard-budget-mb` (auto-regenerated from argparse if `ll-verify-docs` runs the regen; otherwise manual).
- `docs/reference/API.md` — `HostGuardConfig` and the new events.
- `docs/guides/LOOPS_GUIDE.md` — `fsm.host_guard` block; `backoff:` field doc update (ENH-2454).
- `docs/development/TROUBLESHOOTING.md` — new "jetsam-killed session during ll-loop" entry pointing to this EPIC.

### Configuration

- Per-loop `fsm.host_guard` block.
- Per-run CLI overrides: `--no-host-guard`, `--host-guard-budget-mb`.
- No new global config keys (`ll-config.json`) for v1.

## Impact

- **Priority**: P2 — significant user-impacting failure mode (silent jetsam kill of interactive session); no current mitigation beyond manually setting `--delay`.
- **Effort**: Medium — ~250 LOC across both ENH children + schema block + tests + docs. The design reuses existing patterns (`circuit`, `RateLimitCircuit`, `StallDetector`) so design risk is low.
- **Risk**: Low — both ENH children are default-enabled with conservative thresholds; existing loops only get slower, never broken. The macOS-soft signal (no cgroups to enforce hard cap) is documented as a known limitation in both children.
- **Breaking Change**: No — all new fields are optional, defaulting to safe values. Existing loops without `fsm.host_guard` declared inherit the defaults.

## Related Key Documentation

- `docs/reference/CLI.md` (`--delay` flag documentation at lines 521, 707)
- `docs/guides/LOOPS_GUIDE.md` (`backoff:` per-state field at line 439)
- `docs/reference/API.md` (FSMExecutor / circuit config)

## Related Issues

- **ENH-1176** (parallel-state resource limits) — sibling, owns `parallel:` state fan-out. ENH-1176's "memory/file-handle cap" claim remains parallel-only; this EPIC's ENH-2453 is the general-FSM counterpart.
- **ENH-2452**, **ENH-2453**, **ENH-2454** — children of this EPIC.

## Status

**Open** | Created: 2026-07-02 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-03T02:05:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ff12421-1849-4d8d-abe4-d955b4becd84.jsonl`
