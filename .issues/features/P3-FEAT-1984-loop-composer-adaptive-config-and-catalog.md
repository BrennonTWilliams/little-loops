---
id: FEAT-1984
title: "Adaptive loop-composer \u2014 Config Schema, Orchestration Parser, and Skill\
  \ Catalog"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-06T23:17:19Z'
discovered_date: 2026-06-06
discovered_by: issue-size-review
blocked_by:
- FEAT-1983
relates_to:
- FEAT-1983
- FEAT-1809
labels:
- loop-composer
- orchestration
- adaptive
- config
size: Small
confidence_score: 100
outcome_confidence: 87
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 22
---

# FEAT-1984: Adaptive loop-composer — Config Schema, Orchestration Parser, and Skill Catalog

## Summary

Wire the adaptive `loop-composer` configuration into the project config system and update the skill catalog. This covers: extending `config-schema.json` with the `orchestration.composer` sub-object, updating `OrchestrationConfig.from_dict()` in `orchestration.py` to parse `composer.adaptive.*` fields, and updating `skills/create-loop` templates and type listings to reflect the now-active adaptive variant.

## Parent Issue

Decomposed from FEAT-1809: Adaptive `loop-composer` — Re-plan-on-Failure Variant

## Prerequisite

FEAT-1983 must ship first — this child wires the config keys that the loop YAML reads.

## Motivation

The adaptive loop-composer YAML (shipped in FEAT-1983) reads `orchestration.composer.adaptive.*` keys at runtime, but those keys are not declared in `config-schema.json`. Any project that sets them will fail schema validation. `OrchestrationConfig` currently has no `composer` field, so even without validation the values are silently discarded. Additionally, the adaptive variant is not listed in the `skills/create-loop` catalog, making it undiscoverable. This issue completes the integration: schema validation, typed config access, and catalog visibility.

## Use Case

A developer wants to tune the adaptive loop-composer for their project. They add to `.ll/ll-config.json`:

```json
{
  "orchestration": {
    "composer": {
      "adaptive": {
        "enabled": true,
        "max_replans": 3,
        "reassess_min_confidence": 0.7
      }
    }
  }
}
```

The project config loads without schema validation errors, `OrchestrationConfig.composer.adaptive.enabled` is `True`, and the adaptive loop YAML reads the value correctly. When the developer runs `/ll:create-loop`, the adaptive composer type appears in the listing with guidance on when to prefer it over the static variant.

## Current Behavior

- `config-schema.json` has `orchestration.composer` with `max_plan_nodes` (integer, default 8) and `auto` (boolean, default false), but no `adaptive` sub-object; adding `orchestration.composer.adaptive.*` keys to `.ll/ll-config.json` fails schema validation because `orchestration.composer` has `"additionalProperties": false`.
- `OrchestrationConfig` in `scripts/little_loops/config/orchestration.py` has only a `host_cli: str | None` field; the entire `composer` sub-dict (including the existing `max_plan_nodes` and `auto` keys) is silently discarded.
- `skills/create-loop/loop-types.md` — the `### Orch Supervisor` section describes `loop-composer-adaptive` behavior but does not document any `orchestration.composer.adaptive.*` config knobs.
- `skills/create-loop/SKILL.md` Step 1 type mapping comments still label both Composer and Adaptive Composer as "Forthcoming — see EPIC-1811".
- `skills/create-loop/templates.md` already lists the Adaptive Composer as an active option (not "Forthcoming"); no change needed there.

## Expected Behavior

- `config-schema.json` validates `orchestration.composer.adaptive.{enabled,max_replans,reassess_min_confidence}` keys correctly, as a new `adaptive` sub-object within the existing `orchestration.composer.properties`.
- `OrchestrationConfig.composer` is a typed `ComposerConfig` dataclass populated from config; missing keys use safe defaults (`enabled: false`, `max_replans: 2`, `reassess_min_confidence: 0.6`).
- `skills/create-loop/loop-types.md` `### Orch Supervisor` section documents the `orchestration.composer.adaptive.*` config knobs alongside the existing behavior description.
- `skills/create-loop/SKILL.md` Step 1 type mapping no longer shows "Forthcoming" for the Composer / Adaptive Composer entries.
- Existing config loading tests continue to pass.

