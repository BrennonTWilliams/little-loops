---
id: ENH-1132
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1133, ENH-1134, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1132: 429 Resilience — Schema, Config & Fragment Foundation

## Summary

Add the schema and configuration foundation for multi-hour 429 resilience: new `StateConfig` fields for two-tier retry, a `RateLimitsConfig` dataclass under `commands`, updates to `config-schema.json`, and an expanded `with_rate_limit_handling` fragment. This is the prerequisite for ENH-1133 (executor), ENH-1134 (circuit breaker), and ENH-1135 (heartbeat/docs).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

## Current Behavior

`StateConfig` supports only short-tier rate-limit retries (`max_rate_limit_retries`, `rate_limit_backoff_base_seconds`) with no wall-clock budget and no long-wait ladder. There is no `commands.rate_limits` global config block in `config-schema.json`, no `RateLimitsConfig` dataclass, and the `with_rate_limit_handling` fragment in `lib/common.yaml` ships only the 3-retry/30s-base defaults. Consumers that need multi-hour 429 resilience have no schema surface to configure it.

## Motivation

ENH-1131 adds two new per-state config fields (`rate_limit_max_wait_seconds`, `rate_limit_long_wait_ladder`) and a new `commands.rate_limits` global config block. These must be declared in schema and validated before any executor logic can consume them. The `with_rate_limit_handling` fragment in `lib/common.yaml` also needs to ship long-wait defaults so existing loop consumers get the new behavior without per-state overrides.

## Expected Behavior

### 1. `StateConfig` new fields (`fsm/schema.py:239-241`)

Add two optional fields:
- `rate_limit_max_wait_seconds: Optional[int] = None` — total wall-clock budget before routing to `on_rate_limit_exhausted` (default from global config: 21600 = 6h)
- `rate_limit_long_wait_ladder: Optional[list[int]] = None` — backoff ladder for long-wait tier (default: `[300, 900, 1800, 3600]`)

Extend `to_dict` (lines 287-291), `from_dict` (lines 352-354), and docstring (lines 208-214).

### 2. JSON schema (`fsm/fsm-loop-schema.json:261-275`)

Add the two new per-state properties. Both optional, types: integer / array-of-integer.

### 3. Validation (`fsm/validation.py:304-333`)

Extend rate-limit cross-field validation:
- `rate_limit_long_wait_ladder` non-empty if specified; all values > 0
- `rate_limit_max_wait_seconds` > 0 if specified

### 4. `RateLimitsConfig` dataclass (`config/automation.py:112-131`)

```python
@dataclass
class RateLimitsConfig:
    max_wait_seconds: int = 21600
    long_wait_ladder: list[int] = field(default_factory=lambda: [300, 900, 1800, 3600])
    circuit_breaker_enabled: bool = True
    circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"
```

Compose into `CommandsConfig` (lines 112-131) as `rate_limits: RateLimitsConfig = field(default_factory=RateLimitsConfig)`, and extend `CommandsConfig.from_dict()` to call `RateLimitsConfig.from_dict(data.get("rate_limits", {}))` (mirroring the existing `confidence_gate` composition).

### 5. `config-schema.json` (`commands` object, ~lines 282-340`)

Add `rate_limits` nested object inside `commands` (which has `additionalProperties: false`):
```json
"rate_limits": {
  "type": "object",
  "properties": {
    "max_wait_seconds": { "type": "integer", "minimum": 0 },
    "long_wait_ladder": { "type": "array", "items": { "type": "integer", "minimum": 1 } },
    "circuit_breaker_enabled": { "type": "boolean" },
    "circuit_breaker_path": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 6. Config serialization (`config/core.py:401-411`)

Extend `BRConfig.to_dict()` to serialize the new `commands.rate_limits` block so `${commands.rate_limits.max_wait_seconds}` variable interpolation works inside loop YAMLs.

### 7. Public config export (`config/__init__.py`)

Re-export `RateLimitsConfig` alongside `CommandsConfig`.

### 8. Fragment update (`loops/lib/common.yaml:49-55`)

Extend `with_rate_limit_handling` to include:
```yaml
rate_limit_max_wait_seconds: 21600
rate_limit_long_wait_ladder: [300, 900, 1800, 3600]
```

Document opt-out (set budget to 0 or omit ladder) in the fragment description.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/schema.py` — add fields, extend `to_dict`/`from_dict`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add per-state properties
- `scripts/little_loops/fsm/validation.py` — cross-field validation
- `scripts/little_loops/config/automation.py` — `RateLimitsConfig` dataclass + `CommandsConfig` composition
- `config-schema.json` — `commands.rate_limits` block
- `scripts/little_loops/config/core.py` — serialization wiring
- `scripts/little_loops/config/__init__.py` — re-export
- `scripts/little_loops/loops/lib/common.yaml` — fragment defaults

