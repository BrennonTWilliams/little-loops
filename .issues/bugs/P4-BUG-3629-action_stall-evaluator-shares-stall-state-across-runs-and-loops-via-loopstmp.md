---
id: BUG-3629
type: BUG
title: action_stall evaluator shares stall state across runs and loops via .loops/tmp
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T04:29:54Z'
spike_attempted: true
spike_completed: true
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

- Derive `state_dir` from `context.context["run_dir"]` (the function already receives `context`), keying files `<state_name>-<md5(track)[:12]>`; fall back to the current `.loops/tmp` path only when no run context exists (`cli/loop/testing.py::cmd_test` passes a bare `InterpolationContext()`).
- Keep `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`) unchanged.
- Correct the docstring ("different states/loops maintain independent stall counters").
- Coordinate with BUG-3627 so both evaluators share one state-dir/key helper rather than duplicating it.

## Program Design

### Types

- `state_dir: Path | None` — per-run directory for snapshot/count files; `None` keeps the legacy `.loops/tmp` location
- `state_name: str` — state identifier used as the file-key prefix

### Signatures

- `evaluate_action_stall(track: list[str] | None = None, max_repeat: int = 2, context: InterpolationContext | None = None, state_dir: Path | None = None, state_name: str = "") -> EvaluationResult` — state files keyed `<state_name>-<md5(sorted track)[:12]>`; `details` keys unchanged

### Call Path

`evaluate` (`elif eval_type == "action_stall"` branch) -> `evaluate_action_stall(..., state_dir=<context.context["run_dir"]>)` -> `EvaluationResult` verdict `yes` / `no` -> state routing

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_action_stall()` (state path, docstring) and the `evaluate()` `action_stall` branch (~:2044) that derives `state_dir` from `context.context["run_dir"]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test` passes a bare `InterpolationContext()` (must hit the `.loops/tmp` fallback)
- `scripts/little_loops/fsm/schema.py` — `track` / `max_repeat` evaluator fields (unchanged)

### Similar Patterns
- `evaluate_diff_stall()` (BUG-3627), `evaluate_score_stall`, `evaluate_open_question_stall` — `run_dir`-scoped state; share one state-dir/key helper with BUG-3627

### Tests
- `scripts/tests/test_fsm_evaluators.py` — action_stall test class (~:2118); its `clean_state_files` fixture relies on cwd `.loops/tmp`, add run_dir cases

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `action_stall` section (~:465), document per-run scoping

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **BUG-3627 did not produce a shared helper.** Its fix landed as a shell-based `stall_check` state in `scripts/little_loops/loops/continue-task.yaml` (`${context.run_dir}/stall-counter.txt`, `stall-fingerprint.txt`); the Python `evaluate_diff_stall` is unchanged and still cwd-scoped, and `evaluators.py` has no shared stall-state helper (each evaluator inlines the md5-key + `.txt`/`.count` logic). The "share one state-dir/key helper with BUG-3627" constraint therefore has nothing to reuse today; a shared helper would have to be introduced (and `diff_stall`, still used via the `diff_stall_gate` fragment in `loops/lib/common.yaml`, has the same defect).
- **Convention: per-run scoping is done by path default, not by evaluator identity.** `score_stall` / `open_question_stall` resolve `history_file` (default `${context.run_dir}/.score_history` / `.open_questions_history`) in the `evaluate()` dispatch (`evaluators.py` ~:2018-2042); the evaluator functions only read it and the loop writes it. Those two have no `.loops/tmp` fallback (an unresolved `${context.run_dir}` degrades to an empty-history `yes`). `action_stall` is the writer of its own state, so it needs both a run-scoped directory and a fallback for `cmd_test`.
- `run_dir` origin: `cli/loop/run.py` injects `fsm.context["run_dir"]`; `cli/loop/testing.py::cmd_simulate` sets `<loops_dir>/runs/<loop>-simulate/`; `cmd_test` passes a bare `InterpolationContext()` (no `run_dir`, empty `state_name`) and must keep working via the legacy path. `run_dir` elsewhere is read with a `""` default and treated as absent when empty (`persistence.py`, `executor.py`).
- `"action_stall"` is in `_EXIT_CODE_AWARE_EVALUATORS`; `details` keys (`stall_count`, `max_repeat`, `hash_changed`, `tracked_keys`, plus `repeated_hash` on `no`) are documented in `docs/reference/EVENT-SCHEMA.md:315-332` and must stay stable.
- Only `evaluate()` calls `evaluate_action_stall` in production; other references: `scripts/tests/test_grader_coverage.py` (by name), `fsm/schema.py`, `fsm/fsm-loop-schema.json`, `validation/structural_rules.py`, `validation/_base.py`. No YAML under `scripts/little_loops/loops/` uses `type: action_stall`.
- **Tests**: `TestActionStallEvaluator` (`test_fsm_evaluators.py` ~:2117) and `TestDiffStallEvaluator` (~:1843) share an autouse `clean_state_files` fixture that isolates via `monkeypatch.chdir(tmp_path)`; `_ctx()` sets only `ctx.context["action"]` (no `run_dir`), so existing tests exercise the fallback path and must keep passing unchanged. `test_first_call_resets_stale_count_file` (~:1987) pins the diff_stall file naming `ll-diff-stall-<md5("_root_")[:12]>.count`. No existing test uses two run_dirs, two states, or a parent/child sharing one cwd; `test_dispatch_defaults_to_run_dir_history` (~:2100) and `test_fsm_open_question_stall.py:119` show the `InterpolationContext(context={"run_dir": str(tmp_path)})` idiom.
- **Docs**: `AUTOMATIC_HARNESSING_GUIDE.md:465-493` (`action_stall`) and the `diff_stall` section above it are silent on state location; `LOOPS_GUIDE.md:420` says only "file-backed, no git required". No doc names the `ll-action-stall-*` files. Docstring inconsistencies: `evaluate_action_stall` claims independent counters per state/loop; `evaluate_diff_stall` says state lives in "/tmp" but writes `.loops/tmp`.

## Implementation Steps

1. Land or reuse the shared state-dir/key helper from BUG-3627, then add `state_dir` / `state_name` params to `evaluate_action_stall` and key files `<state_name>-<md5(track)[:12]>`.
2. Derive `state_dir` from `context.context["run_dir"]` in the `evaluate()` `action_stall` branch, falling back to `.loops/tmp` when absent; fix the docstring.
3. Update existing action_stall tests and add cases for sequential runs, same-`track` states in one run, shared parent/child `run_dir`, and missing `run_dir`.
4. Run `python -m pytest scripts/tests/test_fsm_evaluators.py` and `ll-loop validate` on a sample loop.

## Impact

- **Priority**: P4 — no built-in loop uses it; false stall verdicts only in user loops.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- Two sequential runs do not share stall state; a fresh run's first check returns `yes`.
- Two states with the same `track` in one run, and a parent/child sharing `run_dir`, do not share stall state.
- Missing `run_dir` falls back to `.loops/tmp` without raising.
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
