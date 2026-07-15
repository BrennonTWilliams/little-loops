---
id: ENH-2643
title: Persist a merge-failure diagnostic artifact when `merge_epic_branch_to_base`
  aborts
type: ENH
status: done
priority: P3
discovered_date: '2026-07-15'
discovered_by: capture-issue
captured_at: '2026-07-15T02:26:46Z'
completed_at: '2026-07-15T02:58:42Z'
decision_needed: false
labels:
- epic-merge
- observability
- loops
confidence_score: 100
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2643: Persist a merge-failure diagnostic artifact when `merge_epic_branch_to_base` aborts

## Summary

When the auto-refine/sprint loop's merge step fails, it records only
`epic_merge_verdict=merge_failed` — no durable detail of *why*. The verify step,
by contrast, writes `verify-detail.txt` (the failing command's output tail). A
merge failure is currently invisible in the run_dir: the operator must
re-reproduce `git merge` by hand to learn the cause.

## Motivation

Observed during `ll-loop run sprint-refine-and-implement --context sprint_name=EPIC-2370`
(2026-07-14): the run reported `merge_failed` with no artifact. The actual cause
— a content conflict in `.ll/decisions.yaml` (see BUG-2642) — was only found by
manually re-running `git merge --no-commit --no-ff`. A decisions-log id collision
silently blocked an EPIC merge-back with zero diagnostic in the run_dir.

## Current Behavior

`merge_epic_branch_to_base` (`scripts/little_loops/worktree_utils.py`) logs
`result.stderr` to the `Logger`, then `git merge --abort`s and returns False.
It persists nothing to the run_dir. The loop only writes `epic-merge-verdict.txt`
(`merge_failed`). There is no `merge-detail.txt` / conflicted-file list /
returncode artifact.

## Expected Behavior

On merge failure, write a diagnostic artifact under `${context.run_dir}/`
mirroring the verify gate's `verify-detail.txt`, e.g.:

- `merge-detail.txt` — the tail of `git merge` stderr/stdout.
- The list of conflicted paths (`git diff --name-only --diff-filter=U`) captured
  before `git merge --abort`.
- `merge-returncode.txt` — the failing returncode.

so `merge_failed` is self-diagnosing without re-running git.

## Implementation Sketch

- In `merge_epic_branch_to_base`, before `git merge --abort`, capture the
  conflicted-file list and combine with `result.stderr`/`stdout`. Reuse the
  `format_verify_detail` tail idiom (`worktree_utils.py`, ENH-2641) so the same
  bounded stdout+stderr-tail formatting applies.
- Thread a `run_dir: Path | None` (or a detail-callback) into the function so it
  can write the artifact; the loop's merge state passes `${context.run_dir}`.
- Loop `merge_epic_branch` state: write `merge-detail.txt` /
  `merge-returncode.txt` alongside `epic-merge-verdict.txt`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

1. Add a `merge_failed`-branch test to
   `scripts/tests/test_builtin_loops.py::TestMergeEpicBranchConfigReadShell`
   (forces a real conflict, asserts `merge-detail.txt` / `merge-returncode.txt`
   exist), plus a "no artifact on success" companion assertion.
2. Update `docs/reference/API.md` (§ lines 3323–3359) — document the new
   `run_dir` kwarg and the `merge-detail.txt` / `merge-returncode.txt` artifacts.
3. Update `docs/development/MERGE-COORDINATOR.md` (§ 5, lines 159–163) — add a
   sentence on the new merge-diagnostic artifact pair, mirroring the verify-gate
   description.
4. (Optional) `docs/ARCHITECTURE.md:490` — only if the artifact convention is
   described nearby.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/worktree_utils.py:384` — `merge_epic_branch_to_base()`.
  Current failure path (lines 429–432) logs `result.stderr` via `logger.warning`,
  runs `git merge --abort`, returns `False` — persists nothing. Add a
  `run_dir: Path | None = None` keyword param; on the failure branch, *before*
  `git merge --abort`, capture the conflicted-file list
  (`git diff --name-only --diff-filter=U` via `git_lock.run`) and write the
  three artifacts under `run_dir` when it is non-`None`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:652` — the
  `merge_epic_branch` state's `merge_epic_branch_to_base(...)` call (inside the
  `PYEOF` heredoc). Thread `run_dir=run_dir` through so the function writes the
  detail artifacts; the state already binds `run_dir = Path("""${context.run_dir}""")`
  and emits `epic-merge-verdict.txt` via the heredoc's stdout redirect
  (`> "$RUN_DIR/epic-merge-verdict.txt"`, line 503).

