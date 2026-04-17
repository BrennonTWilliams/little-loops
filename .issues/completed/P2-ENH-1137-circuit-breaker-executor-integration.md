---
id: ENH-1137
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
parent: ENH-1134
related: [ENH-1134, ENH-1136, ENH-1132]
depends_on: [ENH-1136]
size: Large
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1137: 429 Resilience — Executor Integration & CLI Wiring

## Summary

Wire `RateLimitCircuit` (from ENH-1136) into the FSM executor: pre-action check before LLM actions, `record_rate_limit` call on 429 detection, sub-loop propagation, and CLI wiring in `run.py`, `lifecycle.py`, and `testing.py`. Also export `RateLimitCircuit` from `fsm/__init__.py`.

## Parent Issue

Decomposed from ENH-1134: 429 Resilience — Shared Circuit Breaker Module

## Depends On

- ENH-1136 — `RateLimitCircuit` module must exist before this integration

## Expected Behavior

### 1. Pre-action circuit-breaker check in `executor.py`

Define module-level constant:
```python
LLM_ACTION_TYPES: frozenset[str] = frozenset({"slash_command", "prompt"})
```

Insert after the sub-loop dispatch return (lines 432–438) and before `_run_action` calls (line 443 next-path, line 463 eval-path):

```python
if circuit_breaker_enabled and action_type in LLM_ACTION_TYPES:
    recovery = self._circuit.get_estimated_recovery()
    if recovery is not None:
        wait = recovery - time.time()
        if wait > 0:
            self._interruptible_sleep(wait)
```

Skip check for non-LLM action types (e.g. `action_type: shell`).

### 2. `RateLimitCircuit` injection into `FSMExecutor`

Add `circuit: RateLimitCircuit | None = None` as keyword-only parameter in `executor.py:111-119`, following the existing `action_runner`/`signal_detector`/`handoff_handler` convention (`X | None = None`, stored as `self._circuit = circuit`).

### 3. `record_rate_limit` calls inside `_handle_rate_limit()`

Inside `_handle_rate_limit()` — NOT in the detection block at 491–519 (which has no access to backoff values). Call at two sites, guarded by `if self._circuit is not None:`:
- Right before short-tier `self._interruptible_sleep(_sleep)` at line 940 — pass `_sleep` (positional `backoff_seconds`)
- Right before long-tier `self._interruptible_sleep(_wait)` at line 949 — pass `_wait`

`RateLimitCircuit.record_rate_limit(backoff_seconds: float)` takes a single positional float; the local `_sleep`/`_wait` are already `float` (see `fsm/rate_limit_circuit.py:44`).

The null guard is mandatory to keep existing `TestRateLimitRetries` / `TestRateLimitStorm` / `TestRateLimitTwoTier` tests green.

### 4. Sub-loop propagation in `_execute_sub_loop`

At `executor.py:390-395`, propagate `self._circuit` to child `FSMExecutor`:
```python
FSMExecutor(child_fsm, ..., circuit=self._circuit)
```

### 5. CLI wiring

`RateLimitCircuit.__init__` takes a `Path` (not a `str`) — wrap `config.rate_limits.circuit_breaker_path` with `Path(...)` at each call site.

- `cli/loop/run.py:217` — `_config` is already in scope (used at line 224 for `wire_extensions`); construct `PersistentExecutor` with `circuit=RateLimitCircuit(Path(_config.rate_limits.circuit_breaker_path))` when `_config.rate_limits.circuit_breaker_enabled` is True, else `circuit=None`.
- `cli/loop/lifecycle.py:251` — `cmd_resume` constructs `PersistentExecutor` BEFORE `config = BRConfig(Path.cwd())` (built at line 259). **Must reorder**: move `BRConfig` construction above line 251 so `config.rate_limits` is readable at the executor construction site. The existing `wire_extensions` call at line 260 also uses `config.extensions` and is unaffected by the reorder.
- `cli/loop/testing.py:243` — `cmd_simulate` constructs `FSMExecutor` directly (not `PersistentExecutor`) with `event_callback=simulation_callback, action_runner=sim_runner`; add optional `circuit=` kwarg so tests can redirect the circuit file via `tmp_path`. Default to `None`.

### 6. Public API export (`fsm/__init__.py`) — ALREADY DONE

