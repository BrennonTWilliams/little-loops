---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 79
---

# FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Summary

Extend `FSMExecutor` to dispatch to contributed action types, contributed evaluators, and `before_route`/`after_route` interceptors. Adds `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes, then wires them into the existing dispatch paths in `_action_mode()`, `_run_action()`, and `_evaluate()`.

## Use Case

A developer building a custom FSM loop extension wants to register a contributed action type (e.g., a webhook caller or database writer) without modifying core `executor.py`. They implement the `ActionRunner` protocol from FEAT-983, register it on the `FSMExecutor` instance, and define loop states with `action_type: "webhook"`. At runtime the executor detects the contributed type, dispatches to their runner, and fires any registered route interceptors — enabling per-loop routing observability or redirect overrides without touching shared infrastructure.

## Parent Issue

Decomposed from FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Context

FEAT-983 defines the Protocol and type foundations. This issue implements the FSM executor changes needed to actually dispatch to the registered extensions at runtime. `wire_extensions()` upgrade (FEAT-985) populates these registries; this issue only needs to define them and use them.

## Current Behavior

`FSMExecutor` has no concept of contributed action types or evaluators. `_action_mode()` uses a hardcoded `if/elif` chain. Route interceptors do not exist.

## Motivation

Without runtime dispatch support, the Protocol and type definitions from FEAT-983 have no effect — contributed extensions are defined but never called. This issue closes the gap between interface definition and actual runtime behavior, making the extension system usable end-to-end. It is a direct prerequisite for FEAT-985 (`wire_extensions()`) and unblocks the full contributed-extensions workflow for plugin developers.

## Expected Behavior

- `FSMExecutor.__init__()` initializes three new attributes
- `_action_mode()` checks `_contributed_actions` before fallback
- `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- `_evaluate()` dispatches to contributed evaluator before `evaluate()`
- `before_route`/`after_route` interceptors fire around `_route()` in `_execute_state()`

## Proposed Solution

### 1. New Attributes in `FSMExecutor.__init__()`

Add after `self._depth: int = 0` at `executor.py:125`:

```python
# Extension hook registries — populated by wire_extensions()
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

Add `Any` to existing `from typing import ...` import in `executor.py`.

### 2. Contributed Action Dispatch

**`_action_mode()` (line 701)** — add after `if state.action_type == "shell": return "shell"` (line 697) and before the `/`-prefix heuristic (line 699):

```python
if state.action_type in self._contributed_actions:
    return "contributed"
```

**`_run_action()` (lines 428–443)** — current dispatch is binary (`if "mcp_tool" ... else ...`). Convert to ternary by inserting `elif` before the existing `else`:

```python
elif action_mode == "contributed":
    runner = self._contributed_actions[state.action_type]
    result = runner.run(
        action,
        timeout=state.timeout or self.fsm.default_timeout or 3600,
        is_slash_command=False,
        on_output_line=_on_line,
    )
else:  # prompt / shell — unchanged
    result = self.action_runner.run(...)
```

### 3. Contributed Evaluator Dispatch

**`_evaluate()` (lines 605–616)** — insert contributed evaluator check **before line 605** (the `llm_structured`/`--no-llm` guard), demoting the existing `if` to `elif`:

```python
if state.evaluate.type in self._contributed_evaluators:
    result = self._contributed_evaluators[state.evaluate.type](
        state.evaluate, eval_input,
        action_result.exit_code if action_result else 0,
        ctx,
    )
elif state.evaluate.type == "llm_structured" and not self.fsm.llm.enabled:  # was 'if'
    result = EvaluationResult(
        verdict="error",
        details={"error": "LLM evaluation disabled via --no-llm"},
    )
else:
    result = evaluate(...)  # unchanged
```

### 4. `before_route` / `after_route` Interceptor Dispatch

**Do NOT add dispatch inside `_route()` itself** — it has 8 return sites. Instead, refactor `executor.py:400-402` (the single call site in `_execute_state()`) to capture the return value and wrap with interceptor calls:

```python
# executor.py:400-402 (after modification)
verdict = eval_result.verdict if eval_result else "yes"
route_ctx = RouteContext(
    state_name=self.current_state, state=state, verdict=verdict,
    action_result=action_result, eval_result=eval_result,
    ctx=ctx, iteration=self.iteration,
)
# before_route interceptors
for interceptor in self._interceptors:
    if hasattr(interceptor, "before_route"):
        decision = interceptor.before_route(route_ctx)
        if isinstance(decision, RouteDecision):
            if decision.next_state is None:
                return None   # veto
            return decision.next_state   # redirect — bypass _route()
