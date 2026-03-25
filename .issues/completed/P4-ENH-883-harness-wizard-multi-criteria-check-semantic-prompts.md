---
id: ENH-883
type: ENH
priority: P4
status: completed
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# ENH-883: Harness wizard should generate multi-criteria `check_semantic` evaluation prompts

## Summary

The harness wizard's `check_semantic` (LLM-as-judge) evaluation path generates a single vague binary YES/NO prompt auto-derived from the skill description. This enhancement adds a two-question follow-up in wizard Step H3 to collect success and failure criteria from the user, then generates a numbered multi-criteria evaluation prompt—producing measurably better LLM judge outputs as validated by Anthropic's harness design research.

## Current Behavior

When the user selects LLM-as-judge evaluation in the wizard, a single YES/NO prompt is auto-derived from the skill description with no user input:

```yaml
evaluate:
  prompt: >
    Did the previous action successfully complete the code quality check?
    Answer YES or NO with brief rationale.
```

## Expected Behavior

When LLM-as-judge is selected in Step H3, the wizard asks two follow-up questions ("What should change after the skill runs successfully?" and "What would indicate failure?") and generates a numbered multi-criteria prompt:

```yaml
evaluate:
  prompt: >
    Evaluate the previous action on these criteria:
    1. [criterion from "what should change"]
    2. Absence of failure signals: [criterion from "what indicates failure"]
    Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
```

## Motivation

The harness wizard generates a single YES/NO `check_semantic` evaluation prompt auto-derived from the skill description:

```yaml
evaluate:
  prompt: >
    Did the previous action successfully complete the code quality check?
    Answer YES or NO with brief rationale.
```

Anthropic's harness design research found that **specific, structured multi-criteria evaluation prompts produce significantly better quality judgments** than binary YES/NO questions. Specific language within the criteria also steers model outputs toward better results. A single vague question gives the evaluator minimal signal.

Example of a stronger prompt:

```yaml
evaluate:
  prompt: >
    Evaluate the previous action on these criteria:
    1. Content updated: Was the issue file meaningfully changed with new information?
    2. Research quality: Are claims grounded in specific codebase evidence?
    3. Completeness: Were all required sections addressed?
    Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
```

## Implementation Steps

> **Note**: The issue originally referenced "Step H2" but the relevant wizard step is **Step H3** (Evaluation Phases) at `skills/create-loop/loop-types.md:603`. Step H2 is "Work Item Discovery". The "What does done look like?" question currently exists only in the Custom prompt path (`loop-types.md:575`).

1. **Add follow-up sub-questions in Step H3** — insert after the Skill-based follow-up block at `skills/create-loop/loop-types.md:641-645` (before the "Default selection" note at line 647):

   ```
   **If "LLM-as-judge" is selected**, ask (single AskUserQuestion with two questions, following the pattern in Step H4 at loop-types.md:651-676):
   - "What should be different in the output after the skill runs successfully?"
   - "What would indicate the skill failed or made no progress?"
   ```

2. **Update the prompt template in both YAML variants** — replace the `<auto-derived>` placeholder:
   - Variant A (`loop-types.md:733`): Replace the single-question `prompt:` with a numbered multi-criteria block using the two answers from Step H3
   - Variant B (`loop-types.md:806`): Same replacement

3. **For skill catalog selections** (not custom prompts), pre-populate the sub-questions with suggested criteria derived from the selected skill's SKILL.md description (already read at `loop-types.md:558`). The description string currently feeds into `<skill-description>` — extend this to suggest criterion wording as option labels/descriptions in the AskUserQuestion.

4. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`**:
   - Lines 219-233: Replace single-criterion example prompt with multi-criteria numbered format
   - Lines ~448-457 and ~511-520: Update the Variant A and B worked example YAML blocks
   - Line ~598: Update the `check_semantic.evaluate.prompt` customization tip to mention multi-criteria format

5. **Update built-in example harness files**:
   - `loops/harness-single-shot.yaml:123-126` — Reformat three-condition prose prompt to numbered multi-criteria list
   - `loops/harness-multi-item.yaml:148-151` — Same

## API/Interface

Wizard Step H2 change — additional sub-questions when `check_semantic` is selected:

```
You selected LLM-as-judge evaluation. Help define the criteria:

