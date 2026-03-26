---
id: ENH-893
priority: P3
status: completed
discovered_date: 2026-03-26
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 86
---

# ENH-893: Refactor `refine-to-ready-issue` loop to use configured confidence thresholds

## Summary

The `refine-to-ready-issue` built-in loop hardcodes threshold values (`readiness > 90`, `outcome confidence > 75`) in its `confidence_check` state prompt. These thresholds should be read from the project's `ll-config.json` so that users can tune them without editing the loop YAML directly.

## Current Behavior

`scripts/little_loops/loops/refine-to-ready-issue.yaml` at line 33–38 contains a hardcoded LLM evaluation prompt:

```
Answer YES only if BOTH thresholds are met: (1) Readiness Score > 90, and
(2) Outcome Confidence Score > 75.
```

These values are literals in the YAML and cannot be changed without modifying the loop file itself.

## Expected Behavior

The thresholds are read from `ll-config.json` (under `commands.confidence_gate` or a new `loops.refine_to_ready` key) and interpolated into the loop's evaluation prompt at runtime. Users can override the defaults in their project config without touching the loop YAML.

## Motivation

Hardcoded thresholds create friction: users who want stricter (e.g., readiness > 95) or more relaxed (e.g., readiness > 80) gates must fork the built-in loop. Externalizing the values to config makes the loop reusable across projects with different quality standards and keeps config-driven behavior consistent with how other ll-config settings work.

## Proposed Solution

1. Add threshold fields to `ll-config.json` schema (e.g., under `commands.confidence_gate`):
   ```json
   "confidence_gate": {
     "enabled": true,
     "readiness_threshold": 90,
     "outcome_threshold": 75
   }
   ```
2. Update the `ll-loop` runtime to expose config values as FSM context variables. Two viable approaches:
   - **Approach A (simpler, consistent with `sprint-build-and-validate.yaml`)**: Add a `context:` block to `refine-to-ready-issue.yaml` with default values; users override via `--context readiness_threshold=95`. No runtime changes needed.
   - **Approach B (config-driven)**: In `scripts/little_loops/fsm/executor.py:982-998` (`_build_context`), add a `config` namespace to `InterpolationContext` by loading `BRConfig(Path.cwd()).to_dict()` and exposing it as `${config.commands.confidence_gate.readiness_threshold}`. Requires updating `InterpolationContext` in `fsm/interpolation.py:37-63` and `resolve()` at line 78.
3. Replace the hardcoded values in `refine-to-ready-issue.yaml` with variable references (`${context.readiness_threshold}` for Approach A, or `${config.commands.confidence_gate.readiness_threshold}` for Approach B).
4. Document the new config fields in `config-schema.json` and `docs/`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Decision: Implement Approach A. No Python changes required.**

- `scripts/little_loops/fsm/executor.py:988-989`: `_build_context()` already passes `context=self.fsm.context` to `InterpolationContext` — the YAML `context:` block populates this dict automatically with no wiring needed
- `scripts/little_loops/cli/loop/run.py:61-65`: `--context KEY=VALUE` args merge into `fsm.context` before execution; `--context readiness_threshold=95` works today with no code changes
- `scripts/little_loops/fsm/interpolation.py:78-79`: `context` namespace is already handled by `resolve()`; Approach B's `${config.*}` would raise `InterpolationError("Unknown namespace: config")` and require new Python
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:7-10`: Identical pattern deployed today with comments: `# canonical: commands.confidence_gate.readiness_threshold in ll-config.json`

**Exact YAML change** (only `refine-to-ready-issue.yaml` needs modification):

```yaml
# ADD after line 4 (on_handoff: spawn):
context:
  readiness_threshold: 90   # canonical: commands.confidence_gate.readiness_threshold in ll-config.json
  outcome_threshold: 75     # canonical: commands.confidence_gate.outcome_threshold in ll-config.json

# REPLACE lines 36-37:
# Before:  thresholds are met: (1) Readiness Score > 90, and
#          (2) Outcome Confidence Score > 75. Answer NO if
# After:   thresholds are met: (1) Readiness Score > ${context.readiness_threshold}, and
#          (2) Outcome Confidence Score > ${context.outcome_threshold}. Answer NO if
```

**Default values**: Use `90`/`75` (not `85`/`70`) to preserve current loop behavior. `ConfidenceGateConfig` defaults (`85`/`70`) apply to `manage-issue`'s gate, not this loop's evaluate prompt.

## API/Interface

Config schema addition under `commands.confidence_gate`:

```json
{
  "confidence_gate": {
    "enabled": true,
    "readiness_threshold": 90,
    "outcome_threshold": 75
  }
}
```

Loop YAML variable references — **FSM syntax is `${...}` not `{{...}}`**:
- Approach A (context block): `${context.readiness_threshold}` → integer (default: 90 in YAML, overridable via `--context readiness_threshold=95`)
- Approach B (config namespace): `${config.commands.confidence_gate.readiness_threshold}` → integer (from `ll-config.json`; fallback: `ConfidenceGateConfig` default of 85)

