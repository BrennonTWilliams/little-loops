---
id: ENH-756
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# ENH-756: Refactor create-loop wizard templates and questions to use patterns not use-cases

## Summary

The `/ll:create-loop` wizard's "Start from template" path offers dated templates that conflate loop structure/patterns with use-cases, and the "What kind of automation loop do you want to create?" question has the same problem. Both need to be reframed around structural patterns (like "Harness a skill or prompt" and "Run a sequence of steps"), not concrete use-cases.

## Motivation

The wizard currently offers templates and questions phrased as use-cases (e.g., "Fix errors until clean") rather than reusable structural patterns. This is inconsistent with the two options that already work well ("Harness a skill or prompt (Recommended)" and "Run a sequence of steps"), creates overlap between the template selection step and the loop-type question, and makes the wizard feel dated and confusing. Users should be guided to the right structural pattern first; use-cases can be examples within that pattern.

## Current Behavior

- "Start from template (Recommended)" offers templates that are use-cases/scenarios, not structural patterns
- "What kind of automation loop do you want to create?" also offers use-case-framed options ("Fix errors until clean", "Run a sequence of steps")
- The two prompts overlap in scope, causing confusion about which choice drives the loop structure
- Templates are dated and don't reflect current loop architecture

## Expected Behavior

- All templates offered in the "Start from template" path should be structural patterns, consistent with "Harness a skill or prompt" and "Run a sequence of steps"
- The "What kind of automation loop do you want to create?" question should likewise offer structural patterns only
- No overlap between the template selection and the loop-type question — each step should add distinct information
- Templates should be current and reflect the actual FSM loop YAML structure

## Implementation Steps

1. Audit the current template list and loop-type question options in the `create-loop` skill
2. Identify which options are use-cases vs. structural patterns
3. Reframe all use-case options as structural patterns (using "Harness a skill or prompt" and "Run a sequence of steps" as the gold standard)
4. Remove or merge options that overlap between the two wizard steps
5. Update/replace dated templates with current FSM-aligned YAML starters
6. Test the full wizard flow to verify the two steps are distinct and complementary

## Affected Files

- `skills/create-loop/SKILL.md` — wizard logic and question definitions
- Any template files referenced by the create-loop skill

## Notes

The two options that already get this right and should serve as the model:
- "Harness a skill or prompt (Recommended)" — a structural pattern
- "Run a sequence of steps" — a structural pattern

---
## Status

active
