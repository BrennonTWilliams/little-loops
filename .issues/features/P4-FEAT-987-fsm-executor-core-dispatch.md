---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 86
parent_issue: FEAT-984
---

# FEAT-987: FSMExecutor Core Hook Dispatch (Attributes + Action/Evaluator/Interceptor Dispatch)

## Summary

Add `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes to `FSMExecutor.__init__()`, then wire them into `_action_mode()`, `_run_action()`, `_evaluate()`, and `_execute_state()`. This is the runtime dispatch half of the FEAT-915 extension system.

## Use Case

A developer building a custom FSM loop extension registers a contributed action type (e.g., `action_type: webhook`) on an `FSMExecutor` instance. At runtime the executor detects the contributed type, dispatches to their `ActionRunner` implementation, and fires registered route interceptors — enabling per-loop routing observability or redirect overrides without touching core infrastructure.

## Parent Issue

Decomposed from FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Context

FEAT-983 defines the Protocol and type foundations (`RouteContext`, `RouteDecision`, `Evaluator`). This issue implements the `FSMExecutor` changes needed to actually dispatch to registered extensions at runtime. `wire_extensions()` (FEAT-985) will populate these registries; this issue only defines them and uses them.

## Motivation

This issue is the runtime dispatch half of the FEAT-915 extension system. Without these attribute initializations and dispatch hooks, contributed actions, evaluators, and interceptors registered via `wire_extensions()` (FEAT-985) have nowhere to dispatch to — the extension framework exists in protocol form (FEAT-983) but produces no runtime behavior. Completing this issue unblocks FEAT-988 (integration tests + wiring validation) and ultimately enables third-party FSM loop extensions to function end-to-end.

## Current Behavior

`FSMExecutor` has no concept of contributed action types or evaluators. `_action_mode()` uses a hardcoded sequential-if chain. Route interceptors do not exist.

## Expected Behavior

- `FSMExecutor.__init__()` initializes three new attributes
- `_action_mode()` checks `_contributed_actions` before fallback to shell
- `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- `_evaluate()` dispatches to contributed evaluator before built-in `evaluate()`
- `before_route`/`after_route` interceptors fire around `_route()` in `_execute_state()`

## Proposed Solution

### 1. New Attributes in `FSMExecutor.__init__()`

Add after `self._depth: int = 0` at `executor.py:152`:

```python
# Extension hook registries — populated by wire_extensions()
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

`Any` is already imported at `executor.py:19` — no new import needed.

### 2. Contributed Action Dispatch

**`_action_mode()` (lines 720–731)** — the method uses 4 sequential `if` statements:
- line 722: `if state.action_type == "mcp_tool":`
- line 724: `if state.action_type in ("prompt", "slash_command"):`
- line 726: `if state.action_type == "shell":` ← insert after this line
- lines 729–730: `/`-prefix heuristic
- line 731: fallthrough `return "shell"`

Insert after line 726:

```python
if state.action_type in self._contributed_actions:
    return "contributed"
```

**`_run_action()` (lines 458–473)** — current dispatch: `if action_mode == "mcp_tool":` at line 458, `else:` at line 467. Convert to:

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

**`_evaluate()` (explicit path, lines 625–657)** — insert contributed evaluator check **before line 635** (`llm_structured` guard), demoting the existing `if` to `elif`:

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

Do NOT apply to the default path (lines 561–596, `state.evaluate is None`).

### 4. `before_route` / `after_route` Interceptor Dispatch

Refactor `executor.py:431–432` (the single `_route()` call site in `_execute_state()`):

```python
# executor.py:431–432 (after modification)
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

**Bypass paths that intentionally skip interceptors** (do NOT add dispatch here):
- `executor.py:384`: `return self._execute_sub_loop(...)` — sub-loop
- `executor.py:408`: `return interpolate(state.next, ctx)` — unconditional `next:` transition

## Implementation Steps

1. Add `_contributed_actions`, `_contributed_evaluators`, `_interceptors` attributes to `FSMExecutor.__init__()`
2. Add import for `Evaluator` from `scripts/little_loops/fsm/types.py` (added by FEAT-983). `RouteContext` and `RouteDecision` are already defined in `executor.py` (lines 53–76) — no additional import needed for them.
3. Update `_action_mode()` to check `_contributed_actions` and return `"contributed"` mode
4. Add `elif action_mode == "contributed"` dispatch branch in `_run_action()`
5. Prepend contributed evaluator lookup in `_evaluate()` before the existing `llm_structured` guard
6. Wrap `_route()` call in `_execute_state()` with `before_route`/`after_route` interceptor loops
7. Run `TestActionType`, `TestActionTypeMcpTool`, and direct `_evaluate()` test suites to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Write `TestContributedActionDispatch` tests in `test_fsm_executor.py` — verify `_action_mode()` → `"contributed"` and `_run_action()` contributed dispatch
9. Write `TestContributedEvaluatorDispatch` tests — verify `_evaluate()` contributed callable dispatch and fallback path
10. Write `TestInterceptorDispatch` tests — verify `before_route`/`after_route` firing, veto, redirect, passthrough, and bypass paths (`state.next:`, sub-loop)
11. **Note — sub-loop child constructor** (`executor.py:349–354`): `_execute_sub_loop()` builds a child `FSMExecutor` and does NOT forward `_contributed_actions`, `_contributed_evaluators`, or `_interceptors`. This is intentional per acceptance criteria (sub-loops bypass interceptors), but means contributed action/evaluator types also won't be available in sub-loops. If cross-loop extension dispatch is ever needed, this constructor must be updated. No change required for FEAT-987.

