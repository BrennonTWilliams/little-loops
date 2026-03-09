---
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-662: review-loop FSM Logic Analysis and Evaluation

## Summary

`/ll:review-loop` currently performs structural validation (format, field correctness, QC checks) but provides no analysis or evaluation of the Finite State Machine's logic and flow. Add an FSM logic analysis phase that evaluates whether the states, transitions, and overall flow make sense given the loop's declared purpose.

## Current Behavior

`/ll:review-loop` runs quality checks (QC-1 through QC-7) that validate structural correctness — `max_iterations` bounds, `on_error` routing, `action_type` alignment, hardcoded paths, `on_handoff` presence, etc. These checks are binary pass/fail tests.

For a well-formed loop like `issue-refinement-git`, the output is:

```
Findings: 0 error(s), 0 warning(s), 0 suggestion(s)
✓ Loop passes validation.
```

There is no analysis of whether the FSM logic is correct or well-designed: no evaluation of state purpose, no assessment of transition logic, no detection of spin loops, no identification of missing terminal states, and no commentary on the overall flow coherence relative to the loop's declared objective.

## Expected Behavior

After passing structural validation, `/ll:review-loop` performs an FSM Flow Review that:

1. **Reads the loop's declared purpose** from the `description:` field (or equivalent) in the YAML
2. **Traces the happy path** — the primary flow through the states — and evaluates whether it correctly achieves the loop's purpose
3. **Evaluates each state** — is it logically well-scoped? Does it do one clear thing? Is the action type appropriate?
4. **Evaluates each transition** — is the routing logical? Are edge cases handled? Are transitions complete (all outputs routed)?
5. **Evaluates the whole FSM** — are there spin risks? Missing terminal states? Fragile state (e.g., un-reset `/tmp` counters)? Overly monolithic states? Off-by-one risks in loops?
6. **Summarizes strengths** and issues, with concrete actionable suggestions for problems found

Example output structure:

```
FSM Flow Review: issue-refinement-git.yaml

  Overall flow is logically sound. The loop correctly implements: evaluate → fix → maybe-commit → repeat.

  What works well
  - evaluate → done/fix split is clean: exits only when all issues pass
  - on_partial → evaluate is a sensible retry for ambiguous LLM output
  - ceiling-acceptance in fix (5 refinements, ready≥85) prevents infinite loops

  Issues to consider
  1. /tmp counter never resets (fragile) — persists across restarts
  2. Spin risk on evaluate errors — both on_partial and on_error loop back
  3. No explicit failure terminal — max_iterations just stops silently
```

## Acceptance Criteria

- [ ] Running `/ll:review-loop` on a valid loop produces an "FSM Flow Review" section after structural QC
- [ ] The FSM Flow Review includes a happy path trace that evaluates whether the flow matches the loop's declared `description:`
- [ ] Loops with spin risks (all error/partial transitions loop back to same state without escape) produce a Warning or Error finding
- [ ] Loops missing an explicit failure terminal state produce a Warning finding
- [ ] The FSM analysis output includes "What works well" and "Issues to consider" subsections
- [ ] The findings count (errors/warnings/suggestions) at the top reflects findings from both structural QC and FSM analysis phases

## Motivation

The current review checks structural validity but misses the most important question: *does this FSM actually work correctly?* A loop can pass all QC checks and still have logical bugs — spin risks, missing failure paths, fragile shared state, or a flow that doesn't match its stated purpose. These are the bugs that cause real problems at runtime (loops running to max_iterations silently, /tmp state corruption across restarts, LLM errors causing infinite retries). The FSM analysis phase adds genuine quality assessment to what is currently only a linting tool.

## Proposed Solution

Add a new phase to the `review-loop` skill AFTER structural validation. The phase should:

