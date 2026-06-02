---
id: ENH-1876
title: "Extract research-coverage-flow oracle from deep-research loops"
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
---

# ENH-1876: Extract research-coverage-flow oracle from deep-research loops

## Summary

Extract the shared 6-state FSM topology from `deep-research.yaml` and `deep-research-arxiv.yaml` into a parameterized `oracles/research-coverage.yaml`, eliminating the near-clone duplication between the two loops.

## Parent Issue

Decomposed from ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Current Behavior

`deep-research.yaml` and `deep-research-arxiv.yaml` share the same 6-state FSM topology (`init → generate_queries → search_web → evaluate_sources → score_coverage → [synthesize | plan_next → search_web]`) and identical top-level settings. The divergence spans 5 of 6 shared states:
- `search_web`: arxiv version adds `site:arxiv.org` and different citation format
- `evaluate_sources`: different scoring axis (credibility 1–5 vs. recency time-derived), different dedup key (URL vs. arxiv ID), different pruning rules
- `synthesize`: BibTeX section and different table columns for arxiv

## Expected Behavior

- `research-coverage-flow` extracted to `scripts/little_loops/loops/oracles/research-coverage.yaml` with parameterized source filtering
- Required parameters: `source_filter`, `scoring_axis`, `dedup_key`, `citation_format`, `academic_mode` (bool — gates BibTeX/academic terminology)
- `deep-research.yaml` and `deep-research-arxiv.yaml` converted to delegate the inner FSM chain to the oracle
- If full parameterization grows unwieldy (parameter surface too large), fall back to topology-only extraction with caller prompt overrides for arxiv-specific state content — decide during implementation based on parameter complexity
- All modified loops pass `ll-loop validate`

## Proposed Solution

1. Create `scripts/little_loops/loops/oracles/research-coverage.yaml` with parameters `source_filter`, `scoring_axis`, `dedup_key`, `citation_format`, `academic_mode`; `synthesize` state uses conditional branching for BibTeX vs. standard output
2. Convert `deep-research.yaml` to delegate `generate_queries → … → score_coverage` chain to the oracle with standard parameters
3. Convert `deep-research-arxiv.yaml` to delegate with arxiv-specific parameters (`source_filter: "site:arxiv.org"`, `academic_mode: true`, etc.)
4. Run `ll-loop validate` on both converted loops and the new oracle

## Integration Map

### Files to Create
- `scripts/little_loops/loops/oracles/research-coverage.yaml` — new parameterized flow oracle (check `loops/flows/` convention vs. `oracles/` — use whichever directory pattern matches existing oracles)

### Files to Modify
- `scripts/little_loops/loops/deep-research.yaml` — convert to delegate inner FSM chain to research-coverage oracle
- `scripts/little_loops/loops/deep-research-arxiv.yaml` — same conversion with arxiv-specific parameters

### Tests
- `scripts/tests/test_builtin_loops.py`:
  - Add `research-coverage` to `test_expected_loops_exist` hardcoded set
- `scripts/tests/test_deep_research.py` — **BREAKING**: update `test_required_states_exist()`, `test_coverage_state_uses_sentinel()`, `test_plan_next_loops_back_to_search_web()` for post-delegation structure
- `scripts/tests/test_deep_research_arxiv.py` — **BREAKING**: same 3 methods break under same conditions; update for post-delegation structure
- `scripts/tests/test_doc_counts.py` — add `test_research_coverage_is_runnable()` to `TestIsRunnableLoop` following `test_enumerate_and_prove_is_runnable` pattern

### Documentation
- `docs/reference/loops.md` — add `## oracles/research-coverage` section (parameters table, state machine description, invocation example); update `## deep-research` state graph if delegation changes the flat FSM topology

## Codebase Research Notes

- The divergence between the two loops spans 5 of 6 shared states — extraction is feasible but the parameter surface is larger than originally scoped
- If parameterization grows unwieldy, consider extracting only the FSM topology (stub prompt templates) and keeping arxiv-specific prompts as overrides at the caller state level

## Success Metrics

- `research-coverage-flow` eliminates near-clone state machine across 2 loops
- All modified and new loops pass `ll-loop validate`
- `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short` passes

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
