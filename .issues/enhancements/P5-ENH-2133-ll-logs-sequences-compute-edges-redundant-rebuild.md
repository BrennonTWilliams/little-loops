---
id: ENH-2133
type: ENH
priority: P5
status: done
title: "ll-logs sequences _compute_edges rebuilds transition counter per n-gram (O(K\xB7\
  N\xB2))"
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T01:52:17Z'
completed_at: '2026-06-19T19:56:58Z'
parent: EPIC-1918
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2133: ll-logs sequences _compute_edges rebuilds transition counter per n-gram (O(K·N²))

## Summary

`_compute_edges(ngram, counter)` (lines 464–489 of `cli/logs.py`) is called once per `ChainResult` by `_build_chain_results`. Each call iterates all items in `counter` to rebuild `all_transitions` and `out_degree` from scratch. With K result chains and a counter of size N, this is O(K·N²) work — the full counter is scanned K times.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete signature and diff anchors:_

**New `_compute_edges` signature** (`logs.py:464`):
```python
def _compute_edges(
    ngram: tuple[str, ...],
    all_transitions: Counter,
    out_degree: Counter,
) -> list[Edge]:
```

**In `_build_chain_results` (`logs.py:436`)** — hoist the Phase 1 block before the `most_common()` loop:
```python
# Compute once before loop (moved from _compute_edges)
all_transitions: Counter = Counter()
out_degree: Counter = Counter()
for ngram_key, count in counter.items():
    for i in range(len(ngram_key) - 1):
        pair = (ngram_key[i], ngram_key[i + 1])
        all_transitions[pair] += count
        out_degree[ngram_key[i]] += count

for ngram, count in counter.most_common():
    if count < min_count:
        continue
    edges = _compute_edges(ngram, all_transitions, out_degree)  # updated call
    results.append(ChainResult(chain=list(ngram), count=count, edges=edges))
```

**Verification**: `python -m pytest scripts/tests/test_ll_logs.py::TestSequences -v` covers output shape end-to-end.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_compute_edges`, `_build_chain_results` (~lines 421–474)

### Dependent Files (Callers/Importers)
- N/A — both functions are module-internal to `cli/logs.py`

### Similar Patterns
- `scripts/little_loops/fsm/concurrency.py:201` — `find_conflicting_lock()` normalizes a list once before a comparison loop; comment explicitly names the O(n*m) motivation — same shape as this refactor
- `scripts/little_loops/workflow_sequence/analysis.py:445` — `_compute_boundaries()` pre-computes entity sets once per message before the sliding-window loop; documents motivation inline

### Tests
- Existing tests cover output shape; no new tests needed unless the refactor changes behavior

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact line ranges**: `_build_chain_results` → lines 436–461; `_compute_edges` → lines 464–489 (issue text says "~421–474"; Verification Note says "line 449" — both are slightly stale)
- **Single call site confirmed**: `_compute_edges` is called only at `logs.py:455` inside `_build_chain_results`; no other callers anywhere in the project
- **Code block to extract**: lines 472–479 in `_compute_edges` (the Phase 1 counter rebuild loop) move verbatim into `_build_chain_results` before line 452 (the `counter.most_common()` loop)
- **Test file**: `scripts/tests/test_ll_logs.py` — integration-level sequences tests at lines 719–1036 (`test_sequences_basic_ngram_counting` through `test_sequences_all_mode`); no direct unit tests exist for `_compute_edges` or `_build_chain_results` — the integration tests exercise the full pipeline through `_cmd_sequences` and will catch any regression in edge frequency output

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

2026-06-18 (ACCURATE): `_compute_edges` at line 464 still rebuilds `all_transitions` and `out_degree` counters from scratch on every call (lines 458-464). `_build_chain_results` calls it once per `ChainResult` in the results loop (line 440). O(K·N) redundant work confirmed unfixed.

## Status

**Open** | Created: 2026-06-14 | Priority: P5

## Session Log
- `/ll:ready-issue` - 2026-06-19T19:54:44 - `848b6054-17db-4061-b7d1-93252978f52b.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `dc4fe116-1bee-4f2a-a12e-b0d03db814b0.jsonl`
- `/ll:refine-issue` - 2026-06-19T19:39:51 - `ec7f419c-b39c-4790-accf-cf663d37cb5c.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:55 - `d9bff7da-ceab-4140-99fa-ea076f1863f3.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