### Reuse (do not reimplement)
- `scripts/little_loops/worktree_utils.py:245` — `format_verify_detail(stdout, stderr, *, max_lines=40, max_chars=2000)`.
  Produces the bounded `stderr + stdout` line-tail. Call it on
  `result.stdout` / `result.stderr` to build `merge-detail.txt` verbatim,
  exactly as the verify path does at `auto-refine-and-implement.yaml:411`.

### Established artifact-writing pattern to mirror
- `auto-refine-and-implement.yaml:374–383` — the verify gate's `emit()` helper:
  `(run_dir / 'verify-returncode.txt').write_text(str(returncode))` and
  `(run_dir / 'verify-detail.txt').write_text(detail)` (detail written verbatim,
  NOT re-clipped — ENH-2641). Mirror this for `merge-returncode.txt` /
  `merge-detail.txt` plus a new conflicted-paths capture.

### Dependent Callers
- `scripts/little_loops/parallel/orchestrator.py:1361` — `_merge_epic_branch_to_base()`
  wrapper. The parallel orchestrator has **no per-run `run_dir`** concept, so it
  simply omits the new param (defaults to `None` → no artifact written). The new
  param must be keyword-only with a `None` default so this caller is unaffected.
  This is the ONLY other caller (`grep merge_epic_branch_to_base`).

### Tests
- `scripts/tests/test_worktree_utils.py` — `TestMergeEpicBranchToBase` (class at
  line 201) already exercises `merge_epic_branch_to_base` directly. Extend it:
  add a case that drives a real conflicting merge in a tmp git repo, passes
  `run_dir=tmp_path`, and asserts `merge-detail.txt`, `merge-returncode.txt`,
  and the conflicted-paths artifact exist with expected content — plus a
  regression case that omitting `run_dir` writes nothing (guards the
  orchestrator caller, which passes no `run_dir`). Reuse the class's existing
  tmp-git fixture setup rather than building a new harness.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:2985` — `TestMergeEpicBranchConfigReadShell`
  exercises the `merge_epic_branch` FSM state end-to-end (its `_run()` harness at
  ~line 3023 extracts `loop["states"]["merge_epic_branch"]["action"]`, substitutes
  `${context.run_dir}`/`${context.scope}`, and runs it via `bash -c`). Existing
  cases assert `epic-merge-verdict.txt` for the `merged`/`held_open`/`skipped`/
  `verify_failed` branches, but **no test currently drives the `merge_failed`
  branch** (a real `git merge` conflict on the epic-branch merge-back; YAML line
  ~660 `print("merged" if merged else "merge_failed")`). Add a case that forces a
  real merge conflict (diverging edits to the same file on `main` and the epic
  branch, same technique as `test_conflicting_merge_returns_false_and_aborts` in
  `test_worktree_utils.py`) and asserts `epic-merge-verdict.txt == "merge_failed"`
  **plus** the new `merge-detail.txt` / `merge-returncode.txt` exist under
  `run_dir` — mirroring the verify-gate artifact assertions at
  `test_builtin_loops.py:2950-2951`. Add a companion "no artifact on merge success"
  assertion mirroring `test_builtin_loops.py:2956`.
- `scripts/tests/test_orchestrator.py` — confirmed **no** direct reference to
  `merge_epic_branch_to_base` / `_merge_epic_branch_to_base` (grep clean), so the
  keyword-only `run_dir=None` default leaves the orchestrator path and its tests
  unaffected — no update required. Recorded here so a future pass doesn't re-audit.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3323-3359` — documents the BUG-2614 free-function
  extraction (`merge_epic_branch_to_base` signature/kwargs, line 3325) and the FSM
  loop writing `$RUN_DIR/epic-merge-verdict.txt` (line 3353). Add the new
  `run_dir` kwarg and the `merge-detail.txt` / `merge-returncode.txt` artifacts
  alongside the existing verify-artifact description [Agent 2 finding].
