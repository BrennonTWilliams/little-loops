---
id: ENH-1346
type: ENH
priority: P2

size: Medium
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-05-03T16:23:45Z
parent: ENH-1344
---

# ENH-1346: Config Schema + Python Config Layer for `recursive-refine` Depth Limit

## Summary

Add `commands.recursive_refine.max_depth` to `config-schema.json`, create the `RecursiveRefineConfig` dataclass in `automation.py`, extend `CommandsConfig` with the new field, wire `max_depth: 3` into the `context:` block of `recursive-refine.yaml`, and export `RecursiveRefineConfig` from the config package.

## Current Behavior

No `recursive_refine` config block exists in `config-schema.json`. `CommandsConfig` has no `recursive_refine` field. `BRConfig.to_dict()` does not serialize a `recursive_refine` key. The `recursive-refine.yaml` context block omits `max_depth`, so ENH-1347's depth-tracking states cannot read a configurable default from `${context.max_depth}`.

## Expected Behavior

`config-schema.json` declares `commands.recursive_refine.max_depth` (integer, minimum 1, default 3). `RecursiveRefineConfig` dataclass exists in `automation.py` with a `from_dict` classmethod. `CommandsConfig` exposes `recursive_refine: RecursiveRefineConfig`. `BRConfig.to_dict()` serializes `commands.recursive_refine.max_depth`. `recursive-refine.yaml` includes `max_depth: 3` in its `context:` block. `RecursiveRefineConfig` is exported from `config/__init__.py`.

## Parent Issue

Decomposed from ENH-1344: Implement Per-Subtree Depth Limit in `recursive-refine`

## Motivation

The depth-tracking YAML states (ENH-1347) read `max_depth` from `ll-config.json` via an inline Python snippet. This child establishes the schema definition, Python API, and YAML context wiring so that:
- Config is validated against the schema
- Python callers can read `commands.recursive_refine.max_depth` via `BRConfig`
- The YAML loop has `${context.max_depth}` as a fallback default

## Proposed Solution

### Step 1 — Config schema

Add `commands.recursive_refine` to `config-schema.json`, following the existing `commands.confidence_gate` block (lines 351–421). Insert before the `additionalProperties: false` close at line 422:

```json
"recursive_refine": {
  "type": "object",
  "description": "Configuration for the recursive-refine loop",
  "properties": {
    "max_depth": {
      "type": "integer",
      "minimum": 1,
      "default": 3,
      "description": "Maximum decomposition depth per subtree (default 3)"
    }
  }
}
```

### Step 2 — Python config dataclass

In `scripts/little_loops/config/automation.py`, following the `ConfidenceGateConfig` pattern at lines 96–111:

```python
@dataclass
class RecursiveRefineConfig:
    max_depth: int = 3

    @classmethod
    def from_dict(cls, data: dict) -> "RecursiveRefineConfig":
        return cls(max_depth=data.get("max_depth", 3))
```

Extend `CommandsConfig` (lines 152–172) with:
```python
recursive_refine: RecursiveRefineConfig = field(default_factory=RecursiveRefineConfig)
```

Update `CommandsConfig.from_dict()` (lines 163–172) to include:
```python
recursive_refine=RecursiveRefineConfig.from_dict(data.get("recursive_refine", {}))
```

### Step 3 — Config package exports

In `scripts/little_loops/config/__init__.py`, add `RecursiveRefineConfig` to the `from .automation import (...)` block and to `__all__`, following the pattern for `ConfidenceGateConfig` and `RateLimitsConfig`.

### Step 4 — `BRConfig.to_dict()` serialization

In `scripts/little_loops/config/core.py::BRConfig.to_dict()`, add:
```python
"recursive_refine": {"max_depth": self._commands.recursive_refine.max_depth}
```
inside the `"commands"` dict, alongside the existing `confidence_gate`, `tdd_mode`, `rate_limits` entries.

### Step 5 — YAML context block

In `scripts/little_loops/loops/recursive-refine.yaml`, add to the `context:` block:
```yaml
max_depth: 3  # canonical: commands.recursive_refine.max_depth
```

### Step 6 — Tests (TDD mode)

**`test_config_schema.py`** — add `TestConfigSchema.test_recursive_refine_in_schema`: assert `commands.recursive_refine` key exists with `max_depth` (`type: integer`, `minimum: 1`, `default: 3`), following the `test_commands_rate_limits_block` pattern (line 56).

