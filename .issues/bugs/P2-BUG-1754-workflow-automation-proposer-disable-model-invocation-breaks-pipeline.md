---
id: BUG-1754
title: workflow-automation-proposer disable-model-invocation breaks workflow analysis loop suggester pipeline
type: BUG
status: open
priority: P2
captured_at: '2026-05-27T21:16:34Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
---

# BUG-1754: workflow-automation-proposer disable-model-invocation breaks workflow analysis loop suggester pipeline

## Summary

`skills/workflow-automation-proposer/SKILL.md` has `disable-model-invocation: true` in its frontmatter, which was added as part of ENH-1394 to reduce listing budget. However, `workflow-automation-proposer` is Step 3 of the `analyze-workflows` command pipeline and is also used by `loop-suggester`. Because `disable-model-invocation: true` excludes the skill from the model's skill listing, the Skill tool invocation in `commands/analyze-workflows.md` (`skill: "ll:workflow-automation-proposer"`) may fail silently or be unavailable at runtime, breaking the end-to-end automation proposal pipeline.

## Current Behavior

`workflow-automation-proposer` has `disable-model-invocation: true` set in `skills/workflow-automation-proposer/SKILL.md:3`. The `analyze-workflows` command (Step 3, `commands/analyze-workflows.md:197`) explicitly invokes it via `Skill tool`. When this flag is set, the skill is stripped from the model's available-skills listing — meaning the Skill tool may not be able to resolve and execute it, causing Step 3 to fail or be skipped.

## Expected Behavior

`workflow-automation-proposer` should be invocable via Skill tool as Step 3 in the workflow analysis pipeline. Either:
1. Remove `disable-model-invocation: true` from this skill (it is pipeline-internal, not a user-facing operational/maintenance skill), or
2. The harness should distinguish between "exclude from listing budget" and "exclude from Skill tool invocation" — pipeline skills should be callable even when excluded from listings.

## Root Cause

- **File**: `skills/workflow-automation-proposer/SKILL.md`
- **Line**: `disable-model-invocation: true` (line 3)
- **Explanation**: ENH-1394 applied `disable-model-invocation: true` broadly to operational skills but incorrectly included `workflow-automation-proposer`, which is a pipeline step (not a standalone maintenance skill). The flag was designed to reduce listing budget overhead, not to block programmatic Skill tool invocations.

## Steps to Reproduce

1. Run `/ll:analyze-workflows` on a project with message history
2. Observe Step 3 (Automation Proposals) — the Skill tool call for `ll:workflow-automation-proposer` fails or returns no output
3. Or run `/ll:loop-suggester` and trace whether it can hand off to the proposer

## Impact

- `analyze-workflows` produces incomplete output (Steps 1+2 succeed, Step 3 silently fails)
- `loop-suggester` pipeline cannot complete automation proposals
- Users get no automation recommendations despite workflow patterns being identified

## Implementation Notes

Simplest fix: remove `disable-model-invocation: true` from `skills/workflow-automation-proposer/SKILL.md`. This skill's description is minimal (~100 chars) and it is genuinely needed by the model at runtime when `analyze-workflows` invokes it. If listing budget remains a concern, investigate whether Step 3 can be refactored to a non-skill mechanism (e.g., inline prompt in the command) instead.

Verify fix by running `ll-verify-skill-budget` before and after to confirm the listing stays within budget.

## Related Issues

- ENH-1394: Add `disable-model-invocation: true` to Operational Skills (done — incorrectly classified proposer as operational)
- P4-ENH-1497: Adapt disable-model-invocation skills for Codex

## Session Log
- `/ll:capture-issue` - 2026-05-27T21:16:34Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d76f6684-f28b-48e1-8feb-af054e035afe.jsonl`

---

## Status

`open`
