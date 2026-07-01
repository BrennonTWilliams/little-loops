---
captured_at: '2026-07-01T00:04:14Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: open
priority: P2
type: BUG
relates_to:
- BUG-2408
- BUG-280
- BUG-1538
---

# BUG-2409: ll-auto Phase 3 "plan awaiting approval" short-circuits before checking for uncommitted work

## Summary

`ll-auto` Phase 3 treats *any* plan file matching the issue ID as proof the run
is "awaiting approval" and parks the issue as incomplete — **before** the
git-diff evidence check runs. When the agent has already cleared the confidence
gate and proceeded past planning into implementation, but left changes
uncommitted in the working tree, Phase 3 still sees the stale plan file and
mislabels a completed-but-unfinalized implementation as "plan awaiting
approval." The result: real, validated changes are silently parked and the run
reports "Issues processed: 0."

Observed in `ll-auto --only ENH-2406` (2026-06-30): Phase 3 logged
`Plan created at thoughts/shared/plans/2026-06-30-ENH-2406-management.md,
awaiting approval` and left the issue `open`, despite uncommitted ENH-2406
changes sitting in the working tree.

## Current Behavior

In `process_issue_inplace` Phase 3 (`issue_manager.py:1000-1024`):

1. `verify_issue_completed()` returns False (status still `open`, no commit).
2. `result.returncode == 0` (headless turn ended cleanly).
3. `detect_plan_creation(result.stdout, issue_id)` (`issue_manager.py:489`,
   called at `:1010`) globs `thoughts/shared/plans/*-<ID>-*.md` and returns the
   latest match **purely on file existence** — it ignores stdout and does not
   check whether the plan was superseded by later implementation work.
4. Because a plan file exists, the function returns early with
   `plan_created=True` / `failure_reason=""` and **skips** the "check for
   evidence of work" git-diff path at `:1026+`.
5. The issue is parked as "awaiting approval" even though uncommitted changes
   (diffable against the `_baseline_sha` captured at `:883-888`) prove the agent
   proceeded well past the plan.

## Expected Behavior

The "plan awaiting approval" short-circuit should only fire when the run
genuinely stopped at planning. If uncommitted implementation changes exist
relative to the Phase-2 baseline, Phase 3 should recognize
**completed-but-unfinalized work** and surface it prominently (and/or run the
existing finalization fallback) rather than silently parking the issue.

## Root Cause

`detect_plan_creation` is a pure filesystem existence check with no recency or
work-evidence gate. A plan file legitimately created earlier in the *same* turn
(before the agent implemented) is indistinguishable, to this function, from a
run that halted at plan approval. Its early-return at `:1011-1024` takes
precedence over the git-diff evidence check, so the presence of a plan masks the
presence of real work.

## Integration Map

- `scripts/little_loops/issue_manager.py:489-516` — `detect_plan_creation`
  (existence-only glob).
- `scripts/little_loops/issue_manager.py:1008-1024` — Phase 3 short-circuit that
  returns before the evidence check.
- `scripts/little_loops/issue_manager.py:1026+` — the git-diff "evidence of work"
  fallback that is currently skipped.
- `scripts/little_loops/issue_manager.py:883-888` — `_baseline_sha` captured at
  Phase 2 start; available to diff against.
- `scripts/little_loops/issue_lifecycle.py:440` — `status=… (expected
  done/cancelled)` warning emitted just before this path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — codebase analysis; all 5 line refs above verified
accurate (no drift):_

- **Enclosing function**: the Phase-3 block lives in `process_issue_inplace()`
  (`issue_manager.py:560`), not `_process_single_issue`.
  `AutoManager._process_issue()` (`issue_manager.py:1371`) is a thin wrapper that
  delegates to it and consumes `result.plan_created` / `result.plan_path`.
- **Reusable gate — no new plumbing**: `verify_work_was_done(logger,
  baseline_sha=_baseline_sha)` (`work_verification.py:44-161`) already detects all
  three "uncommitted work vs baseline" cases the fix needs — unstaged
  (`git diff --name-only`), staged (`git diff --cached --name-only`), and
  committed-since-baseline (`git diff --name-only <baseline>..HEAD`). `_baseline_sha`
  is already in scope at the short-circuit site (`:1011`), so the fix only needs to
  call this helper before the `plan_path is not None` early-return and fall through
  when it returns `True`.
- **Plan file self-exclusion**: `EXCLUDED_DIRECTORIES` (`work_verification.py:18-25`)
  excludes `thoughts/` (also `.issues/`, `.speckit/`, `.worktrees/`, `.auto-manage`),
  so the plan file under `thoughts/shared/plans/` is *not* counted as work by
  `verify_work_was_done` — gating on this helper cannot false-positive on the plan
  itself.
- **`detect_plan_creation` ignores stdout**: its `output` param
  (`issue_manager.py:488-516`) is documented "unused, for future pattern matching"
  and never read; `st_mtime` is only used to pick among multiple matches, never to
  gate recency. Confirms the pure-existence root cause.
- **Content-marker ladder runs first on the no-plan path**:
  `check_content_markers(info.path)` (`issue_manager.py:519-542`, called at `:1032`)
  is tried before `verify_work_was_done` at `:1043`. The new gate should sit at the
  plan branch (`:1011`); the fall-through then reuses this existing
  content-marker → work-evidence ladder unchanged.
- **Git subprocess convention**: use bare
  `subprocess.run(["git", ...], capture_output=True, text=True)` (as at `:883-888`),
  **not** `worker_pool.py`'s `_git_lock.run(...)` — documented in BUG-1538.

## Steps to Reproduce

1. Take an issue whose plan clears the confidence gate (≥ threshold) so the agent
   proceeds into implementation in the same turn.
