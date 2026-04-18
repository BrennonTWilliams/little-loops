---
id: FEAT-1161
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
---

# FEAT-1161: Add `captured_at` Timestamp in capture-issue Skill

## Summary

Record a `captured_at` ISO 8601 UTC timestamp in issue frontmatter when `/ll:capture-issue` creates a new issue.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Issues have `discovered_date` (date-only) but no machine-readable record of the exact moment capture happened. Adding `captured_at` enables sub-day velocity metrics in `ll-history` and other analysis tools without reconstructing times from git blame.

## Implementation Steps

1. **`skills/capture-issue/SKILL.md`** (~line 235): Add instruction mandating `captured_at: <ISO 8601 datetime>` alongside `discovered_date` and `discovered_by: capture-issue`.

2. **`skills/capture-issue/templates.md`** (lines 134-139): Add `captured_at: [ISO timestamp]` to the heredoc template.

Shell format to use: `date -u +"%Y-%m-%dT%H:%M:%SZ"` — consistent with the format already used in `issue_lifecycle.py:730`.

## API/Interface

New frontmatter field:

```yaml
captured_at: "2026-04-18T14:32:07Z"   # set by capture-issue
```

## Acceptance Criteria

- [ ] New issues created by `/ll:capture-issue` contain `captured_at` in frontmatter
- [ ] `captured_at` is a valid ISO 8601 UTC string (ends in `Z`)
- [ ] Existing issues without `captured_at` continue to work without errors

## Files to Modify

- `skills/capture-issue/SKILL.md` — add `captured_at` field instruction near line 235 alongside `discovered_date`
- `skills/capture-issue/templates.md` — add `captured_at: [ISO timestamp]` to heredoc template at lines 134-139

## Tests

- `scripts/tests/test_sync.py:748` — add ISO datetime round-trip test for `_update_issue_frontmatter` with a `captured_at` value (not broken by this change, but add a positive test)

## Session Log
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
