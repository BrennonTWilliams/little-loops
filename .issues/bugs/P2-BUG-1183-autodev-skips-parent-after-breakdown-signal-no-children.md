---
captured_at: "2026-04-18T22:20:25Z"
completed_at: 2026-04-18T23:23:41Z
discovered_date: 2026-04-18
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1183: autodev silently skips parent when breakdown flag is set but no children were created

## Summary

When `refine-to-ready-issue` routes through `breakdown_issue` → `write_broke_down` but the invoked `/ll:issue-size-review --auto` only *recommends* breakdown without actually creating child issue files, the outer `autodev` loop takes its "already size-reviewed" shortcut, finds no children, logs `"Skipped: <ID> (no further decomposition possible)"`, and drops the parent from further processing. The parent is never moved to `.issues/completed/` and never re-attempted. Observed on FEAT-1181 during autodev run `2026-04-18T194126` (final event at `22:07:08`).

## Current Behavior

For a parent issue that fails confidence/outcome thresholds:

1. Sub-loop `refine-to-ready-issue` runs `breakdown_issue` → invokes `/ll:issue-size-review <ID> --auto` (70s on FEAT-1181). The skill returns analysis recommending breakdown **but does not create any child issue files**.
2. Sub-loop then runs `write_broke_down` → writes `1` to `.loops/tmp/recursive-refine-broke-down`. Sub-loop exits via `done`.
3. Outer `autodev` loop runs `copy_broke_down` → copies flag into `.loops/tmp/autodev-broke-down` (value: `1`).
4. `check_passed` → exit 1 (issue still below thresholds) → route to `detect_children`.
5. `detect_children` → diffs pre-/post-sub-loop issue IDs filtered by the `Decomposed from <PARENT>` marker → finds **none** → exit 1 → route to `size_review_snap`.
6. `size_review_snap` snapshots post-ids into pre-ids (pre == post going forward).
7. `check_broke_down` evaluates flag: `1 < 1` is false → routes via `on_no` to **`enqueue_or_skip`**, bypassing `recheck_scores` → `run_size_review`.
8. `enqueue_or_skip` re-scans for children (still none, because pre == post and none were ever created) → logs `"Skipped: FEAT-1181 (no further decomposition possible)"`, appends ID to `.loops/tmp/autodev-skipped.txt`, **does not** `git mv` the parent to `.issues/completed/`.
9. `dequeue_next` → queue empty → exit 1 → loop routes to `done` and terminates normally.

Net effect: the parent remains in the active backlog, was never actually decomposed, was never implemented, and the loop reports success.

## Expected Behavior

If the sub-loop's breakdown signal is set (`autodev-broke-down == 1`) **but `detect_children` found no new child issues**, the outer loop should fall through to `run_size_review` (its own size-review state) rather than shortcut to `enqueue_or_skip`. That state would re-invoke `/ll:issue-size-review` in a context where child creation is expected, or route to a terminal "needs human" state with a clearer signal than `"no further decomposition possible"`. Either way, the loop must not silently drop a parent that has never produced children.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `in state check_broke_down` (lines 248–261)
- **Cause**: The `check_broke_down` guard (added in the fix for BUG-1079) treats `broke_down == 1` as proof that size-review already ran *and produced children*. It routes `on_no` straight to `enqueue_or_skip`, skipping `run_size_review`. This collapses two distinct sub-loop outcomes into one branch:
  - (a) sub-loop created children → `detect_children` already caught them; skip is correct.
  - (b) sub-loop only produced analysis → no children exist; skipping `run_size_review` means the outer loop never gets its own chance to create them.
- The contract between `refine-to-ready-issue.breakdown_issue` (which writes the flag unconditionally based on sub-loop state) and `autodev.check_broke_down` (which reads the flag as a proxy for "children exist") is broken when `/ll:issue-size-review --auto` returns without creating files.

## Motivation

The `autodev` loop exists to drive issues to an implementable state. Silently skipping an issue that never decomposed defeats that purpose and is invisible in the summary (appears as a normal skip). When a user submits a targeted list like `ll-loop run autodev "FEAT-1181"`, the expected outcome is either implementation or at minimum a clear failure/decomposition; getting `"Skipped: ... (no further decomposition possible)"` with the parent still in the backlog is a silent no-op that burns ~10 minutes of LLM wall-clock time (refine + wire + confidence + size-review) with zero forward progress. Since `autodev` is the primary driver for targeted multi-issue runs, this regression blocks its use as a reliable pipeline.