**`test_config.py::TestCommandsConfig`**:
- `test_from_dict_with_all_fields` (line 449): add `"recursive_refine": {"max_depth": 5}` to `data` dict and `assert config.recursive_refine.max_depth == 5`; import `RecursiveRefineConfig`
- `test_from_dict_with_defaults` (line 473): add `assert config.recursive_refine.max_depth == 3`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_builtin_loops.py::TestRecursiveRefineLoop.test_context_thresholds_defined` — add `assert "max_depth" in ctx` to guard the YAML context block after Step 5
8. Add `TestRecursiveRefineConfig` class to `scripts/tests/test_config.py` — standalone dataclass tests (`test_from_dict_with_all_fields`, `test_from_dict_with_defaults`) following `TestConfidenceGateConfig` (line 387)
9. Add `TestBRConfig.test_commands_recursive_refine_in_to_dict` to `scripts/tests/test_config.py` — assert `result["commands"]["recursive_refine"]["max_depth"] == 3` in `to_dict()` output

## Acceptance Criteria

- [ ] `config-schema.json` includes `commands.recursive_refine.max_depth` (integer, minimum 1, default 3)
- [ ] `RecursiveRefineConfig` dataclass exists in `automation.py` with `from_dict` classmethod
- [ ] `CommandsConfig` has `recursive_refine: RecursiveRefineConfig` field wired through `from_dict`
- [ ] `RecursiveRefineConfig` exported from `config/__init__.py` in `__all__`
- [ ] `BRConfig.to_dict()` serializes `commands.recursive_refine.max_depth`
- [ ] `recursive-refine.yaml` has `max_depth: 3` in its `context:` block
- [ ] New config schema test passes
- [ ] `test_from_dict_with_all_fields` and `test_from_dict_with_defaults` updated and passing
- [ ] No regression in existing config tests

## Scope Boundaries

- **In scope**: config-schema.json, automation.py, config/__init__.py, config/core.py, recursive-refine.yaml (context block only), test_config.py, test_config_schema.py
- **Out of scope**: YAML depth-tracking states and transitions (ENH-1347), YAML test files (ENH-1347)

## Integration Map

### Files to Modify

- `config-schema.json` — add `commands.recursive_refine` block
- `scripts/little_loops/config/automation.py` — add `RecursiveRefineConfig` dataclass, extend `CommandsConfig`
- `scripts/little_loops/config/__init__.py` — export `RecursiveRefineConfig`
- `scripts/little_loops/config/core.py` — serialize `recursive_refine` in `to_dict()`
- `scripts/little_loops/loops/recursive-refine.yaml` — add `max_depth: 3` to `context:` block
- `scripts/tests/test_config_schema.py` — add schema test
- `scripts/tests/test_config.py` — update `TestCommandsConfig` tests

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports BRConfig as public API; no change needed unless RecursiveRefineConfig is promoted to top-level export
- `scripts/little_loops/fsm/schema.py` — calls `BRConfig.to_dict()` for FSM context injection; additive change (new key) won't break callers
- `scripts/little_loops/cli/loop/lifecycle.py` — reads `config.commands.rate_limits.*` via `config.commands`; attribute addition is backwards-compatible
- `scripts/little_loops/cli/loop/run.py` — same `config.commands.*` access pattern as `lifecycle.py`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestRecursiveRefineLoop.test_context_thresholds_defined` (line 1700) — currently asserts `readiness_threshold`, `outcome_threshold`, `max_refine_count` are `in ctx`; add `assert "max_depth" in ctx` when Step 5 adds `max_depth` to YAML context block [Agent 3]
- `scripts/tests/test_config.py::TestRecursiveRefineConfig` — new standalone test class needed (follow `TestConfidenceGateConfig` at line 387): `test_from_dict_with_all_fields` (pass `{"max_depth": 5}`, assert 5) and `test_from_dict_with_defaults` (pass `{}`, assert 3); the issue lists only `TestCommandsConfig` updates, not the standalone dataclass class [Agent 3]
- `scripts/tests/test_config.py::TestBRConfig.test_commands_recursive_refine_in_to_dict` — new test: load BRConfig, call `to_dict()`, assert `result["commands"]["recursive_refine"]["max_depth"] == 3`; follow `test_to_dict_confidence_gate_schema_aligned_keys` (line 744) [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/show-output.md` — `## commands --show` section (lines 71–86) renders `{{config.commands.*}}`; after ENH-1346, `max_depth` is absent from the display block. Likely in scope for ENH-1345, but flagged as a gap if ENH-1345 doesn't cover configure skill files [Agent 2]
- `skills/configure/areas.md` — `## Area: commands` Current Values block (lines 312–328) lists every `commands.*` key; `max_depth` will be absent. Same ENH-1345 gap note [Agent 2]
- `docs/reference/API.md` — `CommandsConfig` properties table (line 102) lists `confidence_gate`, `tdd_mode`, `rate_limits` but will be missing `RecursiveRefineConfig`; `test_circuit_breaker_doc_wiring.py::TestApiReferenceWiring` does not assert on `recursive_refine` so no test fails, but it's a documentation gap [Agent 2]

### Similar Patterns

- `scripts/little_loops/config/automation.py:95–111` — `ConfidenceGateConfig` pattern to follow (`@dataclass` decorator at 95, `from_dict` at 103)
- `scripts/little_loops/config/automation.py:151–172` — `CommandsConfig` dataclass (`@dataclass` at 151, `from_dict` at 163)
- `scripts/tests/test_config_schema.py:56–80` — `test_commands_rate_limits_block` pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line numbers (2026-05-03):**
- `core.py:364` — `BRConfig.to_dict()` definition; `commands` dict serialization at lines ~419–435
- `config/__init__.py:13–21` — `from .automation import (...)` block; `ConfidenceGateConfig` exported at line 66, `RateLimitsConfig` at line 67; add `RecursiveRefineConfig` here and in `__all__`
- `recursive-refine.yaml:24–27` — current `context:` block (contains `readiness_threshold`, `outcome_threshold`, `max_refine_count`)
- `test_config.py:11–42` — import block; add `RecursiveRefineConfig` alongside `ConfidenceGateConfig`, `CommandsConfig`
- `test_config.py:449–471` — `test_from_dict_with_all_fields` ✓
- `test_config.py:473–485` — `test_from_dict_with_defaults` ✓

**Critical: `max_refine_count` already exists in schema at lines 382–388.**
The commands block already has `max_refine_count` (integer, minimum 1, maximum 20, default 5) between `tdd_mode` (377–381) and `rate_limits` (389–420). Insert the new `recursive_refine` block AFTER `rate_limits` closes (~line 420), immediately before the commands `additionalProperties: false` at line 422. Do NOT insert between `max_refine_count` and `rate_limits`.

## Impact

- **Priority**: P2
- **Effort**: Small — Pure config/dataclass additions following established patterns
- **Risk**: Very Low — No behavioral change; adds config schema and Python API only
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `automation`

## Resolution

- Added `RecursiveRefineConfig` dataclass to `automation.py` with `max_depth: int = 3` and `from_dict` classmethod
- Extended `CommandsConfig` with `recursive_refine: RecursiveRefineConfig` field wired through `from_dict`
- Exported `RecursiveRefineConfig` from `config/__init__.py` and `__all__`
- Added `recursive_refine.max_depth` serialization to `BRConfig.to_dict()` in `core.py`
- Added `max_depth: 3` to `recursive-refine.yaml` context block
- Added `commands.recursive_refine` block to `config-schema.json` (integer, min 1, default 3)
- Added `TestConfigSchema.test_commands_recursive_refine_in_schema` 
- Added `TestRecursiveRefineConfig` standalone dataclass tests
- Updated `TestCommandsConfig` tests with `recursive_refine` assertions
- Added `TestBRConfig.test_commands_recursive_refine_in_to_dict`
- Updated `test_context_thresholds_defined` to assert `max_depth in ctx`
- All 15 targeted tests pass; no regressions introduced

## Status

**Completed** | Created: 2026-05-03 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-03T16:15:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7f2fd3b-a506-4110-abbd-b70c10d63b86.jsonl`
- `/ll:confidence-check` - 2026-05-03T16:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c49f96c7-eda1-4bf9-ba6b-63bf3a2b032a.jsonl`
- `/ll:wire-issue` - 2026-05-03T16:06:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b5e8540-a2e4-4c22-9b76-4cebdd1a1935.jsonl`
- `/ll:refine-issue` - 2026-05-03T16:02:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47226442-43a7-4dd0-8da1-5a1728b7a2cd.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbb0e63c-be49-432f-9671-f8f7f8a4d675.jsonl`
