---
id: ENH-843
type: ENH
priority: P4
status: Open
title: "docs/guides: cosmetic and consistency improvements (post-audit remaining items)"
created: 2026-03-20
---

## Summary

Four low-severity documentation issues remain after the 2026-03-20 audit of `docs/guides/`. All are cosmetic or structural — no factual errors. Grouped here for a single clean-up pass rather than separate issues.

## Current Behavior

Four minor inconsistencies across three guide files:

1. **`SPRINT_GUIDE.md` — recipe near-duplication**: The "Full Plan a Feature Sprint Pipeline" recipe (end of Common Recipes section) near-duplicates the detailed 11-step workflow already in `ISSUE_MANAGEMENT_GUIDE.md`. A reader following the Sprint Guide has to scroll past a block they've already seen.

2. **`LOOPS_GUIDE.md` — mixed arrow styles in diagrams**: Three different arrow characters appear across the guide's ASCII diagrams: `──▶` (walkthrough), `──→` (harness FSM), `▶` (pattern tree). No semantic distinction — purely inconsistent.

3. **`LOOPS_GUIDE.md` — inconsistent `---` separators in APO sections**: The five APO subsections (`apo-feedback-refinement`, `apo-contrastive`, `apo-opro`, `apo-beam`, `apo-textgrad`) do not use `---` horizontal rule separators between them, while the rest of the guide uses `---` consistently between major sections.

4. **`AUTOMATIC_HARNESSING_GUIDE.md` — `action_type: prompt` vs `slash_command` in Variant A**: The generated single-shot harness example (`harness-check-code`) uses `action_type: prompt` for a `/ll:` slash command on the `execute` state, while `check_skill` in the same guide uses `action_type: slash_command`. The difference is explained in the guide's `action_type` table, but the Variant A YAML itself is internally inconsistent with the rest of the harness examples.

## Expected Behavior

1. "Full Plan a Feature Sprint Pipeline" recipe replaced with a short cross-reference to `ISSUE_MANAGEMENT_GUIDE.md` — eliminates duplication without losing information.
2. All ASCII diagrams in `LOOPS_GUIDE.md` use a single arrow style (`──→` preferred, as it is the most common in the file).
3. `---` separators added between each APO subsection (before each `###` heading within the APO section).
4. Variant A YAML updated to use `action_type: slash_command` on the `execute` state, matching `check_skill` and the guide's own recommendation.

## Impact

**Priority:** P4 / Low — cosmetic only; no user is blocked, confused, or misled.
**Affected files:** `docs/guides/SPRINT_GUIDE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`

## Integration Map

- `docs/guides/SPRINT_GUIDE.md` — "Full Plan a Feature Sprint Pipeline" recipe section
- `docs/guides/LOOPS_GUIDE.md` — ASCII diagrams throughout; APO sections (lines 526–739); Troubleshooting tips section
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Variant A YAML block (`harness-check-code` example)

## Implementation Steps

1. `SPRINT_GUIDE.md`: Replace "Full Plan a Feature Sprint Pipeline" recipe body with a one-sentence cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`.
2. `LOOPS_GUIDE.md` diagrams: Do a targeted find-replace of `──▶` → `──→` and `▶` → `→` in diagram blocks only (not prose).
3. `LOOPS_GUIDE.md` APO sections: Add `---` before each `### apo-*` heading within the APO section.
4. `AUTOMATIC_HARNESSING_GUIDE.md` Variant A: Change `action_type: prompt` → `action_type: slash_command` on the `execute` state of `harness-check-code`.

## Status

**Open** | Captured: 2026-03-20 | Source: `/ll:audit-docs docs/guides/`