Note: `ConfidenceGateConfig` in `scripts/little_loops/config/automation.py:98-99` has defaults **85/70**, not 90/75. Implementer must decide: keep current loop behavior (90/75) as defaults in the YAML `context:` block, or adopt the schema defaults (85/70).

No Python public API changes.

## Implementation Steps

1. **No schema change needed** — `config-schema.json` already defines `commands.confidence_gate.readiness_threshold` (default: 85) and `outcome_threshold` (default: 70). `ConfidenceGateConfig` in `scripts/little_loops/config/automation.py:94-109` already models them. Verify defaults match desired behavior (current hardcoded values are 90/75; existing schema defaults are 85/70 — decide which to use).

2. **Implement Approach A** — add `context:` block to `scripts/little_loops/loops/refine-to-ready-issue.yaml` (following `sprint-build-and-validate.yaml:7-10` pattern). No Python changes needed. See exact diff in "Proposed Solution → Codebase Research Findings".

3. **Update `refine-to-ready-issue.yaml`** — replace literal `90` and `75` in `confidence_check.evaluate.prompt` (lines 33-38) with `${context.readiness_threshold}` / `${context.outcome_threshold}` (Approach A) or `${config.commands.confidence_gate.readiness_threshold}` (Approach B).

4. **Tests** — no new tests needed:
   - `scripts/tests/test_fsm_evaluators.py:948-967` (`test_dispatch_llm_structured_interpolates_prompt`) already tests `${context.readiness_threshold}` / `${context.outcome_threshold}` substitution in `evaluate.prompt` — exact variable names, exact pattern
   - `scripts/tests/test_builtin_loops.py:29-44` (`test_all_validate_as_valid_fsm`) auto-picks up the updated YAML and validates it — run to confirm no schema errors

5. **Update documentation**: `docs/guides/LOOPS_GUIDE.md` and `docs/reference/CONFIGURATION.md` (not just `API.md`) to document `commands.confidence_gate` config fields and the threshold override mechanism.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add `context:` block (lines 5-7) and replace hardcoded `90`/`75` with `${context.readiness_threshold}`/`${context.outcome_threshold}` (lines 36-37)

