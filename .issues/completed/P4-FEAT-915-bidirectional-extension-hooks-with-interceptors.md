---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Summary

Extend the observe-only extension protocol (FEAT-911) to support bidirectional communication: extensions can intercept operations via `before_`/`after_` hooks, contribute new FSM action types, and register custom evaluators. This transforms extensions from passive observers into active participants in the loop lifecycle.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." FEAT-911 scopes extensions as event consumers only. This issue captures the write-path capabilities needed for extensions that modify loop behavior — not just observe it.

## Current Behavior

FEAT-911 (once implemented) will provide observe-only extensions: they receive events but cannot influence execution. All action types and evaluators must live in the core plugin.

## Expected Behavior

Extensions can:
- Register `before_` and `after_` hooks on key operations (e.g., `before_route`, `before_issue_close`) that can modify or block the operation
- Contribute new FSM action types (e.g., a "slack-notify" extension adds `action: slack` usable in loop YAML)
- Contribute custom evaluators (e.g., a "metrics-eval" extension checks Prometheus thresholds as gate conditions)
- Declare execution priority so ordering conflicts are detected at load time

## Motivation

Observe-only extensions cover dashboards and logging but not the richer ecosystem use cases: approval gates, custom CI integrations, notification actions, or domain-specific evaluators. Bidirectional hooks make the extension API a true integration surface.

## Proposed Solution

1. Extend `LLExtension` Protocol with optional hook methods: `before_route()`, `after_route()`, `before_issue_close()`, etc.
2. Define `ActionProvider` Protocol — extensions that contribute new action types register a name + callable
3. Define `EvaluatorProvider` Protocol — extensions that contribute evaluator types
4. Add priority/ordering to extension registration; detect conflicts at load time
5. Hook dispatch in FSM executor checks for registered interceptors before key operations

## Implementation Steps

1. Extend `LLExtension` Protocol in `extension.py` with optional hook methods (`before_route`, `after_route`, `before_issue_close`)
2. Define `ActionProvider` Protocol — contributed actions register a name + callable
3. Define `EvaluatorProvider` Protocol — contributed evaluators register a name + evaluator
4. Add priority/ordering field to extension registration; implement conflict detection at load time
5. Add hook dispatch to FSM executor — check registered interceptors before key operations
6. Write reference interceptor extension demonstrating the API
7. Verify existing observe-only extensions continue working unchanged

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line anchors for each step:_

1. **Add protocols to `extension.py`** — insert new `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension` Protocols after `LLExtension` definition at `extension.py:50`. Model after `LLExtension:28-50` (`@runtime_checkable`, attribute + method pattern). `before_route`/`after_route` signatures need a `RouteContext` type to be defined first (see step 5). Note: `NoopLoggerExtension:52-68` is the existing reference implementation to keep working.

2. **Define `ActionProvider` contributed-action dict type** — `provided_actions()` return type is `dict[str, ActionRunner]`; `ActionRunner` Protocol is at `fsm/runners.py:27-48`. The contributed action registry in `FSMExecutor` should use a `dict[str, ActionRunner]`-style lookup, checked in `_action_mode():690-701` before the hardcoded fallback chain.

3. **Define `EvaluatorProvider` contributed-evaluator dict type** — do NOT plug into the module-level `evaluate()` function in `fsm/evaluators.py` (it has no executor context). Instead intercept in `FSMExecutor._evaluate()` at `executor.py:611`, before the call to `evaluate()`. If `state.evaluate.type` is in `self._contributed_evaluators`, call that callable directly and skip `evaluate()`. The existing `_NUMERIC_OPERATORS: dict[str, Callable]` at `evaluators.py:83-90` demonstrates the dict-keyed callable registry pattern; store as `self._contributed_evaluators: dict[str, Evaluator] = {}` in `FSMExecutor.__init__()`.

4. **Priority/ordering and conflict detection** — add a `priority: int` (or similar) attribute to `InterceptorExtension`, readable via `getattr(ext, "priority", 0)` following the `event_filter` pattern at `extension.py:165`. Conflict detection runs at load time in `wire_extensions():139-168`. `EventBus` currently uses insertion order only (`events.py:67-129`); sort by priority before registering interceptors.

