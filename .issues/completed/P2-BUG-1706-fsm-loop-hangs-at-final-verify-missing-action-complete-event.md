---
id: BUG-1706
title: FSM loop hangs at final_verify when action_complete event is never emitted
type: BUG
status: done
priority: P2
captured_at: '2026-05-25T23:53:17Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
labels:
- bug
- ll-loop
- fsm
- captured
confidence_score: 100
outcome_confidence: 69
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# BUG-1706: FSM loop hangs at final_verify when action_complete event is never emitted

## Summary

The `general-task` FSM loop enters `final_verify`, the LLM completes all work (36/36 DoD criteria verified, Final Verification section written), but never emits an `action_complete` event. The FSM stalls indefinitely — the 1800s LLM timeout expired 33+ minutes ago with no kill or retry triggered, leaving the process running but fully idle with completed work trapped inside.

## Current Behavior

1. Loop enters `final_verify` state (23:09:48 UTC)
2. LLM finishes all verification work by 23:13:54 UTC (all 36 DoD criteria re-verified, Final Verification section written to DoD file)
3. No `action_complete` event is emitted
4. FSM waits for `action_complete` → `count_final` transition that never fires
5. Process remains alive and idle 33+ minutes past the 1800s LLM timeout with no kill, retry, or alert

**Expected path:** `final_verify --next--> count_final --yes--> done` (terminal)

**Actual path:** `final_verify` → stalled forever

## Expected Behavior

When the LLM in `final_verify` finishes its task, it should emit `action_complete` so the FSM advances to `count_final` and then `done`. If that event is not emitted within the configured LLM timeout (1800s), the runner should either:
- Kill the idle process (and optionally emit a `timeout` event to trigger recovery), or
- Retry the state, or
- Alert the operator

## Motivation

Work is fully complete but the loop never reaches the terminal `done` state. The result: the operator must manually inspect and kill the process; log artifacts may remain unclosed; any downstream trigger on `done` (notifications, post-loop hooks) never fires. This is a silent failure — the loop appears alive until the operator notices it hasn't progressed.

## Steps to Reproduce

1. Run a `general-task` loop (or similar) with a `final_verify` state that uses `ll_structured` or similar LLM action
2. Have the LLM complete all verification work successfully
3. Observe that the LLM response does not include the `action_complete` event token/signal
4. Observe FSM stalls; wait for LLM timeout to expire; confirm process is not killed

## Root Cause

Two distinct gaps combine to produce this failure:

**Gap 1 — Missing `action_complete` emission (primary):**
- **File**: loop YAML / LLM prompt for `final_verify` state
- **Anchor**: `final_verify` state definition, LLM prompt text
- **Cause**: The LLM prompt for `final_verify` either does not instruct the model to emit `action_complete`, or the model fails to include it in its output. Without the signal, the FSM routing finds no matching event and idles.

**Gap 2 — No liveness enforcement after LLM timeout (secondary):**
- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `FSMExecutor._run_subprocess()`, `FSMExecutor._execute_state()`
- **Cause**: The per-state timeout (`state.timeout or fsm.default_timeout`) should hard-kill the subprocess, but the runner did not kill the process, retry the state, or fire a recovery transition. The `final_verify` state uses `next: count_final` (unconditional), so the FSM `action_complete` event fires only when the subprocess exits — if the subprocess hangs after writing output, no transition ever fires.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`action_complete` is not a routing trigger.** `FSMExecutor._run_action()` (`executor.py` ~line 1007) emits `action_complete` unconditionally after `self.action_runner.run(...)` returns — it is a pure observability event consumed by `display_progress` in `_helpers.py`. The FSM transition from `final_verify` → `count_final` fires when `_run_action()` returns, not when `action_complete` is parsed from LLM output. If `action_runner.run()` never returns (subprocess hangs), `action_complete` is never emitted and the FSM stalls — matching the observed behavior exactly.

**The true failure mode (Gap 2, primary):** The Claude CLI subprocess writes all output, then hangs with stdout still open (never calls `close()`). `run_claude_command()` in `subprocess_utils.py` drives a `selectors`-based loop that blocks in `readline()` waiting for the next line. An `idle_timeout` parameter exists in `run_claude_command()` that would kill the process after N seconds of no output — but `DefaultActionRunner.run()` in `runners.py` never passes `idle_timeout` for the `prompt` action type branch. It is only wired in `scripts/little_loops/parallel/worker_pool.py`.

**Effective timeout for `final_verify` is 3600 seconds (not 1800s).** `FSMExecutor._run_action()` resolves timeout as `state.timeout or self.fsm.default_timeout or 3600`. Neither `final_verify.timeout` nor a top-level `default_timeout:` is set in `general-task.yaml`, so the fallback is 3600s. The "1800s" figure in the incident report likely reflects a runtime config override or elapsed wall-clock before the operator noticed.