## API/Interface

New attributes added to `FSMExecutor` (populated at runtime by `wire_extensions()` from FEAT-985):

```python
# FSMExecutor.__init__() — new extension hook registries
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

Interceptor protocol (defined in FEAT-983, `scripts/little_loops/extension.py:58–75` as `InterceptorExtension`; `RouteContext`/`RouteDecision` defined at `executor.py:53–76`):

```python
# Optional methods — interceptor implements whichever hooks apply
def before_route(ctx: RouteContext) -> RouteDecision | None: ...  # None = no redirect
def after_route(ctx: RouteContext) -> None: ...
```

`RouteDecision.next_state = None` vetoes routing (executor returns `None`). A non-`None` `next_state` redirects, bypassing `_route()` entirely.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py`
  - `__init__()` after line 152: add three new attributes
  - `_action_mode()` after line 726: add contributed check
  - `_run_action()` lines 458–473: add `elif "contributed"` branch
  - `_evaluate()` before line 635: add contributed evaluator check
  - `_execute_state()` lines 431–432: add interceptor dispatch wrapper

### Imports Needed

- `Evaluator` type alias from `scripts/little_loops/fsm/types.py` (added by FEAT-983); currently `executor.py:44` only imports `ActionResult, EventCallback, ExecutionResult` from `types`
- `RouteContext` and `RouteDecision` are **already defined in `executor.py`** (lines 53–76 as module-level dataclasses) — no import needed
- `ActionRunner` already imported via `from little_loops.fsm.runners import ActionRunner` at line 36
- `Any` already imported at line 19

### Dependent Files (read-only — no changes needed)

- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` **wraps** `FSMExecutor` (composition, not subclass); holds executor instance at `self._executor`. New attributes live on `self._executor`, not on `PersistentExecutor` itself — no conflicts. Note: resume path at `persistence.py:486–501` manually restores specific `FSMExecutor` attributes by name; the three new attributes are NOT in that list and will reset to `{}` / `[]` on resume (this is intentional — FEAT-985 `wire_extensions()` re-populates them).
- `scripts/little_loops/cli/loop/testing.py` — imports `FSMExecutor`; no change required
- `scripts/little_loops/fsm/runners.py` — canonical home of `ActionRunner` Protocol
- `scripts/little_loops/extension.py` — defines `InterceptorExtension` Protocol (lines 58–75) with `before_route`/`after_route`/`before_issue_close` methods; also defines `RouteContext` and `RouteDecision` re-exports. Extension detection in `wire_extensions` uses `hasattr()`, consistent with the dispatch approach here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `FSMExecutor`, `ActionRunner`, `RouteContext`, `RouteDecision`, `PersistentExecutor`, `Evaluator` from `executor.py` and `types.py`; read-only
- `scripts/little_loops/__init__.py` — re-exports `InterceptorExtension`, `wire_extensions`, `ActionProviderExtension`, `EvaluatorProviderExtension` from `extension.py`; read-only
- `scripts/little_loops/cli/loop/run.py` — instantiates `PersistentExecutor` (indirectly constructs `FSMExecutor`), calls `wire_extensions`; read-only
- `scripts/little_loops/cli/loop/lifecycle.py` — same pattern as `run.py`; read-only
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_extensions`; read-only
- `scripts/little_loops/cli/parallel.py` — calls `wire_extensions`; read-only

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` subclasses `FSMExecutor`; verify new attributes are inherited transparently without override conflicts

### Tests

**Existing tests that must pass unchanged (regression):**
- `scripts/tests/test_fsm_executor.py` — `TestActionType` (lines 238–370): must pass unchanged; insert contributed check after existing type checks
- `scripts/tests/test_fsm_executor.py` — `TestActionTypeMcpTool` (lines 373–536): must pass unchanged; if/elif restructuring must not disturb `mcp_tool` branch
- `scripts/tests/test_ll_loop_execution.py` — 5 direct `_evaluate()` calls (lines 921, 960, 1008, 1052, 1093): pass only if `_contributed_evaluators = {}` at init
- `scripts/tests/test_extension.py` — `TestNewProtocols` (line 288): structural compliance check for `InterceptorExtension` — verify `before_route`/`after_route` dispatch matches protocol shape

**Additional existing tests exercised indirectly (safe, no changes needed):**

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py:552` — `TestPersistentExecutor` (~40 tests): all call `executor.run()` through real `PersistentExecutor` → real `FSMExecutor.__init__()`; new attributes initialize to empty, interceptor loops add zero iterations — safe
- `scripts/tests/test_ll_loop_integration.py:75` — `TestMainLoopIntegration`: end-to-end CLI path through real `FSMExecutor`; same reasoning — safe

