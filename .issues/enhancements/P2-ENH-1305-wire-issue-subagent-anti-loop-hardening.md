---
id: ENH-1305
type: ENH
priority: P2
title: "wire-issue: harden Phase 4 subagent prompts against infinite loops"
status: backlog
captured_at: "2026-04-27T16:55:56Z"
discovered_date: "2026-04-27"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1305: wire-issue: harden Phase 4 subagent prompts against infinite loops

## Summary

`/ll:wire-issue` Phase 4 spawns 3 parallel subagents (codebase-locator, codebase-analyzer, codebase-pattern-finder) with **no stopping conditions**. When the autodev loop runs wire-issue on large issues, all 3 subagents enter infinite loops and the step never completes.

Observed failure mode (reported from another project):
- Agent 1 (codebase-locator): 600+ repetitions of "File unchanged since last read"
- Agent 2 (codebase-analyzer): 280+ repetitions of "File unchanged since last read"
- Agent 3 (codebase-pattern-finder): repeating identical grep results indefinitely

The hang was observed during a `/ll:wire-issue --auto` run on a broad-scope issue (5+ files, 32+ line references). The loop waited ~40 minutes before being killed manually.

## Current Behavior

When `/ll:wire-issue --auto` runs Phase 4 on a broad-scope issue, the 3 parallel subagents (codebase-locator, codebase-analyzer, codebase-pattern-finder) have no stopping conditions. They re-read unchanged files and repeat identical searches indefinitely, causing the entire wire-issue step to hang until manually killed.

## Expected Behavior

Each Phase 4 subagent should:
- Treat `"File unchanged since last read"` as a hard stop signal and not re-read that file again
- Stop and synthesize if a search returns results identical to a prior search
- Track visited file paths and grep patterns, never re-querying them

A `/ll:wire-issue --auto` run on a large issue should complete in under 5 minutes without manual intervention.

## Root Cause

Claude Code's Read tool returns `"File unchanged since last read"` when a file is re-read without changes. The subagents have no instruction to treat this as a stop signal. Similarly, when grep returns the same results as a prior search, there is no guidance to stop and synthesize.

The 3 subagent prompts in Phase 4 (SKILL.md lines 129-201) are purely goal-oriented with no anti-loop instructions, no tool-call budget, and no visited-file tracking.

## Proposed Solution

### 1. Add anti-loop stop condition to each subagent prompt

Append to each of the 3 prompts:

```
IMPORTANT: If you see "File unchanged since last read" when reading a file,
do NOT re-read it — use the content from your earlier read.
If a search returns results identical to a prior search, do NOT repeat it.
Stop and synthesize your findings immediately.
```

### 2. Add visited-file tracking instruction to each subagent prompt

Append to each of the 3 prompts:

```
Track which files and search patterns you have already queried.
Do NOT re-query the same file path or the same grep pattern a second time.
```

This addresses the underlying habit causing the loop, independent of the error message.

## Motivation

A wire-issue hang blocks the entire autodev loop. The fix is low-risk (adding instructions to existing prompts) and addresses a real recurring production hang. The changes are additive — they don't alter the research logic, only add stopping conditions.

## Implementation Steps

1. Open `skills/wire-issue/SKILL.md`
2. Locate Agent 1 prompt block (lines ~129-155), Agent 2 (~159-178), Agent 3 (~182-201)
3. Append the 2 instruction blocks (anti-loop, visited-file tracking) to each of the 3 prompts
4. Keep existing prompt content intact — append only, do not replace
5. Test by running `/ll:wire-issue --auto --dry-run` on a broad-scope issue and verifying subagents complete

## Integration Map

### Files to Modify

- `skills/wire-issue/SKILL.md` — Phase 4 subagent prompts (Agent 1: ~lines 129-155, Agent 2: ~lines 159-178, Agent 3: ~lines 182-201)

### Tests

- Manual: run `/ll:wire-issue --auto --dry-run` on a large issue and verify all 3 agents complete without looping
- No unit test coverage exists for skill files (they are LLM instruction documents)

### Dependent Files (Callers/Importers)
- N/A — skill files are invoked by Claude Code directly; no code imports them

### Similar Patterns
- Other skills with subagent prompts (e.g., `skills/refine-issue/SKILL.md`, `skills/manage-issue/SKILL.md`) may benefit from similar anti-loop hardening

### Documentation
- N/A — no documentation changes required for this prompt-level fix

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Adding anti-loop stop conditions, tool-call budget, and visited-file tracking to the 3 Phase 4 subagent prompts in `skills/wire-issue/SKILL.md`
- **Out of scope**: Changes to Phase 1, 2, or 3 of wire-issue; changes to other skills' subagent prompts; automated retry logic; programmatic loop detection

## Impact

- **Priority**: P2 — wire-issue hangs block the entire autodev loop; ~40-minute hang observed in production
- **Effort**: Small — additive changes to 3 existing prompt blocks in one skill file; no logic changes
- **Risk**: Low — additions do not alter research logic, only add stopping conditions; fully additive
- **Breaking Change**: No

## Labels

`enhancement`, `automation`, `reliability`, `wire-issue`

## Status

**Open** | Created: 2026-04-27 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-04-27T16:59:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ac2537a-c3f4-41a5-bfff-ceabdb529f5c.jsonl`

- `/ll:capture-issue` - 2026-04-27T16:55:56Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-04-27T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ae65452-a076-486e-8525-07b99c3425ce.jsonl`
