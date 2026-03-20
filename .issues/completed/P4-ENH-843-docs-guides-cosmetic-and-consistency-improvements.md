---
id: ENH-843
type: ENH
priority: P4
status: Open
title: "docs/guides: cosmetic and consistency improvements (post-audit remaining items)"
created: 2026-03-20
testable: false
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

- `docs/guides/SPRINT_GUIDE.md:419-421` — "Full Plan a Feature Sprint Pipeline" recipe section (**CONFIRMED complete** — lines 419-421 already contain the one-sentence cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`; skip in implementation)
- `docs/guides/LOOPS_GUIDE.md:74,77,80,83,86,89` — `──▶` arrows in use-case pattern tree (diagram block lines 72–91)
- `docs/guides/LOOPS_GUIDE.md:192` — bare `▶` arrow in `ll-loop show` walkthrough box-drawing diagram
- `docs/guides/LOOPS_GUIDE.md:526,563,598,637,676` — `### \`apo-*\`` headings missing `---` separators before them
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:390` — `action_type: prompt` on `execute` state of `harness-check-code` Variant A YAML

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Item 1 already done**: `docs/guides/SPRINT_GUIDE.md:419-421` already contains the one-sentence cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`. Git shows `SPRINT_GUIDE.md` is modified — verify with `git diff docs/guides/SPRINT_GUIDE.md` before implementing.
- **Item 2 exact pattern**: Change `▶` → `→` at end of dash-sequences on lines 74, 77, 80, 83, 86, 89, and 192. All other occurrences of `──→` (lines 181–187, 558–779) confirm `→` is the standard.
- **Item 3 exact lines**: Insert `---` + blank line before lines 526, 563, 598, 637, 676. Lines before each heading are blank (following either a prose sentence or a ` ``` ` closing fence).
- **Item 4 exact line**: `AUTOMATIC_HARNESSING_GUIDE.md:390` — `action_type: prompt` → `action_type: slash_command`. Reference pattern at line 180 (`check_skill` with `action_type: slash_command`). Note: `action_type: prompt` at lines 199, 204, 451, 505, 637 are intentional (free-form NL actions, not `/ll:` commands).
- **Cross-reference target**: `ISSUE_MANAGEMENT_GUIDE.md:408` — `### Plan a Feature Sprint` (anchor: `#plan-a-feature-sprint`); within `## Common Workflows (Recipes)` at line 391.

## Implementation Steps

1. `SPRINT_GUIDE.md`: **SKIP — already complete.** Lines 419-421 confirmed to contain the one-sentence cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`.
2. `LOOPS_GUIDE.md:74,77,80,83,86,89,192`: Replace `▶` → `→` at the end of each arrow sequence. Edit only the closing character; preserve dash/box-drawing prefix. Verify with `grep -n '▶' docs/guides/LOOPS_GUIDE.md`.
3. `LOOPS_GUIDE.md:526,563,598,637,676`: Insert `---\n` before each `### \`apo-*\`` heading. Lines 563, 598, 637, 676 are preceded by a blank line after a closing ` ``` ` fence; line 526 is preceded by a blank after a prose sentence.
4. `AUTOMATIC_HARNESSING_GUIDE.md:390`: Change `action_type: prompt` → `action_type: slash_command` on the `execute` state only. Confirm surrounding context: `execute:` at line 388, `action: /ll:check-code --auto` at line 389, `next: check_concrete` at line 391. Do **not** touch other intentional `action_type: prompt` occurrences at lines 199, 204, 451, 505, 637.

## Labels

`documentation`, `cosmetic`, `captured`

## Scope Boundaries

- Changes are limited to the three guide files listed in the Integration Map
- No changes to code, schemas, or non-documentation files
- Item 1 (SPRINT_GUIDE.md cross-reference) is already complete; remaining scope is items 2–4 only
- Arrow style unification applies only to LOOPS_GUIDE.md ASCII diagrams; do not alter other files for consistency
- Do not change `action_type: prompt` occurrences that are intentional (lines 199, 204, 451, 505, 637 of AUTOMATIC_HARNESSING_GUIDE.md)

## Resolution

**Completed** | 2026-03-20

- Item 1 (`SPRINT_GUIDE.md` cross-reference): already complete prior to this session — skipped.
- Item 2 (`LOOPS_GUIDE.md` arrow styles): replaced all `▶` with `→` at lines 74, 77, 80, 83, 86, 89, 192.
- Item 3 (`LOOPS_GUIDE.md` APO separators): inserted `---` before each of the five `### \`apo-*\`` headings (before lines 526, 563, 598, 637, 676).
- Item 4 (`AUTOMATIC_HARNESSING_GUIDE.md:390`): changed `action_type: prompt` → `action_type: slash_command` on the `execute` state of `harness-check-code` Variant A.

## Status

**Completed** | Captured: 2026-03-20 | Source: `/ll:audit-docs docs/guides/`


## Session Log
- `/ll:ready-issue` - 2026-03-20T19:28:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6274724-364d-4d8e-bce7-5e6142a84f94.jsonl`
- `/ll:refine-issue` - 2026-03-20T19:23:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eff6b70f-1b02-408c-b33e-25fc3b821c22.jsonl`
