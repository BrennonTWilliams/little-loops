---
id: FEAT-1456
type: FEAT
priority: P3
status: done
parent: FEAT-1452
discovered_date: 2026-05-12
completed_at: 2026-05-12T03:49:52Z
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1456: LLHookIntentExtension Protocol, Registry, Wiring, and Tests

## Summary

Add `LLHookIntentExtension` as a new `@runtime_checkable` Protocol in `extension.py`, add `_HOOK_INTENT_REGISTRY` + `_register_hook_intents()` to `hooks/__init__.py`, update `wire_extensions()` to detect hook intent handlers via `hasattr()`, export from `little_loops/__init__.py`, and write all required tests.

## Parent Issue

Decomposed from FEAT-1452: LLHookIntentExtension Protocol and Extension Registry Wiring

## Depends On

- FEAT-1448 (types `LLHookEvent`/`LLHookResult` must exist before the Protocol references them)

## Scope

Covers FEAT-1452 / FEAT-1116 Implementation Steps 9 (Extension Registry Wiring), plus implementation steps 1–6 and 8 from FEAT-1452.

**Decision (from FEAT-1452)**: Option A selected — `provided_hook_intents()` mapping method + module-level registry. Mirrors `ActionProviderExtension.provided_actions()` (`extension.py:85`) and `EvaluatorProviderExtension.provided_evaluators()` (`extension.py:96`).

## Files to Modify

- `scripts/little_loops/extension.py` — add `LLHookIntentExtension` Protocol after line 98 (end of `EvaluatorProviderExtension`), add new detection pass after line 254 in `wire_extensions()`
- `scripts/little_loops/hooks/__init__.py` — add `_HOOK_INTENT_REGISTRY`, `_register_hook_intents()`, update `_dispatch_table()` (lines 45–53)
- `scripts/little_loops/__init__.py` — export `LLHookIntentExtension` (extend `from little_loops.extension import (...)` at lines 9–17, add to `__all__` under `# extensions` at lines 61–67)
- `scripts/tests/test_extension.py` — add to `TestNewProtocols` (lines 465–568) and `TestWireExtensions` (lines 135–463)
- `scripts/tests/test_hook_intents.py` — add `_dispatch_table()` merge test in `TestHooksMainModule` (starts at line 247)

## Proposed Solution

### Step 1 — Add Protocol to `extension.py`

Add after line 98 (end of `EvaluatorProviderExtension`, before `NoopLoggerExtension` at line 101):

```python
@runtime_checkable
class LLHookIntentExtension(Protocol):
    """Protocol for extensions that contribute hook intent handlers.

    Detected via hasattr() in wire_extensions(). Returned handlers are
    merged into the dispatch table consulted by little_loops.hooks.main_hooks().
    """

    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

Add import inside `TYPE_CHECKING` block at `extension.py:24–28`:
```python
from little_loops.hooks.types import LLHookEvent, LLHookResult
```

Add at module top: `from collections.abc import Callable` — **confirmed not present** in `extension.py` (top-level imports at lines 1–22; `runtime_checkable` already imported at line 19).

### Step 2 — Add registry to `hooks/__init__.py`

`Callable`, `LLHookEvent`, and `LLHookResult` are already imported at module top (`hooks/__init__.py:33` and `:36`); no new imports required.

Add module-level registry and helpers (place near other module-level state):

```python
_HOOK_INTENT_REGISTRY: dict[str, Callable[[LLHookEvent], LLHookResult]] = {}


def _register_hook_intents(handlers: dict[str, Callable[[LLHookEvent], LLHookResult]]) -> None:
    for name, handler in handlers.items():
        if name in _HOOK_INTENT_REGISTRY:
            raise ValueError(f"Extension conflict: hook intent '{name}' already registered by another extension")
        _HOOK_INTENT_REGISTRY[name] = handler
