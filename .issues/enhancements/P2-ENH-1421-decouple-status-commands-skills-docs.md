---
id: ENH-1421
type: ENH
priority: P2
status: open
parent_issue: ENH-1390
---

# ENH-1421: Decouple Issue Status — Commands, Skills, and Documentation

## Summary

Update all 13 command files, 3 skill files, and 4 documentation files that reference `completed/` or `deferred/` directory patterns. The CRITICAL changes are `manage-release.md` (release detection strategy) and `manage-issue/SKILL.md` (git mv → frontmatter update). Can run in parallel with ENH-1418 and ENH-1419 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1390: Decouple Issue Status from Directory Structure

## Current Behavior

All command files, skill files, and documentation reference `completed/` and `deferred/` directory paths to determine issue status. For example: `manage-release.md` uses `git log --diff-filter=A -- .issues/completed/` for release detection; `manage-issue/SKILL.md` instructs `git mv` to move issues into `completed/`; `align-issues.md`, `create-sprint.md`, and `sync-issues.md` all use `find -not -path "*/completed/*" -not -path "*/deferred/*"` to filter active issues. After ENH-1417 lands the authoritative model will be frontmatter `status`, but these 20 files will still drive behaviour from directory location.

## Expected Behavior

All 13 command files, 3 skill files, and 4 documentation files use the frontmatter `status` field rather than directory path as the source of truth. Specifically: `manage-release.md` detects completed issues via `status: done` + `completed_at` date range; `manage-issue/SKILL.md` performs a frontmatter update (`status: done`) instead of `git mv`; all `find`-based active-issue filters use a `--status` flag or equivalent frontmatter filter. The lifecycle documented in `ISSUE_MANAGEMENT_GUIDE.md` describes status values, not directory routing.

## Motivation

Once ENH-1417 lands the frontmatter-based status data model, any remaining directory references in commands/skills create a split-brain: the data model says status is in frontmatter but the tooling still relies on directory location. This causes release detection to miss issues, lifecycle commands to issue incorrect `git mv` instructions, and docs to contradict the new model. This ENH completes the decoupling for the user-facing layer so the entire stack is consistent after ENH-1390.

## Proposed Solution

### Step 12 — 13 command files

**CRITICAL changes:**

- `commands/manage-release.md`: replace `git log --diff-filter=A … -- .issues/completed/` release detection with frontmatter-based approach — query issues where `status: done` and `completed_at` falls between the previous tag's commit timestamp and HEAD. Use full ISO timestamp comparison (not date-only) to avoid BUG-942 off-by-one failure mode.
- `commands/normalize-issues.md`: ~30 references to `completed/`/`deferred/` directories throughout checks and auto-fix scripts; replace with status-field-based approach

**Standard updates (replace directory patterns with status-field equivalents):**

- `commands/review-sprint.md` — `completed/` directory glob → frontmatter filter
- `commands/tradeoff-review-issues.md` — 6 refs to `{{config.issues.completed_dir}}/` for exclusion and as destination
- `commands/align-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"` → `--status` filter
- `commands/create-sprint.md` — excludes `/completed/` and `/deferred/` path segments; checks blocker membership in completed dir
- `commands/prioritize-issues.md` — excludes `completed/`/`deferred/` from scanning
- `commands/verify-issues.md` — `find` with `-not -path "*/completed/*"`; move instructions to `completed/`
- `commands/sync-issues.md` — `find … -not -path "*/completed/*" -not -path "*/deferred/*"`
- `commands/ready-issue.md` — checks blocker membership in `completed/` directory
- `commands/audit-architecture.md` — references to `completed/` directory in shell patterns
- `commands/refine-issue.md` — line 29 reference to `{{config.issues.completed_dir}}`
- `.claude/CLAUDE.md` — Key Directories section shows `completed/` as a routing subdirectory

### Step 13 — Skills

**CRITICAL change:**

- `skills/manage-issue/SKILL.md` (lines 450–466): replace `CRITICAL: Move to {{config.issues.completed_dir}}/` with `git mv` examples → frontmatter update instructions (`update_frontmatter(path, {"status": "done"})`)

**Standard updates:**

- `skills/init/SKILL.md` — line 148 reference to `issues.completed_dir` in config generation logic
- `skills/init/interactive.md` — lines 248, 342 references to `completed_dir` in config generation instructions

### Step 7 — Documentation

