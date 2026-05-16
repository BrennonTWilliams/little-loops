---
status: done
completed_at: 2026-04-21T00:00:00Z
---
> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-20"
discovered_by: issue-size-review
parent_issue: FEAT-1206
size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1210: TestParallelRunnerRealThreading — Timeout Per-Item Test

## Summary

Add `test_real_threads_timeout_one_while_others_complete` to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`.

## Parent Issue

Decomposed from FEAT-1206: TestParallelRunnerRealThreading — Fail Fast + Timeout Tests

## Use Case

**Who**: Developer completing FEAT-1075 (`ParallelRunner` implementation)

**Context**: After FEAT-1205 adds the `TestParallelRunnerRealThreading` class (or FEAT-1209 creates it), this adds the timeout test to verify that a timed-out worker gets `terminated_by="timeout"` while other workers complete normally and the overall verdict is `"partial"`.

**Goal**: Add 1 real-threading test to `TestParallelRunnerRealThreading` in `scripts/tests/test_parallel_runner.py`. Class-level `@pytest.mark.integration` must be present. MUST run in default CI — NOT gated behind `@pytest.mark.slow`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_timeout_one_while_others_complete -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

Test goes inside `TestParallelRunnerRealThreading` (class-level `@pytest.mark.integration`). Uses real `ThreadPoolExecutor` (no mocks on executor layer).

**`test_real_threads_timeout_one_while_others_complete`** — 4 workers, `timeout_seconds=1`, worker 2 (index 2) sleeps 5s.

Assert:
- `result.all_results[2].terminated_by == "timeout"`
- `result.all_results[2].error.kind == "timeout"`
- `result.all_results[0].verdict == "yes"` and `result.all_results[1].verdict == "yes"` and `result.all_results[3].verdict == "yes"`
- `result.verdict == "partial"`

Implementation sketch (correct wiring — see "Runner API — correction" below; the original `worker_body(item, context)` sketch is not how FEAT-1075 exposes work injection):

```python
# items are strings (FEAT-1075 line 95: items: list[str]); each is interpolated into the child loop's shell action as ${loop_var.item}
items = ["0.1", "0.1", "5", "0.1"]

# Write a minimal child loop YAML to tmp_path / ".loops" (pattern from test_fsm_executor.py:3634+ TestSubLoopExecution)
(tmp_path / ".loops").mkdir()
(tmp_path / ".loops" / "slow_sleep.yaml").write_text(textwrap.dedent("""
    name: slow_sleep
    states:
      sleep:
        type: shell
        action: { cmd: "sleep ${loop_var.item}" }
        next: END
"""))

config = ParallelStateConfig(
    items="item_list",          # context key — FEAT-1202:85 shows `items="ctx_key"` form
    loop="slow_sleep",
    timeout_seconds=1,
    fail_mode="collect",        # not fail_fast — we want siblings to complete
)

runner = ParallelRunner()
result = runner.run(
    items=items,
    loop_name="slow_sleep",
    config=config,
    parent_context={},
)
```

### Implementation Notes

- FEAT-1075 uses `concurrent.futures.TimeoutError` (NOT built-in `TimeoutError`) when enforcing `timeout_seconds` via `future.result(timeout=...)`. Timed-out workers get `ParallelItemResult(verdict="no", terminated_by="timeout", error=ParallelItemError(kind="timeout", ...))`.
- `all_results` ordering guarantee: FEAT-1075 pre-allocates by slot — `all_results[i]` always corresponds to `items[i]`. Safe for index-based assertions.
- Overall verdict: `"partial"` (mixed: 3 success + 1 timeout). Per FEAT-1075: `"yes"` = all passed, `"no"` = all failed, `"partial"` = mixed.
- Test should complete in < 10s total (timeout test: worker 2 hits `timeout_seconds=1` ceiling, not the full 5s sleep).
- **Novelty flag**: No existing test in the suite asserts `terminated_by == "timeout"` on a list-indexed per-item result (`result.all_results[i].terminated_by`). Get the field-path right on the first try rather than copy-adapting from scalar-result precedents.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add 1 test to `TestParallelRunnerRealThreading`

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` with `timeout_seconds` field (FEAT-1074)
- `scripts/little_loops/fsm/__init__.py` — exports `ParallelRunner`, `ParallelItemResult`, `ParallelResult`, `ParallelItemError` (FEAT-1075)
- FEAT-1202 must be complete (creates `test_parallel_runner.py`)
- FEAT-1205 or FEAT-1209 should be complete (creates `TestParallelRunnerRealThreading` class with marker)