_No changes needed to `config-schema.json` (schema already has these fields) or `scripts/little_loops/` Python (Approach A uses existing `context` namespace with no new runtime wiring)._

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:26-34` — `main_loop()` CLI entry; loads `BRConfig(Path.cwd())` but only uses it for `loops_dir` and CLI colors; does **not** pass config into the FSM executor
- `scripts/little_loops/cli/loop/run.py:22-69` — `cmd_run()` loop entry; merges `--context` CLI args into `fsm.context`; only acts on `fsm.config.handoff_threshold` (via `os.environ`); `readiness_threshold` / `outcome_threshold` from `LoopConfigOverrides` are read for display (info.py) but never injected into context
- `scripts/little_loops/fsm/executor.py:982-998` — `FSMExecutor._build_context()` constructs `InterpolationContext`; populates `context`, `captured`, `prev`, `result`, `state`, `loop`, `env` namespaces — **this is the injection point** for a new `config` namespace
- `scripts/little_loops/fsm/interpolation.py:37-100` — `InterpolationContext.resolve()` dispatches on namespace; no `config` namespace exists — referencing `${config.*}` would raise `InterpolationError("Unknown namespace: config")`
- `scripts/little_loops/fsm/evaluators.py:817-830` — calls `interpolate(prompt, context)` on `evaluate.prompt` before sending to LLM; silently falls back to raw prompt on `InterpolationError`
- `scripts/little_loops/fsm/schema.py:389-451` — `LoopConfigOverrides` dataclass already has `readiness_threshold: int | None` and `outcome_threshold: int | None` fields (lines 404-405), but they are only used for display (`info.py:665-668`), not for prompt injection
- `scripts/little_loops/config/automation.py:94-109` — `ConfidenceGateConfig` already defines `readiness_threshold: int = 85` and `outcome_threshold: int = 70` (note: defaults are **85/70**, not 90/75 as hardcoded in the loop YAML)
- `scripts/little_loops/config/core.py:342-405` — `BRConfig.to_dict()` already exports `commands.confidence_gate.readiness_threshold` and `outcome_threshold`; `BRConfig.resolve_variable()` (line 483) supports dot-path traversal over `to_dict()`

### Similar Patterns

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/sprint-build-and-validate.yaml:7-10` — **closest analog**: uses `context:` block with `readiness_threshold: 85` and `outcome_threshold: 70`, then references them in action bodies as `${context.readiness_threshold}` and `${context.outcome_threshold}` — this is the established pattern for config-overridable thresholds in loop YAMLs
- `scripts/little_loops/loops/apo-contrastive.yaml:12,52` and `apo-opro.yaml:15,54` — use `context:` block with a `quality_threshold`/`target_score` and reference via `${context.*}` in evaluate prompts
- `scripts/little_loops/loops/evaluation-quality.yaml:12-15` — three thresholds in `context:` block, referenced via `${context.*}` in action bodies
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:68-72` (and 4 other loops) — inline Python shell snippet pattern for reading `ll-config.json` directly at runtime: `python3 -c "import json, pathlib; p = pathlib.Path('.claude/ll-config.json'); cfg = json.loads(p.read_text()) if p.exists() else {}; print(cfg.get('commands', {}).get('confidence_gate', {}).get('readiness_threshold', 90))"` in a `shell` state
- Variable syntax in FSM is `${namespace.path}` (not `{{...}}`); the issue's Proposed Solution uses incorrect `{{config.*}}` syntax

### Tests
- `scripts/tests/test_fsm_interpolation.py` — `TestInterpolationContext` tests all namespaces; extend to cover a new `config` namespace if added
- `scripts/tests/test_fsm_evaluators.py` — evaluate-prompt tests; add test verifying `${context.readiness_threshold}` is substituted before LLM call
- `scripts/tests/test_fsm_schema.py:1713-1825` — `TestLoopConfigOverrides` already covers `readiness_threshold`/`outcome_threshold` serialization; add test that injecting them into `fsm.context` flows through to `InterpolationContext`
- `scripts/tests/test_config.py:634` — `test_to_dict_confidence_gate_schema_aligned_keys` already asserts `readiness_threshold`/`outcome_threshold` in `BRConfig.to_dict()`; regression test for backward-compat defaults
- `scripts/tests/test_builtin_loops.py:29-44` — `test_all_validate_as_valid_fsm` runs every loop YAML through FSM validation; will catch schema errors in updated `refine-to-ready-issue.yaml`

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document `commands.confidence_gate` config fields
- `docs/reference/API.md` — document new config schema fields with defaults

### Configuration
- `config-schema.json` — new fields: `commands.confidence_gate.readiness_threshold` (default: 90), `commands.confidence_gate.outcome_threshold` (default: 75)
- `.claude/ll-config.json` — user-facing config inheriting new fields

## Acceptance Criteria

- [ ] `refine-to-ready-issue.yaml` has a `context:` block with `readiness_threshold: 90` and `outcome_threshold: 75` as defaults (schema fields already exist in `config-schema.json`/`ConfidenceGateConfig`; no schema changes needed)
- [ ] `refine-to-ready-issue.yaml` uses config-driven values in the `confidence_check` evaluate prompt
- [ ] Changing the thresholds in `ll-config.json` changes loop behavior without modifying the YAML
- [ ] Existing projects without the new fields continue working with the previous defaults

## Scope Boundaries

- **In scope**: YAML update (context block + variable references), docs
- **Out of scope**: Changing default threshold values, adding UI for threshold editing, applying this pattern to other loops

## Success Metrics

- Threshold propagation: changing `readiness_threshold` in `ll-config.json` changes the YES/NO gate in the `confidence_check` evaluate prompt without modifying the loop YAML
- Backward compatibility: projects without `readiness_threshold`/`outcome_threshold` fields run with the original 90/75 defaults unchanged
- No regression: all existing `refine-to-ready-issue` acceptance criteria pass with default config

## Impact

- **Priority**: P3 - Quality-of-life; no urgent production impact
- **Effort**: Small - YAML-only change; no Python or schema modifications needed
- **Risk**: Low - Defaults preserve existing behavior
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `config`, `refine-to-ready`

---

## Status

**Current**: completed

## Resolution

Implemented Approach A (YAML-only change, no Python modifications).

- Added `context:` block to `scripts/little_loops/loops/refine-to-ready-issue.yaml` with `readiness_threshold: 90` and `outcome_threshold: 75` defaults (matching the previous hardcoded values to preserve backward compatibility)
- Replaced hardcoded `> 90` and `> 75` in the `confidence_check` evaluate prompt with `${context.readiness_threshold}` and `${context.outcome_threshold}`
- Updated `docs/reference/CONFIGURATION.md` to note that `refine-to-ready-issue` uses these config-driven thresholds
- Updated `docs/guides/LOOPS_GUIDE.md` to document the per-run `--context` override mechanism

Users can now override thresholds per-run (`--context readiness_threshold=85`) or install the loop locally and set `commands.confidence_gate.readiness_threshold` in `ll-config.json`.

## Session Log
- `/ll:ready-issue` - 2026-03-26T20:02:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3197ba7-99f1-4d43-9a8b-4e3536ea4d41.jsonl`
- `/ll:refine-issue` - 2026-03-26T19:55:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12adbe9d-0694-4215-8345-f111e716f460.jsonl`
- `/ll:confidence-check` - 2026-03-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d74fd998-5ed3-431a-9af6-24ec2e79ab03.jsonl`
- `/ll:refine-issue` - 2026-03-26T19:48:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c471ee77-14f8-4630-9bf8-5cb13df084f7.jsonl`
- `/ll:format-issue` - 2026-03-26T19:40:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ddc13abb-2a4b-4c6f-a878-8a6902ed75f4.jsonl`
- `/ll:manage-issue` - 2026-03-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:capture-issue` - 2026-03-26T19:31:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d8e1735-f189-4b39-be06-236e6011a12e.jsonl`
