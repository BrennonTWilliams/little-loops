---
id: ENH-2452
title: fsm.host_guard — adaptive memory pressure check
type: ENH
parent: EPIC-2455
priority: P2
status: done
labels: [fsm, host-guard, captured]
captured_at: "2026-07-03T02:05:57Z"
discovered_date: "2026-07-02"
discovered_by: capture-issue
---

# ENH-2452: fsm.host_guard — adaptive memory pressure check

## Summary

Add an adaptive memory-pressure gate to the FSM executor. Before each `action_type: prompt` state, the runner samples system memory and either sleeps extra, routes to a configured recovery state, or aborts — based on configurable thresholds. Composes with the existing `--delay` flag (`fsm.backoff`), which becomes the base floor.

## Current Behavior

The `--delay SECONDS` flag sets `fsm.backoff` and the executor honors it as a fixed inter-state sleep (`scripts/little_loops/fsm/executor.py:583-589`). The flag is documented as "useful for recording" but also serves as a manual host-pressure relief valve. There is no *adaptive* gate — the runner cannot sample actual host pressure and only sleeps when pressure is high. A long-running loop (e.g., `brainstorm` with 13 sequential prompt states) can starve a sibling interactive Claude session via macOS jetsam even when `--delay` is set conservatively, because the cumulative subprocess RSS across the run still exceeds the jetsam threshold.

## Expected Behavior

New `fsm.host_guard` block in the FSM schema. Default-enabled with conservative thresholds. When the guard is active and the host's used-memory percentage exceeds `warn_pct` (default 75), the runner sleeps an additional `cooldown_ms` (default 500) before the action runs; if it exceeds `critical_pct` (default 85), the runner emits a `host_pressure` event and either routes to `pressure_state` (when `on_pressure: route`) or sets `_shutdown_requested` and finishes as `host_pressure_abort` (when `on_pressure: abort`). The existing `--delay` becomes a complementary floor — the guard never sleeps *less* than `--delay` seconds.

## Motivation

macOS jetsam killed an interactive Claude session during a 12-minute `ll-loop run brainstorm` on 2026-07-02 at ~20:43 local time. The loop spawned 13 sequential `claude` subprocesses, each holding ~500 MB peak. The user had no way to know in advance that 13 × 500 MB would exceed the jetsam threshold for their session. A runner that detected rising pressure between states and slept through it would have prevented the kill. This guard turns host pressure from a blind spot into a measured signal the loop can react to.

## Proposed Solution

```yaml
# In a loop YAML's fsm: block (mirrors the shape of the existing circuit: block)
fsm:
  host_guard:
    enabled: true                  # default true; disable with --no-host-guard
    cooldown_ms: 500               # added to base --delay when pressure >= warn_pct
    warn_pct: 75                   # host memory use threshold for extra cooldown
    critical_pct: 85               # host memory use threshold for route/abort
    on_pressure: route             # cool_down | route | abort
    pressure_state: paused         # required when on_pressure=route
    on_abort_route: failed         # final state when on_pressure=abort
```

Implementation outline:

1. New module `scripts/little_loops/fsm/host_guard.py` with `HostGuardConfig` (dataclass mirroring the YAML block) and a `vm_stat` (macOS) + `/proc/meminfo` (Linux) probe — no `psutil` dep.
2. Add `host_guard` block to `scripts/little_loops/fsm/fsm-loop-schema.json` with full validation.
3. Wire into `FSMExecutor.__init__` (build the guard from `fsm.host_guard`) and `FSMExecutor.run` (call `guard.pre_state()` immediately after `state_enter`).
4. Add events: `host_pressure`, `host_pressure_relieved`, `host_pressure_abort`, `host_cooldown` — flow through the existing `_emit()` callback.
5. New CLI flag `--no-host-guard` on `ll-loop run` (mirrors `--no-llm`).
6. New `_host_guard` field on `FSMExecutor` parallel to `_circuit` and `_stall_detector`.

## Success Metrics

- A loop running 20+ prompt states never causes macOS jetsam to kill a sibling interactive session (manual verification with `log show` filter on `Jetsam` events before/after the fix).
- The guard adds < 50 ms per-state overhead in the common case (no `vm_stat` invocation if disabled, or single `vm_stat` round-trip otherwise).
- `ll-loop doctor` flags existing heavy loops (estimated by prompt-state count > N) that have `host_guard: enabled: false` and recommends enabling it.

## Scope Boundaries

- Does not address cumulative subprocess RSS budget — see ENH-2453 (the second layer of the design).
- Does not add cgroup or `RLIMIT_RSS` enforcement — macOS doesn't support them and Linux is best-effort.
- Does not modify the `parallel:` state resource guard — ENH-1176 owns that scope.
- Does not auto-tune the thresholds per-host.
- Does not change the existing `--delay` behavior (it remains a CLI knob and per-state `backoff:` field; the guard is the *adaptive* complement).

## API/Interface

