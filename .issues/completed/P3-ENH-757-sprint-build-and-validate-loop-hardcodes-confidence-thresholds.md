---
id: ENH-757
type: ENH
priority: P3
title: "sprint-build-and-validate loop hardcodes confidence thresholds"
status: open
discovered_date: 2026-03-15
discovered_by: capture-issue
---

# ENH-757: sprint-build-and-validate loop hardcodes confidence thresholds

## Summary

The `loops/sprint-build-and-validate.yaml` loop hard-codes readiness (`85`) and outcome confidence (`70`) thresholds directly in its prompt strings instead of reading from `commands.confidence_gate` in `ll-config.json`. If a user changes the config thresholds, the loop silently ignores the change.

## Motivation

`ll-config.json` exposes `commands.confidence_gate.readiness_threshold` and `commands.confidence_gate.outcome_threshold` as the canonical source of truth for confidence gating. The loop currently duplicates these values as magic numbers in two places (`validate_issues` prompt and `route_validation` LLM prompt), creating a drift risk: config changes have no effect on the loop's actual gate logic.

By contrast, `max_issues` is already correctly parameterized via `context:` — the thresholds should follow the same pattern.

## Current Behavior

`loops/sprint-build-and-validate.yaml` has hardcoded literals in **three** locations:

- **Lines 42–43** (`validate_issues` action):
  ```yaml
  - Readiness score < 85
  - Outcome confidence < 70
  ```

- **Lines 52–53** (`route_validation` evaluator prompt):
  ```yaml
  Do any sprint issues fail readiness checks (readiness < 85
  or outcome confidence < 70)?
  ```

- **Line 70** (`fix_issues` action):
  ```yaml
  If an issue can't reach readiness >= 85 after refinement, consider
  ```

Values `85` and `70` are literals, not references to config. The `context:` block (lines 7–8) only defines `max_issues: 8`.

## Expected Behavior

Thresholds should be driven by `ll-config.json`:

```yaml
context:
  max_issues: 8
  readiness_threshold: 85   # default; overridable in ll-config.json
  outcome_threshold: 70     # default; overridable in ll-config.json
```

And referenced in prompts as `${context.readiness_threshold}` / `${context.outcome_threshold}`.

Ideally the loop reads the configured values at runtime (if `ll-loop` supports injecting config values into context), or at minimum the defaults live in `context:` so they're visible and editable in one place.

## Implementation Steps

1. In `loops/sprint-build-and-validate.yaml` `context:` block (after line 8), add:
   ```yaml
   context:
     max_issues: 8
     readiness_threshold: 85   # canonical: commands.confidence_gate.readiness_threshold in ll-config.json
     outcome_threshold: 70     # canonical: commands.confidence_gate.outcome_threshold in ll-config.json
   ```
2. Replace all three hardcoded literal occurrences (lines 42, 43, 52, 53, 70) with `${context.readiness_threshold}` and `${context.outcome_threshold}` respectively.
3. No Python changes required — `ll-loop` does not support automatic config injection, so context defaults in the YAML are the correct approach. Users can override at runtime with `ll-loop run sprint-build-and-validate --context readiness_threshold=90`.

_Note: `ll-loop` does not currently auto-inject `ll-config.json` values into loop context. `BRConfig` is instantiated in `scripts/little_loops/cli/loop/run.py:117` only to read a display color; no config values flow into `fsm.context`. The `--context KEY=VALUE` CLI flag (`run.py:50-57`) provides manual override._

## Scope Boundaries

- **In scope**: Parameterizing readiness and outcome confidence thresholds in `loops/sprint-build-and-validate.yaml`; investigating whether `ll-loop` supports config injection from `ll-config.json`
- **Out of scope**: Changing the default threshold values (85/70); modifying other loops that may also hardcode thresholds (separate issue if found); adding new `ll-config.json` confidence gate keys

## Success Metrics

- No hardcoded threshold literals (`85`, `70`) remain in `loops/sprint-build-and-validate.yaml`
- Changes to `commands.confidence_gate.readiness_threshold` / `outcome_threshold` in `ll-config.json` are reflected when the loop evaluates issues
- Loop behavior is identical to current behavior when config retains default values (85/70)

## API/Interface

N/A — No public API changes. This is a YAML configuration change only.

## Integration Map

### Files to Modify
- `loops/sprint-build-and-validate.yaml` — replace literal threshold values in `validate_issues` prompt and `route_validation` LLM prompt with context variable references

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:50-57` — applies `--context KEY=VALUE` overrides into `fsm.context`; no changes needed
- `scripts/little_loops/fsm/executor.py:896-912` — `_build_context()` passes `fsm.context` dict to `InterpolationContext`; resolves `${context.*}` at runtime; no changes needed

### Similar Patterns
- `max_issues` in `loops/sprint-build-and-validate.yaml` `context:` block — follow this exact parameterization pattern

### Tests
- No new tests needed — this is a pure YAML change. The interpolation behavior is already covered by `scripts/tests/test_fsm_executor.py:537-549` (`test_context_interpolation`) and `scripts/tests/test_fsm_interpolation.py:32-36`.

### Documentation
- `docs/guides/LOOPS_GUIDE.md:206` — documents `${context.*}` interpolation pattern and `--context KEY=VALUE` CLI override; no changes needed

### Configuration
- `.claude/ll-config.json` — `commands.confidence_gate.readiness_threshold` and `commands.confidence_gate.outcome_threshold` are the canonical source of truth

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | Loop runner design and context injection |
| `.claude/ll-config.json` | `commands.confidence_gate` config keys |

## Impact

- **Priority**: P3 — Config consistency improvement; not blocking but prevents silent misconfiguration when users tune thresholds
- **Effort**: Small — YAML edits to one loop file; minor investigation of `loop_runner.py` for config injection; no Python changes expected if config injection is already supported
- **Risk**: Low — Changes are contained to loop YAML; behavior is identical when defaults are unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `loops`, `captured`

## Status

**Completed** | Created: 2026-03-15 | Resolved: 2026-03-15 | Priority: P3

## Resolution

Added `readiness_threshold: 85` and `outcome_threshold: 70` to the `context:` block in `loops/sprint-build-and-validate.yaml`. Replaced all three hardcoded literal occurrences (lines 42–43, 52–53, 70) with `${context.readiness_threshold}` and `${context.outcome_threshold}`. No Python changes were required. Users can override at runtime via `ll-loop run sprint-build-and-validate --context readiness_threshold=90`.

## Session Log
- `/ll:ready-issue` - 2026-03-15T21:03:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db14f153-faad-4c48-ae3f-489c60a50e1a.jsonl`
- `/ll:refine-issue` - 2026-03-15T21:01:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95dcfad1-0399-48c5-b931-a232cf57fd74.jsonl`
- `/ll:format-issue` - 2026-03-15T20:55:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/414699bd-4339-4053-b490-e38ecc9e548d.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
