---
id: BUG-1799
type: BUG
priority: P2
status: open
captured_at: "2026-05-29T20:55:00Z"
discovered_date: "2026-05-29"
discovered_by: capture-issue
labels: [bug, skills, audit-issue-conflicts]
---

# BUG-1799: audit-issue-conflicts scans terminal (done/deferred) issues alongside active ones

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 1 collects every `.md` file under `.issues/{bugs,features,enhancements}/` and treats them all as active. In practice, type directories now contain both active and terminal issues distinguished by `status:` frontmatter, so the audit wastes work on already-closed issues and can spawn hundreds of unnecessary parallel agents on large backlogs.

## Current Behavior

Phase 1 uses a plain `find` glob over type directories (`bugs/`, `features/`, `enhancements/`) that collects every `.md` file regardless of `status:` frontmatter. Terminal issues (`status: done`, `status: deferred`, `status: cancelled`) are included in the active set and passed through to conflict-detection stages, wasting work on already-closed issues.

## Steps to Reproduce

1. Have ≥100 issues in `.issues/{bugs,features,enhancements}/` where most are `status: done` (typical post-`ll-migrate` state)
2. Run `/ll:audit-issue-conflicts`
3. Phase 1 reports "Found N active issues" where N includes all done/deferred/cancelled files

Observed in this repo on 2026-05-29: 1,692 files in type dirs, only 54 with `status: open|in_progress|blocked`. The skill would have batched all 1,692 into ~340 parallel agents instead of ~11.

## Expected Behavior

Phase 1 should filter to issues whose frontmatter `status:` is one of `open`, `in_progress`, `blocked` (or absent — default open). Terminal statuses (`done`, `deferred`, `cancelled`) should be excluded.

## Root Cause

`skills/audit-issue-conflicts/SKILL.md` lines 59–74 (Phase 1 bash block) globs `find "$dir" -maxdepth 1 -name "*.md"` without inspecting frontmatter. The skill predates the ENH-1390/ENH-1551 model where completed issues live alongside active ones in the same type directory rather than under a `completed/` subdir.

## Proposed Solution

Replace the Phase 1 collection block with a status-aware filter:

```bash
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    [ -d "$dir" ] || continue
    for f in "$dir"*.md; do
        [ -f "$f" ] || continue
        status=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$f")
        case "${status:-open}" in
            open|in_progress|blocked) ISSUE_FILES+=("$f") ;;
        esac
    done
done
```

Or invoke `ll-issues list --status open,in_progress,blocked --format path` which already implements this filter.

## Implementation Steps

1. Update Phase 1 collection block in `skills/audit-issue-conflicts/SKILL.md` to filter by status frontmatter
2. Update the count message to clarify: "Found N active issues (excluded M terminal issues)"
3. Add a regression test: create fixture issues with mixed statuses, assert only active ones reach Phase 2
4. Cross-check sibling skills (`tradeoff-review-issues`, `align-issues`, `verify-issues`) for the same defect

## Acceptance Criteria

- Running `/ll:audit-issue-conflicts` on a backlog with mixed statuses processes only active issues
- Phase 1 logs both the active count and the excluded terminal count
- Pytest fixture covers the status-filter path

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 1 collection block

### Similar Patterns
- `/ll:capture-issue` SKILL.md uses a status-aware glob (see Phase 2 "Search Active Issues")
- `ll-issues list --status open --format path` already implements the filter

### Tests
- `scripts/tests/test_skill_audit_issue_conflicts.py` (if exists) — add a mixed-status fixture case

## Impact

- **Priority**: P2 — degrades skill utility on any real backlog; pure-design bug
- **Effort**: Small — single-block rewrite + test
- **Risk**: Low — narrows scope, doesn't change conflict-detection semantics
- **Breaking Change**: No — strictly fewer files audited

## Session Log
- `/ll:format-issue` - 2026-05-29T21:11:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d42814df-045f-41ae-b065-5f4d670ef04d.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P2
