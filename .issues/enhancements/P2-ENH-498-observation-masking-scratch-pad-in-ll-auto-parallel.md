---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 90
outcome_confidence: 64
---

# ENH-498: Observation Masking / Scratch Pad Pattern in ll-auto and ll-parallel

## Summary

Tool outputs are typically 80%+ of total agent context tokens in long automation runs. Implement an "observation masking" pattern: large tool outputs (file contents, test results, lint reports) are written to scratch pad files and referenced by path rather than inlined in conversation context. This significantly reduces context bloat in ll-auto and ll-parallel sessions.

## Current Behavior

In ll-auto and ll-parallel, every tool output is inlined in the conversation history. A single issue implementation might read 10–20 files (each potentially 200–1000 lines), run tests, and execute lint — all of which remain in context for subsequent turns. By mid-session, the context is dominated by tool outputs from earlier steps that are no longer needed.

This contributes directly to context degradation in longer runs (related: ENH-499).

## Expected Behavior

Large tool outputs are captured to temporary scratch files (`/tmp/ll-scratch/<session>/<turn>-<tool>.txt`) and replaced in conversation context with a compact reference:

```
[Output saved to scratch/turn-012-file-read.txt — 847 lines]
```

The agent can re-read the scratch file on demand if it needs the full content. Small outputs (< N lines, configurable) are still inlined normally.

## Motivation

Research benchmarks show this pattern reduces context token usage by 50–80% in tool-heavy sessions without degrading task completion quality — agents selectively re-read what they need rather than having everything compete for attention. For ll-auto processing 5–10 issues sequentially, this could be the difference between completing a run and hitting context limits mid-batch.

## Proposed Solution

Option A (preferred — hook-based): Implement as a `PostToolUse` hook that intercepts large tool outputs and writes them to scratch files before they enter context.

Option B (agent-directed): Update the ll-auto system prompt to instruct Claude to write large outputs to files and reference them, using existing Write tool capability.

Option A is preferable because it's automatic and doesn't require Claude to remember the pattern.

## Scope Boundaries

- **In scope**: Intercepting large tool outputs in ll-auto/ll-parallel sessions; scratch file management; configurable size threshold
- **Out of scope**: Changing issue processing logic, modifying how results are reported in git worktrees

## Implementation Steps

1. Determine which hook event is appropriate (`PostToolUse` in `hooks/hooks.json`)
2. Implement a Python hook script: reads tool output size, if > threshold writes to scratch file, returns compact reference
3. Add `scratch_pad_threshold_lines` to ll-config.json schema (default: 200)
4. Implement scratch file cleanup (per-session, cleared at session start)
5. Update ll-auto and ll-parallel system prompts to acknowledge scratch references and re-read as needed
6. Test with a representative issue that reads multiple large files

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add PostToolUse hook
- `hooks/` — new hook script for observation masking
- `config-schema.json` — add `scratch_pad_threshold_lines` field
- `.claude/ll-config.json` — add default value

### New Files
- `hooks/observation-masking.py` (or `.sh`) — hook implementation

### Tests
- `scripts/tests/` — test hook invocation with mock large output
- Manual: run ll-auto on a file-heavy issue, verify context size reduction

### Documentation
- `docs/ARCHITECTURE.md` — document observation masking pattern
- `docs/guides/` — mention in ll-auto usage guide

## Impact

- **Priority**: P2 — High; directly improves reliability of long automation runs
- **Effort**: Medium — Hook infrastructure + Python script + config changes
- **Risk**: Medium — Hook failures could break tool output delivery; needs robust error handling and fallback
- **Breaking Change**: No (additive)

## Labels

`enhancement`, `context-engineering`, `ll-auto`, `ll-parallel`, `hooks`, `performance`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2
