---
id: FEAT-1452
type: FEAT
priority: P3
status: done
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
decision_needed: false
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
completed_at: 2026-05-11T00:00:00Z
---

# FEAT-1452: LLHookIntentExtension Protocol and Extension Registry Wiring

## Summary

Add `LLHookIntentExtension` as a new `@runtime_checkable` Protocol in `extension.py`, update `wire_extensions()` to detect hook intent handlers via `hasattr()`, write the required tests, and update all authoring docs/skills to include the new Protocol. This implements Decision 2 from FEAT-1116 (reuse the `little_loops.extensions` entry-point group).

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1448 (types `LLHookEvent`/`LLHookResult` must exist before the Protocol references them)

## Scope

Covers FEAT-1116 Implementation Steps 9 and 17.

**Decision 2 (from FEAT-1116)**: Do not introduce a second entry-point group. Add `LLHookIntentExtension` as a new `@runtime_checkable` Protocol alongside `InterceptorExtension` and `ActionProviderExtension` in `scripts/little_loops/extension.py`, detected via `hasattr()` inside `wire_extensions()`. FEAT-1117 tracks revisiting this if a host-specific driver demands discovery-time separation.

### Step 9 — Extension Registry Wiring

- Add `LLHookIntentExtension` Protocol to `scripts/little_loops/extension.py` (alongside `InterceptorExtension`, `ActionProviderExtension`)
- Update `wire_extensions()` to detect `LLHookIntentExtension` via `hasattr()` following the existing pattern
- No changes to `pyproject.toml` entry-point sections (per Decision 2)
- No changes to `ll-create-extension` scaffolding (per Decision 2)

### Step 17 — Authoring Docs and Skills

After `LLHookIntentExtension` ships, update these locations (all are mechanical doc edits):

- `CONTRIBUTING.md` — "Authoring Extensions" > "2. Develop": add `LLHookIntentExtension` to the three-Protocol list
- `CONTRIBUTING.md` — "Event Schema Maintenance": add `LLHookEvent` analogous documentation
- `docs/reference/CLI.md` — `### ll-create-extension` "Generated file contents" code block: add `LLHookIntentExtension`
- `scripts/little_loops/cli/create_extension.py:40-56` — update scaffold docstring/string
- `skills/workflow-automation-proposer/SKILL.md` — Step 7 "For hooks" sketch: update from direct `hooks/hooks.json` edits to adapter model
- `skills/configure/areas.md` — "Area: hooks" Current Values display table: update `session-start.sh` and `precompact-state.sh` paths to `hooks/adapters/claude-code/`
- `skills/audit-claude-config/SKILL.md:41` — add `hooks/adapters/` to audit scope
- `skills/init/SKILL.md` — Section 9.5: update `session-start.sh` warning and `pyyaml` dependency note
- `.claude/CLAUDE.md` — `hooks/` directory entry: add `hooks/adapters/` and `hooks/core/` subdirectory breakdown

## Files to Modify

- `scripts/little_loops/extension.py` — add `LLHookIntentExtension` Protocol, update `wire_extensions()`
- `scripts/tests/test_extension.py` — add tests in `TestNewProtocols` and `TestWireExtensions`
- `CONTRIBUTING.md`, `docs/reference/CLI.md`, `scripts/little_loops/cli/create_extension.py`
- `skills/workflow-automation-proposer/SKILL.md`, `skills/configure/areas.md`, `skills/audit-claude-config/SKILL.md`, `skills/init/SKILL.md`
- `.claude/CLAUDE.md`
- `scripts/little_loops/hooks/__init__.py` — add `_HOOK_INTENT_REGISTRY`, `_register_hook_intents()`, update `_dispatch_table()` to merge extension-contributed intents (see Implementation Step 3)
- `scripts/little_loops/__init__.py` — export `LLHookIntentExtension` from `little_loops.extension`, add `"LLHookIntentExtension"` to `__all__` under the `# extensions` comment (see Implementation Step 5)

## Proposed Solution

_Added by `/ll:refine-issue` — codebase research surfaced an unresolved design question. Two viable options below. `/ll:decide-issue` should select before `/ll:wire-issue` runs._

