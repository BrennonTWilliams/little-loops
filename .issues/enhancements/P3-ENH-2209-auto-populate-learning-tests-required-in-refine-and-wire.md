---
id: ENH-2209
title: Auto-populate `learning_tests_required` in refine-issue and wire-issue
type: enhancement
priority: P3
status: open
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2209: Auto-populate `learning_tests_required` in refine-issue and wire-issue

## Summary

The `learning_tests_required: list[str]` frontmatter field must currently be declared manually by issue authors. The `assumption-firewall` loop already extracts external-API assumptions from issue text via LLM. That same extraction logic should run during `/ll:refine-issue` and `/ll:wire-issue` to auto-populate the field, making the gate self-provisioning.

## Current Behavior

`learning_tests_required` must be declared manually in issue frontmatter. The `assumption-firewall` loop already performs external-API assumption extraction but only as a standalone loop step — not during `/ll:refine-issue` or `/ll:wire-issue`. Issues commonly reach implementation without the field populated, causing the discoverability gate to be bypassed entirely.

## Expected Behavior

After `/ll:refine-issue` or `/ll:wire-issue` completes, `learning_tests_required` is automatically populated in the issue's frontmatter. The extraction step runs after the implementation plan section is written, invokes `ll-learning-tests check` for each found target, and writes the full list to frontmatter. Issues with no external dependencies omit the field (not set to `[]`).

## Motivation

Most issue authors don't know to add `learning_tests_required`. The field is only useful if it's populated before implementation begins. Refinement is the natural point to extract and persist assumptions — after the implementation plan is written but before the issue is marked ready.

## Implementation Steps

1. In the `/ll:refine-issue` skill (and `/ll:wire-issue`), after the implementation plan section is written, run an LLM extraction step: "List all external packages, SDKs, or third-party API surfaces that the plan assumes behavior of."
2. Deduplicate and slugify to match registry lookup keys.
3. For each extracted target, run `ll-learning-tests check "<target>"` to determine current registry status.
4. Write the full list to `learning_tests_required:` frontmatter (overwrite if already present).
5. Surface a summary: "Found N external dependencies — M proven, K unproven. Added to `learning_tests_required`."
6. If all are already proven, emit a brief confirmation and skip the field update if it was already correct.

## Success Metrics

- After `/ll:refine-issue` on an issue that mentions `anthropic`, `requests`, or any third-party package, `learning_tests_required` is populated in frontmatter
- Running `/ll:ready-issue` immediately after shows the correct gate status for each entry
- Issues with no external dependencies have `learning_tests_required` omitted (not set to `[]`)

## Scope Boundaries

- **In scope**: Auto-extraction of external API assumptions from implementation plan text in `refine-issue` and `wire-issue`; writing results to `learning_tests_required` frontmatter; surfacing a summary of proven/unproven entries per issue
- **Out of scope**: Creating new learning test records (owned by `/ll:explore-api`); modifying the `assumption-firewall` loop; retroactive population of existing issues; changes to `ll-learning-tests` CLI internals

## Impact

- **Priority**: P3 — Parent EPIC-2207 is not time-sensitive; improves gate reliability without blocking current workflows
- **Effort**: Small — Adds a post-step to two existing skills; extraction logic modeled directly on the assumption-firewall loop
- **Risk**: Low — Additive frontmatter write only; existing issues and skills are unaffected
- **Breaking Change**: No

## Labels

`enhancement`, `workflow`, `learning-tests`, `refine-issue`, `wire-issue`

## Status

**Open** | Created: 2026-06-18 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-18T18:17:31 - `e95db64d-70ee-4f7f-87aa-5e8414c2d4c9.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
