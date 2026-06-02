---
id: ENH-1876
title: Extract research-coverage-flow oracle from deep-research loops
type: ENH
priority: P3
parent: ENH-1777
captured_at: '2026-06-02T00:00:00Z'
completed_at: '2026-06-02T08:08:49Z'
discovered_date: 2026-06-02
discovered_by: issue-size-review
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
status: done
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
- `scripts/little_loops/loops/README.md` — add row to `## Oracle Sub-loops` table for `research-coverage` [_Wiring pass added by `/ll:wire-issue`:_]
- `README.md` — update `**67 FSM loops**` → `**68 FSM loops**`; doc-count test sweeps this file and will fail if stale [_Wiring pass added by `/ll:wire-issue`:_]
- `CONTRIBUTING.md` — update `(60 YAML files)` → `(61 YAML files)` in the `loops/` directory line; same doc-count sweep [_Wiring pass added by `/ll:wire-issue`:_]

### Tests
- `scripts/tests/test_builtin_loops.py`:
  - Add `research-coverage` to `test_expected_loops_exist` hardcoded set
- `scripts/tests/test_deep_research.py` — **BREAKING**: update `test_required_states_exist()`, `test_coverage_state_uses_sentinel()`, `test_plan_next_loops_back_to_search_web()` for post-delegation structure
  - **Also BREAKING** (not initially listed): `TestDeepResearchYaml.test_score_coverage_has_on_error()` and `TestDeepResearchEvaluators.test_coverage_sentinel_matches()` — both reach into `states["score_coverage"]` which moves into the oracle [_Wiring pass added by `/ll:wire-issue`:_]
  - **New tests to write**: `test_run_research_delegates_to_oracle()` asserting `state.get("loop") == "oracles/research-coverage"`; `test_run_research_with_bindings_present()` asserting `with:` keys (`source_filter`, `academic_mode`) — follow `test_run_gen_eval_delegates_to_generator_evaluator` pattern at line 2782+ of `test_builtin_loops.py` [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_deep_research_arxiv.py` — **BREAKING**: same 3 methods break under same conditions; update for post-delegation structure
  - **Also BREAKING**: same `test_score_coverage_has_on_error()` and `test_coverage_sentinel_matches()` as above [_Wiring pass added by `/ll:wire-issue`:_]
  - **New tests to write**: same delegation + binding tests as `test_deep_research.py`, but with arxiv-specific `with:` values (`source_filter: "site:arxiv.org"`, `academic_mode: true`) [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_doc_counts.py` — add `test_research_coverage_is_runnable()` to `TestIsRunnableLoop` following `test_enumerate_and_prove_is_runnable` pattern

### Documentation
- `docs/reference/loops.md` — add `## oracles/research-coverage` section (parameters table, state machine description, invocation example); update `## deep-research` state graph if delegation changes the flat FSM topology
- `docs/guides/LOOPS_GUIDE.md` — review and update the `deep-research-arxiv` row in the `### Research & Knowledge Loops` table if the observable mechanics description changes after delegation [_Wiring pass added by `/ll:wire-issue`:_]

### Similar Patterns (Oracle Delegation)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `implement_chain` state uses `loop: oracles/implement-issue-chain` + `with: {caller_prefix: ...}`; direct model for the caller delegation state structure
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — `prove` state uses `loop: oracles/enumerate-and-prove` with `${captured.*}` interpolation in `with:` values
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — oracle with `parameters:` block, `on_handoff: spawn`, `import: [lib/common.yaml]`; closest structural analog (multiple required/optional params, `context:` supplies defaults)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — oracle that accepts full prompt strings as parameters (`generate_prompt`, `rubric`); model for the fallback strategy if individual flag parameters grow unwieldy
- `docs/reference/loops.md` line 191 — `## oracles/generator-evaluator` section is the exact documentation template to follow (parameters table, Invocation example, Internal state machine diagram, Fragment dependency)

## Codebase Research Notes

### State-by-State Divergence Inventory

| State | Divergence Level | Key Differences |
|-------|-----------------|-----------------|
| `init` | identical | Same 4 `touch` commands, same `capture: run_dir` |
| `generate_queries` | minor | Arxiv adds academic-terminology paragraph; opening line differs |
| `search_web` | **major** | Arxiv: `site:arxiv.org` constraint, arxiv ID extraction (`YYMM.NNNNN`), different citation format |
| `evaluate_sources` | **major** | Arxiv: recency axis (time-bracket table) vs credibility axis (1–5); dedup by arxiv ID vs URL; different pruning rules |
| `score_coverage` | identical | Same prompt, same 1–5 rubric, same `COVERAGE_SUFFICIENT` sentinel, same routing |
| `plan_next` | minor | Item 3 phrasing differs; arxiv adds item 4 targeting ablation studies |
| `synthesize` | **major** | Arxiv: different table columns, BibTeX `@misc{}` section, quadruple-backtick fence, different `**Generated by**` header, paper-count dedup note |
| `done` | minor | Closing message text and BibTeX copy note differ |

### Parameter Surface Analysis

The proposed 5-parameter contract (`source_filter`, `scoring_axis`, `dedup_key`, `citation_format`, `academic_mode`) covers the core divergences but note:
- `evaluate_sources` in arxiv uses a **time-bracket table** (≤6m=5, ≤1yr=4, ≤2yr=3, ≤5yr=2, >5yr=1) — `scoring_axis: "recency"` alone won't encode the rubric; either pass the full scoring rubric text as a parameter or use `academic_mode: bool` to gate a full prompt variant
- `synthesize` differences span table columns, fence style, BibTeX section, dedup-note text, and `**Generated by**` tag — `academic_mode` gating a complete prompt override is more maintainable than 4 separate parameters
- `generator-evaluator.yaml` passes full prompt strings as parameters (`generate_prompt: string, required: true`) — this is the established fallback if discrete flags grow unwieldy

### Oracle Delegation Pattern (Concrete Mechanics)

Oracle top-level must declare `on_handoff: spawn` and a `parameters:` block; `context:` supplies defaults for optional parameters:
```yaml
name: research-coverage
on_handoff: spawn
parameters:
  source_filter:
    type: string
    required: false
    description: "Site constraint appended to every search query (e.g. 'site:arxiv.org'); empty = no constraint"
  academic_mode:
    type: boolean
    required: false
    description: "Gates BibTeX section, recency scoring axis, and arxiv ID dedup in synthesize"
context:
  source_filter: ""
  academic_mode: false
import:
  - lib/common.yaml
```

Caller state in `deep-research.yaml` (after conversion):
```yaml
run_research:
  loop: oracles/research-coverage
  with:
    source_filter: ""
    academic_mode: false
  on_success: done
  on_failure: failed
  on_error: failed
```

`_validate_with_bindings()` in `scripts/little_loops/fsm/validation.py` validates that every `required: true` parameter is bound in `with:`, and that no unknown keys are passed — parameter contract is enforced at `ll-loop validate` time, not runtime.

### Test Structure After Delegation

The 3 breaking tests in each test file move or transform as follows:
- `test_required_states_exist()`: delegated states won't be in the parent's `states` dict; replace with `test_run_research_delegates_to_oracle` asserting `state.get("loop") == "oracles/research-coverage"`
- `test_coverage_state_uses_sentinel()`: `score_coverage` moves into the oracle; migrate to `TestResearchCoverageOracle.test_coverage_state_uses_sentinel` in `test_builtin_loops.py`
- `test_plan_next_loops_back_to_search_web()`: `plan_next` moves into the oracle; migrate similarly

New `TestResearchCoverageOracle` class follows `TestEnumerateAndProveOracle` pattern at line 5178 of `test_builtin_loops.py`:
- `test_required_top_level_fields` — checks `name == "research-coverage"`, `initial`, `states` is dict
- `test_has_parameters_block` — checks `source_filter`, `academic_mode` present with correct `required` flags
- `test_required_states_exist` — checks all states in the oracle (at minimum the 6 shared states)
- `test_coverage_state_uses_sentinel` — migrated from `test_deep_research.py`
- `test_plan_next_loops_back_to_search_web` — migrated from `test_deep_research.py`
- `test_has_on_handoff_spawn` — checks `data.get("on_handoff") == "spawn"`

`test_research_coverage_is_runnable` in `test_doc_counts.py` follows `test_enumerate_and_prove_is_runnable` at line 151 (same `_Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "oracles" / "research-coverage.yaml"` path pattern).

## Implementation Steps

1. **Read both source loops in full** — `scripts/little_loops/loops/deep-research.yaml` and `deep-research-arxiv.yaml` — to extract verbatim state content for transplanting into the oracle
2. **Create `oracles/research-coverage.yaml`** — declare `parameters:` block (`source_filter`, `academic_mode`, and any additional params decided per parameter surface analysis above); set `on_handoff: spawn`; set `import: [lib/common.yaml]`; verify with `ll-loop validate scripts/little_loops/loops/oracles/research-coverage.yaml`
3. **Convert `deep-research.yaml`** — replace `generate_queries → … → score_coverage` chain with a single delegation state (`run_research` or similar) via `loop: oracles/research-coverage` with standard non-arxiv `with:` values; keep or adjust `init`, `synthesize`, `done` at parent level depending on whether `academic_mode` handles the full `synthesize` difference
4. **Convert `deep-research-arxiv.yaml`** — same structure, with arxiv-specific `with:` values (`source_filter: "site:arxiv.org"`, `academic_mode: true`); verify both converted loops with `ll-loop validate`
5. **Update tests** — `test_deep_research.py` and `test_deep_research_arxiv.py`: rewrite the 3 originally-listed breaking methods **plus** `test_score_coverage_has_on_error` and `test_coverage_sentinel_matches` for post-delegation structure; add `test_run_research_delegates_to_oracle` and `test_run_research_with_bindings_present` to each file; `test_builtin_loops.py`: add `TestResearchCoverageOracle` class following `TestEnumerateAndProveOracle` at line 5178; `test_doc_counts.py`: add `test_research_coverage_is_runnable` following `test_enumerate_and_prove_is_runnable` at line 151
6. **Update documentation** — `docs/reference/loops.md`: add `## oracles/research-coverage` section following the `## oracles/generator-evaluator` template at line 191 (parameters table, invocation YAML, state machine diagram); update `## deep-research` state graph to reflect delegation; `scripts/little_loops/loops/README.md`: add row to `## Oracle Sub-loops` table; `docs/guides/LOOPS_GUIDE.md`: review `deep-research-arxiv` description row; `README.md`: update `**67 FSM loops**` → `**68 FSM loops**`; `CONTRIBUTING.md`: update `(60 YAML files)` → `(61 YAML files)`
7. **Run full test suite** — `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short`

## Success Metrics

- `research-coverage-flow` eliminates near-clone state machine across 2 loops
- All modified and new loops pass `ll-loop validate`
- `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short` passes

## Scope Boundaries

- Do not add new query strategies or search features not already present in either source loop
- Do not restructure the caller loops beyond the delegation pattern (`init`, `synthesize`, `done` remain at caller level unless `academic_mode` handles the full `synthesize` divergence)
- Do not change the observable behavior of `deep-research` or `deep-research-arxiv` from the user's perspective
- Updating `test_deep_research.py` and `test_deep_research_arxiv.py` for post-delegation structure is in scope; refactoring unrelated test classes in those files is NOT

## Impact

- **Priority**: P3 - Eliminates near-clone duplication between two loops; low urgency but clear technical-debt cost
- **Effort**: Medium - Create new oracle YAML + convert 2 loops + update 4 test files + update docs/README counts
- **Risk**: Low - Both source loops have test coverage; observable behavior is unchanged; no external API surface
- **Breaking Change**: No (behavior preserved; tests must be updated for structural changes to `states` dict)

## Labels

`refactoring`, `loops`, `oracle`, `code-quality`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T07:52:17 - `c4004071-bec5-455c-9bcd-d8689a0de0b3.jsonl`
- `/ll:wire-issue` - 2026-06-02T07:47:24 - `d97b4ed4-f816-4f93-b28f-1dc12e02f532.jsonl`
- `/ll:refine-issue` - 2026-06-02T07:42:06 - `50716fad-3e85-463c-ad4d-43dfa41b5580.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `a80d0fbb-e5fc-4dc0-9ca9-078c452db7c4.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
