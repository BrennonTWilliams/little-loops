---
discovered_date: 2026-05-07
discovered_by: user
status: done
completed_at: 2026-05-07T00:00:00Z
---

# BUG-1379: Skill descriptions exceed Claude Code context budget, causing 38 silent drops

## Summary

All 28 ll skill `description:` frontmatter fields used verbose block scalars averaging ~204 chars each (~1430 tokens total). Combined with built-in and other plugin skills, the aggregate exceeded Claude Code's default `skillListingBudgetFraction` (1% of context), causing Claude Code to silently drop skill descriptions for the 38 least-recently-used skills — including `ll:loop-suggester`, `ll:review-sprint`, `ll:improve-claude-md`, and 35 others. Without a description, Claude cannot route to the correct skill from natural-language prompts.

## Location

- **Files**: All `skills/*/SKILL.md` (28 files)
- **Field**: `description:` frontmatter block scalar

## Current Behavior

`/doctor` reported:

```
Skill listing will be truncated
  38 descriptions dropped (full descriptions kept for most-used skills) (1.8%/1% of context):
ll:loop-suggester, ll:review-sprint, ll:improve-claude-md, +35 more
    run /skills to disable some, or raise skillListingBudgetFraction (currently 1%) in settings.json
  Opting in would cost ~4k tokens for skills every session
```

## Expected Behavior

All 28 ll skill descriptions should fit within the default 1% context budget with room for other plugins. No descriptions should be dropped.

## Root Cause

Skill `description:` fields were written as full prose explanations — trigger conditions, elaboration, implementation notes, supported modes — that are appropriate in the skill body but unnecessary in the listing. The listing description only needs to help Claude decide *when* to invoke the skill; the full instructions load on-demand at invocation. Verbose descriptions consumed ~1430 tokens for ll alone, pushing the total above budget.

## Resolution

Trimmed all 28 `skills/*/SKILL.md` `description:` fields from verbose block scalars to single-line inline values (≤100 chars each). Kept essential trigger condition and key routing keywords; removed elaboration, examples, mode callouts, and implementation details.

- **Before**: 5,720 chars / ~1,430 tokens (~1.4% of 200k context for ll alone)
- **After**: 2,460 chars / ~615 tokens (~0.3% of context)
- **Reduction**: 57%

Format also changed from YAML block scalar (`description: |` + indented body) to plain inline (`description: text`), removing unnecessary syntax overhead.

Example (manage-issue):
```yaml
# Before
description: |
  Use when the user asks to implement an issue, work on a bug/feature/enhancement, manage
  an issue end-to-end, or says "start implementing FEAT-NNN." Autonomously plans,
  implements, verifies, and completes issues.

# After
description: Use when asked to implement an issue end-to-end or start implementing FEAT-NNN.
```

## Session Log
- Manual investigation + edits - 2026-05-07 - fix(skills): trim all 28 SKILL.md descriptions to fit Claude Code context budget

## Status

**Closed** | Created: 2026-05-07 | Resolved: 2026-05-07 | Priority: P3