## Acceptance Criteria

1. `config-schema.json` adds an `adaptive` sub-object inside the existing `orchestration.composer.properties` block (which already contains `max_plan_nodes` and `auto`); the `adaptive` block has `"additionalProperties": false` and declares:
   - `adaptive.enabled` (boolean, default `false`)
   - `adaptive.max_replans` (integer, default `2`)
   - `adaptive.reassess_min_confidence` (number, default `0.6`)
2. `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.from_dict()` parses `composer.adaptive.*` fields without error; existing config files without the new keys continue to load cleanly; `ComposerConfig` and `ComposerAdaptiveConfig` are exported from `scripts/little_loops/config/__init__.py`
3. `skills/create-loop/loop-types.md` `### Orch Supervisor` section documents the `orchestration.composer.adaptive.*` config knobs (enabled, max_replans, reassess_min_confidence) with their defaults
4. `skills/create-loop/SKILL.md` Step 1 type mapping removes "Forthcoming — see EPIC-1811" from the Composer and Adaptive Composer entries
5. Existing tests that validate config loading continue to pass; a new `TestOrchestrationConfig` test in `scripts/tests/test_config.py` asserts `OrchestrationConfig.from_dict({})` produces safe defaults for `composer.adaptive.*`

## Proposed Solution

### Config schema extension (`config-schema.json`)

The `orchestration.composer` sub-object already exists with `max_plan_nodes` and `auto`. Add `adaptive` as a new property inside `orchestration.composer.properties` (do NOT rewrite the whole composer block — append `adaptive` alongside the existing properties):

```json
"adaptive": {
  "type": "object",
  "description": "Tuning knobs for the adaptive loop-composer-adaptive built-in loop.",
  "properties": {
    "enabled": {"type": "boolean", "default": false, "description": "When true, prefer the adaptive composer variant."},
    "max_replans": {"type": "integer", "default": 2, "description": "Maximum re-plan attempts before aborting."},
    "reassess_min_confidence": {"type": "number", "default": 0.6, "description": "Confidence threshold below which the reassess gate triggers a re-plan."}
  },
  "additionalProperties": false
}
```

Add this block inside the existing `"orchestration" → "properties" → "composer" → "properties"` object. The outer `orchestration.composer` block already has `"additionalProperties": false` — adding `adaptive` to its `properties` is sufficient.

### Orchestration config parser (`scripts/little_loops/config/orchestration.py`)

Follow the `CommandsConfig`/`ConfidenceGateConfig` pattern from `scripts/little_loops/config/automation.py`: a leaf sub-dataclass with its own `from_dict()` composed into a parent via `field(default_factory=...)`.

Current `orchestration.py` is 29 lines with a single-field `OrchestrationConfig`. Extend it to:

```python
@dataclass
class ComposerAdaptiveConfig:
    enabled: bool = False
    max_replans: int = 2
    reassess_min_confidence: float = 0.6

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComposerAdaptiveConfig:
        return cls(
            enabled=data.get("enabled", False),
            max_replans=data.get("max_replans", 2),
            reassess_min_confidence=data.get("reassess_min_confidence", 0.6),
        )

@dataclass
class ComposerConfig:
    adaptive: ComposerAdaptiveConfig = field(default_factory=ComposerAdaptiveConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComposerConfig:
        return cls(
            adaptive=ComposerAdaptiveConfig.from_dict(data.get("adaptive", {})),
        )

@dataclass
class OrchestrationConfig:
    host_cli: str | None = None
    composer: ComposerConfig = field(default_factory=ComposerConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationConfig:
        return cls(
            host_cli=data.get("host_cli"),
            composer=ComposerConfig.from_dict(data.get("composer", {})),
        )
```

Export `ComposerConfig` and `ComposerAdaptiveConfig` from `scripts/little_loops/config/__init__.py` alongside the existing `OrchestrationConfig` export.

