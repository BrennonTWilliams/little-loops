---
id: ENH-776
type: ENH
priority: P3
status: active
title: Document on_blocked routing shorthand in LOOPS_GUIDE
---

## Problem

The `on_blocked` routing shorthand is fully implemented in the FSM engine (schema, executor, and LLM evaluator all support it), but it is not documented in `docs/guides/LOOPS_GUIDE.md`. The routing section only mentions `on_yes`, `on_no`, and `on_partial`.

The `llm_structured` evaluator can return a `blocked` verdict (when Claude determines the task cannot proceed), but users have no way to know they can route on it via `on_blocked`.

## Expected

The Routing section in `docs/guides/LOOPS_GUIDE.md` should:
1. Add `on_blocked` to the shorthand routing table alongside `on_yes`, `on_no`, `on_partial`
2. Briefly explain when `blocked` is emitted (LLM determines the task cannot continue — e.g., missing prerequisite, ambiguous state)
3. Optionally show an example state that uses `on_blocked: escalate` to route to a human-escalation state

## Location

- File: `docs/guides/LOOPS_GUIDE.md`
- Section: **Routing** (around line 236)
- Related: Evaluators table (line 194) — `llm_structured` already lists `blocked` as a verdict

## References

- Commit c3eec64: `docs(fsm-loop): add on_blocked shorthand routing documentation` (added to `generalized-fsm-loop.md` but not propagated to LOOPS_GUIDE.md)
- Schema: `scripts/little_loops/fsm/schema.py`
- Executor: `scripts/little_loops/fsm/executor.py`
