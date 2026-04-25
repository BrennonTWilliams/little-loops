---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075]
---

# ENH-1198: `ll-issues` Mutation Atomicity Under Parallel Worktree Mode

## Summary

`ll-issues` CLI mutates files in `.issues/` (create, prioritize, normalize, refine-status). Under parallel worktree mode, multiple workers may invoke `ll-issues` concurrently from sibling worktrees — each seeing its own git worktree's `.issues/` directory. When workers merge back to the parent branch, `.issues/` changes from different workers can conflict silently or produce duplicate IDs. Harden `ll-issues` mutations with per-operation locking or a claim-an-ID protocol so parallel fan-out over issue generation doesn't corrupt the issue catalog.

## Current Behavior

`ll-issues next-id` reads the `.issues/` directory and returns `max(existing) + 1`. If two workers call it in the same millisecond, both see the same `max` and both return the same ID — producing duplicate filenames that `ll:normalize-issues` has to untangle later.

`ll-issues` file-writing operations (new issue, status change) are direct `pathlib.Path.write_text()` — no lock, no rename-into-place, no retry on EEXIST.

In worktree mode, each worker has its own `.issues/` snapshot at worker start. Changes only become visible to other workers after the worktree is merged back. Two workers creating new issues will both pick the same next ID from their respective snapshots, and only surface the duplicate at merge time.

## Expected Behavior

