---
id: ENH-2147
type: ENH
title: "ll-ctx-stats: compute cache hit rate from JSONL cache_read vs cache_creation tokens"
priority: P3
status: open
discovered_date: 2026-06-13
discovered_by: research-review
labels:
  - ctx-stats
  - cache
  - analytics
parent: EPIC-1626
relates_to:
  - FEAT-1624
---

# ENH-2147: ll-ctx-stats — proper cache hit rate from JSONL usage fields

## Summary

`ll-ctx-stats` currently displays a binary "N hits | X saved" cache line
based on a `cache_hit` flag in `tool_events`. It cannot compute the proper
cache hit rate because the denominator (total cache accesses = reads +
writes + uncached) is not tracked. The JSONL transcript already contains all
the data needed to compute an accurate rate.

## Current Behavior

`ll-ctx-stats` displays a binary "N hits | X saved" cache line derived from a
`cache_hit` boolean flag in `tool_events`. The denominator for a real hit-rate
percentage (total cache accesses = reads + writes + uncached) is not tracked,
so no percentage is shown.

## Expected Behavior

`ll-ctx-stats` computes and displays an accurate cache hit rate sourced from
the JSONL transcript's `message.usage` fields, added to both `_render()` text
output and `--json`:

```
Cache hit rate: 93%  (cache_read=61,559 | cache_write=3,689 | uncached=1)
```

## Motivation

This enhancement:
- Replaces a misleading binary flag with an accurate, actionable percentage metric
- Enables detection of cache-busting configurations — e.g., MCP tool order
  changes or CLAUDE.md edits that bust the prefix hash (turn-1 hit rate drops
  from ~94% to ~48% when the cache is cold)
- Uses data already present in the JSONL transcript; no new data collection needed
- Healthy systems show 95–98% hit rate on system prompts and 70–90% on
  conversation messages — surfacing this makes misconfiguration immediately visible

## Standardized Formula

The ecosystem-standard hit rate formula (from
`docs/research/claude-code-token-estimation-python.md`):

```python
hit_rate = cache_read / (cache_read + cache_write + uncached) * 100
```

From Claude Code JSONL assistant entries (`message.usage`):
- `cache_read_input_tokens` — tokens served from cache (read hit)
- `cache_creation_input_tokens` — tokens written to cache (write / miss)
- `input_tokens` — uncached tokens (not in any cache tier)

A healthy system should show 95–98% hit rate on system prompts and 70–90%
on conversation messages (per the research report).

## Evidence from JSONL Inspection

Session sample (latest transcript, last 5 turns):

| Turn | cache_read | cache_create | uncached | hit_rate |
|---|---|---|---|---|
| 1 | 22,528 | 24,458 | 5 | 48% |
| 3 | 46,986 | 333 | 1 | 99% |
| 4 | 47,319 | 4,894 | 1 | 91% |
| 5 | 52,213 | 4,911 | 1 | 91% |
| last | 61,559 | 3,689 | 1 | 94% |

Turn 1 always shows low hit rate (cache warming); subsequent turns should
show 90%+ for a well-configured project. This signal is useful for detecting
cache-busting configurations (e.g., changing MCP tool order, CLAUDE.md edits
that bust the prefix hash).

## Proposed Solution

**`scripts/little_loops/cli/ctx_stats.py`**

Add a `_compute_cache_rate_from_jsonl()` function that:
1. Reads the most recent session JSONL (from `transcript_path` in
   `.ll/ll-context-state.json` or by scanning `~/.claude/projects/<dir>/`)
2. Extracts `cache_read_input_tokens`, `cache_creation_input_tokens`,
   `input_tokens` from each unique assistant entry (deduplicated by usage
   fingerprint to avoid the 2–3 duplicate entries per API call)
3. Computes session-aggregate hit rate

Add to `_render()` and `--json` output:
```
Cache hit rate: 93%  (cache_read=61,559 | cache_write=3,689 | uncached=1)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` — add `_compute_cache_rate_from_jsonl()`, update `_render()` and JSON output

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "ctx_stats\|CtxStats" scripts/`

### Similar Patterns
- TBD — check existing JSONL parsing utilities: `grep -r "cache_read_input_tokens\|jsonl" scripts/little_loops/`

### Tests
- TBD — identify or create test file for `ctx_stats.py` covering JSONL extraction and rate computation

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_compute_cache_rate_from_jsonl()` to `ctx_stats.py` — locate the most recent session JSONL via `transcript_path` in `.ll/ll-context-state.json` or by scanning `~/.claude/projects/<dir>/`
2. Extract and deduplicate `cache_read_input_tokens`, `cache_creation_input_tokens`, `input_tokens` from assistant entries (fingerprint-based dedup to avoid 2–3 duplicate entries per API call)
3. Compute session-aggregate hit rate: `cache_read / (cache_read + cache_write + uncached) * 100`
4. Update `_render()` and `--json` output to include the hit-rate line
5. Add tests for the extraction and computation logic

## Scope Boundaries

- **In scope**: Session-aggregate cache hit rate in `_render()` and `--json`; JSONL-based computation
- **Out of scope**: Changing how `tool_events.cache_hit` is populated (existing boolean flag); per-turn hit rate history (future EPIC-1626 enhancement); alerting on hit rate drops (separate monitoring concern)

## Impact

- **Priority**: P3 — useful diagnostic signal; not blocking core functionality
- **Effort**: Small — single function addition to existing `ctx_stats.py`; JSONL parsing patterns already exist in the codebase
- **Risk**: Low — additive change; existing `_render()` and `--json` output is extended, not replaced
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-13 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-14T04:14:53 - `e2e0a70e-86e6-49f1-872f-c22e27207788.jsonl`
