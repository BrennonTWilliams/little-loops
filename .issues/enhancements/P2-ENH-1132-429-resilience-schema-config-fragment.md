---
id: ENH-1132
type: ENH
priority: P2
status: open
discovered_date: 2026-04-16
parent: ENH-1131
related: [ENH-1131, ENH-1133, ENH-1134, ENH-1135, BUG-1107, BUG-1108, BUG-1109]
---

# ENH-1132: 429 Resilience — Schema, Config & Fragment Foundation

## Summary

Add the schema and configuration foundation for multi-hour 429 resilience: new `StateConfig` fields for two-tier retry, a `RateLimitsConfig` dataclass under `commands`, updates to `config-schema.json`, and an expanded `with_rate_limit_handling` fragment. This is the prerequisite for ENH-1133 (executor), ENH-1134 (circuit breaker), and ENH-1135 (heartbeat/docs).

## Parent Issue

Decomposed from ENH-1131: Multi-Hour 429 Resilience with Shared Circuit Breaker and Wall-Clock Budget

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

Compose into `CommandsConfig` as `rate_limits: RateLimitsConfig`.

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

## Acceptance Criteria

- `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` are optional `StateConfig` fields; round-trip via `to_dict`/`from_dict`
- Both fields appear in `fsm-loop-schema.json` and are validated
- `RateLimitsConfig` dataclass exists with defaults; accessible via `config.__init__`
- `config-schema.json` accepts `commands.rate_limits` block
- `BRConfig.to_dict()` serializes the new block
- `with_rate_limit_handling` fragment includes long-wait defaults; existing consumers still validate
- All affected tests pass; `test_fsm_fragments.py` asserts new fields

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`

---

## Status
- [ ] Open
