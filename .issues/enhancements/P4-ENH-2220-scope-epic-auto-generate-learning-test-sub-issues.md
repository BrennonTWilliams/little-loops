---
id: ENH-2220
title: scope-epic auto-generate learning test sub-issues for external API epics
type: enhancement
priority: P4
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
labels: enhancement, scope-epic, learning-tests
---

# ENH-2220: scope-epic auto-generate learning test sub-issues for external API epics

## Summary

When `/ll:scope-epic` decomposes an epic into child issues, it doesn't detect external API dependencies in the epic description and doesn't create learning test tasks as sub-issues. Add a detection pass: if the epic mentions packages or third-party APIs that have no proven record, automatically propose learning test sub-issues as part of the decomposition.

## Current Behavior

When `/ll:scope-epic` decomposes an epic into child issues, it does not detect external API dependencies mentioned in the epic description and does not create corresponding learning test sub-issues. Learning test prerequisite work — exploring and proving unproven third-party APIs — must be identified and created manually, which is easy to overlook during epic planning.

## Expected Behavior

`/ll:scope-epic` should detect external packages, SDKs, or third-party APIs mentioned in the epic description, check each against the learning test registry via `ll-learning-tests check`, and automatically propose learning test sub-issues for unproven packages alongside the implementation sub-issues in the scope output.

## Motivation

Learning test tasks are prerequisite work that's easy to forget when planning an epic. Surfacing them during scoping — before the implementation sub-issues are created — ensures they appear in the dependency graph from the start and can be prioritized alongside implementation work.

## Implementation Steps

1. In `/ll:scope-epic`, after the initial epic analysis and before sub-issue generation, run an LLM extraction step: "What external packages, SDKs, or third-party APIs does this epic depend on?"
2. For each extracted package, run `ll-learning-tests check "<package>"`.
3. For each unproven package, propose a learning test sub-issue:
   - Title: `Explore and prove <package> API behavior`
   - Type: ENH
   - Priority: match the parent epic's priority
   - Body: pre-filled for `/ll:explore-api "<package>"` as the implementation step
4. Present the proposed learning test sub-issues alongside the implementation sub-issues in the scope output, clearly labeled as prerequisites.
5. Gate behind `learning_tests.enabled`.

## Impact

- **Priority**: P4 — Low priority enhancement; existing workflow is functional but requires manual effort to identify learning test prerequisites
- **Effort**: Medium — Involves adding an LLM extraction step to the scope-epic flow and integrating with the learning test registry; estimated 3-5 days
- **Risk**: Low — New feature addition to an existing flow; does not change existing sub-issue generation behavior
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: LLM extraction of packages/APIs from epic descriptions; integration with `ll-learning-tests check`; sub-issue generation for unproven packages; gating behind `learning_tests.enabled`
- **Out of scope**: Updating the learning test registry itself; modifying `ll-learning-tests` subcommands beyond `check`; retrospective analysis of existing epics; modifying the `ll-learning-tests create` flow

## Acceptance Signals

- An epic mentioning "Anthropic SDK" with no proven `anthropic` record generates a learning test sub-issue
- An epic mentioning `requests` where `requests` is already proven does not generate a sub-issue
- Learning test sub-issues are marked as dependencies (`depends_on:`) for implementation sub-issues that require the same package

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2215 (create-loop wizard) and ENH-2221 (eval dimension).

- This issue must populate `learning_tests_required` in the frontmatter of any generated sub-issues so that ENH-2215's wizard can read it (skipping its own API-detection question).
- This issue also provides the data that ENH-2221 consumes: when `learning_tests_required` is populated on generated sub-issues, ENH-2221's eval generator automatically picks up those targets for `exit_code` criteria.

This creates a defined data pipeline: `scope-epic` writes `learning_tests_required` → `create-loop` reads it → `create-eval-from-issues` consumes it. See [[ENH-2215]] and [[ENH-2221]].

## Session Log
- `/ll:format-issue` - 2026-06-18T19:33:20 - `c65a1122-f4b2-4da5-8a84-b23a59357b7b.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

---

**Open** | Created: 2026-06-18 | Priority: P4 | Parent: EPIC-2207
