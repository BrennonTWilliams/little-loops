---
id: ENH-2148
type: ENH
title: 'context-monitor: use Status hook used_percentage as zero-cost authoritative
  source'
priority: P2
status: deferred
discovered_date: 2026-06-13
discovered_by: research-review
labels:
- context-monitor
- hooks
- accuracy
- performance
parent: EPIC-2149
relates_to:
- BUG-2145
- BUG-865
- BUG-924
- BUG-869
confidence_score: 98
outcome_confidence: 74
decision_needed: false
score_complexity: 20
score_test_coverage: 10
score_ambiguity: 22
score_change_surface: 22
implementation_order_risk: true
size: Very Large
---

# ENH-2148: context-monitor — use Status hook `used_percentage` as primary data source

## Current Behavior

`context-monitor.sh` registers on `PostToolUse` and estimates context usage by
reading the JSONL session transcript and running `jq` processing — all within
the 5s hook timeout. This produces stale, heuristic estimates:

- **Latency**: ~50–100ms cold start per tool call (vs. ~2.5ms for stdin-only reads)
- **Inaccuracy**: Misses system prompts, MCP schemas, and hook overhead that Claude
  Code's internal accounting includes (root cause of BUG-2145, BUG-2146)
- **Timeout risk**: JSONL read + `jq` slurp under 5s budget causes BUG-924
- **Over-firing**: Fires on every tool call regardless of whether the UI has re-rendered

## Expected Behavior

A new `context-status.sh` handler registered on the `Status` hook reads
`context_window.used_percentage` directly from stdin JSON — authoritative,
zero-cost, and accurate to Claude Code's own internal accounting:

- Runs in ~2.5ms (no JSONL I/O, no `jq`), safely within the 2s hook timeout
- Threshold comparison is exact (not heuristic); handoff reminder fires at the
  configured `auto_handoff_threshold` only
- `used_percentage` accounts for system prompts, MCP schemas, and hook overhead
- The `PostToolUse` handler is retained as a fallback for OpenCode and Codex,
  which do not emit `Status` events

## Summary

Claude Code's `Status` hook event pipes a JSON payload via stdin containing
`context_window.used_percentage`, `context_window.total_input_tokens`, and
`context_window.total_output_tokens` on every UI render. This is the
authoritative, zero-cost, fully accurate real-time context signal — no JSONL
parsing, no heuristics, no latency. Our `context-monitor.sh` currently fires
on `PostToolUse` and performs expensive JSONL reads + jq processing within the
5s hook timeout. Adopting the `Status` hook would eliminate the root causes of
BUG-865, BUG-924, and BUG-869.

## Research Validation

From `docs/research/claude-code-token-estimation-python.md`:

> The `statusline` hook is the foundational data source for all real-time
> monitoring. Claude Code pipes `context_window` JSON payloads via stdin
> containing `used_percentage`, `remaining_percentage`,
> `context_window_size` (200,000), `total_input_tokens`, and
> `total_output_tokens` on every UI render (hook event `Status`). This is
> the only zero-cost, fully authoritative real-time context data source.

Performance benchmark from the same report:
- Rust statusline (stdin JSON only): ~2.5ms cold start (lower bound)
- Python/Node with JSONL parsing: ~50ms+ cold start, ~100ms+ full refresh
- Our current jq-based approach in a 5s timeout budget → BUG-924

## Status Hook Payload Shape

```json
{
  "context_window": {
    "total_input_tokens": 65892,
    "total_output_tokens": 643,
    "used_percentage": 33.2,
    "remaining_percentage": 66.8,
    "context_window_size": 200000
  }
}
```

`used_percentage` is computed by Claude Code itself from authoritative internal
state — it accounts for system prompts, MCP schemas, and hook overhead that
API billing fields miss. This directly solves BUG-2145 (stale baseline) and
BUG-2146 (double-counted overhead).

## Proposed Solution

**Add a new `Status` hook handler** (`hooks/scripts/context-status.sh`) that:
1. Reads stdin JSON and extracts `context_window.used_percentage`
2. Compares against the configured `auto_handoff_threshold`
3. Writes minimal state (usage %, total tokens) to `ll-context-state.json`
4. Emits the handoff reminder (exit 2) when threshold crossed

This replaces the JSONL-parsing path in `context-monitor.sh` for all accuracy
and latency concerns. The existing `PostToolUse` handler can remain as a
fallback for hosts that don't emit `Status` events (OpenCode, Codex).