1. Extract the loop's `description:` field to understand intent
2. Build a mental model of the FSM: states, transitions, terminal states, initial state
3. Trace the primary (happy) path and evaluate it against the declared purpose
4. Run heuristic checks for known FSM anti-patterns:
   - **Spin detection**: states where all error/partial transitions loop back to the same state without a counter escape
   - **Missing failure terminal**: loops with no `failed`/`error` terminal state that just hit `max_iterations`
   - **Unresetting shared state**: `/tmp` files or counters written but never reset at loop start
   - **Monolithic prompt states**: single prompt states with multi-step A→B→C instructions that would benefit from decomposition
   - **Unreachable states**: states that no transition points to
   - **Dead-end states**: non-terminal states with no outbound transitions
5. Report findings using the same Error/Warning/Suggestion severity taxonomy as existing QC checks
6. Summarize with "What works well" and "Issues to consider" sections

The analysis is done by Claude (LLM reasoning over the YAML), not rule-based code. The skill should instruct Claude to reason carefully about the FSM structure and apply the heuristics above.

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` — add FSM Flow Review phase (Step 2c) between Step 2b and Step 3; insert between lines ~156-159 where QC checks end and display begins
- `skills/review-loop/reference.md` — add FA-* check definitions (FA-1 through FA-6 for the six anti-patterns) to the quality check catalog; add FSM Flow Review display format alongside existing findings table format

### Dependent Files (Callers/Importers)
- N/A (skill is invoked directly by users)

### Similar Patterns
- Existing QC checks in `skills/review-loop/SKILL.md:112-156` and `reference.md:43-255` for taxonomy/format consistency (findings structure: `{ check_id, severity, location, message }`)
- `skills/create-loop/SKILL.md` for understanding loop author intent and the `description:` field conventions
- QC-2 (`reference.md:67-99`) for the pattern of iterating states and recording findings — the FSM analysis phase should follow the same append-to-findings pattern

### Tests
- Manual test: `/ll:review-loop issue-refinement-git` — should flag `/tmp/issue-refinement-commit-count` counter in `check_commit` state as fragile shared state (written but never reset), and note no explicit failure terminal
- Manual test: `/ll:review-loop fix-quality-and-tests` — should flag `fix-quality` and `fix-tests` as having no explicit `on_error`, and note only `done` (success) terminal — no failure terminal
- Manual test: a well-formed loop (e.g., one created from scratch via `/ll:create-loop`) to confirm "What works well" populates

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`description:` field format discrepancy**: `issue-refinement-git.yaml` uses YAML comments at the top (no `description:` key), while `fix-quality-and-tests.yaml` uses a proper `description:` key (`loops/fix-quality-and-tests.yaml:3`). The FSM analysis phase must handle both: check for `description:` YAML key first, fall back to parsing top comments if absent.

**Exact insertion point**: Step 2c belongs after `SKILL.md:156` (end of QC-7) and before `SKILL.md:159` (Step 3: Display findings header). The new step appends to the same shared findings list used by Step 3's display logic.

**Real anti-pattern examples in test loops**:
- `issue-refinement-git.yaml:66-70` (`check_commit` state): writes `/tmp/issue-refinement-commit-count` but no reset state exists — concrete `/tmp` fragile state example
- `issue-refinement-git.yaml` has no failure terminal — `max_iterations: 100` just stops silently
- `fix-quality-and-tests.yaml`: `fix-quality` and `fix-tests` states lack `on_error` routing (`fix-quality:23`, `fix-tests:54`), caught by QC-2 but also affects FSM logic analysis
- `issue-refinement-git.yaml:31,80` — `on_error: evaluate` in both `evaluate` and `check_commit` states loops back without escape, meeting spin risk criteria

**Findings list structure** (from `SKILL.md:104`): each finding is `{ check_id, severity, location, message }` — FA-* check IDs follow QC-* pattern

## Implementation Steps

1. Read `skills/review-loop/SKILL.md:91-192` to understand QC check structure and findings list format before writing Step 2c
2. Read `skills/review-loop/reference.md:43-284` for the existing check definitions and display format to model FA-* check entries after
3. Design the six FA-* heuristic checks in `reference.md` (after QC-7 at ~line 255): FA-1 spin detection, FA-2 missing failure terminal, FA-3 unresetting `/tmp` shared state, FA-4 monolithic prompt state, FA-5 unreachable states (overlap with V-11 — skip if V-11 already caught it), FA-6 dead-end non-terminal states
4. Add Step 2c to `SKILL.md` after line 156: insert the FSM Flow Review phase — read `description:` (YAML key or comment fallback), trace happy path, run FA-1 through FA-6 checks, build "What works well" and "Issues to consider" lists, append findings to shared list
5. Update `reference.md` display format section (~line 259) to include the "What works well" / "Issues to consider" narrative block after the findings table
6. Test with `issue-refinement-git` (expect: FA-3 fragile counter + missing failure terminal) and `fix-quality-and-tests` (expect: no failure terminal)
7. Verify total findings count in Step 6 summary includes FA-* findings alongside V-* and QC-* findings

## Scope Boundaries

- **In scope**: FSM logic analysis based on LLM reasoning over YAML structure and declared purpose
- **Out of scope**: Automated fixing of FSM logic issues (analysis only, user applies fixes)
- **Out of scope**: Running the loop to validate it empirically (static analysis only)
- **Out of scope**: Adding new structural QC checks (ENH-631 covers test coverage)

## Impact

- **Priority**: P3 - This is the core value proposition of a loop reviewer; without logic analysis, the tool is incomplete
- **Effort**: Small — the skill already has the right structure; this adds a new analysis phase with LLM reasoning instructions
- **Risk**: Low — additive change, does not modify existing QC checks
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop design patterns |
| `.claude/CLAUDE.md` | Skill development conventions |

## Labels

`enhancement`, `review-loop`, `fsm`, `captured`

## Resolution

**Status**: Completed
**Completed**: 2026-03-09
**Implementation**: Additive — added Step 2c (FSM Flow Review) to `skills/review-loop/SKILL.md` and FA-1 through FA-6 check definitions to `skills/review-loop/reference.md`.

### Changes Made

- `skills/review-loop/SKILL.md`: Added Step 2c between Step 2b (QC-7) and Step 3. Step 2c extracts intent from `description:` or YAML comments, traces the happy path, runs FA-1 through FA-6 anti-pattern checks (appending to the shared findings list), builds "What works well" / "Issues to consider" narrative, and outputs the FSM Flow Review block after the findings table.
- `skills/review-loop/reference.md`: Added FA-* check definitions table and detailed entries for FA-1 (spin detection), FA-2 (missing failure terminal), FA-3 (unresetting `/tmp` state), FA-4 (monolithic prompt state), FA-5 (unreachable states, deduped with V-11), FA-6 (dead-end non-terminal states). Updated Findings Display Format to include FSM Flow Review narrative block.

### Acceptance Criteria Verification

- [x] FSM Flow Review section appears after structural QC — Step 2c runs after Step 2b
- [x] Happy path trace evaluates flow against `description:` — Step 2c-3
- [x] Spin risks (FA-1) produce Warning finding
- [x] Missing failure terminal (FA-2) produces Warning finding
- [x] Output includes "What works well" and "Issues to consider" — Step 2c-5 and 2c-6
- [x] Findings count includes FA-* findings — Step 6 summary clarified

## Session Log

- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1a61db5-bf6d-401c-a25e-1b0f6a9507c0.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cd5c8d9-049c-4f5a-bc07-8ebea05c1e60.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8903ae37-9a16-44a8-a4b8-083839c5ad9d.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/339453a3-a63e-483d-9c90-18ccd2e99a4e.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/308f838f-9817-4318-ba85-59074f83f806.jsonl`
- `/ll:manage-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current-session.jsonl`

---

**Completed** | Created: 2026-03-09 | Priority: P3
