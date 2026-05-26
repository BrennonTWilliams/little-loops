---
id: BUG-1723
title: Wire idle_timeout through FSM schema, Protocol, runner, and executor to kill
  hung subprocesses
type: BUG
status: open
priority: P2
parent: BUG-1706
size: Very Large
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-1723: Wire idle_timeout through FSM schema, Protocol, runner, and executor to kill hung subprocesses

## Summary

The FSM runner has no mechanism to kill a Claude CLI subprocess that writes all its output then hangs with stdout open indefinitely. `run_claude_command()` already has an `idle_timeout` parameter, but `DefaultActionRunner.run()` never passes it for prompt-type actions. This child implements the full stack wiring: new schema fields → Protocol update → runner → executor → validation → tests → docs.

## Parent Issue

Decomposed from BUG-1706: FSM loop hangs at final_verify when action_complete event is never emitted

## Root Cause (from parent)

`DefaultActionRunner.run()` in `runners.py` (prompt branch, lines ~101–117) never passes `idle_timeout` to `run_claude_command()`. An `idle_timeout` parameter already exists in `run_claude_command()` in `subprocess_utils.py` and is only wired in `scripts/little_loops/parallel/worker_pool.py`. Without it, any prompt-type state whose subprocess writes all output but never closes stdout blocks `FSMExecutor._run_action()` indefinitely.

## Files to Modify

### Schema
- `scripts/little_loops/fsm/schema.py` — add `idle_timeout: int | None = None` to `FSMState`; add `default_idle_timeout: int | None = None` to `FSMLoop`; add `from_dict()`/`to_dict()` round-trip handling for both new fields

### Protocol & Runners
- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol is defined here (lines 28–53), **not** in `types.py`; add `idle_timeout: int = 0` kwarg to Protocol's `run()` signature; `DefaultActionRunner.run()` signature at lines 62–70, prompt branch lines 86–123: accept `idle_timeout` kwarg and forward to `run_claude_command(idle_timeout=idle_timeout)` (call site lines 102–110); add `idle_timeout: int = 0` to `SimulationActionRunner.run()` (lines 192–198) for Protocol conformance

### Executor
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` (~line 990): resolve `idle_timeout = state.idle_timeout or self.fsm.default_idle_timeout or 0`; forward to `self.action_runner.run(..., idle_timeout=idle_timeout)`

### Validation
- `scripts/little_loops/fsm/validation.py` — add `"default_idle_timeout"` to `KNOWN_TOP_LEVEL_KEYS` frozenset; add non-negative range check in `validate_fsm()` for `fsm.default_idle_timeout` and `state.idle_timeout` (follow the existing pattern for `fsm.timeout`)

### Tests
- `scripts/tests/test_fsm_executor.py` — add test for `_run_action()` passing `idle_timeout` to runner; update all Protocol-implementing mocks to add `idle_timeout: int = 0`: `MockActionRunner`, `ShutdownAfterFirstActionRunner`, `CaptureAndShutdownRunner`, `FailingRunner`, `TimeoutCapturingRunner`; follow `TestRunClaudeCommandIdleTimeout` in `test_subprocess_utils.py` as kill-assertion pattern
- `scripts/tests/test_fsm_persistence.py` — add `idle_timeout: int = 0` to two inline `ActionRunner.run()` implementations at lines ~610 and ~1826
- `scripts/tests/test_fsm_schema.py` — add `from_dict`/`to_dict` round-trip tests in `TestFSMLoopSerialization` (for `default_idle_timeout`) and `TestStateConfigSerialization` (for `idle_timeout`), following the existing `test_roundtrip_serialization` pattern
- `scripts/tests/test_ll_loop_execution.py` — integration test for a prompt-type state whose subprocess writes output then hangs; confirm kill after `idle_timeout`
- `scripts/tests/test_fsm_validation.py` — add `test_default_idle_timeout_recognized_as_top_level_key` (follow `test_circuit_recognized_as_top_level_key` pattern at line 609); confirm `load_and_validate()` emits no "Unknown top-level key" warning when a loop YAML includes `default_idle_timeout`
- `scripts/tests/test_learning_state.py` — add `idle_timeout: int = 0` to `_MockRunner.run()` at line 31 for Protocol conformance

### Documentation
- `docs/reference/API.md` — `#### FSMLoop` section: add `default_idle_timeout` field; `#### StateConfig` section: add `idle_timeout` field; also patch missing `default_timeout` in FSMLoop block
- `docs/generalized-fsm-loop.md` — `# Optional Loop-Level Settings`: add `default_idle_timeout: number`; `## Timeouts` section: document idle-timeout as distinct from wall-clock timeout; per-state schema block: add `idle_timeout: number`
- `docs/guides/LOOPS_GUIDE.md` — add authoring tip near `default_timeout` mention (~line 2888): `idle_timeout` is the correct mechanism for terminal-adjacent states
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `idle_timeout` authoring tip near `default_timeout` mention (~line 713)

## Dependent Callers (no changes needed, but verify after implementation)

