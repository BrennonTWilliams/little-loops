---
id: FEAT-1747
title: "Design-tokens core infrastructure \u2014 schema, dataclass, loader, baseline\
  \ tests"
status: done
priority: P3
type: FEAT
parent: EPIC-1751
relates_to:
- EPIC-1751
discovered_date: 2026-05-27
discovered_by: issue-size-review
completed_at: 2026-05-27 21:54:59+00:00
labels:
- feat
- config
- design-system
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1747: Design-tokens core infrastructure — schema, dataclass, loader, baseline tests

## Summary

Add the foundational infrastructure for design-token support: the `design_tokens` JSON Schema block, the `DesignTokensConfig` dataclass, the `design_tokens.py` loader module with renderers, and all associated tests. This is the dependency gate for the other three FEAT-1746 children.

## Parent Issue
Decomposed from FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Current Behavior

The codebase has no design-token concept. `config-schema.json` has no `design_tokens` property. No `DesignTokensConfig` dataclass, no `design_tokens.py` loader, and no renderers exist. Artifact-generating loops produce HTML/CSS using ad-hoc styling with no shared token source.

## Expected Behavior

`config-schema.json` accepts a `design_tokens` block with six properties. `BRConfig` exposes a `.design_tokens` property returning a `DesignTokensConfig` instance. `load_design_tokens(config)` resolves token references across primitives/semantic/theme layers and returns a `DesignTokens` object (or `None` when disabled/path missing). Session-start warns when `enabled: true` but path is absent.

## Motivation

- Establishes the single source of truth for design system tokens consumed by artifact-generating loops
- Eliminates per-loop color hardcoding; any loop can call `load_design_tokens()` and get resolved values
- Dependency gate for FEAT-1748, FEAT-1749, FEAT-1750 — none of the other three children can be completed without this infrastructure

## Use Case

**Who**: A developer configuring ll for a branded project

**Context**: Running built-in HTML/SVG artifact loops and wanting consistent visual output across all generated files

**Goal**: Configure a `design_tokens` block in `.ll/ll-config.json` once so every loop can load and apply semantic token values

**Outcome**: `load_design_tokens(config)` returns a resolved `DesignTokens` object; loops call `render_as_prompt_context()` to inject token values into generation prompts; generated artifacts reference `color.text.primary`, `color.surface.primary` etc. from the project's config

## API/Interface

```python
@dataclass(frozen=True)
class DesignTokens:
    primitives: dict
    semantic: dict
    theme: dict
    resolved: dict      # flat name -> concrete value, post reference-resolution
    source_path: Path

def load_design_tokens(
    config: BRConfig,
    theme: str | None = None,
) -> DesignTokens | None: ...   # None when disabled or path missing

def render_as_prompt_context(tokens: DesignTokens) -> str: ...
def render_as_css_vars(tokens: DesignTokens) -> str: ...
```

## Proposed Solution

### 1. Schema addition (`config-schema.json`)

Add a top-level `design_tokens` property (sibling to `documents`/`orchestration`; root has `additionalProperties: false` so this must be declared):

```jsonc
"design_tokens": {
  "type": "object",
  "description": "Design system tokens consumed by built-in artifact-generating loops",
  "properties": {
    "enabled":          { "type": "boolean", "default": true },
    "path":             { "type": "string",  "default": ".ll/design-tokens" },
    "primitives_file":  { "type": "string",  "default": "primitives.json" },
    "semantic_file":    { "type": "string",  "default": "semantic.json" },
    "themes_dir":       { "type": "string",  "default": "themes" },
    "active_theme":     { "type": "string",  "default": "light" }
  },
  "additionalProperties": false
}
```

**Insert before `analytics` (~line 1203).** Root `additionalProperties: false` is at line 1216 — the new key must be declared inside the root properties object.

### 2. `DesignTokensConfig` dataclass (`scripts/little_loops/config/features.py`)

Model on `ScanConfig` (multi-field + `from_dict` classmethod, `field(default_factory=...)`):

```python
@dataclass
class DesignTokensConfig:
    enabled: bool = True
    path: str = ".ll/design-tokens"
    primitives_file: str = "primitives.json"
    semantic_file: str = "semantic.json"
    themes_dir: str = "themes"
    active_theme: str = "light"

    @classmethod
    def from_dict(cls, data: dict) -> "DesignTokensConfig":
        return cls(
            enabled=data.get("enabled", True),
            path=data.get("path", ".ll/design-tokens"),
            ...
        )
```

Wire into `BRConfig._parse_config()` (~lines 188–215):
```python
self._design_tokens = DesignTokensConfig.from_dict(
    self._raw_config.get("design_tokens", {})
)
```

Add `@property design_tokens` and include in `to_dict()`. Export from `config/__init__.py`.

### 3. `design_tokens.py` loader (`scripts/little_loops/design_tokens.py`)