**`hooks/hooks.json`** addition:
```json
{
  "Status": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-status.sh",
          "timeout": 2,
          "statusMessage": "Monitoring context..."
        }
      ]
    }
  ]
}
```

The 2s timeout (vs 5s for PostToolUse) is safe because the handler does no
file I/O — just stdin parse + threshold compare + optional state write.

## Bugs Resolved by This Change

| Bug | Root Cause | How Status Hook Fixes It |
|---|---|---|
| BUG-865 (exits 2 on every call) | PostToolUse fires on every tool, heuristic always fires | Status only fires when Claude Code renders; threshold comparison is exact |
| BUG-924 (jq timeout) | JSONL read + jq-s slurp in PostToolUse | No JSONL read; stdin JSON parse only |
| BUG-869 (lock timeout margin) | Lock competition in PostToolUse | Reduced timeout headroom with 2s budget |
| BUG-2145 (stale baseline) | JSONL read-once caching | `used_percentage` is authoritative per-render |

## Acceptance Criteria

- [ ] `hooks/scripts/context-status.sh` reads `context_window.used_percentage` from stdin JSON and completes in < 2 s with no JSONL file I/O
- [ ] Exits 0 silently when `used_percentage` < `auto_handoff_threshold`
- [ ] Exits 2 with `[ll] Context X% used...` on stderr when `used_percentage` ≥ `auto_handoff_threshold` and handoff is not yet complete
- [ ] Handoff reminder is rate-limited to once per 60 s (reuse pattern from `context-monitor.sh` lines 387–395 using `to_epoch`)
- [ ] Exits 0 silently when `context_monitor.enabled` is `false`
- [ ] Writes `used_percentage`, `total_input_tokens`, and `last_reminder_at` to `ll-context-state.json` without overwriting `result_token_count` (written by `issue_manager.py`)
- [ ] `hooks/hooks.json` contains a `Status` entry with `timeout: 2` pointing to `context-status.sh`
- [ ] `PostToolUse` handler (`context-monitor.sh`) continues to fire unchanged — no regression for OpenCode/Codex
- [ ] `ll-ctx-stats` (`scripts/little_loops/cli/ctx_stats.py:_render_fallback()` and `_print_json()`) displays `used_percentage` from fallback state when field is present — requires modifying both render paths to surface the new field (currently silently ignored)

## Implementation Steps

