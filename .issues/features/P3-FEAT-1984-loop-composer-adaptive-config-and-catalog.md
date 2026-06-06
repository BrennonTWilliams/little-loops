---
id: FEAT-1984
title: "Adaptive loop-composer \u2014 Config Schema, Orchestration Parser, and Skill\
  \ Catalog"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
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

- `config-schema.json` has `"additionalProperties": false` on the `orchestration` object; adding `orchestration.composer.*` keys to `.ll/ll-config.json` causes schema validation failures.
- `OrchestrationConfig` has no `composer` field; config values under `orchestration.composer` are silently discarded.
- `skills/create-loop/loop-types.md` does not list the adaptive composer variant.
- `skills/create-loop/templates.md` marks the Composer entry as "Forthcoming".

## Expected Behavior

- `config-schema.json` validates `orchestration.composer.adaptive.{enabled,max_replans,reassess_min_confidence}` keys correctly.
- `OrchestrationConfig.composer` is a typed `ComposerConfig` dataclass populated from config; missing keys use safe defaults (`enabled: false`, `max_replans: 2`, `reassess_min_confidence: 0.6`).
- `skills/create-loop/loop-types.md` lists the adaptive composer variant with when-to-use guidance.
- `skills/create-loop/templates.md` shows the Composer entry as active with a reference to `loop-composer-adaptive.yaml`.
- Existing config loading tests continue to pass.

## Acceptance Criteria

1. `config-schema.json` declares `orchestration.composer` as a property within the `orchestration` object (which currently has `"additionalProperties": false`) with sub-keys:
   - `adaptive.enabled` (boolean, default `false`)
   - `adaptive.max_replans` (integer, default `2`)
   - `adaptive.reassess_min_confidence` (number, default `0.6`)
2. `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.from_dict()` parses `composer.adaptive.*` fields without error; existing config files without the new keys continue to load cleanly
3. `skills/create-loop/loop-types.md` lists the Orch Composer adaptive variant as an active option
4. `skills/create-loop/templates.md` updates the Composer entry from "Forthcoming" to active with adaptive guidance
5. Existing tests that validate config loading continue to pass

## Proposed Solution

### Config schema extension (`config-schema.json`)

Add `composer` property inside the `orchestration` object's `properties`:
```json
"composer": {
  "type": "object",
  "properties": {
    "adaptive": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": false},
        "max_replans": {"type": "integer", "default": 2},
        "reassess_min_confidence": {"type": "number", "default": 0.6}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

Note: `orchestration` currently has `"additionalProperties": false` — the `composer` key must be declared as a property before the schema will accept it.

### Orchestration config parser (`scripts/little_loops/config/orchestration.py`)

Update `OrchestrationConfig.from_dict()` to parse `composer.adaptive.*` fields. Add a `ComposerAdaptiveConfig` dataclass:
```python
@dataclass
class ComposerAdaptiveConfig:
    enabled: bool = False
    max_replans: int = 2
    reassess_min_confidence: float = 0.6

@dataclass
class ComposerConfig:
    adaptive: ComposerAdaptiveConfig = field(default_factory=ComposerAdaptiveConfig)
```

Integrate into `OrchestrationConfig` with a `composer: ComposerConfig` field. Parse via `ComposerConfig(adaptive=ComposerAdaptiveConfig(**raw.get("composer", {}).get("adaptive", {})))` with appropriate defaults.

### Skill catalog updates

- `skills/create-loop/loop-types.md` — add "Orch Composer (adaptive)" row: when to use, key states, evaluator requirements
- `skills/create-loop/templates.md` — update "Composer" section from "Forthcoming" to active; add brief note pointing to `loop-composer-adaptive.yaml` and when to prefer the adaptive variant over the static one

## Integration Map

### Files to Modify
- `config-schema.json` — add `orchestration.composer` property block
- `scripts/little_loops/config/orchestration.py` — add `ComposerAdaptiveConfig` and `ComposerConfig` dataclasses, update `OrchestrationConfig.from_dict()`
- `skills/create-loop/loop-types.md` — add adaptive composer row
- `skills/create-loop/templates.md` — activate composer entry

### Dependent Files (Callers/Importers)
- `loops/loop-composer-adaptive.yaml` (FEAT-1983) — the loop YAML that reads `orchestration.composer.adaptive.*` at runtime
- Any script instantiating `OrchestrationConfig` — gains the new `composer` field (additive, no breaking change)

### Similar Patterns
- `scripts/little_loops/config/orchestration.py` — existing `WorktreeConfig` and `OrchestrationConfig` dataclasses show the pattern to follow for `ComposerConfig`

### Tests
- `scripts/tests/` — existing config loading tests must continue to pass; add a test asserting `OrchestrationConfig.from_dict({})` produces safe defaults for `composer.adaptive.*`

### Documentation
- `skills/create-loop/loop-types.md` and `skills/create-loop/templates.md` updated as part of this issue

### Configuration
- `config-schema.json` extended; `.ll/ll-config.json` files without the new keys load cleanly (all new fields have defaults)

## Implementation Steps

1. Add `composer` property block to the `orchestration` object in `config-schema.json`
2. Add `ComposerAdaptiveConfig` and `ComposerConfig` dataclasses in `scripts/little_loops/config/orchestration.py`
3. Wire `composer: ComposerConfig` into `OrchestrationConfig` and update `from_dict()` to parse it with safe defaults
4. Add "Orch Composer (adaptive)" row to `skills/create-loop/loop-types.md` (when to use, key states, evaluator requirements)
5. Update the Composer entry in `skills/create-loop/templates.md` from "Forthcoming" to active with `loop-composer-adaptive.yaml` reference
6. Run existing config tests to verify no regressions

## Impact

- **Priority**: P3 — Unblocks usage of the adaptive loop-composer but is not a regression fix; the adaptive variant is a new capability.
- **Effort**: Small — ~10-line JSON schema addition, ~15-line dataclass addition, two targeted doc edits.
- **Risk**: Low — purely additive changes; no existing behavior changes. Config files without the new keys continue to load cleanly.
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-06-06T22:19:30 - `a614b3c8-9173-47a3-a2ba-a5bcd371462b.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `4da8ccb1-c9d9-425d-8832-3a5570cd748e.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-06
