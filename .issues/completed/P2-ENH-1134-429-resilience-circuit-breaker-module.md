---
id: ENH-1134
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1132, ENH-1133, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
size: Very Large
---

# ENH-1134: 429 Resilience — Shared Circuit Breaker Module

## Summary

Create `rate_limit_circuit.py`, a new FSM helper that maintains a shared file-locked circuit-breaker record under `.loops/tmp/rate-limit-circuit.json`. Insert a pre-action check in the executor so parallel `ll-parallel` worktrees skip redundant API calls when a rate-limit outage is known. Depends on ENH-1132 (config with `circuit_breaker_path`).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Motivation

Today, `ll-parallel` worktrees independently discover the same outage and burn quota in parallel — N workers each retrying expensive slash commands during a global rate-limit event multiplies waste and delays recovery. A shared file visible to all processes lets any worker record a detected outage, and all others pre-sleep until the estimated recovery time.

## Expected Behavior

### 1. New module: `rate_limit_circuit.py`

```python
class RateLimitCircuit:
    def record_rate_limit(self, backoff_seconds: float) -> None: ...
    def get_estimated_recovery(self) -> float | None: ...  # epoch timestamp or None if stale/absent
    def is_stale(self) -> bool: ...
    def clear(self) -> None: ...
```

Circuit-breaker JSON structure:
```json
{
  "first_seen": 1713300000.0,
  "last_seen": 1713302000.0,
  "attempts": 5,
  "estimated_recovery_at": 1713305600.0
}
```

**File locking**: use `fcntl.flock(fd, fcntl.LOCK_EX)` inside a `with open(...)` block — model on `concurrency.py:121-141` (`LockManager.acquire`). Only stdlib; no `filelock`/`portalocker`.

**Atomic write**: `tempfile.mkstemp` + `os.replace` — model on `persistence.py:200-207`.

**Directory creation**: `Path(circuit_breaker_path).parent.mkdir(parents=True, exist_ok=True)` on first write (`.loops/tmp/` does not pre-exist as a Python-managed directory).

**Stale detection**: if `last_seen` is more than 1h ago with no recent updates, `is_stale()` returns `True` and `get_estimated_recovery()` returns `None` — the calling code treats stale entries as absent and proceeds normally.

**429-detection gate**: reuse `classify_failure()` from `issue_lifecycle.py:47-75` as the single source of truth for rate-limit pattern matching. Do NOT re-implement the pattern set.

### 2. Pre-action circuit-breaker check in executor

Insert between `executor.py:427` and `428` (after sub-loop dispatch guard, before `action_result = None` at line 449):

```python
if circuit_breaker_enabled and action_type in LLM_ACTION_TYPES:
    recovery = self._circuit.get_estimated_recovery()
    if recovery is not None:
        wait = recovery - time.time()
        if wait > 0:
            self._interruptible_sleep(wait)
```

Skip check for non-LLM action types (e.g. `action_type: shell` without embedded `slash_command`).

`LLM_ACTION_TYPES` = `{"slash_command", "prompt"}` (the set that hits the Claude API).

The `RateLimitCircuit` instance is created once per executor with the configured `circuit_breaker_path`; inject via constructor so tests can redirect to `tmp_path`.

### 3. Record on 429 detection

Inside the existing rate-limit detection block (`executor.py:481-541`), after confirming a 429, call `self._circuit.record_rate_limit(next_backoff_seconds)` to update the shared file.

### 4. Public API export (`fsm/__init__.py`)

