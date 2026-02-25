---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-497: Document Tokens-per-Task as ll-auto/ll-parallel Design Principle

## Summary

Add an explicit architecture decision record establishing "tokens-per-task-completion" (not "tokens-per-request") as the correct efficiency metric for ll-auto, ll-parallel, and ll-sprint. This reframe affects compression decisions, context retention tradeoffs, and how we evaluate automation efficiency.

## Current Behavior

There is no documented guidance on how to measure or optimize token efficiency in our automation tools. The implicit assumption is that shorter conversations are better, which leads to over-aggressive compression that causes re-fetching, retries, and error cascades — costing more tokens overall.

## Expected Behavior

`docs/ARCHITECTURE.md` (or a new ADR) includes an explicit principle:

> **Efficiency metric: tokens-per-task, not tokens-per-request.**
> Over-aggressive compression that causes retries, re-reads, or error recovery is less efficient than a longer conversation that completes the task cleanly. When evaluating context compression tradeoffs in ll-auto/ll-sprint, optimize for task completion with minimum total tokens, not minimum per-turn tokens.

This principle should also inform the trigger threshold for context checkpoints (e.g., "compress at 70-80% utilization, not earlier").

## Motivation

This is a subtle but important reframe validated by published research. Without it, contributors naturally optimize for shorter individual turns, which can be counterproductive. Documenting it prevents re-learning the same lesson repeatedly and provides a rationale for design decisions that would otherwise appear wasteful.

Secondary benefit: it provides the conceptual foundation for the context degradation checkpoint work (ENH-499).

## Proposed Solution

1. Add a "Context Efficiency" section to `docs/ARCHITECTURE.md`
2. Define tokens-per-task as the primary metric
3. Explain why tokens-per-request is misleading for sequential automation
4. Document the 70-80% utilization compression trigger recommendation
5. Reference this principle from ll-auto and ll-sprint documentation where compression decisions are made

## Scope Boundaries

- **In scope**: Documentation only — `docs/ARCHITECTURE.md`, no code changes
- **Out of scope**: Actually implementing compression triggers (see ENH-499)

## Implementation Steps

1. Read `docs/ARCHITECTURE.md` to find the right insertion point
2. Draft "Context Efficiency" section with the principle, rationale, and implications
3. Add cross-references from relevant CLI tool documentation

## Integration Map

### Files to Modify
- `docs/ARCHITECTURE.md` — new "Context Efficiency" section

### Related Issues
- ENH-499 — Context degradation checkpoints (implements this principle)

## Impact

- **Priority**: P4 — Documentation only; low urgency
- **Effort**: Low — Writing only
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `context-engineering`, `architecture`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

## Blocked By

- FEAT-441
