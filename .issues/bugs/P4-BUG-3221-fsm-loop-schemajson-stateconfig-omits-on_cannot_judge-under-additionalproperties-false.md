---
id: BUG-3221
type: BUG
title: fsm-loop-schema.json stateConfig omits on_cannot_judge under additionalProperties
  false
priority: P4
status: cancelled
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- **Correction to this issue's core premise**: `definitions.stateConfig` in `scripts/little_loops/fsm/fsm-loop-schema.json` also declares a `patternProperties` block immediately before its `additionalProperties: false` guard (lines 686-692):
  ```json
  "patternProperties": {
    "^on_": {
      "type": "string",
      "description": "Custom on_<verdict> shorthand routing for llm_structured evaluators with non-standard verdict strings"
    }
  }
  ```
  This was added in commit `39fad48f` ("fix(fsm): support custom on_<verdict> routing for llm_structured evaluators", BUG-1039, 2026-04-11) specifically so that any `on_<verdict>` key — including ones with no dedicated `properties` entry — validates. `on_cannot_judge` matches `^on_` and is therefore schema-valid under `patternProperties` regardless of not being separately listed in `properties`.
- Verified empirically: `jsonschema.validate({"action": "x", "on_cannot_judge": "retry_state"}, schema["definitions"]["stateConfig"], resolver=...)` against the live `fsm-loop-schema.json` raises no `ValidationError` — the instance is VALID.
- Consequence: the issue's claim that "the published schema rejects a key the Python loader accepts" does not hold today. Both the runtime loader (`extra_routes`) and the JSON schema (`patternProperties: "^on_"`) already accept `on_cannot_judge`, and have since BUG-1039 landed — this predates BUG-3221's capture (2026-08-16) by roughly four months. An editor/LSP that respects `patternProperties` (standard JSON Schema behavior) would not show an error for `on_cannot_judge` either.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `definitions.stateConfig.properties` (`on_blocked` sits at lines 515-518; a new `on_cannot_judge` entry would follow immediately after, mirroring its two-key shape: `type: string`, one-line `description`). This is optional given the Current Behavior correction above — the key already validates via `patternProperties: "^on_"` — so adding it is a discoverability/documentation improvement (explicit property shows up in editor autocomplete; a pattern property generally does not), not a defect fix.
- `scripts/tests/test_fsm_schema.py` — only if the property is added: extend with a presence assertion.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/schema.py` `StateConfig.from_dict()` — `_known_on_keys` set (lines 853-865) does not include `on_cannot_judge`; the `extra_routes` dict comprehension (lines 866-870) is what already accepts it at runtime regardless of the schema question. Adding an explicit schema property does not change this code path.
- `scripts/little_loops/fsm/executor.py` `_route()` (lines 2699-2752) — consults `state.extra_routes` at lines 2748-2750 as the fallback for any verdict not matched by a named field; this is how `on_cannot_judge` already routes correctly at runtime.

### Conventions in Force
- Lockstep schema/dataclass presence-assertion tests already exist in `scripts/tests/test_fsm_schema.py` for `tamper_guard`/`prepatch_check` (class `TestTamperGuard`, `test_schema_json_declares_state_and_loop_level_tamper_guard` at lines 4571-4579, `test_schema_json_declares_state_and_loop_level_prepatch_check` at lines 4581-4588) — evidence for the pattern a new `on_cannot_judge` presence assertion would follow, in the (optional) case the explicit property is added: `assert "on_cannot_judge" in schema["definitions"]["stateConfig"]["properties"]`.

### Tests
- `scripts/tests/test_fsm_schema.py` — add the presence assertion above only if the explicit property is added.

### Documentation
- `docs/reference/API.md` `little_loops.fsm.validation` section — references `validate_fsm()`'s relationship to `fsm-loop-schema.json`; would need a one-line update only if the explicit property is added.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

### Types
- `extra_routes: dict[str, str]` — the existing `StateConfig` field (`scripts/little_loops/fsm/schema.py:687`) that already carries `on_cannot_judge` at runtime; no new type is introduced.

### Signatures
- `StateConfig.from_dict(data: dict) -> StateConfig` — unaffected by this issue; its `extra_routes` comprehension (`scripts/little_loops/fsm/schema.py:866-870`) already captures `on_cannot_judge`.
- `FSMExecutor._route(state: StateConfig, verdict: str, ctx: InterpolationContext) -> str | None` — unaffected; its `extra_routes` fallback (`scripts/little_loops/fsm/executor.py:2748-2750`) already resolves `on_cannot_judge`.

### Call Path
`StateConfig.from_dict` -> `extra_routes` -> `FSMExecutor._route` is the existing runtime path that already resolves `on_cannot_judge` and is unaffected either way. No call path changes are needed — this issue, per the Current Behavior correction above, reduces to a documentation/discoverability question (should `on_cannot_judge` appear in the JSON schema's `properties` list for editor autocomplete, alongside `on_blocked`) rather than a routing defect. If pursued, the only touched artifact is the static JSON schema file itself.

### Decision Rules
N/A — no new decision logic.

## Implementation Steps

1. Re-verify the Current Behavior correction against the checked-out schema before doing anything else — `jsonschema.validate({"action": "x", "on_cannot_judge": "state"}, schema["definitions"]["stateConfig"], ...)` must actually raise before this issue's premise holds.
2. If step 1 confirms the key already validates (as found during this refine pass), this issue reduces to whether `on_cannot_judge` should additionally appear in `definitions.stateConfig.properties` for editor-autocomplete discoverability — a call for `/ll:go-no-go` or the operator, not a defect fix.
3. If pursued: `on_cannot_judge` mirrors `on_blocked`'s two-key shape (`type: string`, one-line `description`) in `scripts/little_loops/fsm/fsm-loop-schema.json`, and `scripts/tests/test_fsm_schema.py` gains a presence assertion following the `TestTamperGuard` precedent (`assert "on_cannot_judge" in schema["definitions"]["stateConfig"]["properties"]`).
4. `python -m pytest scripts/tests/test_fsm_schema.py -v` passes either way.

## Impact

Documentation and editor-validation correctness only; no runtime behavior change.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.validation` section — the MR rule
  set and `validate_fsm()`'s relationship to `fsm-loop-schema.json`

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-08-16_ — **NO-GO (SKIP)**