Add `RateLimitCircuit` to `fsm/__init__.py` re-exports (alongside `RATE_LIMIT_EXHAUSTED_EVENT`).

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/fsm/rate_limit_circuit.py` (NEW) — `RateLimitCircuit` class
- `scripts/little_loops/fsm/executor.py` — pre-action check (between lines 427-428); `record_rate_limit` call inside detection block; constructor wiring for `_circuit`; `_execute_sub_loop:390-395` must propagate `self._circuit` to child `FSMExecutor`
- `scripts/little_loops/fsm/__init__.py:87,140` — re-export `RateLimitCircuit`
- `scripts/little_loops/cli/loop/run.py` — pass `circuit_breaker_path` from config to executor constructor
- `scripts/little_loops/cli/loop/testing.py` — `SimulationActionRunner` / `DefaultActionRunner`: use configured `circuit_breaker_path` (not hardcoded) so tests redirect to `tmp_path`
- `scripts/little_loops/cli/loop/lifecycle.py:251` — `cmd_resume` constructs `PersistentExecutor` without `circuit=`; needs same config-read + `circuit=RateLimitCircuit(...)` injection as `run.py:217` [_Wiring pass added by `/ll:wire-issue`:_]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py:188-228` — `wire_extensions()` types `FSMExecutor | PersistentExecutor`; unwraps `executor._executor` at line 228; new `_circuit` attribute transparent — no code change required, but verifies that adding `_circuit` to `FSMExecutor` is safe for extension consumers
- `scripts/little_loops/cli/loop/__init__.py` — dispatch layer calling `cmd_run` and `cmd_simulate`; no direct change, but both commands must accept the wired circuit before this dispatch layer is complete

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4003-4009` — `FSMExecutor.__init__` signature is documented without `circuit`; needs `circuit: RateLimitCircuit | None = None` added (already missing `signal_detector`/`handoff_handler`/`loops_dir` — update all at once)
- `docs/guides/LOOPS_GUIDE.md:1672-1691` — two-tier retry prose describes the backoff tiers but has no mention of circuit-breaker pre-action check or cross-worktree coordination; add a circuit-breaker subsection

### Depends On

- ENH-1132 — `RateLimitsConfig` with `circuit_breaker_enabled` and `circuit_breaker_path` fields

### Similar Patterns to Model After

- `scripts/little_loops/fsm/concurrency.py:121-141` — `LockManager.acquire()` with `fcntl.flock`
- `scripts/little_loops/fsm/persistence.py:200-207` — atomic write with `mkstemp + os.replace`
- `scripts/little_loops/issue_lifecycle.py:47-75` — `classify_failure()` pattern set
- `.issues/completed/P2-BUG-965-circuit-breaker-bypass-exception-path.md` — prior circuit-breaker lessons

### Tests

- `scripts/tests/test_rate_limit_circuit.py` (NEW):
  - `test_record_creates_file` — first write creates `.loops/tmp/` directory and JSON file
  - `test_record_updates_existing` — successive records increment `attempts`, advance `estimated_recovery_at`
  - `test_stale_detection` — entry with `last_seen` > 1h ago returns `is_stale() == True`
  - `test_get_estimated_recovery_stale_returns_none` — stale entry returns `None`
  - `test_concurrent_access` — use `threading.Thread` + `threading.Event` (model on `test_git_lock.py:395-460`; no `multiprocessing` — no precedent in the suite)
  - `test_atomic_write_crash_safety` — file content is never partially written (simulate interrupted write)
  - `test_clear_removes_file` — `clear()` removes the JSON file; subsequent `get_estimated_recovery()` returns `None`
- `scripts/tests/test_fsm_executor.py` — add tests for pre-action pre-sleep:
  - Circuit breaker active → action delayed by recovery wait
  - Stale circuit breaker → action proceeds immediately
  - Non-LLM action type → pre-check skipped
  - `TestRateLimitRetries:4303-4817` / `TestRateLimitStorm` / `TestRateLimitTwoTier` — **existing tests that trigger `_handle_rate_limit` will break** if `record_rate_limit` is not guarded by `if self._circuit is not None:`; this guard is mandatory [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_cli_loop_lifecycle.py:721-854` (`TestCmdRunHandoffThreshold` / `TestCmdRunYAMLConfigOverrides`) — exercise real `PersistentExecutor` construction via `cmd_run`; after ENH-1134 these go through the circuit constructor; add a test asserting circuit= is wired when `circuit_breaker_enabled=True` [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/tests/test_ll_loop_commands.py` — **no existing tests cover `cmd_simulate`**; add at least one test that verifies the circuit= kwarg is accepted by the `FSMExecutor` construction inside `cmd_simulate` (testing.py:243); follow existing `test_ll_loop_commands.py` patterns [_Wiring pass added by `/ll:wire-issue`:_]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current codebase:_

**Line-number corrections (research against current HEAD):**
- `concurrency.py` — `LockManager.acquire()` is **lines 98–141**; the `fcntl.flock(dir_lock, fcntl.LOCK_EX)` call is at **line 123**; the sentinel dotfile pattern (`.acquire.lock`) holds LOCK_EX across read-check + write sequence (lines 120–139).
- `persistence.py` — atomic-write pattern is at **lines 229–236** (in `StatePersistence.save_state`), not 200–207. Identical pattern also duplicated at `state.py:145–152` (no shared helper — follow the inline duplication).
- `executor.py` — rate-limit detection block is at **lines 481–519**, not 481–541. Pre-action insertion point: after the sub-loop dispatch return at **lines 432–438** and before `_run_action` calls at line 441 (next-path) and line 462 (evaluation-path). `action_result = None` is at **line 461**, not 449.
- `fsm/__init__.py` — imports at lines 86–95; `__all__` at line 137 (alphabetically sorted flat list, no grouping).
- `test_git_lock.py` — concurrent-access reference pattern is at **lines 421–460** (`test_second_thread_waits_for_first`), not 395–460.

**Dependency status:** ENH-1132 is already **COMPLETED** — `RateLimitsConfig` lives at `scripts/little_loops/config/automation.py:113–146` with fields `circuit_breaker_enabled: bool = True` and `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`. Re-exported via `config/__init__.py:19,61`.

**Missing constant — must be introduced by this issue:** There is **no existing `LLM_ACTION_TYPES` constant** in the codebase. Action type string literals (`"slash_command"`, `"prompt"`, `"mcp_tool"`, `"shell"`) appear only inline in `executor.py:831–844` (`_action_mode()`). ENH-1134 must define `LLM_ACTION_TYPES: frozenset[str] = frozenset({"slash_command", "prompt"})` as a module-level constant in `executor.py` (the API-hitting set per `_action_mode` mapping).

**Record-call site correction:** The issue text says "Inside the existing rate-limit detection block (executor.py:481–541), after confirming a 429, call `self._circuit.record_rate_limit(next_backoff_seconds)`." However, **no variable named `next_backoff_seconds` exists anywhere in the codebase.** The actual sleep durations are computed as local variables inside `_handle_rate_limit()`:
- Short-tier sleep: `_sleep` at `executor.py:937` (computed immediately before `_interruptible_sleep(_sleep)` at line 940)
- Long-tier sleep: `_wait` at `executor.py:948` (computed immediately before `_interruptible_sleep(_wait)` at line 949)

**Implication:** the `self._circuit.record_rate_limit(...)` call must happen **inside `_handle_rate_limit()`** (not in the detection block at 481–519), at two sites — right before each `_interruptible_sleep` call — passing `_sleep` and `_wait` respectively. The detection block calls `_handle_rate_limit(state, route_ctx.state_name)` at line 499 but has no access to the backoff value.

**Injection pattern for `FSMExecutor`:** Add `circuit: RateLimitCircuit | None = None` as a keyword-only parameter in `executor.py:111–119`, following the existing `action_runner`/`signal_detector`/`handoff_handler` convention (`X | None = None`, stored as `self._circuit = circuit`). `PersistentExecutor.__init__` at `persistence.py:350–385` forwards via `**executor_kwargs`, so no change needed there for the kwarg plumbing — only `cli/loop/run.py:217` needs to pass `circuit=RateLimitCircuit(config.rate_limits.circuit_breaker_path)` when constructing `PersistentExecutor`.

**CLI wiring details:**
- Production path: `cli/loop/run.py:217` (`executor = PersistentExecutor(fsm, loops_dir=loops_dir)`) — this is the **only** `PersistentExecutor` construction call in the codebase. Config is loaded at line 94 (`_config = BRConfig(Path.cwd())`) but is **not currently passed to the executor**. This wiring is a pre-req for the circuit breaker.
- Simulation path: `cli/loop/testing.py:243` (`FSMExecutor` constructed directly in `cmd_simulate`, bypassing `PersistentExecutor`). Tests redirecting via `tmp_path` will need the same `circuit=` kwarg accepted here.
- `cmd_test` at `testing.py:83–85` uses `DefaultActionRunner` standalone (no executor) — no change needed.

**Concurrent-test idioms observed in the suite** (any are valid for `test_concurrent_access`):
- `threading.Event` handshake — `test_git_lock.py:421–460`
- `threading.Barrier` synchronized start — `test_concurrency.py:333–355`
- Thread list + join timeout assertions — `test_state.py:460–480`

**Test fixture idiom for `.loops/tmp/` state files:**
Follow `TestStatePersistence` in `test_fsm_persistence.py:140–147` — fixture returns `tmp_path / ".loops"` **not pre-created**; the class creates directories lazily on first write. The `RateLimitCircuit` constructor receives an absolute path (e.g. `tmp_path / ".loops/tmp/rate-limit-circuit.json"`); `.loops/tmp/` is created by `Path(path).parent.mkdir(parents=True, exist_ok=True)` on first `record_rate_limit()` call.

**Classify-failure integration:** `classify_failure()` at `issue_lifecycle.py:47–75` already contains 9 rate-limit patterns (lines 63–73): `"out of extra usage"`, `"rate limit"`, `"quota exceeded"`, `"too many requests"`, `"api limit"`, `"usage limit"`, `"429"`, `"resource exhausted"`, `"resourceexhausted"`. Used by both `executor.py:495` and `issue_manager.py:603`. Do NOT duplicate patterns in `rate_limit_circuit.py` — the module only needs the backoff-write side; detection stays in the executor where `classify_failure` is already called.

**Sibling event constant gap:** `RATE_LIMIT_STORM_EVENT` is defined at `executor.py:62` but is **not currently exported** from `fsm/__init__.py`. Since ENH-1135 covers heartbeat events + public API, adding `RateLimitCircuit` to `__all__` here is consistent with that sibling's scope — but `RATE_LIMIT_STORM_EVENT` itself is out of scope for ENH-1134 (flag for ENH-1135).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/cli/loop/lifecycle.py:251` — `cmd_resume` constructs `PersistentExecutor` without `circuit=`; apply same config-read + `circuit=RateLimitCircuit(config.rate_limits.circuit_breaker_path)` injection as `run.py:217` so resumed loops are also circuit-guarded
6. Update `scripts/little_loops/fsm/executor.py:390-395` (`_execute_sub_loop`) — propagate `self._circuit` to child `FSMExecutor` constructor so sub-loops share the parent's circuit-breaker state: `FSMExecutor(child_fsm, ..., circuit=self._circuit)`
7. Guard `record_rate_limit` call inside `_handle_rate_limit` with `if self._circuit is not None:` — required to keep all existing `TestRateLimitRetries` / `TestRateLimitStorm` / `TestRateLimitTwoTier` tests green (they construct `FSMExecutor` without `circuit=`)
8. Update `docs/reference/API.md:4003-4009` — add `circuit: RateLimitCircuit | None = None` to the documented `FSMExecutor.__init__` signature; include `signal_detector`, `handoff_handler`, `loops_dir` while there (already missing)
9. Update `docs/guides/LOOPS_GUIDE.md:1672-1691` — add circuit-breaker prose: pre-action check behavior, cross-worktree coordination via shared JSON, stale detection

## Acceptance Criteria

- `rate_limit_circuit.py` exists with `RateLimitCircuit` helper
- File locking uses only `fcntl.flock` (no third-party libs)
- Atomic write uses `mkstemp + os.replace`
- `.loops/tmp/` created on demand; no error if already exists
- 429-detection gate reuses `classify_failure()` (no duplicated pattern set)
- Pre-action check skipped for non-LLM action types
- Pre-action check respects `_shutdown_requested` (Ctrl-C exits quickly)
- `RateLimitCircuit` exported from `fsm/__init__.py`
- Tests pass using `tmp_path` fixture; concurrent-access test uses `threading`

## Session Log
- `/ll:confidence-check` - 2026-04-17T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f96a6fce-cf23-475f-a4bd-8bfd821b8768.jsonl`
- `/ll:wire-issue` - 2026-04-17T05:00:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4c0c9ee-dfc2-4b75-a440-d5956d8b2831.jsonl`
- `/ll:refine-issue` - 2026-04-17T04:54:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9450c5f0-bd73-470a-be61-c59ffbb52be2.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81193e52-67e2-461f-8b12-656dced49eb5.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- ENH-1136: 429 Resilience — `rate_limit_circuit.py` Module + Unit Tests
- ENH-1137: 429 Resilience — Executor Integration & CLI Wiring
- ENH-1138: 429 Resilience — Documentation Updates for Circuit Breaker

---

## Status
- [ ] Open
