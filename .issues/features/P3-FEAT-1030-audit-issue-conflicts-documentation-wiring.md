---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 85
outcome_confidence: 80
parent_issue: FEAT-1029
blocked_by: FEAT-1028
---

# FEAT-1030: audit-issue-conflicts — Documentation Wiring

## Summary

Update all registry files and documentation to expose the new `audit-issue-conflicts` skill after FEAT-1028 creates it. Depends on FEAT-1028 (skill file must exist first).

## Motivation

After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill exists but is invisible — absent from help listings, README tables, all documentation surfaces, and uncovered by `ll-verify-docs`. This issue ensures full discoverability and registry consistency.

## Use Case

**Who**: A little-loops developer or plugin maintainer

**Context**: After FEAT-1028 creates `skills/audit-issue-conflicts/SKILL.md`, the skill works but is absent from every discovery surface.

**Goal**: Wire the new skill into all documentation files so users can find it and `ll-verify-docs` passes.

**Outcome**: `audit-issue-conflicts` appears in all expected places; skill count bumped 25→26 everywhere; `ll-verify-docs` passes.

## Parent Issue

Decomposed from FEAT-1029: audit-issue-conflicts — Wiring, Docs, and Tests

## Acceptance Criteria

- [ ] `commands/help.md` — `/ll:audit-issue-conflicts` added to ISSUE REFINEMENT block (lines 44–81) and Quick Reference Table (`Issue Refinement` entry, ~line 254)
- [ ] `README.md` — skill count bumped `25 → 26` (line 89); `/ll:audit-issue-conflicts` row added to Issue Refinement command table (lines 108–124); `/ll:audit-issue-conflicts`^ row added to Skills table (lines 207–235) with capability group "Issue Refinement"
- [ ] `CONTRIBUTING.md` — skill count bumped `25 → 26` (line 125); `audit-issue-conflicts/` added to skill directory tree after `audit-docs/`
- [ ] `docs/ARCHITECTURE.md` — skill count bumped `25 → 26` at lines 26 and 99; `├── audit-issue-conflicts/` added between `audit-claude-config/` and `audit-docs/` (lines 104–107)
- [ ] `docs/reference/COMMANDS.md` — `audit-issue-conflicts` in `--dry-run` consumer list (line 14) and `--auto` consumer list (line 15); `### /ll:audit-issue-conflicts` subsection added after `/ll:tradeoff-review-issues` (~line 204)
- [ ] `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `audit-issue-conflicts` added to "Plan a Feature Sprint" recipe (~line 484) as step 3.5 before `tradeoff-review-issues`; current steps 4–11 renumbered to 5–12
- [ ] `.claude/CLAUDE.md` — `audit-issue-conflicts`^ added to Issue Refinement section; skill count bumped `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
- [ ] `ll-verify-docs` passes after all changes

## Proposed Solution

### Wiring Steps

Work through each file in order. All changes are mechanical and well-specified:

**`commands/help.md`**
- Add `/ll:audit-issue-conflicts` entry to ISSUE REFINEMENT block (lines 44–81)
- Add entry to Quick Reference Table (`Issue Refinement:` entry, ~line 254)

**`README.md`**
- Bump skill count `25 → 26` at line 89
- Add `/ll:audit-issue-conflicts` row to Issue Refinement command table (lines 108–123)
- Add `/ll:audit-issue-conflicts`^ row to Skills table (lines 207–235, three-column format with `^` suffix and "Issue Refinement" capability group)

**`CONTRIBUTING.md`**
- Bump skill count `25 → 26` at line 125
- Add `audit-issue-conflicts/` to skill directory tree after `audit-docs/` (lines 125–148)

**`docs/ARCHITECTURE.md`**
- Bump skill count `25 → 26` at lines 26 and 99
- Add `├── audit-issue-conflicts/` between `audit-claude-config/` and `audit-docs/` (lines 104–107)

