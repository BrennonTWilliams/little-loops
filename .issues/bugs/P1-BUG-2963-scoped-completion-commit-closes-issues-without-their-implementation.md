---
id: BUG-2963
title: Scoped completion commit closes an issue while leaving its implementation
  uncommitted
type: BUG
priority: P1
status: open
discovered_date: 2026-08-01
discovered_by: human
relates_to:
- BUG-2421
- BUG-2424
labels:
- issue-lifecycle
- orchestration
- data-loss
---

# BUG-2963: Scoped completion commit closes an issue while leaving its implementation uncommitted

## Summary

`_commit_issue_completion()` stages **only the issue file**, commits it with an
`implement(<type>): implement <ID>` message, and marks the issue `done` — while
the issue's actual implementation sits in the working tree as unstaged and
untracked files. When the run finishes and the worktree is removed, that code is
destroyed. The issue is recorded as complete and no artifact of the work
survives.

This is the intended BUG-2421 behavior (never `git add -A`) applied to the wrong
case. BUG-2421 correctly assumed the dirty paths were *unrelated* WIP from other
issues. In practice the dirty paths are usually *this issue's own deliverable*,
because the safety-net path fires precisely when the subloop died before
committing its own work.

## Steps to Reproduce

1. Run an orchestrator that closes issues via `issue_lifecycle` (e.g.
   `ll-loop run sprint-refine-and-implement <EPIC>` in a worktree-isolated
   epic branch).
2. Let a subloop write implementation files but exit abnormally (crash, timeout,
   context exhaustion) before committing them.
3. The safety-net path runs `_commit_issue_completion()`.
4. Observe: a commit touching only `.issues/.../P?-<TYPE>-<ID>-*.md`, the issue's
   `status: done`, and a `logger.warning` listing the abandoned paths.
5. When the worktree is removed, the listed paths are gone.

## Current Behavior

Observed in run `sprint-refine-and-implement-20260731T235717` (EPIC-2938):

- `462900cc implement ENH-2943` — 1 file changed (the issue `.md`). Neither
  `cli/loop/rename.py` nor `cleanup.py` was ever committed.
- `affb584f implement ENH-2944` — 1 file changed. `cli/issues/normalize.py` was
  never committed.
- `c9f2681c implement ENH-2952` — issue file plus a decisions fragment only.

The warning at `scripts/little_loops/issue_lifecycle.py:465-469` fired and listed
~65 dirty paths, including `?? scripts/little_loops/cli/issues/normalize.py`,
`?? scripts/little_loops/cli/loop/rename.py`, `?? cleanup.py`, and their four
test files. All three issues were reported closed. The run's `summary.json` read
`{"verdict":"partial","closed":9,"not_closed":0}` — the 3 hollow closures counted
as successes.

The damage is not confined to the lost work: subcommand *wiring* for the missing
modules was committed as collateral in sibling issues' commits, so merging the
branch left `ll-issues` and `ll-loop` raising `ModuleNotFoundError` on import at
`cli/issues/__init__.py:67` and `cli/loop/__init__.py:38,42`. Repaired in
3e76f972.

## Expected Behavior

A completion commit must never close an issue whose implementation is not in the
commit. Given dirty paths at close time, one of:

