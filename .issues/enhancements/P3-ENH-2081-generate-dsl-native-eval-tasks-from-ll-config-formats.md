---
id: ENH-2081
title: Generate DSL-native eval tasks from ll's own config formats
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2081: Generate DSL-native eval tasks from ll's own config formats

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

## Status

open