1. **Globally coordinated ID allocation**: `ll-issues next-id` (and any ID-generating pathway) must coordinate across workers. Options:
   - Lock-based: an `fcntl`-based advisory lock on `.issues/.id-lock` in the repo root (not in the worktree's `.issues/` — the lock must live in a shared path). Works for both thread mode (same process → same fd semantics) and worktree mode (shared filesystem).
   - Reservation-based: a `.issues/.reserved-ids` file listing in-use IDs; workers reserve before creating.
   - Timestamp+worker-ID suffix: append a unique token to the ID to avoid collisions (e.g., `P3-BUG-1042-a3f2-description.md`). Rejected: breaks the established `P[0-5]-[TYPE]-[NNN]` format.
2. **Atomic file writes**: `ll-issues` writes must use write-to-tempfile + `os.rename()` to avoid partial writes visible to other workers or tools.
3. **Parent-level merge semantics**: when worktrees merge back, issue-catalog changes from multiple workers should union cleanly. The parallel state's post-run step must detect and surface (a) duplicate IDs across workers, (b) same-file edits from two workers.
4. **Documented contract**: the parallel-state shared-context mutation contract (FEAT-1189) must explicitly call out `.issues/` as a shared-coordinated path, not a free-write path.

## Use Case

**Who**: A user running a parallel fan-out where each worker generates issues — e.g., a `scan-codebase`-style loop fanning out `scan-product` over product areas, each producing multiple issues.

**Context**: 4 workers each call `ll-issues next-id` within a 100ms window; all 4 get `1199`. All 4 write `P3-BUG-1199-*.md` files in their respective worktrees. Merge back → 4 files with the same ID prefix.

**Outcome**: After this enhancement, each worker gets a distinct ID; post-run merge validates no ID collisions slipped through.

## Proposed Solution

1. Implement `fcntl` advisory lock on `<repo-root>/.issues/.id-lock` around ID allocation. Acquire-read-max-write-new-file happens under the lock.
2. In worktree mode, the lock file must be in a path shared across worktrees — the main repo's `.git/` parent directory is a safe bet, or a well-known `<repo-root>/.ll/.locks/` created once. Decide based on feasibility without reaching out of the worktree boundary.
3. Atomic writes: refactor `ll-issues` file writes to `tempfile.NamedTemporaryFile(dir=<target-dir>)` + `os.rename()`.
4. Add a post-fan-out validation step: after workers merge, `ll-issues validate-catalog` checks for duplicate IDs and same-file edits; fails the parallel state verdict if collisions found.
5. Update `docs/generalized-fsm-loop.md` (and FEAT-1189) to document `.issues/` as a coordinated path, and `ll-issues` as the correct mutation interface.

## Files to Modify

- `scripts/little_loops/cli/issues/` — ID allocation + atomic-write refactor
- `scripts/little_loops/cli/issues/validate.py` (new or existing) — `validate-catalog` subcommand
- `scripts/tests/test_ll_issues_concurrent.py` — simulate concurrent ID allocation with multiple processes
- `docs/generalized-fsm-loop.md` — parallel-state chapter: coordinated-path contract
- `FEAT-1189` issue — cross-reference the `.issues/` contract addition

## Dependencies

- **Hard blockers**: FEAT-1075 (worktree-mode fan-out must exist to drive real testing)
- **Soft**: FEAT-1189 (shared-context mutation contract — this is a specific instance)

## Acceptance Criteria

- `ll-issues next-id` under 4 concurrent invocations (separate processes) returns 4 distinct IDs
- `ll-issues` writes use write-tempfile + rename; no partial-write races visible to concurrent readers
- Lock file path works from sibling worktrees (validated with a real 2-worktree fixture)
- `ll-issues validate-catalog` detects duplicate IDs and same-file edits, exits non-zero if found
- Integration test: a parallel fan-out with 4 workers each calling `ll-issues` produces no ID collisions and no partial writes
- Docs in parallel-state chapter list `.issues/` as a coordinated mutation path with `ll-issues` as the only safe interface

## Impact

- **Priority**: P3 — Real risk whenever a parallel state generates issues. Not blocking v1 ship if v1 use-cases don't include issue-generation fan-outs, but very easy to hit accidentally.
- **Effort**: Medium — locking primitive + atomic-write refactor + real-filesystem concurrency test
- **Risk**: Medium — `fcntl` locking has subtle cross-process semantics; getting worktree-relative vs. repo-root lock paths wrong makes the lock ineffective
- **Breaking Change**: No — behavior is stricter but additive

## Labels

`cli`, `ll-issues`, `parallel`, `concurrency`, `atomicity`

## Related / See Also

- **FEAT-1189** — shared-context mutation contract (this is the `.issues/` concrete instance)
- **ll:normalize-issues** — today's duct-tape for ID collisions; should remain but be rarely needed
- **ENH-1073** — worktree-mode fan-out (primary driver of this issue)

---

## Session Log
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as follow-up from parallel-family review. `ll-issues` under parallel worktree mode has no current coordination story.

---

## Verification Notes

**Verdict**: DEP_ISSUES — Verified 2026-04-23

- `depends_on: [FEAT-1075]` but FEAT-1075 is in `.issues/deferred/` — the dependency is deferred, not completed. This issue is unblocked in theory (the worktree runner FEAT-1075 is not required to fix the ID allocation logic), but the integration test (`validate_catalog` with real 2-worktree fixture) cannot be written without the runner. Consider splitting: fix the fcntl lock + atomic-write changes now; defer the 2-worktree integration test until FEAT-1075 is re-activated.
- `ll-issues next-id` has no locking — confirmed in `scripts/little_loops/cli/issues/` ✓
- Feature not yet implemented ✓

**Closed: Invalid** | Created: 2026-04-20 | Closed: 2026-04-24 | Priority: P3

## Closing Note

Closed as invalid. The core premise — that workers need `fcntl` locking to coordinate `.issues/` mutations — is wrong. `.issues/` is git-tracked, so each worktree gets its own isolated copy, exactly like all other source files. There is no runtime concurrency hazard; there is only a merge-time naming collision when two workers both pick the same next ID from their respective snapshots. `fcntl` locking cannot prevent this because the workers operate in separate filesystem trees and are long gone by merge time. Reaching into the root repo's `.issues/` to acquire a shared lock would break worktree isolation entirely.

The two genuine sub-problems are filed separately:
- **ENH-1279** — `ll-issues validate-catalog`: post-merge duplicate ID detection
- **ENH-1280** — `ll-issues` atomic writes via `tempfile` + `os.rename()`
