---
id: BUG-2538
title: 'general-task.yaml: check_done/continue_work read current-step.txt deleted
  by mark_done'
type: BUG
priority: P2
status: done
captured_at: '2026-07-07T00:00:00Z'
completed_at: '2026-07-08T02:01:47Z'
discovered_date: '2026-07-07'
discovered_by: capture-issue
testable: true
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

## Summary

`general-task.yaml`'s `check_done` state is instructed (by ENH-2486) to read `${context.run_dir}/current-step.txt` as the bounded `LAST_STEP` marker — but `mark_done` deletes that exact file one transition earlier. On every normal step cycle (`select_step → do_work → verify_step → mark_done → check_done`), the worker in `check_done` finds the file missing and improvises by enumerating the run directory, producing diagnostic chatter like `The current-step.txt file doesn't exist. Let me check the run directory contents.` The same file is also referenced by `continue_work`'s timeout-split branch, which is reached via `check_done → count_done → continue_work` and is therefore also post-deletion.

The sibling marker file `last-files.txt` is **not** deleted by `mark_done`, so the `LAST_FILES` half of the marker pair (added by ENH-2486) is intact — only the `LAST_STEP` side is broken.

## Current Behavior

Every iteration after step 1, the worker driving `check_done` receives a prompt that references `current-step.txt` as `LAST_STEP`, opens it, and reports it does not exist. The worker then falls back to scanning the run directory and improvises context for delta-scoped verification. Output is noisy, prompts are larger than necessary (the worker re-derives step identity from the plan file), and the loop pays an extra turn of work per step. `continue_work`'s timeout-split path (`general-task.yaml:544`) has the same issue when reached after a `mark_done` cycle.

The loop still completes correctly because:

1. `last-files.txt` survives `mark_done` and is still readable.
2. `dod.md` and `plan.md` are independently verifiable from filesystem state.
3. `count_done` derives `BLOCKING_DOD` from the DoD file, not from the marker.

So the bug is **correctness-preserving but noisy, slow, and confusing** — the worker in `check_done` and `continue_work` is repeatedly told a file exists that has just been deleted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`check_done` is the primary (unconditional) breakage.** The path `mark_done → check_done` is non-branching (`mark_done` has `next: check_done` at line 282), and `check_done` instructs the worker to read `current-step.txt` for `LAST_STEP` at `general-task.yaml:295-296`. Deletion (line 279) always precedes this read, so `LAST_STEP` context is *always* gone in `check_done`.
- **`continue_work`'s exposure is secondary and conditional — the issue overstates it.** `continue_work`'s read of `current-step.txt` (`general-task.yaml:544`) lives **only in its exit-code-124 (timeout) split branch**. `continue_work` is entered from `verify_step` on_no (`262`), `count_done` on_no (`422`), `run_final_tests` on_no (`483`), and `count_final` on_no (`507`) — the read fires only when the prior captured exit code was `124`. On the `check_done → count_done → continue_work` path there was no timeout (the step completed and `mark_done` ran), so the timeout branch is not taken and the deleted marker is not read there. Net: fixing the deletion timing resolves both sites, but `continue_work` is not equally broken today.

## Expected Behavior

`check_done` and `continue_work` should be able to read `current-step.txt` and reliably find the step that was just executed. The marker's lifecycle should be: written by `select_step`, **persisted through** `mark_done` (or copied to a `last-step.txt` sidecar), read by `check_done` / `continue_work`, and only deleted by the next `select_step` (which unconditionally rewrites it). This mirrors the existing `last-files.txt` lifecycle, where `mark_done` deliberately does not delete it because downstream states still need it.

## Motivation

`general-task` is the project's general-purpose harness loop and is run frequently across many sessions (see `feedback_general_purpose_loop_decoupling` and `feedback_general_purpose_loop_decoupling` in MEMORY.md). Every noisy `check_done` turn costs worker tokens and dilutes the context of the actual delta verification. For long-running tasks with many steps, this compounds — a 20-step task currently wastes 19 `check_done` turns diagnosing a non-existent file instead of doing the verification work it was asked to do.

It also masks real failures: when `check_done` finds `current-step.txt` missing, the worker has to *infer* which step just ran. If the inference is wrong (e.g. a step whose `LAST_FILES` was a file later moved or renamed), the delta-scoped verification silently targets the wrong criterion. The current file-existence smoke gate in `verify_step` mitigates this but doesn't eliminate it for steps that modify files outside `LAST_FILES`.

ENH-2486 explicitly designed the bounded-marker pattern to *avoid* re-embedding large captured outputs (`general-task.yaml:289-293`); that goal is now undermined because the markers don't survive long enough to be read.

## Steps to Reproduce

1. Run `general-task` on any task with at least 2 plan steps (e.g. `ll-loop run general-task --input "..."`).
2. Inspect the captured output / run directory after the first step completes.
3. Observe the worker output for `check_done` (the state reached after `mark_done` on step 2+): the worker narrates `current-step.txt` is missing and proceeds to enumerate `${context.run_dir}` contents.
4. Same observation for `continue_work` when reached via `check_done → count_done → continue_work`.

## Root Cause

- **File**: `scripts/little_loops/loops/general-task.yaml`
- **Anchor**: `mark_done` action (lines 265-283) deletes `${context.run_dir}/current-step.txt` via `rm -f "$STEP_FILE"` at line 279. `check_done` action (lines 285-340) and `continue_work` action (lines 537-606) then read the same path.
- **Cause**: Lifecycle mismatch introduced by `b851b4ba` (ENH-2486, "feat(fsm): per-invocation prompt-size guard + bound general-task re-embeds", 2026-07-05). The ENH migrated `check_done` away from re-embedding `${captured.work_result.output}` / `${captured.selected_step.output}` (which grew with each do_work turn) toward reading bounded marker files (`current-step.txt` for `LAST_STEP`, `last-files.txt` for `LAST_FILES`). The author correctly identified that `last-files.txt` survives `mark_done` (because `mark_done` doesn't delete it) but did not notice that `current-step.txt` was already being deleted by `mark_done` — a pre-existing behavior from BUG-1766's `select_step ↔ mark_done` decoupling fix (`115c16f0`, 2025-08-14). The two fixes overlap destructively: BUG-1766 made `mark_done` clean up its own marker, ENH-2486 made `check_done` start reading the marker it cleaned up.

## Proposed Solution

Move the `rm -f "$STEP_FILE"` line out of `mark_done` and into `select_step`, where the file is unconditionally rewritten anyway (line 179). This restores the invariant that `current-step.txt` exists between `select_step`'s write and the next `select_step`'s overwrite, exactly the window in which `do_work`, `verify_step`, `mark_done`, `check_done`, and `continue_work` all expect to read it.

Concretely:

1. **In `mark_done`**: remove the `rm -f "$STEP_FILE"` line (line 279). Keep `rm -f "${context.run_dir}/checkpoint.json"` — that file is paired with `current-step.txt` only at the `select_step` write boundary, not downstream.
2. **In `select_step`** (`general-task.yaml:152-184`): after `echo "$STEP" > "${context.run_dir}/current-step.txt"` (line 179), the previous run's marker is overwritten in-place. No additional cleanup needed — the overwrite IS the cleanup, matching how `last-files.txt` works today.
3. **Verify**: `resume_check`'s "Fix 2" stale-checkpoint detection (`general-task.yaml:119-126`) already handles the case where `checkpoint.json` exists without `current-step.txt`, so no change is needed there. With the fix, `current-step.txt` will always be present whenever `checkpoint.json` is present (both are written by `select_step` atomically), so Fix 2's `RESUME_CLEAN` branch becomes unreachable in normal flow — but the guard stays as defensive code.

The proposed change is **3 lines net** (delete 1 in `mark_done`, no additions elsewhere) and is bounded — the only files it touches are `general-task.yaml` and any test that asserts `current-step.txt` deletion timing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **All referenced line numbers verified accurate** against the current 641-line `general-task.yaml`: `mark_done` `rm -f "$STEP_FILE"` at line 279, `select_step` write at line 179, `check_done` read at line 295, `resume_check` Fix 2 at lines 119-126.
- **`mark_done` deletes `checkpoint.json` on the *next* line (280), not the same line.** `general-task.yaml:279-280` is two statements: `rm -f "$STEP_FILE"` (279) then `rm -f "${context.run_dir}/checkpoint.json"` (280). The fix removes only line 279; keep line 280 as the issue states.
- **`select_step` already performs the cleanup — no addition is needed there.** The happy path overwrites in place via `echo "$STEP" > "${context.run_dir}/current-step.txt"` (line 179), and the attempt-cap *abandonment* branch explicitly deletes it via `rm -f "${context.run_dir}/current-step.txt" "${context.run_dir}/checkpoint.json"` (line 174). So the fix is a pure 1-line deletion in `mark_done`; the "move the `rm` into `select_step`" framing is already satisfied by existing code.
- **Additional required change the current plan omits: the `resume_check` Fix 2 comment becomes stale.** Lines 119-121 assert *"mark_done deletes both together; a checkpoint without its current-step.txt is a stale/corrupt artifact."* After the fix, `mark_done` deletes only `checkpoint.json`, so `current-step.txt` will normally *survive* `mark_done` while `checkpoint.json` is gone — the exact inverse of the documented invariant. The guard logic (lines 122-126) can stay as defensive dead code, but the comment at 119-121 must be updated so it doesn't mislead a future reader.

## Error Messages

Worker output from `check_done` on the second-and-later steps:

```
The `current-step.txt` file doesn't exist. Let me check the run directory contents.
```

The exact wording varies by worker model, but the diagnostic shape — naming the deleted file and pivoting to directory enumeration — is consistent across recent runs.

## Implementation Steps

1. Remove `rm -f "$STEP_FILE"` from `mark_done` action (`general-task.yaml:279`).
2. Confirm `select_step` (`general-task.yaml:179`) overwrites `current-step.txt` unconditionally on every iteration, eliminating the need for a separate delete step.
3. Add a regression test that exercises a 2-step `general-task` run and asserts `current-step.txt` exists at every state transition from `select_step`'s write through `select_step`'s next write (i.e. is readable by `do_work`, `mark_done`, `check_done`, and `continue_work`).
4. Re-verify `resume_check`'s stale-checkpoint path still works when `checkpoint.json` is present but `current-step.txt` is absent (e.g. a manually-corrupted run directory). Fix 2's `rm -f "$CHECKPOINT"` should still apply.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete additional steps surfaced by research:_

5. **Invert the load-bearing regression test** `test_removes_current_step_temp_file` at `scripts/tests/test_general_task_loop.py:550-556` (class `TestMarkDoneShellAction`). It currently asserts `mark_done` *removes* `current-step.txt`; after the fix it must assert `mark_done` *preserves* it. This is the single test that will break — the issue's Step 3 "any test that asserts deletion timing" refers to exactly this test.
6. **Add the new regression test in `test_general_task_loop.py`, not `test_builtin_loops.py`.** The marker-lifecycle unit tests and their helpers (`_load_state_script`, `_setup_run_dir`, `_bash`, `_setup_dod_plan`) all live in `test_general_task_loop.py`. Model the new test on `TestMarkDoneShellAction` / `TestSelectStepShellAction` (e.g. `test_unchecked_step_writes_temp_file` at `test_general_task_loop.py:459-465`).
7. **Leave these tests green (no change needed):** `test_mark_done_action_references_current_step_file` (`test_general_task_loop.py:738-743`) still passes because `mark_done` keeps *reading* `current-step.txt` (`STEP_FILE`/`STEP_TEXT` at lines 268/273) — only the `rm` at 279 is removed; and `test_checkpoint_without_current_step_emits_resume_clean` (`test_general_task_loop.py:1315-1330`, class `TestResumeCheckBUG1960`) still passes since Fix 2's guard logic is retained.
8. **Update the stale comment** at `general-task.yaml:119-121` (see Proposed Solution findings) and **the doc line** at `docs/guides/LOOPS_REFERENCE.md:111` (see Integration Map findings), both of which describe `mark_done` deleting `current-step.txt`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis (Agent 1 + Agent 3) and must be included in the implementation alongside the steps above:_

9. **Extend `TestCheckpointClearShellAction.test_removes_checkpoint_when_present`** (`scripts/tests/test_general_task_loop.py:615-625`) with `assert step_file.exists()`. The test already sets up `step_file` (line 618) and calls `_run(tmp_path)`; after the fix, adding the marker-existence assertion extends coverage from "checkpoint deleted" to the WHOLE marker-lifecycle contract — the natural complement to Step 5's inversion at line 550-556.
10. **Extend `TestCheckpointClearShellAction.test_tolerates_missing_checkpoint`** (`scripts/tests/test_general_task_loop.py:627-633`) with `assert step_file.exists()` for symmetry. The primary assertion is `result.returncode == 0` (line 633), but a secondary marker-existence assertion closes the marker-lifecycle coverage for the no-checkpoint code path (currently `mark_done` is the only consumer that survives that branch).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — remove `rm -f "$STEP_FILE"` from `mark_done` (line 279).

### Dependent Files (Callers/Importers)
- None — `general-task.yaml` is a self-contained loop YAML. No other loop imports its actions.

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml:152-184` (`select_step`) — already overwrites `current-step.txt` on every iteration; the fix aligns `current-step.txt`'s lifecycle with `last-files.txt`'s.
- `last-files.txt` lifecycle: written by `do_work` (`general-task.yaml:204-206`), read by `verify_step` and `check_done`, never deleted mid-loop. This is the model to mirror.

