# ENH-1137: 429 Resilience — Executor Integration & CLI Wiring

**Plan date:** 2026-04-17
**Issue:** `.issues/enhancements/P2-ENH-1137-circuit-breaker-executor-integration.md`
**Confidence:** 95 (from issue frontmatter)

## Summary

Wire the existing `RateLimitCircuit` module into `FSMExecutor` and the three CLI entry points (`run.py`, `lifecycle.py`, `testing.py`) so parallel worktrees share 429 backoff state. Five concrete changes in `executor.py` + three CLI wire-ups + test coverage.

## Design Decisions (autonomous, no `--gates`)

- **Config access path:** Use `_config.commands.rate_limits.*` (the wiring-pass correction in the issue — `BRConfig` has no top-level `rate_limits`).
- **Skip `--plan-only`:** Action is `improve`, no `--plan-only` flag → implement.
- **TDD mode:** `config.commands.tdd_mode` defaults to `False` → Phase 3a skipped.
- **Confidence gate:** Disabled by default → Phase 2.5 skipped. Score 95 anyway.
- **Already done step 6:** `fsm/__init__.py` already exports `RateLimitCircuit` (verified line 117 / `__all__` line 167).

## Changes

### 1. `scripts/little_loops/fsm/executor.py`

1. Add module-level constant near line 64:
   ```python
   LLM_ACTION_TYPES: frozenset[str] = frozenset({"slash_command", "prompt"})
   ```
2. Add import: `from little_loops.fsm.rate_limit_circuit import RateLimitCircuit`.
3. `__init__`: add `circuit: RateLimitCircuit | None = None` kwarg; store as `self._circuit = circuit`.
4. `_execute_sub_loop` (line 390): pass `circuit=self._circuit` to child; also propagate `signal_detector`, `handoff_handler` if already passed — match current invocation (just add `circuit=self._circuit`).
5. `_execute_state`: before each `_run_action` call (the two sites — next-path line 443, eval-path line 463), add the pre-action circuit-breaker check guarded by `self._circuit is not None` AND `action_type in LLM_ACTION_TYPES`. Use `self._action_mode(state)` to derive action_type — map `"prompt"` (the executor's canonical LLM mode) to the check; the set includes both `"slash_command"` and `"prompt"` for clarity even though `_action_mode` collapses `slash_command` into `"prompt"`.
6. `_handle_rate_limit`: add null-guarded `self._circuit.record_rate_limit(_sleep)` before short-tier sleep (line 940) and `self._circuit.record_rate_limit(_wait)` before long-tier sleep (line 949).

### 2. `scripts/little_loops/cli/loop/run.py:217`

Wrap executor construction with:
```python
circuit = (
    RateLimitCircuit(Path(_config.commands.rate_limits.circuit_breaker_path))
    if _config.commands.rate_limits.circuit_breaker_enabled
    else None
)
executor = PersistentExecutor(fsm, loops_dir=loops_dir, circuit=circuit)
```
Add import `from little_loops.fsm.rate_limit_circuit import RateLimitCircuit` (lazy, inside function with other imports).

### 3. `scripts/little_loops/cli/loop/lifecycle.py:251`

Reorder: construct `BRConfig` at ~line 250 (before `PersistentExecutor`). Replace:
```python
executor = PersistentExecutor(fsm, loops_dir=loops_dir)
```
with construction of circuit from `config.commands.rate_limits`, then pass `circuit=circuit`. Remove the redundant second `BRConfig` creation at line 259; reuse the reordered instance.

### 4. `scripts/little_loops/cli/loop/testing.py:243`

Add `circuit` kwarg to `cmd_simulate` signature (default `None`) and pass through to `FSMExecutor`. This keeps it testable via `tmp_path`. The CLI entry point (`__init__.py`) does not pass a circuit for simulate — default `None` is fine.

### 5. Tests — `scripts/tests/test_fsm_executor.py`

Add new test class `TestRateLimitCircuitIntegration`:
- `test_pre_action_sleep_when_circuit_active` — construct circuit in `tmp_path`, call `record_rate_limit(1000)` → create executor with a state whose action_type is `slash_command`; MockActionRunner asserts no call occurs during pre-sleep (use `_interruptible_sleep` mock to catch duration) OR simpler: mock `_interruptible_sleep` and assert call with positive wait. Action mode is `prompt` (slash-command), single-iteration FSM.
- `test_pre_action_no_sleep_when_circuit_stale` — circuit exists but `get_estimated_recovery()` returns None (no prior records); assert `_interruptible_sleep` not called pre-action.
- `test_pre_action_skipped_for_shell_action` — state with `action_type: shell` and an active circuit; assert no pre-sleep call.
- `test_record_rate_limit_called_on_short_tier` — circuit is active; 429 then success; assert `record_rate_limit` was called once with the short-tier backoff value.
- `test_record_rate_limit_not_called_when_circuit_none` — existing path (no circuit=) ; add assertion `getattr(executor, "_circuit", None) is None` and just run with a 429 → success sequence and confirm it still terminates cleanly (covered by `TestRateLimitRetries` but add an explicit null-guard confirmation).

### 6. Tests — `scripts/tests/test_cli_loop_lifecycle.py`

Add `test_cmd_resume_wires_circuit_when_enabled` and `test_cmd_resume_wires_none_when_disabled` using the existing `mock_exec_cls` pattern — assert the `circuit` kwarg to `PersistentExecutor` has the expected type.

### 7. Tests — `scripts/tests/test_ll_loop_commands.py` (cmd_simulate)

Add a `TestCmdSimulateCircuit` test asserting `FSMExecutor` receives `circuit=` kwarg (simplest: pass circuit directly and confirm it's stored as `_circuit`).

## Verification

- `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_commands.py -v`
- `python -m pytest scripts/tests/` (full)
- `ruff check scripts/`
- `python -m mypy scripts/little_loops/`

## Risks

- **Action-type mapping:** `_action_mode` returns `"prompt"` for both literal `prompt` and `slash_command` action_types. `LLM_ACTION_TYPES` includes both string forms but the derived `action_type` from `_action_mode` only produces `"prompt"`. Using `_action_mode()` output is unambiguous — check `action_mode == "prompt"` directly, using `LLM_ACTION_TYPES` as documentation. Decision: check `self._action_mode(state) == "prompt"` for clarity.
- **Sub-loop propagation:** child circuit is shared by reference — correct for coordination. No copy needed.
- **Existing tests:** All existing `TestRateLimitRetries`/`TestRateLimitStorm`/`TestRateLimitTwoTier` construct `FSMExecutor` without `circuit=`; the null guard preserves them.