The Protocol's external shape and how `wire_extensions()` connects detected extensions to the `main_hooks()` dispatcher are interlocked. Existing FSM-side protocols all populate registries on `FSMExecutor`, but `main_hooks()` builds its dispatch table fresh per CLI invocation (`hooks/__init__.py:45–53`) and never calls `wire_extensions()`. We must choose both the Protocol surface AND the wiring target together.

### Option A — `provided_hook_intents()` mapping method + module-level registry

> **Selected:** Option A — mirrors `ActionProviderExtension` precedent; adding new intents requires no Protocol edits, which matters given 3–5 additional intents planned under FEAT-1116.

Mirror the `ActionProviderExtension` / `EvaluatorProviderExtension` precedent: one mapping method returning intent-name → callable.

```python
# scripts/little_loops/extension.py
@runtime_checkable
class LLHookIntentExtension(Protocol):
    """Protocol for extensions that contribute hook intent handlers.

    Detected via hasattr() in wire_extensions(). Returned handlers are
    merged into the dispatch table consulted by little_loops.hooks.main_hooks().
    """

    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

Wiring extension in `wire_extensions()` (mirroring `extension.py:235–241`):

```python
for ext in extensions:
    if hasattr(ext, "provided_hook_intents"):
        from little_loops.hooks import _register_hook_intents  # new
        _register_hook_intents(ext.provided_hook_intents())
```

`little_loops.hooks` gains a module-level `_HOOK_INTENT_REGISTRY: dict[str, Callable]` that `_dispatch_table()` merges with the built-in `{"pre_compact": ..., "session_start": ...}` (built-ins win on collision; conflicts among extensions raise `ValueError` as `provided_actions` does).

- **Pros**: single uniform pattern across all four optional Protocols; one new intent = no Protocol change for authors; mirrors existing `provided_actions` collision-handling exactly.
- **Cons**: needs a new module-level registry in `little_loops.hooks` (mutable global); `main_hooks()` must also invoke `wire_extensions(EventBus(), ...)` at startup (today it does not), or accept that the registry only matters in long-lived FSM hosts that already call `wire_extensions()`.
- **Wiring footprint**: `extension.py`, `hooks/__init__.py` (add `_HOOK_INTENT_REGISTRY` + `_register_hook_intents` + update `_dispatch_table`), and call `wire_extensions()` from `main_hooks()` or document the limitation explicitly.

### Option B — Explicit per-intent methods (`on_<intent>`) detected per-method

Mirror the `InterceptorExtension` precedent: one method per supported intent, detected disjunctively.

```python
# scripts/little_loops/extension.py
@runtime_checkable
class LLHookIntentExtension(Protocol):
    """Protocol for extensions that contribute hook intent handlers.

    Detected via hasattr() per-method in wire_extensions(). Each method is
    independently optional; an extension implementing only on_pre_compact()
    is a valid LLHookIntentExtension.
    """

    def on_pre_compact(self, event: LLHookEvent) -> LLHookResult: ...
    def on_session_start(self, event: LLHookEvent) -> LLHookResult: ...
```

Wiring inside `wire_extensions()`:

```python
for ext in extensions:
    intent_methods = [m for m in ("on_pre_compact", "on_session_start") if hasattr(ext, m)]
    if intent_methods:
        from little_loops.hooks import _register_hook_intents
        _register_hook_intents({m.removeprefix("on_"): getattr(ext, m) for m in intent_methods})
