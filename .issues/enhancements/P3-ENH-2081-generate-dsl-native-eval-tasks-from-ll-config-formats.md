---
id: ENH-2081
title: Generate DSL-native eval tasks from ll's own config formats
type: ENH
priority: P3
status: open
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 88
outcome_confidence: 65
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 20
decision_needed: true
---

# ENH-2081: Generate DSL-native eval tasks from ll's own config formats

## Summary

Extend `ll:create-eval-from-issues` and `ll-harness` with a DSL-native evaluation mode that generates and runs fill-in-the-blank and transform tasks targeting ll's own YAML loop syntax, issue frontmatter, and FSM spec — producing more discriminating model benchmarks than general Python coding tasks.

## Current Behavior

`ll:create-eval-from-issues` generates general coding evaluation tasks. `ll-harness` runs these tasks but has no DSL-specific mode. Neither tool can generate or evaluate tasks targeting ll's own YAML/frontmatter DSLs (loop transitions, FSM routing tables, issue frontmatter schemas).

## Expected Behavior

`ll:create-eval-from-issues --dsl <loop-yaml>` accepts a loop YAML or issue file and generates DSL-specific tasks (fill-in-the-blank FSM transitions, malformed frontmatter correction, state routing completion) stored under `evals/dsl/<source-name>/` with a metadata header indicating the source DSL. `ll-harness --dsl` runs these task sets and reports pass rates per model.

## Motivation

Standard Python coding tasks compress capability differences between models. Evaluating agent capability on ll's own YAML loop syntax, issue frontmatter, and FSM spec — low-ecosystem DSLs with no training-data saturation — produces more discriminating benchmarks. This directly improves the signal quality of ll-harness and ll-eval for choosing between models or loop designs.

## Proposed Solution

Extend `ll:create-eval-from-issues` to include a DSL task generation mode: given a loop YAML or issue file as a reference, generate a set of fill-in-the-blank and transform tasks (e.g., 'complete this FSM transition table', 'fix this malformed issue frontmatter') that exercise ll-specific syntax rather than general Python. Store the generated tasks under `evals/dsl/` with a metadata header indicating the source DSL. Add a `--dsl` flag to `ll-harness` to run these task sets and report pass rates by model.

## Implementation Steps

1. Add `--dsl` mode to `ll:create-eval-from-issues` that accepts a loop YAML or issue file as input
2. Implement DSL task templates: fill-in-the-blank FSM transitions, malformed frontmatter correction, state routing completion
3. Write generated tasks to `evals/dsl/<source-name>/` with source DSL metadata header
4. Add `--dsl` flag to `ll-harness` CLI to run DSL task sets
5. Report pass rates per model in `ll-harness` output when `--dsl` is active

## Acceptance Criteria

- [ ] `ll:create-eval-from-issues --dsl <loop-yaml>` generates DSL-specific tasks in `evals/dsl/`
- [ ] Generated tasks include fill-in-the-blank and transform variants for ll YAML/frontmatter syntax
- [ ] `ll-harness --dsl` runs the task set and reports pass rates by model
- [ ] Task files include metadata header with source DSL reference

## Scope Boundaries

- Out of scope: changes to existing general Python evaluation modes (unchanged behavior)
- Out of scope: automated ML training or fine-tuning of models based on task results
- Out of scope: task quality validation beyond the metadata header written at generation time
- Out of scope: multi-DSL cross-format tasks (e.g. mixing loop YAML and issue frontmatter in one task) in this iteration

## Impact

- **Priority**: P3 — improves benchmark discriminability for model/loop selection; non-urgent
- **Effort**: Medium — new CLI flags on two tools, DSL task template engine, `evals/dsl/` storage convention
- **Risk**: Low — purely additive; no changes to existing evaluation paths or harness output format
- **Breaking Change**: No

## Labels

`enhancement`, `eval`, `harness`, `dsl`, `captured`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-10; updated 2026-06-10_

**Readiness Score**: 88/100 → PROCEED
**Outcome Confidence**: 65/100 → LOW

### Concerns
- Missing Integration Map / Files to Modify section

### Outcome Risk Factors
- **Open question: DSL task file format** — the issue does not specify the schema/fields for fill-in-the-blank FSM task files or expected response format. This is an open decision that needs to be resolved before writing the task template engine.
- **Open question: `ll-harness --dsl` task-discovery protocol** — the issue does not specify how `ll-harness --dsl` locates tasks (directory scan vs. explicit path argument) or what evaluation criteria it applies to DSL task outputs.
- **Open question: metadata header structure** — "metadata header indicating the source DSL" is mentioned but the format is unspecified (YAML frontmatter? JSON? inline comment?).
- **Open question: evaluation scoring** — "report pass rates per model" is stated but the grading rubric (exact match, partial match, semantic judge?) is not defined.

## Session Log
- `/ll:decide-issue` - 2026-06-11T03:47:32 - `26bee10d-f173-4904-92ec-7625750a7371.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `7c955a46-8e58-4db5-98b5-f8965296ecab.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `4a059ba1-7741-429c-acd5-bbaa7aeb09dc.jsonl`
- `/ll:decide-issue` - 2026-06-11T03:22:56 - `d894c9c1-6275-4e3c-8327-c75215a32cb0.jsonl`
- `/ll:format-issue` - 2026-06-10T23:31:13 - `714a8869-591f-4a9c-91ec-045042d7d120.jsonl`
- `/ll:confidence-check` - 2026-06-10T23:45:00Z - `7a3f7d68-548f-4c2a-bce7-6414775a985c.jsonl`
