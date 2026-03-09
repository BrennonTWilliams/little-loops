---
discovered_date: 2026-03-09
discovered_by: capture-issue
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
- `skills/review-loop/SKILL.md` — add FSM Flow Review phase with analysis instructions and output format

### Dependent Files (Callers/Importers)
- N/A (skill is invoked directly by users)

### Similar Patterns
- Existing QC checks in `skills/review-loop/SKILL.md` for taxonomy/format consistency
- `skills/create-loop/SKILL.md` for understanding what loop authors intend

### Tests
- Manual test: run `/ll:review-loop issue-refinement-git` and verify FSM analysis section appears
- Manual test: run on a loop with known spin risk to verify detection

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read `skills/review-loop/SKILL.md` to understand the current review flow and QC structure
2. Design the FSM Flow Review phase — define the analysis instructions, heuristics, and output format
3. Add the FSM Flow Review phase to `SKILL.md` after existing QC checks
4. Define the "What works well" / "Issues to consider" output format
5. Test with `issue-refinement-git` and at least one other loop to verify quality of analysis
6. Verify existing structural QC still passes correctly and findings count reflects both phases

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

## Session Log

- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1a61db5-bf6d-401c-a25e-1b0f6a9507c0.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cd5c8d9-049c-4f5a-bc07-8ebea05c1e60.jsonl`

---

**Open** | Created: 2026-03-09 | Priority: P3
