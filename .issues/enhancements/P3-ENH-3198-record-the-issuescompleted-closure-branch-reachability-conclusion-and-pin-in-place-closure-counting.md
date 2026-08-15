---
id: ENH-3198
type: ENH
title: Record the .issues/completed/ closure-branch reachability conclusion and pin
  in-place closure counting
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
relates_to: [BUG-3191]
discovered_date: '2026-08-15'
captured_at: '2026-08-15T19:45:21Z'
---

# ENH-3198: Record the .issues/completed/ closure-branch reachability conclusion and pin in-place closure counting

## Summary

`auto-refine-and-implement.yaml` counts closures over a union of two paths: issues
reaching `status: done` in place, and decomposed parents git-mv'd into
`.issues/completed/`. The reachability question is now **settled** (see Findings):
no in-repo caller passes `--move`, so the `completed/` half is unreachable by
automation but still reachable via the opt-in flag — and its snapshot feeds a
**second consumer chain** (three verdict signals) that makes removal actively
harmful on upgraded repos. The work is to write that conclusion down where the
next reader finds it, correct a false comment that has misled every prior pass,
and pin both paths with tests — not to delete the branch.

## Findings

Established 2026-08-15 by direct inspection; recorded here so no future pass
re-derives it.

**1. Nothing invokes `--move` by default.** Every in-repo caller of
`ll-issues finalize-decomposition` invokes it bare:

- `scripts/little_loops/loops/autodev.yaml:1130`, `autodev.yaml:1485`
- `scripts/little_loops/loops/recursive-refine.yaml:431`, `recursive-refine.yaml:722`
- `scripts/little_loops/loops/rn-decompose.yaml:232`

No skill or command invokes `ll-issues finalize-decomposition` at all — the five
loop states above are its only callers.

The only `--move` occurrences outside `.issues/` are the flag definition
(`scripts/little_loops/cli/issues/finalize_decomposition.py:91`), its CLI.md row
(`docs/reference/CLI.md:1527`), and one test
(`scripts/tests/test_recursive_finalize.py:153`).
`scripts/little_loops/recursive_finalize.py:171` gates the move on
`move_to_completed and "completed" not in parent_path.parts`, defaulting `False`
(BUG-2732).

**Corollary: the `init` comment is factually wrong today.**
`auto-refine-and-implement.yaml:90-91` claims the baseline "captures autodev
decomposition closures (enqueue_children git-mv's decomposed umbrellas into
completed/)". Autodev calls `fd` bare, so it git-mv's nothing. The only writer to
`.issues/completed/` is a human running `--move` by hand. This false claim is the
most likely reason prior passes kept re-deriving (and mis-deriving) the branch's
purpose, and correcting it is the highest-value edit in this issue.

**Conclusion: unreachable by default, still reachable via the documented opt-in
`--move`.** By the original decision rule that means *keep the branch* — it costs
one empty file per run and correctly serves a legacy opt-in.

**2. The branch is not merely a cheap no-op — removing it would regress upgraded
repos.** `$P-completed-now.txt` feeds **two** files:

- `auto-refine-and-implement.yaml:782` — the `closed-union` CLOSED **diff**
  (baseline → now), which is what the original framing described.
- `auto-refine-and-implement.yaml:791` — `closed-now-union`, the **full-snapshot**
  set, with deliberately different semantics (comment at lines 786-789: an issue
  closed *before* the run that reappears in `autodev-passed` must not read as
  "not closed").

*Why the legacy IDs cannot arrive any other way* — the load-bearing step, verified
2026-08-15: `completed` is **not an issue category**
(`scripts/little_loops/config/features.py:204-218`; `REQUIRED_CATEGORIES` is
bugs/features/enhancements), and the list walk iterates `config.issue_categories`
only (`scripts/little_loops/issue_parser.py:2510,2540`). So
`ll-issues list --json --status done` structurally *cannot* see files under
`.issues/completed/`, and the `ls` snapshot is their sole route into the union.
(`issue_parser.py:1650-1653` scans the legacy dir, but only for
highest-ID allocation — not for listing.)