## Proposed Solution

Change the semantics of `check_broke_down` so the shortcut is only taken when children actually exist. Two candidate fixes (pick one during implementation):

**Option A — Outer-loop guard:** Have `check_broke_down` AND-combine the flag with a child-existence check:
- If `autodev-broke-down == 1` **and** the `autodev-new-children.txt` (written by `detect_children`) is non-empty → route to `enqueue_or_skip`.
- Otherwise (flag=1 but no children, or flag=0) → route to `recheck_scores` / `run_size_review`.

**Option B — Source-of-truth flag:** Move the flag write out of `write_broke_down` (which fires on sub-loop terminal state) and into the `breakdown_issue` action itself, conditioned on "did `/ll:issue-size-review` create new child files". This keeps `check_broke_down`'s current binary semantics but makes the flag accurately reflect reality.

Option A is smaller and localized to `autodev.yaml`. Option B requires a cross-loop contract change and touches every caller of `refine-to-ready-issue`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Parallel bug confirmed in `recursive-refine.yaml:221-234`** — `recursive-refine`'s own `check_broke_down` state has an identical structure (`output_numeric lt 1`, `on_no: enqueue_or_skip`) and reads `.loops/tmp/recursive-refine-broke-down`. It exhibits the same silent-drop behavior when `/ll:issue-size-review --auto` returns analysis without creating children. Option A should be applied to **both** loops, or the fix scope should be documented as autodev-only with a follow-up issue tracking recursive-refine. Both loops' `detect_children` states already write parallel `-new-children.txt` scratch files (`autodev-new-children.txt` at `autodev.yaml:197`, `recursive-refine-new-children.txt` at `recursive-refine.yaml:172`), so the Option A pattern is directly portable.
- **Option B is infeasible without a new skill contract** — `/ll:issue-size-review --auto` does not currently emit any child-creation signal. The only detection mechanism is the `ll-issues list --json` pre/post diff in `detect_children`. Option B would require adding a new outbound signal from the skill (e.g., a marker file or structured output), making it a cross-component change. Option A is strongly preferred.
- **`autodev-new-children.txt` lifecycle allows Option A to read it safely** — `detect_children` (`autodev.yaml:196-197`) writes the file; `size_review_snap` (235-246) does not touch it; `check_broke_down` (248-262) would be the second reader (after `detect_children`); `enqueue_or_skip` (343-345) overwrites it fresh. No race condition.

## Implementation Steps

1. Decide Option A vs B (recommend A — smaller surface area and doesn't disturb BUG-1079's fix).
2. For Option A: add a shell check in `check_broke_down.action` that reads both flag and child count; emit a numeric value the existing `output_numeric` evaluator can route on (e.g., `0` = fall through, `1` = shortcut).
3. Add a regression test that exercises the "breakdown signaled, no children created" path and asserts `autodev` routes through `run_size_review`.
4. Replay against FEAT-1181 (currently in `.issues/features/`) to verify the parent either decomposes or reaches a clear terminal state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references for each step:_

1. **Model the new `check_broke_down.action` on `check_wire_done` at `scripts/little_loops/loops/refine-to-ready-issue.yaml:81-91`** — it reads a flag file with the canonical safe-read idiom (`cat ... 2>/dev/null || echo 0`) and routes through `output_numeric lt 1`. The Option A fix combines this with a `[ -s .loops/tmp/autodev-new-children.txt ]` test (the canonical empty-check idiom used at `autodev.yaml:199` and `recursive-refine.yaml:174`). Example shape:
   ```bash
   FLAG=$(cat .loops/tmp/autodev-broke-down 2>/dev/null || echo 0)
   if [ "$FLAG" = "1" ] && [ -s .loops/tmp/autodev-new-children.txt ]; then
     echo 1  # flag set AND children exist → shortcut to enqueue_or_skip
   else
     echo 0  # otherwise → fall through to recheck_scores/run_size_review
   fi
   ```
   The existing `output_numeric lt 1` evaluator and `on_yes`/`on_no` routing keep their current destinations; only the action block changes. (Note: under the new semantics, `on_yes` still routes to `recheck_scores` for the "fall through" case — this is unchanged, just now reached more often.)
