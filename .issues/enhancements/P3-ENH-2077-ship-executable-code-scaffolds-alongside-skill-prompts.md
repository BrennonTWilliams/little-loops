---
id: ENH-2077
title: Ship executable code scaffolds alongside skill prompts
type: ENH
priority: P3
status: open
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
relates_to:
- EPIC-2087
confidence_score: 60
outcome_confidence: 44
score_complexity: 12
score_test_coverage: 10
score_ambiguity: 8
score_change_surface: 14
decision_needed: true
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


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-11_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 44/100 → VERY LOW

### Concerns
- `skill_expander.py` is absent from the Integration Map despite being the subprocess-path injection point for all `ll-auto`/`ll-parallel`/`ll-sprint`/`ll-action` invocations
- The dual invocation paths (Skill tool vs subprocess) require different injection approaches and neither is designed

### Gaps to Address
- Add `skill_expander.py` to Integration Map under Files to Modify; spec how it reads `scaffolds/` content and prepends it to the expanded prompt
- Distinguish scaffolds from the existing `templates.md` files in `create-loop/` and `manage-issue/` — either consolidate or explain the different purpose
- Resolve the TBD sections: enumerate callers via `grep -r "skill_expander\|expand_skill" scripts/`, identify test strategy, confirm any relevant skill authoring docs
- Clarify whether scaffold injection applies to both invocation paths or only one

### Outcome Risk Factors
- **Open design decision: two distinct invocation paths** — `Skill tool` direct invocation vs `skill_expander.py` subprocess path are not distinguished; resolve before implementing which path(s) receive scaffold injection and by what mechanism
- **Blast radius extends to all automation CLI callers** — any modification to `skill_expander.py` touches `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-action`; Integration Map does not enumerate these caller sites
- **Existing `templates.md` overlap** — `create-loop/templates.md` and `manage-issue/templates.md` already ship runnable YAML templates into skill context; no differentiation from proposed scaffolds creates a risk of redundant or conflicting artifacts
- **No test coverage for injection verification** — acceptance criterion "Skill invocation injects scaffold content before the generation step" has no test path; integration tests are listed as TBD

## Session Log
- `/ll:decide-issue` - 2026-06-11T20:44:55 - `c11253e7-4c76-4648-93ac-00ac2e0101cb.jsonl`
- `/ll:format-issue` - 2026-06-11T20:10:58 - `e6b03fdf-7ce2-4da2-bdd7-2966c8e338a9.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `51577893-49ed-4585-85fe-085f192947be.jsonl`