5. **Hook dispatch insertion points:**
   - `before_route` / `after_route`: insert calls in `FSMExecutor._route():629-673`. `_route()` currently returns `str | None` (next state name); `RouteContext` must capture at minimum `state`, action result, and interpolation context. `RouteDecision` must be definable as a type carrying either a redirected next-state or a veto.
   - `before_issue_close`: insert call in `issue_lifecycle.close_issue():544` **before** the file move (the file is moved/committed around line ~600); the hook receives the issue path and must be able to return a veto (raise or return `False`).

6. **Reference interceptor** — model after `NoopLoggerExtension:52-68` structure; demonstrates implementing `before_route()` and returning `None` (passthrough).

7. **Regression** — existing observe-only extension tests are in `scripts/tests/test_extension.py`. `wire_extensions` must continue to work for classes that only implement `on_event()`; use `isinstance(ext, InterceptorExtension)` checks before calling interceptor methods.

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — add `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension` protocols; add priority/ordering field
- `scripts/little_loops/fsm/executor.py` — add hook dispatch before route and issue-close operations; wire in contributed action types

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/run.py:156-159` — calls `wire_extensions(executor.event_bus, ...)` after `PersistentExecutor` setup; must pass new protocol types through
- `scripts/little_loops/cli/loop/lifecycle.py:257-260` — calls `wire_extensions()` before `executor.resume()`; same wiring path as `run.py`
- `scripts/little_loops/cli/sprint/run.py:388-397` — creates standalone `EventBus`, calls `wire_extensions()`; sprint path also needs extension wiring
- `scripts/little_loops/cli/parallel.py:225-228` — creates standalone `EventBus`, passes to `ParallelOrchestrator`; no action/evaluator hooks used here
- `scripts/little_loops/issue_lifecycle.py:544` — `close_issue()` — emits `"issue.closed"` only **after** the file has been moved and committed; `before_issue_close` hook must be inserted **before** the file move operation in this function
- `scripts/little_loops/__init__.py` — re-exports `LLExtension`; new protocol types must be added here
- `scripts/little_loops/fsm/__init__.py` — re-exports `ActionRunner` (but NOT `Evaluator` yet — it doesn't exist); `Evaluator` type alias + `RouteContext`, `RouteDecision` should be added to `__all__` here

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/runners.py:27-48` — `ActionRunner` Protocol (without `@runtime_checkable`): exact pattern to follow for `ActionProviderExtension.provided_actions()` return type
- `scripts/little_loops/extension.py:28-50` — `LLExtension` with `@runtime_checkable` and an optional attribute alongside the method — follow this pattern for new `InterceptorExtension` Protocol
- `scripts/little_loops/extension.py:139-168` — `wire_extensions()` uses `getattr(ext, "event_filter", None)` to safely read optional Protocol attributes — follow for priority field
- `scripts/little_loops/fsm/evaluators.py:83-90` — `_NUMERIC_OPERATORS: dict[str, Callable]` — the only dict-keyed callable registry in the codebase; use this pattern for the contributed action and evaluator registries
- `scripts/little_loops/fsm/executor.py:690-701` — `_action_mode()` — hardcoded `if/elif` chain over `state.action_type` strings; contributed action types will need to be checked against the registry **before** the fallback chain

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_extension.py` — existing extension Protocol, loading, and `wire_extensions` tests; add `InterceptorExtension`/`ActionProviderExtension`/`EvaluatorProviderExtension` cases here
- `scripts/tests/test_fsm_executor.py` — existing executor tests with `MockActionRunner` (lines 26-86); add interceptor dispatch tests here using same mock pattern
- `scripts/tests/test_fsm_evaluators.py` — existing evaluator tests; add contributed evaluator registration/dispatch tests here
- `scripts/tests/test_events.py` — `EventBus` tests including filter patterns; add priority/ordering conflict detection tests here
- `scripts/tests/test_issue_lifecycle.py` — existing issue lifecycle tests; add `before_issue_close` hook dispatch tests here
- New: `scripts/tests/test_interceptor_extension.py` — dedicated tests for `before_route`/`after_route` and `before_issue_close` dispatch; model after `test_extension.py:35-49` inline recording-class pattern

### Documentation
- `docs/ARCHITECTURE.md` — FSM executor section; extension protocol section
- `docs/reference/API.md` — new extension protocol exports

### Configuration
- N/A

## API/Interface

```python
class LLExtension(Protocol):
    def on_event(self, event: LLEvent) -> None: ...

