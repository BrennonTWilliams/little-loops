---
id: ENH-717
type: ENH
priority: P3
status: backlog
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
---

# ENH-717: Review-loop should detect LLM prompt states replaceable with programmatic logic

## Summary

Extend the `/ll:review-loop` skill to analyze each FSM state and flag LLM `prompt` states that could be replaced with deterministic, programmatic implementations — reducing latency, cost, and nondeterminism.

## Current Behavior

The `/ll:review-loop` skill analyzes FSM loop configurations for quality, correctness, and consistency, reporting findings by severity (Error/Warning/Suggestion). It does not inspect whether individual `prompt`-type states perform deterministic operations — such as string formatting, file existence checks, counting, or conditional branching on structured data — that could be replaced with cheaper, faster `bash` or `python` states.

## Expected Behavior

The skill includes an additional analysis pass that detects `prompt`-type states matching heuristics for deterministic behavior and reports them as `Suggestion`-severity findings. Each finding includes an explanation of why the state may be replaceable and an example alternative (`bash` state or inline `python`). States that require genuine language understanding (summarizing, classifying free text, generating content) are not flagged.

## Motivation

FSM loops sometimes use LLM prompt states for operations that don't require language model reasoning — e.g., string formatting, file existence checks, counting, filtering, or conditional branching based on structured data. These are better handled programmatically. The review skill already audits quality; adding this analysis closes a gap that makes loops more efficient and predictable.

## Acceptance Criteria

- [ ] `review-loop` inspects each `prompt`-type state during its analysis pass
- [ ] States are flagged as "possibly replaceable" if they match heuristics indicating deterministic behavior (e.g., simple formatting, file/path ops, counting, yes/no decisions on structured input)
- [ ] Flagged states are reported as a **Suggestion**-severity finding with explanation and example alternative (`bash` state or `python` inline)
- [ ] Existing `--dry-run` and `--auto` flags respect the new findings (report only / auto-skip suggestions)
- [ ] No false positives for states that genuinely need language understanding (summarizing, classifying free text, etc.)

## Proposed Solution

Add a new analysis pass in `skills/review-loop/SKILL.md` after existing quality checks. Define heuristics in `skills/review-loop/reference.md` for prompt states that may be deterministic:

- Prompt contains only template variable substitution with no open-ended reasoning
- State output feeds into a transition condition computable directly from structured input
- Prompt body matches patterns like "does X exist?", "count the number of...", "format Y as Z"

Emit findings as `Suggestion` severity (non-blocking) with a suggested alternative:
- Simple conditionals → `bash` state with shell expression
- Counting/filtering → `bash` state with `grep -c` or `wc`
- Formatting → `bash` state with `printf` or `jq`

## Implementation Steps

1. Define heuristics for "replaceable" prompt states in `skills/review-loop/reference.md`:
   - State prompt contains only template variable substitution with no open-ended reasoning
   - State output feeds into a transition condition that could be computed directly
   - Prompt body matches patterns like "does X exist?", "count the number of...", "format Y as Z"
2. Add a new analysis pass in `SKILL.md` after the existing quality checks
3. Emit findings as `Suggestion` severity with suggested replacement approach
4. Update `skills/review-loop/SKILL.md` to document the new check
5. Add test cases to `scripts/tests/` covering detected and non-detected patterns

## Scope Boundaries

- **In scope**: Heuristic detection of deterministic `prompt` states in review-loop analysis; Suggestion-severity findings with example alternatives; heuristic rules documented in `reference.md`; test cases for detected and non-detected patterns
- **Out of scope**: Automatic rewriting or replacing of prompt states; changes to `/ll:create-loop` skill; performance benchmarking; changes to other FSM state types (`bash`, `python`, `evaluate`)

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` — add new analysis pass after existing quality checks
- `skills/review-loop/reference.md` — define replacement heuristics

### Dependent Files (Callers/Importers)
- N/A — skill is invoked directly by user via `/ll:review-loop`

### Similar Patterns
- `skills/review-loop/SKILL.md` — existing quality check pass (follow same pattern for new analysis pass)

### Tests
- `scripts/tests/` — add test cases covering detected patterns (formatting, counting, existence checks) and non-detected patterns (free-text classification, summarization)

### Documentation
- `skills/review-loop/reference.md` — heuristic rules live here per Implementation Steps

### Configuration
- N/A

## Impact

- **Priority**: P3 - Nice-to-have optimization; does not block other work
- **Effort**: Medium - Requires new heuristic definitions and an additional analysis pass in SKILL.md; reference.md update
- **Risk**: Low - Purely additive Suggestion-only findings; no behavior changes to existing Error/Warning findings
- **Breaking Change**: No

## Related

- `/ll:create-loop` — complements by guiding users toward programmatic states at creation time
- `skills/review-loop/reference.md` — where heuristic rules should live

## Labels

`enhancement`, `review-loop`, `optimization`

---

**Open** | Created: 2026-03-13 | Priority: P3

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `skills/review-loop/SKILL.md` exists (404 lines) and has no section detecting replaceable LLM prompt states. `skills/review-loop/reference.md` exists but contains no heuristics for deterministic-state detection. The feature is not yet implemented.

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - captured from user description
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
