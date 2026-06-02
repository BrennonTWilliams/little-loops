---
id: ENH-1777
title: "Wave 4 \u2014 Remaining Fragments, Sub-loops, and Flows"
type: ENH
priority: P3
captured_at: '2026-05-29T01:01:55Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
depends_on:
- ENH-1775
- ENH-1776
confidence_score: 98
outcome_confidence: 63
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
status: done
---

# ENH-1777: Wave 4 — Remaining Fragments, Sub-loops, and Flows

## Summary

Complete the loop simplification initiative with the 4 lower-priority items: extract the `implement-issue-chain` sub-loop shared by two sprint loops, add queue management fragments (`queue_pop`, `queue_track`), extract the `research-coverage-flow` from two near-clone deep-research loops, and add the `diff_stall_gate` fragment.

## Current Behavior

**`implement-issue-chain`** — `scripts/little_loops/loops/auto-refine-and-implement.yaml` and `scripts/little_loops/loops/sprint-refine-and-implement.yaml` share an explicitly noted mirrored chain: `get_passed_issues → implement_next → go_no_go → implement_issue → skip_and_continue`. Both files carry a comment: _"NOTE: … are mirrored in sprint-refine-and-implement.yaml. Keep both files in sync when editing."_ The five states are structurally identical; only the queue-file prefix differs (`auto-refine-and-implement-*` vs `sprint-refine-and-implement-*`). Both use `.loops/tmp/` paths (not `${context.run_dir}/`), which is an MR-3 warning — cross-run sharing of `recursive-refine-passed.txt` is intentional, so `shared_state_ok: true` will be needed on the extracted sub-loop (or the parent callers).

**Queue management** — `autodev.yaml` and `recursive-refine.yaml` use `${context.run_dir}/` for their queue files (correct). `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` use `.loops/tmp/` (MR-3 warning, suppressed via `shared_state_ok: true`). All four share the same atomic head-pop shell idiom: `head -1 <queue>`, `tail -n +2 <queue> > <queue>.tmp`, `mv <queue>.tmp <queue>`. Children are prepended depth-first with `{ echo "$CHILDREN"; echo "$EXISTING"; } | grep -v … > <queue>`. `recursive-refine`'s `dequeue_next` is significantly richer (depth maps, visited list, dequeued-count counter, stderr progress lines) and should not be conflated with a simple `queue_pop` fragment.

**`research-coverage-flow`** — `scripts/little_loops/loops/deep-research.yaml` and `scripts/little_loops/loops/deep-research-arxiv.yaml` share the same 6-state FSM topology (`init → generate_queries → search_web → evaluate_sources → score_coverage → [synthesize | plan_next → search_web]`) and identical top-level settings (`max_iterations: 30`, `timeout: 3600`, `input_key: topic`, `depth: 3`, `coverage_threshold_pct: 85`). However, the divergence is deeper than a single `source_filter` parameter: `search_web` adds `site:arxiv.org` and a different citation format; `evaluate_sources` uses recency (time-derived) vs. credibility (1–5 score), a different dedup key (arxiv ID vs. URL), and different pruning rules; `synthesize` produces a BibTeX section with different table columns. A parameterized flow extraction will need at minimum: `source_filter`, `scoring_axis`, `dedup_key`, `citation_format`, and conditional `synthesize` behavior.

