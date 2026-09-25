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

- `hooks/scripts/context-monitor.sh` combines measured baselines with heuristic overhead, including after the `result_token_count` branch; its `estimated_tokens` is not measured occupancy.
- Nothing marks a measured sample as stale after tool activity or compaction.

## Expected Behavior

- A measured baseline plus estimated overhead is labelled `estimated`.
- Metadata identifies metric, session/context scope and observation boundary. Never label invocation consumption as measured occupancy. Correcting consumption-as-occupancy value selection and resulting handoff decisions belongs to BUG-3587; this issue only adds labels/staleness to existing values.
- A sample becomes stale when context changes or compaction occurs; the observation boundary is recorded.
- With neither a valid measurement nor an estimator, the value is unavailable, never a fabricated zero. The existing estimator and numeric guard inputs stay in place here; BUG-3587 owns correcting their metric selection.

## Scope Boundaries

- **In scope**: additive estimated/stale labels, observation-boundary metadata, and propagation through the context-state fallback text/JSON and `context-health-monitor.yaml`.
- **Out of scope**: threshold/value-selection changes (BUG-3587), estimator accuracy, and redesign of ENH-3528 rendering. Wiring these new fields into the existing rendering contract is in scope. BUG-3587 and this issue can land independently; their changes compose without a dependency cycle.

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
- Producer boundary: `scripts/little_loops/issue_manager.py:_on_usage_writer` writes unqualified invocation consumption today; BUG-3587 owns correcting its value selection. Metadata must not certify this field as occupancy.
- Tests: `test_hooks_integration.py`, `test_cli_ctx_stats.py`, `test_enh3528_token_provenance.py`.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium.
- **Risk**: Low — labels only; thresholds unchanged.

## Acceptance Criteria

- [ ] Baseline measurement and estimate-update timestamps are distinct; a new estimate after tool activity/compaction cannot make the baseline fresh.
- [ ] Fallback text and JSON expose staleness, reasons, scope and available observation times; legacy state files render with conservative unknown freshness.
- [ ] Metadata does not relabel `result_token_count` as measured occupancy. BUG-3587 separately owns the behavior correction; this issue's changes preserve numeric values and guard decisions.

- [ ] Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation.
- [ ] Handoff/threshold behavior is unchanged (existing `test_hooks_integration.py` expectations hold).
- [ ] Context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md` and `docs/development/TROUBLESHOOTING.md` are updated.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
