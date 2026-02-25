---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-499: Context Degradation Checkpoints Between Issues in ll-auto

## Summary

Implement context boundary checkpoints between issues in ll-auto sequential processing. When one issue fails or produces errors, that error state "poisons" the context for subsequent issues. A lightweight summarization checkpoint between issues resets the working context, preventing cascading failures.

## Current Behavior

ll-auto processes issues sequentially in a single conversation. When an issue implementation fails partway through, error messages, failed tool calls, and incorrect assumptions remain in context for the next issue. Claude can inherit a "poisoned" context state where it misidentifies the current file state, continues partial changes, or applies the wrong mental model to a new issue.

The recent fix to prevent failed issues from being skipped (commit 528ef5b) addresses one symptom but not the root cause: context poisoning.

## Expected Behavior

Between each issue in an ll-auto run, a context checkpoint:

1. Summarizes what was accomplished (or failed) in the just-completed issue using the four-section Anchored Iterative Summarization schema (see ENH-495)
2. Explicitly resets mental state: "The previous issue is now complete/failed. The following is a fresh task."
3. Clears accumulated assumptions about file state by re-stating current git status
4. Triggers at configurable context utilization threshold (default: 70%)

This mirrors the "Four-Bucket" mitigation framework: **Write** (checkpoint to file), **Select** (load only next-issue context), **Compress** (summarize prior work), **Isolate** (clear poisoned assumptions).

## Motivation

Error compounding is a well-documented failure mode in sequential LLM processing. In a 10-issue ll-auto run, a failure on issue 3 can degrade quality of issues 4–10 even when issue 3 is correctly marked as failed. A context checkpoint prevents this cascade.

This is especially important for ll-sprint, which was designed to handle multiple issues in sequence and already has resume-after-failure logic that could be extended with checkpoint support.

## Proposed Solution

1. After each issue completion (success or failure), inject a structured inter-issue separator into the conversation
2. The separator includes: completion summary, explicit context reset statement, current git status
3. Add a `context_checkpoint_threshold` to ll-config.json: trigger aggressive compression when context utilization exceeds this threshold (default: 0.70)
4. Optionally write checkpoints to `thoughts/checkpoints/<run-id>/<issue-id>.md` for debugging and resume support

## Scope Boundaries

- **In scope**: Inter-issue context checkpoints in ll-auto; context utilization monitoring; checkpoint file writing
- **Out of scope**: Changes to ll-parallel (worktree isolation already provides context separation); fundamental changes to issue processing order

## Implementation Steps

1. Read `scripts/little_loops/auto.py` (or equivalent) to understand inter-issue boundaries
2. Identify the code location where one issue ends and the next begins
3. Implement checkpoint injection: structured summary + reset statement + git status
4. Add context utilization monitoring (use token count from API response metadata if available)
5. Add `context_checkpoint_threshold` to config schema
6. Optionally implement checkpoint file writing
7. Test with a multi-issue run where issue 2 intentionally fails

## Integration Map

### Files to Modify
- `scripts/little_loops/auto.py` — inter-issue checkpoint injection
- `config-schema.json` — add `context_checkpoint_threshold`
- `.claude/ll-config.json` — default value

### Related Issues
- ENH-495 — Anchored Iterative Summarization (checkpoint output format)
- ENH-497 — Tokens-per-task design principle (conceptual foundation)
- ENH-498 — Observation masking (complementary context reduction)

### Tests
- `scripts/tests/` — unit test checkpoint injection logic
- Integration test: ll-auto run with simulated failure on issue 2; verify issues 3+ are not affected

### Documentation
- `docs/ARCHITECTURE.md` — document context checkpoint pattern

## Impact

- **Priority**: P2 — High; directly improves reliability of ll-auto sequential processing
- **Effort**: Medium — Python changes to auto.py + config schema
- **Risk**: Medium — Changes to core sequential processing loop; needs careful testing
- **Breaking Change**: No (additive; existing behavior preserved without checkpoint trigger)

## Labels

`enhancement`, `context-engineering`, `ll-auto`, `ll-sprint`, `reliability`, `error-handling`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2