### Tests
- `scripts/tests/test_builtin_loops.py` — search for existing `general-task` lifecycle tests; add a regression test asserting `current-step.txt` is readable in `check_done`.
- `python -m pytest scripts/tests/` — must exit 0 (project CI gate per `.claude/CLAUDE.md`).

#### Codebase Research Findings

_Added by `/ll:refine-issue` — the actual marker-lifecycle tests live in a different file than stated above:_

- **Load-bearing test to invert:** `scripts/tests/test_general_task_loop.py:550-556` — `TestMarkDoneShellAction.test_removes_current_step_temp_file` currently asserts `mark_done` *removes* `current-step.txt`. This test **encodes the bug** and must flip to assert preservation.
- **Primary lifecycle test file:** `scripts/tests/test_general_task_loop.py` (not `test_builtin_loops.py`). Relevant siblings: `test_check_done_reads_bounded_marker_files_not_full_captures` (264-283, the ENH-2486 assertion that started requiring the marker read), `test_unchecked_step_writes_temp_file` (459-465), `test_mark_done_action_references_current_step_file` (738-743), `TestResumeCheckBUG1960` Fix 2 (1315-1330). Helpers: `_load_state_script`, `_setup_run_dir`, `_bash`, `_setup_dod_plan`, `_bash("bash -c ...")` subprocess pattern.
- **Secondary file** `scripts/tests/test_builtin_loops.py` — `TestGeneralTaskLoop` (≈8605-8676) loads `general-task.yaml` and asserts FSM shape; no direct `current-step.txt` assertions, but it loads the same YAML the fix edits, so run it too.
- **Suggested test plan** (from existing conventions — `_setup_run_dir` / `_load_state_script` / `_bash` trio at `test_general_task_loop.py:415-426,774-775`):
  1. Flip `test_removes_current_step_temp_file` (550-556) to `assert step_file.exists()`.
  2. Add a cheap structural guard asserting `mark_done.action` no longer contains `rm -f "$STEP_FILE"` (mirrors the positive substring check at 738-743 — no bash needed).
  3. Add a fixture-based persistence test (new class `TestBUG2538CurrentStepPersistence`, or under `TestBUG1766ConvergenceEfficiency` at line 692) that chains `select_step` → `mark_done` against one shared `run_dir` and asserts `current-step.txt` survives with the selected step text. **Note:** no existing helper runs two states in sequence — the closest analogue is `TestAutoRefineAndImplementLoop._run_finalize` in `test_builtin_loops.py`; chain two `_bash` calls inline.