```

- **Pros**: no method-name string typos at extension-author time (mypy catches a bad method name); discoverability via IDE auto-complete; matches `InterceptorExtension` precedent of "any subset of named methods is valid".
- **Cons**: Protocol must be edited every time a new intent is added (e.g., when `pre_tool_use` lands); extension authors who want a generic "handle any intent" can't express it; the disjunctive `hasattr()` list in `wire_extensions()` grows with each intent.
- **Wiring footprint**: identical to Option A on the `hooks/__init__.py` side; the divergence is purely in `extension.py` Protocol shape.

### Recommendation (informational only — `/ll:decide-issue` decides)

Option A aligns more naturally with the existing `provided_actions` / `provided_evaluators` pattern and avoids re-editing the Protocol every time a new intent ships. Option B has stronger static-typing ergonomics. Either is implementable in the scope of this issue.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option A — `provided_hook_intents()` mapping method + module-level registry

**Reasoning**: Option A has direct line-for-line precedent in `ActionProviderExtension.provided_actions()` and `EvaluatorProviderExtension.provided_evaluators()` at `extension.py:79–98`, giving identical `hasattr()` detection, `ValueError` collision-guard, and test patterns (`test_action_provider_extension_protocol_satisfied` at `test_extension.py:517`). FEAT-1116 plans 3–5 additional intents beyond the current two (`pre_tool_use`, `post_tool_use`, `session_end`), making Option B's Protocol-edit obligation per new intent a significant compounding maintenance cost. The module-level `_HOOK_INTENT_REGISTRY` global is structurally new but explicitly required because hook intent dispatch has no executor equivalent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`provided_hook_intents()`) | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |
| Option B (`on_<intent>` per-method) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: Protocol shape, `hasattr()` detection, and collision-guard all exist verbatim at `extension.py:79–98` and `extension.py:235–248`; `_dispatch_table()` at `hooks/__init__.py:45–53` is the correct merge target.
- Option B: `InterceptorExtension` at `extension.py:59–77` and disjunctive `hasattr` block at `extension.py:249–254` are the structural match, but the Protocol body and detection list must be edited for each new intent added.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis 2026-05-11:_

### Protocol additions (`scripts/little_loops/extension.py`)

- **Existing Protocols** (lines 35–99) follow a consistent pattern:
  - `LLExtension` (35–56) — only Protocol decorated `@runtime_checkable`; required for `isinstance()` callers
  - `InterceptorExtension` (59–77) — no decorator; detected per-method via `hasattr()` (`before_route` / `after_route` / `before_issue_close`)
  - `ActionProviderExtension` (79–88) — no decorator; detected via `hasattr(ext, "provided_actions")`; method returns `dict[str, ActionRunner]`
  - `EvaluatorProviderExtension` (90–99) — no decorator; detected via `hasattr(ext, "provided_evaluators")`; method returns `dict[str, Evaluator]`
- FEAT-1452 scope says `LLHookIntentExtension` should be `@runtime_checkable` per FEAT-1116 Decision 2; mirror `LLExtension`'s decorator + docstring style, not the bare-Protocol style of the three FSM-side protocols.

### Wiring (`scripts/little_loops/extension.py:wire_extensions` lines 188–258)

- Two-pass structure: (1) EventBus pass detects `hasattr(ext, "on_event")` and calls `bus.register(_make_callback(ext), filter=...)`; (2) FSM-executor pass populates `_contributed_actions` / `_contributed_evaluators` / `_interceptors` only when `executor` is not `None`.
- **Knowledge gap (decision required)**: hook intents have **no executor equivalent**. `main_hooks()` builds its dispatch table fresh per CLI invocation via `_dispatch_table()` at `scripts/little_loops/hooks/__init__.py:45–53`. `wire_extensions()` is not currently called from `main_hooks()`. See "Proposed Solution" below for the two viable wiring strategies.
- Collision behavior to mirror: `ActionProviderExtension` raises `ValueError("Extension conflict: action '<name>' already registered by another extension")` on duplicate name (`extension.py:237–240`). The same pattern fits intent-name collisions if Option A is selected.

### Hook intent type surface (`scripts/little_loops/hooks/types.py`)

- `LLHookEvent` (lines 20–82): `@dataclass` with `host`, `intent`, `timestamp`, `payload`, `session_id`, `cwd`; `to_dict`/`from_dict` use `"ts"` as the timestamp wire key.
- `LLHookResult` (lines 84–145): `@dataclass` with `exit_code`, `feedback`, `decision`, `data`, `stdout`; `to_dict` omits `None`-valued fields.
- Both are re-exported from `little_loops/__init__.py` and `little_loops/hooks/__init__.py:__all__`.
- Handler signature pattern used by every existing intent module (`pre_compact.handle`, `session_start.handle`): `def handle(event: LLHookEvent) -> LLHookResult`.

### Test patterns to mirror (`scripts/tests/test_extension.py`)

- `TestNewProtocols.test_smoke_import_*` (lines 469–567) — single-line import + `assert X is not None`; add as a peer of `test_smoke_import_ll_hook_event` (line 557) and `test_smoke_import_ll_hook_result` (line 563).
- `TestNewProtocols.test_*_protocol_satisfied` (lines 499–537) — inline class implementing required methods, assigned to a typed `_:` variable with `# type: ignore[assignment]`. Mirror `test_action_provider_extension_protocol_satisfied` (line 517) for the single-method Protocol shape.
- `TestWireExtensions.test_wire_extensions_with_executor_populates_*` (lines 315–383) — define an inline extension class, build a stub executor with `type("Executor", (), {...})()`, patch `ExtensionLoader.load_all`, call `wire_extensions(bus, executor=executor_obj)`, assert the executor's registry was populated. No module-level fixtures exist — every test rebuilds its own stub inline.
- **If Option B is selected**, the wiring test cannot use the executor stub pattern; it must instead patch the hook dispatch registry that the new wiring populates.