**Status (verified 2026-04-17 by `/ll:ready-issue`):** `RateLimitCircuit` is already imported at `fsm/__init__.py:117` (`from little_loops.fsm.rate_limit_circuit import RateLimitCircuit`) and listed in `__all__` at line 167. This step was completed as part of ENH-1136 and requires no further action in this issue.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — `LLM_ACTION_TYPES` constant; `circuit` kwarg in `__init__`; pre-action check; `record_rate_limit` calls in `_handle_rate_limit`; sub-loop propagation in `_execute_sub_loop`
- ~~`scripts/little_loops/fsm/__init__.py:89-98,144` — re-export `RateLimitCircuit`~~ (already present at line 117 / `__all__` line 167 — no change needed)
- `scripts/little_loops/cli/loop/run.py:217` — circuit wiring to `PersistentExecutor`
- `scripts/little_loops/cli/loop/lifecycle.py:251` — circuit wiring to `cmd_resume`
- `scripts/little_loops/cli/loop/testing.py:243` — circuit kwarg in `cmd_simulate`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py:25-26` — imports `FSMExecutor` and `PersistentExecutor`; `wire_extensions` accesses `executor._executor._contributed_actions` etc.; new `_circuit` attribute is invisible to this path, no code change needed [Agent 1]
- `scripts/little_loops/cli/loop/__init__.py` — CLI entry point that dispatches `cmd_resume` (lifecycle) and `cmd_simulate` (testing) as named subcommands; no code change needed but affected by the cmd_resume/cmd_simulate signature changes [Agent 1]
- `scripts/little_loops/cli/loop/_helpers.py` — references `FSMExecutor._current_process` and accepts `PersistentExecutor` in shutdown helper; new `_circuit` attribute is not accessed here, no code change needed [Agent 1]

### Key Reference Points

- `scripts/little_loops/fsm/persistence.py:350-385` — `PersistentExecutor.__init__` accepts `**executor_kwargs: Any` at line 355 and forwards to `FSMExecutor(...)` at line 384; no change needed there — only `run.py:217` / `lifecycle.py:251` need to pass `circuit=`
- `executor.py:111-119` — `FSMExecutor.__init__` signature, current kwargs: `fsm`, `event_callback`, `action_runner`, `signal_detector`, `handoff_handler`, `loops_dir` (all `| None = None`). Add `circuit: RateLimitCircuit | None = None` at end to match the convention.
- `executor.py:491-519` — rate-limit detection block; `classify_failure` at 495, `_handle_rate_limit()` call at 499
- `executor.py:831-844` — `_action_mode()` showing inline action type string literals
- `executor.py:955-968` — `_interruptible_sleep(self, duration: float) -> float` polls `self._shutdown_requested` in 100ms ticks and returns actual elapsed seconds (callers need not track wall-clock separately)
- `fsm/rate_limit_circuit.py:40,44,77` — `__init__(path: Path)` / `record_rate_limit(backoff_seconds: float) -> None` / `get_estimated_recovery() -> float | None` (epoch timestamp or `None` when absent/stale)
- `scripts/little_loops/config/automation.py:133-134` — `RateLimitsConfig` fields `circuit_breaker_enabled: bool = True` and `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"` (already present from ENH-1132)

### Tests

- `scripts/tests/test_fsm_executor.py` (4818 lines) — add tests for pre-action pre-sleep. Model after existing `TestRateLimitRetries` (line 4303), `TestRateLimitStorm` (line 4549), `TestRateLimitTwoTier` (line 4662). Standard pattern: `patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0)` + `MockActionRunner(use_indexed_order=True)` with indexed results. New test cases:
  - Circuit breaker active → pre-action `_interruptible_sleep` called with positive duration
  - Stale circuit breaker (`get_estimated_recovery()` returns `None`) → action proceeds immediately, no pre-sleep
  - Non-LLM action type (e.g. `shell`) → pre-check skipped entirely
  - `self._circuit is None` → no `record_rate_limit` call inside `_handle_rate_limit` (guards existing `TestRateLimitRetries`/`TestRateLimitStorm`/`TestRateLimitTwoTier` — which construct `FSMExecutor` without `circuit=`)
