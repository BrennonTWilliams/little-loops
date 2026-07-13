---
id: ENH-2630
title: merge_epic_branch re-runs full suite already run by verify state
type: enhancement
status: open
priority: P3
captured_at: "2026-07-13T18:30:06Z"
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to: [BUG-2629, BUG-2614]
decision_needed: true
---

# ENH-2630: merge_epic_branch re-runs full suite already run by verify state

## Motivation

In the `auto-refine-and-implement` FSM loop, a completed EPIC runs the full test
suite **twice**: once in the `verify` state (advisory `verify_verdict`) and again
in `merge_epic_branch`'s pre-merge gate (`verify_before_merge: true`). For this
project that is ~15k tests run twice per epic finalize — wasted wall-clock — and,
worse, the two runs can **disagree** (different timing, flakiness, or divergent
environment), so the advisory verdict and the binding gate verdict need not
match. There is no reason to pay for and reconcile two independent runs of the
same commands against the same branch tip.

## Current Behavior

`scripts/little_loops/loops/auto-refine-and-implement.yaml`:
- `verify` state (~line 348) calls `verify_epic_branch_before_merge(...,
  verify_before_merge=True)` unconditionally and writes `verify-verdict.txt`.
- `merge_epic_branch` (~line 527) calls the same function again, gated by
  `epic_cfg.verify_before_merge`, and emits `verify_failed` on failure.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — the `verify` state
  (lines 348–416) and `merge_epic_branch` state (lines 428–559). Both inline
  `python3` heredocs. `verify` currently writes only the verdict
  (`echo "$VERIFY_VERDICT" > "$RUN_DIR/verify-verdict.txt"`, line 412); it must
  also persist the epic branch tip SHA. `merge_epic_branch` (line 527) calls
  `verify_epic_branch_before_merge(...)` a second time and must instead read the
  persisted verdict+SHA and skip the re-run when fresh.

### Do NOT Modify (out of scope)
- `scripts/little_loops/worktree_utils.py:245` `verify_epic_branch_before_merge()`
  — the shared, stateless verify function. Both loop states and the orchestrator
  call it. Changing its signature would ripple to the `ll-parallel` path
  (`orchestrator.py:1336`). Keep the reuse/freshness logic in the loop YAML, not
  the function.
- `scripts/little_loops/parallel/orchestrator.py:1323`
  `_verify_epic_branch_before_merge()` — the `WorkerPool`/`ll-parallel` path.
  It fires `_maybe_complete_epic` possibly multiple times and is a *different*
  execution model (no `run_dir`/verdict-file); the double-run described here is
  specific to the FSM loop's two-state path, so this issue does not touch it.

### Callers of `verify_epic_branch_before_merge`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:396` — `verify` state
  (`verify_before_merge=True`, unconditional).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:527` — `merge_epic_branch`
  state (`verify_before_merge=epic_cfg.verify_before_merge`, the redundant run).
- `scripts/little_loops/parallel/orchestrator.py:1336` — orchestrator path (unaffected).

### State transition
- `verify` (`next: merge_epic_branch`, `on_error: merge_epic_branch`, line 415–416)
  → `merge_epic_branch`. The two states run back-to-back in the same loop
  execution against the same epic branch tip, so between them **no new commits
  land on the branch** — the SHA freshness check will normally match, making
  Option 1 (reuse) reliable rather than a rare optimization.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestMergeEpicBranchState` (harness
  `_run()` at ~line 2810; cases `test_merges_when_all_children_done`,
  `test_held_open_when_child_not_done`, `test_skipped_when_merge_to_base_on_complete_false`,
  `test_skipped_when_no_epic_branch_file`, `test_idempotent_when_branch_already_merged`
  at lines 2861–2918). This harness extracts and `bash -c`-runs the
  `merge_epic_branch` action in isolation — the natural home for a new
  "reuses fresh verdict, skips re-run" test and a "re-runs on stale/missing SHA"
  test. Verify-state behavior is asserted at lines 2112–2129
  (`verify_before_merge=True` presence checks).

### Configuration
- `.ll/ll-config.json` → `parallel.epic_branches.verify_before_merge` (currently
  `true`, set by commit `1ccd4da8`). Parsed via `BRConfig(...).parallel.epic_branches`
  (`epic_cfg.verify_before_merge`, YAML line 481, 530). The `verify_before_merge: false`
  path must still short-circuit correctly (the function early-returns `(True, None)`
  at `worktree_utils.py:285`).

## Proposed Change

Make the `verify` state authoritative and have `merge_epic_branch` **reuse** its
`verify-verdict.txt` when it is fresh for the same branch tip, instead of
re-running the suite. Options:

1. `merge_epic_branch` reads `verify-verdict.txt`; if it is `passed` (and, if we
   want a freshness guard, the recorded branch SHA matches the current tip),
   skip the re-run and proceed to merge. Only re-run when the verdict is missing
   or stale.
2. Or: drop the redundant gate call entirely and route `merge_epic_branch` off
   the `verify` state's verdict — i.e. `verify` gates the transition into
   `merge_epic_branch`.

