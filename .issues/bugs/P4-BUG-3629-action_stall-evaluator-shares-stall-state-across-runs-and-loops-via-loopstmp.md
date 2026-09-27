---
id: BUG-3629
type: BUG
title: action_stall evaluator shares stall state across runs and loops via .loops/tmp
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T04:29:54Z'
depends_on:
- BUG-3627
spike_attempted: true
spike_completed: true
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3629: action_stall evaluator shares stall state across runs and loops via .loops/tmp

## Summary

`evaluate_action_stall` (`little_loops.fsm.evaluators`, `evaluators.py` ~:837) persists its snapshot hash and stall counter in `.loops/tmp/ll-action-stall-<md5(sorted track keys)[:12]>.{txt,count}`, resolved from `Path.cwd()`. The key derives only from the tracked key names, and nothing resets it at run start, so state leaks across runs and across loops. Follow-up split out of BUG-3627 (`diff_stall` has the same defect and was scoped separately).

## Current Behavior

- Every loop using the default `track: ["action"]` shares `ll-action-stall-<key>.*`, so concurrent runs of different loops clobber each other's counters.
- A new run inherits the previous run's snapshot and count. If the prior run ended stalled and the new run's first tracked value hashes identically, the first check increments past `max_repeat` and returns `no` immediately instead of the first-call `yes`.
- The docstring claims "different states/loops maintain independent stall counters"; that holds only when their tracked key names differ, not their runs or states.
- No built-in loop under `scripts/little_loops/loops/` currently uses `action_stall` (grep finds none), so exposure is limited to user-authored loops. Hence P4.

## Steps to Reproduce

1. Author a loop with a state using `evaluate: {type: action_stall, max_repeat: 1}` and the default `track: ["action"]`, with a constant action string.
2. Run it until the evaluator returns `no` (stalled); `.loops/tmp/ll-action-stall-<key>.count` now holds `>= max_repeat`.
3. Start a second run (same or a different loop with the same `track`) from the same working directory.
4. Observe: the first check on the new run returns `no` immediately (inherited snapshot and count) instead of the first-call `yes` with `stall_count` 0.

## Expected Behavior

Stall state is scoped per run instance and per state. A fresh run's first check always returns `yes` with `stall_count` 0.

## Motivation

`action_stall` is a documented non-LLM stall evaluator (used to satisfy MR-1 pairing for harness loops). Cross-run and cross-loop state leakage produces false stall verdicts that terminate healthy loops early, or hide real stalls when concurrent loops reset each other's counters. Fixing it keeps the evaluator trustworthy and aligns it with the per-run `run_dir` convention already used by `score_stall` / `open_question_stall`.

## Proposed Solution

Mirror the BUG-3627 approach:

- Derive `state_dir` from `context.context["run_dir"]` (the function already receives `context`), keying files `ll-action-stall-<loop_name>-<state_name>-<md5(sorted track)[:12]>.{txt,count}`. Fall back to the current `.loops/tmp/ll-action-stall-<md5(track)[:12]>` path only when no run context exists (`cli/loop/testing.py::cmd_test` passes a bare `InterpolationContext()`).
- **Key includes loop name, not only state name** (review 2026-09-27, aligns with BUG-3627): child loops `setdefault` the parent's `run_dir`, and state names repeat across loops. A parent and child that both name the state `check_stall` with the same `track` would collide under a `<state_name>-<hash>` key. The spike's `test_parent_child_sharing_run_dir_isolated` passed only because it used different state names. Read `context.loop_name` alongside `context.state_name`.
- **File names keep the `ll-action-stall-` prefix inside `run_dir`**: the spike's `<state_name>-<key>` stem drops it and becomes `-<key>` when `state_name` is empty (the `cmd_test` shape). Use BUG-3627's shared `_stall_state_paths("action", state_dir, loop_name, state_name, track)` helper, which prefixes, sanitizes names (`/` in loop names such as `oracles/…`), and handles empty names.
- Keep `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`) unchanged.
- Correct the docstring ("different states/loops maintain independent stall counters").
- **Implementation order**: BUG-3627 introduces `_stall_state_paths`; this issue reuses it (`depends_on: BUG-3627`). Implementing both in one change is also fine.
- **Accepted limitations, same decisions as BUG-3627 (2026-09-27)**: a child loop re-entered within one parent run shares `run_dir` and key, so it inherits the prior invocation's stall state. `ll-loop simulate` uses a fixed `runs/<loop>-simulate/` dir, so stall state carries across simulate runs. Neither is covered by the fresh-run guarantee; document both in the docstring and `cmd_simulate` docstring rather than clearing files.