**Deciding Factor**: The bug as titled does not exist (schema already permits the key at runtime via `patternProperties`), and the claimed tooling benefit has no consumer in this codebase, making this a P4 cosmetic change that should wait behind the EPIC's substantive P1/P2 siblings rather than be implemented now.

### Key Arguments For
- One-line, additive, low-risk change mirroring `on_partial`/`on_blocked`, with zero Python changes needed since `on_cannot_judge` already flows through `extra_routes`.
- Direct precedent exists twice in `test_fsm_schema.py` (tamper_guard, prepatch_check presence-assertion tests).

### Key Arguments Against
- Empirically verified: `jsonschema.validate()` already accepts `on_cannot_judge` via the pre-existing `patternProperties: "^on_"` block (BUG-1039) — the issue's premise is false.
- No live consumer: a grep of all 91 built-in loop YAMLs plus `.loops/*.yaml` found zero `# yaml-language-server: $schema=...` headers, so the claimed editor-autocomplete benefit cannot manifest anywhere in this repo today. Additionally, `on_blocked` is a first-class `StateConfig` dataclass field while `on_cannot_judge` is deliberately generic via `extra_routes` — adding the schema property alone would create a documented-but-unimplemented divergence.

### Rationale
The described defect doesn't exist at runtime — the schema already accepts `on_cannot_judge` via `patternProperties`, and the issue's own refine pass already conceded this reduces to documentation/editor-validation only. The claimed autocomplete benefit has zero live consumers in this repo. Implementation ease doesn't matter if the change delivers no measurable value, and it's outranked by EPIC-3217's substantive P1/P2 siblings.

## Status

**Open** | Created: 2026-08-16 | Priority: P4


## Session Log
- `/ll:go-no-go` - 2026-08-17T00:05:52 - `2b0d7a64-ad77-453d-9916-2734007f4e80.jsonl`
- `/ll:refine-issue` - 2026-08-16T23:51:18 - `40668286-18e1-4fb3-b8c2-566405cf8bec.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
