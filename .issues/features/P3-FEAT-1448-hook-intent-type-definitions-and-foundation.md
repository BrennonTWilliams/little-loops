---
id: FEAT-1448
type: FEAT
priority: P3
status: done
parent: FEAT-1116
discovered_date: 2026-05-12
completed_at: 2026-05-12T00:44:08Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1448: Hook-Intent Type Definitions and Foundation

## Summary

Define `LLHookEvent` and `LLHookResult` dataclasses, create the `scripts/little_loops/hooks/` package skeleton, decide the public API surface, and update `config-schema.json` to accept a `hooks` property block. This is the foundational child of FEAT-1116 that every other child depends on.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Scope

Covers FEAT-1116 Implementation Steps 1, 10, 11.

- **Step 1**: Define `LLHookEvent` and `LLHookResult` as sibling `@dataclass` types in `scripts/little_loops/hooks/types.py` (Decision 1 from FEAT-1116: not inheriting from `LLEvent`). Include `host: str` field on `LLHookEvent`. Cross-link to `LLEvent` in `docs/reference/EVENT-SCHEMA.md`.
- **Step 10**: Decide if `LLHookEvent`/`LLHookResult` belong in `scripts/little_loops/__init__.py` `__all__`; if yes, add imports.
- **Step 11**: Add a `"hooks"` property block (with `host: string`) to `config-schema.json` before any `hooks.*` key is used; the root schema uses `additionalProperties: false`-equivalent strictness so this is required.

## New Files to Create

- `scripts/little_loops/hooks/__init__.py`
- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult` dataclasses
- `scripts/little_loops/hooks/__main__.py` — dispatch `python -m little_loops.hooks <intent>` (following `scripts/little_loops/cli/loop/__main__.py:1-6` pattern)

## Files to Modify

- `scripts/little_loops/__init__.py` — add `LLHookEvent`, `LLHookResult` to imports and `__all__` if they are public API
- `config-schema.json` — add `"hooks"` property block with `host: string`
- `docs/reference/EVENT-SCHEMA.md` — cross-link `LLHookEvent` to `LLEvent`

## Patterns to Follow

- **Dataclass style**: `scripts/little_loops/events.py:28-65` (`LLEvent`) — `@dataclass`, `from __future__ import annotations`, `to_dict()` skipping `None` optionals, classmethod `from_dict()`
- **Module CLI entry**: `scripts/little_loops/cli/loop/__main__.py:1-6` — `main() -> int` + `raise SystemExit(main())`
- **Smoke-import + Protocol structural test**: `scripts/tests/test_extension.py:465-543` (`TestNewProtocols`)

## Tests

Add `scripts/tests/test_hook_intents.py`:
- Dataclass round-trip (`to_dict`/`from_dict`) following `scripts/tests/test_events.py:27-75` pattern
- Smoke-import: `from little_loops.hooks.types import LLHookEvent, LLHookResult; assert LLHookEvent is not None`
- If `LLHookEvent`/`LLHookResult` are added to `__init__.py`: add `TestNewProtocols`-style entries in `scripts/tests/test_extension.py:465-543`

## Acceptance Criteria

- `scripts/little_loops/hooks/` package exists with `__init__.py`, `types.py`, `__main__.py`
- `LLHookEvent` and `LLHookResult` are `@dataclass` types with `to_dict()`/`from_dict()` round-trip
- `LLHookEvent` has a `host: str` field
- `config-schema.json` has a `"hooks"` property block; schema validation passes
- `docs/reference/EVENT-SCHEMA.md` cross-links `LLHookEvent` to `LLEvent`
- Tests pass: `python -m pytest scripts/tests/test_hook_intents.py -v`
- Type checks: `python -m mypy scripts/little_loops/hooks/`
- Lint: `ruff check scripts/little_loops/hooks/`

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/__init__.py` — add `from little_loops.hooks.types import LLHookEvent, LLHookResult` and append to `__all__` under a `# hooks` comment block (model after the existing `# events` block at lines 53–55)
- `config-schema.json` — add `"hooks"` property block; root has `"additionalProperties": false` at line 1168 so this is required before any consumer uses `hooks.host`. Logical insertion point: between `"events"` and `"extensions"` (function-grouped, not alphabetical)
- `docs/reference/EVENT-SCHEMA.md` — cross-link in the `## Wire Format` section, immediately after the existing `LLEvent` field-mapping code block (~line 29–35)

