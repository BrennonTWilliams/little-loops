---
id: ENH-1550
type: enhancement
priority: P3
status: open
parent: ENH-1539
size: Small
---

# ENH-1550: Status canonical enum — documentation and skill references

## Summary

Document the canonical `status:` enum in `.claude/CLAUDE.md` and add one-line references in the five issue-touching skill files and two guide/reference docs, so coding agents stop generating synonym drift in the first place.

## Parent Issue

Decomposed from ENH-1539: Normalize status synonyms and document canonical enum

## Proposed Solution

### 1. `.claude/CLAUDE.md` — canonical enum subsection

Add a short subsection (≤5 lines) under "Issue File Format" (between the `Priorities` bullet and `## Important Files`, near line 95):

> **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace. Synonyms are coerced to canonical values on read, but writing canonical values avoids ambiguity.

### 2. Issue-touching skills — one-line reference

Add a single line to each of the following skill files, in their "frontmatter" or "issue format" sections:

- `skills/capture-issue/SKILL.md`
- `skills/ready-issue/SKILL.md`
- `skills/manage-issue/SKILL.md`
- `skills/format-issue/SKILL.md`
- `skills/refine-issue/SKILL.md`

Line to add (after any existing status mention):
> Status enum: see `.claude/CLAUDE.md` § Issue File Format — Status values.

### 3. `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

The file already has a `### Frontmatter status Values` table at lines 106-119. Add a one-liner after the table:

> Synonyms (`complete`, `completed`, `finished`, `wip`, `in-progress`) are silently coerced to canonical values on read; authors don't need to worry about fixing them manually.

### 4. `docs/reference/CLI.md`

At ~line 557 where `--status {open,in_progress,...}` filter choices are documented, add a one-liner:

> Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs).

## Files to Modify

- `.claude/CLAUDE.md` — add "Status values" subsection
- `skills/capture-issue/SKILL.md` — add one-line enum reference
- `skills/ready-issue/SKILL.md` — add one-line enum reference
- `skills/manage-issue/SKILL.md` — add one-line enum reference
- `skills/format-issue/SKILL.md` — add one-line enum reference
- `skills/refine-issue/SKILL.md` — add one-line enum reference
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — add synonym coercion note
- `docs/reference/CLI.md` — add CLI input note

## Acceptance Criteria

1. `.claude/CLAUDE.md` names all 6 canonical status values and explicitly lists forbidden synonyms
2. Each of the 5 skill files has a one-line pointer to the canonical enum location
3. `ISSUE_MANAGEMENT_GUIDE.md` mentions synonym coercion in the status table section
4. `CLI.md` clarifies that `--status` input must be canonical even though on-disk synonyms are coerced

## Impact

- **Effort**: Very small — 8 files, 1-5 lines each; no code changes
- **Risk**: None — documentation only
- **Can be done in parallel with ENH-1549**

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e994b5a7-bd67-4e1b-8e86-ff8daad14873.jsonl`
