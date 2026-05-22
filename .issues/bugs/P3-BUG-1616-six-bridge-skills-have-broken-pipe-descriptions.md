---
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
---

# BUG-1616: Six bridge skills have broken pipe-character descriptions

## Summary

Six `ll-*` bridge skills have `description: |` (YAML block scalar indicator with no content) as their frontmatter description. The skill budget checker records them as 0-token entries, but they still consume listing slots in the flat skill registry. Claude receives no routing information for these skills — they are dead weight in the listing.

Affected skills: `ll-loop-suggester`, `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`.

## Current Behavior

`check_skill_budget()` in `doc_counts.py` reports these six skills with description `|` and 0 tokens. The YAML block scalar indicator was written to the frontmatter without a body value. These skills appear in the skill listing but provide no routing signal — Claude cannot match them to natural-language requests because the description field is effectively empty.

## Expected Behavior

Each of the six skills has a valid single-line description (≤100 chars) following the trigger-first convention. Example for `ll-loop-suggester`: `Analyze user message history to suggest FSM loop configurations automatically.` (matching the existing `metadata.short-description`).

Alternatively, if ENH-1615 is implemented first (adding `disable-model-invocation: true` to all bridge skills), the description field becomes irrelevant for Claude Code routing and can be set to any valid value.

## Impact

- **Priority**: P3 — wastes listing slots but doesn't block functionality
- **Effort**: Small — fix 6 description fields in `skills/ll-*/SKILL.md`
- **Risk**: None
- **Breaking Change**: No

## Labels

`bug`, `skills`, `context-engineering`, `data-quality`

## Session Log
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3