# Note: use INDEPENDENT Protocols (not InterceptorExtension(LLExtension, Protocol))
# No Protocol-inherits-Protocol pattern exists in this codebase; no isinstance() checks
# against Protocol types exist in production code. Use hasattr()/getattr() in wire_extensions()
# to check for hook methods, same as the event_filter pattern at extension.py:165.

class InterceptorExtension(Protocol):
    def before_route(self, context: RouteContext) -> RouteDecision | None: ...
    def after_route(self, context: RouteContext) -> None: ...
    def before_issue_close(self, info: IssueInfo) -> bool | None: ...

class ActionProviderExtension(Protocol):
    def provided_actions(self) -> dict[str, ActionRunner]: ...

class EvaluatorProviderExtension(Protocol):
    def provided_evaluators(self) -> dict[str, Evaluator]: ...
```

### Concrete Type Definitions

_Added by `/ll:refine-issue` — derived from `executor.py:629-674` and `issue_lifecycle.py:544-632` analysis:_

```python
@dataclass
class RouteContext:
    """Context passed to before_route / after_route interceptors."""
    state_name:    str                       # executor.current_state — executor.py:92
    state:         StateConfig              # route tables and shortcuts — schema.py:180
    verdict:       str                      # routing key: "yes"/"no"/"error"/"partial"/"blocked"/custom — evaluators.py:49
    action_result: ActionResult | None      # None when state has no action field — types.py:52
    eval_result:   EvaluationResult | None  # None when state has no evaluator — evaluators.py:40
    ctx:           InterpolationContext     # ctx.result pre-populated at route time — interpolation.py:37
    iteration:     int                      # 1-based iteration counter — executor.py:96

@dataclass
class RouteDecision:
    """Returned by before_route to redirect or veto a routing transition."""
    next_state: str | None  # str → redirect to this state name; None → veto

# before_route return semantics (RouteDecision | None):
#   None (implicit)              → passthrough — routing proceeds normally
#   RouteDecision("other-state") → redirect to "other-state"
#   RouteDecision(None)          → veto → _route() returns None → _finish("error", "No valid transition")
#
# Three-valued type is required: str | None (the _route() return type) cannot distinguish
# "no intervention" from "explicit veto." RouteDecision wrapper is the minimal addition.

# before_issue_close return semantics (bool | None):
#   None (implicit) → passthrough — closure proceeds
#   False           → veto — close_issue() returns False immediately (consistent with all
#                    -> bool lifecycle functions; callers at issue_manager.py:466 and
#                    parallel/orchestrator.py:861 already branch on the bool return)

# IssueInfo — already exists at issue_parser.py:201-239; imported in issue_lifecycle.py:20
# before_issue_close(self, info: IssueInfo) uses the EXISTING type — no new type needed.
# Fields available to interceptors: path, issue_type, priority, issue_id, title,
# blocked_by, blocks, discovered_by, product_impact, effort, impact, confidence_score,
# outcome_confidence, testable, session_commands, session_command_counts