2. Arrange for the turn to end after edits but before commit + status update
   (e.g. the BUG-2408 background-wait stall).
3. Run `ll-auto --only <ID>`.
4. Observe Phase 3 log "Plan created … awaiting approval" and park the issue,
   even though `git status` shows uncommitted implementation changes.

## Proposed Solution

Gate the plan-awaiting-approval short-circuit on the **absence** of uncommitted
work relative to the Phase-2 baseline:

- Before returning the `plan_created=True` result, compare the working tree /
  index against `_baseline_sha` (reuse the existing `verify_work_was_done()` /
  `git diff` helpers). If changes exist, fall through to the evidence-of-work
  path instead of parking as "awaiting approval."
- Optionally, only treat the plan as "awaiting approval" when its mtime is newer
  than the most recent source edit (i.e. nothing happened after the plan).
- When completed-but-unfinalized work is detected, log it distinctly (e.g.
  "implementation completed but not committed/finalized") so it is not conflated
  with a genuine approval pause (BUG-280) or a false negative (BUG-1538).

## Tests to Add

- Phase-3 unit test: plan file present **and** uncommitted diff vs baseline →
  does *not* return `plan_created=True`; routes to the evidence-of-work path.
- Regression test preserving BUG-280 behavior: plan file present **and** clean
  tree (no diff vs baseline) → still returns "awaiting approval."

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test targets from codebase analysis:_

- **Coverage gap confirmed**: `test_issue_manager.py` has **zero** references to
  `plan_created` — no existing test drives the `plan_path is not None` branch. Both
  new tests are net-new coverage of that branch.
- **Home for the new tests**: `TestFallbackVerification`
  (`scripts/tests/test_issue_manager.py:2367-2619`), which already exercises the
  Phase-3 fallback via `process_issue_inplace`.
- **Exact template to model after**: `test_baseline_sha_passed_to_verify_work_was_done`
  (`test_issue_manager.py:2565-2618`). It patches `run_claude_command`,
  `run_with_continuation`, `verify_issue_completed=False`, `detect_plan_creation`,
  `check_content_markers=False`, `little_loops.issue_manager.subprocess.run`
  (for `git rev-parse HEAD`), and `verify_work_was_done`, then asserts on the result.
  For the two new tests, patch `detect_plan_creation` to return a real `Path`
  (plan present) and vary `verify_work_was_done` → `True` (dirty tree: assert the
  result does *not* have `plan_created is True` and routes to the evidence path) vs
  `False` (clean tree: assert `plan_created is True`, BUG-280 invariant preserved).
- **Fixtures**: reuse `mock_config` and `sample_issue` from `TestFallbackVerification`.
  Note `temp_project_dir` (`conftest.py:130`) is **not** a real git repo — git state
  is simulated by patching `subprocess.run`, not by real commits.
- **Sibling gate-test conventions**: `TestEarlyCompletionGuard`
  (`test_issue_manager.py:2621-2684`) and `TestDecisionNeededGate` (`:3462-3557`)
  show the file's "same setup, one flag flipped, assert on the branch taken" shape.
- **Low-level helper already covered**: `TestVerifyWorkWasDoneBaselineSha`
  (`scripts/tests/test_work_verification.py:428-509`) already tests baseline-diff
  detection itself; the new tests cover only the Phase-3 *gating*, not the helper.
- **Existing glob-helper tests**: `TestDetectPlanCreation`
  (`test_issue_manager.py:3286-3387`) covers `detect_plan_creation` in isolation.

## Acceptance Criteria

- With a plan file present but uncommitted changes vs the Phase-2 baseline,
  Phase 3 no longer parks the issue as "awaiting approval."
- The genuine plan-approval pause (clean tree, BUG-280) is unchanged.

## Impact

- **Priority**: P2 - Masks completed work as unprocessed and undermines
  run-summary reliability, but recoverable via re-run or manual commit (no data
  loss).
- **Effort**: Small - Reuses the existing `_baseline_sha` capture and the
  `git diff` / `verify_work_was_done()` helpers; gates a single early-return in
  Phase 3.
- **Risk**: Medium - Touches Phase-3 completion detection, which historically
  has subtle interactions with the genuine approval-pause path (BUG-280) and
  committed-work detection (BUG-1538); regression risk to the "clean tree =
  awaiting approval" case.
- **Breaking Change**: No

Masks BUG-2408 and any other end-of-turn stall: a fully implemented, validated
issue is reported as "0 processed" and left `open` with stranded uncommitted
changes, because a stale plan file outranks the actual work evidence. Undermines
the reliability of the run summary and risks a dirty-tree re-plan on re-run.

## Related Issues

- **BUG-2408** — the agent-side stall that produces the completed-but-uncommitted
  state this heuristic then mislabels.
- **BUG-280** (done) — original "false verification failure when plan awaiting
  approval" fix; this issue refines its detection to avoid over-firing.
- **BUG-1538** (done) — verification missed committed work + rejected a status
  synonym (adjacent Phase-3 correctness work).

## Out of Scope

- The agent-behavior fix in `skills/manage-issue/SKILL.md` (tracked in BUG-2408).
- Auto-committing on the agent's behalf from `ll-auto` (a policy decision beyond
  this detection fix).

## Labels

ll-auto, verification, phase-3, plan-detection, automation

## Session Log
- `/ll:refine-issue` - 2026-07-01T00:20:03 - `3fb8d5dc-1928-4342-8cac-be6c5066aa24.jsonl`
- `/ll:format-issue` - 2026-07-01T00:08:39 - `f960a02a-adbc-4f7d-b3c8-b867aa0ea338.jsonl`
- `/ll:capture-issue` - 2026-07-01T00:04:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50bef1ad-9ed2-44c2-9376-d53bca2305b4.jsonl`

---

## Status

**Current Status**: open
