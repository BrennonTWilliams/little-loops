---
id: ENH-3709
type: ENH
title: scratch-cleanup.sh never sweeps stray subdirectories under .loops/tmp/scratch
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:30:29Z'
relates_to:
- ENH-3706
- BUG-3705
- ENH-2924
- ENH-2927
deferred_by: human
deferred_date: '2026-10-03T18:07:43Z'
deferred_reason: Await evidence of recurring nested scratch artifacts after a one-time cleanup; the current seven-file inventory does not justify a recursive collector.
---

# ENH-3709: scratch-cleanup.sh never sweeps stray subdirectories under .loops/tmp/scratch

## Summary

`hooks/scripts/scratch-cleanup.sh` intentionally considers only regular files directly in `.loops/tmp/scratch`, so nested scratch artifacts are outside its retention policy. The 2026-10-03 inventory found `.ll`, `split`, `head`, `pbuild`, and `__pycache__`: seven files totaling roughly 1.3 MB, with no evidence yet that these directories recur after cleanup.

**Deferred by the user-approved pre-implementation review.** Prefer a one-time cleanup of verified disposable artifacts and investigation if they recur. Do not add recursive collection to ENH-3706 or implement a recurring cleanup mechanism solely from this inventory.

The original root-shadowing justification was incorrect for this repository: completed ENH-2924 makes `find_project_root` prefer an ancestor with both `.git` and `.ll`, and completed ENH-2927 centralizes `.ll` creation through `resolve_ll_dir`. Resolution from scratch returned the correct repository root. Non-Git nearest-`.ll` fallback remains intentional and is not proof of a new defect.

## Current Behavior

The hook's `find -maxdepth 1 -type f` excludes subdirectories and nested files. The observed inventory comprises an empty `.ll`, one old Python cache file, one copied API document, three copied Python files, and one HTML artifact. The observation establishes residual clutter, not unbounded recurring production or an active root-resolution failure.

Current `find_project_root` tests cover a stray nested `.ll`, a worktree `.git` file, non-Git fallback, and monorepo subprojects. The scratch/root review's 27 selected tests passed, and direct resolution from this repo's scratch directory returned the actual repository root.

## Expected Behavior

Keep this issue deferred until recurrence or another measurable ongoing impact is demonstrated after a one-time cleanup. Reopening requires the recreated paths, timestamps, generating command/hook and cwd where identifiable, and a repeatable example. Investigate and fix a reproduced producer defect before considering recurring recursive collection.

If recurrence justifies recursive retention, first specify its design and tests. Use ENH-3706's per-file policy consistently: direct or nested regular files older than seven days receive no permanent exemption based on a live filename PID; younger files retain the existing 24h/live-PID semantics. Fresh descendants must survive even when their parent directory is old.

## Motivation

A new recursive deletion mechanism expands both filesystem work and the scope of automatic removal. Seven residual files without recurring growth do not justify that cost. The corrected framing keeps a useful recurrence investigation available without treating an already-fixed root-resolution problem as an implementation trigger.

## Proposed Solution

**Selected disposition: defer recurring cleanup pending recurrence evidence.** No recursive hook implementation is selected in this review. ENH-3706 remains independent and continues to exclude subdirectories.

1. Record the existing small inventory and corrected root-resolution evidence; relate this issue to completed ENH-2924 and ENH-2927.
2. A one-time cleanup may remove verified disposable artifacts. This issue-file update does not perform that filesystem cleanup or establish that recurrence has been tested.
3. Reopen only with evidence of recreation or measurable ongoing cost. Identify the producer and choose a producer fix if the recreated artifact is unintended.
4. If intentional nested scratch production needs retention, define per-file eligibility using the same two tiers as ENH-3706, never follow symlinks, and remove empty directories bottom-up with `rmdir`. Never infer that all descendants are disposable from a parent directory's mtime and never delete a whole subtree on that basis.
5. Before recursive implementation, refine Program Design, Integration Map, Implementation Steps, and Acceptance Criteria for the reproduced case, including how enumeration/deletion fits the hook's best-effort timeout contract. The current sections record the deferral and future constraints, not an implementation-ready recursive design.

## Scope Boundaries

- **In scope now**: correcting this issue, recording the inventory and existing fixes, and a human deferral with an explicit reopening condition.
- **Out of scope now**: recursive deletion, automatic empty-directory pruning, root-resolution changes, modifications to ENH-3706's direct-file scope, and performing a one-time cleanup as part of the issue-file edit.
- **Required if reopened for recursive retention**: per-file age decisions, preservation of fresh descendants, no traversal through symlinks, safe complete-path handling, bottom-up empty-directory removal, and an explicit best-effort timeout contract.
- This deferred issue does not block ENH-3706. No dependency edge is introduced merely because the issues concern the same scratch directory.