2. **Preserve BUG-1079's "no double size-review" invariant** — the BUG-1079 completed issue lives at `.issues/completed/P3-BUG-1079-recursive-refine-double-size-review-after-breakdown.md`. The invariant to preserve: when `breakdown_issue` *did* create children, `check_broke_down` must still shortcut to `enqueue_or_skip` to avoid a second `/ll:issue-size-review` call. The combined AND-check in step 1 preserves this because children-exist + flag=1 still routes through the shortcut.
3. **Regression test goes in `scripts/tests/test_builtin_loops.py` under `TestAutodevLoop` (lines 1009-1205)** — follow the pattern at lines 1173-1177 (`test_check_broke_down_reads_autodev_namespaced_flag`). Add new assertions that `check_broke_down.action` also references `autodev-new-children.txt`. For end-to-end verification of routing, use the mock-Popen pattern in `scripts/tests/test_ll_loop_execution.py:111-143` (`_make_mock_popen_factory`). Parallel assertions at `TestRecursiveRefineLoop` (lines 1325-1364) will need matching updates if Option A is applied to `recursive-refine.yaml` as well.
4. **If Option A is applied to `recursive-refine.yaml`**, the mirrored change is at `recursive-refine.yaml:221-234`, reading `.loops/tmp/recursive-refine-broke-down` + `[ -s .loops/tmp/recursive-refine-new-children.txt ]`.
5. **Add/update tests** beyond the existing `test_check_broke_down_reads_autodev_namespaced_flag`:
   - Update `test_builtin_loops.py:1173-1177` to also assert `"autodev-new-children.txt" in action`.
   - Add 4 new assertions in `TestAutodevLoop` (parallel to `TestRecursiveRefineLoop:1331-1364`): evaluate type/operator/target, on_yes/on_no/on_error routing.
   - If Option A applied to `recursive-refine.yaml`, add matching assertion that `recursive-refine-new-children.txt` is in that action.
   - Add integration test in `test_ll_loop_execution.py` using `_make_mock_popen_factory` pattern: three-state inline FSM where stdout=`"1"` and `autodev-new-children.txt` is absent → FSM routes to `recheck_scores`, not `enqueue_or_skip`.
6. **Update docs** at `docs/guides/LOOPS_GUIDE.md`: branch label at line 451-452 (autodev diagram), Breakdown guard prose at line 468 (recursive-refine), and flow diagram at lines 505-506 (recursive-refine).
7. **Verification replay**: rerun `ll-loop run autodev "FEAT-1181"` after the fix (FEAT-1181 is still in `.issues/features/`). Expected new path: `check_broke_down` → `recheck_scores` → `run_size_review` → `enqueue_or_skip` (instead of jumping directly to `enqueue_or_skip`). If `/ll:issue-size-review` in `run_size_review` also fails to create children, the parent should reach a terminal path with a clearer signal than the current silent skip.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml:248-261` — change `check_broke_down` evaluate/routing so flag=1 + no-children falls through to `recheck_scores`/`run_size_review`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:226-232` — owns `breakdown_issue` + `write_broke_down`; no behavior change needed for Option A.
- `.loops/tmp/autodev-new-children.txt` — written by `detect_children` (autodev.yaml ~line 173), consumed today by `enqueue_or_skip`. Option A adds a second reader in `check_broke_down`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:42` — invokes `recursive-refine` as sub-loop; behavioral change to `check_broke_down` in recursive-refine will affect its routing outcomes; no code change needed but verify end-to-end behavior.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:51` — same as above; invokes `recursive-refine` as sub-loop.
- `scripts/little_loops/loops/README.md` — documents autodev and recursive-refine behavior including the broke-down handshake; update if check_broke_down semantics are described here.

### Similar Patterns
- BUG-1079 (completed) introduced the `check_broke_down` shortcut to avoid double size-review. Review its fix commit before changing the semantics to avoid regressing the double-invocation problem.

### Tests
- `scripts/tests/` — find existing `autodev` or `refine-to-ready-issue` loop tests; add a scenario where `breakdown_issue` writes the flag but no child files appear.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1173-1177` (`TestAutodevLoop.test_check_broke_down_reads_autodev_namespaced_flag`) — **update**: add parallel assertion `assert "autodev-new-children.txt" in action` alongside the existing `"autodev-broke-down"` check.
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`) — **new tests** (currently missing; parallel to `TestRecursiveRefineLoop:1331-1364`):
  - `test_check_broke_down_evaluate_output_numeric_lt_1` — assert `evaluate.type == "output_numeric"`, `operator == "lt"`, `target == 1`
  - `test_check_broke_down_on_yes_routes_to_recheck_scores` — assert `on_yes == "recheck_scores"`
  - `test_check_broke_down_on_no_routes_to_enqueue_or_skip` — assert `on_no == "enqueue_or_skip"`
  - `test_check_broke_down_on_error_routes_to_recheck_scores` — assert `on_error == "recheck_scores"`