```

Update `_dispatch_table()` (currently lines 45–53) to merge `_HOOK_INTENT_REGISTRY` after built-ins (built-ins win on collision). The current implementation imports `pre_compact` and `session_start` lazily inside the function and references `pre_compact.handle` / `session_start.handle` — preserve that pattern:

```python
def _dispatch_table() -> dict[str, Callable[[LLHookEvent], LLHookResult]]:
    from little_loops.hooks import pre_compact, session_start

    built_ins = {
        "pre_compact": pre_compact.handle,
        "session_start": session_start.handle,
    }
    return {**_HOOK_INTENT_REGISTRY, **built_ins}  # built-ins shadow extensions
```

### Step 3 — Update `wire_extensions()`

`wire_extensions()` currently spans lines 188–258 with two passes: EventBus registration (lines 221–223), then FSM-executor unwrapping (lines 225–231) and the FSM-executor pass for actions/evaluators/interceptors (lines 233–254). Insert the new hook-intent detection block as an **independent third pass after line 254** (before the final `if extensions:` block at line 256). It is independent of the `executor is None` guard since hooks have no executor dependency:

```python
for ext in extensions:
    if hasattr(ext, "provided_hook_intents"):
        from little_loops.hooks import _register_hook_intents
        _register_hook_intents(ext.provided_hook_intents())
```

### Step 4 — Export from `little_loops/__init__.py`

Mirror the existing extension-Protocol export pattern (NOT the `LLHookEvent` / `LLHookResult` hook-types pattern, since `LLHookIntentExtension` lives in `extension.py`, not `hooks/types.py`):

- Extend the existing `from little_loops.extension import (...)` block at lines 9–17 to include `LLHookIntentExtension` (kept alphabetical with the other Protocols).
- Add `"LLHookIntentExtension"` to `__all__` under the `# extensions` comment at lines 61–67 (between `InterceptorExtension` and `LLExtension`).

## Integration Map

### Protocol additions (`scripts/little_loops/extension.py`)

- **Existing Protocols** (lines 35–98) follow a consistent pattern:
  - `LLExtension` (35–56) — only Protocol decorated `@runtime_checkable`
  - `InterceptorExtension` (59–77) — no decorator; detected per-method via `hasattr()`
  - `ActionProviderExtension` (79–88) — no decorator; detected via `hasattr(ext, "provided_actions")` (method signature at `extension.py:85`)
  - `EvaluatorProviderExtension` (90–98) — no decorator; detected via `hasattr(ext, "provided_evaluators")` (method signature at `extension.py:96`)
- `LLHookIntentExtension` should be `@runtime_checkable` per FEAT-1116 Decision 2; mirror `LLExtension`'s decorator + docstring style.

### Wiring (`scripts/little_loops/extension.py:wire_extensions` lines 188–258)

- Two-pass structure: (1) EventBus pass at lines 221–223; (2) FSM-executor pass at lines 233–254 (preceded by executor unwrapping at 225–231). Hook intent detection runs as an independent third pass inserted after line 254 (no executor dependency).
- Collision behavior: mirror `ActionProviderExtension` at `extension.py:237–240` and `EvaluatorProviderExtension` at `extension.py:244–247` — raise `ValueError` on duplicate intent names.

### Callers of `wire_extensions()` (no changes needed)

- `scripts/little_loops/cli/loop/run.py:348`
- `scripts/little_loops/cli/loop/lifecycle.py:414`
- `scripts/little_loops/cli/parallel.py:234`
- `scripts/little_loops/cli/sprint/run.py:425`