1. Create `hooks/scripts/context-status.sh` (~40–50 lines): source `hooks/scripts/lib/common.sh`, gate on `ll_feature_enabled "context_monitor.enabled"`, read stdin with `INPUT=$(cat)`, extract fields in a single `jq @tsv` pass using `(.context_window.used_percentage // 0 | floor)` to coerce the float to int for bash `[ -ge ]` comparison (store raw float separately for state write), compare integer against `ll_config_value "context_monitor.auto_handoff_threshold" "80"`, write `used_percentage` / `total_input_tokens` / `status_last_reminder_at` (NOT `last_reminder_at` — that field is owned by `context-monitor.sh`) into state via a field-level jq merge (read existing → `jq ". + {new_fields}"` → `atomic_write_json`) to avoid clobbering `result_token_count` or `estimated_tokens`, apply 60 s rate-limit using `to_epoch "${STATUS_LAST_REMINDER_AT:-}"`, exit 2 with stderr message when threshold crossed
2. Add `Status` hook entry to `hooks/hooks.json` (no `matcher` field, `timeout: 2`) pointing to `context-status.sh`; model on existing Stop entry format (lines 133–141)
3. Set `context_monitor.use_transcript_baseline: false` in `.ll/ll-config.json` for Claude Code host (keep `true` for OpenCode/Codex fallback in `PostToolUse`)
4. Add `TestContextStatus` test class to `scripts/tests/test_hooks_integration.py`: for threshold/state assertions model after `TestContextHandoffSentinel` (lines 2298–2488, e.g. `test_sentinel_written_above_threshold` / `test_sentinel_not_written_below_threshold` shape); for the subprocess invocation itself use `TestContextMonitor`'s call pattern (lines 57–63: `subprocess.run([str(hook_script)], input=json.dumps(payload), capture_output=True, text=True, timeout=3)`) with Status stdin payload `{"context_window": {"used_percentage": 85.0, "total_input_tokens": 170000, "context_window_size": 200000}}`; include rate-limit suppression test (two sequential calls: first exits 2, second exits 0) following `test_reminder_rate_limited_second_call` (lines 435–488); include inverse test (cooldown expired → re-fires) following `test_reminder_fires_again_after_cooldown_expires` (lines 622–678) which pre-seeds `status_last_reminder_at` as 120s ago via `datetime.now(UTC) - timedelta(seconds=120)` in the state file, then asserts exit 2; and `status_last_reminder_at` field isolation test (confirm `last_reminder_at` written by PostToolUse handler is not mutated after `context-status.sh` runs); also update `scripts/tests/test_cli_ctx_stats.py` to add a fallback-with-used-percentage test that pre-seeds `{"estimated_tokens": 50000, "tool_calls": 5, "used_percentage": 33.2}` in `ll-context-state.json` and asserts `_render_fallback()` output contains `"33.2"` and `_print_json()` output includes `"used_percentage"` key
5. After stabilization, lower `PostToolUse` monitor to sampling-only mode via `ll_config_value "context_monitor.sample_rate"`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reference implementation**: `hooks/scripts/context-handoff-sentinel.sh` — simplest existing stdin→config→threshold→file-write→exit-2 pattern; closest structural analog to `context-status.sh`
- **Atomic state writes**: `hooks/scripts/lib/common.sh:atomic_write_json()` (lines 59–85) — use this for all state file mutations; it writes to `.tmp.$$`, validates with `jq empty`, then `mv -f`
- **Rate-limiting pattern**: `hooks/scripts/context-monitor.sh` lines 387–395 — `to_epoch "${LAST_REMINDER_AT:-}"` + 60 s comparison; `to_epoch` handles both macOS `date -j` and GNU `date -d`
- **Rate-limit field name**: do NOT reuse `last_reminder_at` — that field is written by `context-monitor.sh` (line 399) and read back by it (line 250); sharing it across handlers causes cross-handler interference. Use a separate `status_last_reminder_at` field for `context-status.sh`'s 60 s cooldown
- **Config read pattern**: `THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"` — env var wins; see `context-monitor.sh` line 26
- **Float coercion**: `used_percentage` is a float (e.g. `33.2`); bash `[ -ge ]` only handles integers. Extract as integer via jq: `(.context_window.used_percentage // 0 | floor)` so the comparison is `[ "$USED_PCT_INT" -ge "$THRESHOLD" ]`. The raw float should still be written to the state file for display accuracy
- **`result_token_count` field**: written by `scripts/little_loops/issue_manager.py:_on_usage_writer()` (lines 571–579) without a lock; `context-status.sh` must merge its fields without clobbering this key — use a `jq` field-level merge: read existing state with `jq ". + {key: val}"` (or `jq --arg v "$V" '. + {"used_percentage": ($v | tonumber), "status_last_reminder_at": $t}'`) rather than full document replacement
- **State file readers**: `session_start.py` (deletes on startup), `pre_compact.py` (reads before compaction), `ctx_stats.py:_load_fallback_state()` (line 164), `merge_coordinator.py` (skips merging this file in parallel runs)
- **hooks.json `Status` entry**: does not exist yet; registration uses no `matcher` field (same as Stop hook, lines 133–141 of `hooks/hooks.json`)
- **Test class analog**: `TestContextHandoffSentinel` (lines 2298–2488 of `test_hooks_integration.py`) is the closer structural model for `TestContextStatus` — it tests threshold-based exit behavior with pre-seeded state, not stdin tool processing. Use its `test_sentinel_written_above_threshold` / `test_sentinel_not_written_below_threshold` shape. For the stdin JSON invocation itself, follow `TestContextMonitor`'s `subprocess.run([hook_script], input=json.dumps(payload), ...)` call pattern (lines 57–63) with Status payload `{"context_window": {"used_percentage": 85.0, "total_input_tokens": 170000, "context_window_size": 200000}}`
- **Inverse rate-limit test pattern**: `TestContextMonitor.test_reminder_fires_again_after_cooldown_expires` (lines 622–678 of `test_hooks_integration.py`) — pre-seeds `last_reminder_at` (use `status_last_reminder_at` for the Status handler) as 120 seconds in the past via `(datetime.now(UTC) - timedelta(seconds=120)).strftime(...)` in the state file, then asserts the hook exits 2 again. Mirror this shape for the `TestContextStatus` cooldown-expired case.
- **`test_cli_ctx_stats.py` gap**: `scripts/tests/test_cli_ctx_stats.py` has a fallback test at line ~198 that pre-seeds only `{"estimated_tokens": ..., "tool_calls": ...}` — no `used_percentage` assertions exist. The test for `_render_fallback()` / `_print_json()` displaying the new field must be added to this file as part of Step 4.

## Integration Map

