---
id: BUG-2832
type: BUG
title: "input_hash never injected for sub-loops — general-task always fails as a sub-loop"
priority: P1
status: open
captured_at: '2026-07-26T18:09:17Z'
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

## Proposed Solution

Move (or duplicate) the `input_hash` derivation into the sub-loop spawn path so every child executor gets it:

1. In `_execute_sub_loop`, after resolving the child context, apply the same derivation: if `input_hash` absent and `input` is a str, set `input_hash = sha256(input)[:12]`.
2. Prefer extracting a shared helper (e.g. `inject_runner_context(fsm)` in `fsm/` used by both `cli/loop/run.py` and `_execute_sub_loop`) so the `RUNNER_INJECTED` contract in `validation.py:609` has a single implementation to drift-check against.
3. Defensively, `general-task.yaml` could also use `${context.input_hash:default=}` at lines 114/189, but the primary fix is the executor injection — other loops referencing runner-injected vars would otherwise hit the same class of bug.

## Steps to Reproduce

1. `ll-loop run proof-first-task --context issue_file=<any issue path> --context targets_csv=anthropic`
2. Observe `general-task` (the `run_impl` child) fail at iteration 5 (`resume_check` → `diagnose` → `failed`) with all plan steps unchecked.
3. `sqlite3 .ll/history.db "select final_state, iterations from loop_runs where loop_name='general-task' order by started_at desc limit 5"` → all `failed|5`.

## Acceptance Criteria

- [ ] `_execute_sub_loop` injects `input_hash` into the child context (derived from the child's resolved `input`, matching the top-level derivation in `cli/loop/run.py`)
- [ ] The derivation logic is shared (single helper) between the CLI entry and the sub-loop spawn path
- [ ] A unit test in `scripts/tests/test_fsm_executor.py` asserts a sub-loop child context contains `input_hash` and that a child state interpolating `${context.input_hash}` executes without an interpolation error
- [ ] `general-task` invoked as a sub-loop progresses past `resume_check` (integration-level test or targeted executor test with a minimal child loop referencing `${context.input_hash}`)
- [ ] `python -m pytest scripts/tests/` passes with no new failures

## Session Log
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`
