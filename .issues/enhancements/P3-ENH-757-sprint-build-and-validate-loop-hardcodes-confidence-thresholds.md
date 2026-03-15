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

`loops/sprint-build-and-validate.yaml` lines 41–44 and 51–53:

```yaml
validate_issues:
  action: |
    Flag any issues with:
    - Readiness score < 85
    - Outcome confidence < 70

route_validation:
  evaluate:
    prompt: |
      Do any sprint issues fail readiness checks (readiness < 85
      or outcome confidence < 70)?
```

Values `85` and `70` are literals, not references to config.

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

1. Check whether `ll-loop` supports config-injection into `context:` (e.g. from `ll-config.json` at startup).
2. If yes: map `commands.confidence_gate.readiness_threshold` → `context.readiness_threshold` and `commands.confidence_gate.outcome_threshold` → `context.outcome_threshold`.
3. If no: add explicit `context:` defaults (`readiness_threshold: 85`, `outcome_threshold: 70`) and replace the four literal occurrences in the YAML with `${context.readiness_threshold}` / `${context.outcome_threshold}`.
4. Update `loops/sprint-build-and-validate.yaml` accordingly.
5. Add a comment in the loop's `context:` block pointing to the config key for reference.

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
- `scripts/little_loops/loop_runner.py` (or equivalent) — investigate config injection support; may need to add logic to inject `ll-config.json` values into loop `context:` at startup

### Similar Patterns
- `max_issues` in `loops/sprint-build-and-validate.yaml` `context:` block — follow this exact parameterization pattern

### Tests
- TBD — if config injection is added to `loop_runner.py`, add a test verifying context variables override defaults

### Documentation
- `docs/ARCHITECTURE.md` — may reference loop runner context injection design

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

**Open** | Created: 2026-03-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
