---
discovered_date: "2026-04-21"
completed_at: 2026-04-21T16:05:52Z
discovered_by: issue-size-review
parent_issue: FEAT-1080
size: Medium
confidence_score: 90
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1227: Parallel State Core API Exports and Config Wiring

## Summary

Export `ParallelStateConfig` and `ParallelResult` from `scripts/little_loops/fsm/__init__.py`, add the `parallel` glyph field to `LoopsGlyphsConfig` in `config/features.py`, add the `parallel` key to `config-schema.json`, and update all affected test assertions.

## Parent Issue

Decomposed from FEAT-1080: Parallel State FSM API Exports and Config Wiring

## Use Case

**Who**: A developer building FSM loops with parallel state execution

**Context**: After `ParallelStateConfig` and `ParallelResult` are added to `fsm/schema.py` (FEAT-1074), a developer importing these types via `from little_loops.fsm import ...` needs them exposed in the public module API. Similarly, a user who sets `loops.glyphs.parallel` in `ll-config.json` expects the key to be accepted and applied.

**Goal**: Import `ParallelStateConfig` and `ParallelResult` from `little_loops.fsm` without resorting to internal module paths; configure the parallel state badge via the standard `loops.glyphs` config key.

**Outcome**: All parallel state types are available in the public FSM API; `loops.glyphs.parallel` in `ll-config.json` validates and takes effect.

## Current Behavior

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` raises `ImportError` — neither type is in `__init__.py`'s import block or `__all__`
- `LoopsGlyphsConfig` in `config/features.py:257-288` has no `parallel` field, so downstream code that reads `badges.get("parallel", ...)` will always fall back to its default regardless of user config
- `config-schema.json` `loops.glyphs` block at lines 760–772 has `"additionalProperties": false` at line 771 and no `"parallel"` property, so any `ll-config.json` with `loops.glyphs.parallel` is rejected by schema validation
- `test_config.py:1530` (`test_to_dict_returns_all_keys`) asserts `set(d.keys()) == {"prompt", "slash_command", "shell", "mcp_tool", "sub_loop", "route"}` — will break if `to_dict()` gains `"parallel"`

## Expected Behavior

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` succeeds
- `LoopsGlyphsConfig.parallel` field defaults to `"∥"` and is included in `to_dict()` / `from_dict()`
- `config-schema.json` accepts `loops.glyphs.parallel` as a valid string property
- `test_config.py:1530` (`test_to_dict_returns_all_keys`) assertion includes `"parallel"` in the expected key set

## Proposed Solution

### `fsm/__init__.py` exports

- Extend the `from little_loops.fsm.schema import (...)` block at lines 120–127 to include `ParallelStateConfig` and `ParallelResult`
- Add both to `__all__` (lines 143–195); alphabetically sorted, insert `"ParallelResult"` then `"ParallelStateConfig"` immediately before `"PersistentExecutor"` at line 170
- Add brief parallel state type description to module docstring (lines 1–71) under the `# Schema` comment block (the category headers are listed inside the docstring at lines 8–71; insert parallel types immediately after the `StateConfig` entry at line 11)

### `config/features.py` — `LoopsGlyphsConfig`

- Add `parallel: str = "∥"` to `LoopsGlyphsConfig` dataclass (lines 257–288). **Use bare inline default — NO `field()` wrapper** (matches existing style: `route: str = "⑃"`).
- Add `"parallel": self.parallel` entry to `to_dict()` (lines 279–288) after the existing `"route"` entry at line 287
- Update `from_dict()` (lines 267–277) to read the `"parallel"` key: `parallel=data.get("parallel", "∥"),` after the `route=...` line at 276

### `config-schema.json`

- Add `"parallel"` property to the `loops.glyphs` object schema (block at lines 760–772, insert before `"additionalProperties": false` at line 771):
  ```json
  "parallel": {
    "type": "string",
    "default": "∥",
    "description": "Badge for parallel states (default: ∥)"
  }
  ```
  Mirrors the `"sub_loop"` and `"route"` entries already present.