- `docs/ARCHITECTURE.md` (lines 41–59) — remove state directories from directory structure diagram; describe `status:` field lifecycle
- `docs/reference/CONFIGURATION.md` — update `completed_dir`/`deferred_dir` table entries to document new `status` field approach
- `docs/reference/API.md` — update `status` field documentation and valid values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — CRITICAL: full rewrite of lifecycle diagram and frontmatter status table; remove "Directory location determines CLI bucketing" statement (lines directly contradicting ENH-1390's goal)

### Test to Update

- `scripts/tests/test_feat1172_doc_wiring.py` — `test_completed_at_row_describes_completed_dir` asserts docs mention `completed` directory; update assertion to match new status field documentation

## Acceptance Criteria

- `manage-release.md` uses `completed_at` date range for release detection (full ISO timestamps)
- `normalize-issues.md` uses status-field patterns, not directory patterns
- All 13 command files and 3 skill files no longer reference `completed/` or `deferred/` as active-use directories
- `ISSUE_MANAGEMENT_GUIDE.md` lifecycle section accurately describes frontmatter-based status model
- `ARCHITECTURE.md` directory structure diagram reflects type-dirs-only layout
- `test_feat1172_doc_wiring.py` passes

## Scope Boundaries

- **In scope**: `.md` command files (`commands/`), skill `.md` files (`skills/`), and documentation files (`docs/`) that reference `completed/` or `deferred/` directory patterns
- **Out of scope**: Python CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync`, etc.) — covered by ENH-1419
- **Out of scope**: Python data model, `IssueStatus` enum, frontmatter read/write utilities — covered by ENH-1417
- **Out of scope**: Discovery and lifecycle hooks (`ll-issues refine-status`) — covered by ENH-1418
- **Out of scope**: Session log format or JSONL schema changes

## Integration Map

### Files to Modify
- `commands/manage-release.md` — CRITICAL: rewrite release detection from `git log --diff-filter=A -- .issues/completed/` to frontmatter query (`status: done` + `completed_at` ISO range)
- `commands/normalize-issues.md` — ~30 references to `completed/`/`deferred/` in checks and auto-fix scripts → status-field approach
- `commands/review-sprint.md` — `completed/` directory glob → frontmatter filter
- `commands/tradeoff-review-issues.md` — 6 refs to `{{config.issues.completed_dir}}/`
- `commands/align-issues.md` — `find -not -path "*/completed/*" -not -path "*/deferred/*"` → `--status` filter
- `commands/create-sprint.md` — `/completed/`/`/deferred/` path exclusions; blocker membership check
- `commands/prioritize-issues.md` — `completed/`/`deferred/` scan exclusions
- `commands/verify-issues.md` — `find -not -path "*/completed/*"`; move-to-completed instructions
- `commands/sync-issues.md` — `find -not -path "*/completed/*" -not -path "*/deferred/*"`
- `commands/ready-issue.md` — blocker membership check against `completed/` directory
- `commands/audit-architecture.md` — `completed/` directory shell patterns
- `commands/refine-issue.md` — line 29 `{{config.issues.completed_dir}}` reference
- `.claude/CLAUDE.md` — Key Directories section lists `completed/` as routing subdirectory
- `skills/manage-issue/SKILL.md` — CRITICAL: replace `git mv → completed/` with `update_frontmatter(path, {"status": "done"})`
- `skills/init/SKILL.md` — `issues.completed_dir` config generation reference
- `skills/init/interactive.md` — `completed_dir` in config generation instructions (2 occurrences)
- `docs/ARCHITECTURE.md` — remove state directories from directory structure diagram; describe `status:` lifecycle
- `docs/reference/CONFIGURATION.md` — update `completed_dir`/`deferred_dir` table entries
- `docs/reference/API.md` — update `status` field documentation and valid values
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — CRITICAL: rewrite lifecycle diagram and frontmatter status table

### Dependent Files (Callers/Importers)
- N/A — command/skill `.md` files are leaf consumers, not imported by other code

### Similar Patterns
- All files using `{{config.issues.completed_dir}}` or `{{config.issues.deferred_dir}}` template vars
- Search: `grep -r "completed_dir\|deferred_dir\|completed/\|deferred/" commands/ skills/ docs/ .claude/`

### Tests
- `scripts/tests/test_feat1172_doc_wiring.py` — update `test_completed_at_row_describes_completed_dir` assertion to match new status-field documentation

### Documentation
- All four `docs/` files listed above are themselves part of this ENH's scope

### Configuration
- N/A

## Implementation Steps

1. After ENH-1417 merges, update `commands/manage-release.md` (frontmatter-based release detection with full ISO `completed_at` range)
2. Update `commands/normalize-issues.md` (~30 directory references → status-field equivalents)
3. Update remaining 11 command files and `.claude/CLAUDE.md` with standard directory→status-filter replacements
4. Update `skills/manage-issue/SKILL.md` (`git mv` → `update_frontmatter(path, {"status": "done"})`)
5. Update `skills/init/SKILL.md` and `skills/init/interactive.md`
6. Rewrite `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` lifecycle section; update remaining 3 doc files
7. Update `test_feat1172_doc_wiring.py` assertion and verify suite passes

## Impact

- **Priority**: P2 — Blocks ENH-1390 from being functionally complete; commands will misbehave after ENH-1417 if directory references remain
- **Effort**: Large — 20 files across commands, skills, and docs; 2 critical rewrites plus 18 standard pattern replacements
- **Risk**: Low — pure text changes to `.md` command/skill/doc files; no new logic or runtime code introduced
- **Breaking Change**: No (internal tooling only; `.md` command files are instruction text)

## Labels

`enhancement`, `refactor`, `issue-management`, `documentation`

## Session Log
- `/ll:format-issue` - 2026-05-10T15:21:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/293739bc-9ebc-4dac-a29c-99529166ae17.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
