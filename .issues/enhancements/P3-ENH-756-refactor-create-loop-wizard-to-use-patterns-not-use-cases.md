---
id: ENH-756
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
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

## Scope Boundaries

- **In scope**: Reframing wizard template names/descriptions and loop-type question options to use structural pattern language; updating or replacing dated template YAML starters to reflect current FSM structure
- **Out of scope**: Changing the underlying FSM YAML schema or loop execution engine; adding new loop types beyond what already exists; altering the wizard's step count or overall flow structure

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — wizard logic, loop-type question options, and template definitions

### Dependent Files (Callers/Importers)
- `commands/loop-suggester.md` — references `/ll:create-loop` in comparison docs; does not reference template names directly, so no update needed after rename
- `skills/review-loop/SKILL.md` — references `/ll:create-loop` in integration section; no template name dependencies

### Similar Patterns
- `skills/review-loop/SKILL.md` — uses structural pattern framing; use as reference for consistent language

### Tests
- N/A — skill is a prompt file, no automated tests

### Documentation
- `docs/` — check for any references to old use-case template names
- `README.md` or `CONTRIBUTING.md` — if create-loop wizard examples are documented

### Configuration
- N/A

## Impact

- **Priority**: P3 — UX improvement; wizard confusion reduces adoption but doesn't block core functionality
- **Effort**: Small — changes are limited to prompt text in `SKILL.md`; no code or schema changes
- **Risk**: Low — prompt-only changes with no breaking effect on existing loop YAML files
- **Breaking Change**: No

## Labels

`ux`, `create-loop`, `wizard`, `skill`

## Notes

The two options that already get this right and should serve as the model:
- "Harness a skill or prompt (Recommended)" — a structural pattern
- "Run a sequence of steps" — a structural pattern

---
## Status

**Open** | Created: 2026-03-15 | Priority: P3


## Verification Notes

Verified 2026-03-15 against codebase. All core claims confirmed accurate:
- `skills/create-loop/templates.md` shows 4 use-case/language-specific templates ("Python quality", "JavaScript quality", "Tests until passing", "Full quality gate") — not structural patterns
- `skills/create-loop/SKILL.md:60-66` confirms use-case-framed loop-type options in Step 1
- `SKILL.md:67-69` confirms "Harness a skill or prompt" and "Run a sequence of steps" exist as the structural-pattern models cited in Notes

**Correction applied**: Integration Map listed `skills/loop-suggester/SKILL.md` — this path does not exist. `loop-suggester` is a command at `commands/loop-suggester.md` and does not reference create-loop template names directly.

## Session Log
- `/ll:verify-issues` - 2026-03-15T19:32:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:format-issue` - 2026-03-15T19:29:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:confidence-check` - 2026-03-15T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