# Evaluator type — does NOT currently exist; must be CREATED in fsm/types.py
# Follow the EventCallback = Callable[[dict[str, Any]], None] pattern at fsm/types.py:70:
Evaluator = Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]
# EvaluateConfig: fsm/schema.py:26  EvaluationResult: fsm/evaluators.py:40
# InterpolationContext: fsm/interpolation.py:37
# Also add to fsm/__init__.py __all__ (lines 133-178)
```

### Contributed Action Dispatch — Key Architecture Correction

_Added by `/ll:refine-issue` — `_action_mode()` is not the dispatch point; `_run_action()` is:_

The issue says contributed actions "will be checked against the registry before the fallback chain" in `_action_mode():690-701`. This is **half-right**: `_action_mode()` must be updated, but the actual dispatch branch lives in **`_run_action():428-443`** — `_execute_state()` never sees the mode string.

Three precise changes needed:

1. **`FSMExecutor.__init__()`** — add after `self._retry_counts: dict[str, int] = {}` (line 119):
   ```python
   self._contributed_actions: dict[str, ActionRunner] = {}
   ```

2. **`_action_mode()` (line 701)** — add before `return "shell"`:
   ```python
   if state.action_type in self._contributed_actions:
       return "contributed"
   ```

3. **`_run_action()` (line 428-443)** — add `elif` between the `if "mcp_tool":` block (line 428) and the `else:` catch-all (line 437):
   ```python
   elif action_mode == "contributed":
       runner = self._contributed_actions[state.action_type]
       result = runner.run(
           action,
           timeout=state.timeout or self.fsm.default_timeout or 3600,
           is_slash_command=False,
           on_output_line=_on_line,
       )
   ```

### `wire_extensions()` Design Gap

_Added by `/ll:refine-issue` — current `wire_extensions()` only wires `on_event()` to EventBus; interceptors and contributed actions need to reach `FSMExecutor` too:_

Current signature at `extension.py:139`: `wire_extensions(bus: EventBus, config_paths: list[str] | None = None) -> list[LLExtension]`

**Use Option A**: Extend `wire_extensions()` with `executor: FSMExecutor | None = None`. After the existing `bus.register()` loop, add a second pass over extensions:
```python
if executor is not None:
    for ext in extensions:
        if hasattr(ext, "provided_actions"):
            executor._contributed_actions.update(ext.provided_actions())
        if hasattr(ext, "provided_evaluators"):
            executor._contributed_evaluators.update(ext.provided_evaluators())
        if hasattr(ext, "before_route") or hasattr(ext, "after_route") or hasattr(ext, "before_issue_close"):
            executor._interceptors.append(ext)
```
Option B (separate function) was rejected: it requires callers to make two calls and hold a reference to the extensions list.

Callers at `run.py:156-159`, `lifecycle.py:257-260`, `sprint/run.py:388-397` must pass the executor so contributed types reach it. `parallel.py:225-228` does not create an executor, so no change needed there.

### Remaining Implementation Gaps

_Added by `/ll:refine-issue` — four gaps identified from executor and extension source analysis:_

#### 1. `FSMExecutor.__init__()` — All Three New Attributes

The existing "Contributed Action Dispatch" section only specifies `_contributed_actions`. All three attributes must be added together after `self._retry_counts: dict[str, int] = {}` at `executor.py:119`:

```python
# executor.py — after line 119 (self._retry_counts: dict[str, int] = {})
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

`_interceptors` uses `list[Any]` because the interceptor protocol types don't exist at the time `executor.py` imports. Add `Any` to the existing `from typing import ...` import in `executor.py`.

#### 2. `after_route` — Call Site Placement, Not Inside `_route()`

`_route()` (lines 629-674) has **8 return sites** (6× `return self._resolve_route(...)`, 2× `return None`). There is no single terminal return to attach `after_route` to. The single call site is at `executor.py:400-402`:

```python
# executor.py:400-402 (current)
verdict = eval_result.verdict if eval_result else "yes"
return self._route(state, verdict, ctx)
```

Refactor to capture the return value so both `before_route` and `after_route` can be dispatched from `_execute_state()` without touching `_route()` internals:

```python
# executor.py:400-402 (after modification)
verdict = eval_result.verdict if eval_result else "yes"
# before_route interceptors
route_ctx = RouteContext(state_name=self.current_state, state=state, verdict=verdict,
                         action_result=action_result, eval_result=eval_result,
                         ctx=ctx, iteration=self.iteration)
for interceptor in self._interceptors:
    if hasattr(interceptor, "before_route"):
        decision = interceptor.before_route(route_ctx)
        if isinstance(decision, RouteDecision):
            if decision.next_state is None:
                return None   # veto
            verdict = decision.next_state   # redirect — re-route with new verdict? or bypass _route()
# Run core routing
next_state = self._route(state, verdict, ctx)
# after_route interceptors
for interceptor in self._interceptors:
    if hasattr(interceptor, "after_route"):
        interceptor.after_route(route_ctx)
return next_state
```