> **Note**: `loop-composer-adaptive.yaml` reads its tunables from `${context.max_replans}` etc. (context-block defaults), not directly from `orchestration.composer.adaptive.*`. The Python config is the authoritative typed representation for tooling/programmatic use. A future issue can wire the runner to inject config values into context defaults on startup; that is out of scope here.

### Skill catalog updates

- `skills/create-loop/loop-types.md` — in the `### Orch Supervisor` subsection, append a "Config knobs (`ll-config.json`)" paragraph listing `orchestration.composer.adaptive.{enabled,max_replans,reassess_min_confidence}` with defaults; follow the format of the "Key context knobs" block already present in `### Orch Composer`
- `skills/create-loop/SKILL.md` — in the Step 1 type mapping table, remove "Forthcoming — see EPIC-1811" from both "Orch: Composer (goal → DAG)" and "Orch: Supervisor (adaptive re-plan)" and replace with active loop names (`loop-composer` / `loop-composer-adaptive`)
- `skills/create-loop/templates.md` — already active; no "Forthcoming" text present; no changes needed

## Integration Map

### Files to Modify
- `config-schema.json` — add `adaptive` sub-object inside existing `orchestration.composer.properties` block (after the `auto` property)
- `scripts/little_loops/config/orchestration.py` — add `ComposerAdaptiveConfig` and `ComposerConfig` dataclasses, update `OrchestrationConfig` and its `from_dict()`
- `scripts/little_loops/config/__init__.py` — export `ComposerConfig` and `ComposerAdaptiveConfig`
- `skills/create-loop/loop-types.md` — append config-knobs paragraph to `### Orch Supervisor` subsection
- `skills/create-loop/SKILL.md` — update Step 1 type mapping to remove "Forthcoming" from Composer/Adaptive Composer entries

### Dependent Files (Callers/Importers)
- Any script importing `OrchestrationConfig` from `scripts/little_loops/config/` — gains the new `composer` field (additive, no breaking change)
- `scripts/little_loops/config/core.py:BRConfig._parse_config()` — already wires `OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))` at line ~218; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py` — calls `apply_host_cli_from_config()` which accesses `config.orchestration.host_cli`; no change needed (additive change only touches `host_cli`), but confirmed runtime consumer of the `OrchestrationConfig` object [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/config/automation.py:CommandsConfig` — the canonical nested-dataclass pattern in this codebase; `ConfidenceGateConfig`, `RateLimitsConfig`, and `RecursiveRefineConfig` each have their own `from_dict()` and are composed via `field(default_factory=...)` — follow this exactly for `ComposerConfig`

### Tests
- `scripts/tests/test_config.py:TestOrchestrationConfig` — existing class with tests for `from_dict({})` defaults and `host_cli`; add a `test_from_dict_defaults_composer_adaptive()` test following `TestCommandsConfig.test_from_dict_with_defaults` pattern (line ~513) — call `OrchestrationConfig.from_dict({})` and assert `config.composer.adaptive.enabled is False`, `config.composer.adaptive.max_replans == 2`, `config.composer.adaptive.reassess_min_confidence == 0.6`
- `scripts/tests/test_config.py:TestBRConfigOrchestration` — existing integration tests; add a parallel `test_orchestration_composer_adaptive_from_file()` test
- `scripts/tests/test_config_schema.py` — existing schema validation tests; verify the schema accepts `{"orchestration": {"composer": {"adaptive": {"enabled": true, "max_replans": 3}}}}`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — top-level import block (lines 11–54) imports from `little_loops.config` and is the established convention for validating public exports; add `ComposerConfig` and `ComposerAdaptiveConfig` to this import block after they are exported from `__init__.py` — if the exports are missing or misnamed, the entire test module will fail to import [Agent 3 finding]