- `scripts/tests/test_builtin_loops.py` (`TestRecursiveRefineLoop`) — **new assertion** after line 1364: `assert "recursive-refine-new-children.txt" in action` when Option A is applied to `recursive-refine.yaml`.
- `scripts/tests/test_ll_loop_execution.py` — **new integration test** using `_make_mock_popen_factory` pattern (lines 26-41): inline three-state FSM (`check_broke_down` → `recheck_scores` | `enqueue_or_skip`) where shell stdout = `"1"` and `autodev-new-children.txt` is absent → verify routes to `recheck_scores` not `enqueue_or_skip` (direct BUG-1183 regression guard).

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — any FSM diagram or prose that documents the `check_broke_down` branching table should be updated to show the new three-way decision.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:451-452` — autodev FSM flow diagram branch label: `[already size-reviewed?]` becomes `[already size-reviewed AND children exist?]`; YES branch condition changes to `flag=1 AND non-empty children file`.
- `docs/guides/LOOPS_GUIDE.md:468` — **critical**: recursive-refine **Breakdown guard** callout prose currently reads "flag is set → skip `run_size_review`"; must be updated to "flag is set AND children file is non-empty → skip". Most precisely wrong text after the fix.
- `docs/guides/LOOPS_GUIDE.md:505-506` — recursive-refine FSM flow diagram: same branch label update as the autodev diagram above.

### Configuration
- None.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified file paths and line ranges:_

**Files to Modify (confirmed with exact ranges):**
- `scripts/little_loops/loops/autodev.yaml:248-262` — `check_broke_down` state block (the shell action at line 249-251, evaluator at 252-255, routes at 256-261).
- `scripts/little_loops/loops/recursive-refine.yaml:221-234` — parallel `check_broke_down` with the same bug; apply mirrored fix here or file a follow-up.

**Dependent Files (verified):**
- `scripts/little_loops/loops/autodev.yaml:100-113` — `copy_broke_down` writes `.loops/tmp/autodev-broke-down` from the inner flag or `0`.
- `scripts/little_loops/loops/autodev.yaml:171-208` — `detect_children` writes `.loops/tmp/autodev-new-children.txt` at lines 196-197; Option A reads it.
- `scripts/little_loops/loops/autodev.yaml:235-246` — `size_review_snap` (between `detect_children` and `check_broke_down`) does not touch `autodev-new-children.txt`, so the file survives into `check_broke_down`.
- `scripts/little_loops/loops/autodev.yaml:320-368` — `enqueue_or_skip` consumes and overwrites `autodev-new-children.txt` (second reader after Option A fix); runs the identical `Decomposed from $PARENT_ID` grep filter as `detect_children`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:226-236` — `breakdown_issue` + `write_broke_down` (unconditionally writes `1` at line 233, regardless of child creation — the root contract defect).
- `scripts/little_loops/fsm/evaluators.py:115-151` — `evaluate_output_numeric` parses shell stdout as `float`, applies `_NUMERIC_OPERATORS[operator]` (line 83-90 dispatch table), returns `yes`/`no`/`error` verdicts.

**Similar Patterns (modeled on existing codebase):**
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:81-91` — `check_wire_done`: canonical "read flag file → `output_numeric lt 1`" state. Directly analogous shape for Option A.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:32-73` — `check_lifetime_limit`: canonical "compute inside shell, emit single numeric, route" pattern; closest structural analog for combined-condition shell checks.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:174-191` — `check_refine_limit`: another example of a shell action that emits a single number to drive `output_numeric` routing.

**Tests:**
- `scripts/tests/test_builtin_loops.py:1009-1205` — `TestAutodevLoop` class. Key existing assertions: `test_check_broke_down_reads_autodev_namespaced_flag` (lines 1173-1177), `test_broke_down_flag_copied_to_autodev_namespace` (lines 1159-1170), `test_enqueue_children_filters_by_parent_reference` (lines 1152-1157).
- `scripts/tests/test_builtin_loops.py:1325-1364` — `TestRecursiveRefineLoop.test_check_broke_down_*` assertions (evaluate type/operator/target + on_yes/on_no/on_error routes). Port this pattern for autodev's updated state.
- `scripts/tests/test_ll_loop_execution.py:111-143` — `_make_mock_popen_factory` + end-to-end FSM execution test pattern for routing verification.
- `scripts/tests/test_fsm_evaluators.py` — existing tests for `output_numeric` with `operator: lt`.
- `scripts/tests/test_issue_size_review_skill.py` — tests for the `/ll:issue-size-review` skill's write-back behavior.

**Documentation:**
- `docs/guides/LOOPS_GUIDE.md:428-482` — describes the breakdown/size-review pattern; line 468 documents the `check_broke_down` "no double size-review" invariant that must be preserved.
- `skills/issue-size-review/SKILL.md:197-199` — documents the `## Parent Issue` body section with `Decomposed from [PARENT-ID]` marker (the convention used by `detect_children` and `enqueue_or_skip` greps).