All callers automatically benefit from the new detection pass without code changes.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:348` — calls `wire_extensions()`; no changes needed (already listed above)
- `scripts/little_loops/cli/loop/lifecycle.py:414` — calls `wire_extensions()`; no changes needed (already listed above)
- `scripts/little_loops/cli/parallel.py:234` — calls `wire_extensions()`; no changes needed (already listed above)
- `scripts/little_loops/cli/sprint/run.py:425` — calls `wire_extensions()`; no changes needed (already listed above)
- `scripts/tests/test_cli_loop_queue.py` — patches `little_loops.extension.wire_extensions` in 4 test setups; no changes needed
- `scripts/tests/test_cli_loop_lifecycle.py` — patches `little_loops.extension.wire_extensions` in 5 test setups; no changes needed

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_interceptor_extension.py` — `TestReferenceInterceptorWiring` calls `wire_extensions()` directly with a real extension object; verify no regression after new hook intent detection pass (no code changes needed — detection pass is additive and only fires when `hasattr(ext, "provided_hook_intents")` is True)
- `scripts/tests/test_cli_loop_queue.py` — patches `wire_extensions`; no changes needed, but run to confirm patch still works after signature unchanged
- `scripts/tests/test_cli_loop_lifecycle.py` — patches `wire_extensions`; no changes needed

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### wire_extensions` > `**Behavior:**` block must describe new third-pass (hook intent detection); `**Duplicate key conflicts**` must add new `ValueError` message — **covered by sibling issue FEAT-1457**
- `docs/ARCHITECTURE.md` — Components table (lines 478–487) needs `LLHookIntentExtension` row; CLI Entry Points table (lines 502–507) needs updated `Extensions Wired` column — **covered by FEAT-1457**
- `CONTRIBUTING.md` — `## Authoring Extensions` > `**2. Develop**` needs `LLHookIntentExtension` added to "Optional mixin Protocols" list — **covered by FEAT-1457**
- `scripts/little_loops/cli/create_extension.py` — `_render_extension()` lines 82–83 scaffold string lists three mixin Protocols; must add `LLHookIntentExtension` — **covered by FEAT-1457**
- `docs/reference/CLI.md` — `### ll-create-extension` generated `extension.py` block (lines 1344–1345) mirrors the scaffold string; same update — **covered by FEAT-1457**

## Tests

Following `scripts/tests/test_extension.py:TestNewProtocols` (lines 465–568):

1. `test_smoke_import_ll_hook_intent_extension` — one-line `from little_loops import LLHookIntentExtension` + `assert ... is not None` (follow `test_smoke_import_ll_hook_event` at lines 557–561).
2. `test_ll_hook_intent_extension_protocol_satisfied` — inline class implementing `provided_hook_intents()`, assigned to `_: LLHookIntentExtension = instance  # type: ignore[assignment]` (follow `test_action_provider_extension_protocol_satisfied` at line 517).

Following `scripts/tests/test_extension.py:TestWireExtensions` (lines 135–463):

3. `test_wire_extensions_registers_hook_intents` — mirror the existing `patch.object(ExtensionLoader, "load_all", return_value=[...])` pattern (see `test_wire_extensions_registers_on_bus` at lines 138–159 for the canonical shape). Call `wire_extensions(bus, config_paths=["fake:Extension"])`, then assert `_HOOK_INTENT_REGISTRY` contains the expected intent.
4. Collision test — two extensions providing the same intent name should raise `ValueError` (mirror existing collision tests in `TestWireExtensions` for action/evaluator providers).

**Registry isolation:** there is no precedent for `_ACTION_REGISTRY` / `_EVALUATOR_REGISTRY` resets in the codebase (the action/evaluator detection paths in `wire_extensions()` operate on local dicts, not module-level registries). Since `_HOOK_INTENT_REGISTRY` is module-level mutable state, each test that mutates it must isolate via `monkeypatch.setattr("little_loops.hooks._HOOK_INTENT_REGISTRY", {})` (or equivalent `monkeypatch.setitem` on `little_loops.hooks.__dict__`) to prevent test order coupling. This is a new isolation pattern this issue introduces — document it inline in the test docstrings.

Following `scripts/tests/test_hook_intents.py:TestHooksMainModule` (starts at line 247):

5. `test_dispatch_table_merges_hook_intent_registry` — seed `_HOOK_INTENT_REGISTRY` with a test handler (with `monkeypatch` isolation as above), call `_dispatch_table()`, assert extension intent appears alongside built-in `pre_compact` and `session_start`. Test built-in precedence: registering an extension intent named `"session_start"` should be shadowed by the built-in in the returned dispatch table. Note that existing tests in this class (e.g., `test_ll_hook_host_env_var_propagates` at lines 313–345) use `monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {...})` to stub the whole function — that pattern is for testing `main_hooks()`, not the merge semantics; use direct registry seeding here instead.

## Implementation Steps

