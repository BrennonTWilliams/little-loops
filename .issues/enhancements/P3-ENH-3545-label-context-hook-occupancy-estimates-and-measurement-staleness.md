---
id: ENH-3545
type: ENH
title: Label context-hook occupancy estimates and measurement staleness
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
relates_to:
- ENH-3528
---

# ENH-3545: Label context-hook occupancy estimates and measurement staleness

## Summary

Label context-occupancy figures produced by the context hooks as `estimated`, and expose when a measured baseline has gone stale, without changing thresholds. Split out of ENH-3528 (its Implementation Step 5), which already marked this work as separable.

## Current Behavior

- `hooks/scripts/context-monitor.sh` combines measured baselines with heuristic overhead, including after the `result_token_count` branch; its `estimated_tokens` is not measured occupancy.
- Nothing marks a measured sample as stale after tool activity or compaction.

## Expected Behavior

- A measured baseline plus estimated overhead is labelled `estimated`.
- An estimate is replaced only by a measurement of the same metric, scope and interval; cumulative consumption is never used as occupancy.
- A sample becomes stale when context changes or compaction occurs; the observation boundary is recorded.
- With neither a valid measurement nor an estimator, the value is unavailable. The existing estimator stays in place.

## Scope Boundaries

- **In scope**: `estimated`/stale labels and observation-boundary metadata in the context hooks and `context-health-monitor.yaml`.
- **Out of scope**: threshold changes; estimator accuracy; `ll-ctx-stats` rendering (ENH-3528).

## Program Design

### Types

- Context-state JSON written by `context-monitor.sh` gains `provenance` (`measured | estimated`), `observed_at`, and `stale` (bool, with `stale_reason`).

### Signatures

- `_load_fallback_state(path: Path) -> dict[str, Any] | None` — unchanged (`little_loops.cli.ctx_stats`); must tolerate the additive fields and state files that lack them.
- Hook scripts: fields are additive to the state file; `context-handoff-sentinel.sh` threshold logic is unchanged.

### Call Path

- `context-monitor.sh` → context-state file → `_load_fallback_state` → `_render_fallback`
- `context-monitor.sh` → context-state file → `context-handoff-sentinel.sh` / `context-health-monitor.yaml`

## Integration Map

- `hooks/scripts/context-monitor.sh`, `hooks/scripts/context-handoff-sentinel.sh`, `scripts/little_loops/loops/context-health-monitor.yaml`.
- Tests: `test_hooks_integration.py`.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium.
- **Risk**: Low — labels only; thresholds unchanged.

## Acceptance Criteria

- [ ] Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation.
- [ ] Handoff/threshold behavior is unchanged (existing `test_hooks_integration.py` expectations hold).
- [ ] Context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md` and `docs/development/TROUBLESHOOTING.md` are updated.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
