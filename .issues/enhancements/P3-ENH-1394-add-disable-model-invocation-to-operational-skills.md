---
captured_at: "2026-05-09T20:48:12Z"
discovered_date: 2026-05-09
discovered_by: capture-issue
---

# ENH-1394: Add `disable-model-invocation: true` to Operational Skills

## Summary

Tag ~15 maintenance/audit skills with `disable-model-invocation: true` in their frontmatter so Claude Code excludes their descriptions from the listing budget. This is the direct fix for the `/doctor` warning that 23 skill descriptions are being dropped (1.4% used vs 1% budget) every session.

## Current Behavior

All 28 skill descriptions are included in the listing budget regardless of whether the LLM needs to discover them. Skills like `update`, `cleanup-worktrees`, `analyze-history`, and `audit-claude-config` are always user-invoked by typing the command — yet their descriptions consume budget that causes other skills to be silently truncated.

## Expected Behavior

Operational/maintenance skills are tagged `disable-model-invocation: true`. Their descriptions are excluded from the listing budget. The total listing footprint drops from ~1.4% to ~0.6% (estimate), eliminating the truncation warning. Affected skills remain fully functional — users can still type them explicitly; they just won't appear in the LLM's skill routing list.

## Motivation

Every session, Claude Code silently drops 23 skill descriptions due to budget overflow. The MRU algorithm keeps recently-used skills and drops the rest, making rarely-used skills unroutable by the LLM unless the user already knows the skill name. As more skills are added, this problem compounds. The fix is principled: skills that are always user-invoked don't need LLM routing and shouldn't occupy listing budget.

## Proposed Solution

Add `disable-model-invocation: true` to the YAML frontmatter of each operational skill's `SKILL.md`.

**Skills to tag (always user-invoked, never need LLM routing):**
- `update` — explicit maintenance command
- `cleanup-worktrees` — explicit maintenance command
- `cleanup-loops` — explicit maintenance command
- `rename-loop` — explicit loop management
- `review-loop` — explicit loop audit
- `debug-loop-run` — explicit loop debugging
- `audit-loop-run` — explicit loop audit
- `issue-workflow` — quick reference card
- `analyze-history` — explicit analysis trigger
- `audit-docs` — explicit audit trigger
- `update-docs` — explicit update trigger
- `improve-claude-md` — explicit improvement trigger
- `map-dependencies` — explicit dependency analysis
- `audit-issue-conflicts` — explicit conflict audit
- `audit-claude-config` — explicit config audit
- `issue-size-review` — explicit planning review
- `tradeoff-review-issues` — explicit planning review

**Skills that MUST remain LLM-discoverable (natural language routing):**
- `capture-issue`, `manage-issue`, `configure`, `init`, `go-no-go`, `confidence-check`
- `wire-issue`, `format-issue`, `create-loop`, `workflow-automation-proposer`
- `create-eval-from-issues`, `product-analyzer`, `decide-issue`, `audit-architecture`

## Implementation Steps

1. For each skill in the "to tag" list above, open `skills/<name>/SKILL.md`
2. Add `disable-model-invocation: true` to the YAML frontmatter block (or create frontmatter if absent)
3. After all edits, run `/doctor` to verify the truncation warning is gone
4. Run `/skills` to confirm tagged skills still appear in the available list

## Integration Map

### Files to Modify
- `skills/update/SKILL.md` — add frontmatter flag
- `skills/cleanup-worktrees/SKILL.md` — add frontmatter flag
- `skills/cleanup-loops/SKILL.md` — add frontmatter flag
- `skills/rename-loop/SKILL.md` — add frontmatter flag
- `skills/review-loop/SKILL.md` — add frontmatter flag
- `skills/debug-loop-run/SKILL.md` — add frontmatter flag
- `skills/audit-loop-run/SKILL.md` — add frontmatter flag
- `skills/issue-workflow/SKILL.md` — add frontmatter flag
- `skills/analyze-history/SKILL.md` — add frontmatter flag
- `skills/audit-docs/SKILL.md` — add frontmatter flag
- `skills/update-docs/SKILL.md` — add frontmatter flag
- `skills/improve-claude-md/SKILL.md` — add frontmatter flag
- `skills/map-dependencies/SKILL.md` — add frontmatter flag
- `skills/audit-issue-conflicts/SKILL.md` — add frontmatter flag
- `skills/audit-claude-config/SKILL.md` — add frontmatter flag
- `skills/issue-size-review/SKILL.md` — add frontmatter flag
- `skills/tradeoff-review-issues/SKILL.md` — add frontmatter flag

### Dependent Files (Callers/Importers)
- N/A — frontmatter flag is read by Claude Code harness, not by project code

### Similar Patterns
- N/A — this is a novel field in this project; no existing examples to follow

### Tests
- N/A — no automated test for this; verification is `/doctor` output

### Documentation
- `CONTRIBUTING.md` — add note that operational skills use this flag (covered by ENH-1395)
- `.claude/CLAUDE.md` — no change needed

### Configuration
- N/A

## Impact

- **Priority**: P3 — active session-quality issue; truncation happens every session
- **Effort**: Low — frontmatter edits only, ~17 files
- **Risk**: Very low — flag removes descriptions from LLM listing; skills remain fully functional
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `ux`

## Status

**Open** | Created: 2026-05-09 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`
