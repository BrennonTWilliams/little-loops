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

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0cc6049e-f9fc-4387-9af6-418507182087.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