Note: if `before_route` redirects with `RouteDecision("some-state")`, the implementation must decide whether to pass `"some-state"` as the new `verdict` into `_route()` (re-routing) or to treat it as the direct `next_state` (bypassing routing). The simpler and safer interpretation: `RouteDecision.next_state` is a direct state name (not a verdict), bypassing `_route()` entirely. Update `RouteDecision` semantics accordingly:

```python
# before_route return semantics — REVISED:
#   None (implicit)               → passthrough — routing proceeds normally through _route()
#   RouteDecision("other-state")  → bypass _route(), use "other-state" directly as next_state
#   RouteDecision(None)           → veto → _execute_state() returns None → _finish("error", ...)
```

#### 3. Conflict Detection — Concrete Spec

The issue says "detect conflicts at load time" but gives no definition. No existing precedent in the codebase for extension registration conflicts. Based on analysis of `fsm/validation.py:453,462,487` (the only `raise ValueError` at load time in the FSM subsystem), the concrete spec:

- **What constitutes a conflict**: Two extensions register the same action name key in `_contributed_actions`, or two extensions register the same evaluator type key in `_contributed_evaluators`.
- **Detection location**: In the executor wiring pass inside `wire_extensions()`, before calling `update()`.
- **Pattern** (follow `fsm/validation.py:453`):
  ```python
  for name in ext.provided_actions():
      if name in executor._contributed_actions:
          raise ValueError(
              f"Extension conflict: action '{name}' already registered by another extension"
          )
  executor._contributed_actions.update(ext.provided_actions())
  ```
- **Priority conflicts** are NOT defined — the issue mentions sorting interceptors by priority (not preventing same-priority conflicts). Same-priority interceptors run in load order. Only duplicate-key conflicts (action/evaluator names) require a `raise`.

#### 4. Step 7 Inconsistency — `isinstance` vs `hasattr`

Implementation Step 7 (regression) says: _"use `isinstance(ext, InterceptorExtension)` checks before calling interceptor methods."_

This conflicts with the API/Interface section which explicitly states: _"No isinstance() checks against Protocol types exist in production code. Use hasattr()/getattr() in wire_extensions()."_

**Correct approach**: use `hasattr(ext, "before_route")`, `hasattr(ext, "after_route")`, etc. — not `isinstance(ext, InterceptorExtension)`. The `wire_extensions()` design section already shows the correct `hasattr` pattern. Step 7 is incorrect and should not be followed.

#### 5. `FSMExecutor.__init__()` — Correct Insertion Point

The existing spec says "add after `self._retry_counts: dict[str, int] = {}` at `executor.py:119`." This is imprecise — `_retry_counts` at line 119 is followed by `_prev_state` (line 121) and `_depth` (line 125). The three new attributes belong **after line 125** (the end of `__init__`), as a named block:

```python
# executor.py — after line 125 (self._depth: int = 0)
# Extension hook registries — populated by wire_extensions()
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

#### 6. `_action_mode()` — Two `return "shell"` Paths

The method at lines 690–701 has sequential `if` statements (not `elif`). There are two `return "shell"` paths: one explicit at line 697 (`if state.action_type == "shell": return "shell"`) and one implicit fallback at line 701 (`return "shell"`). The contributed-action check goes **after the explicit shell check (697) and before the `/`-prefix heuristic (699)**:

```python
# executor.py — after line 697 (if state.action_type == "shell": return "shell")
if state.action_type in self._contributed_actions:
    return "contributed"
