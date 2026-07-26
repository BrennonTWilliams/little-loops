---
id: BUG-2832
type: BUG
title: "input_hash never injected for sub-loops \u2014 general-task always fails as\
  \ a sub-loop"
priority: P1
status: done
captured_at: '2026-07-26T18:09:17Z'
completed_at: '2026-07-26T18:37:01Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to:
- BUG-2831
- FEAT-1738
labels:
- fsm
- sub-loop
- general-task
- learning-gate
confidence_score: 96
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2832: input_hash never injected for sub-loops — general-task always fails as a sub-loop

## Summary

`input_hash` is a runner-injected context variable (listed in `RUNNER_INJECTED = {"run_dir", "loop_name", "started_at", "input_hash"}` at `scripts/little_loops/fsm/validation.py:609`), but it is only actually computed at the CLI top level: `scripts/little_loops/cli/loop/run.py:203` hashes `fsm.context["input"]` into `fsm.context["input_hash"]`. `_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:803`) never injects it into the child context. Any sub-loop whose states interpolate `${context.input_hash}` — `general-task.yaml` does at lines 114 (`resume_check`) and 189 (checkpoint write) — hits an interpolation error, routes `on_error: diagnose`, and lands in the `failed` terminal.

Because the validator treats `input_hash` as runner-injected, capture-reachability checks assume it always exists, so this cannot be caught at validate time either.

## Current Behavior

