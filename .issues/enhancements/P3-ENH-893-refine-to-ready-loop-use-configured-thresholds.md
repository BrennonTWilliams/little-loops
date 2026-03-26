---
id: ENH-893
priority: P3
status: backlog
discovered_date: 2026-03-26
discovered_by: capture-issue
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
2. Update the `ll-loop` runtime (or loop YAML variable interpolation) to expose config values as template variables (e.g., `{{config.commands.confidence_gate.readiness_threshold}}`).
3. Replace the hardcoded values in `refine-to-ready-issue.yaml` with those variable references.
4. Document the new config fields in `config-schema.json` and `docs/`.

## Implementation Steps

1. Extend `config-schema.json` to add `readiness_threshold` and `outcome_threshold` under `commands.confidence_gate`
2. Update `ll-loop` context loading to inject `config.*` values into FSM variable context
3. Update `scripts/little_loops/loops/refine-to-ready-issue.yaml` `confidence_check.evaluate.prompt` to use interpolated variables
4. Add defaults (90 / 75) to the schema so existing configs without these fields continue to work
5. Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/API.md` to document the new config fields

## Acceptance Criteria

- [ ] `ll-config.json` schema includes `readiness_threshold` and `outcome_threshold` with defaults 90 / 75
- [ ] `refine-to-ready-issue.yaml` uses config-driven values in the `confidence_check` evaluate prompt
- [ ] Changing the thresholds in `ll-config.json` changes loop behavior without modifying the YAML
- [ ] Existing projects without the new fields continue working with the previous defaults

## Scope Boundaries

- **In scope**: Schema extension, runtime variable injection for config values, YAML update, docs
- **Out of scope**: Changing default threshold values, adding UI for threshold editing, applying this pattern to other loops

## Impact

- **Priority**: P3 - Quality-of-life; no urgent production impact
- **Effort**: Small-Medium - Requires touching the loop runner context injection and schema
- **Risk**: Low - Defaults preserve existing behavior

## Labels

`enhancement`, `loops`, `config`, `refine-to-ready`

---

## Status

**Current**: backlog

## Session Log
- `/ll:capture-issue` - 2026-03-26T19:31:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d8e1735-f189-4b39-be06-236e6011a12e.jsonl`