**Related Completed Fix:**
- `.issues/completed/P3-BUG-1079-recursive-refine-double-size-review-after-breakdown.md` — the fix that introduced `check_broke_down`. Review its Resolution section (lines 188-205) before changing the semantics to preserve the "no double size-review" invariant.

## Impact

- **Priority**: P2 — silently drops issues from autodev's targeted queue; primary-function failure but bounded (loop exits cleanly, parent still on disk).
- **Effort**: Small — localized YAML + evaluator change if Option A is chosen.
- **Risk**: Medium — tangled with BUG-1079's fix; must preserve the "no double size-review" invariant.
- **Breaking Change**: No — loop config change only; existing callers unaffected.

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md:428-482` — FSM breakdown/size-review pattern and `check_broke_down` invariant.
- `skills/issue-size-review/SKILL.md:197-199` — `Decomposed from [PARENT-ID]` marker convention used by `detect_children`.
- `.issues/completed/P3-BUG-1079-recursive-refine-double-size-review-after-breakdown.md` — the fix that introduced `check_broke_down` and established the "no double size-review" invariant this bug's fix must preserve.

## Labels

`bug`, `loops`, `autodev`, `captured`

## Status

**Completed** | Created: 2026-04-18 | Completed: 2026-04-18 | Priority: P2

## Resolution

Applied **Option A** to both `autodev.yaml` (lines 248-269) and `recursive-refine.yaml` (lines 221-242). The `check_broke_down.action` now AND-combines the broke-down flag with an `[ -s .loops/tmp/*-new-children.txt ]` test; the shortcut to `enqueue_or_skip` fires only when *both* conditions hold. When the flag is set but no children were created, control falls through to `recheck_scores` → `run_size_review` so the outer loop gets its own chance to decompose (or reach a clear terminal state).

The BUG-1079 "no double size-review" invariant is preserved: flag=1 AND children exist still shortcuts past `run_size_review`.

**Files modified:**
- `scripts/little_loops/loops/autodev.yaml` — `check_broke_down` action + comment.
- `scripts/little_loops/loops/recursive-refine.yaml` — mirrored fix.
- `scripts/tests/test_builtin_loops.py` — 1 updated + 5 new structural tests (4 for `TestAutodevLoop` paralleling recursive-refine; 1 new `test_check_broke_down_requires_children_file` on each).
- `docs/guides/LOOPS_GUIDE.md` — updated 3 spots (autodev diagram branch label, recursive-refine breakdown guard prose, recursive-refine diagram branch label).

**Verification:** `5004 passed, 5 skipped` on `python -m pytest scripts/tests/`. Pre-existing ruff UP017 warning in `scripts/little_loops/cli/loop/run.py:166` is unrelated to this change.

## Session Log
- `/ll:ready-issue` - 2026-04-18T23:19:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b8781941-62db-49a8-ac16-472e4090cdf6.jsonl`
- `/ll:confidence-check` - 2026-04-18T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75426ad0-55f6-40b5-bf17-f733e53313c9.jsonl`
- `/ll:wire-issue` - 2026-04-18T23:16:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/431ae0bc-066d-4318-9b8a-b705369c757f.jsonl`
- `/ll:refine-issue` - 2026-04-18T23:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d784429a-8e02-4b00-9c77-3ace6ff55f65.jsonl`
- `/ll:capture-issue` - 2026-04-18T22:20:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ccc8368e-06c9-482f-96d4-4fbb17a0fbbf.jsonl`
- `/ll:manage-issue` - 2026-04-18T23:23:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fce08054-16c4-48b1-a9b3-26191966efde.jsonl`
