---
discovered_date: 2026-05-05
discovered_by: session-observation
confidence_score: 100
outcome_confidence: 95
blocked_by: []
status: done
completed_at: 2026-05-05T00:00:00Z
---

# ENH-1370: Strip Redundant Trigger Keywords from Skill Descriptions

## Summary

Removed the `Trigger keywords: "...", "..."` enumeration lines from all 28 `SKILL.md` frontmatter descriptions, reducing total description size by 42% (9,932 → 5,669 chars). This resolves the "40 Skills Dropped" warning from `skillListingBudgetFraction` overflow without touching skill logic or reducing routing effectiveness.

## Problem Observed

Claude Code reported at startup:

```
Skill listing will be truncated
  40 descriptions dropped (full descriptions kept for most-used skills) (2.2%/1% of context)
  run /skills to disable some, or raise skillListingBudgetFraction (currently 1%) in settings.json
```

The skill listing budget (1% of context) was exceeded because all 28 skills had two-part descriptions: a "Use when..." prose sentence followed by a blank line and a `Trigger keywords: ...` enumeration.

## Root Cause

ENH-493 (completed 2026-04-01) rewrote all skill descriptions as trigger documents — "Use when..." sentences that directly describe activation conditions. The `Trigger keywords:` enumeration lines added alongside them were redundant: every keyword in the list was already expressed semantically in the prose sentence above it. The duplication added ~4,200 chars of listing budget with no additional routing signal.

ENH-494 (500-line SKILL.md body limit) was considered but does not address this problem — it targets context consumed when a skill is *running*, not the skill *listing* budget consumed at startup.

## Why "Use when..." was kept (not keywords)

Claude Code routes skills via semantic matching against the `description` field, not keyword lookup. The "Use when..." prose is the richer trigger document ENH-493 was designed to produce. The keyword lists were the redundant half.

Removing the prose and keeping only keywords would have regressed ENH-493: brittle exact-match routing instead of semantic activation.

## Implementation

Single Python script pass across all `skills/*/SKILL.md` files:

```python
re.sub(r'(\n\n  (?:Trigger keywords|TRIGGER):[^\n]*)', '', content)
```

All 28 files modified; zero files with `Trigger keywords` remaining.

## Result

| Metric | Before | After |
|--------|--------|-------|
| Total description chars | 9,932 | 5,669 |
| Reduction | — | 4,263 chars (42%) |
| Skills with trigger keyword lines | 28 | 0 |

## Impact

- **No skill logic changed** — body content, tool lists, model settings all untouched
- **No routing regression** — "Use when..." prose retained; semantic matching unaffected
- **Listing budget freed** — 42% reduction in ll's contribution to `skillListingBudgetFraction`

## Labels

`enhancement`, `skills`, `context-engineering`, `skill-listing-budget`

## Status

**Completed** | Created: 2026-05-05 | Resolved: 2026-05-05 | Priority: P3

## Resolution

- **Resolved**: 2026-05-05
- **Action**: improve
- **Changes**: Stripped `Trigger keywords: ...` enumeration lines from all 28 `skills/*/SKILL.md` frontmatter descriptions
- **Files modified**: 28 `SKILL.md` files