## Program Design

### Types

- `state_dir: Path | None` — per-run directory for snapshot/count files; `None` keeps the legacy `.loops/tmp` location
- `state_name: str` — state identifier, part of the file key
- `loop_name: str` — loop identifier, part of the file key (separates parent/child states with the same name)

### Signatures

- `evaluate_action_stall(track: list[str] | None = None, max_repeat: int = 2, context: InterpolationContext | None = None, state_dir: Path | None = None, state_name: str = "", loop_name: str = "") -> EvaluationResult` — state files from `_stall_state_paths("action", ...)`: `ll-action-stall-<loop_name>-<state_name>-<md5(sorted track)[:12]>`; `details` keys unchanged

### Call Path

`evaluate` (`elif eval_type == "action_stall"` branch) -> `evaluate_action_stall(..., state_dir=<context.context["run_dir"]>, state_name=context.state_name, loop_name=context.loop_name)` -> `EvaluationResult` verdict `yes` / `no` -> state routing

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_action_stall()` (state path, docstring) and the `evaluate()` `action_stall` branch (~:2044) that derives `state_dir` from `context.context["run_dir"]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test` passes a bare `InterpolationContext()` (must hit the `.loops/tmp` fallback)
- `scripts/little_loops/fsm/schema.py` — `track` / `max_repeat` evaluator fields (unchanged)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()` calls `evaluate(config=..., output=..., exit_code=..., context=ctx)` (~:3196); `ctx` is built with `state_name=self.current_state` (~:2353) and `context=self.fsm.context` (incl. `run_dir`), so `state_name` for the file key comes from `context.state_name` with no new `evaluate()` parameter (same source `evaluate()` already uses for the `advisor_consult` branch, ~:2094) [Agent 1 + 2 finding]
- `scripts/little_loops/cli/loop/run.py` — injects `fsm.context["run_dir"]` as `runs/<instance_id or loop_name>/` (~:236) and `mkdir`s it before evaluation (~:614); `--context run_dir=` overrides. `run_dir` is a trailing-slash string, so wrap in `Path()` [Agent 2 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — resume path sets `run_dir` to `runs/<instance_id>/` (~:681), so a resumed run keeps its stall state (desired) [Agent 2 finding]
- `scripts/little_loops/cli/loop/testing.py::cmd_simulate` — sets `run_dir` to `<loops_dir>/runs/<loop>-simulate/` on every invocation, so stall state persists across successive `ll-loop simulate` runs of the same loop (same `-simulate` dir). Decided (2026-09-27, shared with BUG-3627): accept and document in the `cmd_simulate` docstring [Agent 2 finding]
- `scripts/little_loops/cli/loop/testing.py::cmd_test` — bare `InterpolationContext()` has `state_name == ""` as well as no `run_dir`; the legacy-path fallback must not require a non-empty `state_name`. Its docstring (~:189) says the state file is "normally under `.loops/tmp/`" — update [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py` sub-loop handling (~:1152, ~:1238) — `child_fsm.context.setdefault("run_dir", ...)` makes parent and child share `run_dir`; confirms `state_name` must be in the file key [Agent 2 finding]
- `scripts/little_loops/persistence.py::archive_run` — archives `run_dir`; stall files moved under it are now archived with the run (today's `.loops/tmp` files are outside it) [Agent 2 finding]
- `scripts/little_loops/fsm/validation/meta_rules.py` — MR-1 counts `action_stall` as a non-LLM evaluator by type only; `_SHARED_TMP_PATH_RE` scans state actions, not evaluator internals, so the `.loops/tmp` fallback is not linted. No change [Agent 2 finding]

### Similar Patterns
- `evaluate_diff_stall()` (BUG-3627), `evaluate_score_stall`, `evaluate_open_question_stall` — `run_dir`-scoped state; share one state-dir/key helper with BUG-3627

### Tests
- `scripts/tests/test_fsm_evaluators.py` — action_stall test class (~:2118); its `clean_state_files` fixture relies on cwd `.loops/tmp`, add run_dir cases

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py::TestActionStallEvaluator` — the six direct-call tests (`test_first_iteration_returns_yes`, `test_different_action_returns_yes`, `test_identical_at_threshold_returns_no`, `test_identical_below_threshold_returns_yes`, `test_stall_then_progress_resets`, multi-key test) call `evaluate_action_stall(context=ctx)` with no `state_dir`; keep them unchanged as fallback-path regression coverage (new params must default to `None` / `""`) [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py::_ctx` — extend or add a variant accepting `run_dir` and `state_name`; `state_name` is an `InterpolationContext` field, not a `context` key, so it needs `InterpolationContext(state_name=...)` [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py::test_dispatch_action_stall`, `test_dispatch_action_stall_with_options` — bare context, exercise the fallback; add sibling dispatch tests with `InterpolationContext(context={"run_dir": str(tmp_path/"run")}, state_name="s")` asserting the files land under `run_dir` and a second `run_dir` starts fresh (model: `test_dispatch_defaults_to_run_dir_history`) [Agent 3 finding]
- `scripts/tests/test_fsm_evaluators.py::test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators[action_stall]` (~:942) — runs the real evaluator with a bare context and **no chdir isolation**, so it writes to the real cwd `.loops/tmp`; stays green via fallback, but must never start raising on a missing `state_dir` [Agent 3 finding]
- `scripts/tests/test_grader_coverage.py` — `EXEMPT_GRADERS` lists `"evaluate_action_stall"` (~:51); `test_all_evaluate_functions_classified` requires the function name unchanged. No change [Agent 1 + 3 finding]
- `scripts/tests/test_fsm_schema.py` (`test_action_stall_round_trips_through_dict`, `test_action_stall_to_dict_omits_defaults`) — break only if new `EvaluateConfig` fields are added; none are planned. No change [Agent 3 finding]
- `scripts/tests/spike/action_stall_run_scope/test_run_scoped_stall.py` — promote the behavioural tests into `TestActionStallEvaluator`, rewriting `_check(...)` to call `evaluate_action_stall(track=..., max_repeat=..., context=ctx, state_dir=..., state_name=...)` and mapping `(verdict, count)` to `result.verdict` / `result.details["stall_count"]`; drop `test_guard_spike_does_not_import_production_evaluators`; also assert no `.loops/` is created under cwd when `state_dir` is set [Agent 3 finding]
- **New (none exist):** executor-level two-run test in `scripts/tests/test_fsm_executor.py` — `FSMLoop` with a `StateConfig` carrying `evaluate: action_stall`, run twice with different `fsm.context["run_dir"]`, assert the second run does not inherit the first's stall count (model FSM construction on the blocks at ~:2066-2280) [Agent 3 finding]
- **New:** `state_dir` set with empty `state_name` case (the `cmd_test` shape once `run_dir` is present) [Agent 3 finding]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `action_stall` section (~:465), document per-run scoping

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — evaluator table row `action_stall` (~:420) says only "file-backed, no git required"; note per-run/per-state scoping [Agent 2 finding]
- `docs/reference/API.md` — `EvaluateConfig` listing (~:6086, ~:6113) lists type/fields only, not the function signature; update only if it documents `evaluate_action_stall` params [Agent 2 + 3 finding]
- `docs/reference/EVENT-SCHEMA.md` — `action_stall` evaluator detail fields (~:315-332); unchanged as long as `details` keys stay stable [Agent 2 finding]
- `scripts/little_loops/fsm/evaluators.py::evaluate_diff_stall` docstring — says state lives in "/tmp" but writes `.loops/tmp`; fix in passing (already noted in research findings) [Agent 2 finding]

### Configuration
- N/A — wiring pass confirmed no changes needed to `fsm-loop-schema.json`, `schema.py` (`EvaluateConfig`), `validation/structural_rules.py`, `validation/_base.py`, `cli/loop/info.py`, `.gitignore` (blanket `.loops/tmp/` entry), or any hook/scratch-cleanup script (they touch only `.loops/tmp/scratch`). No loop YAML, hook, skill or command references `ll-action-stall-*` files.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **No shared helper exists yet — BUG-3627 is still open** (corrected 2026-09-27). The shell-based `stall_check` state in `scripts/little_loops/loops/continue-task.yaml` (`${context.run_dir}/stall-counter.txt`, `stall-fingerprint.txt`) is FEAT-3594's loop-local replacement, not BUG-3627's fix. The Python `evaluate_diff_stall` is unchanged and still cwd-scoped, and `evaluators.py` has no shared stall-state helper (each evaluator inlines the md5-key + `.txt`/`.count` logic). BUG-3627 now specifies `_stall_state_paths`, which this issue reuses (`depends_on: BUG-3627`).
- **Convention: per-run scoping is done by path default, not by evaluator identity.** `score_stall` / `open_question_stall` resolve `history_file` (default `${context.run_dir}/.score_history` / `.open_questions_history`) in the `evaluate()` dispatch (`evaluators.py` ~:2018-2042); the evaluator functions only read it and the loop writes it. Those two have no `.loops/tmp` fallback (an unresolved `${context.run_dir}` degrades to an empty-history `yes`). `action_stall` is the writer of its own state, so it needs both a run-scoped directory and a fallback for `cmd_test`.
- `run_dir` origin: `cli/loop/run.py` injects `fsm.context["run_dir"]`; `cli/loop/testing.py::cmd_simulate` sets `<loops_dir>/runs/<loop>-simulate/`; `cmd_test` passes a bare `InterpolationContext()` (no `run_dir`, empty `state_name`) and must keep working via the legacy path. `run_dir` elsewhere is read with a `""` default and treated as absent when empty (`persistence.py`, `executor.py`).
- `"action_stall"` is in `_EXIT_CODE_AWARE_EVALUATORS`; `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`, plus `repeated_hash` on `no`) are documented in `docs/reference/EVENT-SCHEMA.md:315-332` and must stay stable.
- Only `evaluate()` calls `evaluate_action_stall` in production; other references: `scripts/tests/test_grader_coverage.py` (by name), `fsm/schema.py`, `fsm/fsm-loop-schema.json`, `validation/structural_rules.py`, `validation/_base.py`. No YAML under `scripts/little_loops/loops/` uses `type: action_stall`.
- **Tests**: `TestActionStallEvaluator` (`test_fsm_evaluators.py` ~:2117) and `TestDiffStallEvaluator` (~:1843) share an autouse `clean_state_files` fixture that isolates via `monkeypatch.chdir(tmp_path)`; `_ctx()` sets only `ctx.context["action"]` (no `run_dir`), so existing tests exercise the fallback path and must keep passing unchanged. `test_first_call_resets_stale_count_file` (~:1987) pins the diff_stall file naming `ll-diff-stall-<md5("_root_")[:12]>.count`. No existing test uses two run_dirs, two states, or a parent/child sharing one cwd; `test_dispatch_defaults_to_run_dir_history` (~:2100) and `test_fsm_open_question_stall.py:119` show the `InterpolationContext(context={"run_dir": str(tmp_path)})` idiom.
- **Docs**: `AUTOMATIC_HARNESSING_GUIDE.md:465-493` (`action_stall`) and the `diff_stall` section above it are silent on state location; `LOOPS_GUIDE.md:420` says only "file-backed, no git required". No doc names the `ll-action-stall-*` files. Docstring inconsistencies: `evaluate_action_stall` claims independent counters per state/loop; `evaluate_diff_stall` says state lives in "/tmp" but writes `.loops/tmp`.

## Implementation Steps

1. After BUG-3627 lands `_stall_state_paths` (or in the same change), add `state_dir` / `state_name` / `loop_name` params to `evaluate_action_stall` and key files `ll-action-stall-<loop_name>-<state_name>-<md5(track)[:12]>` via the helper.
2. Derive `state_dir` from `context.context["run_dir"]` in the `evaluate()` `action_stall` branch, falling back to `.loops/tmp` when absent; fix the docstring.
3. Update existing action_stall tests and add cases for sequential runs, same-`track` states in one run, shared parent/child `run_dir`, and missing `run_dir`.
4. Run `python -m pytest scripts/tests/test_fsm_evaluators.py` and `ll-loop validate` on a sample loop.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- In the `evaluate()` `action_stall` branch, read `state_name` from `context.state_name` (no new `evaluate()` parameter; `FSMExecutor._evaluate` already populates it) and `run_dir` from `context.context.get("run_dir", "")`, treating empty as absent
- Update `scripts/little_loops/cli/loop/testing.py` — fix the `cmd_test` docstring (~:189); decide whether `cmd_simulate`'s fixed `runs/<loop>-simulate/` dir should clear stall files between invocations
- Update `scripts/tests/test_fsm_evaluators.py` — extend `_ctx()` for `run_dir`/`state_name`, add dispatch tests with `run_dir`, promote spike tests (drop the import-guard test)
- Add executor-level two-run test in `scripts/tests/test_fsm_executor.py`
- Update `docs/guides/LOOPS_GUIDE.md` (~:420) alongside `AUTOMATIC_HARNESSING_GUIDE.md`

## Impact

- **Priority**: P4 — no built-in loop uses it; false stall verdicts only in user loops.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- Two sequential runs do not share stall state; a fresh run's first check returns `yes`.
- Two states with the same `track` in one run, and a parent/child sharing `run_dir`, do not share stall state, **including a parent and child that both use the same state name**.
- State files in `run_dir` carry the `ll-action-stall-` prefix and come from BUG-3627's shared `_stall_state_paths` helper; an empty `state_name` does not produce a bare `-<key>` file name.
- Missing `run_dir` falls back to `.loops/tmp` without raising.
- The docstring states the accepted limitations (re-entered child loop, `ll-loop simulate` fixed run dir).
- Existing `action_stall` evaluator tests updated; new tests cover each case.

## Related

- BUG-3627 — same defect in `diff_stall`; source of this split.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Spike Results

_Added by `/ll:spike` on 2026-09-26_

**Retired risks**

| Risk (standalone analysis of Proposed Solution) | Proven by | Result |
|--------------------------------------------------|-----------|--------|
| Sequential runs share state via cwd `.loops/tmp` | `test_sequential_runs_do_not_share_state` | ✓ pass |
| Same-`track` states in one run collide | `test_same_track_states_in_one_run_isolated` | ✓ pass |
| Parent/child sharing `run_dir` collide (state name must be in key) | `test_parent_child_sharing_run_dir_isolated` | ✓ pass |
| Missing `run_dir` fallback (`cmd_test`) | `test_missing_run_dir_falls_back_to_cwd_loops_tmp` | ✓ pass |
| Stall yes/yes/no semantics preserved | `test_stall_semantics_preserved` | ✓ pass |

**Spike location**: `scripts/tests/spike/action_stall_run_scope/` (plan: `.ll/spikes/spike-BUG-3629.md`)
**Verification**: 7 spike tests (incl. 2 guards) + 291 `test_fsm_evaluators.py` tests pass across 2 commands.
**Promotion**: fold into `evaluate_action_stall` under `project.src_dir` and its test under `project.test_dir`, in a separate PR.

## Session Log
- `/ll:confidence-check` - 2026-09-27T04:52:55 - `27697508-48d3-40e3-be84-6db81402352c.jsonl`
- `/ll:wire-issue` - 2026-09-27T04:50:04 - `cedcb440-51cb-42b2-9a38-b12a6ea640a7.jsonl`
- `/ll:spike` - 2026-09-27T04:46:25 - `a9f61bee-9049-4d2c-bd00-adce91a7501c.jsonl`
- `/ll:refine-issue` - 2026-09-27T04:35:38 - `7d85ed80-1899-46ba-9e99-00eacba73eb5.jsonl`
- `/ll:format-issue` - 2026-09-27T04:32:29 - `79da1788-ca93-44d9-aace-4d2e47c2197b.jsonl`
- `/ll:capture-issue` - 2026-09-27T04:30:00 - `1a55a3cf-a3d0-4f25-8b08-d58a3a50c7bc.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate_action_stall()`
- **Cause**: the state-file key is `md5("|".join(sorted(effective_track)))[:12]` and the directory is `Path.cwd() / ".loops" / "tmp"`; `run_dir`, loop name and state name never enter the path. Files `ll-action-stall-<key>.txt` / `.count` are never deleted or reset at run start, so a later run's first check compares against the previous run's last hash and count. `context` is used only to resolve tracked values, never for scoping.
- The `evaluate()` `action_stall` branch calls `evaluate_action_stall(track=config.track, max_repeat=config.max_repeat, context=context)`. `FSMExecutor._evaluate` passes a full `InterpolationContext` (`state_name=self.current_state`, `loop_name=self.fsm.name`, `context=self.fsm.context` incl. `run_dir`), so the identity is already available in the evaluator without a new `evaluate()` parameter. The `StateConfig` itself is not passed.
- Sub-loops inherit the parent's `run_dir` (`child_fsm.context.setdefault("run_dir", ...)` in the executor), so `run_dir` alone does not separate parent and child states with the same `track`; the state name must be part of the key too.
