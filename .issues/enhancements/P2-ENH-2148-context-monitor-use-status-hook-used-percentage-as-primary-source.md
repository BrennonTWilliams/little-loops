---
id: ENH-2148
type: ENH
title: "context-monitor: use Status hook used_percentage as zero-cost authoritative source"
priority: P2
status: open
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

## Implementation Steps

1. Add `context-status.sh` handler using `Status` hook (this issue)
2. Set `context_monitor.use_transcript_baseline: false` on Claude Code host
   (keep it `true` for OpenCode/Codex fallback in `PostToolUse`)
3. After stabilization, lower PostToolUse monitor to sampling-only mode
   (fire every Nth call) via `ll_config_value "context_monitor.sample_rate"`

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


## Session Log
- `/ll:format-issue` - 2026-06-14T04:14:43 - `e2e0a70e-86e6-49f1-872f-c22e27207788.jsonl`
