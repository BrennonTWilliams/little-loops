---
id: ENH-3198
type: ENH
title: Determine whether auto-refine-and-implement's .issues/completed/ closure branch
  is still reachable
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
relates_to: [BUG-3191]
discovered_date: '2026-08-15'
captured_at: '2026-08-15T19:45:21Z'
---

# ENH-3198: Determine whether auto-refine-and-implement's .issues/completed/ closure branch is still reachable

## Summary

auto-refine-and-implement.yaml counts closures over a union of two paths: issues reaching `status: done` in place, and decomposed parents git-mv'd into `.issues/completed/`. Now that BUG-2732 is done and `ll-issues fd --move` is opt-in, the `completed/` half may be unreachable in practice — but confirming that and deleting the branch is a behavior change to closure accounting, not a cleanup.

## Problem

`scripts/little_loops/loops/auto-refine-and-implement.yaml` counts run closures
over a **union of two paths**, annotated in place with a BUG-2403 citation:

- `init` snapshots both the `.issues/completed/` directory listing *and* the live
  `status: done` set.
- `finalize` diffs both against their post-run states and unions the results.

The dual path exists because leaf issues complete **in place** (frontmatter
`status: done`, never moving directories) while decomposed parents were still
git-mv'd into `.issues/completed/`.

Since then, BUG-2732 landed and `ll-issues fd --move` became opt-in. The
`completed/` half may now be unreachable in every default configuration — in
which case `init` writes an always-empty file each run and `finalize` diffs two
empty sets.

**This is not a doc-sweep item and must not be treated as one.** BUG-3191
explicitly left it alone: deleting the branch changes closure accounting, which
is what decides a run's `verdict` (`success` / `partial` / `phantom` / `no-op`).
Getting it wrong silently under-counts closures and mislabels successful runs.

## Current Behavior

`init` (`scripts/little_loops/loops/auto-refine-and-implement.yaml`) writes two
baseline snapshots per run: a `ls .issues/completed/` listing and a live
`status: done` ID set. `finalize` diffs both against their post-run states and
unions the results into the closure count feeding `summary.json`'s `closed`
figure and the run `verdict`.

On a default-configured repo the `completed/` directory is never created, so the
first snapshot is an empty file and its diff contributes nothing. The union is
therefore equal to the `status: done` half alone — but nothing in the loop or its
tests asserts that, so the claim is inference, not fact.

## Expected Behavior

The reachability of the `completed/` path is a recorded, dated conclusion rather
than something each reader re-derives — and the YAML either drops the branch (if
provably unreachable, with a test pinning closure counting to the in-place path)
or keeps it with a comment stating why.

## Program Design

This is chiefly a YAML change gated on an investigation; the only new Python
symbol is the pinning test.

### Signatures

`test_finalize_counts_in_place_done_closure(tmp_path: Path) -> None` — assert `finalize` counts an issue closed via frontmatter `status: done`, with no `.issues/completed/` directory present, and that `summary.json`'s `closed` figure matches the pre-change YAML for the same fixture.

`moved_to_completed_is_reachable() -> bool` — investigation helper only, not shipped: enumerate call sites reaching `finalize_decomposition(..., move_to_completed=True)` and report whether any default path arrives there.


Sites, if the branch is removed:

- `init` state (`scripts/little_loops/loops/auto-refine-and-implement.yaml`) — drop the `ls .issues/completed/` snapshot and the file it writes, keeping the live done-set snapshot as the sole baseline.
- `finalize` state (same file) — drop the `git ls-tree`/`ls` half of the diff and the union step, leaving the `status: done` diff as the closure count.
- `ll-issues fd --move` (`scripts/little_loops/cli/issues/finalize_decomposition.py`) — the one known writer of `.issues/completed/`. **Not modified by this issue**; it is the artifact whose reachability decides the outcome.

New test, in an existing loop-behavior test module: assert `finalize` counts an
issue closed in place via `status: done`, and that `summary.json`'s `closed`
figure is unchanged for a representative run against the pre-change YAML.

### Call Path

`ll-loop run auto-refine-and-implement` -> `init` (snapshot: `completed/` listing
+ live done-set) -> `autodev` sub-loop -> `finalize` -> diff both baselines ->
union -> `summary.json` `closed` -> **run `verdict`** (the value at risk) ->
`subloop_outcome` token.

The `completed/` writer sits on a different path entirely:
`/ll:manage-issue` decomposition -> `ll-issues fd --move` ->
`move_to_completed=args.move` -> `git mv` into `.issues/completed/`. Establishing
whether anything reaches that `--move` by default is the whole investigation.

## Scope Boundaries

**In scope**: determining reachability; editing `init`/`finalize` in
`auto-refine-and-implement.yaml` if the answer is "unreachable"; the pinning test;
updating the in-YAML comment if the answer is "keep".

**Out of scope**:
- Changing `ll-issues fd --move` or removing the flag — it is documented legacy behavior and BUG-3191 explicitly preserved its CLI.md entry.
- The defensive `-not -path '.issues/completed/*'` excludes in `backlog-flow-optimizer.yaml` and `issue-staleness-review.yaml`, and the `must not be recreated` guard in the latter. Harmless, and the guard is load-bearing.
- `.issues/completed/` mentions in `CHANGELOG.md`, `.ll/decisions.yaml`, and files under `.issues/` — historical records that are supposed to mention the legacy path.
- The `MERGE-COORDINATOR.md:579` occurrence, which is a deliberate counterexample in a BUG-968 explanation.

## Proposed Solution

Answer the reachability question first, with evidence — then act on the answer.

1. Determine whether any current code path still git-mv's an issue into
   `.issues/completed/`. `ll-issues fd --move` is the known one; establish
   whether it is the *only* one, and whether anything invokes it by default.
2. If unreachable by default but still reachable via `--move`: **leave the
   branch.** It costs one empty file per run and correctly handles a legacy
   opt-in. Close this issue with that finding recorded.
3. If genuinely unreachable: remove the `completed/` half of both `init` and
   `finalize`, and add a test that pins closure counting to the `status: done`
   path so the accounting cannot silently regress.

Either way the outcome is a recorded decision, not a guess. Note that a repo
checked out before the transition may still *have* the directory, so "the
directory is absent here" is not evidence of unreachability.

## Acceptance Criteria

- [ ] A recorded finding on whether any default path still moves issues into `.issues/completed/`.
- [ ] If the branch is removed: a test asserts `finalize` counts an in-place `status: done` closure, and the run verdict is unchanged for a representative run.
- [ ] If the branch is kept: the YAML comment is updated to state the current reachability conclusion and its date, so the next reader does not re-derive it.
- [ ] `ll-loop validate auto-refine-and-implement` passes.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Motivation

Six closed issues already touch this area (BUG-2798, BUG-2728, BUG-2732,
BUG-2733, BUG-2766, BUG-1485). Residue survived every one of them because each
pass treated it as a string sweep rather than asking whether the branch was
load-bearing. This issue exists to settle the question once and write the answer
down.

## Impact

- **Priority**: P3 — no user-visible defect today; the cost is one empty file per run plus recurring reviewer confusion.
- **Effort**: Small-Medium — the investigation is most of it; the edit is small either way.
- **Risk**: Medium if the branch is removed — closure accounting drives run verdicts, so a wrong call mislabels runs. Low if it is kept.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
