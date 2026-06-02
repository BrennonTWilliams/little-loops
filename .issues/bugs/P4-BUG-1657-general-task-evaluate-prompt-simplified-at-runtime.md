---
id: BUG-1657
type: BUG
priority: P4
status: done
discovered_date: 2026-05-23
discovered_by: audit-loop-run
confidence_score: 80
outcome_confidence: 75
relates_to: [ENH-1655]
---

# BUG-1657: check_done evaluate prompt is silently simplified at runtime vs FSM definition

## Summary

The `general-task` loop's FSM definition specifies a 3-condition `evaluate.prompt` for `check_done`: verify (1) all DoD criteria are [x], (2) all plan steps are [x], (3) sample verification section has no FAILED entries. However, the evaluate prompts actually sent to the LLM at runtime only check condition (1) — "Are ALL criteria marked [x]?" — omitting plan-step and sample-verification checks.

## Problem

FSM definition (from `ll-loop show general-task --resolved --json`):
```
(1) The DoD file shows ALL Verification Criteria marked [x]
(2) The plan file shows ALL plan steps marked [x]
(3) The `## Sample Verification` section reports every sampled criterion as [x]
    with passing evidence (no FAILED entries)
```

Actual evaluate prompt sent to the LLM (from event history, all 6 evaluate calls):
```
Read <path>/general-task-dod.md. Are ALL criteria marked [x]?
Answer YES only if every criterion is checked off.
Answer NO if any remain unchecked.
```

Conditions (2) and (3) are never checked by the evaluator. This means:
- A loop could pass evaluation with unchecked plan steps
- A loop could pass evaluation with FAILED sample re-verifications
- The action prompt instructs the model to do sample re-verification and write a `## Sample Verification` section, but the evaluator never reads it

In practice, the action prompt's thorough verification means this gap hasn't caused incorrect terminations, but it creates a structural blind spot: the evaluator is supposed to be the independent gate, but it's checking a subset of what the FSM author intended.

## Investigation Notes

The `check_done` action text in the event history also differs from the FSM definition:
- **FSM definition**: 3-step process — Plan-vs-DoD coverage reconciliation, verify each criterion, sample re-verification
- **Runtime action**: "Read the DoD... For EACH criterion, actively verify it is met... Update the DoD file"

This suggests either the FSM was updated after the run, or there's prompt truncation/resolution happening at runtime that strips content.

## Proposed Fix

Investigate why the evaluate prompt is simplified at runtime. If this is intentional truncation (e.g., to reduce token cost), make it explicit in the FSM definition rather than silently diverging. If it's a bug in prompt resolution, fix the resolver.

The evaluate prompt should at minimum check plan step completeness (condition 2), since that's the direct measure of "are we done executing steps?"


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:45 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-05-24
- **Reason**: Superseded by ENH-1658 — fixing the prompt divergence now risks being discarded when ENH-1658 replaces the `llm_structured` evaluator with a shell counter entirely.

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: LOW

### Rationale
ENH-1658 (replace the LLM evaluator with a shell counter) is open and would make this bug structurally moot — the `check_done` evaluate prompt won't exist after that change. Fixing the prompt divergence now risks being immediately thrown away.
- `/ll:tradeoff-review-issues` - 2026-05-24T13:57:35 - `f0630921-fb2f-426a-a549-1a1d30e210f9.jsonl`