### Dependent Files (Downstream Consumers — siblings of this issue)
- FEAT-1449 (`P3-FEAT-1449-precompact-intent-python-core-and-claude-code-adapter.md`) — imports `LLHookEvent`/`LLHookResult` for the PreCompact handler
- FEAT-1450 (`P3-FEAT-1450-sessionstart-intent-python-core-and-claude-code-adapter.md`) — imports for SessionStart handler
- FEAT-1451 (`P3-FEAT-1451-opencode-adapter-for-hook-intents.md`) — OpenCode TS adapter consumes the wire format produced by `to_dict()`
- FEAT-1452 (`P3-FEAT-1452-llhookintentextension-protocol-and-extension-registry-wiring.md`) — adds `LLHookIntentExtension` Protocol referencing these types in `scripts/little_loops/extension.py`
- FEAT-1453 (`P3-FEAT-1453-hook-intent-abstraction-documentation.md`) — documents the new public API in `docs/reference/API.md` and `docs/ARCHITECTURE.md`

### Reference Patterns (existing — model after)
- `scripts/little_loops/events.py:28-65` — `LLEvent` dataclass, `to_dict()` flat-spread, `from_dict()` two-alias `pop()` pattern
- `scripts/little_loops/config/features.py` — `OTelEventsConfig` (`endpoint: str` default, `from_dict()` using `data.get(...)`) — closest analog for a `str`-typed required field
- `scripts/little_loops/extensions/__init__.py` — minimal sub-package `__init__.py` re-export pattern
- `scripts/little_loops/fsm/__init__.py` — full-docstring + exhaustive `__all__` re-export pattern (use this if hooks grows)
- `scripts/little_loops/cli/loop/__main__.py:1-6` — three-line `__main__.py` entry shape; real `main_loop()` lives in the sibling `__init__.py` with `argparse` subparsers and a flat `if/elif args.command` dispatch (`scripts/little_loops/cli/loop/__init__.py:379-405`)

### Tests
- `scripts/tests/test_events.py:27-92` — `TestLLEvent` class: separate methods for `test_to_dict`, `test_from_dict`, `test_from_dict_missing_fields`, `test_to_dict_json_serializable`, `test_roundtrip` (asserts each field individually, not `==` on the whole instance)
- `scripts/tests/test_extension.py:465-543` — `TestNewProtocols`: smoke-import pattern is `from little_loops import X  # noqa: F401 — import is the test` then `assert X is not None`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — `TestConfigSchema`: add `test_hooks_in_schema` method asserting `"hooks" in data["properties"]` and confirming `host` sub-property (`enum: ["claude-code", "opencode"]`); follows pattern of `test_events_in_schema` (lines 136–221). The root `additionalProperties: false` means a missing schema declaration silently breaks consumers — this test guards against that regression. [Agent 2 + 3 finding]

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — `## Wire Format` section is the cross-link target; per-event docs use H3 + field tables + JSON example
- `docs/ARCHITECTURE.md` and `docs/reference/API.md` — owned by FEAT-1453, not this issue

### Configuration
- `config-schema.json:1168` — root `additionalProperties: false`; every sub-object also uses `additionalProperties: false`. The new `"hooks"` block must follow this convention.

## Decisions Resolved by Research

_Added by `/ll:refine-issue` — resolves open decisions in the original scope:_

