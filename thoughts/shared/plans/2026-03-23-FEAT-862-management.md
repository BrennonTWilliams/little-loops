# FEAT-862: FSM Loop YAML Per-Loop Config Overrides — Implementation Plan

**Date**: 2026-03-23
**Issue**: P3-FEAT-862-fsm-loop-yaml-per-loop-config-overrides.md
**Action**: implement

## Summary

Add an optional top-level `config:` block to loop YAML files. This block embeds per-loop overrides for ll-config values (`handoff_threshold`, confidence gate thresholds, `max_continuations`). Overrides are applied at run/resume time; CLI flags always win.

## Precedence Order

1. CLI flags (`--handoff-threshold`) — highest
2. Loop YAML `config:` block
3. Global `ll-config.json`
4. Schema defaults

## Phases

### Phase 0: Prerequisite — Extend ConfidenceGateConfig
**File**: `scripts/little_loops/config/automation.py`

Add `readiness_threshold: int = 85` and `outcome_threshold: int = 70` fields to `ConfidenceGateConfig`. Update `from_dict` to read both.

### Phase 1: Add LoopConfigOverrides to schema.py
**File**: `scripts/little_loops/fsm/schema.py`

- New `@dataclass LoopConfigOverrides` after `LLMConfig` class
  - `handoff_threshold: int | None = None`
  - `readiness_threshold: int | None = None` (→ `commands.confidence_gate.readiness_threshold`)
  - `outcome_threshold: int | None = None` (→ `commands.confidence_gate.outcome_threshold`)
  - `max_continuations: int | None = None`
  - `to_dict()` — skip-if-None pattern
  - `from_dict()` — reads nested structure: `config.commands.confidence_gate.*`
- Add `config: LoopConfigOverrides | None = None` field to `FSMLoop`
- Update `FSMLoop.to_dict()` — serialize config block
- Update `FSMLoop.from_dict()` — parse config block

### Phase 2: Update fsm-loop-schema.json
**File**: `scripts/little_loops/fsm/fsm-loop-schema.json`

Add `config` property to top-level `properties` with `additionalProperties: false` and optional fields:
- `handoff_threshold`: integer, 1-100
- `commands`: object with `confidence_gate` subobject
- `automation`/`continuation`: object with `max_continuations`

Also add `"on_handoff"` and `"default_timeout"` which are missing from the schema (not part of this issue but needed for correctness).

### Phase 3: Update validation.py
**File**: `scripts/little_loops/fsm/validation.py`

Add `"config"` (and `"default_timeout"`, `"on_handoff"`) to `KNOWN_TOP_LEVEL_KEYS`.

### Phase 4: Apply overrides in run.py
**File**: `scripts/little_loops/cli/loop/run.py`

After line 65 (context injection), before line 67 (CLI `--handoff-threshold`):
```python
if fsm.config is not None:
    if fsm.config.handoff_threshold is not None:
        os.environ["LL_HANDOFF_THRESHOLD"] = str(fsm.config.handoff_threshold)
```

### Phase 5: Fix lifecycle.py (resume path)
**File**: `scripts/little_loops/cli/loop/lifecycle.py`

After line 190 (delay override), before `persistence = StatePersistence(...)`:
```python
if fsm.config is not None:
    if fsm.config.handoff_threshold is not None:
        os.environ["LL_HANDOFF_THRESHOLD"] = str(fsm.config.handoff_threshold)
if getattr(args, "handoff_threshold", None) is not None:
    if not (1 <= args.handoff_threshold <= 100):
        raise SystemExit("--handoff-threshold must be between 1 and 100")
    os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)
```

### Phase 6: Display in info.py
**File**: `scripts/little_loops/cli/loop/info.py`

After the `llm` block (after line 661), add conditional config override display:
```python
if fsm.config is not None:
    cfg = fsm.config
    cfg_parts = []
    if cfg.handoff_threshold is not None:
        cfg_parts.append(f"handoff_threshold={cfg.handoff_threshold}")
    if cfg.readiness_threshold is not None:
        cfg_parts.append(f"readiness_threshold={cfg.readiness_threshold}")
    if cfg.outcome_threshold is not None:
        cfg_parts.append(f"outcome_threshold={cfg.outcome_threshold}")
    if cfg.max_continuations is not None:
        cfg_parts.append(f"max_continuations={cfg.max_continuations}")
    if cfg_parts:
        config_parts.append(f"config: {', '.join(cfg_parts)}")
```

## Success Criteria

- [x] YAML `config` block parses correctly (all fields optional)
- [x] `LL_HANDOFF_THRESHOLD` set from YAML when no CLI flag
- [x] CLI `--handoff-threshold` overrides YAML value
- [x] `ll-loop resume` applies YAML config block + fixes `--handoff-threshold` handling
- [x] Schema validation does not warn for `config:` blocks
- [x] `ll-loop info` displays config overrides
- [x] All tests pass

## Test Plan

**test_fsm_schema.py** — Add `TestLoopConfigOverrides` class:
- `test_defaults` — all fields None
- `test_to_dict_empty_for_defaults` — returns `{}`
- `test_to_dict_with_handoff_threshold`
- `test_from_dict_handoff_threshold`
- `test_from_dict_confidence_gate_fields`
- `test_from_dict_max_continuations`
- `test_roundtrip` — from_dict → to_dict fidelity

**test_cli_loop_lifecycle.py** — Add `TestCmdRunYAMLConfigOverrides` class:
- `test_yaml_config_handoff_threshold_sets_env_var`
- `test_cli_handoff_threshold_wins_over_yaml`
- `test_no_yaml_config_no_env_var` (baseline)
- `test_yaml_config_out_of_range_rejected` (validation)