### Files to Create
- `hooks/scripts/context-status.sh` — new Status hook handler (~40–50 lines)

### Files to Modify
- `hooks/hooks.json` — add `Status` entry with `timeout: 2`
- `.ll/ll-config.json` — set `context_monitor.use_transcript_baseline: false` (Claude Code host; leave `true` for other hosts)
- `scripts/little_loops/cli/ctx_stats.py` — `_render_fallback()` (accesses only `estimated_tokens`, `tool_calls`, `breakdown`) and `_print_json()` both silently ignore `used_percentage`; modify to display it when present in the fallback state dict

### Shell Library (Source-Only)
- `hooks/scripts/lib/common.sh` — provides `ll_resolve_config`, `ll_feature_enabled`, `ll_config_value`, `acquire_lock`, `release_lock`, `atomic_write_json`, `to_epoch`, `get_mtime`

### State File Compatibility Surface
- `scripts/little_loops/hooks/session_start.py` — deletes `ll-context-state.json` on startup; any new fields written by `context-status.sh` are cleared per session
- `scripts/little_loops/hooks/pre_compact.py` — reads `estimated_tokens`, `tool_calls`, etc. before compaction; new fields must not break its JSON reads
- `scripts/little_loops/issue_manager.py` — writes `result_token_count` to state (`_on_usage_writer()`, lines 571–579); `context-status.sh` must not overwrite this field
- `scripts/little_loops/cli/ctx_stats.py` — reads `ll-context-state.json` as fallback (`_load_fallback_state()`, line 164); **requires code change**: `_render_fallback()` and `_print_json()` both silently ignore unknown fields — `used_percentage` will not display unless those functions are updated (see "Files to Modify" above)
- `scripts/little_loops/parallel/merge_coordinator.py` — skips merging `ll-context-state.json` during parallel runs (line 172); no action needed

### Tests
- `scripts/tests/test_hooks_integration.py` — add `TestContextStatus` class mirroring `TestContextMonitor` (lines 14–1232)
- `scripts/tests/test_cli_ctx_stats.py` — add tests for `_render_fallback()` and `_print_json()` displaying `used_percentage` when field is present in fallback state; existing fallback test at line ~198 covers only the basic path and has no `used_percentage` assertions

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add section describing new Status hook handler alongside existing PostToolUse context-monitor entry

## Scope Boundaries

- Removing the PostToolUse handler (needed for non-Claude-Code hosts)
- Adding burn-rate prediction or "turns remaining" estimates (future)
- Prometheus/OTel export (separate greenfield opportunity per research report)

## Impact

- **Priority**: P2 — Root-cause fix for BUG-865, BUG-924, BUG-869, BUG-2145, and BUG-2146; context monitoring accuracy is critical harness infrastructure
- **Effort**: Medium — New shell handler (~30 lines), one `hooks/hooks.json` entry, one config flag; stabilization period before PostToolUse can be downgraded
- **Risk**: Low — Purely additive; existing PostToolUse handler unchanged until stabilization confirms parity
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-13 | Priority: P2


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-14_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Shell hook test coverage gap** — `context-status.sh` will start with zero automated coverage; `TestContextStatus` class is a co-deliverable of Step 4, so tests are written as part of implementing the script, not after. Follow `TestContextMonitor` (lines 14–1232 of `test_hooks_integration.py`) for the stdin payload pattern and `TestContextHandoffSentinel` (lines 2298–2488) for threshold/state-write assertions.

## Session Log
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `43a26be2-978c-4f32-991b-56383441ef58.jsonl`
- `/ll:refine-issue` - 2026-06-14T06:46:37 - `c724eff9-ab57-4466-b21b-f40c5a7050c4.jsonl`
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `f2822c8c-9f26-4b9a-b2e4-5e8125a9f221.jsonl`
- `/ll:refine-issue` - 2026-06-14T06:35:12 - `2acea60f-75a8-4db0-b8ce-8c5cf7523a09.jsonl`
- `/ll:refine-issue` - 2026-06-14T06:25:20 - `ab6f1892-037c-46e2-98a7-0945269c4f31.jsonl`
- `/ll:format-issue` - 2026-06-14T04:14:43 - `e2e0a70e-86e6-49f1-872f-c22e27207788.jsonl`
- `/ll:confidence-check` - 2026-06-14T04:20:00Z - `d0d40044-58bf-4615-8102-ea8da992e5ea.jsonl`
- `/ll:confidence-check` - 2026-06-14T07:00:00Z - `ab6f1892-037c-46e2-98a7-0945269c4f31.jsonl`