### Tests

- `scripts/tests/test_config.py:1510` — `TestLoopsGlyphsConfig.test_defaults`: add `assert config.parallel == "∥"`
- `scripts/tests/test_config.py:1519` — `test_from_dict_empty`: add `assert config.parallel == "∥"` to cover default when key absent
- `scripts/tests/test_config.py:1524` — `test_from_dict_partial_override`: add override case `from_dict({"parallel": "P"})` → `config.parallel == "P"`
- `scripts/tests/test_config.py:1530` — `test_to_dict_returns_all_keys`: add `"parallel"` to set assertion; add `assert d["parallel"] == "∥"` after line 1542
- `scripts/tests/test_config.py:1558` — `test_loops_glyphs_defaults_when_absent`: add `assert config.loops.glyphs.parallel == "∥"`
- `scripts/tests/test_config.py:1564-1573` — `test_loops_glyphs_override_from_config`: include `"parallel"` in sample config; assert default and override round-trip
- `scripts/tests/test_config_schema.py` — add `test_loops_glyphs_parallel_in_schema`: navigate `data["properties"]["loops"]["properties"]["glyphs"]["properties"]` and assert `"parallel"` key present with `"type": "string"`
- `scripts/tests/test_fsm_schema.py` — add `TestParallelStatePublicExports` class with smoke tests importing `ParallelStateConfig` and `ParallelResult` from `little_loops.fsm` (public API, not internal module path). Model on the canonical export-smoke pattern in `scripts/tests/test_fsm_executor.py:4783-4799` (`TestRateLimitRetries.test_rate_limit_*_exported` — inline `from little_loops.fsm import X` followed by an identity/value assertion)

## Implementation Steps

1. Export `ParallelStateConfig` and `ParallelResult` from `fsm/__init__.py` (import block + `__all__` + module docstring) — **blocked on FEAT-1074**
2. Add `parallel: str = "∥"` field to `LoopsGlyphsConfig`, `to_dict()`, and `from_dict()` in `config/features.py`
3. Add `"parallel"` property to `loops.glyphs` in `config-schema.json`
4. Update `test_config.py` assertions (test_defaults, test_from_dict_empty, test_from_dict_partial_override, test_to_dict_returns_all_keys, test_loops_glyphs_defaults_when_absent, test_loops_glyphs_override_from_config)
5. Add `test_loops_glyphs_parallel_in_schema` to `test_config_schema.py`
6. Add `TestParallelStatePublicExports` smoke test class to `test_fsm_schema.py` — **blocked on FEAT-1074**

Steps 2–5 are actionable immediately. Steps 1 and 6 require FEAT-1074 to ship first.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/__init__.py` — Add `ParallelStateConfig`, `ParallelResult` to import block, `__all__`, docstring (blocked on FEAT-1074)
- `scripts/little_loops/config/features.py` — Add `parallel` field to `LoopsGlyphsConfig` dataclass, `to_dict()`, `from_dict()` (lines 257–288)
- `config-schema.json` — Add `"parallel"` to `loops.glyphs` schema (lines 760–772)
- `scripts/tests/test_config.py` — Update 6 test assertions
- `scripts/tests/test_config_schema.py` — Add new test
- `scripts/tests/test_fsm_schema.py` — Add smoke test class (blocked on FEAT-1074)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:100` — calls `_config.loops.glyphs.to_dict()` and passes result as `badges=` to FSM executor display; silently gains `"parallel"` key after FEAT-1227 (no code change needed — key is carried but unused until FEAT-1081)
- `scripts/little_loops/cli/loop/info.py:728` — calls `BRConfig(Path.cwd()).loops.glyphs.to_dict()` and passes result as `badges=` to `_render_fsm_diagram()`; same silent-carry behavior
- `scripts/little_loops/config/core.py:430` — calls `self._loops.glyphs.to_dict()` inside `BRConfig.to_dict()` serialization; gains `"parallel"` key in serialized output
- `scripts/little_loops/cli/loop/layout.py:119` — `_get_state_badge()` receives `badges` dict and merges with `_ACTION_TYPE_BADGES`; `"parallel"` key flows through silently until FEAT-1081 adds the consuming branch
- `scripts/little_loops/config/__init__.py:40,60` — re-exports `LoopsGlyphsConfig` in import block and `__all__`; no change needed (re-export is transparent)
- `scripts/little_loops/__init__.py:18` — imports from `little_loops.fsm` at package load time; if FEAT-1074 is not complete when steps 1 & 6 land, this causes a top-level import failure for all `little_loops` consumers