- `scripts/little_loops/cli/loop/_helpers.py` — invokes `FSMExecutor`
- `scripts/little_loops/cli/loop/run.py` — constructs `PersistentExecutor`
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `PersistentExecutor`
- `scripts/little_loops/fsm/persistence.py` — verify `idle_timeout` fields survive state round-trips

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified line numbers from codebase analysis:_

**Key anchors — files to modify:**
- `scripts/little_loops/fsm/schema.py` — `StateConfig` class (~line 309); existing `timeout: int | None = None` at line 375 (model for `idle_timeout`); `FSMLoop` class (~line 847); `default_timeout` at line 880 (model for `default_idle_timeout`); `StateConfig.to_dict()` skip-if-None at line 425; `FSMLoop.to_dict()` pattern at lines 917–920; `FSMLoop.from_dict()` at line 958
- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol at lines 28–53; `DefaultActionRunner.run()` at lines 62–70; `run_claude_command()` call at lines 102–110; `SimulationActionRunner.run()` at lines 192–198
- `scripts/little_loops/fsm/executor.py` — `_run_action()` call to `self.action_runner.run()` at lines 988–995; existing timeout resolution pattern: `state.timeout or self.fsm.default_timeout or 3600`
- `scripts/little_loops/fsm/validation.py` — `KNOWN_TOP_LEVEL_KEYS` frozenset at lines 100–132; `timeout` range-check pattern at lines 813–819: `if fsm.timeout is not None and fsm.timeout <= 0: errors.append(...)`
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` signature at lines 221–234; `idle_timeout: int = 0` (0 = disabled); raises `subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")` — use the `output="idle_timeout"` sentinel in integration test assertions to distinguish idle-kill from wall-clock kill

**Test mock signatures — 7 locations to add `idle_timeout: int = 0`:**
- `scripts/tests/test_fsm_executor.py:31` — `MockActionRunner.run()` (class-level dataclass)
- `scripts/tests/test_fsm_executor.py:1924` — `FailingRunner.run()` (inline)
- `scripts/tests/test_fsm_executor.py:2359` — `ShutdownAfterFirstActionRunner.run()` (inline)
- `scripts/tests/test_fsm_executor.py:2442` — `CaptureAndShutdownRunner.run()` (inline)
- `scripts/tests/test_fsm_executor.py:3757` — `TestDefaultTimeout.TimeoutCapturingRunner.run()` (nested dataclass)
- `scripts/tests/test_fsm_persistence.py:602` — `MockActionRunner.run()` (class-level)
- `scripts/tests/test_fsm_persistence.py:1823` — `CaptureAndShutdownRunner.run()` (inline)