*Blast radius is wider than NOT_CLOSED* — `closed-now-union` has **three**
consumers, so dropping `completed-now.txt` degrades three independent signals:

- `:837` — the `NOT_CLOSED` exclusion (`autodev-passed − closed-now-union`).
- `:824` — the `ABANDONED` subtraction. Legacy IDs lingering in
  `autodev-queue.txt` would stop being subtracted and count as abandoned.
- `:806` — the `INFLIGHT_UNRESOLVED` guard. A sentinel for a legacy-closed issue
  would flip to unresolved.

Each of those feeds the verdict ladder, so the regression is not merely inflated
`not_closed`: a clean run can flip to `incomplete-abandoned` (ABANDONED > 0 takes
precedence over every `closed > 0` bucket) or to `phantom` — both of which exit 1
and route to the `incomplete` terminal, rendering a successful run as a failure.
This is a positive reason to keep the branch, not just the absence of a reason to
remove it.

**3. Snapshot asymmetries (documented, not fixed here).** Three distinct ones sit
in this block; all are currently harmless, but they are exactly what a future
reader will be reasoning about:

- `init:92` snapshots with `ls .issues/completed/` (working tree, includes
  untracked files); `finalize:731` snapshots the epic-branch case with
  `git ls-tree -r --name-only "$EPIC_BRANCH"` (tracked only). `comm -13` counts
  only additions, so an untracked-baseline case under-reports to zero rather than
  over-counting.
- `init`'s baseline is **never** branch-aware — there is no `EPIC_BRANCH` handling
  in `init` at all — while `finalize`'s "now" side is (ENH-2609). On an epic run
  the two sides of the diff are therefore drawn from different trees.
- On an epic run the `done-now` snapshot uses
  `git grep -lE "^status: *done" <branch> -- .issues`, which **does** traverse
  `.issues/completed/`. So the two snapshots overlap on epic runs while being
  disjoint on default runs. Harmless (both feed `sort -u` unions) but it defeats
  the "leaves never enter completed/" mental model the comments assert.

## Problem

The conclusion above is not written down anywhere durable. Six closed issues
already touched this area (BUG-2798, BUG-2728, BUG-2732, BUG-2733, BUG-2766,
BUG-1485) and the residue survived every one, because each pass treated it as a
string sweep rather than asking whether the branch was load-bearing. BUG-3191
correctly declined to touch it. Without a recorded decision and a test, the next
sweep deletes it — and per Finding 2 that silently mislabels runs on upgraded
repos, since closure accounting drives the run `verdict`
(`success` / `partial` / `phantom` / `no-op`).

## Current Behavior

`init` (`scripts/little_loops/loops/auto-refine-and-implement.yaml:88-114`) writes
two baseline snapshots per run: a `ls .issues/completed/` listing and a live
`status: done` ID set. `finalize` (lines 728-791) diffs both against their post-run
states, unions the diffs into CLOSED, and separately unions the full *now*
snapshots into the NOT_CLOSED exclusion set.

On a default-configured repo the `completed/` directory is never created, so the
first snapshot is an empty file and its diff contributes nothing. Nothing in the
loop or its tests asserts that in-place `status: done` closures are counted, so
the in-place path — the one that actually carries every closure today — is
unpinned.

## Expected Behavior

The reachability conclusion is a recorded, dated decision in two places (a
decisions entry and the two canonical YAML comments), and a test pins closure
counting to the in-place `status: done` path so the accounting cannot silently
regress if the `completed/` branch is later removed.

## Program Design

This is a comment/decision-record change plus one new test. No production Python
or YAML logic changes.

### Signatures

`test_finalize_counts_in_place_done_closure(tmp_path: Path) -> None` — assert `finalize` counts an issue closed via frontmatter `status: done` with no `.issues/completed/` directory present, and that `summary.json`'s `closed` figure reflects that closure.