**New tests to write (no coverage currently exists):**

_Wiring pass added by `/ll:wire-issue`:_
- New `TestContributedActionDispatch` class in `scripts/tests/test_fsm_executor.py` — follow `TestActionType` fixture factory pattern + `MockActionRunner` pattern (lines 31–90); cover:
  - `_action_mode()` returns `"contributed"` when `state.action_type` is in `_contributed_actions`
  - `_action_mode()` returns `"shell"` when type is NOT registered (regression)
  - `_run_action()` calls `contributed_runner.run(action, timeout=..., is_slash_command=False, on_output_line=...)` with correct args
  - Contributed runner's `ActionResult` flows through routing
- New `TestContributedEvaluatorDispatch` in `scripts/tests/test_ll_loop_execution.py` — follow direct `_evaluate()` call pattern (lines 900–926); cover:
  - `_evaluate()` dispatches to contributed callable when type is in `_contributed_evaluators`
  - Built-in `evaluate()` is NOT called when contributed evaluator handles type
  - Contributed callable receives `(state.evaluate, eval_input, exit_code, ctx)` in correct order
  - Fallback to existing path when type is NOT in `_contributed_evaluators`
- New `TestInterceptorDispatch` class in `scripts/tests/test_fsm_executor.py` — follow collaborator dispatch pattern at lines 2548–2589; inject via `executor._interceptors = [mock_interceptor]` post-construction; cover:
  - `before_route` called with `RouteContext` containing correct `state_name`, `verdict`, `action_result`, `eval_result`, `iteration`
  - `before_route` returning `RouteDecision("some_state")` bypasses `_route()` and routes to `"some_state"`
  - `before_route` returning `RouteDecision(None)` vetoes — `_execute_state` returns `None`, loop terminates with `"error"`
  - `before_route` returning `None` (passthrough) — `_route()` still called
  - `after_route` called after `_route()` with correct `RouteContext`
  - Multiple interceptors — both `before_route` called in order; first `RouteDecision` short-circuits remaining
  - `state.next:` unconditional branch does NOT call interceptors
  - Sub-loop branch does NOT call interceptors

### Documentation
- N/A — internal `FSMExecutor` dispatch changes; no public-facing documentation update needed

### Configuration
- N/A — extension registries populated at runtime via `wire_extensions()`; no config schema changes

## Verification

After implementation, verify these existing tests still pass without modification:

- `scripts/tests/test_fsm_executor.py:238–370` — `TestActionType`; at-risk if contributed check intercepts known type strings (insert after the three existing checks)
- `scripts/tests/test_fsm_executor.py:373–536` — `TestActionTypeMcpTool`; at-risk if `if/elif/else` restructuring disturbs the `mcp_tool` branch
- `scripts/tests/test_ll_loop_execution.py:921,960,1008,1052,1093` — 5 direct `_evaluate()` calls; pass only if `_contributed_evaluators = {}` in `__init__()`

## Acceptance Criteria

- [ ] `_contributed_actions`, `_contributed_evaluators`, `_interceptors` initialized in `FSMExecutor.__init__()`
- [ ] `_action_mode()` returns `"contributed"` when `state.action_type` is in `_contributed_actions`
- [ ] `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- [ ] `_evaluate()` calls contributed evaluator before `evaluate()` when type is in `_contributed_evaluators`
- [ ] `before_route` interceptors fire before `_route()` with correct `RouteContext`; veto returns `None`; redirect bypasses `_route()`
- [ ] `after_route` interceptors fire after `_route()` returns
- [ ] Existing action/evaluator dispatch paths unchanged when no contributed types registered
- [ ] `state.next:` and sub-loop branches do NOT fire interceptors
- [ ] All three existing test suites (TestActionType, TestActionTypeMcpTool, direct _evaluate() calls) pass

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small-Medium — surgical edits to 5 specific locations in executor.py
- **Risk**: High — interceptors in the execution path; subtle bugs can break unrelated loop runs
- **Depends On**: FEAT-983 (Protocol and type definitions for RouteContext, RouteDecision, Evaluator)
- **Blocks**: FEAT-988 (tests + wiring), FEAT-985 (wire_extensions())

## Labels

`feature`, `fsm`, `executor`, `extension-hooks`, `decomposed`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:wire-issue` - 2026-04-08T02:44:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f501fbe-c8b1-423a-afe0-0db40d370b5b.jsonl`
- `/ll:refine-issue` - 2026-04-08T02:39:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99ccfc8b-d45d-41ce-bc44-dbb43c9bb507.jsonl`
- `/ll:format-issue` - 2026-04-08T02:35:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fcc3b663-4002-4345-93fd-f9fde61a5879.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f3aa3c7-ca33-4c8b-b435-c5b746906130.jsonl`