```python
@dataclass(frozen=True)
class DesignTokens:
    primitives: dict
    semantic: dict
    theme: dict
    resolved: dict     # flat name -> concrete value, post reference-resolution
    source_path: Path

def load_design_tokens(
    config: BRConfig,
    theme: str | None = None,
) -> DesignTokens | None: ...    # None when disabled or path missing

def render_as_prompt_context(tokens: DesignTokens) -> str: ...
def render_as_css_vars(tokens: DesignTokens) -> str: ...
```

- Reference-resolution: `{color.brand.500}` → resolved primitive value. Use `BRConfig.resolve_variable` style (return None on miss) or raise on unknown alias — pick one and document it.
- Cycle detection: raise a clear error on circular token references.
- When `design_tokens.enabled: false` or the path doesn't exist: return `None`.

### 4. Fix no-warning test fixtures (prerequisite)

Before wiring `_validate_features`, fix tests that will break when `design_tokens.enabled` defaults to `True`:

- `tests/test_hook_session_start.py`: `TestSessionStartFeatureValidation.test_no_warnings_when_features_disabled` and `test_no_product_warning_even_when_enabled` — add `"design_tokens": {"enabled": False}` to their fixture configs.
- `tests/test_hooks_integration.py`: `TestSessionStartValidation.test_no_warnings_when_features_disabled` and `test_no_warnings_when_properly_configured` — same fix.

Add validation to `hooks/session_start.py:_validate_features()` (~lines 170–177): warn when `design_tokens.enabled: true` but `path` doesn't exist, mirroring the existing `documents` warn pattern.

Add new test: `test_warns_design_tokens_enabled_without_path` following the `test_warns_sync_enabled_without_github` pattern.

### 5. Tests

**New file** `scripts/tests/test_design_tokens.py`:
- `load_design_tokens` happy path (flat resolution)
- Theme override layering
- Missing-file fallback (returns None)
- Unknown-token error path
- Cycle detection raises
- `render_as_prompt_context` output shape
- `render_as_css_vars` output shape
- Disabled feature returns None

**Update** `scripts/tests/test_config.py`:
- Add `TestDesignTokensConfig` (tests `from_dict({})` defaults and `from_dict(full_data)`)
- Add `TestBRConfigDesignTokensIntegration` (property absent, present, round-trip `to_dict()`)
- Follow `TestLearningTestsConfig` / `TestBRConfigLearningTestsIntegration` pattern (lines 2097–2127)
- Add `DesignTokensConfig` to the import block