What should change after the skill runs successfully?
> [user input]

What would indicate the skill failed or made no progress?
> [user input]
```

Generated prompt:

```yaml
evaluate:
  prompt: >
    Evaluate the previous action on these criteria:
    1. [criterion from "what should change"]
    2. Absence of failure signals: [criterion from "what indicates failure"]
    Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
```

## Integration Map

### Files to Modify

- `skills/create-loop/loop-types.md:641-645` — Step H3: Insert follow-up AskUserQuestion block after Skill-based follow-up (before "Default selection" note at line 647); mirror the Skill-based follow-up pattern at lines 641–645 and the H4 two-question AskUserQuestion structure at lines 651–676
- `skills/create-loop/loop-types.md:733` — Variant A `check_semantic` template: Replace `<auto-derived>` placeholder with multi-criteria numbered format using user answers
- `skills/create-loop/loop-types.md:806` — Variant B `check_semantic` template: Same replacement
- `skills/create-loop/loop-types.md:575` — Custom prompt path: Extend "What does 'done' look like?" to also use the two-question format for consistency
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:219-233` — Update LLM-as-Judge section example prompt
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:~448-457` — Update Variant A worked example
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:~511-520` — Update Variant B worked example
- `loops/harness-single-shot.yaml:123-126` — Update example `check_semantic` prompt (three-condition prose → numbered list)
- `loops/harness-multi-item.yaml:148-151` — Update example `check_semantic` prompt (three-condition prose → numbered list)

### Dependent Files (Read-Only / Context)

- `skills/create-loop/loop-types.md:556-558` — Skill description reading in Step H1; description string is the source for pre-populated criteria suggestions
- `skills/create-loop/loop-types.md:636-659` — Step H4 multi-question AskUserQuestion pattern to follow for the new H3 follow-up
- `scripts/little_loops/fsm/schema.py:56-79` — `EvaluateConfig.prompt` accepts any string; no schema changes needed
- `scripts/little_loops/fsm/evaluators.py:528-563` — `evaluate_llm_structured()` uses prompt string as-is; multi-criteria format requires no evaluator changes

### Tests

- `scripts/tests/test_create_loop.py` — Tests for the wizard flow; may need cases for the new H3 LLM-as-judge follow-up
- `scripts/tests/test_fsm_evaluators.py:550` — `TestLLMStructuredEvaluator`; multi-criteria prompts are structurally compatible, no evaluator test changes required

### Documentation

- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Primary doc; LLM-as-judge section and worked examples need updating
- `docs/guides/LOOPS_GUIDE.md` — May reference `check_semantic`; audit for single-criterion examples

### Similar Patterns to Follow

- `skills/create-loop/loop-types.md:651-676` — Step H4 two-question AskUserQuestion in a single call; use this exact pattern structure for the H3 LLM-as-judge follow-up
- `loops/oracles/oracle-capture-issue.yaml:65-98` — Multi-criteria scoring pattern with numbered dimensions and explicit positive/negative signals per criterion

### Codebase Research Findings

_Updated by `/ll:refine-issue` — re-verified after `check_stall` and `check_skill` wizard commits shifted lines:_

**Verified line ranges in `skills/create-loop/loop-types.md`** (as of 2026-03-24):
- Step H3 header at line 603; LLM-as-judge option at lines 635–636; no LLM-as-judge follow-up exists — confirmed gap
- Skill-based follow-up block (reference pattern) at lines 641–645
- Insertion point for new LLM-as-judge follow-up: after line 645, before line 647 ("Default selection" note)
- Step H4 two-question AskUserQuestion pattern (structural reference): lines 651–676
- Variant A `check_semantic` block: lines 727–735; `evaluate.prompt` placeholder at line 733
- Variant B `check_semantic` block: lines 800–808; `evaluate.prompt` placeholder at line 806
- Custom prompt "done" question: line 575 (unchanged)

