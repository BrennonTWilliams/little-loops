---
id: ENH-1428
type: ENH
priority: P2
status: open
parent_issue: ENH-1422
---

# ENH-1428: Decouple Issue Status — ll-issues CLI Documentation Updates

## Summary

Update `docs/reference/CLI.md` and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` to reflect the new frontmatter-based status vocabulary introduced by ENH-1427. Can be written concurrently with ENH-1427 but must be accurate against the shipped code before merge.

## Parent Issue

Decomposed from ENH-1422: Decouple Issue Status — ll-issues CLI (list/show/count/search)

## Motivation

After the vocabulary transition from `"active"/"completed"/"deferred"` to `"open"/"in_progress"/"blocked"/"done"/"cancelled"`, the CLI reference and management guide still describe the old directory-based status model and old `--status` choice values. Users following these docs will use stale flag values.

## Proposed Solution

### `docs/reference/CLI.md`

- Lines ~501, ~515, ~546: update `--status` choices tables for `list`, `search`, and `count` subcommands from `active/completed/deferred/all` to `open/in_progress/blocked/deferred/done/cancelled/all`
- Line ~691: update example `ll-issues count --status completed` to `--status done`

### `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

- Line ~118: revise "**Directory location determines CLI bucketing.**" to describe frontmatter-based status
- Update vocabulary table entries replacing `active` → `open`/`in_progress`/`blocked` and `completed` → `done`/`cancelled`
- Update any directory-move instructions that describe moving files to `completed/` or `deferred/` as the mechanism for changing status

## Implementation Steps

13. Update `docs/reference/CLI.md` — change `--status` choices in all three subcommand tables (list, search, count) from `active/completed/deferred/all` to the new vocabulary; update `ll-issues count --status completed` example to `--status done`
14. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — revise "Directory location determines CLI bucketing" to describe frontmatter-based status; update vocabulary table and any directory-move instructions

## Files to Modify

- `docs/reference/CLI.md`
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`

## Acceptance Criteria

- `docs/reference/CLI.md` `--status` choices for list/search/count match the new vocab
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` no longer states directory location determines status
- `ll-verify-docs` passes after changes

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de4dc0e-8a1e-41f5-94a2-7daaa289459e.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
