---
id: ENH-1986
title: 'decide-issue --auto: skip already-RESOLVED questions and emit NO_ACTIONABLE_DECISIONS
  when all questions are resolved'
type: ENH
priority: P3
status: open
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
decision_needed: false
confidence_score: 92
outcome_confidence: 85
score_complexity: 23
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
relates_to:
- BUG-1416
- BUG-1985
labels:
- decide-issue
- skill-improvement
---

# ENH-1986: decide-issue --auto skip already-RESOLVED questions

## Summary

`/ll:decide-issue --auto` currently scans all open questions including those already marked `✅ RESOLVED` or `✔ RESOLVED`. In run `2026-06-06T220136`, it spent 112s (a full LLM session) "resolving" the fork-vs-flag question in FEAT-1809 that had been marked `✅ RESOLVED (2026-06-04)` — editing stale provisional language while the actual blocking question (Q2: combined cap) remained untouched. The call should skip resolved questions in Phase 3b and emit a structured `NO_ACTIONABLE_DECISIONS` signal when every question in the issue is already resolved.

## Current Behavior

Phase 3 of `skills/decide-issue/SKILL.md` scans `## Open Questions` and `## Proposed Solution` for provisional language without filtering by resolution status. A question marked `✅ RESOLVED` is indistinguishable from an open question to the scanner, so the skill performs edit work on already-resolved items and reports success — leaving `decision_needed: false` even though the real blocking question was untouched.

## Expected Behavior

1. Phase 3b should prefix-check each question for `✅ RESOLVED`, `✔ RESOLVED`, or `**RESOLVED**` markers before treating it as a candidate for resolution.
2. If all questions are already marked resolved (or there are no questions) and `decision_needed: true`, the skill should:
   - Emit a structured `## RESULT: NO_ACTIONABLE_DECISIONS` block to stdout
   - NOT edit the issue
   - Leave `decision_needed: true` intact (the human set it; automation cannot clear a flag it didn't earn)
3. In `--auto` mode, exit 0 with the `NO_ACTIONABLE_DECISIONS` block so the calling loop can detect the condition.

## Motivation

Without this filter, the `rn-remediate` loop's `decide → re_assess` cycle can:
1. Call `decide-issue` on an issue where all formal questions are RESOLVED
2. `decide-issue` edits stale language, clears `decision_needed: false`
3. `re_assess` re-detects a genuine unresolved open question with no formal options and re-sets `decision_needed: true`
4. Scores don't improve → `CONVERGED_STALLED` → decompose (see BUG-1985)

An early `NO_ACTIONABLE_DECISIONS` exit skips the stale-edit LLM call and gives the loop a signal it can route on, potentially routing to human escalation directly.

## Proposed Solution

In `skills/decide-issue/SKILL.md`, Phase 3b, before the provisional-language scan:

```markdown
### Phase 3b: Filter resolved questions

Before scanning for provisional language, collect all `## Open Questions` items and
check each for resolution markers:
- `✅ RESOLVED`, `✔ RESOLVED`, `**RESOLVED**`, or `> **RESOLVED**` at the start of the item body

If ALL items are resolved (or the section has no items), and `decision_needed: true` is set:
- Output: `## RESULT: NO_ACTIONABLE_DECISIONS — all questions already marked resolved`
- Do NOT edit the issue file
- Exit 0 (in --auto mode the loop reads this token; in interactive mode inform the user)

Otherwise, proceed to scan only UNRESOLVED items for provisional language.
```

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — add Phase 3b resolved-filter before provisional-language scan

### Dependent Files (Callers/Importers)
- `loops/rn-remediate.yaml` — calls `decide-issue --auto` in the `decide → re_assess` cycle; benefits from `NO_ACTIONABLE_DECISIONS` routing
- Any loop that invokes `/ll:decide-issue --auto` as an FSM state action

### Similar Patterns
- `skills/ready-issue/SKILL.md` — similar "check and emit structured signal" pattern for early-exit on already-compliant issues

### Tests
- Add skill test: issue with all questions marked RESOLVED + `decision_needed: true` → `NO_ACTIONABLE_DECISIONS` output, no file edits

### Documentation
- N/A — no docs reference `decide-issue` Phase 3 internals

### Configuration
- N/A

## Implementation Steps

1. Edit `skills/decide-issue/SKILL.md`: add Phase 3b resolved-filter before provisional-language scan.
2. Add detection for `✅ RESOLVED` / `✔ RESOLVED` / `**RESOLVED**` prefixes on question items.
3. Add `NO_ACTIONABLE_DECISIONS` structured output block with clear formatting.
4. In `--auto` mode, do not clear `decision_needed` and do not ask interactive questions.
5. Add skill test: issue with all questions marked RESOLVED + `decision_needed: true` → `NO_ACTIONABLE_DECISIONS` output, no file edits.

## Scope Boundaries

- **In scope**: Phase 3b resolved-question filter in `decide-issue`; `NO_ACTIONABLE_DECISIONS` structured output in `--auto` mode; preserving `decision_needed: true` when automation cannot clear it
- **Out of scope**: Changing interactive-mode behavior (interactive mode informs user but still exits without editing); modifying calling loops (loops can optionally route on the `NO_ACTIONABLE_DECISIONS` token but no loop YAML changes are required); changes to other skills

## Impact

- **Priority**: P3 — quality improvement; reduces wasted LLM calls and stale-edit confusion
- **Effort**: Small — skill text edit only, no YAML loop changes
- **Risk**: Low — additive filter before existing logic; no existing paths change
- **Breaking Change**: No
- **Blast radius**: Any `decide-issue --auto` call on an issue whose open questions are all RESOLVED

## Session Log
- `/ll:confidence-check` - 2026-06-06T22:34:19 - `ff437ea5-76bb-4629-990d-f8a8924c35be.jsonl`
- `/ll:format-issue` - 2026-06-06T22:29:23 - `c5f213ad-5cfc-4441-bd86-e6da3b6dece1.jsonl`
- `/ll:audit-loop-run` - 2026-06-06 - from run 2026-06-06T220136 (FEAT-1809 / BUG-1985)
