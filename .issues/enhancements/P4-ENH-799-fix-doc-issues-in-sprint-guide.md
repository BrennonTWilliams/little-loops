---
discovered_date: 2026-03-17T00:00:00Z
discovered_by: capture-issue
---

# ENH-799: Fix documentation issues in SPRINT_GUIDE.md

## Summary

Minor inconsistencies and missing prose explanations in `docs/guides/SPRINT_GUIDE.md`.

## Current Behavior

`docs/guides/SPRINT_GUIDE.md` has five low-severity readability issues:
- Wave label format is inconsistent across execution plan examples (`"Wave 2 (after Wave 1) parallel:"` vs `"Wave 1 (parallel):"`)
- `--handoff-threshold` appears in the CLI reference table without any prose explaining what "handoff threshold" means
- `options.max_iterations` is present in the YAML anatomy table but missing from the Configuration section
- `manage-issue` is referenced in recipe sections without a link or explanation for readers unfamiliar with the command
- The "Full Plan a Feature Sprint Pipeline" recipe largely duplicates content from `ISSUE_MANAGEMENT_GUIDE.md`

## Expected Behavior

- Wave label format is standardized consistently throughout all examples
- A prose explanation of "handoff threshold" appears near the `--handoff-threshold` CLI flag
- `options.max_iterations` is documented in the Configuration section
- `manage-issue` is linked or briefly explained on first reference in recipe sections
- The "Full Plan a Feature Sprint Pipeline" recipe is replaced by or supplemented with a cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`

## Motivation

The wave label format inconsistency is a small readability issue. The missing prose explanation for `--handoff-threshold` and the absent `options.max_iterations` in the Configuration section are gaps that reduce the reference value of the guide.

## Issues to Fix

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | Low | Execution plan example | Inconsistent wave label format: `"Wave 2 (after Wave 1) parallel:"` vs `"Wave 1 (parallel):"` — standardize |
| 2 | Low | CLI reference | `--handoff-threshold` listed in table without prose explanation of what "handoff threshold" means |
| 3 | Low | YAML anatomy table | `options.max_iterations` in anatomy table but absent from Configuration section — add it |
| 4 | Low | Recipe sections | `manage-issue` referenced without link or explanation for unfamiliar readers |
| 5 | Low | "Full Plan a Feature Sprint Pipeline" recipe | Near-duplicates content from `ISSUE_MANAGEMENT_GUIDE.md` — consider replacing with a cross-reference |

## Implementation Steps

1. Standardize wave label format throughout execution plan examples
2. Add prose explanation of "handoff threshold" concept near the `--handoff-threshold` CLI flag
3. Add `options.max_iterations` to the Configuration section
4. Add a link or brief explanation when `manage-issue` is first referenced in recipe sections
5. Evaluate whether the "Full Plan a Feature Sprint Pipeline" recipe can be replaced by a cross-reference to `ISSUE_MANAGEMENT_GUIDE.md`

## Scope Boundaries

- Only `docs/guides/SPRINT_GUIDE.md` is modified (and a cross-reference link to `ISSUE_MANAGEMENT_GUIDE.md` if item 5 is addressed)
- No code changes
- No changes to other guide files beyond adding the cross-reference target link if needed
- Do not add new features or restructure the guide; only fix the five listed issues

## Impact

- **Priority**: P4 — Low; readability improvements to a guide, no functional impact
- **Effort**: Small — All five fixes are prose edits or minor YAML additions in a single file
- **Risk**: Low — Documentation only, no code paths affected
- **Breaking Change**: No

## Labels

`documentation`, `captured`

## Status

**Open** | Created: 2026-03-17 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-03-18T01:52:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0b5a688-4ca6-4171-a6bb-f5be121354ad.jsonl`
- `/ll:capture-issue` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8a2338-e3dd-4309-8117-478c418261ea.jsonl`