# Heuristic: / prefix = slash_command (prompt mode)  ← line 699, unchanged
```

#### 7. `_run_action()` — Binary Dispatch Becomes Ternary

Current dispatch at lines 428–443 is binary: `if action_mode == "mcp_tool": ... else: action_runner.run(...)`. Convert to ternary by inserting `elif` before the existing `else`:

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

#### 8. Interceptor Bypass Paths in `_execute_state()`

`before_route`/`after_route` dispatch at lines 401-402 only fires on the **evaluate-then-route path**. Two other exit paths bypass interceptors entirely:
- Line 355: `return self._execute_sub_loop(...)` — sub-loop branch (no routing)
- Line 378: `return interpolate(state.next, ctx)` — unconditional `next:` transition

This is intentional: `state.next` transitions are deterministic and need no interception. Sub-loop exits delegate routing to the child executor. Implementers should not add interceptor dispatch to these branches.

#### 9. `fsm/types.py` — `Evaluator` Alias Insertion Point

`Evaluator` does not exist in any file under `scripts/little_loops/fsm/`. The only existing alias is `EventCallback = Callable[[dict[str, Any]], None]` at `fsm/types.py:70`. Add the new alias directly after line 70:

```python
# fsm/types.py — after line 70
Evaluator = Callable[["EvaluateConfig", str, int, "InterpolationContext"], "EvaluationResult"]
```

Use forward-reference strings to avoid circular imports (`EvaluateConfig` lives in `schema.py`, `EvaluationResult` in `evaluators.py`, `InterpolationContext` in `interpolation.py`).

#### 11. Contributed Evaluator Intercept — Correct Insertion Point Is Line 605, Not 611

Implementation Step 3 says "intercept in `FSMExecutor._evaluate()` at `executor.py:611`, before the call to `evaluate()`." This is imprecise. The actual code at lines 605–616 is:

```python
if state.evaluate.type == "llm_structured" and not self.fsm.llm.enabled:  # 605
    result = EvaluationResult(...)  # 606-609
else:
    result = evaluate(...)  # 611-616
```

The contributed evaluator check must be inserted **before line 605** (not 611) so it also bypasses the `llm_structured`/`--no-llm` guard. Convert the existing `if` to `elif`:

```python
# executor.py — before line 605 (insert new if, demote existing if to elif)
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

#### 12. `wire_extensions()` Missing `hasattr(on_event)` Guard

`ExtensionLoader.load_all()` accepts any class (its return type annotation `list[LLExtension]` is not enforced — it uses `list[Any]` internally; no `isinstance(ext, LLExtension)` check is performed). An extension that implements only `InterceptorExtension`, `ActionProviderExtension`, or `EvaluatorProviderExtension` — without `on_event()` — will still pass through `load_all()`.

The current `wire_extensions()` loop (lines 157–165) calls `bus.register(_make_callback(ext))` unconditionally for every loaded extension. `_make_callback` creates a closure that calls `e.on_event(...)` at dispatch time. If `ext` has no `on_event()`, this raises `AttributeError` on the first event emitted.

Fix: add `hasattr(ext, "on_event")` guard before calling `bus.register()`:

```python
# extension.py:157-165 — add hasattr guard
for ext in extensions:
    if hasattr(ext, "on_event"):
        bus.register(_make_callback(ext), filter=getattr(ext, "event_filter", None))
```

This is required alongside the second pass that wires interceptors/contributed types to the executor.

#### 10. Export Updates Required in Two `__init__.py` Files

**`fsm/__init__.py`** — add to the import block (from `executor.py` or new `types.py` entries) and to `__all__` (lines 133–178):
- `RouteContext` — from `executor.py` (or new `fsm/types.py` if defined there)
- `RouteDecision` — same
- `Evaluator` — from `fsm/types.py`

**`little_loops/__init__.py`** — add to the `from little_loops.extension import (...)` block and to `__all__` under `# extensions` (lines 39–43):
- `InterceptorExtension`
- `ActionProviderExtension`
- `EvaluatorProviderExtension`

#### 13. Priority Sort — Exact Implementation in `wire_extensions()`

_Added by `/ll:refine-issue` — the issue says "sort by priority before registering interceptors" but gives no code:_

