---
id: FEAT-1407
type: FEAT
priority: P2
status: open
parent_issue: FEAT-1389
captured_at: '2026-05-09T00:00:00Z'
discovered_date: '2026-05-09'
---

# FEAT-1407: EPIC Type — Skills, Commands, and Documentation Updates

## Summary

Update all skills, commands, and documentation files that hardcode the `BUG|FEAT|ENH` type list. This child is largely independent of the code changes in FEAT-1405 and FEAT-1406 — text file updates can proceed in parallel. Covers 10 skill/command files and 7 documentation files plus `.claude/CLAUDE.md`.

## Parent Issue

Decomposed from FEAT-1389: Add EPIC as a First-Class Issue Type

## Proposed Solution

### Step 7 — Update capture-issue and manage-issue skills/commands

- `skills/capture-issue/SKILL.md` — add EPIC creation flow (user can say "create an epic", produces `EPIC-NNN` in `.issues/epics/`)
- `commands/capture-issue.md` — same EPIC creation flow
- `skills/manage-issue/SKILL.md` — add epic management guidance (epics coordinate work, not directly implementable; direct implementation to child issues)

Also document `ll-auto` exclusion: `ll-auto` should be run with `--type BUG,FEAT,ENH` to skip epics, since epics are containers and not implementable units. Update `ll-auto` help text or default filter.

### Step 18 — Update 10 skills/commands with hardcoded type lists

Update each to include `EPIC` in all hardcoded type references:

1. `commands/normalize-issues.md` — six bash grep patterns with `(BUG|FEAT|ENH)`: scan regex, duplicate-ID grep, validation rule regex, category mapping table, misclassification heuristics table, directory structure rules
2. `skills/format-issue/SKILL.md` — Step 3 "Identify issue type from filename or ID prefix (BUG/FEAT/ENH)"; template filename note; placement rules headings "For BUGs", "For FEATs", "For ENHs" — add "For EPICs" branch
3. `skills/decide-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
4. `skills/wire-issue/SKILL.md` — output template `Type: [BUG|FEAT|ENH]` — add EPIC
5. `skills/confidence-check/SKILL.md` — three type-specific scoring rubrics `**BUG**:`, `**FEAT**:`, `**ENH**:`; add `**EPIC**:` rubric covering coordination scope and child issue completeness criteria
6. `skills/issue-size-review/SKILL.md` — output template `type: [BUG|FEAT|ENH]` and dependency mention scoring rule referencing `BUG-/FEAT-/ENH-` — add EPIC
7. `skills/audit-issue-conflicts/SKILL.md` — card schema `- **Type** (\`BUG\`, \`FEAT\`, \`ENH\`)` and output templates `- **Type**: [BUG/FEAT/ENH]` — add EPIC
8. `skills/product-analyzer/SKILL.md` — `issue_type: [FEAT|ENH]` in YAML output description; add EPIC for strategic/container-level captures
9. `skills/issue-workflow/SKILL.md` — directory reference table `bugs/`, `features/`, `enhancements/`; add `epics/` row with EPIC type
10. `skills/debug-loop-run/SKILL.md` — `### 6b. Determine issue type and category` routing table; add EPIC row

### Step 19 — Update 7 documentation files

1. `docs/reference/CLI.md` — `--type` flag documented as "`BUG`, `FEAT`, `ENH`" in six places across `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-issues list/count/sequence/search/impact-effort/refine-status/anchor-sweep`; also the `Norm` column regex `^P[0-5]-(BUG|FEAT|ENH)-...`; add EPIC in all locations
2. `docs/reference/CONFIGURATION.md` — `cli.colors.type` table lists only BUG/FEAT/ENH; `label_mapping` default shows only three keys; `sync.github.label_mapping` description references `{"BUG": "bug", ...}`; add EPIC entries
3. `docs/reference/OUTPUT_STYLING.md` — type color table and `cmd_list` description list only three types; add EPIC row (color `35` / purple-magenta)
4. `docs/reference/ISSUE_TEMPLATE.md` — `### Type-Specific Sections` lists only "BUG", "FEAT", "ENH"; quality check checklists only cover those three; add EPIC section
5. `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — "type: BUG, FEAT, or ENH" in `### Issue File Anatomy`; directory listing omits `epics/`; update both
6. `docs/guides/GETTING_STARTED.md` — "type: BUG, FEAT, or ENH" description; add EPIC
7. `.claude/CLAUDE.md` — `Types: \`BUG\`, \`FEAT\`, \`ENH\`` in `## Issue File Format`; add EPIC

Also update `docs/reference/API.md` — EPIC type, `epic:` field, `children:` field definitions; and `docs/ARCHITECTURE.md` — add epic tier to issue hierarchy diagram (following the JIRA Epic→Story / ADO Epic→Feature analogy).

## Acceptance Criteria

- `skills/capture-issue/SKILL.md` includes EPIC creation flow
- All 10 skill/command files include EPIC in type lists/routing tables
- All 7 documentation files include EPIC where BUG/FEAT/ENH are listed
- `.claude/CLAUDE.md` issue type list includes EPIC
- `docs/ARCHITECTURE.md` shows epic tier in issue hierarchy
- No skill, command, or doc file retains a hardcoded `BUG|FEAT|ENH` list that excludes EPIC

## Files to Touch

- `skills/capture-issue/SKILL.md`
- `commands/capture-issue.md`
- `skills/manage-issue/SKILL.md`
- `commands/normalize-issues.md`
- `skills/format-issue/SKILL.md`
- `skills/decide-issue/SKILL.md`
- `skills/wire-issue/SKILL.md`
- `skills/confidence-check/SKILL.md`
- `skills/issue-size-review/SKILL.md`
- `skills/audit-issue-conflicts/SKILL.md`
- `skills/product-analyzer/SKILL.md`
- `skills/issue-workflow/SKILL.md`
- `skills/debug-loop-run/SKILL.md`
- `docs/reference/CLI.md`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/OUTPUT_STYLING.md`
- `docs/reference/ISSUE_TEMPLATE.md`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`
- `docs/guides/GETTING_STARTED.md`
- `docs/reference/API.md`
- `docs/ARCHITECTURE.md`
- `.claude/CLAUDE.md`

## Session Log
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
