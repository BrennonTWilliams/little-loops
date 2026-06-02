---
captured_at: "2026-04-23T01:03:13Z"
completed_at: "2026-04-23T01:43:57Z"
discovered_date: 2026-04-23
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
status: done
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical clarification**: Step 2c (`skills/review-loop/SKILL.md:215-258`) already exists — added by ENH-662. The implementation is NOT to add a new Step 2c, but to **insert new SR-* sub-steps within the existing Step 2c**, between 2c-2 (~line 238) and 2c-3 (~line 239). The `description:` extraction (2c-1) and happy-path tracing (via the FSM mental model at `SKILL.md:163`) are already in place and reusable.

**SR-* check definition format** (follow exactly from `reference.md:279-306`):
- Section header: `### SR-N: <Title>`
- Three metadata lines: `**Severity**`, `**Breaking**: false`, `**When to auto-apply**: Never`
- Condition description in prose
- `**Finding**: \`<template with \<name\> placeholders>\``
- Optional `**Fix template**` (omit for open-ended recommendations)

**Findings schema** (unchanged from existing checks): `{ check_id: "SR-N", severity: "Warning"|"Suggestion", location: "states.<name>"|(loop)", message: "<text>" }`

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` — add Step 2c Semantic Flow Review phase
- `skills/review-loop/reference.md` — add SR-* check definitions

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/SKILL.md:268,284` — suggests `/ll:review-loop <name>` in success messages after loop creation; soft reference only, no change needed unless review-loop output format changes significantly [Agent 1 finding]

### Similar Patterns
- QC-8 through QC-13 in SKILL.md — existing FSM structural checks to build alongside
- ENH-662 (completed) — prior attempt at FSM logic analysis; read its implementation notes in `thoughts/` if available

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_review_loop.py` — primary test file; add new `TestReviewLoopSemanticChecks` class following the `TestReplaceablePromptStateDetection` pattern (class-level constants, private helpers, positive/negative/exemption test methods per SR-* sub-check) [Agent 3 finding]
- `scripts/tests/fixtures/fsm/semantic-goal-mismatch.yaml` — new fixture: `description: "Fix all lint errors until clean"` but states are named/actioned around issue refinement; exercises SR-1 positive detection [Agent 3 finding]
- `scripts/tests/fixtures/fsm/semantic-incoherent-state.yaml` — new fixture: state named `check_done` with action `"Run the full test suite and report all failures"` (name implies gate, action is broad analysis); exercises SR-2 positive detection [Agent 3 finding]
- `scripts/tests/fixtures/fsm/semantic-backwards-transition.yaml` — new fixture: `on_yes` from `verify` routes back to `analyze` (success → earlier step); exercises SR-3 positive detection [Agent 3 finding]
- `scripts/tests/fixtures/fsm/semantic-goal-gap.yaml` — new fixture: `description` mentions "commit and push" but no state performs git operations; exercises SR-4 positive detection [Agent 3 finding]
- `scripts/tests/fixtures/fsm/semantic-valid-aligned.yaml` — new fixture: well-named loop with `description:`, aligned state names, coherent happy path; clean negative case for all SR-* checks [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — adjacent coverage: tests V-series checks that review-loop Step 2a depends on; verify no breakage [Agent 1 finding]
- `scripts/tests/test_fsm_schema.py` — adjacent coverage: tests FSM schema validation review-loop logic depends on [Agent 1 finding]
- `scripts/little_loops/loops/issue-refinement.yaml` — only existing built-in loop with `description:` field; only YAML suitable for realistic SR-* integration testing without new fixtures; used in parametrized `test_builtin_loops_are_valid` at `test_review_loop.py:187-198` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:504-512` — detailed `/ll:review-loop` entry; describes skill generically without listing check families, so no update required when SR-* is added [Agent 2 finding — verified no change needed]
- `docs/guides/LOOPS_GUIDE.md:2231` — single generic bullet listing review-loop; no check IDs mentioned; no update required [Agent 2 finding — verified no change needed]
- `README.md:165` — command reference table entry; generic; no update required [Agent 2 finding — verified no change needed]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact insertion points:**
- `skills/review-loop/SKILL.md:215-258` — **Step 2c already exists** (added by ENH-662); titled "FSM Flow Review Narrative" with sub-steps 2c-1 (extract intent), 2c-2 (build narrative from FA-* findings), and 2c-3 (output block). New SR-* sub-steps insert between end of 2c-2 (~line 238) and 2c-3 (~line 239).
- `skills/review-loop/SKILL.md:163` — FSM mental model already built here before QC-8 (terminal states, transition map, inbound map, happy path); SR-* checks reuse this directly.
- `skills/review-loop/SKILL.md:389` — Step 6 summary reads "includes V-*, QC-*, and FA-* checks"; needs SR-* appended.
- `skills/review-loop/reference.md:432` — FA-6 ends here; new SR-* check section inserts after this line, following the FA-* entry template from `reference.md:279-306`.
- `skills/review-loop/reference.md:264-267` — FA-* section header declares checks are "performed by LLM reasoning over the parsed YAML, not by the validator"; SR-* should use identical framing.

**Test files (confirmed to exist):**
- `scripts/tests/test_review_loop.py` — primary test file for review-loop skill
- `scripts/tests/fixtures/fsm/valid-loop.yaml` — well-formed reference loop for semantic review testing
- `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml` — tests happy path tracing edge cases
- `scripts/little_loops/loops/issue-refinement.yaml` — complex built-in loop for realistic semantic review testing

**ENH-662 completed issue:**
- `.issues/completed/P3-ENH-662-review-loop-fsm-logic-analysis-and-evaluation.md:165-181` — confirms QC-8 through QC-13 + FA-* are mechanical pattern matches, not open-ended LLM reasoning; this is the exact gap SR-* fills

