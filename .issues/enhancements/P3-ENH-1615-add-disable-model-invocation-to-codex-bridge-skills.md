---
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
---

# ENH-1615: Add disable-model-invocation to all 28 ll-* Codex bridge skills

## Summary

The 28 `ll-*` bridge skills (e.g., `ll-align-issues`, `ll-commit`, `ll-help`) are 11-line stubs that bridge `commands/*.md` to the Codex Skills API. They consume 388/720 tokens (54%) of the skill listing budget but provide zero routing value for Claude Code users — Claude Code already routes through the identically-named slash commands. Adding `disable-model-invocation: true` to all 28 would cut the listing budget from 720 to ~332 tokens with no functional impact for Claude Code users.

## Current Behavior

All 28 `ll-*` skills are LLM-discoverable (no `disable-model-invocation`). Their descriptions appear in the listing budget alongside the real Tier 1 skills. Each bridge skill is an 11-line stub referencing its source command file. Six of them have broken `|` descriptions (covered by BUG-1616). Combined, they represent 54% of the total skill listing budget.

## Expected Behavior

All 28 `ll-*` bridge skills have `disable-model-invocation: true`. Claude Code users invoke skills through the existing slash commands (`commands/*.md`) — the bridges are only needed for Codex CLI discovery. The listing budget drops from 720 to ~332 tokens. Codex users are unaffected since Codex discovers skills via the `agents/openai.yaml` sidecar, not via the listing budget.

## Impact

- **Priority**: P3 — structural budget waste, no user-facing bug
- **Effort**: Small — bulk `disable-model-invocation: true` insertion into 28 SKILL.md frontmatter blocks
- **Risk**: None — additive field only; does not change invocation behavior for Claude Code or Codex
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `context-engineering`, `budget`

## Session Log
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3