- **Commit them under this issue** when they are plausibly this issue's
  deliverable (path overlaps the issue's `## Integration Map` / `Files to
  Create`, or the issue is the only one in flight in this worktree), or
- **Refuse to close**: leave `status: in_progress`, emit an explicit failure, and
  let the issue be requeued — the loop's `not_closed`/`abandoned` counters exist
  for exactly this.

Silently committing the bookkeeping and discarding the deliverable is the one
outcome that must not happen. At minimum the verdict must not read `closed`.

## Motivation

Three issues' worth of implementation was destroyed in a single 4.5-hour,
$13.85 run, and the loss was invisible: `summary.json` reported them closed, the
issue frontmatter said `done`, and the only signal was a `logger.warning` inside
a 10K-line log. Any orchestrator using this path can silently lose work.

## Root Cause

`scripts/little_loops/issue_lifecycle.py:414-498`, `_commit_issue_completion()`.

The BUG-2421 comment block at lines 431-440 states the reasoning: stage only the
issue file "but still commits the issue file (per AC #5), only warning about the
dirty paths it leaves behind rather than skipping." The gap is that no branch
distinguishes *unrelated* dirty paths (BUG-2421's premise) from *this issue's
own implementation*, and the closure proceeds unconditionally either way.

The sibling parallel path `_stage_and_commit_issue_scoped()`
(`parallel/orchestrator.py`, BUG-2424) needs the same audit.

## Proposed Solution

1. In `_commit_issue_completion()`, classify the non-issue-file dirty paths
   before committing. A path is *attributable* to this issue when it matches the
   issue's declared `## Integration Map` / `### Files to Create` entries, or when
   no other issue is in flight in this working tree.
2. If attributable paths exist: stage them alongside the issue file. This keeps
   BUG-2421's guarantee (no blind `git add -A`) while preserving the work.
3. If unattributable paths exist: keep the current warn-and-skip, unchanged.
4. If *any* attributable path could not be committed, do not close: return a
   distinct failure so the caller writes `status: in_progress` and increments
   `not_closed` rather than `closed`.
5. Make the loss legible in the summary — emit an `uncommitted_paths` count into
   `summary.json` so a hollow closure is visible without reading the log.
6. Audit `_stage_and_commit_issue_scoped()` in `parallel/orchestrator.py` for the
   same defect.

## Program Design

### Signatures

New helper and result type in `scripts/little_loops/issue_lifecycle.py`:

- `_triage_dirty_paths(info: IssueInfo, porcelain_lines: list[str], sole_issue_in_tree: bool) -> DirtyPathTriage`

  Splits `git status --porcelain` lines into paths this issue owns and paths it
  does not.

- `DirtyPathTriage` — frozen dataclass with `attributable: list[str]` (this
  issue's deliverable, must be committed) and `unattributable: list[str]`
  (unrelated WIP, left alone per BUG-2421's premise).

- `_commit_issue_completion(info: IssueInfo, commit_prefix: str, commit_body: str, logger: Logger) -> CompletionResult`

  Return type replaces the current unconditional `bool` `True`.
  `CompletionResult` is a `StrEnum` of `COMMITTED` (issue file plus all
  attributable paths staged) and `NOT_CLOSED` (attributable paths could not be
  staged).

### Call Path

`close_issue` -> `_commit_issue_completion` -> `git add -- <issue file>` ->
`_triage_dirty_paths` -> `git add -- <attributable>` -> `git commit`; on
`NOT_CLOSED` the caller writes `status: in_progress` and increments
`not_closed` instead of `done`/`closed`. `logger.warning` now reports only
`DirtyPathTriage.unattributable`.

Attribution rule, in precedence order:

1. Path appears in the issue body's `## Integration Map` (including its
   `### Files to Create` subsection) → attributable.
2. `sole_issue_in_tree` is True (worktree-isolated run, one issue in flight) →
   every dirty path is attributable.
3. Otherwise → unattributable.

`_commit_issue_completion()` gains a return type carrying the outcome instead of
its current unconditional `True`:

```python
class CompletionResult(StrEnum):
    COMMITTED = "committed"          # issue file + all attributable paths staged
    NOT_CLOSED = "not_closed"        # attributable paths could not be staged
```

Callers map `NOT_CLOSED` to `status: in_progress` plus the `not_closed` counter
rather than `done`/`closed`. The `logger.warning` stays for the unattributable
list only.

## Integration Map

- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()`
  (lines 414-498), the fix site.
- `scripts/little_loops/parallel/orchestrator.py` —
  `_stage_and_commit_issue_scoped()`, sibling path to audit.
- `scripts/little_loops/loops/*.yaml` — states that count `closed` in
  `summary.json`; must respect the new not-closed signal.
- `scripts/tests/test_issue_lifecycle.py` — new coverage: dirty attributable
  paths get committed; unattributable ones do not; a blocked attributable path
  yields not-closed rather than closed.

## Impact

**Severity: P1.** Silent, unrecoverable loss of completed implementation work,
combined with a false success signal. Any `ll-auto` / `ll-parallel` /
`ll-sprint` / FSM run that hits the safety-net path is exposed. Recovery is
impossible once the worktree is pruned — there is no stash, no branch, no
dangling object.

## Status

Open. Discovered while auditing run
`.loops/runs/sprint-refine-and-implement-20260731T235717/` (EPIC-2938).
ENH-2943, ENH-2944, and ENH-2952 were reopened; the dangling CLI wiring the
partial commits left behind was stripped in 3e76f972.

## Session Log
