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

## Steps to Reproduce

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

## Actual Behavior

When all 4 optional features are selected in Round 3 plus a custom issues directory path chosen in Round 2, Round 5 attempts to present 6 questions in a single `AskUserQuestion` call. This exceeds the tool's 4-question limit, causing the wizard to fail or silently truncate the question list, leaving some advanced settings unconfigured.

## Proposed Solution

Add logic to `interactive.md` Round 5 to split questions into batches of 4 when more than 4 conditions are active. E.g., "Round 5a" and "Round 5b".

## Root Cause

- **File**: `skills/init/interactive.md`
- **Anchor**: `Round 5 section (lines ~287-401)`
- **Cause**: Round 5 builds questions dynamically based on feature selections but has no overflow strategy. The maximum combination (parallel + context monitor + GitHub sync + confidence gate + custom issues dir from Round 2) produces 6 questions, exceeding the AskUserQuestion 4-question limit.

## Location

- **File**: `skills/init/interactive.md`
- **Lines**: ~287-401
- **Anchor**: `Round 5 — Advanced Settings`

## Motivation

When users enable all optional features during init, the wizard silently fails or behaves unexpectedly at Round 5. This breakage occurs at the exact moment users are most actively configuring the tool, undermining trust in the wizard flow and preventing proper configuration.

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — Round 5: add "Round 5a"/"Round 5b" split logic when question count > 4

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md` — wizard orchestration; Round 5 is invoked from main skill flow

### Similar Patterns
- N/A — no existing overflow handling for AskUserQuestion in other wizard rounds

### Tests
- N/A — skills don't have unit tests; integration tested via usage

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Count all possible Round 5 question conditions in `interactive.md` and identify the maximum
2. Add overflow logic: if active question count > 4, split into Round 5a (first 4 questions) and Round 5b (remaining)
3. Verify that all 6-question combinations are handled correctly without dropping any question

## Impact

- **Priority**: P1 — Blocks onboarding for users who enable all features; wizard fails silently
- **Effort**: Small — Localised change to Round 5 of interactive.md only
- **Risk**: Low — Additive; only affects the overflow condition; behavior unchanged when ≤4 questions are active
- **Breaking Change**: No

## Labels

`bug`, `init`, `interactive-wizard`, `askuserquestion`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocks

- ENH-451
- ENH-454
- ENH-455
- ENH-456
- ENH-457

---

## Status

**Open** | Created: 2026-02-22 | Priority: P1