#### Wiring Findings

_Added by `/ll:wire-issue` — complement-assertion sites that extend existing tests' coverage without inventing new classes:_

- `scripts/tests/test_general_task_loop.py:615-625` (`TestCheckpointClearShellAction.test_removes_checkpoint_when_present`) — passes unchanged after the fix (only asserts `not checkpoint.exists()`), but stops exercising the WHOLE marker-lifecycle contract. Adding `assert step_file.exists()` is the natural complement to Step 5's inversion at line 550-556 — the test already creates `step_file` on line 618. Captured by Agent 1 and Agent 3 independently.
- `scripts/tests/test_general_task_loop.py:627-633` (`TestCheckpointClearShellAction.test_tolerates_missing_checkpoint`) — same situation for the no-checkpoint branch. Primary purpose is `result.returncode == 0` (line 633), but extending with `assert step_file.exists()` closes the marker-lifecycle coverage for the path that previously exercised both `rm` lines simultaneously.
- **No other tests in `scripts/tests/` reference `current-step.txt`, `last-files.txt`, or the `mark_done` action text outside this file.** Tests in `test_fsm_validation.py:2693-2736` (`test_general_task_pattern_emits_warning`), `test_fsm_interpolation.py:773-782` (`test_general_task_check_done_safe_with_empty_captured`), and `test_fsm_interpolation.py:784-793` (`test_general_task_run_final_tests_safe_with_empty_context`) load or mirror the FSM YAML but do not exercise the marker-lifecycle bash path; they remain accurate after the fix.

