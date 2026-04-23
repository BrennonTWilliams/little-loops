---
captured_at: "2026-04-23T01:03:13Z"
discovered_date: 2026-04-23
discovered_by: capture-issue
---

# ENH-1265: Deepen review-loop Logical Flow and Goal-Alignment Analysis

## Summary

`/ll:review-loop` analysis is too narrowly focused on structural validation and error/termination state checks. It does not evaluate whether the loop's states and transitions make semantic sense relative to the loop's declared purpose, nor does it assess whether the overall flow coherently accomplishes the stated goal. Refactor the skill to add a semantic/goal-alignment analysis phase.

## Current Behavior

`/ll:review-loop` runs two phases:

1. **First-pass validation** (`ll-loop validate`) — structural correctness (field types, required keys, schema compliance)
2. **Quality checks QC-1 through QC-13** — mechanical checks for `max_iterations` range, missing `on_error` routing, action type mismatches, spin detection, shared state cleanup, unreachable states, etc.

QC-8 through QC-13 touch FSM structure (spin risks, unreachable states, dead-ends) but are still mechanical pattern matches — they do not reason about what the loop is *supposed* to do. There is no analysis of:

- Whether the state names/actions align with the loop's `description:` field
- Whether the happy path actually achieves the declared goal
- Whether individual states have clear, well-scoped purposes
- Whether transitions represent semantically correct routing decisions
- Whether the loop could achieve its goal more simply or reliably

Prior work: ENH-662 was captured and marked complete, but its implementation landed as structural checks (QC-8 through QC-13) rather than semantic/goal-oriented analysis. This issue addresses the remaining gap.

## Expected Behavior

After existing QC checks pass (or alongside them), `/ll:review-loop` performs a **Semantic Flow Review** phase that:

1. **Reads the loop's declared purpose** from the `description:` field
2. **Maps the happy path** — traces `on_yes`/`next` from `initial` to terminal — and evaluates whether it semantically achieves the declared purpose
3. **Evaluates state coherence** — does each state do one clear, well-named thing? Is the `action` text appropriate for the `action_type`? Do state names reflect their actual role?
4. **Evaluates transition logic** — are routing decisions (`on_yes`, `on_no`, `on_partial`, `on_error`) semantically appropriate? Would a reader understand why each branch routes where it does?
5. **Evaluates overall goal alignment** — does the FSM as a whole reliably accomplish the declared goal, or are there gaps, dead-ends, or detours that undermine it?
6. **Highlights strengths** as well as weaknesses — not just a list of problems
7. **Produces actionable suggestions** for any weaknesses, not just flags

Example output addition:

```
### Semantic Flow Review

**Loop goal**: "Refine open issues with codebase context until all sections are populated"

**Happy path**: start → analyze_issue → check_completeness → finalize → done
  ✓ Path is coherent and achieves the stated goal.

**State analysis**:
  ✓ `analyze_issue` — clear single-responsibility state; action text matches goal
  ⚠ `check_completeness` — action prompt asks LLM to "check if done" but doesn't specify *what* "done" means; risks inconsistent verdicts across runs
  ✓ `finalize` — well-scoped terminal prep state

**Transition analysis**:
  ✓ on_yes from check_completeness → finalize is semantically correct
  ⚠ on_no from check_completeness → analyze_issue could spin without a counter; consider a dedicated retry counter or escalation path

**Goal alignment**: Mostly aligned. Primary risk is the ambiguous completeness criterion in `check_completeness`.
```

## Motivation

The loop review tool is most useful when it catches design problems that a structural linter cannot. Most real loop bugs are semantic — a state that does too much, transitions that route incorrectly, or a happy path that doesn't actually accomplish the goal. The current implementation misses all of these. Users get a false sense of confidence from a clean structural review when the loop's logic is still flawed.

## Proposed Solution

Add a **Step 2c: Semantic Flow Review** phase to `skills/review-loop/SKILL.md`, positioned after QC-13. The phase uses the LLM (Claude) to reason about the loop semantically:

1. Extract `description:` from the YAML as the declared goal
2. Trace the happy path (already computed for QC-12)
3. For each state and transition on/near the happy path, assess semantic coherence against the goal
4. Produce structured findings with severity (`Info`/`Suggestion`/`Warning`) and concrete recommendations

The semantic review should be integrated into the same findings report, with its own section header and check IDs (e.g., `SR-1` through `SR-N`).

Reference `reference.md` to see if any existing check definitions can be extended rather than duplicated.

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` — add Step 2c Semantic Flow Review phase
- `skills/review-loop/reference.md` — add SR-* check definitions

### Dependent Files (Callers/Importers)
- No callers — skill is invoked directly by users

### Similar Patterns
- QC-8 through QC-13 in SKILL.md — existing FSM structural checks to build alongside
- ENH-662 (completed) — prior attempt at FSM logic analysis; read its implementation notes in `thoughts/` if available

### Tests
- TBD — check if `scripts/tests/` has review-loop test fixtures; add semantic review test cases

### Documentation
- `docs/` — check for any review-loop documentation to update

### Configuration
- N/A

## Implementation Steps

1. Read the full `skills/review-loop/SKILL.md` and `skills/review-loop/reference.md` to understand existing check structure
2. Add SR-* check definitions to `reference.md` covering: happy-path goal alignment, state coherence, transition semantic appropriateness, and overall goal coverage
3. Add Step 2c to `SKILL.md` that: extracts `description:`, traces happy path, runs SR checks, and emits structured findings
4. Integrate SR findings into the existing findings report format (same severity levels, same output block)
5. Test against 2-3 real loop YAML files and verify output is meaningful and actionable

## Impact

- **Priority**: P3 - Improves quality of an existing tool; not blocking
- **Effort**: Medium - Primarily prompt engineering in SKILL.md + reference.md additions
- **Risk**: Low - Additive only; no existing checks removed or changed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Status

**Open** | Created: 2026-04-23 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-04-23T01:03:13Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf5a7c2d-7f8f-4698-a4df-06642c6487ba.jsonl`
