---
id: ENH-3545
type: ENH
title: Label context-hook occupancy estimates and measurement staleness
priority: P3
status: done
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
completed_at: '2026-09-29T08:22:42Z'
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

- `hooks/scripts/context-monitor.sh` computes `NEW_TOKENS` as `TRANSCRIPT_BASELINE + TOKENS` (per-tool heuristic) when a transcript baseline exists, else `CURRENT_TOKENS + TOKENS`, and persists it as `estimated_tokens`. The baseline is a measurement of the transcript at `last_baseline_mtime`; the sum is an estimate, but nothing labels it.
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
- Occupancy is stored in context state and is not a `usage_events` consumption observation; EPIC-3562's counted-once stored-consumption goal applies to token consumption, while this issue supplies the separate occupancy provenance and freshness contract.

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

- [x] Baseline measurement and estimate-update timestamps are distinct; a new estimate after tool activity/compaction cannot make the baseline fresh.
- [x] Fallback text and JSON expose staleness, reasons, scope and available observation times; legacy state files render with conservative unknown freshness.
- [x] A legacy state file carrying `result_token_count` renders without surfacing it as a measurement; this issue's changes preserve numeric values and guard decisions.

- [x] Tests cover missing/stale measurements, tool activity between observations, and compaction invalidation.
- [x] Handoff/threshold behavior is unchanged (existing `test_hooks_integration.py` expectations hold).
- [x] Context-monitor examples in `BUILTIN_HOOKS_GUIDE.md`, `SESSION_HANDOFF.md` and `docs/development/TROUBLESHOOTING.md` are updated.

## Implementation Evidence

- Context-state writes now carry the estimate method, session and context boundary,
  baseline observation and estimate update times, and baseline freshness. The
  baseline observation advances only after a valid transcript read.
- The sentinel and context-health snapshot propagate these labels. The sentinel
  still uses `estimated_tokens` and the same percentage threshold.
- `ll-ctx-stats` fallback text and JSON show the context-occupancy provenance.
  Legacy files retain their numeric estimate with unknown freshness, and
  `result_token_count` remains ignored.
- Focused verification: context monitor and sentinel integration tests (37 passed),
  ctx-stats and token-provenance tests (122 passed), shell syntax, targeted Ruff
  and Mypy checks, and `ll-loop validate context-health-monitor`.

## Status

**Done** | Created: 2026-09-24 | Priority: P3


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Context-hook output separates occupancy estimates from consumption and exposes baseline freshness and observation times.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.


## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:42 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