**`skills/create-loop/templates.md`**: Contains no `check_semantic` states or `evaluate.prompt` fields — **no changes needed**. Resolves the prior "additional file to audit" uncertainty.

**Corrected line ranges in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`**:
- Lines 219–233: LLM-as-Judge section — confirmed correct
- Variant A worked example: lines 448–457 (check_semantic block; prompt at 453–455)
- Variant B worked example: lines 511–520 (check_semantic block; prompt at 516–518)

**Current harness YAML prompts** (three-condition prose — need reformatting to numbered list):
- `loops/harness-single-shot.yaml:123–126` — prose: "at least one file was modified, no errors were reported, and the task appears complete"
- `loops/harness-multi-item.yaml:148–151` — prose: "the item was meaningfully updated, no errors occurred, and the overall quality improved"

## Scope Boundaries

- No changes to FSM schema (`EvaluateConfig.prompt` accepts any string; no schema updates needed)
- No changes to `evaluate_llm_structured()` evaluator logic
- Existing harness YAML files produced by previous wizard runs are unaffected
- Skill-based evaluation path (Step H3 skill-based follow-up) is unchanged
- Pre-populated criteria suggestions from skill description (Step H3, item 3) are optional; the core flow only requires the two follow-up questions
- No changes to non-`check_semantic` evaluation types (`exit_code`, `file_exists`, etc.)

## Impact

- **Priority**: P4 — Quality improvement for wizard-generated harnesses; not blocking any other work
- **Effort**: Small — Adds ~2 AskUserQuestion sub-questions to one wizard step; updates 2 YAML template variants and docs
- **Risk**: Low — No schema or evaluator changes; no breaking changes to existing loops
- **Breaking Change**: No

## Labels

`enhancement`, `wizard`, `harness`, `check-semantic`, `evaluation`

## Status

**Open** | Created: 2026-03-24 | Priority: P4

## Resolution

Implemented all five changes described in the Implementation Steps:

1. **Step H3 follow-up** (`loop-types.md`): Added LLM-as-judge two-question follow-up block after the Skill-based validation follow-up, including a note about pre-populating suggestions from skill description.
2. **Custom prompt path** (`loop-types.md:575`): Replaced single "done" question with the two-question format for consistency.
3. **Variant A template** (`loop-types.md`): Replaced `<auto-derived>` placeholder with numbered multi-criteria format using `<success-criterion>` and `<failure-criterion>` placeholders.
4. **Variant B template** (`loop-types.md`): Same replacement.
5. **Docs** (`AUTOMATIC_HARNESSING_GUIDE.md`): Updated LLM-as-Judge section description, both worked examples (Variant A/B), and the customization tip table row.
6. **Example harnesses** (`harness-single-shot.yaml`, `harness-multi-item.yaml`): Reformatted prose prompts to numbered multi-criteria format.

## Session Log
- `/ll:ready-issue` - 2026-03-25T03:50:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83280324-52b5-44e9-b8f2-0920a7fb2a15.jsonl`
- `/ll:confidence-check` - 2026-03-25T04:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39ccdd92-6e91-4cbf-a732-3a2195f532e6.jsonl`
- `/ll:refine-issue` - 2026-03-25T03:36:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f0c9302-3842-474a-b57f-bab3e4187f1d.jsonl`
- `/ll:refine-issue` - 2026-03-25T02:34:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d706ae24-efb5-4d22-b384-27e1793cb625.jsonl`
- `/ll:format-issue` - 2026-03-25T01:57:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15f2515b-b7d9-4642-9556-f9fa1158773a.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/556f7371-7835-47ca-a34d-204ed0fd9aed.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e447577-879b-46c6-bd2c-f3b7cdd1e037.jsonl`
- `/ll:refine-issue` - 2026-03-25T00:48:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7bda774-ec89-44b3-8910-da455deea386.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3df6195-41d1-442e-a5ec-89e21c18fa59.jsonl`
