---
id: BUG-2145
type: BUG
title: 'context-monitor: transcript baseline read once and never refreshed across
  turns'
priority: P2
status: done
discovered_date: 2026-06-13
completed_at: 2026-06-14 05:50:18+00:00
discovered_by: research-review
labels:
- context-monitor
- accuracy
- jsonl
parent: EPIC-2149
relates_to:
- ENH-810
- ENH-1376
- BUG-809
confidence_score: 94
outcome_confidence: 78
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 18
score_change_surface: 23
---

# BUG-2145: context-monitor transcript baseline never refreshed across turns

## Summary

`context-monitor.sh` reads the JSONL transcript baseline once (when
`transcript_baseline_tokens` in state is 0) and caches it for the entire
session. In long sessions where context grows from ~47K to 120K+, the
estimate diverges from reality by 70K+ tokens because the stale baseline
combined with the 800-token/turn heuristic cannot keep up with actual
accumulation.

## Current Behavior

`context-monitor.sh` reads the JSONL transcript baseline once per session (when `transcript_baseline_tokens` in state is 0), caches it, and reuses it for all subsequent turns. The stale baseline combined with an 800-token/turn heuristic produces estimates that diverge from real usage over time. By turn 100, the monitor may report ~54% context usage when actual JSONL usage is ~78%, causing handoff to fire late or not at all.

## Expected Behavior

The transcript baseline is refreshed on each new turn so that estimated context percentage tracks actual JSONL usage within a small margin throughout the session. Context handoff fires reliably when real usage crosses the configured threshold (default 80%).

## Steps to Reproduce

1. Start a Claude Code session in a project with `context_monitor.enabled: true`
2. Run the session for 40+ turns (e.g., use `ll-auto` on a batch of issues)
3. After each turn, compare `estimated_tokens` in `.ll/ll-context-state.json` against `cache_read_input_tokens` in the latest `assistant` entry of the JSONL transcript
4. Observe: estimated tokens grows at ~800/turn while `cache_read_input_tokens` grows much faster
5. At ~100 turns: estimated shows ~54% of 200K window; JSONL shows ~78%

## Evidence

Direct inspection of Claude Code JSONL transcripts in this project:

| Session length | First `cache_read_input_tokens` | Last `cache_read_input_tokens` | Delta |
|---|---|---|---|
| 92 entries (~45 turns) | 22,574 | 119,285 | +96,711 |
| 216 entries (~100 turns) | 20,637 | 155,933 | +135,296 |
| 76 entries (~38 turns) | 21,814 | 105,651 | +83,837 |

The `cache_read_input_tokens` field in `assistant` JSONL entries is the
authoritative, growing measure of accumulated context. At 100 turns the real
context is at ~78% of the 200K window; the stale-baseline estimate (initial
~47K + 100 × 800) shows only ~54%.

## Root Cause

`hooks/scripts/context-monitor.sh` lines 281–284:

```bash
TRANSCRIPT_BASELINE="${CACHED_BASELINE:-0}"
if [ "${USE_TRANSCRIPT_BASELINE}" = "true" ] && [ -n "$TRANSCRIPT_PATH" ] && \
   { [ "${TRANSCRIPT_BASELINE}" -le 0 ] 2>/dev/null || [ -z "$TRANSCRIPT_BASELINE" ]; }; then
    TRANSCRIPT_BASELINE=$(get_transcript_baseline "$TRANSCRIPT_PATH")
fi
```

The guard `[ "${TRANSCRIPT_BASELINE}" -le 0 ]` means the file is only read
once (when the cached value is 0). The cached value is then written back to
state (line 335) and persists for the rest of the session. Subsequent turns
use the stale initial reading.

## JSONL Entry Structure (verified)

Each API call produces 2–3 duplicate `assistant` entries in the JSONL (one
per content block: `thinking`, `text`, `tool_use`). All duplicates carry
identical usage values. `get_transcript_baseline()` uses `| last` which
correctly picks one duplicate from the most recent turn — but only if the
transcript is re-read.

