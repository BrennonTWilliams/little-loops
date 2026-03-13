---
id: ENH-717
type: ENH
priority: P3
status: backlog
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-717: Review-loop should detect LLM prompt states replaceable with programmatic logic

## Summary

Extend the `/ll:review-loop` skill to analyze each FSM state and flag LLM `prompt` states that could be replaced with deterministic, programmatic implementations — reducing latency, cost, and nondeterminism.

## Motivation

FSM loops sometimes use LLM prompt states for operations that don't require language model reasoning — e.g., string formatting, file existence checks, counting, filtering, or conditional branching based on structured data. These are better handled programmatically. The review skill already audits quality; adding this analysis closes a gap that makes loops more efficient and predictable.

## Acceptance Criteria

- [ ] `review-loop` inspects each `prompt`-type state during its analysis pass
- [ ] States are flagged as "possibly replaceable" if they match heuristics indicating deterministic behavior (e.g., simple formatting, file/path ops, counting, yes/no decisions on structured input)
- [ ] Flagged states are reported as a **Suggestion**-severity finding with explanation and example alternative (`bash` state or `python` inline)
- [ ] Existing `--dry-run` and `--auto` flags respect the new findings (report only / auto-skip suggestions)
- [ ] No false positives for states that genuinely need language understanding (summarizing, classifying free text, etc.)

## Implementation Steps

1. Define heuristics for "replaceable" prompt states in `skills/review-loop/reference.md`:
   - State prompt contains only template variable substitution with no open-ended reasoning
   - State output feeds into a transition condition that could be computed directly
   - Prompt body matches patterns like "does X exist?", "count the number of...", "format Y as Z"
2. Add a new analysis pass in `SKILL.md` after the existing quality checks
3. Emit findings as `Suggestion` severity with suggested replacement approach
4. Update `skills/review-loop/SKILL.md` to document the new check
5. Add test cases to `scripts/tests/` covering detected and non-detected patterns

## Related

- `/ll:create-loop` — complements by guiding users toward programmatic states at creation time
- `skills/review-loop/reference.md` — where heuristic rules should live

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - captured from user description
