---
type: BUG
id: BUG-449
title: Init wizard Round 5 can exceed AskUserQuestion 4-question limit
priority: P1
status: open
created: 2026-02-22
---

# Init wizard Round 5 can exceed AskUserQuestion 4-question limit

## Summary

When a user selects multiple features in Round 3 (parallel + context monitoring + GitHub sync + confidence gate), Round 5 dynamically builds follow-up questions that can total 5-6 questions. `AskUserQuestion` only supports a maximum of 4 questions per call, so the wizard will fail or behave unexpectedly.

## Reproduction

1. Run `/ll:init --interactive`
2. In Round 3, select all 4 features: "Parallel processing", "Context monitoring", "GitHub sync", "Confidence gate"
3. If "Yes, custom directory" was also selected in Round 2 for issues, Round 5 needs 6 questions:
   - `issues_path` (from Round 2 custom dir)
   - `worktree_files` (parallel)
   - `threshold` (context monitoring)
   - `priority_labels` (GitHub sync)
   - `sync_completed` (GitHub sync)
   - `gate_threshold` (confidence gate)

## Expected Behavior

Round 5 should split into multiple AskUserQuestion calls when more than 4 questions are needed, or reorganize the questions to stay within limits.

## Current Behavior

The skill definition shows all 6 possible questions in a single `questions:` block with no overflow strategy documented.

## Fix

Add logic to `interactive.md` Round 5 to split questions into batches of 4 when more than 4 conditions are active. E.g., "Round 5a" and "Round 5b".

## Files

- `skills/init/interactive.md` (Round 5 section, lines ~287-401)