### Documentation
- None — internal-only loop YAML; no external API.

#### Codebase Research Findings

_Added by `/ll:refine-issue` — a documentation reference does exist and will go stale:_

- **`docs/guides/LOOPS_REFERENCE.md:111`** states `mark_done` "removes the current-step temp file and the in-flight checkpoint" — false after the fix; update to reflect that `mark_done` removes only the checkpoint and `current-step.txt` persists until the next `select_step` overwrite. Lines 122-125 (describing `continue_work` reading `current-step.txt` on the exit-124 branch) remain accurate.

#### Wiring Findings

_Added by `/ll:wire-issue` — documentation scope confirmation (no additional edits needed):_

- **`docs/guides/LOOPS_REFERENCE.md:107-109,114`** (`resume_check`, `select_step`, `do_work`, `check_done`) all remain accurate after the fix — verified by Agent 1. Only line 111 needs editing.
- **`docs/guides/LOOPS_GUIDE.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`** are listed above under "Related Key Documentation" as cross-references, but grep across both files returned **zero matches** for `current-step.txt`, `checkpoint.json`, `last-files.txt`, `mark_done`, `select_step`, `LAST_STEP`, `LAST_FILES`, or `bounded`. They describe the bounded-marker pattern at the conceptual level without naming the file. **No edits needed in either file** — they remain accurate as conceptual cross-references and should not be expected to mention the marker-file mechanics.
- **`CHANGELOG.md`** does not currently reference BUG-2538. A release entry will be added at release-prep time per the project's `BUG-NNN — short summary` convention (per memory `feedback_changelog_no_unreleased.md`). Out of scope for this fix.
- **No CLI / command / skill / hook / agent coupling** was found: `commands/`, `skills/`, `agents/loop-specialist.md`, `hooks/hooks.json`, `.claude-plugin/plugin.json`, `.ll/ll-config.json`, and `config-schema.json` were all searched. The only non-test `general-task` reference is `scripts/little_loops/loops/proof-first-task.yaml:14` (`impl_loop: "general-task"` — a configurable default) which does not import any actions and is not affected by the marker lifecycle.
- **No other loops share the bounded-marker pattern**: `scripts/little_loops/loops/loop-composer.yaml` and `loop-composer-adaptive.yaml` use different filenames (`current-step-{id,num,loop,input}.txt`, `current-step-output.jsonl`) and never `rm` them — zero cross-loop blast radius (confirmed by Agent 1 + Agent 2).
- **No FSM engine-side coupling**: `scripts/little_loops/fsm/validation.py` MR-1..10 lints do not scan for `rm -f "$STEP_FILE"` patterns. `ll-loop validate` will not flag the rm removal (verified by Agent 1).

