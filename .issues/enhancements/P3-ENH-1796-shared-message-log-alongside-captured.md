---
id: ENH-1796
type: ENH
title: Shared message log alongside captured.* for cross-state context
priority: P3
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - captured
  - fsm
  - harness
  - loops
  - state-management
relates_to: []
---

# ENH-1796: Shared message log alongside `captured.*` for cross-state context

## Summary

Add a run-scoped `messages` channel that every FSM state can append to
and any later state can read in full. This complements the existing
per-state `capture:` mechanism (which only exposes `${captured.<name>.output}`
and is essentially key-value), giving us the analogue of LangGraph's
`MessagesState` with `Annotated[list, add_messages]` — an append-only
conversation log that survives the whole run.

## Current Behavior

- States expose their output via `capture: <name>` and other states
  reference it as `${captured.<name>.output}`.
- When four states each need the same context (e.g., `discover` →
  `investigate` → `execute` → `check_semantic` all wanting both the
  item ID and prior reasoning), the YAML becomes a daisy-chain of
  `${captured.X.output}` concatenations, and each downstream state has
  to know exactly which upstream key holds what.
- There is no run-scoped append-only log of "what happened so far" that
  late states can summarize over.

## Expected Behavior

A `messages:` channel that:

1. Any state can append to via a state-level field, e.g.
   `append_to_messages: "${captured.execute.output}"`, or implicitly when
   `action_type: prompt`.
2. Any state can reference via `${messages}` (full log) or
   `${messages.last(3)}` (windowed view) in prompts/actions.
3. Persists to `.loops/runs/<id>/messages.jsonl` for replay and audit.
4. Has a size budget — when `messages` exceed N tokens, the runner
   summarizes older entries (mirrors DeerFlow's summarization
   middleware) and surfaces the summary as `${messages.summary}`.

This unblocks specialist-role pipelines (see FEAT-1798) where Plan →
Research → Implement → Report all need to see prior steps' reasoning,
not just the immediately-preceding output.

## Motivation

This enhancement would:
- Eliminate the N-state daisy-chain of `${captured.X.output}` concatenations that currently plagues multi-state FSM loops
- Enable specialist-role pipelines (see FEAT-1798) where Plan → Research → Implement → Report all share prior reasoning
- Provide the LangGraph `MessagesState` analogue (`Annotated[list, add_messages]`) for FSM loops — a well-understood pattern for append-only cross-state context

## Success Metrics

- Template variable references per downstream state: reduced from O(N) `${captured.X.output}` chains to O(1) `${messages}` reference
- Specialist-role pipeline viability: a 4-state pipeline (Plan → Research → Implement → Report) can share context without explicit per-state capture wiring
- Token budget: summarization keeps in-context messages within the loop's configured token limit

## Scope Boundaries

- **In scope**: `messages` channel with append semantics, `${messages}` / `${messages.last(N)}` / `${messages.summary}` template variables, JSONL persistence to `.loops/runs/<id>/messages.jsonl`, size-budget summarization middleware
- **Out of scope**: Replacing or removing the existing `captured.*` per-state mechanism, cross-run message persistence or replay, message editing or deletion, real-time streaming to external systems, structured message types beyond plain text

## API/Interface

New YAML fields and template variables:

```yaml
# State-level field — append output to the shared messages log
append_to_messages: "${captured.execute.output}"

# Template variables available in prompts/actions:
#   ${messages}            — full message log
#   ${messages.last(N)}    — last N messages (windowed view)
#   ${messages.summary}    — LLM-summarized older entries (when budget exceeded)
```

## Impact

- **Priority**: P3 — quality-of-life; current `captured.*` works but
  scales poorly past ~3 states with shared context.
- **Effort**: Medium — runner storage, prompt-interpolation extension,
  summarization policy, docs, tests.
- **Risk**: Medium — token budget interactions can surprise; needs
  conservative defaults and per-state opt-out.
- **Breaking Change**: No — additive.

## Implementation Steps

1. Extend runner storage to create and manage `.loops/runs/<id>/messages.jsonl` per run
2. Add `append_to_messages` state-level field and wire into state execution lifecycle
3. Extend prompt-interpolation to resolve `${messages}`, `${messages.last(N)}`, and `${messages.summary}`
4. Implement token-budget summarization middleware — when messages exceed threshold, summarize older entries via LLM call
5. Add tests for append, read, windowed-view, summarization, and budget enforcement
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` and `skills/create-loop/reference.md`

## Integration Map

### Files to Modify
- `scripts/little_loops/runner.py` — runner storage, state execution, prompt interpolation
- `skills/create-loop/reference.md` — FSM field reference documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — documented captured-outputs pattern

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "captured\." scripts/little_loops/`

### Similar Patterns
- TBD — search for consistency: `grep -r "append\|messages\|conversation_log" scripts/`

### Tests
- TBD — identify test files for runner, interpolation, and summarization

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
- `skills/create-loop/reference.md`

### Configuration
- N/A

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Referencing Captured Outputs | Today's documented pattern; this issue extends it |
| `skills/create-loop/reference.md` | FSM field reference where the new `messages` channel would be specified |

## Labels

`captured`, `fsm`, `harness`, `loops`, `state-management`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-29T21:14:09 - `0a9cb5c6-15fc-4ffc-a6bb-7ab28458c9d2.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