## Implementation Steps

1. Read the full `skills/review-loop/SKILL.md` and `skills/review-loop/reference.md` to understand existing check structure
2. Add SR-* check definitions to `reference.md` covering: happy-path goal alignment, state coherence, transition semantic appropriateness, and overall goal coverage
3. Add Step 2c to `SKILL.md` that: extracts `description:`, traces happy path, runs SR checks, and emits structured findings
4. Integrate SR findings into the existing findings report format (same severity levels, same output block)
5. Test against 2-3 real loop YAML files and verify output is meaningful and actionable

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. Read `skills/review-loop/SKILL.md:215-258` (existing Step 2c sub-steps 2c-1/2c-2/2c-3) and `skills/review-loop/reference.md:264-432` (FA-* check definitions) — understand exact structure before inserting
2. Add SR-* check section to `reference.md` **after line 432** (after FA-6 entry), following the summary-table-then-detailed-entries pattern from `reference.md:264-432`; declare SR-* as LLM-reasoning checks (same framing as `reference.md:264-267`)
3. Insert SR-* sub-steps into `SKILL.md` **within Step 2c**, between end of 2c-2 (~line 238) and 2c-3 (~line 239); each sub-step follows the QC-8 through QC-13 format from `SKILL.md:163-210`; reuse the FSM mental model already built at `SKILL.md:163`
4. Extend the 2c-3 output block or add a sibling `### Semantic Flow Review:` narrative block that renders SR-* findings — mirrors FA-* "Issues to consider" rendering at `SKILL.md:239-258`
5. Update `SKILL.md:389` Step 6 summary: add `SR-*` to "includes V-*, QC-*, and FA-* checks"
6. Update `SKILL.md:290` Step 3 empty-findings sentinel: `"No V-* or QC-* findings."` — evaluate whether SR-* findings appear in the findings table (if so, update to include SR-*) or only in the narrative block [Agent 2 finding]
7. Update `SKILL.md:293` comment: `"it may surface FA-* findings"` → `"it may surface FA-* and SR-* findings"` [Agent 2 finding]
8. Add an SR-* example row to `reference.md` Findings Display Format section (after FA-6, ~line 435-476) so the display format section is consistent with the new check family [Agent 2 finding]
9. Create semantic test fixtures: `semantic-goal-mismatch.yaml`, `semantic-incoherent-state.yaml`, `semantic-backwards-transition.yaml`, `semantic-goal-gap.yaml`, `semantic-valid-aligned.yaml` in `scripts/tests/fixtures/fsm/` [Agent 3 finding]
10. Add `TestReviewLoopSemanticChecks` class to `scripts/tests/test_review_loop.py` following `TestReplaceablePromptStateDetection` pattern; add SR-1 through SR-4 positive/negative/exemption test methods using inline dict specs [Agent 3 finding]
11. Test against `scripts/tests/fixtures/fsm/valid-loop.yaml` and `scripts/little_loops/loops/issue-refinement.yaml`; verify SR-* output is meaningful and not redundant with existing QC/FA checks
12. Run `python -m pytest scripts/tests/test_review_loop.py -v`

## Scope Boundaries

**In scope:**
- Adding SR-* semantic sub-steps to the existing Step 2c in `skills/review-loop/SKILL.md`
- Adding SR-* check definitions to `skills/review-loop/reference.md`
- Updating Step 6 summary line and Step 3 sentinel/comment to reference SR-* checks
- Creating semantic test fixtures (`semantic-*.yaml`) in `scripts/tests/fixtures/fsm/`
- Adding `TestReviewLoopSemanticChecks` class to `scripts/tests/test_review_loop.py`

**Out of scope:**
- Modifying or replacing existing V-*, QC-*, FA-*, or PR-* checks
- Changing the findings report table format or output structure
- Modifying the `ll-loop validate` structural validator (Step 2a)
- Adding ML/embedding-based analysis — LLM reasoning only
- Changes to loop execution (`ll-loop run`) or other CLI tools

## Impact

- **Priority**: P3 - Improves quality of an existing tool; not blocking
- **Effort**: Medium - Primarily prompt engineering in SKILL.md + reference.md additions
- **Risk**: Low - Additive only; no existing checks removed or changed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Resolution

Added SR-1 through SR-4 semantic flow review checks to `skills/review-loop/SKILL.md` and `skills/review-loop/reference.md`. The existing Step 2c was extended with a new sub-step (2c-3: Semantic Flow Review Checks) that evaluates happy-path goal alignment, state name/action coherence, backwards transitions, and goal coverage gaps. The old 2c-3 (output) was renumbered to 2c-4 and extended with a `### Semantic Flow Review` narrative block. Added 5 fixture files and `TestReviewLoopSemanticChecks` test class (70 tests pass, 0 regressions).

## Status

**Completed** | Created: 2026-04-23 | Completed: 2026-04-23 | Priority: P3

---

## Session Log
- `/ll:ready-issue` - 2026-04-23T01:35:07 - `77489a07-79fc-4f0a-bec9-1978a232c91a.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `fb66d5fa-1e18-4297-b9a0-84c7a6347716.jsonl`
- `/ll:refine-issue` - 2026-04-23T01:26:23 - `0dfab9de-bfbe-4be1-83f9-5e81ba5e7259.jsonl`
- `/ll:wire-issue` - 2026-04-22T00:00:00
- `/ll:capture-issue` - 2026-04-23T01:03:13Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf5a7c2d-7f8f-4698-a4df-06642c6487ba.jsonl`
- `/ll:manage-issue` - 2026-04-23T01:43:57Z - `fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
