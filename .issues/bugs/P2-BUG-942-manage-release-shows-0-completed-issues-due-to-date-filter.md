---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# BUG-942: manage-release Shows 0 Completed Issues Due to Date-Filter Approach

## Summary

`/ll:manage-release` generates a changelog with 0 completed issues even when 16+ issues were moved to `.issues/completed/` between releases. The root cause is a two-part failure: Agent 2 filters by `completed_date >= last_tag_date`, but completed issue files have no date field — and if run after the release tag already exists, `git describe --tags --abbrev=0` returns the current tag making the git range empty.

## Current Behavior

Running `/ll:manage-release changelog v1.70.0` produces a changelog with 0 issues. Agent 2 scans all files in `.issues/completed/`, attempts to filter by `completed_date`, finds no date fields in any of the 16 recently-completed issue files, and excludes them all. Confirmed with:

```bash
git log --diff-filter=A --name-only --format="" v1.69.0..v1.70.0 -- .issues/completed/
# → 16 issue files (P2-BUG-928, P2-BUG-930, P2-BUG-931, etc.)

grep -r "\*\*Completed\*\*\|\*\*Fixed\*\*\|\*\*Closed\*\*" .issues/completed/P3-FEAT-934-*.md
# → (no output — no date fields present)
```

Secondary failure: if run after tagging (e.g., "changelog only" after a manual tag), `git describe --tags --abbrev=0` returns the new tag itself (v1.70.0), so `v1.70.0..HEAD` is an empty range.

## Expected Behavior

Agent 2 should use `git log --diff-filter=A` to enumerate which issue files were added to `.issues/completed/` between the previous tag and HEAD. This is 100% reliable regardless of whether completed issues have date fields — git history is the ground truth for what was completed in this release.

## Motivation

Release notes are unusable when they list 0 issues despite a real release. This defeats the purpose of the changelog automation entirely. The current approach depends on a date field convention that the codebase does not enforce — making the feature unreliable by design. Every release that lacks date fields in its completed issues will silently produce an empty changelog.

## Steps to Reproduce

1. Complete several issues by moving them to `.issues/completed/` (without adding date fields).
2. Create a git tag (`git tag v1.70.0`).
3. Run `/ll:manage-release changelog v1.70.0`.
4. Observe: changelog shows 0 completed issues.

## Root Cause

- **File**: `commands/manage-release.md`
- **Anchor**: Agent 2 prompt (issue scanning section)
- **Cause**: Agent 2 scans all files in `completed/` and filters by `completed_date >= last_tag_date`. When no date fields are present, the Explore subagent finds nothing to compare and excludes all issues. Additionally, the `git describe --tags --abbrev=0` call without `^` offset returns the current tag when HEAD is exactly at a tag, yielding an empty `HEAD..HEAD` range.

## Proposed Solution

Replace the date-filter approach in Agent 2 with a git-first approach:

```
# Smart detection: handles whether new release tag already exists
if git describe --exact-match HEAD >/dev/null 2>&1; then
  # HEAD is at a tag → use the tag before it
  CURRENT_TAG=$(git describe --exact-match HEAD)
  PREV_TAG=$(git describe --tags --abbrev=0 "${CURRENT_TAG}^")
else
  # HEAD is not at a tag → most recent tag is the baseline
  PREV_TAG=$(git describe --tags --abbrev=0)
fi

# List all issue files added to completed/ since that tag
git log --diff-filter=A --name-only --format="" "${PREV_TAG}..HEAD" -- .issues/completed/
```

For each file returned, parse filename for type/ID and read for title and `github_issue` frontmatter. This requires no date fields at all — git history is the source of truth.

## Integration Map

### Files to Modify
- `commands/manage-release.md` — Agent 2 prompt (issue scanning section, ~lines 170–201)

### Dependent Files (Callers/Importers)
- N/A — this is a command prompt file, not imported by Python code

### Similar Patterns
- N/A — Agent 2 is the only place that scans completed issues for changelog generation

### Tests
- Manual verification: run `/ll:manage-release changelog v1.70.0` after the fix and confirm 16 issues appear

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the Agent 2 prompt block in `commands/manage-release.md` (~lines 170–201).
2. Replace the date-filter scanning logic with the `git log --diff-filter=A` approach (smart tag detection for pre-tag and post-tag scenarios).
3. Verify against the known list of 16 issues (BUG-928, BUG-930, BUG-931, BUG-938, BUG-939, BUG-940, BUG-941, ENH-497, ENH-825, ENH-841, ENH-925, ENH-929, ENH-932, ENH-935, ENH-936, FEAT-934).

## Impact

- **Priority**: P2 — Changelog automation is completely broken; every release produces empty release notes
- **Effort**: Small — Single file change, replacing one prompt block (~30 lines)
- **Risk**: Low — Isolated to the Agent 2 prompt; no Python code changes; git log approach is simpler and more reliable
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7308edca-cfb1-4076-acfb-845ecd8be944.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P2