The correct total context window usage from the last JSONL entry:
```
input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens
```
This naturally captures the accumulated system prompt, CLAUDE.md, MCP tool
schemas, and full conversation history — no separate overhead constant needed.

## Proposed Solution

Re-read the transcript on the first PostToolUse call of each new turn rather
than once per session. A turn boundary can be detected cheaply by comparing
the JSONL file's mtime against a `last_baseline_mtime` value stored in
state — a newer mtime means a new assistant entry has been written (new turn),
so the baseline should be refreshed.

Alternative: unconditionally re-read `tail -50` on every PostToolUse. The
`get_transcript_baseline()` function already uses `tail -50` for performance;
the extra JSONL read adds ~2ms and is within the 5s hook timeout budget.


## Implementation Steps

1. Remove the stale-baseline guard in `context-monitor.sh` (`get_transcript_baseline` call block, lines 281–284) that prevents re-reading after the first turn
2. Add mtime-based change detection: store `last_baseline_mtime` in state; compare against the JSONL file's current mtime on each PostToolUse call — re-read only when mtime has advanced (new turn written)
3. Update the state-write block (around line 335) to persist `last_baseline_mtime` alongside `TRANSCRIPT_BASELINE`
4. Add a regression test simulating a multi-turn session to verify estimated tokens track within 5% of JSONL actual `cache_read_input_tokens`
5. Verify hook execution stays within the 5s timeout budget (~2ms per `tail -50` JSONL read)

## Impact

- Context handoff fires late (or not at all) on long sessions — the monitor
  may report 54% when the real usage is 78%, never crossing the 80% threshold.
- `ll-ctx-stats` fallback reporting is also affected (reads
  `estimated_tokens` from `ll-context-state.json`).
- Particularly affects `ll-auto` and `ll-parallel` runs where sessions grow
  large before a handoff is triggered.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — remove the stale-baseline guard; add mtime-based refresh logic and `last_baseline_mtime` state field

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers `context-monitor.sh` as a PostToolUse hook; no changes needed
- `.ll/ll-context-state.json` — runtime state file that caches `transcript_baseline_tokens`; will gain a new `last_baseline_mtime` field

### Similar Patterns
- `hooks/scripts/context-monitor.sh` lines 325–340 — existing state-persistence pattern to follow for the new mtime field

### Tests
- `scripts/tests/` — add test for baseline refresh across simulated turns (mock JSONL file, advance mtime, verify re-read occurs)

### Documentation
- N/A — no user-facing documentation references context-monitor accuracy internals

### Configuration
- N/A — no config changes needed; hook is already registered

## Status

**Open** | Created: 2026-06-13 | Priority: P2


## Resolution

Replaced the one-shot guard (`TRANSCRIPT_BASELINE -le 0`) in `hooks/scripts/context-monitor.sh` with mtime-based change detection. The JSONL transcript is now re-read on the first `PostToolUse` call of each new turn (detected by comparing the file's mtime against a `last_baseline_mtime` value stored in state). Subsequent calls within the same turn use the cached baseline. The new `last_baseline_mtime` field is persisted alongside `transcript_baseline_tokens` in `.ll/ll-context-state.json`.

Added regression test `test_transcript_baseline_refreshed_on_new_turn` in `scripts/tests/test_hooks_integration.py` that simulates a multi-turn session and verifies the baseline is cached mid-turn and refreshed when mtime advances.

## Session Log
- `/ll:manage-issue` - 2026-06-14T05:50:18Z - BUG fix implemented and tested
- `/ll:ready-issue` - 2026-06-14T05:44:27 - `f6374f01-4a21-402b-91b9-10ec7638da4d.jsonl`
- `/ll:format-issue` - 2026-06-14T04:14:38 - `14a1adc0-a69d-4b4c-b62c-4bcfd24495c3.jsonl`
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `8286dbf0-96e5-4773-bc5d-91477e28b4f1.jsonl`