### Similar Patterns (for assertion syntax)
- `scripts/tests/test_fsm_executor.py:2033-2037` — `assert result.terminated_by == "timeout"` on `ExecutionResult`; parallel analogue is `result.all_results[2].terminated_by == "timeout"` on `ParallelItemResult`. Same string, different dataclass.
- `scripts/tests/test_fsm_persistence.py:868` — `assert result.terminated_by == "timeout"` on `PersistentExecutor` result; same value.
- `scripts/tests/test_fsm_evaluators.py:620-627` — `assert result.verdict == "partial"` on `EvaluationResult`; parallel analogue is `assert result.verdict == "partial"` on `ParallelResult`.
- `scripts/tests/test_worker_pool.py:461-462` — `future.result(timeout=5)` blocking pattern; matches runner-internal timeout path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-20):_

- **Existing pattern references verified accurate** — all four line references above (`test_fsm_executor.py:2033-2037`, `test_fsm_persistence.py:868`, `test_fsm_evaluators.py:620-627`, `test_worker_pool.py:461-462`) were confirmed at current HEAD with their quoted assertions intact.
- **Class-level `@pytest.mark.integration` precedent**: use `scripts/tests/test_goals_parser.py:437-438` (`@pytest.mark.integration` on `class TestIntegration:`) as the structural model. The six other integration test files (`test_worker_pool.py:34`, `test_merge_coordinator.py:17`, `test_orchestrator.py:40`, `test_git_lock.py:16`, `test_cli_e2e.py:21`, `test_sprint_integration.py:12`) use file-level `pytestmark = pytest.mark.integration` instead — **not applicable** here because `test_parallel_runner.py` will contain both mocked unit classes (FEAT-1202) and real-threading classes (FEAT-1205/1209/1210).
- **Runtime timeout-catch precedent**: `scripts/little_loops/parallel/orchestrator.py:796` is the only existing `future.result(timeout=...)` call in the repo. It sits inside a broad `except Exception as e:` at `orchestrator.py:800-802` (not a typed `concurrent.futures.TimeoutError` catch). FEAT-1075 intentionally diverges by catching the futures-module exception specifically. This test is the first integration test to exercise that typed path.
- **Pre-condition check — exports absent at HEAD**: `ParallelRunner`, `ParallelResult`, `ParallelItemResult`, and `ParallelItemError` have zero occurrences under `scripts/` at this moment. The test's top-level `from little_loops.fsm import ParallelRunner` will `ImportError` until FEAT-1075 lands. This is expected; FEAT-1075 is a hard blocker.
- **`all_results[i]` indexed-attribute novelty confirmed**: zero matches for `all_results` anywhere under `scripts/`. No existing test asserts on a per-item domain field via `result.<list>[i].<attr>` — the closest real-`ThreadPoolExecutor` tests (`test_state.py:426-431`, `test_hooks_integration.py:68-70`) assert only on `len()` and simple scalar fields. This reinforces the issue's novelty flag: don't copy-adapt from scalar-result precedents.
- **pytest-markers config**: `scripts/pyproject.toml:113-116` registers `integration` (and `slow`) under `[tool.pytest.ini_options].markers`. `--strict-markers` is active (`pyproject.toml:106-112`) so a typo in the marker name would fail at collection time.

### Runner API — correction from second refinement pass (2026-04-20)

_Added by `/ll:refine-issue` — corrects a gap that would mis-direct an implementer:_

