---
discovered_date: 2026-03-25
discovered_by: audit-architecture
focus_area: integration
confidence_score: 98
outcome_confidence: 79
---

# ENH-889: `ConfidenceGateConfig.threshold` is a legacy field inconsistent with schema and `to_dict()`

## Summary

`ConfidenceGateConfig` has a `threshold` dataclass field that does not exist in the schema.
The schema defines `readiness_threshold` and `outcome_threshold` (added in ENH-562). The
`from_dict()` reads all three, but `BRConfig.to_dict()` only serializes the old `threshold`
key, not the two schema-aligned fields. `docs/reference/CONFIGURATION.md` compounds this by
showing `"threshold": 85` alongside the two new fields in its example, suggesting it is
a valid config key.

## Motivation

This enhancement would:
- Remove config inconsistency between `ConfidenceGateConfig` dataclass fields, `config-schema.json` definitions, and `BRConfig.to_dict()` serialization output
- Prevent user confusion about which config keys are valid (`threshold` vs `readiness_threshold`)
- Ensure `{{config.commands.confidence_gate.readiness_threshold}}` and `{{config.commands.confidence_gate.outcome_threshold}}` template variables resolve correctly instead of returning `None`
- Eliminate the documentation error that falsely shows `threshold` as a supported config key alongside the two schema-aligned fields

## Current Behavior

`ConfidenceGateConfig` has a `threshold` field not defined in `config-schema.json`. `BRConfig.to_dict()` serializes only the legacy `threshold` key, dropping `readiness_threshold` and `outcome_threshold`. `docs/reference/CONFIGURATION.md` shows `threshold` as a valid config key alongside the two schema-aligned fields. See `## Finding` for full technical detail.

## Expected Behavior

`ConfidenceGateConfig` should have only schema-aligned fields (`readiness_threshold`, `outcome_threshold`). `BRConfig.to_dict()` should export `readiness_threshold` and `outcome_threshold`, not `threshold`. `from_dict()` should accept legacy `threshold` as a silent fallback for backwards compatibility. Documentation should not show `threshold` as a config key.

## Location

- **File**: `scripts/little_loops/config/automation.py`
- **Lines**: 94–110 (`ConfidenceGateConfig`)
- **File**: `scripts/little_loops/config/core.py`
- **Lines**: 392–399 (`BRConfig.to_dict()` commands section)

## Finding

### Current State

```python
# automation.py:94-110
@dataclass
class ConfidenceGateConfig:
    enabled: bool = False
    threshold: int = 85           # ← not in schema; legacy field
    readiness_threshold: int = 85
    outcome_threshold: int = 70

    @classmethod
    def from_dict(cls, data):
        return cls(
            enabled=data.get("enabled", False),
            threshold=data.get("threshold", 85),                  # reads undocumented key
            readiness_threshold=data.get("readiness_threshold", 85),
            outcome_threshold=data.get("outcome_threshold", 70),
        )
```

```python
# core.py:392-399 — to_dict() exports undocumented legacy key only
"confidence_gate": {
    "enabled": self._commands.confidence_gate.enabled,
    "threshold": self._commands.confidence_gate.threshold,   # ← only exports legacy key
    # readiness_threshold: MISSING
    # outcome_threshold: MISSING
},
```

The schema (`config-schema.json:300–325`) defines only `enabled`, `readiness_threshold`, and
`outcome_threshold`. There is no `threshold` in the schema.

`docs/reference/CONFIGURATION.md:73-76` example:
```json
"confidence_gate": {
  "enabled": false,
  "threshold": 85,            ← undocumented, not in schema
  "readiness_threshold": 85,
  "outcome_threshold": 70
}
```

### Impact

- `{{config.commands.confidence_gate.readiness_threshold}}` and
  `{{config.commands.confidence_gate.outcome_threshold}}` resolve to `None` via
  `resolve_variable()`.
- Users setting `readiness_threshold` in config are not sure if `threshold` is also needed.
- The `confidence-check` skill's handling of these thresholds may rely on the wrong value.

## Proposed Solution

1. **Remove `threshold` from the dataclass** or keep it as a backwards-compat alias but stop
   using it as the primary field:

```python
@dataclass
class ConfidenceGateConfig:
    enabled: bool = False
    readiness_threshold: int = 85
    outcome_threshold: int = 70

    @classmethod
    def from_dict(cls, data):
        # Accept legacy "threshold" as fallback for both thresholds
        legacy = data.get("threshold", 85)
        return cls(
            enabled=data.get("enabled", False),
            readiness_threshold=data.get("readiness_threshold", legacy),
            outcome_threshold=data.get("outcome_threshold", 70),
        )
```

2. **Fix `to_dict()`** to export schema-aligned keys:

```python
"confidence_gate": {
    "enabled": self._commands.confidence_gate.enabled,
    "readiness_threshold": self._commands.confidence_gate.readiness_threshold,
    "outcome_threshold": self._commands.confidence_gate.outcome_threshold,
},
```

3. **Remove `"threshold": 85`** from `docs/reference/CONFIGURATION.md` example.

4. Search for any internal Python code using `confidence_gate.threshold` and migrate to
   `readiness_threshold`.

## Scope Boundaries

- **In scope**: Remove `threshold` from `ConfidenceGateConfig` dataclass, update `from_dict()` with legacy fallback, fix `BRConfig.to_dict()` to export schema-aligned keys, update `docs/reference/CONFIGURATION.md`, migrate `skills/manage-issue/SKILL.md:173` from `threshold` → `readiness_threshold`, update `TestConfidenceGateConfig` / `TestCommandsConfig` / `TestBRConfig.test_to_dict()` tests
- **Out of scope**: Changes to `config-schema.json` (already correct), refactoring other config dataclasses, changing the threshold default values, changes to FSM schema or CLI argument parsers (already schema-aligned)

