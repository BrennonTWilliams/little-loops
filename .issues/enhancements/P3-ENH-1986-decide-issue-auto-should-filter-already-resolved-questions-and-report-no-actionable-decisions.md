---
id: ENH-1986
title: 'decide-issue --auto: skip already-RESOLVED questions and emit NO_ACTIONABLE_DECISIONS
  when all questions are resolved'
type: ENH
priority: P3
status: done
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
decision_needed: false
confidence_score: 100
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify (with anchor detail):**
- `skills/decide-issue/SKILL.md` — target section: `## Phase 3b: Inline Decision Scan (AUTO_MODE only)`. Add a resolution-marker pre-filter at the top of this phase before the provisional-language pattern scan (Patterns A/B/C). The NO_ACTIONABLE_DECISIONS path must NOT pass through **Phase 7b** (the `decision_needed: false` frontmatter write via inline `---` block replacement).

**Additional Callers/Importers discovered:**
- `scripts/little_loops/loops/autodev.yaml` — states `decide_current` + `run_decide`: calls `ll-issues check-flag <id> decision_needed` then `/ll:decide-issue <id> --auto`; uses a separate `autodev-decide-ran` flag (ENH-1415) to prevent re-entering the decide path — benefits from NO_ACTIONABLE_DECISIONS without requiring YAML changes
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — state `check_decision_needed`: routes to `done` if `decision_needed=true` without invoking decide-issue; not a direct caller but part of the decision_needed flag ecosystem

**Similar patterns — structured output token routing:**
- `scripts/little_loops/loops/general-task.yaml` state `resume_check` — emits `RESUME_SKIP` token, routed via `evaluate: type: output_contains` + `on_yes: mark_done`; canonical pattern for the NO_ACTIONABLE_DECISIONS token
- `scripts/little_loops/loops/rn-remediate.yaml` states `route_d_implement` → `route_d_decide` → `route_d_wire` — multi-token routing chain on captured shell output; any future loop routing on NO_ACTIONABLE_DECISIONS would add a new link in this chain style

**Tests (concrete model):**
- `scripts/tests/test_decide_issue_skill.py` — class `TestPhase3bInlineProvisionalScan` — exact structural test pattern to model the new `TestPhase3bResolvedFilter` class after (slices skill text between section heading and next `## Phase`, asserts string presence)
- `scripts/tests/test_issues_cli.py` — `test_show_json_includes_decision_needed` — fixture pattern for frontmatter flag tests (write minimal frontmatter + assert `fm.get("decision_needed")`)

## Implementation Steps

1. Edit `skills/decide-issue/SKILL.md`: add Phase 3b resolved-filter before provisional-language scan.
2. Add detection for `✅ RESOLVED` / `✔ RESOLVED` / `**RESOLVED**` prefixes on question items.
3. Add `NO_ACTIONABLE_DECISIONS` structured output block with clear formatting.
4. In `--auto` mode, do not clear `decision_needed` and do not ask interactive questions.
5. Add skill test: issue with all questions marked RESOLVED + `decision_needed: true` → `NO_ACTIONABLE_DECISIONS` output, no file edits.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete anchors per step:**

1. **Step 1**: In `skills/decide-issue/SKILL.md`, the target section heading is `## Phase 3b: Inline Decision Scan (AUTO_MODE only)`. Insert a new subsection `### Phase 3b-i: Skip resolved questions` at the top of this phase. Scope the scan to `## Open Questions` items only (not all sections as the current provisional-language scan does). Observed marker format from FEAT-1809: markers appear inline after the bold question label — e.g., `**Fork vs. flag.** ✅ **RESOLVED** (2026-06-04 by …)`.

2. **Step 2**: The four marker variants to detect: `✅ RESOLVED`, `✔ RESOLVED`, `**RESOLVED**`, `> **RESOLVED**`. Check whether each numbered list item under `## Open Questions` contains any of these markers. If ALL items match (or the section has no items), branch to the NO_ACTIONABLE_DECISIONS path.

3. **Step 3**: The `## RESULT: NO_ACTIONABLE_DECISIONS` block should follow the structural precedent of `ready-issue`'s `## VERDICT` format (`commands/ready-issue.md` § "Output Format"). The NO_ACTIONABLE_DECISIONS path exits before Phase 9's standard report, emitting its own compact block then jumping to Phase 8 (session log append).

4. **Step 4**: Preserving `decision_needed: true` means the NO_ACTIONABLE_DECISIONS path must skip Phase 7b entirely (the `decision_needed: false` frontmatter write). Confirm `rn-remediate.yaml:decide` routes `on_success → re_assess` without inspecting stdout — the NO_ACTIONABLE_DECISIONS token is available for any future loop that adds an `output_contains` evaluator, but no rn-remediate YAML change is required for the fix.

5. **Step 5**: New test class `TestPhase3bResolvedFilter` in `scripts/tests/test_decide_issue_skill.py` — model after `TestPhase3bInlineProvisionalScan` (slice text between section heading and next `## Phase` marker; assert presence of `✅ RESOLVED`, `NO_ACTIONABLE_DECISIONS`; assert `decision_needed: false` write is NOT documented within the new path).

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
- `/ll:confidence-check` - 2026-06-06T22:50:00 - `ce1b46ba-d25e-4957-bdb1-2e1141fe4e66.jsonl`
- `/ll:refine-issue` - 2026-06-06T22:41:04 - `0ca21a34-10fe-4584-bba4-cf168e9b3350.jsonl`
- `/ll:confidence-check` - 2026-06-06T22:34:19 - `ff437ea5-76bb-4629-990d-f8a8924c35be.jsonl`
- `/ll:format-issue` - 2026-06-06T22:29:23 - `c5f213ad-5cfc-4441-bd86-e6da3b6dece1.jsonl`
- `/ll:audit-loop-run` - 2026-06-06 - from run 2026-06-06T220136 (FEAT-1809 / BUG-1985)