Codebase sort idiom (see `dependency_graph.py:135`, `git_operations.py:412`) uses concrete attribute access. Since extension `priority` is optional (may not exist), use `getattr` with default:

```python
# extension.py — between line 156 (load_all return) and line 157 (for ext in extensions:)
extensions = sorted(extensions, key=lambda e: getattr(e, "priority", 0))
```

This sort runs once, before both the `bus.register` loop and the second (interceptor/contributed-type) pass, so event dispatch order and interceptor dispatch order are consistent. Interceptors with lower priority values fire first (ascending sort matches codebase convention in `dependency_graph.py:135`).

#### 14. `before_issue_close` Insertion Point — Final Confirmation

_Added by `/ll:refine-issue` — resolves earlier ambiguity between "line 544" and "line 596":_

- Line 544: `def close_issue(` — function signature, not the insertion point
- Line 595: `logger.info(f"Closing {info.issue_id}: {close_status} (reason: {close_reason})")` — last line before I/O
- Line 596: blank line — **hook dispatch goes here**
- Line 597: `try:` — first file I/O begins inside this block
- Line 602: `_prepare_issue_content()` — reads original file
- Line 605: `_move_issue_to_completed()` — actual file move
- Lines 618–627: `event_bus.emit({"event": "issue.closed", ...})` — emitted **after** file move

The `before_issue_close` hook must be called between lines 595 and 597 (replacing blank line 596). The `issue.closed` event at lines 618–627 fires after the move and is unaffected.

#### 15. `evaluate()` Keyword Argument Names — For Test Authoring

_Added by `/ll:refine-issue` — confirms Evaluator type alias parameter order:_

The actual `evaluate()` call at `executor.py:611-616` uses keyword args:
```python
result = evaluate(
    config=state.evaluate,
    output=eval_input,
    exit_code=action_result.exit_code if action_result else 0,
    context=ctx,
)
```
The `Evaluator = Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]` type alias matches this positional order (`config`, `output`, `exit_code`, `context`). When writing tests for contributed evaluators, mock the callable to accept these 4 positional args in this order.

## Use Case

A compliance extension intercepts `before_issue_close` and blocks closure unless an external approval system has signed off. A Slack extension contributes an `action: slack-notify` type that loops use to send messages at specific states.

## Acceptance Criteria

- [ ] `InterceptorExtension` Protocol defined with at least `before_route` and `after_route`
- [ ] `ActionProviderExtension` Protocol defined; contributed actions usable in loop YAML
- [ ] `EvaluatorProviderExtension` Protocol defined; contributed evaluators callable from FSM executor
- [ ] `RouteContext` and `RouteDecision` types defined as `@dataclass` in `executor.py` (or `fsm/types.py`)
- [ ] `Evaluator` type alias added to `fsm/types.py` after `EventCallback` (line 70)
- [ ] `wire_extensions()` extended with `executor: FSMExecutor | None = None`; second pass wires interceptors and contributed types to executor
- [ ] `on_event` `hasattr` guard added to `bus.register()` loop in `wire_extensions()` (line 157)
- [ ] `before_issue_close` hook dispatch implemented in `issue_lifecycle.close_issue()` before file move at line 605
- [ ] Conflict detection (duplicate action/evaluator name keys) raises `ValueError` at load time in `wire_extensions()`
- [ ] Extension priority/ordering enforced at registration time
- [ ] New protocol types exported from `scripts/little_loops/__init__.py` and `fsm/__init__.py`
- [ ] Existing observe-only extensions continue to work unchanged
- [ ] At least one reference interceptor extension demonstrates the API

## Impact

