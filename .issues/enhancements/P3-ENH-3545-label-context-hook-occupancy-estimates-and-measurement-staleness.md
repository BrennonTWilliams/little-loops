---
id: ENH-3545
type: ENH
title: Label context-hook occupancy estimates and measurement staleness
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:14Z'
labels:
- observability
relates_to:
- ENH-3528
- BUG-3587
---

# ENH-3545: Label context-hook occupancy estimates and measurement staleness

## Summary

Label context-occupancy figures produced by the context hooks as `estimated`, and expose when a measured baseline has gone stale, without changing thresholds. Split out of ENH-3528 (its Implementation Step 5), which already marked this work as separable.

## Current Behavior

_Refreshed 2026-09-28 after BUG-3587 landed (b3b452e40)._

- `hooks/scripts/context-monitor.sh` computes `estimated_tokens` as `transcript_baseline_tokens + TOKENS` (per-tool heuristic) when a transcript baseline exists, else `estimated_tokens + TOKENS`. The baseline is a measurement of the transcript at `last_baseline_mtime`; the sum is an estimate, but nothing labels it.
- BUG-3587 removed the `result_token_count` tier from `context-monitor.sh` and `context-handoff-sentinel.sh` and deleted the issue-manager on-usage writer closure; invocation consumption no longer enters the state file or guard decisions. The sentinel now uses `estimated_tokens` only.
- State files written before BUG-3587 may still carry a stale `result_token_count` key; nothing reads it.
- Nothing marks a baseline as stale after tool activity or compaction, and the state distinguishes neither baseline measurement time nor estimate update time (`last_baseline_mtime` is the transcript file's mtime, not an observation timestamp).

## Expected Behavior

- A measured baseline plus estimated overhead is labelled `estimated`; a pure heuristic accumulation (no baseline) is also `estimated`, with a reason distinguishing the two.
- Metadata identifies metric, session/context scope and observation boundary. Invocation consumption is never labelled occupancy; a legacy `result_token_count` key is ignored and never surfaced as a measurement.
- A baseline becomes stale when context changes (tool activity after the baseline) or compaction occurs; the observation boundary is recorded.
- With neither a valid measurement nor an estimator, the value is unavailable, never a fabricated zero. Numeric values and guard inputs are unchanged.

## Scope Boundaries

- **In scope**: additive estimated/stale labels, observation-boundary metadata, and propagation through the context-state fallback text/JSON and `context-health-monitor.yaml`.
- **Out of scope**: threshold/value-selection changes (done in BUG-3587), estimator accuracy, and redesign of ENH-3528 rendering. Wiring these new fields into the existing rendering contract is in scope.

## Program Design

### Types

- Context-state JSON gains additive metric/scope metadata, `provenance` (`measured | estimated | unknown`), `baseline_observed_at`, `estimate_updated_at`, and `stale` (`bool | null`, null when freshness is unknown) with `stale_reason`. Retain an `observed_at` compatibility field only with a documented meaning; it must not conflate baseline measurement time and estimate refresh time.
- Baseline freshness is relative to its session/context boundary. Tool activity or compaction invalidates an older baseline; recomputing an estimate does not advance `baseline_observed_at` or clear its staleness. A new valid measurement of the same metric/scope may do so. Existing state without evidence gets unknown freshness; do not invent a timestamp from read time.

### Signatures

- `_load_fallback_state(path: Path) -> dict[str, Any] | None` — unchanged (`little_loops.cli.ctx_stats`); must tolerate the additive fields and state files that lack them.
- Hook scripts: fields are additive to the state file; `context-handoff-sentinel.sh` threshold logic is unchanged.

### Call Path

- `context-monitor.sh` → context-state file → `_load_fallback_state` → `_render_fallback`
- `context-monitor.sh` → context-state file → `context-handoff-sentinel.sh` / `context-health-monitor.yaml`

## Integration Map

- `hooks/scripts/context-monitor.sh`, `hooks/scripts/context-handoff-sentinel.sh`, `scripts/little_loops/loops/context-health-monitor.yaml`, `scripts/little_loops/cli/ctx_stats.py` (`_fallback_provenance`, fallback text/JSON), `scripts/little_loops/token_provenance.py`.
- Producer boundary: the issue-manager on-usage writer closure was removed by BUG-3587; no Python producer writes the context-state file's token fields now. Only `context-monitor.sh` writes them.
- Tests: `test_hooks_integration.py`, `test_cli_ctx_stats.py`, `test_enh3528_token_provenance.py`.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium.
- **Risk**: Low — labels only; thresholds unchanged.

## Acceptance Criteria

- [ ] Baseline measurement and estimate-update timestamps are distinct; a new estimate after tool activity/compaction cannot make the baseline fresh.
- [ ] Fallback text and JSON expose staleness, reasons, scope and available observation times; legacy state files render with conservative unknown freshness.
- [ ] A legacy state file carrying `result_token_count` renders without surfacing it as a measurement; this issue's changes preserve numeric values and guard decisions.

- [ ] Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation.
- [ ] Handoff/threshold behavior is unchanged (existing `test_hooks_integration.py` expectations hold).
- [ ] Context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md` and `docs/development/TROUBLESHOOTING.md` are updated.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
