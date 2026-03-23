---
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 92
outcome_confidence: 79
---

# FEAT-862: FSM loop YAML per-loop config overrides

## Summary

Add an optional `config` block to the loop YAML definition that allows a loop to embed per-loop overrides for ll-config values (e.g., `handoff_threshold`, `readiness_threshold`, `outcome_threshold`). These overrides apply for the duration of that loop's execution and take precedence over global ll-config settings and CLI flags.

## Context

**Direct mode**: User description: "Enable FSM loops yaml to include overrides for values like --handoff-threshold, readiness and outcome confidence thresholds, and other related values from ll-config (schema is config-schema.json)"

Currently the only way to override `LL_HANDOFF_THRESHOLD` for a loop run is via `ll-loop run --handoff-threshold N` (added in ENH-768). There is no mechanism to bake the override into the loop YAML itself, so operators must re-specify it every time or wrap `ll-loop run` in a script. For confidence gate thresholds (`readiness_threshold`, `outcome_threshold`), there are no per-run override flags at all — only global ll-config settings.

## Current Behavior

Loop configuration values such as `handoff_threshold`, `readiness_threshold`, and `outcome_threshold` can only be set via:
1. Global `ll-config.json` settings (applies to all loops)
2. CLI flags at invocation time: `ll-loop run --handoff-threshold N`

There is no mechanism to embed these overrides in the loop YAML itself. Operators must re-specify CLI flags on every `ll-loop run` invocation or wrap the command in a script. For confidence gate thresholds (`readiness_threshold`, `outcome_threshold`), there are no per-run override flags at all — only global `ll-config` settings apply.

## Expected Behavior

Loop YAML files support an optional top-level `config` block that embeds per-loop overrides for `ll-config` values. When `ll-loop run <loop-name>` is invoked, the `config` block overrides the global `ll-config` for the session. CLI flags take highest precedence and override both the YAML config block and global settings.

## Motivation

- **Self-contained loops**: Loop authors can ship YAML files that encode their own configuration requirements without burdening users with CLI flag documentation.
- **Eliminates error-prone re-specification**: Operators no longer need to re-specify `--handoff-threshold` on every invocation; the intent is captured in the loop definition.
- **Fills a configuration gap**: Confidence gate thresholds (`readiness_threshold`, `outcome_threshold`) have no per-run CLI override at all — only global config. This provides the missing per-loop escape hatch.
- **Consistent resume behavior**: `ll-loop resume` respects the same YAML config block, ensuring resumed loops behave identically to fresh runs.

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

> **Prerequisite (Step 0)**: Before implementing `commands.confidence_gate.readiness_threshold` / `outcome_threshold` overrides, extend `ConfidenceGateConfig` in `scripts/little_loops/config/automation.py:91-104`. The class currently has only `enabled` and `threshold` fields. Add `readiness_threshold: int = 85` and `outcome_threshold: int = 70` to align it with `config-schema.json` (lines 295-320). Update `from_dict` to read these fields. See **Schema Divergence** section below. This prerequisite can be scoped out of v1 if only `handoff_threshold` is shipped first.