- `docs/development/MERGE-COORDINATOR.md:159-163` — § "5. EPIC-Aware Merge Path";
  most detailed prose on the merge/verify free-function split and the FSM loop's
  artifact-writing convention. Add a sentence describing the `merge-detail.txt` /
  `merge-returncode.txt` pair, mirroring how `verify-detail.txt` is documented in
  the adjacent verify-gate section [Agent 2 finding].
- `docs/ARCHITECTURE.md:490` — references `merge_epic_branch_to_base` in the
  EPIC-merge routing narrative (no signature detail; low coupling — update only if
  the artifact convention is described nearby) [Agent 2 finding].

## Scope Boundaries

**In scope**: capturing and persisting the merge-failure detail.
**Out of scope**: fixing the recurring decisions-log conflict itself (that is
BUG-2642); changing merge strategy or conflict-resolution behavior.

## Impact

- **Priority**: P3 — observability only; does not change merge outcomes, but
  turns a silent stall into a self-diagnosing one and saves manual re-reproduction.
- **Effort**: Small — mirror the existing verify-detail artifact plumbing.
- **Risk**: Low — additive diagnostic writes; no behavior change to the merge itself.

## Related

- BUG-2642 — the recurring decisions-log conflict this would have diagnosed.
- ENH-2641 / `format_verify_detail` — the verify-detail tail idiom to reuse.

## Resolution

**Done** — 2026-07-15. `merge_epic_branch_to_base` gained an optional keyword-only
`run_dir: Path | None = None` param; on merge failure (before `git merge --abort`)
it persists `merge-detail.txt` (bounded `stderr + stdout` tail via
`format_verify_detail`), `merge-returncode.txt`, and `merge-conflicts.txt`
(`git diff --name-only --diff-filter=U`). The FSM `merge_epic_branch` state threads
`run_dir=run_dir` through; the `ll-parallel` orchestrator wrapper omits it (None →
no artifact), so its path is unchanged.

- `scripts/little_loops/worktree_utils.py` — new `run_dir` kwarg + failure-path writes.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — thread `run_dir`.
- `scripts/tests/test_worktree_utils.py` — conflict-with-run_dir, conflict-without-run_dir,
  and success-no-artifacts cases.
- `scripts/tests/test_builtin_loops.py` — `merge_failed` end-to-end case (real conflict)
  + no-artifact-on-success assertion; `_setup_repo`/`_run` gained a `conflict` flag.
- `docs/reference/API.md`, `docs/development/MERGE-COORDINATOR.md` — documented the pair.

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-15T02:58:14Z - persist merge-failure diagnostic (implementation)
- `/ll:ready-issue` - 2026-07-15T02:52:10 - `b07b6793-36b3-4b23-905a-8f880191f0a6.jsonl`
- `/ll:wire-issue` - 2026-07-15T02:50:01 - `702b6e00-f980-4b53-842c-f7d2b5801dbf.jsonl`
- `/ll:refine-issue` - 2026-07-15T02:43:19 - `24810d9d-ab7b-40fe-9efe-4d8305a5c480.jsonl`
- `/ll:capture-issue` - 2026-07-15T02:26:46Z - session: sprint-refine-and-implement EPIC-2370 review