`test_finalize_excludes_legacy_completed_ids_from_not_closed(tmp_path: Path) -> None` — seed a legacy `.issues/completed/BUG-9999-x.md` and list `BUG-9999` in `autodev-passed.txt`; assert `summary.json` reports `not_closed == 0`. This is the test that **fails if the `completed/` branch is deleted**, and it is the pin Finding 2 actually calls for.

Note on why both are needed: `test_finalize_counts_in_place_done_closure` still
passes after someone removes the `completed/` branch, so on its own it does not
protect against the failure mode this issue exists to prevent.

### Test mechanics

The `finalize` action is ~290 lines and shells out to `ll-issues`, so this is not
a one-line test. Established facts for the implementer:

- **Harness precedent**: `scripts/tests/test_general_task_loop.py:1856`
  (`_load_script` + `_bash`) — load the loop YAML, substitute `${context.*}` and
  `${context.run_dir}`, run the action under bash with `cwd` set to a tmp project.
- `${captured.issue_set.output}` also needs substituting (empty string is fine);
  it is interpolated in the `INPUT_SIZE` fallback branch.
- The test must build a **real mini project root** (`.ll/ll-config.json` plus
  `.issues/bugs/`) in `tmp_path`. Without it `find_project_root` finds nothing,
  `ll-issues list` returns non-zero, `done_ids` is silently empty, and the
  assertion passes vacuously.
- **Pre-create empty `*-completed-baseline.txt` and `*-done-baseline.txt`.**
  `comm` fails on a missing operand and the `2>/dev/null` swallows it, so a
  missing baseline zeroes the closure count instead of erroring.
- No existing test module exercises this loop's shell actions
  (`test_builtin_loops.py` et al. assert on parsed YAML structure only). A new
  `scripts/tests/test_auto_refine_closure_accounting.py` is cleaner than wedging
  these in.

### Sites

- `.ll/decisions.d/` — a decision entry recorded via `ll-issues decisions add` capturing Findings 1 and 2 with today's date. This is the durable record; the YAML comments point at it.
- `init` state (`scripts/little_loops/loops/auto-refine-and-implement.yaml`, the `ENH-2385:`/`BUG-2403:` comment block above the `completed-baseline` snapshot) — **correct the false git-mv claim** (Finding 1 corollary), then state the conclusion and date.
- `finalize` state (same file, the `CLOSED is ground truth` block in the state header and the `ENH-2385:` block above the `completed-now.txt` snapshot) — same, and enumerate the `closed-now-union` consumers from Finding 2 so the uses of `completed-now.txt` are not conflated.
- New test module — the two pinning tests above.

Sites are named by comment marker rather than line number deliberately: the
numbers cited throughout this issue are a 2026-08-15 snapshot and will drift
before implementation (they are already off by one from the original capture).

**Explicitly left alone**: the comments at lines 15-17, 38, 277, and 741-742. They
are accurate; editing all seven sites produces a scattered diff for no gain.

### Call Path

`ll-loop run auto-refine-and-implement` -> `init` (snapshot: `completed/` listing +
live done-set) -> `autodev` sub-loop -> `finalize` -> two diffs -> **union ->
`closed-union` -> `summary.json` `closed` -> run `verdict`**, and separately
**full-snapshot union -> `closed-now-union` -> {NOT_CLOSED exclusion, ABANDONED
subtraction, INFLIGHT_UNRESOLVED guard} -> `verdict`**. Both files consume
`$P-completed-now.txt`; only the first branch was previously documented.

The `completed/` writer sits on a different path entirely:
`ll-issues fd --move` -> `move_to_completed=args.move` -> `git mv` into
`.issues/completed/`. Per Finding 1 **no automation reaches it at all** — not
autodev, not recursive-refine, not `/ll:manage-issue`, which never invokes `fd`.
The only live writer is a human passing `--move` by hand.

## Scope Boundaries

**In scope**: recording the decision; updating the two canonical YAML comment
blocks; the pinning test.

