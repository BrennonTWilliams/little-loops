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

## Status

open
