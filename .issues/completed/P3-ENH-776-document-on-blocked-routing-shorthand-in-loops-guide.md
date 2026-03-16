---
id: ENH-776
type: ENH
priority: P3
status: active
title: Document on_blocked routing shorthand in LOOPS_GUIDE
confidence_score: 100
outcome_confidence: 100
---

## Summary

The `on_blocked` routing shorthand is fully implemented in the FSM engine (schema, executor, and LLM evaluator all support it), but it is not documented in `docs/guides/LOOPS_GUIDE.md`. The routing section only mentions `on_yes`, `on_no`, and `on_partial`.

The `llm_structured` evaluator can return a `blocked` verdict (when Claude determines the task cannot proceed), but users have no way to know they can route on it via `on_blocked`.

## Motivation

This enhancement would:
- Eliminate documentation gap: users of `llm_structured` evaluator cannot discover `on_blocked` routing without reading source code
- Business value: enables loop authors to handle blocked states explicitly rather than relying on undefined fallback behavior
- Technical debt: `on_blocked` is already documented in `generalized-fsm-loop.md` (commit c3eec64) but was not propagated to the primary user-facing guide

## Expected

The Routing section in `docs/guides/LOOPS_GUIDE.md` should:
1. Add `on_blocked` to the shorthand routing table alongside `on_yes`, `on_no`, `on_partial`
2. Briefly explain when `blocked` is emitted (LLM determines the task cannot continue — e.g., missing prerequisite, ambiguous state)
3. Optionally show an example state that uses `on_blocked: escalate` to route to a human-escalation state

## Success Metrics

- `LOOPS_GUIDE.md` routing shorthand table includes `on_blocked` alongside `on_yes`, `on_no`, `on_partial`
- `blocked` verdict explanation is present in the evaluators section (or routing section)
- At least one example demonstrates `on_blocked: <target_state>` usage

## Scope Boundaries

- **In scope**: Documentation update to `docs/guides/LOOPS_GUIDE.md` routing section and evaluators table; optional usage example
- **Out of scope**: Changes to schema, executor, or evaluator code (already fully implemented); changes to `generalized-fsm-loop.md` (already updated in commit c3eec64)

## Acceptance Criteria

- [x] `on_blocked` appears in the shorthand routing table in `LOOPS_GUIDE.md` alongside `on_yes`, `on_no`, `on_partial`
- [x] `blocked` verdict is explained (when `llm_structured` emits it — e.g., missing prerequisite, ambiguous state)
- [x] At least one example state shows `on_blocked: <target_state>` routing

## Implementation Steps

1. In `docs/guides/LOOPS_GUIDE.md:240`, add `on_blocked` to the shorthand list in the prose: change `` (`on_yes`, `on_no`, `on_partial`) `` → `` (`on_yes`, `on_no`, `on_partial`, `on_blocked`) ``
2. After the shorthand prose and before (or after) the route table example, insert the `on_blocked` paragraph and YAML example mirroring `docs/generalized-fsm-loop.md:445–456`
3. The evaluators table at `docs/guides/LOOPS_GUIDE.md:198` already lists `blocked` as an `llm_structured` verdict — no change needed there
4. Verify by checking that `on_blocked` now appears in the routing section and cross-checking wording against `docs/generalized-fsm-loop.md:445–456`

## Location

- File: `docs/guides/LOOPS_GUIDE.md`
- Section: **Routing** (line 240 — shorthand prose listing `on_yes`, `on_no`, `on_partial`)
- Related: Evaluators table (line 198) — `llm_structured` already lists `blocked` as a verdict (no change needed)

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — routing section (line 240, shorthand prose); insert `on_blocked` paragraph after existing shorthand description

### Dependent Files (Callers/Importers)
- N/A — documentation-only change

### Similar Patterns
- `docs/generalized-fsm-loop.md:445–456` — source of truth for `on_blocked` wording; mirror exactly
- `docs/generalized-fsm-loop.md:499` — resolution order list that includes `on_blocked` alongside `on_yes`/`on_no`/`on_error`

