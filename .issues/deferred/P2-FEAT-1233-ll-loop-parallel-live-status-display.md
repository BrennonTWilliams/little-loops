---
discovered_date: "2026-04-21"
discovered_by: planning-discussion
confidence_score: 82
size: Small
depends_on: FEAT-1232
status: deferred
deferred_date: "2026-04-21"
deferred_reason: low-value
---

# FEAT-1233: Live Status Display for `ll-loop parallel`

## Summary

While `ll-loop parallel` blocks waiting for loops to finish, display a live-updating status table showing each loop's current state, iteration count, and elapsed time. Refresh by polling the state files on disk.

## Current Behavior

After FEAT-1232, `ll-loop parallel` starts loops and waits silently until all finish. There is no visibility into what each loop is doing during the run.

## Expected Behavior

While loops are running, print a refreshed status table every 5 seconds (or on terminal resize):

```
Running 3 loops in parallel  [0:02:14]

  loop              state            iter    elapsed
  ──────────────────────────────────────────────────
  code-review       evaluate         4/20    2m 14s
  test-watcher      wait-for-green   1/10    2m 14s
  dependency-audit  DONE ✓           8/8     1m 03s
```

- Each row shows: loop name, current state (read from `.state.json`), `current_iteration/max_iterations`, elapsed time since start.
- Completed loops show their terminal status (✓ for success, ✗ for failure) and stop updating.
- Table reprints in-place (clear previous output with ANSI escape) when stdout is a TTY; falls back to one line per poll when non-TTY (CI-friendly).
- `--no-status` flag on `ll-loop parallel` disables the table entirely (useful for scripting).

## Deferral Notes

Deferred as potentially low value. The live display is largely redundant with `ll-loop list --running`, which already shows state, iteration count, and status for all running loops. The only real addition is auto-refresh every 5s. More critically, this feature is artificially scoped to loops launched via `ll-loop parallel` — a general `ll-loop watch` (or `--watch` flag on `list --running`) would be more useful and serve all running loops regardless of launch method. If a watch/live-refresh capability becomes desirable, implement it as a standalone monitoring command rather than a parallel-launch dependency.

## Motivation

Without visibility into what each loop is doing, users have no way to tell if a parallel run is stuck, which loops are progressing, or when to expect completion.

## Acceptance Criteria

- [ ] Status table refreshes every 5s while any loop is still running
- [ ] Each row reads from `.loops/.running/<name>.state.json` (non-blocking; skip silently if file is missing)
- [ ] TTY mode: table redraws in-place without scrollback pollution
- [ ] Non-TTY mode: one progress line per poll (no ANSI movement codes)
- [ ] `--no-status` flag suppresses all intermediate output; only final summary is printed
- [ ] Completed loop rows persist with their final state and a done indicator
- [ ] No race conditions: read state files atomically (read-then-parse; don't crash on partial writes)

## Implementation Notes

- Add a `_display_parallel_status()` function in `parallel.py` (from FEAT-1232) that is called in the poll loop
- State fields to read: `current_state`, `current_iteration`, `max_iterations`, `terminated_by` (indicates done)
- Elapsed time: track `start_times: dict[str, float]` keyed by loop name in the launcher
- TTY detection: `sys.stdout.isatty()`; use `\033[{N}A` (cursor up N lines) + `\033[J` (clear to end) for in-place refresh
- Table column widths: compute from max name/state lengths at first render; don't recompute mid-run to avoid jitter
- Poll interval: 5s default; expose as `--status-interval` flag (int seconds, min 1) for power users