### Tests / Docs (already enumerated in Scope above)

- `scripts/tests/test_extension.py:TestNewProtocols` (465–555) and `TestWireExtensions` (~300–440)
- 9 authoring doc/skill locations (already enumerated in Step 17)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — calls `wire_extensions()` at line 348; no code change needed, hook intent detection pass activates automatically for any installed extension
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `wire_extensions()` at line 414; same — no change needed
- `scripts/little_loops/cli/parallel.py` — calls `wire_extensions()` at line 234; same — no change needed
- `scripts/little_loops/cli/sprint/run.py` — calls `wire_extensions()` at line 425; same — no change needed

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### wire_extensions` description (line 5944): add `LLHookIntentExtension` to the Protocol list ("each extension that implements the corresponding protocols (`ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension`)"); sync with FEAT-1453's broader docs pass
- `docs/ARCHITECTURE.md` — Components table (lines 484–487): add `LLHookIntentExtension` row describing its role (detected via `hasattr()`, populates `_HOOK_INTENT_REGISTRY` in `hooks/__init__.py`)

## Tests

Following `scripts/tests/test_extension.py:TestNewProtocols` (lines 465–567):
- `test_smoke_import_ll_hook_intent_extension` — smoke import (follow `test_smoke_import_ll_hook_event` at line 557 — one-line `from little_loops import LLHookIntentExtension` + `assert ... is not None`). Requires re-exporting `LLHookIntentExtension` from `scripts/little_loops/__init__.py` (mirror the existing `LLHookEvent`/`LLHookResult` exports).
- `test_ll_hook_intent_extension_protocol_satisfied` — structural compliance test (follow `test_action_provider_extension_protocol_satisfied` at line 517 for Option A's single-method shape, OR `test_interceptor_extension_protocol_satisfied` at line 499 for Option B's multi-method shape). Inline class implementing the chosen Protocol surface, assigned to `_: LLHookIntentExtension = instance  # type: ignore[assignment]`.

Following `scripts/tests/test_extension.py:TestWireExtensions` (lines 315–383):
- New `test_wire_extensions_registers_hook_intents` method — mirror `test_wire_extensions_with_executor_populates_interceptors` (line 361) structure but patch `little_loops.hooks._HOOK_INTENT_REGISTRY` (the new module-level registry) instead of building an executor stub; assert the registry contains the expected intent name(s) after `wire_extensions()` returns. Use `patch.object(ExtensionLoader, "load_all", return_value=[FakeHookExt()])` as the other wiring tests do.
- Add a collision test paralleling `extension.py:237–240` if Option A's `ValueError` collision behavior is adopted: two extensions providing the same intent name should raise `ValueError`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py` — add a new test in `TestHooksMainModule` to verify that `_dispatch_table()` merges `_HOOK_INTENT_REGISTRY` entries alongside built-in intents. Existing tests at lines 331/359 monkeypatch `_dispatch_table` entirely (bypassing the new merge) — safe, not broken, but the merge path is uncovered. New test: seed `_HOOK_INTENT_REGISTRY` with a test handler, call `_dispatch_table()`, assert the extension intent appears in the result alongside the built-in `pre_compact` and `session_start` entries.

## Implementation Steps

_Concretized by `/ll:refine-issue`. Steps 1–3 require the option from `## Proposed Solution` to be selected first._