**Update** `scripts/tests/test_config_schema.py`:
- Add `TestConfigSchema.test_design_tokens_in_schema` following the `test_analytics_in_schema` pattern (lines 136–155): assert top-level key, `type == "object"`, `additionalProperties == False`, enumerate each sub-property with its type and default.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_validate_features()` actual range is `session_start.py:150-178` (the issue text says ~170-177 above); the function uses **raw dict access** (`config.get("design_tokens", {})`), not the typed `BRConfig.design_tokens` property — match that pattern exactly for the new warning
- Wiring a new typed dataclass into `BRConfig` requires **five** locations in `core.py`, not just `_parse_config`: (1) import block at lines 23-31, (2) `_parse_config` at lines 188-215, (3) the new `@property` (after the last property at ~line 290), (4) `to_dict()` at lines 475-644, plus the `__init__.py` import at lines 38-57 and `__all__` at lines 60-98
- `ScanConfig.from_dict` repeats the same literal defaults in both `field(default_factory=...)` and inside `from_dict` (no delegation) — do the same for `DesignTokensConfig`
- `test_no_warnings_when_features_disabled` in `test_hook_session_start.py:184-193` and `test_hooks_integration.py:1596-1623` only disable `sync`, `documents`, `product` — add `"design_tokens": {"enabled": False}` to each
- `test_no_product_warning_even_when_enabled` in `test_hook_session_start.py:195-208` and `test_no_warnings_when_properly_configured` in `test_hooks_integration.py:1555-1594` also need `"design_tokens": {"enabled": False}` (or a valid configured block) because `enabled` defaults to `True`

## Files to Modify / Create

### Modified
- `config-schema.json` — add `design_tokens` block
- `scripts/little_loops/config/features.py` — add `DesignTokensConfig`
- `scripts/little_loops/config/core.py` — wire `DesignTokensConfig` into `BRConfig`
- `scripts/little_loops/config/__init__.py` — export `DesignTokensConfig`
- `scripts/little_loops/hooks/session_start.py` — add `_validate_features` warning
- `scripts/tests/test_config.py` — add dataclass + integration tests
- `scripts/tests/test_config_schema.py` — add schema test
- `scripts/tests/test_hook_session_start.py` — fix fixtures + add warning test
- `scripts/tests/test_hooks_integration.py` — fix fixtures

### New
- `scripts/little_loops/design_tokens.py`
- `scripts/tests/test_design_tokens.py`

## Integration Map

### Files to Modify
- `config-schema.json:1203` — insert `design_tokens` block before `analytics`; root `additionalProperties: false` is at line 1216
- `scripts/little_loops/config/features.py:265` — add `DesignTokensConfig` dataclass after `ScanConfig` (ends ~line 265)
- `scripts/little_loops/config/core.py:23-31` — add `DesignTokensConfig` to `from little_loops.config.features import (...)` block
- `scripts/little_loops/config/core.py:188-215` — add `self._design_tokens = DesignTokensConfig.from_dict(self._raw_config.get("design_tokens", {}))` in `_parse_config`
- `scripts/little_loops/config/core.py:~290` — add `@property design_tokens` after the last existing property
- `scripts/little_loops/config/core.py:475-644` — add `design_tokens` top-level key in `to_dict()`
- `scripts/little_loops/config/__init__.py:38-57` — add `DesignTokensConfig` to the `features.py` import block
- `scripts/little_loops/config/__init__.py:60-98` — add `DesignTokensConfig` to `__all__`
- `scripts/little_loops/hooks/session_start.py:150-178` — add design_tokens warning in `_validate_features()` using raw dict: `config.get("design_tokens", {})`, `is True` identity check, path-existence check
- `scripts/tests/test_config.py:2097-2127` — add `TestDesignTokensConfig` and `TestBRConfigDesignTokensIntegration` after `TestBRConfigLearningTestsIntegration`
- `scripts/tests/test_config_schema.py:136-155` — add `test_design_tokens_in_schema` in `TestConfigSchema` following `test_analytics_in_schema`
- `scripts/tests/test_hook_session_start.py:184-193` — add `"design_tokens": {"enabled": False}` to `test_no_warnings_when_features_disabled` fixture dict
- `scripts/tests/test_hook_session_start.py:195-208` — add `"design_tokens": {"enabled": False}` to `test_no_product_warning_even_when_enabled` fixture dict
- `scripts/tests/test_hooks_integration.py:1555-1594` — add `"design_tokens": {"enabled": False}` to `test_no_warnings_when_properly_configured` fixture dict
- `scripts/tests/test_hooks_integration.py:1596-1623` — add `"design_tokens": {"enabled": False}` to `test_no_warnings_when_features_disabled` fixture dict

### New Files
- `scripts/little_loops/design_tokens.py` — new loader module (no existing callers)
- `scripts/tests/test_design_tokens.py` — new test file

### Similar Patterns (Verified)
- `scripts/little_loops/config/features.py:246-265` — `ScanConfig` (multi-field dataclass with `from_dict`; uses `field(default_factory=...)` for mutable fields; `from_dict` repeats the same literal defaults)
- `scripts/little_loops/config/core.py:646-668` — `resolve_variable` (dot-path traversal over `to_dict()`, returns `None` on any miss — reference for token reference-resolution semantics)
- `scripts/tests/test_config.py:2097-2127` — `TestLearningTestsConfig` + `TestBRConfigLearningTestsIntegration` (exact test class templates including `temp_project_dir` fixture usage)
- `scripts/tests/test_config_schema.py:136-155` — `test_analytics_in_schema` (asserts key presence, `type == "object"`, `additionalProperties is False`, each sub-property type and default)
- `scripts/tests/test_hook_session_start.py:163-209` — `TestSessionStartFeatureValidation` with `_run_with` helper, `in_tmp` fixture, and `test_warns_sync_enabled_without_github` / all-disabled negative pattern

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:97-115` — BRConfig `#### Properties` table lists every config property by name and type; needs `design_tokens \| DesignTokensConfig \| Design system token settings` row added after `dependency_mapping` [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:7-225` — "Full Configuration Example" JSON block enumerates every top-level key; needs a `design_tokens` object entry added. "Configuration Sections" at line 228 has a `###` section per key; needs `### design_tokens` section with property table [Agent 2 finding]
- `docs/ARCHITECTURE.md:596-606` — BRConfig class diagram in `classDiagram` block omits newer properties; optionally add `+design_tokens: DesignTokensConfig` to the BRConfig class node [Agent 2 finding]

Note: `docs/reference/CONFIGURATION.md` full content is primarily FEAT-1750 scope ("design-tokens-init-configure-docs"); only the property-table row in `docs/reference/API.md` and the ARCHITECTURE.md diagram are strictly in-scope for FEAT-1747.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — needs new `test_warns_design_tokens_enabled_without_path` method in `TestSessionStartValidation`, analogous to `test_warns_sync_without_github` at line 1507 (writes `{"design_tokens": {"enabled": True}}` to ll-config.json, runs hook script, asserts warning string in stderr). The issue currently only adds this test in `test_hook_session_start.py` — both levels need coverage [Agent 3 finding]

## Acceptance Criteria

- [ ] `config-schema.json` defines `design_tokens` with all six properties; schema validates a config containing the block.
- [ ] `DesignTokensConfig` defaults match schema defaults; `from_dict({})` produces defaults; `to_dict()` round-trips.
- [ ] `load_design_tokens` resolves token references across primitives/semantic/theme layers; reference cycles raise a clear error.
- [ ] `render_as_prompt_context` returns a compact markdown/JSON snippet; `render_as_css_vars` returns `:root { ... }` block.
- [ ] When `enabled: false` or path missing, `load_design_tokens` returns `None` without error.
- [ ] All existing `"Warning:" not in` tests pass after fixture fixes.
- [ ] `_validate_features` emits a warning when `enabled: true` but path is absent.
- [ ] All new and updated tests pass: `pytest scripts/tests/test_design_tokens.py scripts/tests/test_config.py scripts/tests/test_config_schema.py scripts/tests/test_hook_session_start.py scripts/tests/test_hooks_integration.py`

## Implementation Steps

1. Add `design_tokens` block to `config-schema.json` before `analytics` at line 1203; root `additionalProperties: false` is at line 1216
2. Add `DesignTokensConfig` dataclass to `features.py` after `ScanConfig` (~line 265); add import in `core.py:23-31`; add parse assignment in `_parse_config` (lines 188-215); add `@property design_tokens` (~line 290); add `design_tokens` key in `to_dict()` (lines 475-644); add `DesignTokensConfig` to `config/__init__.py` import (lines 38-57) and `__all__` (lines 60-98)
3. Create `scripts/little_loops/design_tokens.py` with `DesignTokens` dataclass, `load_design_tokens()` (reference resolution using `resolve_variable`-style None-on-miss semantics, cycle detection), `render_as_prompt_context()`, `render_as_css_vars()`
4. Fix no-warning fixtures in `test_hook_session_start.py:184-208` and `test_hooks_integration.py:1555-1623` by adding `"design_tokens": {"enabled": False}`; add `_validate_features` warning in `session_start.py:150-178` using raw dict access (`config.get("design_tokens", {})` + `is True` + path check)
5. Write `test_design_tokens.py`; add `TestDesignTokensConfig` and `TestBRConfigDesignTokensIntegration` to `test_config.py` after line 2127; add `test_design_tokens_in_schema` to `TestConfigSchema` in `test_config_schema.py` after line 155; run `pytest scripts/tests/test_design_tokens.py scripts/tests/test_config.py scripts/tests/test_config_schema.py scripts/tests/test_hook_session_start.py scripts/tests/test_hooks_integration.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `test_warns_design_tokens_enabled_without_path` to `TestSessionStartValidation` in `test_hooks_integration.py` — mirrors `test_warns_sync_without_github` at line 1507 (write `{"design_tokens": {"enabled": True}}` to `.ll/ll-config.json`, run hook script subprocess, assert warning string in `result.stderr`)
7. Add `design_tokens \| DesignTokensConfig \| Design system token settings` row to the `#### Properties` table in `docs/reference/API.md:97-115` (BRConfig Properties section)

## Impact

- **Priority**: P3 — foundational; no existing feature breaks without it, but blocks FEAT-1749
- **Effort**: Medium — new module, schema extension, multiple test classes across five test files
- **Risk**: Low — purely additive; no existing APIs change
- **Breaking Change**: No

## Similar Patterns

- **`ScanConfig`** (`scripts/little_loops/config/features.py:ScanConfig`) — multi-field dataclass with `from_dict` and `field(default_factory=...)`.
- **`OrchestrationConfig`** (`scripts/little_loops/config/orchestration.py`) — minimal single-module config class.
- **`BRConfig.resolve_variable`** (`config/core.py`) — dot-path traversal returning None on miss — token reference resolution analogue.
- **`TestLearningTestsConfig`** (`scripts/tests/test_config.py:2097`) — test class template to follow.
- **`TestConfigSchema.test_analytics_in_schema`** (`scripts/tests/test_config_schema.py:136`) — schema test template.

## Session Log
- `/ll:ready-issue` - 2026-05-27T21:47:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d93cb966-39e0-4c09-bae4-94a3d9170aac.jsonl`
- `/ll:confidence-check` - 2026-05-27T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44bd17d7-665a-4c5a-a921-73c4db032c3e.jsonl`
- `/ll:wire-issue` - 2026-05-27T21:42:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c18ac59-f823-4be7-916e-f317ba96b849.jsonl`
- `/ll:refine-issue` - 2026-05-27T21:36:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa38874c-af9f-4c14-8800-0dd6b1affa99.jsonl`
- `/ll:format-issue` - 2026-05-27T20:25:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