**`diff_stall_gate`** — the `diff_stall` evaluator is used in 3 loops: `scripts/little_loops/loops/incremental-refactor.yaml` (state `execute_step`, attached to a prompt action, `on_no: replan`), `scripts/little_loops/loops/harness-multi-item.yaml` (state `check_stall`, dedicated `echo 'checking stall'` shell state, `on_no: advance`), and `scripts/little_loops/loops/harness-single-shot.yaml` (state `check_stall`, same echo pattern, `on_no: done`). All three use `max_stall: 2`. A `diff_stall_gate` fragment standardizes the `evaluate:` block only — callers still supply `action`/`action_type` and routing since `on_no` behavior differs.

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
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — new sub-loop (create)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — replace states `get_passed_issues`, `implement_next`, `go_no_go`, `implement_issue`, `skip_and_continue` with a `loop:` delegation
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same 5-state replacement; uses `context_passthrough: true` for `refine_issue` (vs. explicit `with:` in the auto variant — keep this difference)
- `scripts/little_loops/loops/lib/common.yaml` — add `queue_pop` (head-pop), `queue_track` (skip-list append), and `diff_stall_gate` fragments
- `scripts/little_loops/loops/autodev.yaml` — convert `dequeue_next` to use `queue_pop` fragment
- `scripts/little_loops/loops/recursive-refine.yaml` — `dequeue_next` is richer (depth map, visited list, counter); convert only the core head-pop lines or leave intact with a comment (decide during implementation)
- `scripts/little_loops/loops/incremental-refactor.yaml` — convert `execute_step` `evaluate:` block to use `diff_stall_gate`; `on_no` routes to `replan`
- `scripts/little_loops/loops/harness-multi-item.yaml` — convert `check_stall` to use `diff_stall_gate`; `on_no: advance`
- `scripts/little_loops/loops/harness-single-shot.yaml` — convert `check_stall` to use `diff_stall_gate`; `on_no: done`
- `scripts/little_loops/loops/oracles/research-coverage.yaml` — new parameterized flow (create); parameters needed: `source_filter`, `scoring_axis`, `dedup_key`, `citation_format`, plus conditional `synthesize` behavior
- `scripts/little_loops/loops/deep-research.yaml` — convert to delegate `generate_queries → … → score_coverage` chain to the flow
- `scripts/little_loops/loops/deep-research-arxiv.yaml` — same conversion with arxiv-specific parameters
- `README.md` — update loop count (`**67 FSM loops**` → `**69 FSM loops**`) after two new oracle YAMLs are created; `ll-verify-docs` enforces this automatically [Wiring pass finding]

### Reference: Existing Oracle Pattern
Model the new `implement-issue-chain` sub-loop after:
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — `parameters:` block, `on_handoff: spawn`, terminal states `done`/`failed`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — `import: [lib/common.yaml]`, `context:` defaults, `with:` binding pattern from callers

### Reference: Fragment Library Pattern
Model new fragments in `common.yaml` after existing entries:
- `convergence_gate` — evaluator-only fragment (no `action`); caller supplies `action`, routing
- `shell_exit` — `action_type: shell` + `evaluate.type: exit_code`; caller supplies `action`, routing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — `ll-loop validate` entry point
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` calls `load_and_validate()`
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()`, `_deep_merge()` (no change needed; read to understand merge semantics)
- `scripts/little_loops/fsm/validation.py` — `_validate_artifact_isolation()` enforces MR-3; `_validate_meta_loop_evaluation()` enforces MR-1