**`docs/reference/COMMANDS.md`**
- Append `, \`audit-issue-conflicts\`` to `--dry-run` consumer cell (line 14)
- Append `, \`audit-issue-conflicts\`` to `--auto` consumer cell (line 15)
- Add `### /ll:audit-issue-conflicts` subsection after `/ll:tradeoff-review-issues` (~line 204):
  ```
  Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types detected: requirement contradictions, conflicting objectives, architectural disagreements, and scope overlaps.

  **Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written)

  **Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"
  ```

**`docs/guides/ISSUE_MANAGEMENT_GUIDE.md`**
- "Plan a Feature Sprint" heading at line 475; recipe block runs lines 479–492 with steps 1–11
- Insert `/ll:audit-issue-conflicts` between step 3 (`prioritize-issues`) and current step 4 (`tradeoff-review-issues`), renumbering all subsequent steps (4→5, 5→6, … 11→12)

**`.claude/CLAUDE.md`**
- Add `audit-issue-conflicts`^ to Issue Refinement section in command list
- Bump skill count `25 → 26` at line 38 (`# Skill definitions (25 skills)`)
- Note: `ll-verify-docs` does NOT scan `.claude/CLAUDE.md`, so this drift is silent — must be caught manually

## Integration Map

### Files to Modify

- `commands/help.md` — ISSUE REFINEMENT block + Quick Reference Table
- `README.md` — skill count (line 89) + Issue Refinement command table row (lines 108–124) + Skills table row (lines 207–235)
- `CONTRIBUTING.md` — skill count + directory tree entry
- `docs/ARCHITECTURE.md` — skill count (×2) + directory listing entry
- `docs/reference/COMMANDS.md` — `--dry-run` list (line 14) + `--auto` list (line 15) + new subsection after `tradeoff-review-issues`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "Plan a Feature Sprint" recipe (insert at step 4, renumber 4–11 to 5–12)
- `.claude/CLAUDE.md` — command list (Issue Refinement section) + skill count bump

### Codebase Research Findings

- All line numbers verified accurate as of 2026-04-11
- `docs/reference/COMMANDS.md` line 14 = `--dry-run` consumer list, line 15 = `--auto` consumer list
  - Line 14: `| \`--dry-run\` | Show what would happen without making changes | \`manage-issue\`, \`align-issues\`, \`refine-issue\`, \`format-issue\`, \`manage-release\` |`
  - Line 15: `| \`--auto\` | Non-interactive mode (no prompts) | \`commit\`, \`refine-issue\`, \`prioritize-issues\`, \`format-issue\`, \`confidence-check\`, \`verify-issues\`, \`map-dependencies\`, \`issue-size-review\` |`
  - Append `, \`audit-issue-conflicts\`` to the pipe-delimited consumer cell in each row
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` "Plan a Feature Sprint" heading is at line 475; recipe block runs lines 479–492 with steps 1–11

## Implementation Steps

1. **Verify FEAT-1028 is complete** — confirm `skills/audit-issue-conflicts/SKILL.md` exists before proceeding
2. **Update `commands/help.md`** — ISSUE REFINEMENT block entry + Quick Reference Table entry
3. **Update `README.md`** — skill count `25→26`; Issue Refinement command table row; Skills table row
4. **Update `CONTRIBUTING.md`** — skill count `25→26`; directory tree entry
5. **Update `docs/ARCHITECTURE.md`** — skill count `25→26` at lines 26 and 99; directory listing entry
6. **Update `docs/reference/COMMANDS.md`** — `--dry-run` list, `--auto` list, new subsection
7. **Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`** — insert step 4, renumber 4–11 to 5–12
8. **Update `.claude/CLAUDE.md`** — `audit-issue-conflicts`^ to Issue Refinement section; skill count bump
9. **Run `ll-verify-docs`** — confirm passes

## Impact

- **Priority**: P3 - Medium value
- **Effort**: Small - Mechanical wiring; no logic to implement
- **Risk**: Very Low - Documentation changes only
- **Breaking Change**: No

## Labels

`feature`, `issue-management`, `audit`, `wiring`, `docs`

## Status

**Open** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