**Additional test mock signatures — 7 more locations (wiring pass finding):**

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:1882` — `ShutdownAfterFirstRunner.run()` (inline)
- `scripts/tests/test_fsm_persistence.py:1966` — `ProgressTrackingRunner.run()` (inline)
- `scripts/tests/test_fsm_executor.py:2619` — `RaisingRunner.run()` (inline)
- `scripts/tests/test_fsm_executor.py:4516` — `CapturingRunner.run()` (inline, agent/tools test 1)
- `scripts/tests/test_fsm_executor.py:4554` — `CapturingRunner.run()` (inline, agent/tools test 2)
- `scripts/tests/test_fsm_executor.py:6436` — `ProgressRunner.run()` (inline, stall-detector test)
- `scripts/tests/test_learning_state.py:31` — `_MockRunner.run()` (class-level)

**Reference patterns to model after:**
- `scripts/tests/test_subprocess_utils.py:1009` — `TestRunClaudeCommandIdleTimeout`: kill-assertion pattern using `time.time` mock + `mock_process.kill.assert_called_once()` + `assert exc_info.value.output == "idle_timeout"`
- `scripts/tests/test_fsm_schema.py:756` — `TestFSMLoop.test_roundtrip_serialization`: pattern for `default_idle_timeout` round-trip test
- `scripts/tests/test_fsm_schema.py:455` — `TestStateConfig.test_roundtrip_serialization`: pattern for `idle_timeout` round-trip test
- `scripts/tests/test_fsm_schema.py:1512` — `TestFSMValidation.test_timeout_zero_rejected`: pattern for range-check validation tests

## Implementation Steps

1. **Reproduce**: create a minimal loop with `action_type: prompt`; mock a subprocess that writes output but never closes stdout; confirm `_run_action()` (executor.py:988) blocks indefinitely
2. **Add schema fields** (`schema.py`): add `idle_timeout: int | None = None` to `StateConfig` (after line 375 `timeout` field); add `default_idle_timeout: int | None = None` to `FSMLoop` (after line 880 `default_timeout` field); follow skip-if-None pattern in `to_dict()` (lines 425, 917) and `data.get()` pattern in `from_dict()` (lines 518, 958)
3. **Update Protocol** (`runners.py:28–53`): add `idle_timeout: int = 0` kwarg to `ActionRunner.run()` — Protocol is in `runners.py`, not `types.py`
4. **Wire runner** (`runners.py`): `DefaultActionRunner.run()` (lines 62–70): add `idle_timeout: int = 0` param and forward at the `run_claude_command()` call (lines 102–110); same for `SimulationActionRunner.run()` (lines 192–198)
5. **Forward from executor** (`executor.py:988`): resolve `idle_timeout = state.idle_timeout or self.fsm.default_idle_timeout or 0`; add as kwarg to existing `self.action_runner.run(...)` call
6. **Fix validation** (`validation.py`): add `"default_idle_timeout"` to `KNOWN_TOP_LEVEL_KEYS` (lines 100–132); add non-negative range check following the `timeout` pattern (lines 813–819): `if fsm.default_idle_timeout is not None and fsm.default_idle_timeout <= 0`; same for `state.idle_timeout`
7. **Update test mock signatures** (14 locations): add `idle_timeout: int = 0` to each — see Integration Map for the original 7 locations in `test_fsm_executor.py` and `test_fsm_persistence.py`, plus 7 additional locations found by wiring analysis (`test_fsm_persistence.py:1882`, `1966`; `test_fsm_executor.py:2619`, `4516`, `4554`, `6436`; `test_learning_state.py:31`)
8. **Add behavioral tests** (`test_fsm_executor.py`): capture `idle_timeout` value passed to runner (follow `TestDefaultTimeout.TimeoutCapturingRunner` pattern at line 3757); integration test in `test_ll_loop_execution.py`: hanging subprocess killed after `idle_timeout`, assert `exc.output == "idle_timeout"` (follow `TestRunClaudeCommandIdleTimeout` at `test_subprocess_utils.py:1009`)
9. **Add schema round-trip tests** (`test_fsm_schema.py`): `default_idle_timeout` in `TestFSMLoop` (follow pattern at line 756); `idle_timeout` in `TestStateConfig` (follow pattern at line 455); range-check tests following `TestFSMValidation.test_timeout_zero_rejected` (line 1512)
10. **Update docs** (4 files): API.md, generalized-fsm-loop.md, LOOPS_GUIDE.md (~line 2888), AUTOMATIC_HARNESSING_GUIDE.md (~line 713)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/tests/test_fsm_persistence.py:1882` — add `idle_timeout: int = 0` to `ShutdownAfterFirstRunner.run()`
12. Update `scripts/tests/test_fsm_persistence.py:1966` — add `idle_timeout: int = 0` to `ProgressTrackingRunner.run()`
13. Update `scripts/tests/test_fsm_executor.py:2619` — add `idle_timeout: int = 0` to `RaisingRunner.run()`
14. Update `scripts/tests/test_fsm_executor.py:4516,4554,6436` — add `idle_timeout: int = 0` to `CapturingRunner.run()` (×2) and `ProgressRunner.run()`
15. Update `scripts/tests/test_learning_state.py:31` — add `idle_timeout: int = 0` to `_MockRunner.run()`
16. Add `test_default_idle_timeout_recognized_as_top_level_key` to `scripts/tests/test_fsm_validation.py` (follow `test_circuit_recognized_as_top_level_key` at line 609)
17. **(Optional)** Update `skills/create-loop/reference.md:132,192` and `skills/create-loop/loop-types.md:714,790` — add `idle_timeout` row/note alongside existing `timeout`/`default_timeout` references in field tables and YAML examples

Run `python -m mypy scripts/little_loops/` after each Protocol-conformance update to catch missed signatures.

## Acceptance Criteria

- `DefaultActionRunner.run()` accepts and forwards `idle_timeout` to `run_claude_command()`
- A subprocess that writes output but never exits is killed after `idle_timeout` seconds of silence
- `ll-loop validate` does not emit "Unknown top-level key" for `default_idle_timeout`
- `python -m mypy scripts/little_loops/` passes with no new errors
- `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_persistence.py scripts/tests/test_fsm_schema.py` passes

## Impact

- **Priority**: P2
- **Effort**: Medium (mechanical but multi-file; 18+ touch points)
- **Risk**: Low/Medium — timeout enforcement changes runner behavior; test hung-subprocess behavior carefully

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-25_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Broad Protocol fanout**: The ActionRunner Protocol change fans out to 14 mock runner implementations across 5 test files. All locations are enumerated in the Integration Map, but the blast radius is genuinely broad — run `python -m mypy scripts/little_loops/` after each Protocol-conformance update to catch any missed signatures before moving to the next step.
- **Multi-phase implementation ordering**: Schema → Protocol → Runner → Executor → Validation → Tests must proceed in the order given; each layer depends on the previous. The numbered steps reflect this correctly — follow them sequentially rather than implementing all production code before adding tests.

## Session Log
- `/ll:issue-size-review` - 2026-05-25T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c841cd66-9a6d-4efd-9971-f4ce6e734f58.jsonl`
- `/ll:wire-issue` - 2026-05-26T03:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a81eae6-fc78-4eca-a52a-8960c2ffbd7a.jsonl`
- `/ll:refine-issue` - 2026-05-26T02:55:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010b6d0-c5ea-42f5-b7da-dacb34c4bb15.jsonl`
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ec7ab86-eac4-42cb-b06f-00661e557291.jsonl`
- `/ll:confidence-check` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c66ef3df-2111-4e4b-a024-348d313b0477.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P2