### Read-only Dependencies

- `scripts/little_loops/fsm/schema.py` — source of `ParallelStateConfig` and `ParallelResult` (FEAT-1074 must be complete before steps 1 & 6)

### Similar Patterns

- `from little_loops.fsm.schema import (...)` grouped import block in `fsm/__init__.py:120-127`
- `sub_loop: str` and `route: str` fields in `LoopsGlyphsConfig` — naming and wiring pattern
- `"sub_loop"` and `"route"` entries in `config-schema.json` `loops.glyphs` block

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:467-472` — `loops.glyphs` table lists 6 existing glyph keys but has no `parallel` row; `config-schema.json` will accept the key but user docs will not describe it until FEAT-1082 scope lands
- `docs/reference/API.md:3726-3748` — Quick Import block has no `ParallelStateConfig` / `ParallelResult` entries; will be incomplete for new public FSM symbols until FEAT-1082/1084

Note: These doc files are out of scope for FEAT-1227; flagged here so FEAT-1082 owners have precise line targets.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py` — covers `_get_state_badge()` and badge rendering functions that receive the `badges` dict from `to_dict()`; no exhaustive key-set assertions found — no changes required, but verify this file passes after FEAT-1227 lands to catch any unexpected coupling

### Dependent Issues

- FEAT-1228 (outer-CLI awareness) — builds on the `LoopsGlyphsConfig.parallel` field added here
- FEAT-1081 (parallel state CLI display) — imports `ParallelResult` once exported
- FEAT-1082 (parallel state documentation) — references `ParallelStateConfig` in API docs

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-21):_

- **FEAT-1074 blocker confirmed**: `scripts/little_loops/fsm/schema.py` (671 lines) defines `EvaluateConfig:25`, `RouteConfig:143`, `StateConfig:179`, `LLMConfig:414`, `LoopConfigOverrides:458`, `FSMLoop:523`. Neither `ParallelStateConfig` nor `ParallelResult` exists. Steps 1 and 6 cannot proceed until FEAT-1074 ships.
- **`__all__` insertion point verified** (`fsm/__init__.py:143-195`): `"ParallelResult"` and `"ParallelStateConfig"` both sort between `"PersistentExecutor"` (line 170) and `"RateLimitCircuit"` (line 171). Insert in that order (alphabetical: `ParallelResult` before `ParallelStateConfig`).
- **`LoopsGlyphsConfig` structure** (`config/features.py`): `@dataclass` decorator at line 256; class body lines 257–288. Field source order is `prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route` (NOT alphabetical). The issue's instruction to add `parallel` **after** `route` in `to_dict()`/`from_dict()`/field list is consistent with the prevailing append-at-end convention — follow source order, not alphabetical.
- **`config-schema.json` source order** (`loops.glyphs` block, lines 760–772): properties are in the same non-alphabetical source order as the dataclass (`prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route`). Insert `"parallel"` after the `"route"` entry (line 769) and before `"additionalProperties": false` (line 771), mirroring the dataclass ordering.
- **Test schema navigation pattern** (`test_config_schema.py`): Uses `data = json.loads(CONFIG_SCHEMA.read_text())` then chained `["properties"][...]["properties"]` navigation. Closest 4-level precedent is `test_issues_next_issue_in_schema` (lines 44–54); closest 2-level is `test_scratch_pad_properties` (lines 28–37). There is no existing test for any `loops.glyphs` property — `test_loops_glyphs_parallel_in_schema` will be the first.
- **Export-smoke test pattern** (`test_fsm_executor.py:4783-4799`, `TestRateLimitRetries`): Canonical form is a per-symbol method with an inline `from little_loops.fsm import X` and an identity assertion. `test_fsm_schema.py` currently imports only from internal paths (`little_loops.fsm.schema`, `little_loops.fsm.validation`) at lines 16–30, so `TestParallelStatePublicExports` will be the first public-API smoke-test class in that file.

