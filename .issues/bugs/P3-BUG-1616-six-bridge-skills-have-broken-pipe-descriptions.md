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

## Steps to Reproduce

1. Run `ll-verify-skill-budget` (or inspect `check_skill_budget()` in `scripts/little_loops/doc_counts.py`).
2. Open any of the six affected bridge skills, e.g. `skills/ll-loop-suggester/SKILL.md`.
3. Observe: the frontmatter `description:` field is a bare `|` block scalar indicator with no indented body, so the parsed description is an empty string and the budget checker records the skill as a 0-token entry.

## Expected Behavior

Each of the six skills has a valid single-line description (≤100 chars) following the trigger-first convention. Example for `ll-loop-suggester`: `Analyze user message history to suggest FSM loop configurations automatically.` (matching the existing `metadata.short-description`).

Alternatively, if ENH-1615 is implemented first (adding `disable-model-invocation: true` to all bridge skills), the description field becomes irrelevant for Claude Code routing and can be set to any valid value.

## Motivation

The skill listing has a finite token budget. Six skills currently occupy listing slots while contributing zero routing signal — pure waste with no benefit. Fixing the descriptions either restores model-invocation routing for six skills or, if ENH-1615 lands first, confirms the field is intentionally inert. Either way removes ambiguity from the registry.

## Root Cause

- **File**: `skills/ll-loop-suggester/SKILL.md` (and `ll-manage-release`, `ll-open-pr`, `ll-review-sprint`, `ll-sync-issues`, `ll-tradeoff-review-issues`)
- **Anchor**: frontmatter `description:` field
- **Cause**: a YAML block scalar indicator (`|`) was written without an indented body line, so the parser yields an empty string instead of a description. Likely introduced by a generator (e.g. `ll-adapt-skills-for-codex` or `ll-generate-skill-descriptions`) that emitted the indicator before the body value was available.

## Proposed Solution

For each of the six `skills/ll-*/SKILL.md` files, replace the empty `description: |` with a valid ≤100-char single-line, trigger-first description. Reuse the existing `metadata.short-description` value where present to keep the two fields consistent.

If ENH-1615 (adding `disable-model-invocation: true` to all bridge skills) is implemented first, the description still needs a non-empty valid value but its routing content no longer matters — coordinate ordering with that issue.

## Integration Map

### Files to Modify
- `skills/ll-loop-suggester/SKILL.md`
- `skills/ll-manage-release/SKILL.md`
- `skills/ll-open-pr/SKILL.md`
- `skills/ll-review-sprint/SKILL.md`
- `skills/ll-sync-issues/SKILL.md`
- `skills/ll-tradeoff-review-issues/SKILL.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/doc_counts.py` — `check_skill_budget()` reads these descriptions (no code change required)

### Similar Patterns
- Other `skills/ll-*/SKILL.md` bridge skills — verify none share the same empty-description defect

### Tests
- `ll-verify-skill-budget` — should be re-run after the fix; confirm the six skills no longer report 0 tokens

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Confirm the existing `metadata.short-description` value for each of the six skills.
2. Replace the empty `description: |` frontmatter field with a valid ≤100-char trigger-first description.
3. Re-run `ll-verify-skill-budget` to confirm non-zero token counts and that the listing budget is still within limits.

## Impact

- **Priority**: P3 — wastes listing slots but doesn't block functionality
- **Effort**: Small — fix 6 description fields in `skills/ll-*/SKILL.md`
- **Risk**: Low — frontmatter-only edits to six files, verifiable with `ll-verify-skill-budget`
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `skills`, `context-engineering`, `data-quality`

## Session Log
- `/ll:format-issue` - 2026-05-22T22:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da2cdb66-57d9-4b9e-ad13-a2228c32b4d3.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3