## Integration Map

### Files to Modify
- This issue file — corrected justification, deferral, reopening evidence, and future safety constraints only.
- If reopened, identify the reproduced producer before assigning code changes; `hooks/scripts/scratch-cleanup.sh` is a candidate only if recursive retention is selected.

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — invokes scratch cleanup at SessionStart with a 5s timeout; no changes while deferred.
- `scripts/little_loops/paths.py` — owns the already-correct `find_project_root` and `resolve_ll_dir` behavior; no change justified by this inventory.

### Similar Patterns
- Completed ENH-2924 and ENH-2927 — existing root-resolution and `.ll` creation fixes, not outstanding blockers.
- ENH-3706 — selected universal seven-day eligibility and retained 24h dead-PID tier for direct regular files; use the same policy if nested retention is later justified.

### Tests
- `scripts/tests/test_program_design_gate.py` `TestFindProjectRoot` — existing stray-directory/worktree/non-Git coverage supports the correction.
- `scripts/tests/test_hooks_integration.py` `TestScratchCleanupSessionEnd` — existing direct-file contract; no test/code additions while deferred.
- On reopening, reproduce the creator. If recursion is selected, cover an old parent with a fresh descendant, old/live-PID files under the universal cap, nested symlinks and unchanged external targets, complete filenames, bottom-up empty removal, and interrupted/repeated sweeps.

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` and mirrored `.claude/CLAUDE.md`/`AGENTS.md` — amend only if a later implementation changes recursive retention. No product documentation change is required for this deferral.

### Configuration
- No configuration change is selected.

## Program Design

### Types

- No new types or recursive collector are designed while deferred. Existing `Path`-based root resolution supplies the evidence for the corrected claim.

### Signatures

- `find_project_root(start: Path) -> Path | None` — existing function in `scripts/little_loops/paths.py`; prefers a Git/project ancestor over a stray nested `.ll`.
- `resolve_ll_dir(start: Path | None = None, create: bool = False) -> Path | None` — existing centralized lookup/creation function; no proposed behavior change.

### Call Path

`resolve_ll_dir` -> `find_project_root` -> inspect ancestor `.git`/`.ll` markers within the repository boundary -> resolved project `.ll` path. This is the existing ENH-2924/2927 resolution path, not a new recursive deletion path. A collector call path must be specified from recurrence evidence before this issue returns to implementation planning.

## Implementation Steps

1. Preserve `status: deferred` and the human deferral reason; retain this issue as the recurrence investigation record.
2. After a one-time cleanup, document any recreation with paths, timestamps, command/hook, cwd, and measured impact. No recurrence check or cleanup has been performed by this issue-file update.
3. If recurrence warrants reopening, reproduce it and choose a producer fix or justified per-file retention design. Rewrite the directive sections and obtain fresh readiness scores before implementation.
4. For any eventual code change, add the reproduced regression and applicable recursive safety cases, then run `python -m pytest scripts/tests/`; use the existing test matrix for any required platform checks.

## Impact

- **Priority**: P4 — seven residual files, approximately 1.3 MB, without a demonstrated recurring producer.
- **Effort**: Small for this correction/deferral; implementation scope must be estimated after recurrence is reproduced.
- **Risk**: Low while deferred. Recursive deletion would expand the automatic-removal surface and requires fresh review.
- **Breaking Change**: No for this deferral; any later nested retention change must explicitly assess loss of the existing exclusion guarantee.

## Acceptance Criteria

- [x] The unconditional root-shadowing claim is corrected and completed ENH-2924/ENH-2927 are linked.
- [x] The observed five-directory/seven-file inventory and lack of demonstrated recurrence are recorded.
- [x] Human deferral and the evidence required to reopen are stated; ENH-3706 is not blocked by this issue.
- [ ] Before reopening, recurrence or measurable ongoing impact after a one-time cleanup is documented with a repeatable example.
- [ ] Before implementation, the selected producer fix or justified recursive retention design has concrete Program Design, files, tests, scope, and fresh readiness scores. Recursive retention, if chosen, applies the shared per-file tiers, preserves fresh descendants and external symlink targets, and removes only empty directories bottom-up.

## Status

**Deferred** | Created: 2026-10-03 | Priority: P4 | Deferred after review: 2026-10-03

## Session Log
- `/ll:capture-issue` - 2026-10-03T17:30:52 - `782c403d-3c0b-47cc-a461-f433badb1263.jsonl`
