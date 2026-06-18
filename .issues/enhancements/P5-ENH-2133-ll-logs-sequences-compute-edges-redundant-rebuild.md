---
id: ENH-2133
type: ENH
priority: P5
status: open
title: ll-logs sequences _compute_edges rebuilds transition counter per n-gram (O(K·N²))
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
parent: EPIC-1918
---

# ENH-2133: ll-logs sequences _compute_edges rebuilds transition counter per n-gram (O(K·N²))

## Summary

`_compute_edges(ngram, counter)` (lines 449–474 of `cli/logs.py`) is called once per `ChainResult` by `_build_chain_results`. Each call iterates all items in `counter` to rebuild `all_transitions` and `out_degree` from scratch. With K result chains and a counter of size N, this is O(K·N²) work — the full counter is scanned K times.

At current ll usage scale (tens of sessions, hundreds of invocations) this is imperceptible. It becomes noticeable as the corpus grows.

## Current Behavior

`_compute_edges` is called once per `ChainResult` in `_build_chain_results`. Each call iterates all N items in `counter` to rebuild `all_transitions` and `out_degree` from scratch — O(N) work per call. With K result chains, total work is O(K·N) for the counter scans alone, making the sequences pipeline scale poorly as session corpus size grows.

## Expected Behavior

`all_transitions` and `out_degree` are computed once in `_build_chain_results` before the results loop (single O(N) pass), then passed into `_compute_edges` as pre-built arguments. The redundant per-call rebuilds are eliminated, reducing total counter work from O(K·N) to O(N).

## Implementation Steps

1. Move the `all_transitions` and `out_degree` counter construction out of `_compute_edges` into `_build_chain_results`, computed once before the results loop.
2. Change `_compute_edges` signature to accept pre-computed `all_transitions: Counter` and `out_degree: Counter` instead of rebuilding them from `counter`.
3. Update the single call site in `_build_chain_results`.
4. Existing tests cover the output shape; no new tests needed unless the refactor changes behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_compute_edges`, `_build_chain_results` (~lines 421–474)

### Dependent Files (Callers/Importers)
- N/A — both functions are module-internal to `cli/logs.py`

### Similar Patterns
- N/A

### Tests
- Existing tests cover output shape; no new tests needed unless the refactor changes behavior

### Documentation
- N/A

### Configuration
- N/A

## Scope Boundaries

- Only `_compute_edges` and `_build_chain_results` in `cli/logs.py`
- No algorithm changes — same edge-counting logic, restructured for efficiency
- No changes to `ll-logs sequences` output format or CLI interface
- No new tests required (existing coverage sufficient for this refactor)

## Impact

- **Priority**: P5 — Low priority performance optimization; imperceptible at current usage scale
- **Effort**: Small — Targeted internal function signature change with a single call-site update; no new patterns
- **Risk**: Low — Internal functions not exposed externally; existing tests cover output shape
- **Breaking Change**: No

## Labels

`performance`, `refactor`, `ll-logs`

## Verification Notes

2026-06-18 (ACCURATE): `_compute_edges` at line 449 still rebuilds `all_transitions` and `out_degree` counters from scratch on every call (lines 458-464). `_build_chain_results` calls it once per `ChainResult` in the results loop (line 440). O(K·N) redundant work confirmed unfixed.

## Status

**Open** | Created: 2026-06-14 | Priority: P5

## Session Log
- `/ll:format-issue` - 2026-06-14T01:58:55 - `d9bff7da-ceab-4140-99fa-ea076f1863f3.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