- `scripts/tests/test_rate_limit_circuit.py` (193 lines, from ENH-1136) — reference only; do NOT duplicate module-level tests here
- `scripts/tests/test_cli_loop_lifecycle.py` (1025 lines) — add test asserting `circuit=` is wired on `PersistentExecutor` when `_config.rate_limits.circuit_breaker_enabled=True` (and `circuit=None` when disabled). Existing rate-limit-related tests span 721-854.
- `scripts/tests/test_ll_loop_commands.py` (2837 lines) — add test verifying `circuit=` kwarg is accepted by `FSMExecutor` in `cmd_simulate` (tests pass a `RateLimitCircuit` pointed at `tmp_path` to confirm state is redirected away from `.loops/tmp/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:1852` — `test_save_state_includes_rate_limit_retries`: constructs `PersistentExecutor` without `circuit=`; should remain green (null default + null guard), but validate after implementation [Agent 3]
- `scripts/tests/test_fsm_persistence.py:1886` — `test_resume_restores_rate_limit_retries`: same concern — constructs `PersistentExecutor` without circuit; verify green with null guard in place [Agent 3]
- `scripts/tests/test_ll_loop_execution.py` — `TestEndToEndExecution` (line 95) drives full `cmd_run → PersistentExecutor → FSMExecutor` path; uses `capture_persistent_executor_init` with `**kwargs` pass-through (lines 689–711), so adding `circuit=` to `run.py:217` flows through transparently — no breakage expected, but this is the right file to add an integration test asserting circuit is wired with the correct path [Agent 3]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

**CORRECTION — Config access path bug in CLI Wiring section:**
Lines 74–76 in this issue write `_config.rate_limits.circuit_breaker_path` and `_config.rate_limits.circuit_breaker_enabled`, but `BRConfig` has **no top-level `rate_limits` property**. The correct access chain is `_config.commands.rate_limits.circuit_breaker_path` (and `.circuit_breaker_enabled`). Confirmed via `config/core.py:138` — `commands` is the only property that exposes `CommandsConfig`, which in turn has `rate_limits: RateLimitsConfig`. Apply this correction to both `run.py:217` and `lifecycle.py:251`.

_Corrected code for `run.py:217`:_
```python
circuit = (
    RateLimitCircuit(Path(_config.commands.rate_limits.circuit_breaker_path))
    if _config.commands.rate_limits.circuit_breaker_enabled
    else None
)
```

_Same correction applies to the `lifecycle.py:251` site after the BRConfig reorder._

## Acceptance Criteria

- Pre-action check skipped for non-LLM action types
- Pre-action check respects `_shutdown_requested` (Ctrl-C exits quickly via `_interruptible_sleep`)
- `record_rate_limit` call guarded by `if self._circuit is not None:` — all existing rate-limit tests pass unchanged
- `RateLimitCircuit` exported from `fsm/__init__.py`
- `cmd_resume` and `cmd_simulate` both wired with circuit injection
- Sub-loops inherit parent circuit instance

## Resolution

Resolved 2026-04-17 via `/ll:manage-issue`.

- `executor.py`: added `LLM_ACTION_TYPES` constant, `circuit` kwarg on `FSMExecutor.__init__`, `_maybe_wait_for_circuit` helper inserted before both `_run_action` call sites, null-guarded `record_rate_limit` calls in `_handle_rate_limit` short/long tiers, and sub-loop propagation of `self._circuit` to child executors.
- `cli/loop/run.py`: constructs `RateLimitCircuit(Path(_config.commands.rate_limits.circuit_breaker_path))` when enabled and passes via `circuit=` to `PersistentExecutor`.
- `cli/loop/lifecycle.py`: reordered `BRConfig` construction before `PersistentExecutor` and wired circuit injection for `cmd_resume`.
- `cli/loop/testing.py`: added `circuit: RateLimitCircuit | None = None` kwarg to `cmd_simulate`, forwarded to `FSMExecutor`.
- Tests: added `TestRateLimitCircuitIntegration` (6 cases) in `test_fsm_executor.py`, `TestCmdResumeCircuitWiring` (2 cases) in `test_cli_loop_lifecycle.py`, `TestCmdSimulateCircuit` in `test_ll_loop_commands.py`.
- Verification: 4902 tests pass, ruff clean, mypy clean on modified files.
- Plan: `thoughts/shared/plans/2026-04-17-ENH-1137-management.md`.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T05:44:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e803071-550e-4546-bc58-d0c2cba8fd53.jsonl`
- `/ll:manage-issue` - 2026-04-17T06:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-04-17T05:35:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4714e4c-45b9-48ee-a533-8361fe72c130.jsonl`
- `/ll:wire-issue` - 2026-04-17T05:30:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3b2c022-5f3e-4aec-86f8-a52503804cc4.jsonl`
- `/ll:refine-issue` - 2026-04-17T05:22:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5c36e83-54fa-44b3-8c2a-31d4f4e1c445.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81193e52-67e2-451f-8b12-656dced49eb5.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6e6a606-f95f-4c8c-a010-a9bc9b589bad.jsonl`

---

## Status
- [x] Completed 2026-04-17