# Core routing
next_state = self._route(state, verdict, ctx)
# after_route interceptors
for interceptor in self._interceptors:
    if hasattr(interceptor, "after_route"):
        interceptor.after_route(route_ctx)
return next_state
```

Note: `before_route` redirect returns `decision.next_state` directly as `next_state` (bypasses `_route()` entirely — it is a direct state name, not a new verdict).

### Bypass Paths That Intentionally Skip Interceptors

`before_route`/`after_route` dispatch only fires on the evaluate-then-route path:
- Line 355: `return self._execute_sub_loop(...)` — sub-loop (no interception; child executor handles routing)
- Line 378: `return interpolate(state.next, ctx)` — unconditional `next:` transition (deterministic, no interception needed)

Do NOT add interceptor dispatch to these branches.

## API/Interface

New attributes added to `FSMExecutor` (populated by `wire_extensions()` in FEAT-985):

```python
# scripts/little_loops/fsm/executor.py — FSMExecutor.__init__()
self._contributed_actions: dict[str, ActionRunner] = {}    # keyed by action_type string
self._contributed_evaluators: dict[str, Evaluator] = {}    # keyed by evaluate.type string
self._interceptors: list[Any] = []                          # RouteInterceptor protocol instances
```

Types defined in FEAT-983 and consumed here:

```python
# RouteContext — passed to before_route / after_route interceptors
@dataclass
class RouteContext:
    state_name: str
    state: FSMState
    verdict: str
    action_result: ActionResult | None
    eval_result: EvaluationResult | None
    ctx: dict
    iteration: int

# RouteDecision — returned by before_route to redirect or veto routing
@dataclass
class RouteDecision:
    next_state: str | None  # None = veto (halt), str = redirect to that state