Every recent `general-task` row in `.ll/history.db` `loop_runs` shows `final_state=failed, iterations=5` — the loop dies deterministically at `resume_check` when invoked as a sub-loop (e.g. `proof-first-task` → `run_impl` → `general-task`). Observed concretely in run `proof-first-task-20260726T125247` (spawned by ll-auto's learning gate for BUG-2831): `ready-to-implement-gate` → done, `general-task` → failed at 5 iterations with zero plan steps executed, `proof-first-task` → `impl_failed`. Downstream, this failure was mislabeled as a learning-gate block (see BUG-2833) and BUG-2831 was deferred as `gate_blocked`.

## Expected Behavior

A sub-loop receives the same runner-injected context contract as a top-level loop: `input_hash` (hash of the child's resolved `input`, or of the empty string when input is empty) is present in the child context, and `general-task` runs identically whether invoked top-level or as a sub-loop.

## Root Cause

`scripts/little_loops/cli/loop/run.py:203` — `input_hash` derivation lives in the CLI entry point instead of shared executor/spawn code:

```python
if "input_hash" not in fsm.context and isinstance(fsm.context.get("input"), str):
    fsm.context["input_hash"] = hashlib.sha256(fsm.context["input"].encode()).hexdigest()[:12]
```

`_execute_sub_loop` (`scripts/little_loops/fsm/executor.py:803`) builds the child context from `with:` bindings plus child defaults and injects `run_dir`/`loop_name`/etc., but not `input_hash`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The identical two-line `input_hash` idiom is actually duplicated at **three** sites, not one — all three need to funnel through whatever shared helper is extracted: `scripts/little_loops/cli/loop/run.py:203-204` (fresh top-level run), `scripts/little_loops/cli/loop/lifecycle.py:527-528` (resume path — re-injects on resumed runs), and `scripts/little_loops/cli/loop/testing.py:218-221` (simulation path, with its own local `import hashlib`). `_execute_sub_loop` is the fourth, missing site.
- `loop_name`/`started_at` are **not** actually written into `fsm.context` as literal dict keys anywhere in `run.py` or `executor.py`, despite being listed in `RUNNER_INJECTED` alongside `run_dir`/`input_hash` (`validation.py:609`). They're tracked as executor instance state instead — `self.fsm.name` and `self.started_at` (set via `_iso_now()` at `executor.py:452`) — used only for observability event payloads (`executor.py:2517-2519`, `:2904`, `:2908-2909`). So the Root Cause statement above ("injects `run_dir`/`loop_name`/etc.") should be read as: only `run_dir` gets an actual context-dict re-injection in `_execute_sub_loop` today; `loop_name`/`started_at` were never context-dict keys to begin with.
- Exact precedent for where to add the `input_hash` fix: `_execute_sub_loop`'s `with:` branch (`executor.py:846-875`) already re-injects `run_dir` via `child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])` at lines 867-875, with an inline comment explaining why (`run_dir` is only injected top-level, every loop assumes its presence). This is the direct model to follow for `input_hash`, except the derivation should hash the **child's own resolved `input`** (post `with:` merge), not blindly copy the parent's value — the `context_passthrough` branch (`executor.py:876-883`, which spreads `**self.fsm.context` first) already gets the parent's `input_hash` "for free" if present, but that's only correct when the child's `input` is the same string as the parent's.
- `seed_confidence_thresholds()` (`scripts/little_loops/cli/loop/_helpers.py`, called at `executor.py:889-891` per BUG-2767) is the one existing precedent in this codebase for a shared helper function invoked from `_execute_sub_loop` specifically to backfill a context value that only the top-level CLI path sets by default — the closest existing model for the `inject_runner_context(fsm)`-style helper this issue's Proposed Solution step 2 proposes.
- Predecessor issue `ENH-1959` (status: done) is where the top-level `input_hash` injection (and the `RUNNER_INJECTED` validator entry) was originally introduced — it covered `run.py`, `lifecycle.py`, and `validation.py`, but never touched `_execute_sub_loop`, which is exactly the gap this bug closes.
- Test model: `scripts/tests/test_fsm_executor.py:5700` (`test_sub_loop_context_passthrough`) and `:5734` (`test_sub_loop_context_passthrough_captured_values`) build a parent `FSMLoop` inline with a temp child YAML string, run `executor.run()`, and assert on `executor.captured[...]` / captured output values — this is the shape to model the new `input_hash`-in-sub-loop test after (write a temp child YAML whose action interpolates `${context.input_hash}`, run the parent, assert no interpolation error and that the captured value equals the expected sha256 truncated hash).
- No existing shared sha256-truncated-hex helper exists elsewhere in `scripts/little_loops/` to reuse — the new helper is new code, not a wrapper over something pre-existing.

## Proposed Solution

Move (or duplicate) the `input_hash` derivation into the sub-loop spawn path so every child executor gets it:

1. In `_execute_sub_loop`, after resolving the child context, apply the same derivation: if `input_hash` absent and `input` is a str, set `input_hash = sha256(input)[:12]`.
2. Prefer extracting a shared helper (e.g. `inject_runner_context(fsm)` in `fsm/` used by both `cli/loop/run.py` and `_execute_sub_loop`) so the `RUNNER_INJECTED` contract in `validation.py:609` has a single implementation to drift-check against.
3. Defensively, `general-task.yaml` could also use `${context.input_hash:default=}` at lines 114/189, but the primary fix is the executor injection — other loops referencing runner-injected vars would otherwise hit the same class of bug.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The shared helper (step 2) should consolidate **all four** derivation sites, not just `run.py` + `_execute_sub_loop`: `cli/loop/run.py:203-204`, `cli/loop/lifecycle.py:527-528` (resume path), and `cli/loop/testing.py:218-221` (simulation path) all currently duplicate the identical `if "input_hash" not in fsm.context and isinstance(fsm.context.get("input"), str): ...` idiom.
- Follow the `run_dir` re-injection pattern already in `_execute_sub_loop`'s `with:` branch (`executor.py:867-875`, a `setdefault` guarded by presence-in-parent) as the structural template, and `seed_confidence_thresholds()` (`cli/loop/_helpers.py`, called at `executor.py:889-891`) as the precedent for a genuinely shared cross-module helper function called from `_execute_sub_loop`.
- Derive the hash from the **child's own resolved `input`** (post `with:` merge), not the parent's `input_hash` value — the `context_passthrough` branch already inherits the parent's `input_hash` via its full-context spread, which is only correct when the child's `input` is identical to the parent's.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add a new sub-loop `input_hash`-injection test in `test_fsm_executor.py`, modeled structurally on `test_with_inherits_parent_run_dir`/`test_with_explicit_run_dir_overrides_parent` (lines 8215/8264) rather than only the more general `test_sub_loop_context_passthrough` pair — include the `with:`-explicit-override-wins variant to mirror `run.py`'s existing override test.
5. Add a `cmd_simulate` `input_hash` test to `scripts/tests/test_cli_loop_testing.py` (currently zero coverage of that code path).
6. Add an integration-level test exercising `general-task` as an actual sub-loop (e.g. via `proof-first-task`'s `run_impl` delegation or a minimal equivalent) through the real FSM executor — `test_general_task_loop.py`'s existing shell-action tests manually substitute `${context.input_hash}` and cannot catch this class of bug.
7. Update `docs/generalized-fsm-loop.md:1069`'s `input_hash` reference table row to state it is also injected for sub-loop spawns, not just `cmd_run`/`cmd_resume`.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml` — delegates to `general-task` as a sub-loop (`run_impl` state); this is the concrete reproduction path in the bug's own Current Behavior section, so it should be the integration-level test target [Agent 1 finding]
- `scripts/little_loops/loops/rn-refine.yaml` — delegates to a child loop that may also reference `input_hash`; worth a quick grep pass once the fix lands to confirm no other builtin loop hits the same gap [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:1069` — reference table row documents `input_hash` as injected by `cmd_run` / `cmd_resume` only; should be updated to state it's also injected for sub-loop spawns once `_execute_sub_loop` is fixed [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:107` — describes `general-task`'s `resume_check` state validating `task_hash` against `${context.input_hash}`; this prose implicitly assumes `input_hash` is always present, which is only true post-fix — no change needed to the prose itself, but worth a sanity-check pass once fixed [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_program_md.py:334,371,398` (`test_input_hash_injected_into_context`, `test_input_hash_not_injected_when_input_absent`, `test_context_input_hash_not_overwritten_by_user_context`) — existing top-level `run.py` behavioral-contract tests; should keep passing unchanged through a like-for-like helper extraction, but verify after refactor since they're the actual home of these assertions (not `test_ll_loop_commands.py`, despite the issue's Root Cause section citing only `run.py:203`) [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py:4711` (`test_input_hash_determinism`) — same-input→same-hash / different-input→different-hash / 12-char-length contract the shared helper must preserve exactly [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py:948` (`test_input_hash_injected_via_cmd_resume`) — resume-path contract test; no existing test covers the `--context input_hash=` override-wins case on this path specifically (a gap relative to the `run.py` override test) [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py:2469` (`test_input_hash_in_runner_injected`) — documents the validator's static-analysis assumption that `input_hash` is always present; remains correct post-fix and needs no change, but is the direct precedent for why this bug was invisible to `ll-loop validate` [Agent 3 finding]
- `scripts/tests/test_cli_loop_testing.py` — **test gap**: no test in this file (or anywhere in `scripts/tests/`) covers `testing.py:218-221`'s simulation-path `input_hash` derivation; new test needed once the shared helper is wired into `cmd_simulate` [Agent 3 finding]
- `scripts/tests/test_general_task_loop.py` (`TestResumeCheckShellAction`, `TestCheckpointWriteShellAction`, etc.) — existing tests manually string-replace `${context.input_hash}` before running the shell body via `_bash(...)`, bypassing FSM interpolation entirely; **these cannot and do not catch BUG-2832** since the substitution always succeeds. Confirms the issue's own AC #4 (integration-level or targeted sub-loop test) is filling a real gap, not duplicating coverage [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py:8215,8264` (`test_with_inherits_parent_run_dir`, `test_with_explicit_run_dir_overrides_parent`) — the direct structural template for the new sub-loop `input_hash` test (child echoes `${context.input_hash}`, capture, assert against expected hash) and its `with:`-override-wins sibling; more precise template than the `test_sub_loop_context_passthrough` pair already cited in Codebase Research Findings [Agent 3 finding]

## Steps to Reproduce

1. `ll-loop run proof-first-task --context issue_file=<any issue path> --context targets_csv=anthropic`
2. Observe `general-task` (the `run_impl` child) fail at iteration 5 (`resume_check` → `diagnose` → `failed`) with all plan steps unchecked.
3. `sqlite3 .ll/history.db "select final_state, iterations from loop_runs where loop_name='general-task' order by started_at desc limit 5"` → all `failed|5`.

## Acceptance Criteria

- [x] `_execute_sub_loop` injects `input_hash` into the child context (derived from the child's resolved `input`, matching the top-level derivation in `cli/loop/run.py`)
- [x] The derivation logic is shared (single helper) between the CLI entry (`cli/loop/run.py`), the resume path (`cli/loop/lifecycle.py`), the simulation path (`cli/loop/testing.py`), and the sub-loop spawn path (`fsm/executor.py`) — all four call the shared helper instead of duplicating the inline sha256 idiom
- [x] A unit test in `scripts/tests/test_fsm_executor.py`, modeled on `test_sub_loop_context_passthrough` (line 5700), asserts a sub-loop child context contains `input_hash` and that a child state interpolating `${context.input_hash}` executes without an interpolation error
- [x] `general-task` invoked as a sub-loop progresses past `resume_check` (integration-level test or targeted executor test with a minimal child loop referencing `${context.input_hash}`) — satisfied via the targeted-executor-test alternative (`test_sub_loop_input_hash_injected`)
- [x] `python -m pytest scripts/tests/` passes with no new failures

## Session Log
- `/ll:manage-issue` - 2026-07-26T18:37:00Z - `00557ce1-99c8-4081-bd88-ee5dff5c38ff.jsonl`
- `/ll:ready-issue` - 2026-07-26T18:28:14 - `e32d8c88-f54b-4a89-bb59-bd12bced264f.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00Z - `58ee651f-68b7-4dfc-93f8-d62a929344d1.jsonl`
- `/ll:wire-issue` - 2026-07-26T18:25:03 - `45de3257-8d9c-4924-9061-a874c56aca41.jsonl`
- `/ll:refine-issue` - 2026-07-26T18:20:56 - `d06f3217-7cde-412d-8425-41e312d3e98e.jsonl`
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`
