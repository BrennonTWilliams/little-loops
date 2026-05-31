---
id: ENH-1777
title: Wave 4 — Remaining Fragments, Sub-loops, and Flows
type: ENH
priority: P3
captured_at: "2026-05-29T01:01:55Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
---

# ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Summary

Complete the loop simplification initiative with the 4 lower-priority items: extract the `implement-issue-chain` sub-loop shared by two sprint loops, add queue management fragments (`queue_pop`, `queue_track`), extract the `research-coverage-flow` from two near-clone deep-research loops, and add the `diff_stall_gate` fragment.

## Current Behavior

**`implement-issue-chain`** — `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` share an explicitly noted mirrored chain: `get_passed_issues → implement_next → go_no_go → implement_issue → skip_and_continue`. The sprint variant's comment says "Mirrors auto-refine-and-implement.yaml."

**Queue management** — `autodev.yaml`, `recursive-refine.yaml`, `auto-refine-and-implement.yaml`, and `sprint-refine-and-implement.yaml` all manage issue queues via temp files with head-pop, push, and skip tracking patterns — identical operations with different file paths.

**`research-coverage-flow`** — `deep-research.yaml` and `deep-research-arxiv.yaml` are near-clones with identical state machines (`generate_queries → search_web → evaluate_sources → score_coverage → [synthesize | plan_next → search_web]`), differing only in arxiv.org constraint and recency vs credibility scoring.

**`diff_stall_gate`** — the `diff_stall` evaluator is used in 3 loops (`incremental-refactor.yaml`, `harness-multi-item.yaml`, `harness-single-shot.yaml`) with duplicated configuration.

## Expected Behavior

- `implement-issue-chain` extracted as a shared sub-loop, eliminating the mirrored duplication between the two sprint loops
- `queue_pop` and `queue_track` fragments in `loops/lib/common.yaml` abstracting temp-file queue operations with context variables for queue path
- `research-coverage-flow` extracted with a `source_filter` parameter so both deep-research loops compose from the same flow
- `diff_stall_gate` fragment in `loops/lib/common.yaml` standardizing the diff_stall evaluator configuration

## Motivation

These are the remaining lower-priority deduplication opportunities. While individually smaller than Waves 1-3 items, together they eliminate the last major duplication clusters and complete the loop library simplification.

## Proposed Solution

1. Extract `implement-issue-chain` sub-loop to `loops/oracles/implement-issue-chain.yaml`
2. Add `queue_pop` and `queue_track` fragments to `loops/lib/common.yaml`
3. Extract `research-coverage-flow` with parameterized source filtering
4. Add `diff_stall_gate` fragment to `loops/lib/common.yaml`
5. Convert all callers for each item
6. Run `ll-loop validate` on all modified loops
7. Run `python -m pytest scripts/tests/ -v --tb=short`

## API/Interface

N/A — No public API changes; this is a loop YAML refactoring that changes internal FSM composition without altering CLI interfaces or Python APIs.

## Integration Map

### Files to Modify
- `loops/oracles/implement-issue-chain.yaml` — new sub-loop
- `loops/auto-refine-and-implement.yaml` — convert to delegate to sub-loop
- `loops/sprint-refine-and-implement.yaml` — convert to delegate to sub-loop
- `loops/lib/common.yaml` — add `queue_pop`, `queue_track`, `diff_stall_gate` fragments
- `loops/autodev.yaml` — convert queue operations
- `loops/recursive-refine.yaml` — convert queue operations
- `loops/incremental-refactor.yaml` — convert diff_stall state
- `loops/harness-multi-item.yaml` — convert diff_stall state
- `loops/harness-single-shot.yaml` — convert diff_stall state
- `loops/oracles/research-coverage.yaml` — new flow
- `loops/deep-research.yaml` — convert to use flow
- `loops/deep-research-arxiv.yaml` — convert to use flow

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` CLI

### Similar Patterns
- Any future queue-based issue processing loop should use `queue_pop`/`queue_track`

### Tests
- `scripts/tests/` — regression suite

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract `implement-issue-chain` sub-loop
2. Add `queue_pop` and `queue_track` fragments to `loops/lib/common.yaml`
3. Extract `research-coverage-flow` with source_filter parameter
4. Add `diff_stall_gate` fragment to `loops/lib/common.yaml`
5. Convert all callers for each new shared component
6. Run `ll-loop validate` on all modified loops
7. Run `python -m pytest scripts/tests/ -v --tb=short` to verify no regressions

## Success Metrics

- `implement-issue-chain` eliminates 5 duplicated states across 2 sprint loops
- Queue fragments eliminate duplicated temp-file operations across 4 loops
- `research-coverage-flow` eliminates a near-clone state machine across 2 loops
- `diff_stall_gate` standardizes 3 loops
- All modified loops pass `ll-loop validate`
- Test suite passes with no regressions
- All 11 items from the audit plan are complete

## Scope Boundaries

- Only the 4 listed items; no new patterns introduced
- `research-coverage-flow` should be a parameterized flow, not a sub-loop (the two loops differ only in source filter and scoring weights)
- This wave completes the epic; after this, all 57 loops should compose from the enriched shared library

## Impact

- **Priority**: P3 — Lower priority than Waves 1-3; items are smaller and affect fewer loops
- **Effort**: Medium — 4 items across ~12 loops; `research-coverage-flow` is the most complex
- **Risk**: Low — Smaller, more isolated changes than earlier waves; well-understood patterns
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop composition and flow definitions |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T01:16:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5513c747-2bdb-461c-ade9-635f62428078.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Status

**Open** | Created: 2026-05-28 | Priority: P3
