---
id: ENH-2221
title: Eval dimension — learning_tests_required as machine-checkable criterion
type: enhancement
priority: P4
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2221: Eval dimension — learning_tests_required as machine-checkable criterion

## Summary

`/ll:create-eval-from-issues` generates eval scenarios from issue specs but all evaluation criteria are LLM-judged. For issues with `learning_tests_required`, add a machine-checkable eval criterion: "All declared learning tests are proven before implementation begins." This is verifiable via `ll-learning-tests check` (exit code 0/1) — no LLM judge needed.

## Current Behavior

`/ll:create-eval-from-issues` generates eval scenarios from issue specs, but all evaluation criteria use LLM-judged (`check_semantic`) evaluators. There is no support for machine-checkable (`exit_code`) criteria, even when an issue declares `learning_tests_required` with known, shell-verifiable targets.

Learning test proof status must be verified manually or through separate tooling — the eval harness does not enforce it as part of the automated eval run.

## Expected Behavior

When an issue with `learning_tests_required` is processed by `/ll:create-eval-from-issues`, the generated eval YAML includes `exit_code` criteria that verify each required learning test is proven via `ll-learning-tests check`. These criteria are grouped separately from LLM-judged dimensions under a `## Proof-First Gates` section, producing an objective PASS/FAIL signal alongside semantic evaluations.

## Motivation

The eval harness (`ll-harness`) supports `exit_code` evaluators alongside `check_semantic`. Learning test proof status is a perfect fit: it's binary, shell-accessible, and captures a real quality gate. Adding it as a criterion means eval runs can report "proof-first gate: PASS/FAIL" objectively alongside LLM-judged dimensions.

## Proposed Solution

In `/ll:create-eval-from-issues`, after parsing issue frontmatter for `learning_tests_required`:

1. For each target in the list, construct an `exit_code` criterion:
   ```yaml
   - id: lt_proven_<slug>
     type: exit_code
     command: "ll-learning-tests check \"<target>\""
     expected_exit: 0
     label: "Learning test proven: <target>"
   ```
2. Inject these criteria before the LLM-judged criteria in the generated eval YAML.
3. In eval output, group them under a `## Proof-First Gates` section header.
4. Gate the behavior behind `learning_tests.enabled`.

The existing `ll-harness` evaluator framework already handles `exit_code` evaluators — no changes to the harness executor are needed. This change is isolated to the eval-from-issues generation logic.

## Implementation Steps

1. In `/ll:create-eval-from-issues`, after parsing the issue, check for `learning_tests_required`.
2. For each target in the list, add an eval criterion of type `exit_code`:
   ```yaml
   - id: lt_proven_<slug>
     type: exit_code
     command: "ll-learning-tests check \"<target>\""
     expected_exit: 0
     label: "Learning test proven: <target>"
   ```
3. Inject these criteria before the LLM-judged criteria in the generated eval YAML.
4. In eval output, group them under a `## Proof-First Gates` section header.
5. Gate behind `learning_tests.enabled`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/create_eval_from_issues.py` — add `learning_tests_required` parsing and `exit_code` criterion injection
- Eval YAML template or assembler — add `## Proof-First Gates` section grouping in output

### Dependent Files

- `ll-harness` — already supports `exit_code` evaluators; no changes needed
- `ll-learning-tests` — the `check` subcommand is the verification mechanism; no changes needed

### Tests

- Add tests for `exit_code` criterion generation when `learning_tests_required` is present
- Add tests verifying issues without `learning_tests_required` produce identical output (unchanged behavior)

### Documentation

- Update eval-from-issues documentation if it describes criterion generation internals

### Configuration

- `learning_tests.enabled` config property gating the new behavior

## Acceptance Signals

- Eval generated from an issue with `learning_tests_required: [anthropic]` includes an `exit_code` criterion for `ll-learning-tests check "anthropic"`
- Running `ll-harness` on the eval returns `PASS` for a proven record and `FAIL` for missing/stale
- The criterion appears in eval output as a separate section from LLM-judged dimensions
- Issues without `learning_tests_required` are unchanged

## Success Metrics

- Eval YAML for `learning_tests_required: [anthropic]` contains an `exit_code` criterion per target
- `ll-harness` eval run reports PASS/FAIL for learning test gates distinctly from semantic criteria
- Issues without `learning_tests_required` produce identical output to current behavior
- Learning test gates are visually grouped under their own section header in eval reports

## Scope Boundaries

- **In scope**: Adding machine-checkable `exit_code` criteria to eval YAML generation; grouping criteria under "Proof-First Gates" in output
- **Out of scope**: Modifying `ll-learning-tests check` itself; adding new CLI commands; changing the LLM-judged criterion format; adding learning test record management features

## Impact

- **Priority**: P4 — valuable quality gate but non-critical; builds on existing learning test infrastructure
- **Effort**: Small — leverages existing `exit_code` evaluator support in `ll-harness`; isolated to eval generation logic
- **Risk**: Low — additive change with no breaking modifications to existing criterion generation
- **Breaking Change**: No

## Labels

`enhancement`, `captured`, `eval`, `learning-tests`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2214 (release gate) and ENH-2220 (scope-epic).

- A complementary machine-checkable gate exists at the release stage (ENH-2214). That gate uses project-wide import scans and configurable `block`/`warn` behavior. This issue's gate uses issue-frontmatter targets and `exit_code` criteria in eval YAML. They are distinct lifecycle stages with different implementations. See [[ENH-2214]].
- This issue consumes `learning_tests_required` frontmatter populated by ENH-2220's scope-epic flow. When ENH-2220 generates sub-issues with learning test prerequisites, those targets become available for eval criterion generation here. See [[ENH-2220]].

## Session Log
- `/ll:format-issue` - 2026-06-18T19:33:39 - `eebe5815-0f5b-4c82-acb0-64597681c904.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P4
