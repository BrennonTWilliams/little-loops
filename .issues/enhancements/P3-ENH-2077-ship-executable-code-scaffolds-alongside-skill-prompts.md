---
id: ENH-2077
title: Ship executable code scaffolds alongside skill prompts
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
relates_to: [EPIC-2087]
---

# ENH-2077: Ship executable code scaffolds alongside skill prompts

## Summary

Skills like `create-loop`, `manage-issue`, and `create-eval-from-issues` currently provide strategy guidance in prose but ship no runnable code scaffolds. Adding scaffold artifacts alongside each skill's prompt — and injecting them into context before the generation step — bridges the gap from conceptual guidance to executable reference and is expected to lift mid-tier model performance on complex automation tasks.

## Current Behavior

Skills `create-loop`, `manage-issue`, and `create-eval-from-issues` provide strategy guidance exclusively through prose instructions. There are no runnable starter scaffolds, template YAMLs, or example code snippets shipped alongside these skill prompts. Agents must infer correct structure from descriptions alone, increasing error rates and retry counts on complex generation tasks.

## Expected Behavior

Each identified high-complexity skill has a `scaffolds/` subdirectory containing a runnable template (YAML, Python module, or annotated snippet). Skill invocation automatically injects scaffold content into context before the generation step. Retry counts for ll-loop runs on these skills are tracked before and after scaffold introduction.

## Motivation

Skills like create-loop, manage-issue, and eval harness templates currently provide strategy guidance in prose. Conceptual descriptions tell agents what to do; only runnable code scaffolds bridge the gap to execution. Providing a working reference library of primitives alongside prompts dramatically lifts mid-tier model performance on complex automation tasks.

## Proposed Solution

Identify the highest-complexity skills (create-loop, manage-issue, create-eval-from-issues) and accompany each with a starter scaffold: a template YAML, a Python helper module, or an example-driven code snippet embedded in the skill preamble rather than prose instructions. Add a `scaffolds/` directory under each skill folder to hold these artifacts. Update skill invocation to inject the scaffold content into context before the generation step. Track whether including the scaffold reduces retry counts in ll-loop runs.

## Implementation Steps

1. Identify top-complexity skills: create-loop, manage-issue, create-eval-from-issues
2. Create `scaffolds/` subdirectory under each identified skill folder
3. Author template YAML / Python helper / code snippet for each skill
4. Update skill invocation logic to inject scaffold content into context preamble
5. Add ll-loop run tracking to measure retry count delta before/after scaffold injection

## Acceptance Criteria

- [ ] `scaffolds/` directory exists under at least create-loop, manage-issue, create-eval-from-issues skill folders
- [ ] Each scaffold contains a runnable template (YAML, Python module, or annotated snippet)
- [ ] Skill invocation injects scaffold content before the generation step
- [ ] Retry count tracking is documented or instrumented

## Success Metrics

- Retry count delta: measurable reduction in ll-loop retry counts for targeted skills after scaffold injection
- Scaffold coverage: `scaffolds/` directory present under all 3 identified skills
- Injection verification: scaffold content confirmed in skill context preamble via test or trace

## Scope Boundaries

- **In scope**: `scaffolds/` directories under `create-loop`, `manage-issue`, and `create-eval-from-issues`; context injection for these three skills; retry count tracking
- **Out of scope**: Scaffolds for all other skills; automated scaffold generation; changes to FSM loop YAML schema

## API/Interface

N/A - No public API changes. Scaffold injection is internal to skill invocation context.

## Integration Map

### Files to Modify
- `skills/create-loop/` — add `scaffolds/` directory with template YAML scaffold
- `skills/manage-issue/` — add `scaffolds/` directory with example code snippet
- `skills/create-eval-from-issues/` — add `scaffolds/` directory with eval harness template
- Each skill's SKILL.md preamble or invocation hook to inject scaffold content

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "create-loop\|manage-issue\|create-eval-from-issues" scripts/` to find callers

### Similar Patterns
- TBD — search: `grep -r "scaffold\|preamble" skills/`

### Tests
- TBD — integration tests verifying scaffold content appears in context for each skill

### Documentation
- TBD — skill authoring guide if one exists

### Configuration
- N/A

## Impact

- **Priority**: P3 - Developer experience improvement; not blocking active work
- **Effort**: Medium - authoring 3 scaffolds and updating invocation logic; no infrastructure changes
- **Risk**: Low - additive only; does not modify existing skill prompts, only prepends scaffold context
- **Breaking Change**: No

## Labels

`enhancement`, `skill-enhancement`, `developer-experience`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-11T20:10:58 - `e6b03fdf-7ce2-4da2-bdd7-2966c8e338a9.jsonl`