- **Step 10 (public API re-export)** — **Yes, re-export.** Every sibling dataclass in the same tier (`LLEvent`, `LLTestBus`, `RouteContext`, `RouteDecision`, `InterceptorExtension`, `ActionProviderExtension`, etc.) is imported into `scripts/little_loops/__init__.py` and listed in `__all__` with a function-grouped comment header. Mirroring this is the established convention; deviating would create an inconsistent public-API surface for a foundational type.
- **`to_dict()` None-skipping (net-new pattern)** — `LLEvent.to_dict()` has **no** `None`-skipping logic because `LLEvent` has no `Optional[X] = None` scalar fields (only required `type`, `timestamp` and a non-nullable `payload: dict`). FEAT-1448's "skipping `None` optionals" requirement is a **new** pattern introduced on `LLHookEvent`/`LLHookResult`, not inherited. Implement it as: `return {k: v for k, v in {"host": self.host, ...}.items() if v is not None}` when any field is `Optional[...]`.
- **`from_dict()` key-alias fallback** — `LLEvent.from_dict()` uses the pattern `copy.pop("event", copy.pop("type", "unknown"))` to support both wire-key and field-name. For `LLHookEvent`/`LLHookResult`, this is only needed if the wire format will rename fields (e.g., `host` ↔ something else). Otherwise prefer the simpler single-key `data.get("host", default)` pattern seen in `config/features.py` dataclasses.
- **`host` is net-new** — no `host:` field, `host:` config key, or host-discriminator concept exists anywhere in current Python source or `hooks/hooks.json`. The closest analog (an enum-constrained `str` discriminator) is `sync.provider` at `config-schema.json:963`. Document permitted values (`claude-code`, `opencode`) in the schema description and in the docstring.
- **`__main__.py` dispatch shape** — three lines, mirroring `cli/loop/__main__.py`. The real `main_hooks() -> int` lives in `scripts/little_loops/hooks/__init__.py`. In FEAT-1448 it can be a stub that prints help and returns `0`; FEAT-1449/1450 will populate the intent dispatch.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete sequence based on research:_

1. **Create package skeleton** — `scripts/little_loops/hooks/__init__.py` (with module docstring + future `__all__`), `types.py` (initially empty stub with `from __future__ import annotations`), `__main__.py` (mirror `cli/loop/__main__.py:1-6` — `raise SystemExit(main_hooks())`).
2. **Implement `LLHookEvent`** in `types.py` — `@dataclass`, fields: `host: str` (required) plus the hook event payload fields agreed in FEAT-1116. Add `to_dict()` with `None`-skipping comprehension, `from_dict()` classmethod using `data.get(...)` defaults (mirror `OTelEventsConfig.from_dict`).
3. **Implement `LLHookResult`** in `types.py` — sibling `@dataclass` with the result shape from FEAT-1116. Same `to_dict()`/`from_dict()` contract.
4. **Add `main_hooks()` stub** in `hooks/__init__.py` — `def main_hooks() -> int: ...` that prints usage and returns `0` (real intent dispatch lands in FEAT-1449/1450). Add `hooks/__main__.py` calling it.
5. **Promote to public API** — edit `scripts/little_loops/__init__.py`: add `from little_loops.hooks.types import LLHookEvent, LLHookResult` next to the `LLEvent` import; append to `__all__` with a `# hooks` comment block adjacent to `# events`.
6. **Update `config-schema.json`** — insert a `"hooks"` property block between `"events"` and `"extensions"`. Shape: `{ "type": "object", "properties": { "host": { "type": "string", "enum": ["claude-code", "opencode"], "description": "Host agent identifier" } }, "additionalProperties": false }`.
7. **Update `docs/reference/EVENT-SCHEMA.md`** — in `## Wire Format`, after the `LLEvent` field-mapping code block, add a short paragraph cross-linking `LLHookEvent`/`LLHookResult` and pointing to `scripts/little_loops/hooks/types.py`.
8. **Write `scripts/tests/test_hook_intents.py`** — mirror `test_events.py:TestLLEvent` with one class per type (`TestLLHookEvent`, `TestLLHookResult`). Each class needs `test_to_dict`, `test_from_dict`, `test_roundtrip`, `test_to_dict_json_serializable`, plus a `test_to_dict_skips_none` for the new `None`-skipping behavior.
9. **Add smoke-import tests** — in `scripts/tests/test_extension.py:TestNewProtocols`, append `test_smoke_import_ll_hook_event` and `test_smoke_import_ll_hook_result` following the `from little_loops import X  # noqa: F401 — import is the test` pattern.
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/tests/test_config_schema.py` — add `test_hooks_in_schema` to `TestConfigSchema` following the `test_events_in_schema` pattern (lines 136–221): assert `"hooks" in data["properties"]`, confirm `host` sub-property exists with `"enum": ["claude-code", "opencode"]`

10. **Verify** — run in order:
    - `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_extension.py -v`
    - `python -m mypy scripts/little_loops/hooks/`
    - `ruff check scripts/little_loops/hooks/`
    - `python -c "from little_loops import LLHookEvent, LLHookResult; print('ok')"` — confirms public API export
    - `python -m little_loops.hooks` — confirms `__main__.py` dispatch works (should print usage, exit 0)

## Resolution

Implemented the foundational hook-intent types and package skeleton.

**Created**:
- `scripts/little_loops/hooks/__init__.py` — public exports and `main_hooks()` CLI stub
- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult` `@dataclass` types with `to_dict()`/`from_dict()` round-trip and `None`-skipping serialization
- `scripts/little_loops/hooks/__main__.py` — three-line entry point mirroring `cli/loop/__main__.py`
- `scripts/tests/test_hook_intents.py` — 23 tests covering round-trip, None-skipping, defaults, JSON serializability, and `python -m little_loops.hooks` dispatch

