---
id: ENH-756
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 68
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

1. In `skills/create-loop/templates.md:8-21`, replace the four use-case template options ("Python quality", "JavaScript quality", "Tests until passing", "Full quality gate") with structural pattern options — e.g., "Fix until clean", "Maintain constraints", "Run a sequence", "Harness a skill or prompt" — and update their descriptions to name the pattern shape, not the use-case
2. In `skills/create-loop/templates.md:28-148`, update template YAML starters to match renamed patterns; the existing YAML is structurally valid — only labels, descriptions, and customization questions need updating (e.g., "Fix until clean" asks for check command; "Maintain constraints" asks for constraint list)
3. In `skills/create-loop/SKILL.md:48-76`, review Step 1 options: "Fix errors until clean", "Maintain code quality continuously", "Drive a metric toward a target", "Run a sequence of steps", "Harness a skill or prompt", and the three RL types — confirm wording consistently reflects structural patterns and remove any remaining use-case phrasing
4. Ensure Step 0 (template path) and Step 1 (scratch path) present the same structural vocabulary so users who take either path see consistent terminology
5. Verify the wizard end-to-end: template path (Step 0 → 0.1 → 0.2 → 4) and scratch path (Step 1 → 2 → 3 → 4) both produce valid FSM YAML matching the structure in `loops/*.yaml`

## Scope Boundaries

- **In scope**: Reframing wizard template names/descriptions and loop-type question options to use structural pattern language; updating or replacing dated template YAML starters to reflect current FSM structure
- **Out of scope**: Changing the underlying FSM YAML schema or loop execution engine; adding new loop types beyond what already exists; altering the wizard's step count or overall flow structure

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — wizard logic, loop-type question options, and template definitions
- `skills/create-loop/templates.md` — all four pre-built template definitions (separate file, not inline in SKILL.md)

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**templates.md exact current options** (`skills/create-loop/templates.md:8-21`):
- "Python quality (Recommended)" — "Fix lint, type, and format errors for Python projects. Best for: ruff + mypy"
- "JavaScript quality" — "Fix lint and type errors for JS/TS projects. Best for: eslint + tsc"
- "Tests until passing" — "Run tests and fix failures until all pass. Best for: any project with a test suite"
- "Full quality gate" — "Multi-constraint quality gate covering tests, types, and lint. Best for: CI-like validation"

**SKILL.md Step 1 exact current options** (`skills/create-loop/SKILL.md:48-76`):
- "Fix errors until clean (Recommended)" — `fix-until-clean` type → states: evaluate, fix, done
- "Maintain code quality continuously" — `maintain-constraints` type → check/fix pairs + terminal
- "Drive a metric toward a target" — `drive-metric` type → states: measure, apply, done
- "Run a sequence of steps" — `run-sequence` type → step_0…step_N, check_done, done
- "Harness a skill or prompt" — `harness` type → states: discover, execute, check_concrete, check_semantic, check_invariants, advance, done
- Three RL types (bandit, RLHF-style, policy iteration) — already fully structural

**Type-to-YAML mapping** (`SKILL.md:78-86`): maps each label to FSM type string used in generated YAML.

**Template customization** (`templates.md:151-194`): after template selection, Step 0.2 asks for source directory and max iterations, substituting `{{src_dir}}`, `{{max_iterations}}`, `{{test_cmd}}`, `{{type_cmd}}`, `{{lint_cmd}}`, `{{lint_fix_cmd}}` into YAML.

**FSM YAML structure reference**: production loop examples in `loops/*.yaml`; minimal valid structure in `scripts/tests/fixtures/fsm/valid-loop.yaml`. All template YAML starters in `templates.md` are structurally current — only label/description text needs updating.

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
- `/ll:refine-issue` - 2026-03-16T23:38:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46067e65-3dd1-4058-a36b-dc2c5cfbade9.jsonl`
- `/ll:verify-issues` - 2026-03-15T19:32:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:format-issue` - 2026-03-15T19:29:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:confidence-check` - 2026-03-15T20:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e43041b-8ea4-411c-bfcc-e55b7286039c.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a783bed6-ca14-454d-baf2-ee97b0cf2f33.jsonl`
