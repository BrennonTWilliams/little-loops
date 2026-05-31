---
id: ENH-1776
title: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`
type: ENH
priority: P3
captured_at: "2026-05-29T01:01:55Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
---

# ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Summary

Add two shared evaluator fragments (`convergence_gate` and `ll_rubric_score`) that standardize repeated evaluator patterns across 10 loops combined, and extract the `enumerate → parse → flatten → prove` chain from two integration loops into a reusable flow.

## Current Behavior

**`convergence_gate` pattern** — 5 loops use the `convergence` evaluator type with duplicated direction, target, tolerance, and previous-value wiring:

- `test-coverage-improvement.yaml`
- `agent-eval-improve.yaml`
- `rl-coding-agent.yaml`
- `rl-policy.yaml`
- `harness-optimize.yaml`

**`ll_rubric_score` pattern** — all 5 harness loops use an LLM prompt with a multi-criterion weighted rubric, structured output with per-criterion scores, and ALL_PASS/ITERATE routing. The rubric structure is duplicated with different criteria names across loops.

**`enumerate-prove` chain** — `adopt-third-party-api.yaml` and `integrate-sdk.yaml` both contain nearly identical `parse_enumeration` (python3 heredoc), `flatten_targets`/`flatten_surfaces` (python3 comma-join), and delegation to `ready-to-implement-gate` — a four-state chain duplicated across both loops.

## Expected Behavior

**`convergence_gate` fragment** in `loops/lib/common.yaml`:

```yaml
convergence_gate:
  action_type: shell
  evaluate:
    type: convergence
    direction: maximize
    target: "${context.convergence_target}"
    tolerance: "${context.convergence_tolerance}"
    previous: "${captured.prev_value.output}"
```

**`ll_rubric_score` fragment** — a parameterized LLM prompt fragment that takes `context.rubric_criteria` (YAML/JSON), `context.pass_threshold`, and evaluates via `output_contains` on ALL_PASS.

**`enumerate-prove-flow`** extracted as a named, composable multi-state sequence that takes a source (URL or codebase path) and returns proven targets.

## Motivation

The convergence evaluator is used identically across 5 loops but has no fragment template — each loop re-specifies direction, target, and tolerance inline. The rubric scoring pattern is the core of every harness loop's quality gate but each copy is independent. The enumerate-prove chain is four states duplicated verbatim across two integration loops.

## Proposed Solution

1. Add `convergence_gate` fragment to `loops/lib/common.yaml`
2. Add `ll_rubric_score` fragment to `loops/lib/common.yaml` (or `lib/harness.yaml`)
3. Extract `enumerate-prove-flow` as a flow definition or sub-loop
4. Convert 5 convergence callers to reference the fragment
5. Convert 5 harness loops to reference `ll_rubric_score`
6. Convert `adopt-third-party-api.yaml` and `integrate-sdk.yaml` to use the flow
7. Run `ll-loop validate` on all modified loops
8. Run `python -m pytest scripts/tests/ -v --tb=short`

## Integration Map

### Files to Modify
- `loops/lib/common.yaml` — add `convergence_gate` fragment
- `loops/lib/common.yaml` (or `lib/harness.yaml`) — add `ll_rubric_score` fragment
- `loops/oracles/enumerate-and-prove.yaml` — new sub-loop/flow
- `loops/test-coverage-improvement.yaml` — convert convergence state
- `loops/agent-eval-improve.yaml` — convert convergence state
- `loops/rl-coding-agent.yaml` — convert convergence state
- `loops/rl-policy.yaml` — convert convergence state
- `loops/harness-optimize.yaml` — convert convergence state
- `loops/html-website-generator.yaml` — convert rubric scoring (post Wave 2 refactor)
- `loops/svg-image-generator.yaml` — convert rubric scoring
- `loops/html-anything.yaml` — convert rubric scoring
- `loops/hitl-md.yaml` — convert rubric scoring
- `loops/hitl-compare.yaml` — convert rubric scoring
- `loops/adopt-third-party-api.yaml` — convert to use enumerate-prove flow
- `loops/integrate-sdk.yaml` — convert to use enumerate-prove flow

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` CLI
- `scripts/little_loops/loop_runner.py` — convergence evaluator implementation (no changes, validate only)

### Similar Patterns
- Any future loop using convergence-based termination should use this fragment

### Tests
- `scripts/tests/` — regression suite

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `convergence_gate` fragment to `loops/lib/common.yaml`
2. Add `ll_rubric_score` fragment to shared lib
3. Extract `enumerate-prove-flow` to `loops/oracles/enumerate-and-prove.yaml`
4. Convert 5 convergence callers to reference the fragment
5. Convert 5 harness loops to reference `ll_rubric_score`
6. Convert 2 integration loops to use `enumerate-prove-flow`
7. Run `ll-loop validate` on all modified loops
8. Run `python -m pytest scripts/tests/ -v --tb=short`

## Success Metrics

- `convergence_gate` fragment eliminates 5 duplicate convergence evaluator definitions
- `ll_rubric_score` fragment eliminates 5 duplicate rubric-scoring states
- `enumerate-prove-flow` eliminates 4 duplicated states across 2 integration loops
- All modified loops pass `ll-loop validate`
- Test suite passes with no regressions

## Scope Boundaries

- Fragment additions and flow extraction only — no behavioral changes
- `ll_rubric_score` should build on the `generator-evaluator` sub-loop from Wave 2 if applicable
- Only the listed loops; no new convergence or rubric patterns introduced

## API/Interface

N/A - No public API changes

## Impact

- **Priority**: P3 — Medium ROI; further standardizes evaluator patterns but builds on Waves 1-2
- **Effort**: Medium — 3 items across ~12 loops; `ll_rubric_score` design depends on Wave 2's sub-loop interface
- **Risk**: Low-Medium — Convergence fragment is trivial (pure evaluator); rubric fragment must handle varying criteria structures
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop composition and evaluator types |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T01:15:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe72aa2c-e995-4907-94b6-587fa28e4586.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): ENH-1775 (Wave 2) moves rubric scoring into the `generator-evaluator` sub-loop. After Wave 2, the 5 harness parent loops are thin wrappers delegating to that sub-loop — they no longer contain inline rubric states. This issue's `ll_rubric_score` fragment MUST target `loops/oracles/generator-evaluator.yaml` (the sub-loop), NOT the 5 parent wrapper loops. The `enumerate-prove-flow` shares `adopt-third-party-api.yaml` and `integrate-sdk.yaml` with Wave 2's `parse_tagged_json` fragment; the flow MUST compose from Wave 2's fragment. Coordinate fragment placement with ENH-1774 (uses `cli.yaml`) — use `common.yaml` for new fragments to maintain consistency across waves.

## Status

**Open** | Created: 2026-05-28 | Priority: P3