### Configuration
- N/A

## Impact

- **Priority**: P2 — bug is correctness-preserving (loop still completes, DoD machinery is unaffected) but produces noisy worker output, wastes a turn of context per step in `check_done` and `continue_work`, and obscures the `LAST_STEP` semantics ENH-2486 was added to provide. P2 fits because: it's user-visible (the diagnostic chatter is exactly what triggered this capture), it's a regression (introduced by `b851b4ba` 2 days ago), and it's blocking clean adoption of ENH-2486's bounded-marker pattern across other loops that may want to reuse the same idiom.
- **Effort**: Small — 1-line deletion in `mark_done`, plus a regression test. The hardest part is verifying no other loop relies on `current-step.txt` being deleted by `mark_done`.
- **Risk**: Low — `current-step.txt` is `rm -f`'d (not unlinked with strict semantics), so the file is recreated on the next `select_step` regardless. The fix only changes *when* the cleanup happens, not *whether* it happens. `resume_check`'s Fix 2 path remains valid as defensive code.
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — bounded-marker pattern rules and lifecycle guidance (the source of the fix's shape)
- `docs/guides/LOOPS_GUIDE.md` — `general-task` lifecycle documentation
- `.claude/CLAUDE.md` § Development / Testing & CI Policy — `python -m pytest scripts/tests/` is the project's CI gate

## Session Log
- `/ll:wire-issue` - 2026-07-08T01:35:39 - `6596b6ea-de92-4885-bfd7-2eca18d38e3f.jsonl`
- `/ll:refine-issue` - 2026-07-08T01:10:19 - `580b0186-6653-4e5a-9130-197bbb958dca.jsonl`

- `/ll:capture-issue` - 2026-07-07 - capture triggered by user observation of recurring "current-step.txt doesn't exist" diagnostic in `general-task` runs
- `/ll:manage-issue` - 2026-07-08T02:01:47 - `5fdce2b2-0412-4f3e-a374-b1f830b080cd.jsonl` - removed `rm -f "$STEP_FILE"` from mark_done; updated stale resume_check comment + LOOPS_REFERENCE.md; inverted test_removes_current_step_temp_file → test_preserves_current_step_marker_file; added test_action_does_not_rm_step_file (structural guard); extended TestCheckpointClearShellAction with `assert step_file.exists()` on both branches

## Status

**Open** | Created: 2026-07-07 | Priority: P2