**Modified**:
- `scripts/little_loops/__init__.py` — re-exports `LLHookEvent`, `LLHookResult` under a `# hooks` block in `__all__`
- `config-schema.json` — new `"hooks"` property block between `extensions` and `events` with `host: enum["claude-code", "opencode"]` and `additionalProperties: false`
- `docs/reference/EVENT-SCHEMA.md` — cross-link to `LLHookEvent`/`LLHookResult` as the sibling request/response type to `LLEvent`
- `scripts/tests/test_extension.py` — smoke-import tests `test_smoke_import_ll_hook_event` and `test_smoke_import_ll_hook_result` in `TestNewProtocols`
- `scripts/tests/test_config_schema.py` — `test_hooks_in_schema` guarding the new schema block against `additionalProperties: false` regression

**Field shape**:
- `LLHookEvent(host: str, intent: str = "", timestamp: str = "", payload: dict = {}, session_id: str | None = None, cwd: str | None = None)`
- `LLHookResult(exit_code: int = 0, feedback: str | None = None, decision: str | None = None, data: dict = {})`
- `exit_code` semantics borrowed from Claude Code (`0` pass, `2` block + inject feedback); adapters translate for other hosts.

**Verification**:
- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_extension.py scripts/tests/test_config_schema.py scripts/tests/test_events.py` → 97 passed
- `python -m mypy scripts/little_loops/hooks/` → clean
- `ruff check scripts/little_loops/hooks/` → clean
- `python -c "from little_loops import LLHookEvent, LLHookResult"` → ok
- `python -m little_loops.hooks` → prints usage stub, exits 0

Downstream issues (FEAT-1449, FEAT-1450, FEAT-1451, FEAT-1452, FEAT-1453) can now import these types and consume the wire format.

## Session Log
- `/ll:manage-issue` - 2026-05-12T00:44:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6757264-73e6-4e0f-831d-fb2fb85ba038.jsonl`
- `/ll:ready-issue` - 2026-05-12T00:39:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78401886-76fe-4446-b5d3-3d5306bdd8c9.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d741a832-b0c4-4e6a-84d5-8faf4d5dd659.jsonl`
- `/ll:wire-issue` - 2026-05-12T00:35:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6752dc5e-825c-4ea9-99ad-59b0667cabe9.jsonl`
- `/ll:refine-issue` - 2026-05-12T00:28:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8211e223-fbea-436e-8701-f51574d9f5c8.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