1. **Extend `FSMLoop` schema** (`scripts/little_loops/fsm/schema.py`): Add an optional `config` field (dict or typed dataclass) that maps recognized ll-config keys to their override values. Model after `LLMConfig` (lines 346-386): a nested `@dataclass` with `from_dict`/`to_dict` and a field on `FSMLoop`. Validate recognized keys on load; warn (don't fail) on unknown keys.

2. **Update `fsm-loop-schema.json`** (`scripts/little_loops/fsm/fsm-loop-schema.json`): Add a `config` property definition at the top level. The schema currently has `additionalProperties: false`, which means any YAML with a `config:` block will **fail schema validation (hard error)** until this file is updated. Define the `config` object with optional fields matching the recognized override keys: `handoff_threshold` (integer, 1–100), nested `commands.confidence_gate` with `readiness_threshold` and `outcome_threshold` (integers), and nested `automation`/`continuation` with `max_continuations` (integer ≥1). Set `additionalProperties: false` inside the `config` object to keep the schema strict.

3. **Define recognized override keys**: Start with the subset most useful for loop authors:
   - `handoff_threshold` (int, 1–100) → sets `LL_HANDOFF_THRESHOLD` env var
   - `commands.confidence_gate.readiness_threshold` (int, 1–100) ← requires Prerequisite
   - `commands.confidence_gate.outcome_threshold` (int, 1–100) ← requires Prerequisite
   - `automation.max_continuations` (int, ≥1)
   - `continuation.max_continuations` (int, ≥1)

4. **Apply overrides in `ll-loop run`** (`scripts/little_loops/cli/loop/run.py`): Inject YAML config overrides in two places so CLI flags always win:
   - **FSM object mutations** (e.g., `max_continuations`): after line 41 (`load_and_validate`) and before line 49 (CLI override block) — YAML sets the field, CLI overwrites it.
   - **Env var overrides** (e.g., `handoff_threshold`): after line 65 (context injection) and before line 67 (CLI `--handoff-threshold` check) — YAML sets `LL_HANDOFF_THRESHOLD`, CLI overwrites it.
   ```python
   # After line 65 — apply YAML loop config env overrides (CLI lines 67-70 overwrite)
   if fsm.config and fsm.config.handoff_threshold is not None:
       os.environ["LL_HANDOFF_THRESHOLD"] = str(fsm.config.handoff_threshold)
   ```

5. **Apply overrides in `ll-loop resume`** (`scripts/little_loops/cli/loop/lifecycle.py:cmd_resume`): The resume path (`lifecycle.py:143-212`) loads the FSM via `load_loop()` but currently only applies `--context` (line 183) and `--delay` (line 189). It **silently ignores `--handoff-threshold`** despite having the arg registered (via `add_handoff_threshold_arg` in `__init__.py:221`). This must be fixed as part of this feature: apply YAML config overrides after line 190, then apply the CLI `--handoff-threshold` arg on top.

6. **Update `ll-loop info`** (`scripts/little_loops/cli/loop/info.py`): Display any config overrides in loop info output.

7. **Update schema validation** (`scripts/little_loops/fsm/validation.py`): Add `"config"` to `KNOWN_TOP_LEVEL_KEYS` frozenset (line 76-91). Without this, any YAML with a `config:` block will emit a WARNING on every load.

8. **Update `ll-loop create` / create-loop skill**: Prompt for config overrides during interactive loop creation.

9. **Tests**: Add unit tests for schema parsing with `config` block, override application, and CLI flag precedence. See **Acceptance Criteria** below.

## Acceptance Criteria

_Added by `/ll:refine-issue` — explicit test scenarios for flag-vs-YAML precedence:_

| Scenario | Setup | Expected Result |
|----------|-------|----------------|
| YAML only | Loop YAML has `config.handoff_threshold: 60`; no CLI flag | `LL_HANDOFF_THRESHOLD=60` during session |
| CLI wins over YAML | YAML has `config.handoff_threshold: 60`; CLI `--handoff-threshold 80` | `LL_HANDOFF_THRESHOLD=80` (CLI overrides) |
| Global config baseline | No YAML config block; no CLI flag | `LL_HANDOFF_THRESHOLD` unset; hook falls back to `ll-config` |
| Invalid YAML value | `config.handoff_threshold: 150` | Validation warning on load; value rejected |
| Unknown key in config | `config.unknown_key: foo` | Warning logged; key ignored; loop proceeds |
| Resume applies YAML | `ll-loop resume` with YAML `config.handoff_threshold: 60` | Same behavior as `ll-loop run` |
| Resume CLI wins | `ll-loop resume --handoff-threshold 80` with YAML `config.handoff_threshold: 60` | `LL_HANDOFF_THRESHOLD=80` |

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
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Add `config` property to top-level schema; schema has `additionalProperties: false` so this is a hard requirement (YAML with `config:` block fails validation without it)
- `scripts/little_loops/cli/loop/run.py` — Inject YAML config overrides after line 65, before CLI `--handoff-threshold` check at line 67; see Step 3 above
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume` (line 143): fix silent ignore of `--handoff-threshold`; add YAML config override application after line 190 (delay override); add CLI `--handoff-threshold` handling on top
- `scripts/little_loops/cli/loop/info.py` — Display config overrides in `cmd_show` header block (lines 638-661)
- `scripts/little_loops/fsm/validation.py` — Add `"config"` to `KNOWN_TOP_LEVEL_KEYS` frozenset (line 76-91); add validation for recognized override keys
- `scripts/little_loops/config/automation.py` — `ConfidenceGateConfig` (lines 91-104): currently only has `enabled` and `threshold`; to support `readiness_threshold`/`outcome_threshold` as separate overridable fields, this class needs two new fields (see **Schema Divergence** below; can be deferred if v1 ships only `handoff_threshold`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:8` — imports `add_handoff_threshold_arg`; defines the `--handoff-threshold` CLI arg registered at line 153
- `scripts/little_loops/cli/loop/_helpers.py:256-258` — forwards `args.handoff_threshold` to the background subprocess via CLI flag. `subprocess.Popen` at line 264 has **no** `env=` kwarg, so the child inherits the parent process environment. YAML-derived `LL_HANDOFF_THRESHOLD` set via `os.environ` in `run.py` before `run_background()` is called will be inherited automatically — **no changes to `_helpers.py` are required**. The CLI flag path (lines 256-258) still correctly overrides when `--handoff-threshold` is explicitly passed.
- `scripts/little_loops/cli_args.py` — contains `add_handoff_threshold_arg`; referenced pattern for how threshold args are added

### Similar Patterns
- `FSMLoop.from_dict` at `schema.py:459-486` — all new fields follow the same `.get(key, default)` pattern; `LLMConfig` (lines 346-386) is the cleanest analogy: a nested dataclass with its own `from_dict`/`to_dict` and a field on `FSMLoop`
- `run.py:49-73` — existing override block applies CLI args to `fsm` object; new config-block overrides slot in after line 65 (context injection) and before line 76 (dry-run check)
- `run.py:67-73` — `LL_HANDOFF_THRESHOLD` and `LL_CONTEXT_LIMIT` pattern shows how env-var overrides are applied

### Tests
- `scripts/tests/test_fsm_schema.py` — primary schema test file; uses `make_fsm()` helper (line 59) and `FSMLoop.from_dict` round-trips (line 556); `LLMConfig` tests at lines 496-508 are the model for new `LoopConfigOverrides` tests; add config-block parsing tests here
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdRunHandoffThreshold` class at lines 672-756; existing tests for env-var set / not-set / out-of-range; add YAML config override and flag-precedence tests here (not `test_ll_loop_integration.py`)
- `scripts/tests/test_fsm_schema_fuzz.py` — fuzz tests for schema; may need updating for new `config` field
- `scripts/tests/test_ll_loop_parsing.py:245` — parser-level tests for `--handoff-threshold`; may need updating

### Documentation / Configuration
- `config-schema.json` — JSON schema for `ll-config.json`; the loop YAML schema is not separately documented there, but the config keys used as overrides must match the schema keys (e.g., `commands.confidence_gate.readiness_threshold`)
- `skills/create-loop/` — interactive loop creation skill; should prompt for config overrides

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

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

## Impact

- **Priority**: P3 — Quality-of-life improvement for loop authors; no blocking dependency on other work
- **Effort**: Medium — Requires changes across 7+ files (schema, validation, run, resume, info), but follows the established `LLMConfig` dataclass pattern; prerequisite `ConfidenceGateConfig` extension can be deferred
- **Risk**: Low — Additive change; existing loops without a `config:` block are unaffected; schema validation ensures invalid values are warned but don't break execution
- **Breaking Change**: No

## Labels

`feat`, `fsm`, `loops`, `config`, `captured`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-23_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- **ConfidenceGateConfig prerequisite**: `automation.py:91-104` only has a single `threshold` field; the new `readiness_threshold`/`outcome_threshold` override keys require extending this class first. This is documented in "Schema Divergence" but missing from the numbered implementation steps — add as a prerequisite or scope those keys out of v1.
- **No acceptance criteria**: Missing explicit test scenarios for edge cases (e.g., "given YAML `config.handoff_threshold: 60` and CLI default 80, effective threshold must be 60"). Without these, flag-vs-YAML precedence may be incompletely tested.
- **`ll-loop resume` not in implementation steps**: The refine-issue findings note `ll-loop resume` (line 221 in `__init__.py`) also registers `--handoff-threshold` and should apply YAML config overrides, but Step 3 only covers `ll-loop run`.

## Status

**Open** | Created: 2026-03-23 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-03-23T21:07:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9db96889-7141-4c7a-9208-51f9a202e218.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87d63032-1c5a-48a2-bbbb-58a14a066171.jsonl`
- `/ll:refine-issue` - 2026-03-23T19:44:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4128aee-3c7e-4973-884d-baaf30142c8f.jsonl`
- `/ll:refine-issue` - 2026-03-23T19:28:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96b5e822-aa37-416b-9c6d-1f4c72316bb4.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/345cc7c0-0969-446e-b124-5aecd9852207.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d420b221-a92a-4a4a-ac2a-b4d27643c447.jsonl`
