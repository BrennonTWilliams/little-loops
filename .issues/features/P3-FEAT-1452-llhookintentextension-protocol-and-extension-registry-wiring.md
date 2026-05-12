---
id: FEAT-1452
type: FEAT
priority: P3
status: open
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
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

## Tests

Following `scripts/tests/test_extension.py:TestNewProtocols` (lines 465–555):
- `test_smoke_import_ll_hook_intent_extension` — smoke import (following line 469 pattern)
- `test_ll_hook_intent_extension_protocol_satisfied` — structural compliance test (following line 499 pattern)

Following `scripts/tests/test_extension.py:TestWireExtensions`:
- New method detecting `LLHookIntentExtension` via `hasattr()` — following `test_wire_extensions_with_executor_populates_interceptors` pattern

## Acceptance Criteria

- `LLHookIntentExtension` is a `@runtime_checkable` Protocol in `extension.py`
- `wire_extensions()` detects hook intent handlers via `hasattr()`
- Two new Protocol tests + one new `TestWireExtensions` method pass
- All 9 authoring doc/skill locations updated
- `python -m pytest scripts/tests/test_extension.py -v`
- `python -m mypy scripts/little_loops/extension.py`

## Session Log
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