**The FSM-level `timeout:` field cannot interrupt in-progress actions.** The wall-clock check in `FSMExecutor.run()` only fires between iterations — while `_execute_state()` is blocked inside `action_runner.run()`, the FSM-level guard is frozen. `general-task.yaml` sets no loop-level `timeout:` either.

**Gap 1 is secondary.** `action_complete` is not a signal the LLM must emit; the LLM just needs to cause the subprocess to exit. If the subprocess exits cleanly (exit 0), `_run_action()` returns, emits `action_complete`, and the `next: count_final` unconditional path fires. Gap 1 (prompt doesn't instruct clean exit) may be a contributing factor but Gap 2 (`idle_timeout` not wired) is the architectural gap that leaves any hung subprocess undetected.

## Proposed Solution

1. **Audit `final_verify` (and similar terminal-adjacent) state prompts** to ensure `action_complete` is explicitly required in the model's output format.
2. **Enforce LLM timeout kill/retry in the runner**: when a state's wall-clock time exceeds `llm_timeout`, the runner should kill the blocking subprocess and either retry the state (up to a configured max) or transition via a `timeout` event to a recovery/failure state.
3. **Add a liveness watchdog**: a lightweight background monitor that fires an alert or transition when a state has been idle longer than `llm_timeout * N`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `final_verify` state: audit prompt to ensure clean subprocess exit; the state uses `next: count_final` (unconditional) so the FSM `action_complete` event fires only when the subprocess exits; add `default_timeout:` at loop level (e.g., `1800`) to avoid the 3600s fallback
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` (prompt branch, lines ~101–117): wire `idle_timeout` parameter into `run_claude_command()` call so a subprocess that writes output but hangs without closing stdout is killed after N seconds of silence; expose `idle_timeout` as a parameter on `run()` itself; also update `SimulationActionRunner.run()` to add `idle_timeout: int = 0` to its signature (Protocol conformance — currently accepts the same parameters as the Protocol, so adding `idle_timeout` to the Protocol requires matching it here) [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` (lines ~973–1007): accept and forward `idle_timeout` to `action_runner.run()`; resolve it from `state.idle_timeout or self.fsm.default_idle_timeout or 0`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` dataclass: add `default_idle_timeout: int | None = None` field; `FSMState` dataclass: add `idle_timeout: int | None = None` field; update `from_dict()` / `to_dict()` on both classes (add `data.get("idle_timeout")` / `data.get("default_idle_timeout")` and corresponding `if self.X is not None` serialization guards)
- `scripts/little_loops/fsm/validation.py` — **CRITICAL**: add `"default_idle_timeout"` to `KNOWN_TOP_LEVEL_KEYS` frozenset (without this `ll-loop validate` emits "Unknown top-level key" warnings for any loop YAML using the new field); also add a non-negative range check in `validate_fsm()` for `fsm.default_idle_timeout` and `state.idle_timeout` following the existing `if fsm.timeout is not None and fsm.timeout <= 0` pattern [Agent 2 finding]
- `scripts/little_loops/loops/eval-driven-development.yaml` — unprotected prompt states (`route_eval`, `commit_impl`, `commit_eval`, `tradeoff_review`) have no `timeout:` and the loop has no `default_timeout:`; add `default_timeout:` or per-state `timeout:` to protect against indefinite hangs [Agent 2 finding]
- `scripts/little_loops/loops/harness-multi-item.yaml` — `execute` state (prompt type) has no `timeout:` despite loop having `timeout: 14400` (loop-level timeout only fires between iterations, not inside a blocking action); add per-state `timeout:` to `execute` [Agent 2 finding]
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` — `check-quality` state (prompt type) has no `timeout:` while all other states have explicit timeouts; add per-state `timeout:` [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` — invokes `FSMExecutor`
- `scripts/little_loops/cli/loop/testing.py` — test runner that also constructs `FSMExecutor`
- `scripts/little_loops/parallel/worker_pool.py` — only existing caller that wires `idle_timeout` into `run_claude_command()`; pattern to follow for the FSM runner path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — constructs `PersistentExecutor` (lines ~344, 356); CLI entry point for `ll-loop run`; drives the full execution chain through `_helpers.run_foreground()` [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `PersistentExecutor`, manages resumable executor state (`StatePersistence`); invoked by resume/pause subcommands [Agent 1 finding]
- `scripts/little_loops/fsm/types.py` — defines the `ActionRunner` Protocol; adding `idle_timeout` kwarg to `DefaultActionRunner.run()` requires updating the Protocol signature here so all conforming implementations are also updated [Agent 2 finding]
- `scripts/little_loops/fsm/persistence.py` — manages `PersistentExecutor` and loop state serialization; ensure `idle_timeout` fields survive state round-trips if persisted [Agent 1 finding]

### Similar Patterns
- Other loops with terminal-adjacent LLM states: `scripts/little_loops/loops/eval-driven-development.yaml`, `scripts/little_loops/loops/harness-multi-item.yaml`, `scripts/little_loops/loops/apo-textgrad.yaml`
- `scripts/little_loops/loops/general-task.yaml` (confirmed affected)
- Per-state timeout examples to follow: `scripts/little_loops/loops/fix-quality-and-tests.yaml` (states with explicit `timeout: 300/600/1800`)
- Related prior fixes: BUG-718 (negative-exit-code routing in `state.next` branch, `executor.py:_execute_state()` lines 819–826); BUG-583 (added `timeout: 1200` to a stuck state)

### Tests
- `scripts/tests/test_fsm_executor.py` — add test for timeout-kill enforcement when subprocess hangs past per-state deadline; also update `MockActionRunner.run()`, `ShutdownAfterFirstActionRunner.run()`, `CaptureAndShutdownRunner.run()`, `FailingRunner.run()`, and `TestDefaultTimeout.TimeoutCapturingRunner.run()` — all have explicit Protocol signatures that will fail mypy once `idle_timeout` is added to the Protocol
- `scripts/tests/test_ll_loop_execution.py` — add integration test for subprocess that completes output but never exits; update `make_test_state()` (add `idle_timeout: int | None = None` param) and `make_test_fsm()` (add `default_idle_timeout: int | None = None` param)
- `scripts/tests/test_general_task_loop.py` — existing general-task loop tests to update/extend; add assertion that `raw_data.get("default_timeout") == 1800` after the YAML change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` — two inline `ActionRunner.run()` implementations at lines ~610 and ~1826 have explicit Protocol signatures (without `**kwargs`); they will fail mypy once `idle_timeout` is added to the Protocol — add `idle_timeout: int = 0` to each [Agent 2 + 3 finding]
- `scripts/tests/test_fsm_schema.py` — add `from_dict`/`to_dict` round-trip tests in `TestFSMLoopSerialization` (for `default_idle_timeout`) and `TestStateConfigSerialization` (for `idle_timeout`), following the existing `test_roundtrip_serialization` pattern in those classes [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` — `TestRunClaudeCommandIdleTimeout` class (lines ~1009–1173) is the reference pattern to follow for new `idle_timeout` enforcement tests in `test_fsm_executor.py`; no changes needed here but must be referenced in implementation [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — loop config `llm_timeout` semantics; also update `#### FSMLoop` section (add `default_idle_timeout` field) and `#### StateConfig` section (add `idle_timeout` field) — currently `default_timeout` is also missing from the FSMLoop block, so patch both gaps together

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — **`# Optional Loop-Level Settings`** reference block: add `default_idle_timeout: number` entry alongside `default_timeout: number`; **`## Timeouts`** section: document the new idle-timeout mechanism as distinct from wall-clock `timeout` (idle fires when subprocess produces no output for N seconds, wall-clock fires regardless); per-state schema block: add `idle_timeout: number` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — authoring tip section that mentions `default_timeout` in MCP-heavy execute states context (~line 2888): add a note that `idle_timeout` is the correct mechanism for terminal-adjacent states where the subprocess may hang after writing all output [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — similarly mentions `default_timeout` (~line 713): add `idle_timeout` authoring tip for execute states [Agent 2 finding]

### Configuration
- Loop YAML: per-state `state.timeout` / `fsm.default_timeout` (was 1800s in the affected run)

## Implementation Steps

1. **Reproduce**: create a minimal loop with a `final_verify` state that uses `action_type: prompt`; mock a subprocess that writes output but never closes stdout; confirm `_run_action()` blocks indefinitely (no `idle_timeout` wired)
2. **Add schema fields** (`scripts/little_loops/fsm/schema.py`): add `idle_timeout: int | None = None` to `FSMState` and `default_idle_timeout: int | None = None` to `FSMLoop`
3. **Wire `idle_timeout` in runner** (`scripts/little_loops/fsm/runners.py:DefaultActionRunner.run()`, prompt branch ~lines 101–117): accept `idle_timeout` kwarg and pass it to `run_claude_command(idle_timeout=idle_timeout)`; follow the pattern in `scripts/little_loops/parallel/worker_pool.py` (the only existing caller)
4. **Forward `idle_timeout` from executor** (`scripts/little_loops/fsm/executor.py:FSMExecutor._run_action()`, ~line 990): resolve `idle_timeout = state.idle_timeout or self.fsm.default_idle_timeout or 0`; pass to `self.action_runner.run(..., idle_timeout=idle_timeout)`
5. **Fix `general-task.yaml`**: add `default_timeout: 1800` at the loop level (currently absent — effective timeout is 3600s fallback); optionally add `idle_timeout: 300` on `final_verify` state directly
6. **Add regression tests**:
   - `scripts/tests/test_fsm_executor.py` (`TestTimeoutHandling`): test that `_run_action()` passes `idle_timeout` to runner; use `MockActionRunner`; follow existing patterns at lines 1944–2136
   - `scripts/tests/test_ll_loop_execution.py`: integration test for a prompt-type state whose subprocess writes output then hangs — confirm kill after `idle_timeout`
   - Model after `scripts/tests/test_subprocess_utils.py:TestRunClaudeCommandIdleTimeout` for the subprocess-level kill assertion pattern
7. **Audit peer terminal-adjacent states** in `eval-driven-development.yaml`, `harness-multi-item.yaml`, `apo-textgrad.yaml` — add per-state or loop-level `default_timeout:` where absent

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/fsm/validation.py` → add `"default_idle_timeout"` to `KNOWN_TOP_LEVEL_KEYS` frozenset; add non-negative range check in `validate_fsm()` for `fsm.default_idle_timeout` and `state.idle_timeout` (prevents silent acceptance of negative values)
9. Update `scripts/little_loops/fsm/runners.py` → add `idle_timeout: int = 0` to `SimulationActionRunner.run()` signature to maintain Protocol conformance after the Protocol gains the new parameter
10. Update `scripts/little_loops/fsm/schema.py` → also add `from_dict()`/`to_dict()` round-trip handling for both new fields (not just the dataclass field declarations)
11. Update test runner signatures in `scripts/tests/test_fsm_executor.py` (`MockActionRunner`, `ShutdownAfterFirstActionRunner`, `CaptureAndShutdownRunner`, `FailingRunner`, `TimeoutCapturingRunner`) and `scripts/tests/test_fsm_persistence.py` (lines ~610, ~1826) — all have explicit Protocol signatures that will fail mypy
12. Add round-trip tests in `scripts/tests/test_fsm_schema.py` → `TestFSMLoopSerialization` and `TestStateConfigSerialization` for the new fields (follow the existing `test_roundtrip_serialization` pattern)
13. Add per-state `timeout:` to `check-quality` in `fix-quality-and-tests.yaml` and `execute` in `harness-multi-item.yaml`; add `default_timeout:` to `eval-driven-development.yaml`
14. Update `docs/generalized-fsm-loop.md`, `docs/guides/LOOPS_GUIDE.md`, and `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` with `idle_timeout` / `default_idle_timeout` documentation

## Impact

- **Priority**: P2 — significant; work completes but the loop silently hangs; operator intervention required; downstream hooks never fire
- **Effort**: Medium — prompt fix is small; runner timeout enforcement is moderate; watchdog is optional follow-on
- **Risk**: Low/Medium — timeout enforcement changes runner behavior; needs care to not kill legitimately long-running states
- **Breaking Change**: No (fixing a hang is not a breaking change; timeout enforcement is additive behavior)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `fsm`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-25_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- **~18-site enumeration breadth** — the change is mechanical to local at each site, but spans 18+ files (schema, runner, executor, validation, Protocol, 4 YAML loops, 5 test files, 3 docs); execute against the implementation step checklist in order and verify no site is skipped
- **Protocol conformance sweep across 7 mock runners** — adding `idle_timeout` to `ActionRunner` Protocol requires updating `MockActionRunner`, `ShutdownAfterFirstActionRunner`, `CaptureAndShutdownRunner`, `FailingRunner`, `TimeoutCapturingRunner` in `test_fsm_executor.py` plus 2 inline runners in `test_fsm_persistence.py` (~lines 610, 1826); any missed signature fails mypy; run `python -m mypy scripts/little_loops/` after each runner update to catch misses early

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-25
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- BUG-1723: Wire idle_timeout through FSM schema, Protocol, runner, and executor to kill hung subprocesses
- BUG-1724: Audit and fix missing default_timeout in FSM loop YAMLs to prevent indefinite hangs

## Session Log
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ec7ab86-eac4-42cb-b06f-00661e557291.jsonl`
- `/ll:confidence-check` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9a0ee27-f874-487c-b607-ea72efb6da24.jsonl`
- `/ll:wire-issue` - 2026-05-26T02:42:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23f61094-2a86-4174-a9e8-1ef35d1be50b.jsonl`
- `/ll:refine-issue` - 2026-05-26T02:33:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/61a97210-bdd9-4d12-b14a-ccdea70162b4.jsonl`
- `/ll:format-issue` - 2026-05-26T01:45:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fa4ab33-784c-4215-956e-0cb379a1456c.jsonl`
- `/ll:capture-issue` - 2026-05-25T23:53:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6beeb46c-ca56-4385-8e86-f1d1ac1a4edf.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P2
