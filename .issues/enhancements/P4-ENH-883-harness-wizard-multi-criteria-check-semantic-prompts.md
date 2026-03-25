---
id: ENH-883
type: ENH
priority: P4
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 71
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

1. **Add follow-up sub-questions in Step H3** (`skills/create-loop/loop-types.md:624-630`) — after the existing `"If 'Skill-based evaluation' is selected"` block, add a parallel block:

   ```
   **If "LLM-as-judge" is selected**, ask (single AskUserQuestion with two questions, following the pattern in Step H4 at loop-types.md:636-659):
   - "What should be different in the output after the skill runs successfully?"
   - "What would indicate the skill failed or made no progress?"
   ```

2. **Update the prompt template in both YAML variants** — replace the `<auto-derived>` placeholder:
   - Variant A (`loop-types.md:705`): Replace the single-question `prompt:` with a numbered multi-criteria block using the two answers from Step H3
   - Variant B (`loop-types.md:767`): Same replacement

3. **For skill catalog selections** (not custom prompts), pre-populate the sub-questions with suggested criteria derived from the selected skill's SKILL.md description (already read at `loop-types.md:558`). The description string currently feeds into `<skill-description>` — extend this to suggest criterion wording as option labels/descriptions in the AskUserQuestion.

4. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`**:
   - Lines 219-233: Replace single-criterion example prompt with multi-criteria numbered format
   - Lines ~404-415 and ~468-476: Update the Variant A and B worked example YAML blocks
   - Line ~601: Update the `check_semantic.evaluate.prompt` customization tip to mention multi-criteria format

5. **Update built-in example harness files**:
   - `loops/harness-single-shot.yaml:121-124` — Replace single-criterion prompt with multi-criteria example
   - `loops/harness-multi-item.yaml:146-149` — Same

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

- `skills/create-loop/loop-types.md:603-630` — Step H3: Add follow-up AskUserQuestion after "LLM-as-judge" selection (mirroring the Skill-based evaluation follow-up at line 624)
- `skills/create-loop/loop-types.md:700-707` — Variant A `check_semantic` template: Replace `<auto-derived>` placeholder with multi-criteria numbered format using user answers
- `skills/create-loop/loop-types.md:762-768` — Variant B `check_semantic` template: Same replacement
- `skills/create-loop/loop-types.md:575` — Custom prompt path: Extend "What does 'done' look like?" to also use the two-question format for consistency
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:219-233` — Update LLM-as-Judge section example prompt
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:~404-415` — Update Variant A worked example
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:~468-476` — Update Variant B worked example
- `loops/harness-single-shot.yaml:121-124` — Update example `check_semantic` prompt
- `loops/harness-multi-item.yaml:146-149` — Update example `check_semantic` prompt

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

- `skills/create-loop/loop-types.md:636-659` — Step H4 two-question AskUserQuestion in a single call; use this exact pattern structure for the H3 LLM-as-judge follow-up
- `loops/oracles/oracle-capture-issue.yaml:65-98` — Multi-criteria scoring pattern with numbered dimensions and explicit positive/negative signals per criterion

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

## Session Log
- `/ll:format-issue` - 2026-03-25T01:57:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15f2515b-b7d9-4642-9556-f9fa1158773a.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/556f7371-7835-47ca-a34d-204ed0fd9aed.jsonl`
- `/ll:refine-issue` - 2026-03-25T00:48:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7bda774-ec89-44b3-8910-da455deea386.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3df6195-41d1-442e-a5ec-89e21c18fa59.jsonl`