1. Add `@runtime_checkable LLHookIntentExtension` Protocol to `extension.py` after line 99.
2. Add `_HOOK_INTENT_REGISTRY` + `_register_hook_intents()` to `hooks/__init__.py`; update `_dispatch_table()` to merge.
3. Update `wire_extensions()` with the `provided_hook_intents` detection block.
4. Export `LLHookIntentExtension` from `little_loops/__init__.py`.
5. Add 5 tests across `test_extension.py` and `test_hook_intents.py`.
6. Verify:
   - `python -m pytest scripts/tests/test_extension.py -v`
   - `python -m pytest scripts/tests/ -v`
   - `python -m mypy scripts/little_loops/extension.py scripts/little_loops/hooks/`
   - `ruff check scripts/little_loops/`

## Acceptance Criteria

- `LLHookIntentExtension` is a `@runtime_checkable` Protocol in `extension.py`
- `wire_extensions()` detects hook intent handlers via `hasattr(ext, "provided_hook_intents")`
- `_HOOK_INTENT_REGISTRY` in `hooks/__init__.py` is populated by `wire_extensions()` and merged by `_dispatch_table()`
- Two new `TestNewProtocols` tests + one `TestWireExtensions` test + one collision test + one dispatch-table merge test pass
- `python -m pytest scripts/tests/test_extension.py -v` passes
- `python -m mypy scripts/little_loops/extension.py` passes

## Resolution

Implemented per the plan:

- Added `@runtime_checkable LLHookIntentExtension` Protocol to `scripts/little_loops/extension.py` with `provided_hook_intents()` method returning `dict[str, Callable[[LLHookEvent], LLHookResult]]`.
- Added `_HOOK_INTENT_REGISTRY` dict and `_register_hook_intents()` helper to `scripts/little_loops/hooks/__init__.py`; `_dispatch_table()` now merges the registry with built-ins (built-ins shadow extension intents on collision).
- Added an independent third pass to `wire_extensions()` that detects `provided_hook_intents` via `hasattr()` and calls `_register_hook_intents()` (no executor dependency, runs unconditionally).
- Exported `LLHookIntentExtension` from `little_loops/__init__.py` (import block + `__all__`).
- Added 5 tests:
  - `test_smoke_import_ll_hook_intent_extension` and `test_ll_hook_intent_extension_protocol_satisfied` in `TestNewProtocols`.
  - `test_wire_extensions_registers_hook_intents` and `test_wire_extensions_conflict_detection_hook_intents` in `TestWireExtensions` (both with `monkeypatch` registry isolation).
  - `test_dispatch_table_merges_hook_intent_registry` in `TestHooksMainModule` (verifies merge plus built-in precedence on collision).

Verification: targeted suite (`scripts/tests/test_extension.py` + `scripts/tests/test_hook_intents.py`) — 72 passed. Full suite — 6435 passed; 7 pre-existing failures (`test_generate_schemas.py`, `test_update_skill.py` version sync) confirmed unrelated by stashing changes and re-running. `python -m mypy scripts/little_loops/extension.py scripts/little_loops/hooks/` — clean. `ruff check scripts/little_loops/ scripts/tests/test_extension.py scripts/tests/test_hook_intents.py` — clean.

Docs updates (CONTRIBUTING.md, ARCHITECTURE.md, API.md, CLI.md, `create_extension.py` scaffold) are owned by sibling FEAT-1457.

## Session Log
- `/ll:manage-issue` - 2026-05-12T03:49:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36bb4e94-10f8-40d3-a238-3621a6453d53.jsonl`
- `/ll:ready-issue` - 2026-05-12T03:40:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da779f89-519e-4f07-b56b-f079535a15f2.jsonl`
- `/ll:wire-issue` - 2026-05-12T03:35:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a7ef6d3-1040-417a-868c-594d1ea0b6cc.jsonl`
- `/ll:refine-issue` - 2026-05-12T03:30:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f62cb1a-4e94-42b7-86ab-0ea4c79220f7.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b21eb7d-ba29-48d1-a82f-90d0bc6238a5.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9329fed-2fa8-471b-831c-99fd1204e736.jsonl`