### Documentation
- `skills/create-loop/loop-types.md` — `### Orch Supervisor` subsection gets a config-knobs block
- `skills/create-loop/SKILL.md` — Step 1 type mapping updated (removes "Forthcoming" text)
- `skills/create-loop/templates.md` — already active; no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### orchestration` section (line 971) currently documents only `host_cli`; the new `orchestration.composer.adaptive.*` keys (`enabled`, `max_replans`, `reassess_min_confidence`) are not documented here; add a `composer.adaptive` sub-table or paragraph listing the three new keys with types and defaults [Agent 2 finding]
- `skills/create-loop/reference.md` — Orchestration Loops section (near line 1162) documents `ll-loop run loop-composer` invocation but has no `orchestration.composer.*` config-knobs reference; add a "Config knobs (`ll-config.json`)" block matching the format used in `loop-types.md` [Agent 2 finding]

### Configuration
- `config-schema.json` extended; `.ll/ll-config.json` files without the new keys load cleanly (all new fields have defaults)

## Implementation Steps

1. In `config-schema.json`, locate `orchestration → properties → composer → properties` (currently contains `max_plan_nodes` and `auto`) and add the `adaptive` sub-object with `enabled`, `max_replans`, `reassess_min_confidence` and `"additionalProperties": false`
2. In `scripts/little_loops/config/orchestration.py`, add `ComposerAdaptiveConfig` and `ComposerConfig` dataclasses (each with `from_dict()`) following the `ConfidenceGateConfig` pattern in `automation.py`
3. Update `OrchestrationConfig` to add `composer: ComposerConfig = field(default_factory=ComposerConfig)` and update `from_dict()` to parse `composer=ComposerConfig.from_dict(data.get("composer", {}))`
4. In `scripts/little_loops/config/__init__.py`, add `ComposerConfig` and `ComposerAdaptiveConfig` to the exports
5. In `skills/create-loop/loop-types.md`, append a "Config knobs (`ll-config.json`)" paragraph to the `### Orch Supervisor` subsection with the three `orchestration.composer.adaptive.*` keys and their defaults
6. In `skills/create-loop/SKILL.md`, find the Step 1 type mapping entries for "Orch: Composer (goal → DAG)" and "Orch: Supervisor (adaptive re-plan)" and remove the "Forthcoming — see EPIC-1811" suffix; replace with the active loop names
7. Add tests to `scripts/tests/test_config.py` — one unit test asserting `OrchestrationConfig.from_dict({}).composer.adaptive` defaults, one with explicit values set, and optionally one schema-validation test in `test_config_schema.py`; also add `ComposerConfig` and `ComposerAdaptiveConfig` to the top-level import block (lines 11–54) to validate the `__init__.py` exports
8. Run `python -m pytest scripts/tests/test_config.py scripts/tests/test_config_schema.py -v` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/reference/CONFIGURATION.md` `### orchestration` section — add a `composer.adaptive` sub-section or table documenting `enabled` (boolean, default `false`), `max_replans` (integer, default `2`), and `reassess_min_confidence` (number, default `0.6`)
10. Update `skills/create-loop/reference.md` Orchestration Loops section — add a "Config knobs (`ll-config.json`)" block for `loop-composer-adaptive` listing the three `orchestration.composer.adaptive.*` keys, following the format used in `loop-types.md`

## Impact

- **Priority**: P3 — Unblocks usage of the adaptive loop-composer but is not a regression fix; the adaptive variant is a new capability.
- **Effort**: Small — ~10-line JSON schema addition, ~15-line dataclass addition, two targeted doc edits.
- **Risk**: Low — purely additive changes; no existing behavior changes. Config files without the new keys continue to load cleanly.
- **Breaking Change**: No

## Session Log
- `/ll:ready-issue` - 2026-06-06T23:14:01 - `9ede9f4a-af0f-45d9-9eeb-7c5dfcd2756e.jsonl`
- `/ll:wire-issue` - 2026-06-06T23:10:44 - `761b33a9-e683-4cd4-bb8c-476e36fa4ded.jsonl`
- `/ll:refine-issue` - 2026-06-06T23:04:58 - `43bd0b4e-cd16-4288-b473-ac350f44aee1.jsonl`
- `/ll:format-issue` - 2026-06-06T22:19:30 - `a614b3c8-9173-47a3-a2ba-a5bcd371462b.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `4da8ccb1-c9d9-425d-8832-3a5570cd748e.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-06