**Out of scope**:
- Removing the `completed/` branch from `init`/`finalize` — Finding 2 rules it out.
- Fixing any of the three snapshot asymmetries in Finding 3 (`ls` vs `git ls-tree`, the never-branch-aware `init` baseline, the epic-run `git grep` overlap) — all currently harmless; file separately if any ever matters.
- Changing `ll-issues fd --move` or removing the flag — documented legacy behavior; BUG-3191 explicitly preserved its CLI.md entry.
- The defensive `-not -path '.issues/completed/*'` excludes in `backlog-flow-optimizer.yaml` and `issue-staleness-review.yaml`, and the `must not be recreated` guard in the latter. Harmless, and the guard is load-bearing.
- `.issues/completed/` mentions in `CHANGELOG.md`, `.ll/decisions.yaml`, and files under `.issues/` — historical records that are supposed to mention the legacy path.
- The `MERGE-COORDINATOR.md:579` occurrence, a deliberate counterexample in a BUG-968 explanation.

## Proposed Solution

1. Record a decision entry (`ll-issues decisions add`) stating: as of 2026-08-15
   **no automation at all** moves issues into `.issues/completed/`; the branch is
   retained because `--move` remains a documented opt-in **and** because
   `completed-now.txt` feeds `closed-now-union`, whose three consumers
   (NOT_CLOSED, ABANDONED, INFLIGHT_UNRESOLVED) all drive the verdict — dropping
   it would flip clean runs to `incomplete-abandoned`/`phantom` on repos upgraded
   from pre-BUG-2732 little-loops.
2. Correct the false git-mv claim in the `init` comment block (Finding 1
   corollary), and update the `init` and `finalize` comment blocks with the
   conclusion, its date, and a pointer to the decision entry — including the
   enumeration of `closed-now-union`'s consumers.
3. Add `test_finalize_counts_in_place_done_closure`, pinning closure counting to
   the in-place `status: done` path.
4. Add `test_finalize_excludes_legacy_completed_ids_from_not_closed`, which fails
   if the `completed/` branch is removed — the actual guard against the failure
   mode this issue exists to prevent.

Note for any future reader: a repo checked out before the transition may still
*have* the directory, so "the directory is absent here" is never evidence of
unreachability.

## Acceptance Criteria

- [ ] A decision entry exists under `.ll/decisions.d/` recording Findings 1 and 2 with the date.
- [ ] The `init` comment block no longer claims `enqueue_children` git-mv's decomposed umbrellas into `completed/` (it does not).
- [ ] The `init` (`ENH-2385:`/`BUG-2403:` block) and `finalize` (state-header `CLOSED is ground truth` block and the `ENH-2385:` block above the `completed-now.txt` snapshot) comments state the reachability conclusion, its date, and the decision-entry pointer; the other five `completed/` comment sites are untouched.
- [ ] The `finalize` comment distinguishes the two files fed by `$P-completed-now.txt` (the CLOSED diff and `closed-now-union`) and enumerates `closed-now-union`'s three consumers (NOT_CLOSED, ABANDONED, INFLIGHT_UNRESOLVED).
- [ ] A test asserts `finalize` counts an in-place `status: done` closure with no `.issues/completed/` directory present.
- [ ] A test asserts a legacy `.issues/completed/` ID appearing in `autodev-passed.txt` yields `not_closed == 0` — and that test fails if the `completed/` snapshot branch is deleted from `init`/`finalize` (verify by deleting it locally before committing).
- [ ] `ll-loop validate auto-refine-and-implement` passes.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Motivation

Six closed issues already touched this area and the residue survived every one.
The reachability answer is cheap to derive and expensive to re-derive; the second
consumer (Finding 2) is easy to miss and turns an apparently safe cleanup into a
verdict regression. This issue exists to settle both once and write them down.

## Impact

- **Priority**: P3 — no user-visible defect today; the cost is recurring reviewer confusion and the standing risk of a well-intentioned deletion.
- **Effort**: Small-to-medium — the investigation is complete and the comment/decision edits are trivial, but the two tests execute a ~290-line shell action against a synthesized project root (see Test mechanics) and are the bulk of the work.
- **Risk**: Low — no production logic changes.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
