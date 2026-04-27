---
id: ENH-1305
type: ENH
priority: P2
title: "wire-issue: harden Phase 4 subagent prompts against infinite loops"
status: backlog
captured_at: "2026-04-27T16:55:56Z"
discovered_date: "2026-04-27"
discovered_by: capture-issue
---

# ENH-1305: wire-issue: harden Phase 4 subagent prompts against infinite loops

## Problem

`/ll:wire-issue` Phase 4 spawns 3 parallel subagents (codebase-locator, codebase-analyzer, codebase-pattern-finder) with **no stopping conditions**. When the autodev loop runs wire-issue on large issues, all 3 subagents enter infinite loops and the step never completes.

Observed failure mode (reported from another project):
- Agent 1 (codebase-locator): 600+ repetitions of "File unchanged since last read"
- Agent 2 (codebase-analyzer): 280+ repetitions of "File unchanged since last read"
- Agent 3 (codebase-pattern-finder): repeating identical grep results indefinitely

The hang was observed during a `/ll:wire-issue --auto` run on a broad-scope issue (5+ files, 32+ line references). The loop waited ~40 minutes before being killed manually.

## Root Cause

Claude Code's Read tool returns `"File unchanged since last read"` when a file is re-read without changes. The subagents have no instruction to treat this as a stop signal. Similarly, when grep returns the same results as a prior search, there is no guidance to stop and synthesize.

The 3 subagent prompts in Phase 4 (SKILL.md lines 129-201) are purely goal-oriented with no anti-loop instructions, no tool-call budget, and no visited-file tracking.

## Proposed Fix

### 1. Add anti-loop stop condition to each subagent prompt

Append to each of the 3 prompts:

```
IMPORTANT: If you see "File unchanged since last read" when reading a file,
do NOT re-read it — use the content from your earlier read.
If a search returns results identical to a prior search, do NOT repeat it.
Stop and synthesize your findings immediately.
```

### 2. Add tool-call budget to each subagent prompt

Append to each of the 3 prompts:

```
Complete your research in no more than 20 tool calls.
Prioritize breadth over depth — if you've covered the main files, synthesize.
```

This provides a concrete stopping condition that doesn't depend on the agent recognizing error messages.

### 3. Add visited-file tracking instruction to each subagent prompt

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
3. Append the 3 instruction blocks (anti-loop, tool-call budget, visited-file tracking) to each of the 3 prompts
4. Keep existing prompt content intact — append only, do not replace
5. Test by running `/ll:wire-issue --auto --dry-run` on a broad-scope issue and verifying subagents complete

## Integration Map

### Files to Modify

- `skills/wire-issue/SKILL.md` — Phase 4 subagent prompts (Agent 1: ~lines 129-155, Agent 2: ~lines 159-178, Agent 3: ~lines 182-201)

### Tests

- Manual: run `/ll:wire-issue --auto --dry-run` on a large issue and verify all 3 agents complete without looping
- No unit test coverage exists for skill files (they are LLM instruction documents)

## Session Log

- `/ll:capture-issue` - 2026-04-27T16:55:56Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