### Tests
- `scripts/tests/test_builtin_loops.py` — `test_all_validate_as_valid_fsm()` runs `ll-loop validate` on every built-in loop; all new/modified loops must pass
- `scripts/tests/test_fsm_fragments.py` — `TestResolveFragmentsWithImports` covers fragment resolution; add cases for new fragments
- `scripts/tests/test_loops_recursive_refine.py` — covers `recursive-refine` state machine; check for regressions if `dequeue_next` is touched

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **BREAKING (12+ methods)**: `TestAutoRefineAndImplementLoop` (8+ methods asserting `get_passed_issues`, `implement_next`, `implement_issue`, `skip_and_continue`, `go_no_go` states) and `TestSprintRefineAndImplementLoop` (4+ methods) will break when those states are replaced by `loop:` delegation — update/replace these test methods [Agent 2 + 3 finding]
- `scripts/tests/test_builtin_loops.py` — `test_expected_loops_exist` hardcoded expected set must have new oracle names (`implement-issue-chain`, `research-coverage`) added [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.builtin_loops` fixture uses `.glob("*.yaml")` (non-recursive); new oracle files under `loops/oracles/` are NOT auto-validated by generic tests — change to `.rglob("*.yaml")` filtered by `is_runnable_loop()` [Agent 2 finding]
- `scripts/tests/test_deep_research.py` — **BREAKING**: `TestDeepResearchYaml.test_required_states_exist()`, `test_coverage_state_uses_sentinel()`, `test_plan_next_loops_back_to_search_web()` will break if `deep-research.yaml` delegates inner states to `research-coverage` oracle; update these for post-delegation structure [Agent 2 + 3 finding]
- `scripts/tests/test_deep_research_arxiv.py` — **BREAKING**: `TestDeepResearchArxivYaml` same 3 methods break under same conditions [Agent 2 + 3 finding]
- `scripts/tests/test_doc_counts.py` — add `test_implement_issue_chain_is_runnable()` and `test_research_coverage_is_runnable()` to `TestIsRunnableLoop` following the existing `test_enumerate_and_prove_is_runnable` pattern [Agent 2 finding]
- `scripts/tests/test_fsm_fragments.py` — add two-level test classes (`TestQueuePopFragment`, `TestQueueTrackFragment`, `TestDiffStallGateFragment`) following `TestConvergenceGateFragment` pattern (schema presence + `resolve_fragments` integration test); ensure each new fragment includes `description:` field to pass `test_all_common_yaml_fragments_have_description` [Agent 3 finding]

### Documentation
- `scripts/little_loops/loops/README.md` — built-in loops table; add entries for new oracles/flows
- `docs/guides/LOOPS_GUIDE.md` — fragment authoring section; no change expected unless new fragment pattern is introduced

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — add `## oracles/research-coverage` section following `## oracles/generator-evaluator` pattern (parameters table, invocation example, internal state machine description); update `## deep-research` state graph if delegation restructuring changes the flat FSM topology [Agent 2 finding]
- `skills/create-loop/reference.md` — `## Fragment Catalog → ### lib/common.yaml fragments` table needs rows for `queue_pop`, `queue_track`, `diff_stall_gate` (what each provides vs. what caller must supply); update `## Stall Detection` code example (~line 391) from inline `diff_stall` config to `fragment: diff_stall_gate` pattern [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — update `### Stall Detection` inline example (~line 2766) to reflect `fragment: diff_stall_gate` pattern (trigger condition met: new fragment pattern introduced by this wave) [Agent 2 + 3 finding]

### Configuration
- N/A

## Implementation Steps

1. **Extract `implement-issue-chain` sub-loop** — create `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` with states `get_passed_issues`, `implement_next`, `go_no_go`, `implement_issue`, `skip_and_continue` following the oracle pattern (`parameters:`, `on_handoff: spawn`, terminal states `done`/`failed`). Add `shared_state_ok: true` at the loop top level (queue files cross-run by design). Then replace the 5 mirrored states in `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` with a `loop: oracles/implement-issue-chain` delegation; preserve the `context_passthrough: true` vs. explicit `with:` difference between the two callers.

2. **Add `queue_pop` and `queue_track` fragments to `scripts/little_loops/loops/lib/common.yaml`** — `queue_pop`: `action_type: shell`, evaluate `exit_code`, supplies the atomic head-pop shell idiom (3-line: `head -1`, `tail -n +2 > .tmp`, `mv`); caller supplies `action` (queue file path via `${context.*}`) and routing. `queue_track`: `action_type: shell`, no evaluator; appends to skip list with `>>`. Model after `shell_exit` fragment in same file. Then convert `autodev.yaml:dequeue_next` to use `queue_pop`. Assess `recursive-refine.yaml:dequeue_next` — if the depth-map / visited-list logic makes fragment reuse impractical, leave with a code comment pointing to the fragment and mark as known exception.

3. **Extract `research-coverage-flow`** — create `scripts/little_loops/loops/oracles/research-coverage.yaml` (or `loops/flows/` if a `flows/` convention is preferred; check existing loop listing). Required parameters: `source_filter` (e.g., `"site:arxiv.org"`), `scoring_axis` (credibility vs. recency), `dedup_key` (URL vs. arxiv ID), `citation_format`, and `academic_mode` (bool — gates the academic-terminology instructions). The `synthesize` state will need conditional branching or separate terminal states for BibTeX vs. standard output. Then convert `deep-research.yaml` and `deep-research-arxiv.yaml` to delegate the inner FSM chain to the flow.

4. **Add `diff_stall_gate` fragment to `scripts/little_loops/loops/lib/common.yaml`** — supplies `evaluate.type: diff_stall` and `evaluate.max_stall: 2` as defaults; caller supplies `action`, `action_type`, and all routing (`on_yes`, `on_no`, `on_error`). Then convert `incremental-refactor.yaml:execute_step`, `harness-multi-item.yaml:check_stall`, and `harness-single-shot.yaml:check_stall` to use `fragment: diff_stall_gate`.

5. **Run `ll-loop validate` on all modified loops** — `ll-loop validate scripts/little_loops/loops/auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`, `autodev.yaml`, `incremental-refactor.yaml`, `harness-multi-item.yaml`, `harness-single-shot.yaml`, `deep-research.yaml`, `deep-research-arxiv.yaml`, and the two new oracle files.

6. **Run test suite** — `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py -v --tb=short` to verify no regressions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `README.md` — bump loop count from `**67 FSM loops**` to `**69 FSM loops**` after creating the two new oracle YAMLs; run `ll-verify-docs` to confirm count matches
8. Update `docs/reference/loops.md` — add `## oracles/research-coverage` section (parameters table, state machine description, invocation example); update `## deep-research` state graph if delegation changes the flat FSM topology
9. Update `skills/create-loop/reference.md` — add fragment catalog rows for `queue_pop`, `queue_track`, `diff_stall_gate`; update `## Stall Detection` code example to show `fragment: diff_stall_gate` pattern
10. Update `docs/guides/LOOPS_GUIDE.md` — revise `### Stall Detection` inline example (~line 2766) to use `fragment: diff_stall_gate`
11. Update `scripts/tests/test_builtin_loops.py` — (a) update/replace `TestAutoRefineAndImplementLoop` and `TestSprintRefineAndImplementLoop` methods asserting the 5 extracted states; (b) add new oracle names to `test_expected_loops_exist` hardcoded set; (c) fix `TestBuiltinLoopFiles.builtin_loops` fixture from `.glob("*.yaml")` to `.rglob("*.yaml")` filtered by `is_runnable_loop()`
12. Update `scripts/tests/test_deep_research.py` and `scripts/tests/test_deep_research_arxiv.py` — revise `test_required_states_exist()`, `test_coverage_state_uses_sentinel()`, and `test_plan_next_loops_back_to_search_web()` in both files for the post-delegation structure
13. Add to `scripts/tests/test_doc_counts.py` — `test_implement_issue_chain_is_runnable()` and `test_research_coverage_is_runnable()` to `TestIsRunnableLoop`
14. Add to `scripts/tests/test_fsm_fragments.py` — `TestQueuePopFragment`, `TestQueueTrackFragment`, `TestDiffStallGateFragment` test classes (schema presence + `resolve_fragments` integration; all new fragments need `description:` field)
15. Run expanded test suite: `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_loops_recursive_refine.py scripts/tests/test_deep_research.py scripts/tests/test_deep_research_arxiv.py scripts/tests/test_doc_counts.py -v --tb=short`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` both contain the comment `# NOTE: … are mirrored in sprint-refine-and-implement.yaml. Keep both files in sync when editing.` — confirms the extraction is well-motivated and the divergence risk is known.
- The `diff_stall` evaluator implementation is in `scripts/little_loops/fsm/evaluators.py:evaluate_diff_stall()` — persists state to `.loops/tmp/ll-diff-stall-<hash>.txt` and `.loops/tmp/ll-diff-stall-<hash>.count`; optional `scope:` field limits the diff to specific paths.
- Fragment merge is implemented in `scripts/little_loops/fsm/fragments.py:_deep_merge()` — fragment fields are the base, state-level keys win at every nesting level; fragment `description:` is stripped before merge. This means `diff_stall_gate` can supply `evaluate:` as a nested dict and callers can override individual subkeys.
- `scripts/tests/test_builtin_loops.py:test_all_validate_as_valid_fsm()` iterates over all files returned by `get_builtin_loops_dir()` — new files in `loops/oracles/` are automatically picked up with no test changes needed.
- The `research-coverage-flow` divergence spans 5 of 6 shared states (`generate_queries`, `search_web`, `evaluate_sources`, `plan_next`, `synthesize`) — extraction is feasible but the parameter surface is larger than originally scoped. If parameterization grows unwieldy, consider extracting only the FSM topology (stub prompt templates) and keeping arxiv-specific prompts as overrides at the caller state level.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-02_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across 21 sites — largest implementation risk is tracking all sites; stage and validate after each sub-item, not all at once
- research-coverage-flow parameterization — 5+ parameters plus conditional synthesize behavior; this sub-item may require as much effort as items 1, 3, and 4 combined; fallback (topology-only extraction with caller prompt overrides) is documented — decide early if the full parameter surface grows unwieldy
- 12+ BREAKING test methods in test_builtin_loops.py — recommend updating tests after each oracle extraction rather than batching all test updates to the end

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - (current session)
- `/ll:wire-issue` - 2026-06-02T06:00:35 - `7dd9a718-8ad5-44a8-ae24-1bdd078a6e05.jsonl`
- `/ll:refine-issue` - 2026-06-02T05:52:52 - `9baac2c8-a902-4e42-9cf8-2a7ac7ac4db5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:58 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:18 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T20:39:40 - `878c5913-3278-47e9-865c-2f4ceb07948f.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T01:16:05 - `5513c747-2bdb-461c-ade9-635f62428078.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue adds a `diff_stall_gate` fragment to `loops/lib/common.yaml` to standardize the existing `diff_stall` evaluator. ENH-1795 adds a new `action_stall` evaluator as a complement to `diff_stall`. After ENH-1795 ships, `common.yaml` should also include an `action_stall_gate` fragment for symmetry — but that is NOT in this issue's scope (Wave 4 is bounded to the 4 listed items). Either ENH-1795 should add `loops/lib/common.yaml` to its integration map (to add the `action_stall_gate` fragment there), or a Wave 5 follow-up should be filed. This issue does not depend on ENH-1795, but the combined result is incomplete without the symmetric fragment.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue modifies `loops/incremental-refactor.yaml` (for the `diff_stall_gate` fragment) and `loops/lib/common.yaml` (for `queue_pop`, `queue_track`, and `diff_stall_gate` fragments). Both of these files are also modified by ENH-1775 (Wave 2) and ENH-1776 (Wave 3). This issue's `depends_on: [ENH-1775, ENH-1776]` serializes the wave sequence correctly — enforce this in sprint planning to prevent concurrent edits to `incremental-refactor.yaml` and `common.yaml`. ENH-1776's `common.yaml` additions (`convergence_gate`, `ll_rubric_score`) must be merged before this issue adds `queue_pop`, `queue_track`, and `diff_stall_gate` to the same file.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-02
- **Reason**: Issue too large for single session (score: 11/11, Very Large)

### Decomposed Into
- ENH-1874: Extract implement-issue-chain sub-loop
- ENH-1875: Add queue_pop and queue_track fragments to common.yaml
- ENH-1876: Extract research-coverage-flow oracle from deep-research loops
- ENH-1877: Add diff_stall_gate fragment and complete Wave 4 integration

## Status

**Done** | Created: 2026-05-28 | Priority: P3
