---
discovered_date: "2026-04-24"
discovered_by: review
status: done
completed_at: 2026-04-24T00:00:00Z
---

# ENH-1279: `ll-issues validate-catalog` — Post-Merge Duplicate ID Detection

## Summary

When a parallel worktree fan-out completes and worktrees merge back, two workers that both created new issues will have independently picked the same next ID from their snapshot of `.issues/`. The resulting duplicate-ID files merge silently (different filenames, same ID prefix). Add `ll-issues validate-catalog` to detect this after merge and fail loudly so the user can run `ll:normalize-issues` to repair.

## Current Behavior

`ll:normalize-issues` can fix duplicate IDs reactively, but nothing actively detects them post-merge. A user who doesn't know to run normalization after a parallel fan-out may end up with a corrupted issue catalog indefinitely.

## Expected Behavior

`ll-issues validate-catalog` scans `.issues/` across all subdirectories, extracts the numeric ID from each filename, and reports any ID that appears more than once. Exits non-zero if duplicates are found, with output naming the conflicting files. Intended as a post-merge step in `ll-parallel` and `ll-sprint` runners, and as a standalone user command.

## Proposed Solution

1. Add `validate-catalog` subcommand to `ll-issues` CLI.
2. Scan all `.issues/**/*.md` filenames, parse the `NNN` segment, group by ID.
3. Report duplicates to stderr; exit 1 if any found.
4. Call `validate-catalog` at the end of `ll-parallel` / `ll-sprint` post-merge step (or document it as a manual step until those runners add it).

## Files to Modify

- `scripts/little_loops/cli/issues/` — add `validate_catalog` command
- `scripts/tests/test_ll_issues_validate_catalog.py` — unit tests with fixture `.issues/` dirs containing duplicates

## Acceptance Criteria

- `ll-issues validate-catalog` exits 0 when no duplicate IDs exist
- Exits 1 and names conflicting files when duplicates are present
- Handles all subdirectories (`bugs/`, `features/`, `enhancements/`, `completed/`, `deferred/`)
- Unit tests cover: clean catalog, single duplicate pair, multiple collisions

## Impact

- **Priority**: P4 — Nice-to-have safety net; `ll:normalize-issues` already exists as fallback
- **Effort**: Small — pure read + parse + report, no mutations
- **Risk**: Low
- **Breaking Change**: No

## Labels

`cli`, `ll-issues`, `parallel`, `validation`

## Related / See Also

- **ENH-1198** — closed invalid; this issue extracted from it
- **ENH-1280** — `ll-issues` atomic writes (companion issue)
- **ll:normalize-issues** — existing repair tool for duplicate IDs

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-04-24_ — **NO-GO (CLOSE)**

**Deciding Factor**: Existing functionality (`/ll:normalize-issues --check`) already satisfies every stated acceptance criterion, making this issue redundant rather than additive.

### Key Arguments For
- Implementation is ~40 lines, purely additive, reuses scan infrastructure from `get_next_issue_number` in `issue_parser.py:130–151`
- A dedicated Python CLI subcommand would be more composable in automated pipeline contexts than invoking a slash command

### Key Arguments Against
- `/ll:normalize-issues --check` already covers every acceptance criterion verbatim (`commands/normalize-issues.md:63–71`): scan all subdirs, report duplicate IDs, exit 1 on violations, exit 0 on clean — including FSM exit-code routing
- Current `ll-parallel` workers run `manage-issue` on existing issues (`worker_pool.py:388`), never calling `ll-issues next-id`; the described collision scenario requires deferred FEAT-1075

### Rationale
`/ll:normalize-issues --check` already satisfies every stated acceptance criterion word-for-word. The theoretical parallel-collision scenario depends on FEAT-1075 (deferred P2), not the current `ll-parallel` runner — `worker_pool.py` confirms existing workers never call `next-id`. Adding `validate-catalog` would create a parallel code path that must stay in sync with normalize-issues detection logic indefinitely.

---

**Closed (Won't Do)** | Created: 2026-04-24 | Closed: 2026-04-24 | Priority: P4
