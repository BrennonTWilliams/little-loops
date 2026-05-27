---
id: FEAT-1747
title: Design-tokens core infrastructure — schema, dataclass, loader, baseline tests
status: open
priority: P3
type: FEAT
parent: EPIC-1751
relates_to: [EPIC-1751]
discovered_date: 2026-05-27
discovered_by: issue-size-review
labels:
- feat
- config
- design-system
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

1. Add `design_tokens` block to `config-schema.json` before `analytics` (~line 1203)
2. Implement `DesignTokensConfig` in `features.py`; wire into `BRConfig._parse_config()`, add `.design_tokens` property and `to_dict()` support; export from `config/__init__.py`
3. Create `scripts/little_loops/design_tokens.py` with `DesignTokens` dataclass, `load_design_tokens()` (with reference resolution and cycle detection), `render_as_prompt_context()`, `render_as_css_vars()`
4. Fix no-warning fixtures in `test_hook_session_start.py` and `test_hooks_integration.py`; add `_validate_features` warning in `session_start.py`
5. Write `test_design_tokens.py`; add `TestDesignTokensConfig` and `TestBRConfigDesignTokensIntegration` to `test_config.py`; add `test_design_tokens_in_schema` to `test_config_schema.py`; run full suite

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
- `/ll:format-issue` - 2026-05-27T20:25:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/652005b7-b7e9-404a-9ee0-b21de41aeefa.jsonl`
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