## Dependencies

- FEAT-1074 must be complete for steps 1 and 6 (`ParallelStateConfig` and `ParallelResult` must exist in `schema.py`)

## Acceptance Criteria

- `from little_loops.fsm import ParallelStateConfig, ParallelResult` works without error
- `LoopsGlyphsConfig.parallel` field exists, defaults to `"∥"`, and round-trips through `to_dict()` / `from_dict()`
- `config-schema.json` validates `ll-config.json` files with `loops.glyphs.parallel`
- All existing tests pass; all new and updated assertions pass

## Impact

- **Priority**: P2
- **Effort**: Small — Additive-only: import extension, dataclass field, schema property, test assertion updates
- **Risk**: Low — No existing behavior modified
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `wiring`

---

**Completed** | Created: 2026-04-21 | Completed: 2026-04-21 | Priority: P2

## Resolution

Implemented steps 2–5 of the issue plan (config wiring). Steps 1 and 6 remain blocked on FEAT-1074 (which has not yet introduced `ParallelStateConfig` / `ParallelResult` in `fsm/schema.py`) and are deferred to follow-up work once FEAT-1074 ships.

Changes:
- `scripts/little_loops/config/features.py`: added `parallel: str = "∥"` to `LoopsGlyphsConfig`; extended `from_dict()` and `to_dict()` to carry the key.
- `config-schema.json`: added `"parallel"` property to the `loops.glyphs` object schema so `ll-config.json` can set `loops.glyphs.parallel` without being rejected by `additionalProperties: false`.
- `scripts/tests/test_config.py`: extended `test_defaults`, `test_from_dict_empty`, `test_to_dict_returns_all_keys`, `test_loops_glyphs_defaults_when_absent`, and `test_loops_glyphs_override_from_config`; added a new `test_from_dict_parallel_override` case.
- `scripts/tests/test_config_schema.py`: added `test_loops_glyphs_parallel_in_schema` sentinel.

Verification: 5014 passed (5 skipped) across `scripts/tests/`; `ruff check scripts/` clean; `mypy scripts/little_loops/` reports only the pre-existing `wcwidth` import-stubs warning in `cli/loop/layout.py` (unrelated).

Deferred (blocked on FEAT-1074):
- Step 1: exporting `ParallelStateConfig` and `ParallelResult` from `scripts/little_loops/fsm/__init__.py`.
- Step 6: `TestParallelStatePublicExports` smoke tests in `test_fsm_schema.py`.

## Session Log
- `/ll:manage-issue` - 2026-04-21T16:05:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc77cd46-8794-4705-b388-f7b4ccb9b3e6.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e308cc8e-783d-4af2-a83a-1df1e69af4b0.jsonl`
- `/ll:wire-issue` - 2026-04-21T15:56:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91c1fdd9-d4ff-46e3-9d24-8708037cba60.jsonl`
- `/ll:refine-issue` - 2026-04-21T15:49:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3e382f2-c757-4752-b41a-df5e90fcdb13.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c25b41ad-2e86-4d04-bea4-6daf251405e7.jsonl`