- **Priority**: P4 - Strategic; depends on FEAT-911 being implemented first
- **Effort**: Large - Extends core execution path with hook dispatch
- **Risk**: High - Interceptors in the execution path add complexity and potential for misbehaving extensions to break loops
- **Breaking Change**: No (additive to FEAT-911's extension Protocol)
- **Depends On**: FEAT-911

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM executor architecture and action runner protocol |
| architecture | docs/reference/API.md | Extension type exports and public API surface |

## Labels

`feat`, `extension-api`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- FEAT-911 is COMPLETED — `extension.py` has `LLExtension` Protocol with `on_event()` only; no bidirectional hooks
- No `InterceptorExtension`, `ActionProviderExtension`, or `EvaluatorProviderExtension` protocols defined ✓
- `extension.py` does NOT import `ActionRunner`; `ActionRunner` Protocol is defined at `fsm/runners.py:27-48` and imported into `fsm/executor.py:35-40`; the contributed action registry will live on a new `FSMExecutor._contributed_actions: dict[str, ActionRunner] = {}` attribute
- Issue accurately describes the gap between observe-only FEAT-911 and write-path capabilities

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-03_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 56/100 → LOW

### Concerns
- `RouteContext` type is underspecified — issue says "at minimum: state, action result, interpolation context" but exact fields/types are not defined. Designing this type is a first-task prerequisite.
- `RouteDecision` type likewise not defined — "redirected next-state or veto" needs a concrete type before the Protocol signatures are valid.
- Veto mechanism for `before_issue_close` is unresolved ("raise or return False") — two competing approaches; pick one before coding hook dispatch.

### Outcome Risk Factors
- **Multi-subsystem blast radius**: changes touch extension loading, FSM routing, FSM action dispatch, and issue lifecycle. A subtle type error in RouteContext/RouteDecision could break unrelated loop execution paths.
- **Protocol multi-inheritance**: `InterceptorExtension(LLExtension, Protocol)` — `@runtime_checkable` with Protocol multi-inheritance can have surprising isinstance behavior in Python 3.11; verify before committing to the class hierarchy.
- **No interceptor precedent in codebase**: this creates a new execution hook mechanism with no existing reference to validate against; budget extra iteration time.

### Resolved by `/ll:refine-issue` (2026-04-03)

**RouteContext fields** — fully specified from `executor.py:629-674` analysis. See `## API/Interface → Concrete Type Definitions` for the full `@dataclass` definition. Both `action_result` and `eval_result` must be `| None` because states with no `action` field can still trigger routing (executor.py:401).

**RouteDecision type** — `before_route` returns `RouteDecision | None` (three-valued). `str | None` is insufficient because it cannot distinguish "interceptor did not intervene" from "interceptor vetoed." `RouteDecision(next_state=None)` = veto; `RouteDecision(next_state="foo")` = redirect; Python `None` return = passthrough.

**Veto mechanism for `before_issue_close`** — use **`return False`**:
- All lifecycle functions in `issue_lifecycle.py` use `-> bool` / `return False` for failure; none use `raise` for control flow
- Both callers (`issue_manager.py:466`, `parallel/orchestrator.py:861`) already branch on the bool return — no caller changes needed
- Hook return type: `bool | None` — `None` = passthrough, `False` = veto
- Insertion point: `issue_lifecycle.py:596` — between `logger.info` (line 595) and `try:` (line 597), before any file I/O

**Protocol multi-inheritance concern** — **resolved: use independent Protocols**:
- No `isinstance()` checks against Protocol types exist in production code anywhere
- No Protocol-inheriting-Protocol pattern exists in the codebase (only two Protocols: `LLExtension` at `extension.py:28` and `ActionRunner` at `runners.py:27`, both single-parent)
- Concrete implementors satisfy protocols structurally (no explicit base declaration)
- Solution: define `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension` as independent `Protocol` classes; detect them in `wire_extensions()` via `hasattr()` / `getattr()`, same as `event_filter` at `extension.py:165`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-07
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-983: Extension Protocol and Type Definitions
- FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors
- FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Status

**Decomposed** | Created: 2026-04-02 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`
- `/ll:format-issue` - 2026-04-06T04:34:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42b4ffbf-f1c8-49af-9c70-592b7bd6958e.jsonl`
- `/ll:confidence-check` - 2026-04-03T14:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:35:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T13:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:29:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T12:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:23:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T11:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:17:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T10:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T09:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:06:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:01:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T08:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:52:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T07:46:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T07:42:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:23:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:29:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-04-03T08:36:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