1. **Select Option A or B** via `/ll:decide-issue FEAT-1452` (sets the Protocol method shape).
2. **Add Protocol** to `scripts/little_loops/extension.py` after line 99 (current end of `EvaluatorProviderExtension`). Use `@runtime_checkable` (matches FEAT-1116 Decision 2). Reference `LLHookEvent` / `LLHookResult` from `little_loops.hooks.types`; add the import inside a `TYPE_CHECKING` block alongside the existing FSM imports at `extension.py:24–28` (the runtime callable type can use `from collections.abc import Callable` at module top).
3. **Add hook intent registry** in `scripts/little_loops/hooks/__init__.py`:
   - Module-level `_HOOK_INTENT_REGISTRY: dict[str, Callable[[LLHookEvent], LLHookResult]] = {}`
   - `_register_hook_intents(handlers: dict[...])` — raises `ValueError` on duplicate keys (mirror `extension.py:237–240` collision message)
   - Update `_dispatch_table()` (line 45) to merge `_HOOK_INTENT_REGISTRY` over the built-in `{"pre_compact": ..., "session_start": ...}` (built-ins win — extensions cannot shadow core intents).
4. **Update `wire_extensions()`** at `scripts/little_loops/extension.py:233` (or extend the existing `if fsm_executor is not None:` block / add a sibling block). Per the selected option, detect via `hasattr(ext, "provided_hook_intents")` (A) or the disjunctive list (B), then call `_register_hook_intents(...)`. Hook intent detection should run independently of `executor is None` since hooks have no executor dependency.
5. **Export from public API** — add `LLHookIntentExtension` to `scripts/little_loops/__init__.py` imports and `__all__` (mirror the existing `LLHookEvent` / `LLHookResult` export pattern there).
6. **Add tests** in `scripts/tests/test_extension.py`:
   - Two `TestNewProtocols` methods (smoke import + protocol_satisfied) — append after line 567 (current end of `TestNewProtocols`).
   - One `TestWireExtensions` method (`test_wire_extensions_registers_hook_intents`) — append after `test_wire_extensions_with_executor_populates_interceptors` at line 383. Use `monkeypatch.setattr("little_loops.hooks._HOOK_INTENT_REGISTRY", {})` or a `try/finally` reset in the test so registry state does not leak between tests.
   - Optionally a collision test if Option A's `ValueError` is adopted.
7. **Update the 9 authoring doc/skill locations** enumerated under "Step 17 — Authoring Docs and Skills" above. These are mechanical text edits — they should be batched in a single Edit pass per file.
8. **Verification**:
   - `python -m pytest scripts/tests/test_extension.py -v`
   - `python -m pytest scripts/tests/ -v` (no regressions in hook-intent integration tests)
   - `python -m mypy scripts/little_loops/extension.py scripts/little_loops/hooks/`
   - `ruff check scripts/little_loops/`

## Acceptance Criteria

- `LLHookIntentExtension` is a `@runtime_checkable` Protocol in `extension.py`
- `wire_extensions()` detects hook intent handlers via `hasattr()`
- Two new Protocol tests + one new `TestWireExtensions` method pass
- All 9 authoring doc/skill locations updated
- `python -m pytest scripts/tests/test_extension.py -v`
- `python -m mypy scripts/little_loops/extension.py`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Wide doc fanout without verification** — 9 skill/doc sites are enumerated in Step 17 but there is no verification grep to catch a missed edit; CI won't surface an omission.
- **Minor unresolved sub-question: `main_hooks()` + `wire_extensions()` integration path** — Option A notes the registry "only matters in long-lived FSM hosts that already call `wire_extensions()`" since `main_hooks()` doesn't call it today; the issue says "call `wire_extensions()` from `main_hooks()` or document the limitation explicitly" without choosing — implementer must decide before writing `hooks/__init__.py`.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-12
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1456: LLHookIntentExtension Protocol, Registry, Wiring, and Tests
- FEAT-1457: LLHookIntentExtension Authoring Docs and Skills Update

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:00:00 - `0b21eb7d-ba29-48d1-a82f-90d0bc6238a5.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `82321d7d-e2c4-449b-98a6-72e150abb16e.jsonl`
- `/ll:decide-issue` - 2026-05-12T03:20:35 - `94bcac04-f76e-4220-b166-25df7aeb524d.jsonl`
- `/ll:confidence-check` - 2026-05-11T12:00:00 - `67e7efb4-ec30-481a-bd3e-f3ef0c5e6daa.jsonl`
- `/ll:wire-issue` - 2026-05-12T03:12:41 - `bd4c5b26-025a-453f-9fc3-134e15455eaa.jsonl`
- `/ll:refine-issue` - 2026-05-12T03:06:53 - `5a9d0b5e-3dd8-4c75-9cc4-c75e3e21b41c.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
