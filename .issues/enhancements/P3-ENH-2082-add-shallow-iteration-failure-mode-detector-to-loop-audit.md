---
id: ENH-2082
title: Add shallow-iteration failure mode detector to loop audit
type: ENH
priority: P3
status: done
captured_at: '2026-06-10T18:12:09Z'
completed_at: '2026-06-11T04:00:47Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 93
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2082: Add shallow-iteration failure mode detector to loop audit

## Summary

`ll:audit-loop-run` has no detector for the shallow-iteration failure mode: runs that burn a high tool-call budget without accumulating stable helper artifacts. This enhancement adds a heuristic that flags such runs as `shallow-iteration` warnings, cross-references corroborating `diff_stall` verdicts, and documents the pattern in the harness optimization guide alongside `feature-stubbing`.

## Current Behavior

`ll:audit-loop-run` detects phantom convergence, feature-stubbing, rubric drift, and sub-loop verdict laundering. It has no detector for shallow-iteration: a run that exceeds a high tool-call count but creates or modifies no helper files outside the primary artifact path. These runs are reported only as generic token-budget exhaustion at best, masking the root cause.

## Expected Behavior

When a loop run exceeds a configurable tool-call threshold (default: 30) without creating or modifying files outside the primary artifact path, `ll:audit-loop-run` emits a `shallow-iteration` warning in its audit output. When a `diff_stall` evaluator verdict is also present, the warning is upgraded to a corroborated finding. The pattern and its remediation are documented in `HARNESS_OPTIMIZATION_GUIDE.md` under the failure-mode taxonomy alongside `feature-stubbing`.

## Motivation

A common failure pattern in loop runs is high tool-call counts without accumulating reusable structure — the loop iterates shallowly without building stable primitives, burning token budget without progress. This is a more specific diagnostic than the existing `feature-stubbing` taxonomy and has a concrete detectable signal. Without it, users see only "budget exhausted" rather than "the loop was not building anything."

## Proposed Solution

Add a heuristic to `ll:audit-loop-run` that flags runs where the tool-call count exceeds a threshold (e.g., >30) but no new helper files were created or modified outside the primary artifact path. Report this as a `shallow-iteration` warning in the audit output. Cross-reference with `diff_stall` evaluator verdicts as a corroborating signal. Document the pattern in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` under the failure mode taxonomy alongside feature-stubbing.

## Implementation Steps

1. Add `shallow-iteration` detection heuristic to `ll:audit-loop-run`
2. Implement threshold check: tool-call count > 30 with no helper file creates/modifies outside primary artifact path
3. Cross-reference with `diff_stall` evaluator verdicts to emit corroborated warnings
4. Report `shallow-iteration` warning in audit output with remediation suggestion
5. Document pattern in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` under failure mode taxonomy

## Scope Boundaries

- Does not change loop execution behavior — detection is post-hoc in audit output only
- Does not auto-remediate or halt shallow-iteration loops during a run
- Does not add new FSM evaluator types; no changes to `diff_stall` evaluator itself
- Does not cover shallow iteration in loops not captured by `ll:audit-loop-run` (e.g., live runs)

## Acceptance Criteria

- [ ] `ll:audit-loop-run` emits `shallow-iteration` warning when tool-call count exceeds threshold without auxiliary file changes
- [ ] Warning cross-references `diff_stall` verdict when present
- [ ] `HARNESS_OPTIMIZATION_GUIDE.md` documents `shallow-iteration` alongside `feature-stubbing`
- [ ] Threshold is configurable or clearly documented

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — add shallow-iteration detection step and warning format
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document `shallow-iteration` under failure-mode taxonomy

### Dependent Files (Callers/Importers)
- N/A — `audit-loop-run` is a user-facing skill, not imported by automation code

### Similar Patterns
- `feature-stubbing` detection in `skills/audit-loop-run/SKILL.md` — follow same warning structure and corroboration pattern

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` — add test case for shallow-iteration detection

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — new subsection under failure-mode taxonomy

### Configuration
- Threshold default (30 tool calls) should be documented in the skill; no config file change required

## Impact

- **Priority**: P3 — Diagnostic gap; does not block existing loop functionality; improves observability
- **Effort**: Small — Additive heuristic check in an existing skill; no new infrastructure or evaluator types
- **Risk**: Low — Additive change to audit output only; no behavioral changes to loop execution or FSM
- **Breaking Change**: No

## Labels

`enhancement`, `loop-audit`, `observability`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-11T03:54:08 - `3ddf2422-577e-4dfc-8b7c-0d181fb69d87.jsonl`
- `/ll:ready-issue` - 2026-06-11T03:31:56 - `51051097-4e84-426b-80d7-3a69806057f7.jsonl`
- `/ll:format-issue` - 2026-06-10T23:31:49 - `20d6c357-b807-4649-87f0-e98fb94ab6bf.jsonl`
- `/ll:confidence-check` - 2026-06-10T23:45:00 - `ecb359fa-11ce-4856-8a5d-fc9e0f7af230.jsonl`
- `/ll:confidence-check` - 2026-06-10T18:00:00 - `793b5ac4-6dc4-4790-8fa0-31f200928ece.jsonl`