```

No public Python API changes — these attributes are internal registries populated by `wire_extensions()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py`
  - `__init__()` after line 125: add three new attributes
  - `_action_mode()` after line 697: add contributed check
  - `_run_action()` lines 428–443: add `elif "contributed"` branch
  - `_evaluate()` before line 605: add contributed evaluator check
  - `_execute_state()` lines 400–402: add interceptor dispatch wrapper

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — add `RouteContext`, `RouteDecision` to re-export block (lines 86–92) and `__all__` (lines 133–178)
- `scripts/little_loops/__init__.py` — add `RouteContext`, `RouteDecision` to package-level public exports and `__all__` (lines 9–14, 39–43)
- `scripts/little_loops/fsm/schema.py:214` — widen `action_type` from `Literal["prompt", "slash_command", "shell", "mcp_tool"] | None` to `str | None`; contributed type strings (e.g., `"webhook"`) currently fail mypy at static type-check time
- `scripts/little_loops/fsm/fsm-loop-schema.json:177` — JSON Schema `enum` for `action_type` lists only 4 known values; a state with `action_type: webhook` fails schema validation at loop load time; relax or remove the enum restriction

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py` — import `RouteContext`, `RouteDecision` from executor (or types.py); these are needed in executor.py at definition time
- `scripts/little_loops/fsm/types.py` — `Evaluator` alias (defined in FEAT-983); imported by executor

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py` — imports `FSMExecutor` directly; `PersistentExecutor` wraps it at line 37; inherits new attributes transparently — no change required
- `scripts/little_loops/cli/loop/testing.py` — imports `FSMExecutor`, `DefaultActionRunner`, `SimulationActionRunner` from executor; no change required
- `scripts/little_loops/fsm/runners.py` — canonical home of `ActionRunner` Protocol (lines 28–49) that contributed runners must implement; imported by executor at line 36
- `scripts/tests/test_ll_loop_execution.py:893,932,973,1016,1060` — constructs `FSMExecutor(fsm)` and calls `executor._evaluate()` directly at lines 921, 960, 1008, 1052, 1093; these call sites are on the explicit-evaluate path and exercise the dispatch branch that the contributed evaluator check inserts before
- `scripts/little_loops/__init__.py` — package-level `__all__` at lines 39–43 must be updated to export `RouteContext` and `RouteDecision` once they exist

### Similar Patterns
- `scripts/little_loops/fsm/executor.py` — `_action_mode()` binary `if/elif` dispatch pattern; this issue converts it to ternary by inserting a contributed-type branch

### Tests
- `scripts/tests/test_fsm_executor.py` — existing `MockActionRunner` at lines 26–86; add contributed action/evaluator dispatch tests using same mock pattern
- `scripts/tests/test_fsm_evaluators.py` — add contributed evaluator registration/dispatch tests

_Wiring pass added by `/ll:wire-issue`:_

**New test classes to write in `scripts/tests/test_fsm_executor.py`:**
- `TestContributedActionDispatch` — contributed `action_type` string returns `"contributed"` from `_action_mode()`; dispatches to registered runner; does not call `self.action_runner`; follow `TestActionType` pattern at lines 234–366
- `TestContributedEvaluatorDispatch` — contributed evaluator type is called before `evaluate()`; result passed through routing; follow `@pytest.mark.parametrize` pattern at `test_fsm_evaluators.py:49–63`
- `TestRouteInterceptors` — `before_route` veto returns `None`; `before_route` redirect bypasses `_route()` and returns `decision.next_state` directly; `after_route` fires after routing; `state.next:` and sub-loop branches do NOT fire interceptors; use `MockActionRunner.always_return()` and assert on `ExecutionResult.final_state`

**New test classes for new dataclasses (in `scripts/tests/test_fsm_schema.py`):**
- `TestRouteContextDataclass` — field defaults and construction; follow `TestEvaluateConfig` pattern at `test_fsm_schema.py:80–179`
- `TestRouteDecisionDataclass` — `next_state=None` (veto) and `next_state="some_state"` (redirect); follow `TestHandoffResult` pattern at `test_handoff_handler.py:103–123`

**At-risk existing tests (verify no breakage after implementation):**
- `scripts/tests/test_fsm_executor.py:234–366` — `TestActionType`; **risk**: breaks if contributed check in `_action_mode()` is inserted in wrong position and intercepts known type strings
- `scripts/tests/test_fsm_executor.py:369–532` — `TestActionTypeMcpTool`; **risk**: breaks if `if/elif/else` restructuring in `_run_action()` disturbs the `mcp_tool` branch
- `scripts/tests/test_ll_loop_execution.py:889–1097` — direct `_evaluate()` calls; **risk**: breaks only if `_contributed_evaluators` is not initialized to `{}` in `__init__()`; verify all 5 call sites still reach their intended dispatch branch

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4040–4053` — `ActionRunner Protocol` section describes the protocol only as a testing/customization tool; after FEAT-984 it also serves as the contributed-actions runtime dispatch interface — update description
- `docs/ARCHITECTURE.md:454–458` — Extension component table omits the three new `_contributed_actions`, `_contributed_evaluators`, `_interceptors` registries; update the extension section after implementation
- `skills/review-loop/reference.md:103–132` — QC-3 `action_type` mismatch check only knows `prompt`, `shell`, `slash_command`, `mcp_tool`; a loop YAML with a contributed `action_type` (e.g., `action_type: webhook`) will be flagged as an error; update QC-3 to treat unknown values as potential contributed types (warn, not error)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:214` — `StateConfig.action_type` is `Literal["prompt", "slash_command", "shell", "mcp_tool"] | None`; contributed type strings fail mypy at static type-check time; must widen to `str | None` (the `from_dict()` method at line 279 already passes through any string at runtime — only the static annotation needs widening)
- `scripts/little_loops/fsm/fsm-loop-schema.json:177` — `action_type` field has `"enum": ["prompt", "slash_command", "shell", "mcp_tool"]`; a state YAML with `action_type: webhook` fails `load_and_validate()` at load time before the executor ever sees it; relax by removing the enum or replacing it with a `oneOf` that allows additional strings

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line references (executor.py):**
- `__init__()` terminal attribute `self._depth: int = 0` confirmed at line 125; new attributes insert after it; line 127 begins `request_shutdown()`
- `_action_mode()` is at lines 693–704 and uses **4 sequential `if` statements** (not if/elif). Actual layout:
  - line 695: `if state.action_type == "mcp_tool":`
  - line 697: `if state.action_type in ("prompt", "slash_command"):`
  - **line 699**: `if state.action_type == "shell":` ← contributed check inserts after this line (issue incorrectly cites 697 as the shell check)
  - lines 701–703: `/`-prefix heuristic
  - line 704: fallthrough `return "shell"`
- `_run_action()` binary dispatch is at lines **431–446** (issue cites 428–443): `if action_mode == "mcp_tool":` at line 431, `else:` at line 440; `action_runner.run()` at lines 441–446
- `_evaluate()` has two dispatch paths:
  - **Default path** (lines 561–596, when `state.evaluate is None`): action-mode-based — contributed evaluator does NOT apply here
  - **Explicit path** (lines 598–629, when `state.evaluate is not None`): `llm_structured` guard at **line 608** (issue cites 605); contributed evaluator check inserts before line 608
- `_execute_state()` route call is at **lines 404–405** (issue cites 400–402): `verdict = eval_result.verdict if eval_result else "yes"` at line 404, `return self._route(state, verdict, ctx)` at line 405

**`types.py` dependency gap (FEAT-983):**
- `scripts/little_loops/fsm/types.py` currently contains only `ExecutionResult`, `ActionResult`, and `EventCallback` — **no `RouteContext`, `RouteDecision`, or `Evaluator`**
- `ActionRunner` Protocol is already defined at `scripts/little_loops/fsm/runners.py:28-49` (not types.py); executor imports it via `from little_loops.fsm.runners import ActionRunner` at line 36
- FEAT-983 must add `RouteContext`, `RouteDecision` (dataclasses) and `Evaluator` (Callable type alias) to `types.py` before FEAT-984 can import them; if FEAT-983 is not yet complete, these must be added in this issue

**Import notes:**
- `executor.py` already imports `Any` from `typing` at line 19 — no new `typing` import needed for the new attributes
- `RouteContext` and `RouteDecision` will be imported from `scripts/little_loops/fsm/types.py` (added by FEAT-983)
- `Evaluator` type alias (`Callable[[EvaluateConfig, str, int, dict], EvaluationResult]`) needs to be defined in `types.py`

**Test pattern to follow:**
- `TestActionType` class at `scripts/tests/test_fsm_executor.py:234-366` is the exact test class structure to model contributed-action dispatch tests after
- For contributed evaluator tests, follow `@pytest.mark.parametrize` pattern at `scripts/tests/test_fsm_evaluators.py:49-63`
- Interceptor veto/redirect/passthrough tests should use `MockActionRunner.always_return()` with a contributed-type state and assert `result` (ExecutionResult) final_state

## Implementation Steps

1. Add `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes to `FSMExecutor.__init__()`
2. Update `_action_mode()` to return `"contributed"` when `state.action_type` is in `_contributed_actions`
3. Add `elif action_mode == "contributed"` dispatch branch in `_run_action()`
4. Insert contributed evaluator check at the top of `_evaluate()` dispatch chain (before existing `llm_structured` guard)
5. Refactor `_execute_state()` routing call-site to wrap `_route()` with `before_route`/`after_route` interceptor dispatch
6. Write unit tests for contributed action dispatch, evaluator dispatch, and interceptor veto/redirect/passthrough paths

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/fsm/schema.py:214` — widen `action_type` from `Literal[...]` to `str | None` so contributed action type strings pass mypy; the runtime `from_dict()` path already handles arbitrary strings
8. Update `scripts/little_loops/fsm/fsm-loop-schema.json:177` — relax or remove `action_type` enum so contributed type values (e.g., `"webhook"`) pass `load_and_validate()` at loop load time
9. Add `RouteContext`, `RouteDecision` to `scripts/little_loops/fsm/__init__.py` re-export block (lines 86–92) and `__all__` (lines 133–178)
10. Add `RouteContext`, `RouteDecision` to `scripts/little_loops/__init__.py` public exports and `__all__` (lines 9–14, 39–43)
11. Verify `test_fsm_executor.py:TestActionType` (lines 234–366) and `TestActionTypeMcpTool` (lines 369–532) pass without modification — confirm contributed check is inserted after the three existing type checks in `_action_mode()`
12. Verify `test_ll_loop_execution.py:889–1097` (5 direct `_evaluate()` call sites) pass without modification — contingent on `_contributed_evaluators = {}` in `__init__()`

## Acceptance Criteria

- [ ] `_contributed_actions`, `_contributed_evaluators`, `_interceptors` initialized in `FSMExecutor.__init__()`
- [ ] `_action_mode()` returns `"contributed"` when `state.action_type` is in `_contributed_actions`
- [ ] `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- [ ] `_evaluate()` calls contributed evaluator before `evaluate()` when type is in `_contributed_evaluators`
- [ ] `before_route` interceptors fire before `_route()` with correct `RouteContext`; veto returns `None`; redirect bypasses `_route()`
- [ ] `after_route` interceptors fire after `_route()` returns
- [ ] Existing action/evaluator dispatch paths unchanged when no contributed types registered
- [ ] `state.next:` and sub-loop branches do NOT fire interceptors

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Medium — touches core execution path, multiple methods
- **Risk**: High — interceptors in the execution path; subtle bugs can break unrelated loop runs
- **Depends On**: FEAT-983 (Protocol and type definitions)
- **Blocks**: FEAT-985 (needs executor attributes to exist before wiring)

## Labels

`feature`, `fsm`, `executor`, `extension-hooks`, `decomposed`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7fe877d-b918-49ec-8638-70727399f5fa.jsonl`
- `/ll:refine-issue` - 2026-04-08T00:09:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2171263a-aabe-46f3-8311-74a1f594a7c9.jsonl`
- `/ll:format-issue` - 2026-04-08T00:05:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a84943e-cf1c-448d-b622-db27d098ac1d.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/MEMORY.md`