Prefer whichever keeps a single source of truth for the epic's pre-merge
correctness signal. Pairs with BUG-2629 (fix the verify command once, in one
place).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The two numbered options above map to two concrete implementations:

**Option A** (reuse-with-freshness — issue option 1): Keep both states. In the
`verify` state, after computing `$VERIFY_VERDICT`, also record the epic branch
tip: `git rev-parse --verify "$EPIC_BRANCH" > "$RUN_DIR/verify-sha.txt"` (this is
the established resolve-a-branch-tip idiom already used at
`worktree_utils.py:113`). In `merge_epic_branch`, before calling
`verify_epic_branch_before_merge(...)` at YAML line 527, read
`verify-verdict.txt` + `verify-sha.txt`; if the verdict is `passed` **and** the
recorded SHA equals the current `git rev-parse --verify <epic_branch>`, skip the
re-run and proceed straight to the merge/PR block (lines 543–557). Only re-run on
a missing verdict, a non-`passed` verdict, or a SHA mismatch. Lowest-risk:
preserves the existing gate as a fallback, so a disagreement still cannot merge a
failing tip.

**Option B** (route off verify's verdict — issue option 2): Drop the
`verify_epic_branch_before_merge` call inside `merge_epic_branch` entirely and
make the `verify` state gate the transition — e.g. route `verify` to `finalize`
(bypassing merge) when its verdict is `failed`, and only into `merge_epic_branch`
when `passed`. Simpler single-source-of-truth, but `merge_epic_branch`'s current
`next`/`on_error` both point at it unconditionally (line 415–416), so this
requires restructuring the routing and re-checking the `verify_before_merge:
false` and non-epic paths, which currently rely on the gate being a no-op inside
merge.

**Recommended**: Option A for v1 — it is additive (no routing surgery), keeps the
binding gate as a safety net, and the back-to-back state execution means the SHA
almost always matches so the re-run is genuinely eliminated in the common case.
The `verify_before_merge: false` path is unaffected because the function already
early-returns at `worktree_utils.py:285`.

> Note: the `verify` state's SHA capture must guard the non-epic case — when
> `epic-branch-name.txt` is absent it runs checks in-place (YAML lines 371–383)
> and there is no epic branch to `rev-parse`; write the SHA only on the
> epic-branch code path.

## Implementation Steps

1. Persist the branch tip SHA alongside the verdict in the `verify` state (e.g.
   `verify-verdict.txt` + `verify-sha.txt`) for a freshness check.
2. In `merge_epic_branch`, gate on the persisted verdict/SHA; re-run only on
   miss/stale.
3. Ensure the non-epic path and `verify_before_merge: false` config still behave
   correctly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete step mapping (assumes Option A):_

1. In `scripts/little_loops/loops/auto-refine-and-implement.yaml` `verify` state,
   on the epic-branch code path only (inside `if epic_branch:`, after line 388 /
   before the final `print`), capture the tip and write it next to the verdict:
   `git rev-parse --verify "$EPIC_BRANCH"` → `$RUN_DIR/verify-sha.txt`. Do **not**
   write it on the non-epic in-place path (lines 371–383). Keep the existing
   `echo "$VERIFY_VERDICT" > "$RUN_DIR/verify-verdict.txt"` (line 412).
2. In the `merge_epic_branch` state heredoc, after resolving `epic_branch` and
   confirming it still exists (lines 468–476) but before the
   `verify_epic_branch_before_merge(...)` call (line 527), read
   `run_dir/'verify-verdict.txt'` and `run_dir/'verify-sha.txt'`; compute
   `current = subprocess.run(["git","rev-parse","--verify",epic_branch],...)`.
   If verdict == `passed` and recorded SHA == current SHA, set `ok, message =
   True, None` and skip the call; otherwise fall through to the existing gate.
   Preserve the `verify_failed` emission (lines 538–541) for the re-run branch.
3. Gate step 2 on `epic_cfg.verify_before_merge` so `false` still skips (the
   function's `worktree_utils.py:285` early-return already covers the direct-call
   fallback).
4. Add tests in `scripts/tests/test_builtin_loops.py` `TestMergeEpicBranchState`:
   one where a fresh `verify-verdict.txt=passed` + matching `verify-sha.txt`
   causes `merged` **without** invoking the verify worktree (assert re-run
   skipped — e.g. no `verify-<epic>-*` scratch worktree created), and one where a
   stale/missing SHA forces the re-run. Extend the `_run()` harness (~line 2810)
   to seed the two verdict files.
5. Verify: `python -m pytest scripts/tests/test_builtin_loops.py -k MergeEpicBranch -v`
   and `ll-loop validate loops/auto-refine-and-implement` (YAML shell-escape rules).

## Acceptance Criteria

- A completed EPIC finalize runs the full suite at most once when the verify
  verdict is fresh for the current branch tip.
- The merge decision and the reported `verify_verdict` cannot disagree for the
  same tip.

## Session Log
- `/ll:refine-issue` - 2026-07-13T18:55:38 - `e555b243-e23c-429d-9cab-61c70b69018b.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:30:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
