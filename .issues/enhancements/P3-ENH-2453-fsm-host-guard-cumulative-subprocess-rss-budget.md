---
id: ENH-2453
title: fsm.host_guard — cumulative subprocess RSS budget
type: ENH
parent: EPIC-2455
priority: P3
status: done
labels: [fsm, host-guard, captured]
captured_at: "2026-07-03T02:05:57Z"
discovered_date: "2026-07-02"
discovered_by: capture-issue
---

# ENH-2453: fsm.host_guard — cumulative subprocess RSS budget

## Summary

Add a cumulative subprocess RSS budget to the FSM host guard. Track the peak resident memory of each spawned subprocess (via `ps -o rss=` sampling at start and end, or `top -l 1 -pid PID` on macOS), accumulate across the run, and route or abort when the cumulative total exceeds a configured ceiling. Pairs with ENH-2452 (the adaptive pressure gate) as the second tier of the host-pressure defense.

## Current Behavior

The `fsm.host_guard` block from ENH-2452 samples system memory globally. There is no per-loop accounting for how much *subprocess memory the loop itself has spawned*. A loop running 13 sequential `claude` subprocesses can pass the system-pressure check (because the global used-memory drops between spawns) but still starve a neighbor via cumulative spike. ENH-1176 (parallel-state resource limits) calls out "no memory/file-handle cap on held subprocesses" as missing for `parallel:` state fan-out specifically, but the same gap exists in the general FSM context.

## Expected Behavior

New fields on the `fsm.host_guard` block:

```yaml
fsm:
  host_guard:
    max_cumulative_subproc_mb: 0   # 0 = disabled; otherwise cap on summed peak RSS
    on_budget_exceeded: route      # route | abort
    budget_state: out_of_resources # required when on_budget_exceeded=route
```

When `max_cumulative_subproc_mb > 0`, the runner samples the spawned subprocess's peak RSS at completion (using the macOS `top -l 1 -pid PID -stats rsize` form, or `ps -o rss=` cross-platform fallback), adds it to a running sum, and when the sum exceeds the budget, emits `host_budget_exceeded` and either routes to `budget_state` or aborts. The cumulative sum is reset at the start of each run and is independent of `--max-iterations` restart cycles.

## Motivation

ENH-2452's global memory check protects against sustained pressure but is blind to short spikes from heavy individual states. A loop whose per-state RSS is moderate (say 400 MB peak) but whose *cumulative* across many states exceeds the host's available memory headroom will still jetsam a neighbor. The cumulative budget is the second line of defense: it owns the loop's *responsibility* for memory, not just the system's. The 2026-07-02 brainstorm incident (13 × 500 MB sequential) would have triggered this guard well before the 13th spawn if the budget were set to ~4 GB (a conservative default for an 8 GB machine).

## Proposed Solution

```yaml
fsm:
  host_guard:
    enabled: true
    cooldown_ms: 500
    warn_pct: 75
    critical_pct: 85
    on_pressure: route
    pressure_state: paused
    # NEW (this issue):
    max_cumulative_subproc_mb: 4096  # default 0 (disabled)
    on_budget_exceeded: route
    budget_state: out_of_resources
```

Implementation outline:

1. Extend `HostGuardConfig` (from ENH-2452) with the new fields.
2. Add `_cumulative_subproc_mb: int = 0` and `_current_run_subprocs: list[tuple[str, int]]` (for the events payload) to `FSMExecutor`.
3. Hook the RSS sample into the action runner's `run()` method (so every action mode — `prompt`, `slash_command`, `mcp_tool`, `contributed` — gets it). The sample is taken from the spawned process's PID via `subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)])` after the process exits.
4. Emit `host_subproc_rss` event per subprocess (modeled on `action_complete`'s token accounting shape) and `host_budget_exceeded` when the cumulative sum crosses the budget.
5. macOS-specific: use `top -l 1 -pid <pid> -stats rsize -n 0` for peak RSS (more accurate). Linux: `/proc/<pid>/status` `VmHWM` for peak.
6. Reuse the existing route/abort ladder shape from ENH-2452.

## Success Metrics

- A loop with `max_cumulative_subproc_mb: 4096` aborts or routes to `budget_state` after spawning ~8 × 500 MB subprocesses (deterministic, testable with a mock subprocess returning a fixed RSS).
- The per-subprocess RSS sample adds < 100 ms overhead (single `ps` call after process exit).
- `ll-loop doctor` flags loops with estimated peak-RSS-per-prompt × prompt-state-count > 50% of system memory as "should set max_cumulative_subproc_mb".

## Scope Boundaries

- Does not change the adaptive pressure gate (ENH-2452 owns that).
- Does not modify ENH-1176 (parallel-state resource limits). ENH-1176's "memory/file-handle cap" claim is for `parallel:` state fan-out; this issue's scope is the *general* FSM host.
- Does not add cgroup or `RLIMIT_RSS` enforcement — macOS doesn't support them.
- Does not measure the parent Python process's own RSS (only subprocesses it spawns).

## API/Interface

- Three new fields on `fsm.host_guard`: `max_cumulative_subproc_mb`, `on_budget_exceeded`, `budget_state`.
- Two new events in the run's events stream: `host_subproc_rss` (per subproc), `host_budget_exceeded` (per exceedance).
- New CLI flag `--host-guard-budget-mb N` on `ll-loop run` to override at runtime.
- New `max_cumulative_subproc_mb: int | None` field on `FSMExecutor` parallel to existing guard config.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/host_guard.py` — extend `HostGuardConfig` with the new fields; add `record_subproc_rss(pid, peak_rss_mb) -> None` method.
- `scripts/little_loops/fsm/executor.py` — track `_cumulative_subproc_mb`; check budget in `run()` after each state.
- `scripts/little_loops/fsm/runners.py` — sample peak RSS in `DefaultActionRunner.run()` after process exit.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — extend `host_guard` block.
- `scripts/little_loops/cli/loop/__init__.py` — add `--host-guard-budget-mb` argument.
- `scripts/little_loops/cli/loop/run.py` — pass the override.

### Dependent Files (Callers/Importers)
- Same call site as ENH-2452 — this is an additive extension.
- The action runner change is the only one that affects all action modes (prompt, slash_command, mcp_tool, contributed).

### Similar Patterns to Reuse
- `RateLimitCircuit.record_rate_limit(sleep)` — same accumulator pattern.
- `StallDetector._recurrent_counts` — same per-run state accumulator.
- `_run_action`'s `result.usage_events` aggregation (`executor.py:1296-1306`) — same shape for the per-subprocess accounting.

### Tests
- `scripts/tests/test_host_guard.py` (extend): test the budget accumulator with mocked RSS samples.
- `scripts/tests/test_runners.py` (new or extend): test the post-process RSS sample hook.
- `scripts/tests/test_executor.py` (extend): integration test for the `on_budget_exceeded` routing.

### Documentation
- `docs/reference/API.md` — document the new fields and events.
- `docs/guides/LOOPS_GUIDE.md` — document the new YAML keys.
- `docs/reference/CLI.md` — document `--host-guard-budget-mb`.

### Configuration
- Three new keys in the `fsm.host_guard` YAML block.
- One new CLI flag.
- No new global config keys (no `ll-config.json` surface for v1).

## Implementation Steps

1. Extend `HostGuardConfig` dataclass with the three new fields.
2. Add `_cumulative_subproc_mb` to `FSMExecutor` and the budget check in `run()`.
3. Add the `host_subproc_rss` sample hook to `DefaultActionRunner.run()`.
4. Emit `host_budget_exceeded` and the route/abort ladder.
5. Add the CLI override flag.
6. Add tests at all three layers.
7. Update docs.

## Impact

- **Priority**: P3 — important for long-running and heavy loops (brainstorm, deep-research), but ENH-2452 (the adaptive pressure gate) covers the common case. This is the second tier.
- **Effort**: Medium — ~100 LOC extension to ENH-2452's module + tests + docs. The post-process RSS sample is the trickiest piece (cross-platform peak-RSS detection).
- **Risk**: Medium — the `ps -o rss=` / `top -l 1` sampling is portable but noisy (RSS samples vary by ±5–10 MB run-to-run). Budget thresholds need to be conservative to avoid false-positive budget-exceeded routes. macOS-soft signal (no cgroups to enforce hard cap) means the budget is a *routing* signal, not a *containment* one.
- **Breaking Change**: No — all new fields are optional; default `max_cumulative_subproc_mb: 0` means existing loops are unaffected.

## Related Key Documentation

- `docs/reference/API.md` (`HostGuardConfig` from ENH-2452)
- `docs/guides/LOOPS_GUIDE.md` (`fsm.host_guard` block from ENH-2452)

## Related Issues

- **ENH-2452** (adaptive pressure gate) — prerequisite and sibling. The adaptive pressure gate is layer 1; this is layer 2.
- **ENH-1176** (parallel-state resource limits) — sibling scoped to `parallel:` state. ENH-1176's "memory/file-handle cap" claim remains parallel-only; this issue is the general-FSM counterpart.

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P3

Implemented: `max_cumulative_subproc_mb` / `on_budget_exceeded` / `budget_state` on `HostGuardConfig` + schema + validation; `HostGuard.record_subproc_rss()` accumulator (fires once at crossing); `ActionResult.peak_rss_mb`; `RssSampler` thread sampling (`/proc/<pid>/status` `VmHWM` on Linux, `ps -o rss=` fallback) wired into `DefaultActionRunner` (shell + prompt paths, gated on `sample_rss`) and the executor's mcp_tool `_run_subprocess`; `host_subproc_rss` + `host_budget_exceeded` events; route/abort ladder in `run()` (`terminated_by="host_budget_exceeded"` on abort); `--host-guard-budget-mb` CLI override with background forwarding. Tests in `scripts/tests/test_host_guard.py` + `test_cli_loop_dispatch.py`; docs in CLI.md/API.md/LOOPS_GUIDE.md.

## Session Log

- `/ll:capture-issue` - 2026-07-03T02:05:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ff12421-1849-4d8d-abe4-d955b4becd84.jsonl`

> **Historical duplicate ID (normalize-issues 2026-07-10):** number `2453` is a cross-type duplicate shared with **FEAT-2453** (`downstream-consumer-read-sites`). Both issues are `done` and embedded in shipped code/CHANGELOG/git history, so neither was renumbered — the type prefix disambiguates them. (The four resolvable collisions 2519/2520/2521, 2575/2576/2577, and 2530 were renumbered to 2580–2586 the same day.)