### Tests
- N/A — no code changes; verify manually by reading updated LOOPS_GUIDE.md

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — primary file to update

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact content of gap** (`LOOPS_GUIDE.md:240`): The routing section prose reads:
> States use **shorthand** (`` `on_yes`, `on_no`, `on_partial` ``) or a **route table** for verdict-to-state mapping

`on_blocked` is entirely absent from this file (confirmed by grep).

**Evaluators table gap**: `LOOPS_GUIDE.md:198` already shows `llm_structured` verdicts as `yes / no / blocked / partial` — the `blocked` verdict is visible, but no corresponding shorthand key is documented. This is the mismatch that confuses users.

**Content to insert** (mirror `generalized-fsm-loop.md:445–456`):
```markdown
An additional shorthand, `on_blocked`, routes when the evaluator returns a `blocked` verdict (i.e., the action cannot proceed without external intervention):

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    on_yes: "verify"
    on_no: "fix"
    on_blocked: "escalate"
```

`on_blocked` is resolved alongside `on_yes`/`on_no`/`on_error` in the shorthand lookup. It is equivalent to adding `blocked: "escalate"` to a full `route` table. If a `blocked` verdict is returned and no `on_blocked` target is defined, the loop terminates with a fatal routing error — define `on_blocked` on any state whose action can return a `blocked` verdict.
```

**Real-world usage** — six production loops already use `on_blocked`:
- `loops/issue-staleness-review.yaml:48` — routes blocked back to loop (skip and continue)
- `loops/issue-size-split.yaml:31` — routes blocked to terminal (abort gracefully)
- `loops/sprint-build-and-validate.yaml:69,106` — routes blocked to fix state
- `loops/apo-opro.yaml:33,55,73` and `loops/apo-textgrad.yaml:22,36,55` — `on_blocked: done` on prompt states

**When `blocked` is emitted**: `llm_structured` evaluator (`evaluators.py:54–79`) constrains LLM to enum `["yes","no","blocked","partial"]`. The `blocked` option description: "Cannot proceed without external help". It is the **default evaluator** for all slash command and prompt-type states (executor.py:777), so any state using `/` actions can return `blocked` without an explicit `evaluate:` block.

## API/Interface

N/A - No public API changes (documentation-only enhancement)

## References

- Commit c3eec64: `docs(fsm-loop): add on_blocked shorthand routing documentation` (added to `generalized-fsm-loop.md` but not propagated to LOOPS_GUIDE.md)
- Schema: `scripts/little_loops/fsm/schema.py`
- Executor: `scripts/little_loops/fsm/executor.py`


## Resolution

- **Status**: COMPLETED — 2026-03-16
- Updated `docs/guides/LOOPS_GUIDE.md` line 240: added `on_blocked` to shorthand list and inserted paragraph + example mirroring `generalized-fsm-loop.md:445–456`

## Verification Notes

- **Verdict**: VALID — gap confirmed as of 2026-03-16
- `docs/guides/LOOPS_GUIDE.md` routing section (line 240) lists `on_yes`, `on_no`, `on_partial` but has no `on_blocked` shorthand
- `docs/guides/LOOPS_GUIDE.md` evaluators table (line 198) lists `blocked` as an `llm_structured` verdict, but no routing shorthand is documented
- `docs/generalized-fsm-loop.md` fully documents `on_blocked` (line 445 with example) — gap is specific to LOOPS_GUIDE.md propagation
- All referenced code files exist: `scripts/little_loops/fsm/schema.py`, `scripts/little_loops/fsm/executor.py`

## Session Log
- `/ll:ready-issue` - 2026-03-16T20:24:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cfbbc21-6b64-450a-a7fd-588221611c38.jsonl`
- `/ll:confidence-check` - 2026-03-16T19:26:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:refine-issue` - 2026-03-16T19:25:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T19:21:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:refine-issue` - 2026-03-16T19:20:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T19:16:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:refine-issue` - 2026-03-16T19:15:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:09:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:06:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
