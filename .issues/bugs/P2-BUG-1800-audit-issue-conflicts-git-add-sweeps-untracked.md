---
id: BUG-1800
type: BUG
priority: P2
status: done
captured_at: "2026-05-29T20:55:00Z"
completed_at: "2026-05-30T06:45:00Z"
discovered_date: "2026-05-29"
discovered_by: capture-issue
labels: [bug, skills, audit-issue-conflicts, git]
parent: EPIC-1745
---

# BUG-1800: audit-issue-conflicts `git add .issues/` stages unrelated untracked files

## Summary

`skills/audit-issue-conflicts/SKILL.md` Phase 5 runs `git add {{config.issues.base_dir}}/` to stage modified issue files. This recursive stage sweeps in any pre-existing untracked files under `.issues/` that the audit never touched, polluting the resulting commit.

## Current Behavior

Phase 5 of `audit-issue-conflicts` runs `git add .issues/` which recursively stages all files under `.issues/`, including untracked files that were never touched by the audit. This pollutes the resulting commit with files unrelated to the audit's changes.

## Steps to Reproduce

1. Have one or more untracked issue files in `.issues/` (e.g., recently captured but uncommitted)
2. Run `/ll:audit-issue-conflicts` and approve at least one recommendation
3. `git status` after Phase 5 shows the untracked files staged as `A` alongside the audit's `M` edits

Observed in this run on 2026-05-29: 9 audit-modified files were correctly staged as `M`, but 5 unrelated untracked files (ENH-1795, ENH-1796, ENH-1797, FEAT-1794, FEAT-1798) were also staged as `A`.

## Expected Behavior

Phase 5 should stage only files that the skill actually modified during Phase 4b.

## Motivation

This bug would:
- Surprise users who expect minimal-diff commits — the audit can silently pull in unrelated untracked issue files
- Threaten commit hygiene — users may unwittingly commit draft issues before they're ready
- Violate the principle of least surprise for automation tools

## Root Cause

`skills/audit-issue-conflicts/SKILL.md` Phase 5 (lines 347–349) uses:

```bash
git add {{config.issues.base_dir}}/
```

…which recursively stages everything in `.issues/`, including untracked files. The skill has no list of files modified during the run.

## Proposed Solution

Track modified file paths in a session-local list during Phase 4b, then stage exactly those files in Phase 5:

```bash
# Phase 4b: track each edit
MODIFIED_FILES+=("$path_to_edited_file")

# Phase 5
for f in "${MODIFIED_FILES[@]}"; do
    git add "$f"
done
```

Alternatively, capture `git status --porcelain .issues/` before Phase 4b begins, diff against the post-edit state, and stage only the M-status delta.

## Implementation Steps

1. Add a `MODIFIED_FILES` accumulator at top of Phase 4b in `skills/audit-issue-conflicts/SKILL.md`
2. Update each Phase 4b action (merge/deprecate, add_dependency, split/update_scope) to append to the list
3. Rewrite Phase 5 to iterate the list with `git add "$f"`
4. Add a regression test: pre-create an untracked `.issues/.../*.md` fixture, run the audit, assert the untracked file remains untracked

## Acceptance Criteria

- After a Phase 4 apply, `git status` shows only audit-touched files staged
- Pre-existing untracked issue files remain untracked
- Pytest fixture exercises the staged-set boundary

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 4b accumulator, Phase 5 stage loop

### Similar Patterns
- `/ll:commit` skill stages explicitly enumerated files (does not blanket-add)

### Tests
- `scripts/tests/test_skill_audit_issue_conflicts.py` (if exists) — add untracked-file boundary case

## Impact

- **Priority**: P2 — pollutes user commits; surprises users who expect minimal-diff behavior
- **Effort**: Small — accumulator + loop swap
- **Risk**: Low — narrows what gets staged
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-05-29T21:11:43 - `f6ce04a2-c38b-41b5-adda-cd8229dbc363.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:55:00Z - `53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`

## Status

**Open** | Created: 2026-05-29 | Priority: P2