### Dependent Files (verify no breakage)

- `scripts/little_loops/loops/autodev.yaml:92-98,165-168,310-318` — uses `with_rate_limit_handling`; verify fragment expansion still validates
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:92-95` — same
- `scripts/little_loops/loops/recursive-refine.yaml:95-101` — same

### Tests

- `scripts/tests/test_fsm_schema.py` — new `StateConfig` fields: defaults, round-trip
- `scripts/tests/test_fsm_validation.py` — cross-field validation for new fields
- `scripts/tests/test_fsm_fragments.py:628,634` — update to assert new fragment defaults (`rate_limit_max_wait_seconds == 21600`, `rate_limit_long_wait_ladder == [300, 900, 1800, 3600]`) alongside existing assertions
- `scripts/tests/test_config.py:371` — add `TestRateLimitsConfig` class following `TestConfidenceGateConfig` pattern (defaults + full-fields round-trip)
- `scripts/tests/test_builtin_loops.py` — confirm updated built-in loops still validate

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — new test asserting `commands.rate_limits` property block present; critical because `commands` has `additionalProperties: false` at `config-schema.json:339` — follow pattern of existing `test_extensions_in_properties` test in that file

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/reference.md:939-965` — enumerates `StateConfig` rate-limit fields; will be stale after ENH-1132 adds `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder`
- `skills/create-loop/loop-types.md:791-793` — annotated YAML example listing the three existing rate-limit fields; add the two new fields to keep in sync

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/tests/test_config_schema.py` — add test asserting `commands.rate_limits` block present in schema; the `additionalProperties: false` guard on `commands` (line 339) makes this a load-bearing check — if omitted, any config that sets `commands.rate_limits` will fail JSON Schema validation
10. Update `skills/create-loop/reference.md:939-965` — add `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` to the rate-limit field reference table
11. Update `skills/create-loop/loop-types.md:791-793` — add two new fields to the annotated YAML example

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Pattern to mirror**: `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:93-109`) → composed into `CommandsConfig` via `field(default_factory=...)` and `from_dict` delegation. Replicate this exact shape for `RateLimitsConfig`.
- **Pattern to mirror (serialization)**: `BRConfig.to_dict()` already emits a nested `confidence_gate` dict inside `commands` (`scripts/little_loops/config/core.py:405-409`). Add `rate_limits` as a sibling sub-dict between `tdd_mode` and the closing brace.
- **Pattern to mirror (StateConfig tests)**: `test_fsm_schema.py` uses a 5-test pattern for optional rate-limit fields (default-None, from_dict, to_dict, absent-from-to_dict-when-None, roundtrip). Apply the same 5-test shape to the two new fields.
- **Pattern to mirror (test_config)**: `TestConfidenceGateConfig` + `TestCommandsConfig` at `test_config.py:340-401` — one class tests the leaf dataclass (all-fields + defaults), parent-class composition test verifies the nested field survives `CommandsConfig.from_dict({...})`.
- **Existing `_known_on_keys` (schema.py:316-327)**: already includes `"on_rate_limit_exhausted"`; **no change needed** — the new fields are not `on_*` transition keys and won't leak into `extra_routes`.
- **Config-schema insertion point**: root `config-schema.json` `commands` object has `additionalProperties: false` at line 339. New `rate_limits` property must insert *before* that line (after `max_refine_count` at 337), or it will be rejected.
- **Fragment test extension**: `test_fsm_fragments.py:628-632` (`test_with_rate_limit_handling_default_fields`) asserts `max_rate_limit_retries == 3` and `rate_limit_backoff_base_seconds == 30`. Extend this same method with the two new default assertions rather than creating a parallel method. The resolve-integration test at line 634 (`test_with_rate_limit_handling_resolves_from_real_common_yaml`) should also gain equivalent assertions on the resolved state dict.
- **Out of scope (confirmed)**: `generate_schemas.py` emits JSON schemas for `LLEvent` types only (see module docstring) — it has no awareness of config-schema.json or fsm-loop-schema.json, so it does not need updating for this issue.
- **Docs deferred**: `docs/reference/CONFIGURATION.md`, `COMMANDS.md`, `CHANGELOG.md` reference rate-limit behavior but updating them belongs to ENH-1135 (heartbeat/docs) per the decomposition — keep this issue scoped to schema/config/fragment surfaces.

## Scope Boundaries

Out of scope:
- Executor/runtime logic that *consumes* these fields (ENH-1133)
- Shared circuit breaker state file + coordination (ENH-1134)
- Heartbeat logging and user-facing docs updates in `docs/reference/CONFIGURATION.md`, `COMMANDS.md`, `CHANGELOG.md` (ENH-1135)
- Changes to `generate_schemas.py` — emits `LLEvent` JSON schemas only, unrelated to config/loop schemas

## Impact

- **Priority**: P2 — foundation for ENH-1133/1134/1135; no user-visible behavior change on its own, but unblocks the resilience epic
- **Effort**: Small — mirrors existing `ConfidenceGateConfig` pattern exactly; ~8 files, mostly additive
- **Risk**: Low — all new fields optional; `additionalProperties: false` enforces schema correctness; existing fragment consumers (autodev, auto-refine-and-implement, recursive-refine) gain defaults non-destructively
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `schema`, `fsm`, `rate-limit`, `foundation`, `ready`

## Acceptance Criteria

- `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` are optional `StateConfig` fields; round-trip via `to_dict`/`from_dict`
- Both fields appear in `fsm-loop-schema.json` and are validated
- `RateLimitsConfig` dataclass exists with defaults; accessible via `config.__init__`
- `config-schema.json` accepts `commands.rate_limits` block
- `BRConfig.to_dict()` serializes the new block
- `with_rate_limit_handling` fragment includes long-wait defaults; existing consumers still validate
- All affected tests pass; `test_fsm_fragments.py` asserts new fields

## Resolution

**Status**: Completed 2026-04-16

**Implementation summary** (all acceptance criteria met):

- `StateConfig` — added optional `rate_limit_max_wait_seconds: int | None` and `rate_limit_long_wait_ladder: list[int] | None` fields (`scripts/little_loops/fsm/schema.py`). `to_dict` omits when `None`; `from_dict` reads matching keys; docstring updated.
- `fsm-loop-schema.json` — added per-state properties (integer with `minimum: 1`, array of positive integers) describing fallback to global defaults.
- `fsm/validation.py` — added cross-field checks: `rate_limit_max_wait_seconds >= 1`, `rate_limit_long_wait_ladder` non-empty with all entries positive integers.
- `config/automation.py` — added `RateLimitsConfig` dataclass (defaults: `max_wait_seconds=21600`, `long_wait_ladder=[300,900,1800,3600]`, `circuit_breaker_enabled=True`, `circuit_breaker_path=".loops/tmp/rate-limit-circuit.json"`). Composed into `CommandsConfig` via `field(default_factory=...)` and `from_dict` delegation mirroring `ConfidenceGateConfig`.
- `config-schema.json` — inserted `commands.rate_limits` object (between `max_refine_count` and closing `additionalProperties: false`) with `additionalProperties: false` guarding the leaf.
- `config/core.py` — extended `BRConfig.to_dict()` to serialize `commands.rate_limits` alongside `confidence_gate`.
- `config/__init__.py` — re-exported `RateLimitsConfig`.
- `loops/lib/common.yaml` — extended `with_rate_limit_handling` fragment with `rate_limit_max_wait_seconds: 21600` and `rate_limit_long_wait_ladder: [300, 900, 1800, 3600]`; docstring now explains the two tiers and opt-out via `rate_limit_max_wait_seconds: 0`.
- Tests — added 5-test shape for new `StateConfig` fields (`test_fsm_schema.py`), added 4 validation tests (`test_fsm_validation.py`), added `TestRateLimitsConfig` + extended `TestCommandsConfig` (`test_config.py`), extended fragment assertions (`test_fsm_fragments.py`), added config-schema regression guard (`test_config_schema.py`).
- Docs — updated `skills/create-loop/reference.md` field reference and `skills/create-loop/loop-types.md` annotated YAML example.

**Verification**:
- `python -m pytest scripts/tests/` — 4876 passed, 5 skipped
- `ruff check scripts/` — all checks passed
- `python -m mypy scripts/little_loops/` — 0 new errors (pre-existing `wcwidth` stub note only)
- Built-in loops (`autodev`, `auto-refine-and-implement`, `recursive-refine`) still validate; fragment consumers gain the new defaults non-destructively.

Closes ENH-1132. Unblocks ENH-1133 (executor), ENH-1134 (circuit breaker), ENH-1135 (heartbeat/docs).

## Session Log
- `/ll:manage-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbc863d0-453e-4e8c-8a7d-fee07dbd9489.jsonl`
- `/ll:ready-issue` - 2026-04-17T04:08:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5adda0e0-3b22-46b8-a2f1-2f5f0121aad1.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16c833e3-4e3d-41af-aec2-156ee4006474.jsonl`
- `/ll:wire-issue` - 2026-04-17T04:02:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72f46a20-d0c1-4c76-a4db-d81ab93752ae.jsonl`
- `/ll:refine-issue` - 2026-04-17T03:55:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f33b31a-139a-47fa-81c7-8b4f76e5a7b8.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Status
- [x] Completed 2026-04-16
