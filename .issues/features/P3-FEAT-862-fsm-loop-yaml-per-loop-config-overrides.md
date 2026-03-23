---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# FEAT-862: FSM loop YAML per-loop config overrides

## Summary

Add an optional `config` block to the loop YAML definition that allows a loop to embed per-loop overrides for ll-config values (e.g., `handoff_threshold`, `readiness_threshold`, `outcome_threshold`). These overrides apply for the duration of that loop's execution and take precedence over global ll-config settings and CLI flags.

## Context

**Direct mode**: User description: "Enable FSM loops yaml to include overrides for values like --handoff-threshold, readiness and outcome confidence thresholds, and other related values from ll-config (schema is config-schema.json)"

Currently the only way to override `LL_HANDOFF_THRESHOLD` for a loop run is via `ll-loop run --handoff-threshold N` (added in ENH-768). There is no mechanism to bake the override into the loop YAML itself, so operators must re-specify it every time or wrap `ll-loop run` in a script. For confidence gate thresholds (`readiness_threshold`, `outcome_threshold`), there are no per-run override flags at all — only global ll-config settings.

## Use Case

A loop author wants to ship a loop YAML that always uses a lower handoff threshold (e.g., 60 instead of 80) and relaxed confidence thresholds because it is designed for exploratory, multi-step tasks. Rather than documenting "run with `--handoff-threshold 60`", they embed it directly:

```yaml
name: exploratory-refactor
initial: analyze
on_handoff: spawn
config:
  handoff_threshold: 60
  commands:
    confidence_gate:
      readiness_threshold: 70
      outcome_threshold: 55

states:
  analyze:
    ...
```

When `ll-loop run exploratory-refactor` is invoked, these values override the global ll-config for the session automatically.

## Implementation Steps