- New `fsm.host_guard` YAML block (see Proposed Solution).
- New CLI flag `--no-host-guard` on `ll-loop run`.
- New `HostGuardConfig` dataclass in `scripts/little_loops/fsm/host_guard.py`.
- New events in the run's events stream: `host_pressure`, `host_pressure_relieved`, `host_pressure_abort`, `host_cooldown`.
- New `--no-host-guard` field on `FSMExecutor` constructor parallel to existing `circuit`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/host_guard.py` — new module (~150 LOC).
- `scripts/little_loops/fsm/executor.py` — wire `_host_guard` into `__init__` and `run()`.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `host_guard` block.
- `scripts/little_loops/cli/loop/__init__.py` — add `--no-host-guard` argument.
- `scripts/little_loops/cli/loop/run.py` and `lifecycle.py` — pass `host_guard.enabled = False` when `--no-host-guard`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:1356` — propagates `--delay` to sub-`ll-loop` invocations; mirror that for `--no-host-guard`.

### Similar Patterns to Reuse
- `circuit.repeated_failure` (FSA-correct routing with `on_repeated_failure: abort|route:<state>`) — same vocabulary for `on_pressure`.
- `RateLimitCircuit` (per-action pre-check before launching the LLM subprocess) — same pre-action hook point.
- `StallDetector` (event emission pattern in `run()`) — same shape for the new `host_pressure*` events.
- `_interruptible_sleep` primitive — same sleep primitive for the extra cooldown.

### Tests
- `scripts/tests/test_host_guard.py` (new): unit tests for the `vm_stat`/`meminfo` probe (mocked subprocess output) and the `HostGuardConfig` dataclass.
- `scripts/tests/test_executor.py` (extend): integration tests for `pre_state` routing.
- `scripts/tests/test_cli_loop.py` (extend): `--no-host-guard` flag parsing.

### Documentation
- `docs/reference/CLI.md` — document `--no-host-guard`.
- `docs/reference/API.md` — document `HostGuardConfig` and the new events.
- `docs/guides/LOOPS_GUIDE.md` — document the `fsm.host_guard` block.
- `docs/development/TROUBLESHOOTING.md` — add a "jetsam-killed session during ll-loop" entry pointing to this issue.

### Configuration
- New `host_guard` block in loop YAML (per-loop opt-in/opt-out).
- New `--no-host-guard` CLI flag (per-run override).
- No new global config keys (no `ll-config.json` surface needed for v1).

## Implementation Steps

1. Add `HostGuardConfig` dataclass + `vm_stat`/`meminfo` probe (no new deps).
2. Add `host_guard` block to `fsm-loop-schema.json` with full validation.
3. Wire into `FSMExecutor.__init__` and `run()` (mirror `_circuit` and `_stall_detector` shape).
4. Add `--no-host-guard` CLI flag.
5. Emit `host_pressure` / `host_pressure_relieved` / `host_pressure_abort` / `host_cooldown` events.
6. Add unit tests for the probe (mocked `vm_stat` output) and the executor integration.
7. Add an integration test: run `ll-loop run brainstorm` with `--no-host-guard` and assert no `host_pressure` events; run with default guard and a mocked high-pressure probe, assert `host_pressure` event + `host_pressure_abort` route.
8. Update docs (CLI.md, API.md, LOOPS_GUIDE.md, TROUBLESHOOTING.md).

## Impact

- **Priority**: P2 — significant user-impacting failure mode (silent jetsam kill of interactive session); no current mitigation beyond manually setting `--delay`.
- **Effort**: Medium — ~150 LOC + schema block + tests + docs. Reuses existing patterns (`circuit`, `RateLimitCircuit`, `StallDetector`) so design risk is low.
- **Risk**: Low — default-enabled with conservative thresholds means existing loops get slower but not broken. The `vm_stat` shell-out is portable macOS-only; the `meminfo` path is Linux-only; loops running on either platform get the right probe.
- **Breaking Change**: No — `host_guard` is a new optional field; loops that don't declare it get the default (enabled, conservative thresholds). Existing loops remain runnable as-is.

## Related Key Documentation

- `docs/reference/CLI.md` (`--delay` flag documentation)
- `docs/guides/LOOPS_GUIDE.md` (`backoff` per-state field)
- `docs/reference/API.md` (FSMExecutor / circuit config)

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P2

Implemented: new `scripts/little_loops/fsm/host_guard.py` (`HostGuardConfig`, `HostGuard`, `vm_stat`/`meminfo` probes — no psutil), `host_guard` block in `fsm-loop-schema.json` + `validate_fsm` checks, `_host_guard` wiring in `FSMExecutor` (pre-state check after `state_enter`; events `host_pressure`/`host_pressure_relieved`/`host_pressure_abort`/`host_cooldown`), `--no-host-guard` on `ll-loop run`/`resume` with background forwarding. Tests in `scripts/tests/test_host_guard.py` + `test_cli_loop_dispatch.py`. Docs: CLI.md, API.md, LOOPS_GUIDE.md (Host Guard section), TROUBLESHOOTING.md (jetsam entry).

## Session Log

- `/ll:capture-issue` - 2026-07-03T02:05:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ff12421-1849-4d8d-abe4-d955b4becd84.jsonl`

> **Historical duplicate ID (normalize-issues 2026-07-10):** number `2452` is a cross-type duplicate shared with **FEAT-2452** (`workerpool-and-dataclass-wiring`). Both issues are `done` and embedded in shipped code/CHANGELOG/git history, so neither was renumbered — the type prefix disambiguates them. (The four resolvable collisions 2519/2520/2521, 2575/2576/2577, and 2530 were renumbered to 2580–2586 the same day.)
