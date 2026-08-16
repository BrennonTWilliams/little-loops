---
id: BUG-3221
type: BUG
title: fsm-loop-schema.json stateConfig omits on_cannot_judge under additionalProperties
  false
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:28:24Z'
parent: EPIC-3217
---

# BUG-3221: fsm-loop-schema.json stateConfig omits on_cannot_judge under additionalProperties false

## Summary

`scripts/little_loops/fsm/fsm-loop-schema.json` declares `on_yes`, `on_no`, `on_error`, `on_partial`, and `on_blocked` as properties of `definitions.stateConfig`, which sets `additionalProperties: false`. `on_cannot_judge` — the routing key ENH-3185 introduced — is not declared, so the published schema rejects a key the Python loader accepts.

## Current Behavior

`ll-loop validate` accepts `on_cannot_judge` (verified empirically against a modified copy of `harness-single-shot.yaml`: valid, with only the unrelated MR-8 evidence-contract warning). It does so because `StateConfig._from_dict()` collects any unrecognized `on_*` key into `extra_routes`, and `_route()` consults `extra_routes` before giving up — the mechanism ENH-3185's design notes call out as making the routing "nearly free".

The JSON schema is a separate contract. It is consumed by editor/LSP validation and referenced from `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `docs/reference/CLI.md`, and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`. A loop author who declares `on_cannot_judge` sees a schema error in their editor for a key that works at runtime.

## Expected Behavior

`definitions.stateConfig.properties.on_cannot_judge` exists, typed `string`, described as the shorthand for `cannot_judge` verdict routing — mirroring the existing `on_partial` and `on_blocked` entries.

## Motivation

Every sibling issue under this EPIC adds `on_cannot_judge` lines to loop YAML. Without the schema property, that work produces editor errors across the built-in loops.

## Proposed Solution

Add the property to `definitions.stateConfig.properties` alongside `on_blocked`. Follow the existing lockstep-test convention: `scripts/tests/test_fsm_schema.py` already pins schema/dataclass agreement for `evaluateConfig` (ENH-2896) and asserts the presence of state-level keys for `tamper_guard` (ENH-2934) and `prepatch_check` (ENH-2997) — add the equivalent presence assertion for `on_cannot_judge`.

Consider whether the `on_*` verdict shorthands should be expressed as a `patternProperties` rule instead, given that `extra_routes` accepts arbitrary verdicts by design; that would close the general drift rather than this one instance. Treat it as a design question for the implementer, not a requirement.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

Documentation and editor-validation correctness only; no runtime behavior change.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.validation` section — the MR rule
  set and `validate_fsm()`'s relationship to `fsm-loop-schema.json`

## Status

**Open** | Created: 2026-08-16 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