- **No external `worker_body` callable.** FEAT-1075:92-103 shows the canonical `ParallelRunner` signature: `run(self, items: list[str], loop_name: str, config: ParallelStateConfig, parent_context=None, on_worker_complete=None, starting_item_index=0) -> ParallelResult`. There is **no `worker_body` parameter** anywhere in the design. Each worker internally constructs and runs an `FSMExecutor` on the child `loop_name` (FEAT-1075:122 — "Each thread constructs and runs an `FSMExecutor` for one item"). The `worker_body(item, context)` stub in this issue's Proposed Solution (and in sibling FEAT-1209) is misleading — it describes a mental model, not a parameter.
- **How to inject per-item duration without a worker callable**: use the child-loop pattern from `scripts/tests/test_fsm_executor.py:3634+` (`TestSubLoopExecution`) — write a child YAML to `tmp_path / ".loops"` whose action uses `${loop_var.item}` for the sleep duration. Pass per-item durations as the `items` list: `["0.1", "0.1", "5", "0.1"]`. Worker 2's `sleep 5` hits `future.result(timeout=1)` and is recorded as a timeout.
- **Timeout enforcement mechanism** (FEAT-1075:125): `future.result(timeout=config.timeout_seconds)` raises `concurrent.futures.TimeoutError`; the runner catches and records `ParallelItemResult(verdict="no", terminated_by="timeout", error=ParallelItemError(kind="timeout", ...))`. **Caveat**: Python's `ThreadPoolExecutor` cannot kill a running thread — the timed-out `sleep 5` shell subprocess continues until it exits naturally. Whether the test's overall wall-clock is ~1s or ~5s depends on whether FEAT-1075 uses `executor.shutdown(wait=False)` or an equivalent abandonment path. Implementer should verify this when FEAT-1075 lands; if `wait=True` is used, the "< 10s total" target in Implementation Notes is met but the test will block ~5s on pool shutdown.
- **Correct import statements** (FEAT-1202:80-83 specifies the split — `ParallelItemResult` and `ParallelItemError` are NOT re-exported from `fsm/__init__.py`):
  ```python
  from little_loops.fsm import ParallelRunner, ParallelResult
  from little_loops.fsm.parallel_runner import ParallelItemResult, ParallelItemError
  from little_loops.fsm.schema import ParallelStateConfig
  ```
  Per FEAT-1075:188 `__all__` only adds `ParallelRunner` and `ParallelResult`. An import of `ParallelItemResult` from the package root will fail.
- **`ParallelStateConfig.items` ambiguity — flag for implementer**: FEAT-1202:85 shows the config constructed as `ParallelStateConfig(items="ctx_key", loop="child")` (a context-key string), while FEAT-1075:96 types the `run()` `items` parameter as `list[str]`. These are two distinct parameters: `config.items` is the YAML-level context key the executor uses to resolve the list (FEAT-1076 concern); `run()`'s `items` parameter is the already-resolved literal list. The test should pass the literal list directly via `run(items=[...])` and set `config.items` to any non-empty string (context key does not matter when the runner is called directly, bypassing `_execute_parallel_state()`).
- **FEAT-1209 has the same `worker_body` sketch issue** — both sibling tests need the same correction. Consider a cross-reference update to FEAT-1209 when this issue is picked up.

## Dependencies

- **FEAT-1074** must be complete (`ParallelStateConfig` in `schema.py`)
- **FEAT-1075** must be complete (`ParallelRunner` implementation + `fsm/__init__.py` exports)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1205** or **FEAT-1209** should be complete (creates `TestParallelRunnerRealThreading` class with marker)

### Coverage Gate Risk

`scripts/pyproject.toml:133` sets `fail_under = 80`. This test exercises the `concurrent.futures.TimeoutError` → `terminated_by="timeout"` translation path — a branch that mocked unit tests cannot exercise. If coverage falls below 80 before this lands, CI will fail at the coverage gate. Run with `--no-cov` locally if iterating.

## Acceptance Criteria

- `python -m pytest scripts/tests/test_parallel_runner.py::TestParallelRunnerRealThreading::test_real_threads_timeout_one_while_others_complete -x` passes green
- Test runs in default CI (class-level `@pytest.mark.integration`, no `@pytest.mark.slow`)
- Asserts worker 2 has `terminated_by == "timeout"` and `error.kind == "timeout"`
- Asserts workers 0/1/3 have `verdict == "yes"`
- Asserts `result.verdict == "partial"`

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-20_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- **Hard blockers unresolved at HEAD**: FEAT-1074 (`ParallelStateConfig.timeout_seconds`), FEAT-1075 (`ParallelRunner` + `ParallelItemResult`/`ParallelItemError`), and FEAT-1202 (creates `test_parallel_runner.py`) are all still open in `.issues/features/`. The test cannot be imported or pass until all three land.
- **FEAT-1205 confirmed as ticket-management action**: FEAT-1205 is in `completed/` but `TestParallelRunnerRealThreading` has zero occurrences in `scripts/`. The class must come from FEAT-1209 landing first, or FEAT-1210 must scaffold the class itself.

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e066c90-09b5-4d1f-b6ae-3c26d51cc081.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:56:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6d6f0fc-f735-4c80-9fa4-b4b947a300cf.jsonl`
- `/ll:confidence-check` - 2026-04-20T23:52:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88e30b52-0950-4979-a375-c6ca932af59b.jsonl`
- `/ll:refine-issue` - 2026-04-21T04:46:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c0e60b3-d013-442e-8b68-cfccc9e32f96.jsonl`
- `/ll:issue-size-review` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f84bc5fa-3fa1-4822-8f5a-25670ac913a0.jsonl`
