---
id: ENH-2342
type: ENH
priority: P2
status: open
discovered_date: 2026-06-27
captured_at: "2026-06-27T05:17:49Z"
discovered_by: capture-issue
decision_needed: false
---

# ENH-2342: Evidence-Gate check_semantic LLM Evaluator Verdicts

## Summary

Change the LLM-evaluator prompt contract so every Yes/No/Partial verdict must cite verbatim evidence from the trajectory and defaults to the conservative verdict (No/Partial) when evidence is absent. This applies to `check_semantic` / `llm_structured` evaluator states in FSM loops and to LLM-judged states in meta-loops.

## Current Behavior

`check_semantic` and `llm_structured` loop states ask an LLM to judge whether a condition is met and return a structured verdict. The prompt contract does not require the model to quote evidence from the trajectory — it can assert "Yes, the task is complete" without citing any specific output. This is the pattern that makes LLM self-grades ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4% as noted in CLAUDE.md).

## Expected Behavior

Every `check_semantic` prompt template includes a mandatory evidence block:

```
For each condition you judge:
- State Yes, No, or Partial
- Quote the EXACT line(s) from the trajectory that support your verdict (verbatim, in quotes)
- If you cannot find a verbatim quote, your verdict MUST be No (or Partial if unsure)
```

An LLM that returns a verdict without a matching quote is treated as returning the conservative default. This is enforced in the evaluator parsing layer, not just by prompt instruction.

## Motivation

Two independent papers in the 05-26-2026 research batch converge on this pattern:

- **SELFCOMPACT**: its rubric requires verbatim citations for every yes/no condition; ablation shows removing the rubric collapses quality to the naive baseline (46.4% → 41.0%). The rubric (not the act of compacting) is where the gain comes from.
- **RL-collapse PRS prompt**: "state the root cause in 1–2 lines, then provide 2–4 pieces of evidence from the interaction log." Grounding in citations is what makes both evaluators reliable.

This is a **prompt-template change, not an architecture change**, and it directly attacks the documented LLM self-grade accuracy problem. It pairs with MR-1 (non-LLM evaluator required alongside LLM judges) to make the LLM side of that pair meaningfully discriminating rather than defaulting to optimism.

## Proposed Solution

**1. Update the shared `check_semantic` prompt template** (wherever it lives in `scripts/little_loops/`) to add the evidence contract:

```python
CHECK_SEMANTIC_EVIDENCE_CONTRACT = """
IMPORTANT: For each condition you evaluate:
1. State your verdict: Yes / No / Partial
2. Provide a VERBATIM quote from the output that supports your verdict (exact text, in quotes)
3. If you cannot quote specific text, your verdict is automatically No (or Partial if context suggests partial progress)

Do not assert a verdict without evidence. "The task appears complete" is not evidence.
"""
```

**2. Update the verdict parser** in `llm_structured` / `check_semantic` to validate that returned verdicts include a non-empty evidence field. If the evidence field is empty or missing, coerce the verdict to `No` (or `partial` if the current route table has a `partial` branch).

**3. Add a loop validator check** in `ll-loop validate` (or as an advisory in `ll-loop diagnose-evaluators`) that detects `check_semantic` states whose prompt template omits the evidence contract. Severity: WARNING. Rationale: the contract can't be enforced at parse time if the template never asked for evidence.

**4. Update the `AUTOMATIC_HARNESSING_GUIDE.md` and loop authoring docs** to document the evidence-gating contract as a standard requirement alongside MR-1.

## Implementation Steps

1. Locate the `check_semantic` / `llm_structured` prompt construction code in `scripts/little_loops/`
2. Add `CHECK_SEMANTIC_EVIDENCE_CONTRACT` constant and inject it into all LLM-evaluator prompts
3. Update the structured-output schema for `check_semantic` to include an `evidence: str` field (required, validated non-empty)
4. In the verdict parser: if `evidence` is empty/missing → coerce to conservative verdict; log a warning
5. Add `ll-loop validate` rule: `check_semantic` state without evidence-contract keyword in prompt → WARNING
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` with evidence-contract documentation
7. Write tests covering: verdict with evidence accepted, verdict without evidence coerced, partial coercion, schema enforcement

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/SYNTHESIS-and-recommendations.md` | Source recommendation #2; SELFCOMPACT + PRS findings |
| `.claude/CLAUDE.md` § Loop Authoring MR-1 | The non-LLM pairing rule this enhances |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Where the evidence contract must be documented |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Evaluator health context |

## Session Log
- `/ll:capture-issue` - 2026-06-27T05:17:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd21288e-7370-4e7e-8040-6f118e73e291.jsonl`