1. **Extend `FSMLoop` schema** (`scripts/little_loops/fsm/schema.py`): Add an optional `config` field (dict or typed dataclass) that maps recognized ll-config keys to their override values. Validate recognized keys on load; warn (don't fail) on unknown keys.

2. **Define recognized override keys**: Start with the subset most useful for loop authors:
   - `handoff_threshold` (int, 1–100) → sets `LL_HANDOFF_THRESHOLD` env var
   - `commands.confidence_gate.readiness_threshold` (int, 1–100)
   - `commands.confidence_gate.outcome_threshold` (int, 1–100)
   - `automation.max_continuations` (int, ≥1)
   - `continuation.max_continuations` (int, ≥1)

3. **Apply overrides in `ll-loop run`** (`scripts/little_loops/cli/loop/run.py`): After loading the loop YAML and before spawning the Claude session, merge `loop.config` overrides into the effective config. CLI flags (`--handoff-threshold`) still take highest precedence.

4. **Update `ll-loop info`** (`scripts/little_loops/cli/loop/info.py`): Display any config overrides in loop info output.

5. **Update schema validation** (`scripts/little_loops/fsm/schema.py`): Add YAML schema docs and validation for the `config` block.

6. **Update `ll-loop create` / create-loop skill**: Prompt for config overrides during interactive loop creation.

7. **Tests**: Add unit tests for schema parsing with `config` block, override application, and CLI flag precedence.

## API/Interface

New top-level `config` key in loop YAML (all fields optional):

```yaml
config:
  handoff_threshold: 60            # overrides LL_HANDOFF_THRESHOLD
  commands:
    confidence_gate:
      readiness_threshold: 70
      outcome_threshold: 55
  automation:
    max_continuations: 5
  continuation:
    max_continuations: 5
```

Precedence (highest to lowest):
1. CLI flags (`--handoff-threshold`)
2. Loop YAML `config` block
3. Global `ll-config.json`
4. Schema defaults

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — Add `LoopConfigOverrides` dataclass and `config` field to `FSMLoop`; update `from_dict` and `to_dict`
- `scripts/little_loops/cli/loop/run.py` — Apply `fsm.config` overrides after YAML load (lines 49-73); set env vars and mutate config objects before executor starts
- `scripts/little_loops/cli/loop/info.py` — Display config overrides in `cmd_show` header block (lines 638-661)
- `scripts/little_loops/fsm/validation.py` — Add validation for recognized override keys in `validate_fsm` or `load_and_validate`
- `scripts/little_loops/config/automation.py` — `ConfidenceGateConfig` (lines 91-104): currently only has `enabled` and `threshold`; to support `readiness_threshold`/`outcome_threshold` as separate overridable fields, this class needs two new fields (see **Schema Divergence** below)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:8` — imports `add_handoff_threshold_arg`; defines the `--handoff-threshold` CLI arg registered at line 153
- `scripts/little_loops/cli/loop/_helpers.py:256-258` — forwards `handoff_threshold` arg to background subprocess in `run_background()`; must also forward config-derived threshold when no CLI flag is present
- `scripts/little_loops/cli_args.py` — contains `add_handoff_threshold_arg`; referenced pattern for how threshold args are added

### Similar Patterns
- `FSMLoop.from_dict` at `schema.py:459-486` — all new fields follow the same `.get(key, default)` pattern; `LLMConfig` (lines 346-386) is the cleanest analogy: a nested dataclass with its own `from_dict`/`to_dict` and a field on `FSMLoop`
- `run.py:49-73` — existing override block applies CLI args to `fsm` object; new config-block overrides slot in after line 65 (context injection) and before line 76 (dry-run check)
- `run.py:67-73` — `LL_HANDOFF_THRESHOLD` and `LL_CONTEXT_LIMIT` pattern shows how env-var overrides are applied

### Tests
- `scripts/tests/test_fsm_schema.py` — primary schema test file; uses `make_fsm()` helper and `FSMLoop.from_dict` round-trips; add config-block parsing tests here
- `scripts/tests/test_ll_loop_integration.py` — CLI-level tests; add tests for override application and flag precedence here
- `scripts/tests/test_fsm_schema_fuzz.py` — fuzz tests for schema; may need updating for new `config` field

### Documentation / Configuration
- `config-schema.json` — JSON schema for `ll-config.json`; the loop YAML schema is not separately documented there, but the config keys used as overrides must match the schema keys (e.g., `commands.confidence_gate.readiness_threshold`)
- `skills/create-loop/` — interactive loop creation skill; should prompt for config overrides

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/fsm-loop-schema.json` — **also needs updating**: this is the separate JSON schema for the loop YAML format itself (distinct from `config-schema.json`); must add a `config` block definition here so the schema reflects the new field
- `hooks/scripts/context-monitor.sh:26` — **critical data flow**: this is where `LL_HANDOFF_THRESHOLD` is actually consumed (`THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"`); the Python executor never reads the env var directly — it only detects the `CONTEXT_HANDOFF:` signal that the hook emits
- `scripts/little_loops/fsm/validation.py:76-92` — `KNOWN_TOP_LEVEL_KEYS` frozenset must have `"config"` added; without it, YAML files with a `config:` block will emit a WARNING on every load
- `scripts/little_loops/cli/loop/__init__.py:221` — `ll-loop resume` also registers `add_handoff_threshold_arg`; if resume re-starts a paused loop, it should also apply YAML config block overrides
- `scripts/tests/test_cli_loop_background.py` and `scripts/tests/test_ll_loop_parsing.py` — also test `handoff_threshold`/`LL_HANDOFF_THRESHOLD` behavior; need updates for YAML config block tests
- `loops/` directory (26 YAML files) — at least one live loop already uses `handoff_threshold` and `max_continuations` in context variables; review `loops/sprint-build-and-validate.yaml` as a model for operator usage patterns

### Schema Divergence (Important for Implementer)

The issue mentions `commands.confidence_gate.readiness_threshold` and `commands.confidence_gate.outcome_threshold` as override targets. However, the current Python class (`config/automation.py:91-104`) has only:
```python
@dataclass
class ConfidenceGateConfig:
    enabled: bool = False
    threshold: int = 85  # single field, not split
```

`config-schema.json` (lines 295-320) **does** define separate `readiness_threshold` (default 85) and `outcome_threshold` (default 70) fields, but `ConfidenceGateConfig.from_dict` reads only `threshold`. The `next_action.py` skill reads these as CLI args (`args.ready_threshold`, `args.outcome_threshold`), not from `BRConfig`.

**Implication for this feature**: To make `commands.confidence_gate.readiness_threshold` overridable from loop YAML, the implementer must first update `ConfidenceGateConfig` to add `readiness_threshold` and `outcome_threshold` as separate fields (aligning Python code with the JSON schema), or map the loop YAML override keys differently. This is an undocumented prerequisite.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop execution model and config loading |
| guidelines | .claude/CLAUDE.md | CLI tools and config schema reference |

## Labels

`feat`, `fsm`, `loops`, `config`, `captured`

---

## Status

**Open** | Created: 2026-03-23 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-03-23T19:28:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96b5e822-aa37-416b-9c6d-1f4c72316bb4.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/345cc7c0-0969-446e-b124-5aecd9852207.jsonl`