## Integration Map

### Files to Modify
- `scripts/little_loops/config/automation.py` — Remove `threshold` field, update `from_dict()` with legacy fallback
- `scripts/little_loops/config/core.py` — Fix `BRConfig.to_dict()` confidence_gate section (line 394-398)
- `docs/reference/CONFIGURATION.md` — Remove `threshold` from example config block (line 318)
- `skills/manage-issue/SKILL.md:173` — Migrate `config.commands.confidence_gate.threshold` → `readiness_threshold`

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/schema.py` — `LoopConfigOverrides` nests `readiness_threshold`/`outcome_threshold` under `commands.confidence_gate` in its own `to_dict()`/`from_dict()` (no changes needed; already schema-aligned)
- `scripts/little_loops/cli/issues/next_action.py` — reads `readiness_threshold` and `outcome_threshold` from args; uses them for gate checks (no changes needed; references the dataclass fields directly, not via `to_dict()`)
- `scripts/little_loops/cli/issues/__init__.py` — registers `--outcome_threshold` CLI argument (no changes needed)
- `scripts/little_loops/cli/loop/info.py` — displays `readiness_threshold` and `outcome_threshold` from FSM loop config (no changes needed)
- `skills/manage-issue/SKILL.md:173` — gate pseudocode reads `config.commands.confidence_gate.threshold` via `resolve_variable()`; currently resolves correctly because `to_dict()` emits `threshold`; **must be migrated to `readiness_threshold` when `to_dict()` is fixed**

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Legacy fallback pattern**: `scripts/little_loops/config/automation.py:69` — `ParallelAutomationConfig.from_dict()` uses `data.get("timeout_per_issue", data.get("timeout_seconds", 3600))` — nested `data.get()` with primary key first, legacy key as the default (no helper function needed)
- **Nested dataclass delegation**: `scripts/little_loops/config/automation.py:125-132` — `CommandsConfig.from_dict()` delegates to `ConfidenceGateConfig.from_dict(data.get("confidence_gate", {}))` (no changes needed here)
- **Inline field expansion in `to_dict()`**: `scripts/little_loops/config/core.py:426-439` — `dependency_mapping` section shows how a multi-field nested section is expanded field-by-field inline (the pattern to follow for the fixed `confidence_gate` section)

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_config.py:328-344` — `TestConfidenceGateConfig` — currently only tests `enabled` and `threshold`; needs new tests for `readiness_threshold`, `outcome_threshold`, and the legacy fallback behavior
- `scripts/tests/test_config.py:350-377` — `TestCommandsConfig` — assertions at lines 365 and 376 check `config.confidence_gate.threshold == 90/85`; must be updated to check `readiness_threshold` and `outcome_threshold`
- `scripts/tests/test_config.py:573-587` — `TestBRConfig.test_to_dict()` — add assertion that `result["commands"]["confidence_gate"]` contains `readiness_threshold` and `outcome_threshold` (not `threshold`)
- **Test pattern to follow**: `scripts/tests/test_config.py:310-325` — `TestParallelAutomationConfig` legacy-key tests: (1) primary key only, (2) fallback key only, (3) both present with primary winning

### Documentation
- `docs/reference/CONFIGURATION.md` — confidence_gate example block

### Configuration
- `config-schema.json` — N/A (schema already correct, defines `readiness_threshold` and `outcome_threshold`)

## Implementation Steps

1. **`automation.py:93-110`** — Remove `threshold` field from `ConfidenceGateConfig` dataclass; update `from_dict()` to use the nested-`data.get()` pattern from `automation.py:69`: `readiness_threshold=data.get("readiness_threshold", data.get("threshold", 85))`
2. **`core.py:394-398`** — Fix `BRConfig.to_dict()` confidence_gate section: replace `"threshold": ...` with `"readiness_threshold": ...` and `"outcome_threshold": ...` (follow the inline expansion pattern at `core.py:426-439`)
3. **`skills/manage-issue/SKILL.md:173`** — Migrate `config.commands.confidence_gate.threshold` → `config.commands.confidence_gate.readiness_threshold`
4. **`docs/reference/CONFIGURATION.md:318`** — Remove the `threshold` row from the confidence_gate config table/example
5. **`scripts/tests/test_config.py:328-344`** — Update `TestConfidenceGateConfig` to remove `threshold` assertions; add tests for `readiness_threshold`, `outcome_threshold`, and legacy-`threshold` fallback (follow 3-test pattern at `test_config.py:310-325`)
6. **`scripts/tests/test_config.py:350-377`** — Update `TestCommandsConfig` assertions at lines 365 and 376 to check `readiness_threshold`/`outcome_threshold` instead of `threshold`
7. **`scripts/tests/test_config.py:573-587`** — Add assertions to `TestBRConfig.test_to_dict()` that `confidence_gate` in `to_dict()` output contains `readiness_threshold` and `outcome_threshold`, not `threshold`
8. Run `python -m pytest scripts/tests/test_config.py -v` to verify no regressions

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low — `threshold` is read but never the source of a blocking gate condition
  (the gate uses `readiness_threshold` / `outcome_threshold` directly in the skill logic)
- **Breaking Change**: Minor for any external user who relied on `threshold` in config
  (acceptable since it was never in the schema)

## Labels

`enhancement`, `config`, `confidence-gate`, `auto-generated`

## Session Log
- `/ll:refine-issue` - 2026-03-25T23:42:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:format-issue` - 2026-03-25T23:37:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de7944a-158f-4f7f-be38-172cfa9404eb.jsonl`
- `/ll:confidence-check` - 2026-03-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-25 | Priority: P4
