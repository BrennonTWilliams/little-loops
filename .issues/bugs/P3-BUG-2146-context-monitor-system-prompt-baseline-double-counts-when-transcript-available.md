---
id: BUG-2146
type: BUG
title: "context-monitor: SYSTEM_PROMPT_BASELINE added even when transcript already includes it"
priority: P3
status: open
discovered_date: 2026-06-13
discovered_by: research-review
labels:
  - context-monitor
  - accuracy
  - jsonl
parent: EPIC-2149
relates_to:
  - BUG-2145
  - ENH-810
---

# BUG-2146: context-monitor SYSTEM_PROMPT_BASELINE double-counts with transcript baseline

## Summary

On the first PostToolUse call of a session, `context-monitor.sh` adds
`SYSTEM_PROMPT_BASELINE` (default 10,000 tokens) to `NEW_TOKENS` even when
the JSONL transcript baseline is already available — which already includes the
system prompt via `cache_read_input_tokens`. This inflates the first-call
estimate by ~10K tokens.

## Current Behavior

On the first PostToolUse call of a session, `context-monitor.sh` unconditionally
adds `SYSTEM_PROMPT_BASELINE` (10,000 tokens) to overhead regardless of whether
a JSONL transcript baseline is available. When `TRANSCRIPT_BASELINE > 0`, the
system prompt is double-counted: once via `cache_read_input_tokens` in the
transcript data, and once via the `SYSTEM_PROMPT_BASELINE` heuristic.

## Expected Behavior

`SYSTEM_PROMPT_BASELINE` is added to overhead on the first tool call only when
`TRANSCRIPT_BASELINE` is 0 or unavailable — serving as a pure-heuristic fallback
for sessions where no JSONL data exists. When transcript data is available, the
system prompt is already captured in `cache_read_input_tokens` and no additional
baseline should be applied.

## Steps to Reproduce

1. Start a Claude Code session in a project where JSONL transcripts exist
2. Invoke any tool to trigger a PostToolUse hook
3. Observe the context usage reported by `context-monitor.sh` for the first tool call
4. Compare reported token count against actual values from `usage_stats` in the JSONL
5. Note the first-call estimate exceeds actual by ~10,000 tokens (`SYSTEM_PROMPT_BASELINE`)

## Root Cause

`hooks/scripts/context-monitor.sh` lines 307–312:

```bash
local overhead=$PER_TURN_OVERHEAD
# Add system prompt baseline on first tool call of session
if [ "$CURRENT_CALLS" -eq 0 ]; then
    overhead=$((overhead + SYSTEM_PROMPT_BASELINE))
fi
NEW_TOKENS=$((NEW_TOKENS + overhead))
```

`SYSTEM_PROMPT_BASELINE=10000` was designed as a heuristic correction for
the pure-heuristic path (no transcript). But the same addition applies
regardless of whether `TRANSCRIPT_BASELINE > 0`.

## Evidence

Inspection of Claude Code JSONL transcripts confirms: `cache_read_input_tokens`
on the first assistant entry already contains the system prompt, CLAUDE.md,
and MCP tool schemas (~22K–25K tokens for this project). The `get_transcript_baseline()`
function sums:

```
input_tokens(1) + cache_read(22528) + cache_creation(24458) + output(273) ≈ 47,260
```

Adding `SYSTEM_PROMPT_BASELINE=10000` on top of a 47K transcript baseline
produces 57K — a 10K overestimate.

## Why P3 and Not Higher

The overcounting effect (~10K) partially compensates for the stale baseline
error (BUG-2145), which undercounts by 70K+ on long sessions. Fixing this
without fixing BUG-2145 would make net accuracy *worse*. The two fixes should
ship together.

Additionally, the 10K overcounting only persists until the threshold is crossed
and the state resets — it does not compound.

## Proposed Solution

Guard the `SYSTEM_PROMPT_BASELINE` addition on the absence of a transcript
baseline:

```bash
if [ "$CURRENT_CALLS" -eq 0 ] && [ "${TRANSCRIPT_BASELINE:-0}" -le 0 ]; then
    overhead=$((overhead + SYSTEM_PROMPT_BASELINE))
fi
```

This restores `SYSTEM_PROMPT_BASELINE` to its intended role as a pure-heuristic
fallback, used only when no JSONL data is available.

## Note on Hidden Token Gap

Research report `docs/research/claude-code-token-estimation-python.md` warns
about a 45K–50K "hidden token gap" from system prompts not in billable API
usage fields. For our implementation this is NOT an issue: we sum all four
`usage` fields (`input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens`) which together represent the
complete context window consumption including system prompt overhead.
The "gap" only affects implementations that read only `input_tokens`.

## Impact

- **Priority**: P3 — the ~10K overcounting partially offsets BUG-2145's 70K+ undercounting; must ship together with BUG-2145 to avoid worsening net accuracy
- **Effort**: Small — single conditional guard change in `context-monitor.sh`
- **Risk**: Low — only affects the first-call overhead calculation when a transcript baseline is present; no behavior change for pure-heuristic sessions
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-13 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-14T04:14:30 - `a6f36260-94d2-4cab-bbd5-31dc8ac6ad40.jsonl`
