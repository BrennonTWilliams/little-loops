---
id: BUG-3425
type: BUG
title: Standalone ll-loop run/resume never seed parameters defaults into context
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:41Z'
---

# BUG-3425: Standalone ll-loop run/resume never seed parameters defaults into context

## Summary

Standalone `ll-loop run` and `ll-loop resume` never apply loop-level `parameters:` defaults to the FSM context. `ParameterSpec.default` is only consumed on the sub-loop `with:` binding path (`scripts/little_loops/fsm/executor.py:1090-1096`); neither `scripts/little_loops/cli/loop/run.py` nor `scripts/little_loops/cli/loop/lifecycle.py` reads `fsm.parameters` at all. A loop declaring `parameters: {max_remediation_passes: {type: integer, default: 3}}` therefore gets no `max_remediation_passes` key in context when launched directly, so `${context.max_remediation_passes}` either trips the pre-run missing-key check (`run.py:278`) or renders empty.

## Current Workaround In The Catalog

The builtin loops duplicate the default as a literal under `context:`:

- `scripts/little_loops/loops/rn-remediate.yaml:65` — `max_remediation_passes: 3` under `context:` while the `parameters:` entry at line 48 carries only a description saying "(default: 3)" and no `default:` field.
- `scripts/little_loops/loops/rn-decompose.yaml:51` — `parent_depth: 0` under `context:` mirroring the `parameters:` entry at line 42 ("(default: 0)").
- The comment at `rn-remediate.yaml:86` explicitly calls `max_remediation_passes` "a per-loop default that callers can tune", i.e. the literal exists to serve what `parameters.default` should already provide.

## Origin

Proposal from the ll-console agent (2026-09-09). Its diagnosis was that a `context:` entry shaped `{type: number, default: 3}` renders its Python repr when interpolated and should be "collapsed" at run start. That symptom is real but the seam is wrong: typed dicts under `context:` are an undocumented form (the JSON schema's `context` is `additionalProperties: true`, no typed-entry shape). The documented typed-declaration form is the top-level `parameters:` block (FEAT-1311), and the actual gap is that its defaults are not seeded for standalone runs.

## Proposed Solution

1. Add `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` to `scripts/little_loops/fsm/context_seed.py`. For each non-required parameter whose `default is not None`, `context.setdefault(name, spec.default)`. `setdefault` keeps precedence: positional input (run.py:165-179), `program.md` injection, and the persisted resume context (lifecycle.py:658-660) all land before it and win.
2. Call it from both `run.py` (immediately before the `apply_context_overrides` call at line 190) and `lifecycle.py` (immediately before line 665), following the same shared-helper pattern `apply_context_overrides` already uses so the two launch paths cannot diverge. Placing it before overrides means `--context k=v` still wins and `_coerce_override` sees the typed default (an `int`/`bool` instance), so coercion works without the `{type:}` dict branch.
3. Add `default:` to the `parameters:` entries currently duplicated under `context:` (rn-remediate `max_remediation_passes`, rn-decompose `parent_depth`; audit `scripts/little_loops/loops/lib/common.yaml:54` `max_retries` and any other `parameters:` entry whose description says "default:") and remove the `context:` duplicates. Keep the surrounding comments that explain caller tuning.
4. Optional lint: `ll-loop validate` warning when a `context:` value is a dict carrying a `type` key, pointing the author at `parameters:`.

## Explicit Non-Goals

- Do **not** change `FSMLoop.from_dict` / `to_dict` or what `ll-loop show -j` emits (`scripts/little_loops/fsm/schema.py:1504-1506, 1691`). ll-console renders parameter forms from the raw emitted spec (parameter metadata plus the `context:` literal as the displayed default) and depends on it staying declarative. After step 3 the default moves into the emitted `parameters[name].default`, which is already serialized by `ParameterSpec.to_dict`; ll-console should prefer that field when present.
- Do not add a `{type, default}` dict form under `context:`.

## Acceptance Criteria

- [ ] Fixture loop with `parameters:` of type integer, boolean, and string, each with `default:` and `required: false`; standalone `ll-loop run` seeds all three into context with native Python types.
- [ ] Same fixture via `ll-loop resume` seeds the defaults when the persisted state lacks the key, and does not overwrite a persisted value.
- [ ] `--context k=v` overrides the seeded default and is coerced to the declared type via `_coerce_override`.
- [ ] Positional input and `program.md` injection win over a parameter default for the same key.
- [ ] `required: true` parameters without `default:` are unaffected (still missing, still caught by the pre-run check).
- [ ] `ll-loop show -j` output for the fixture is byte-identical before and after the change apart from the added `default` fields under `parameters`.
- [ ] rn-remediate and rn-decompose carry their defaults under `parameters:` only; `ll-loop validate` passes on both.


## Current Behavior

Standalone `ll-loop run` and `ll-loop resume` never seed `parameters:` defaults into context. Only the sub-loop `with:` binding path in `executor.py:1090-1096` applies `ParameterSpec.default`. A loop declaring an optional parameter with a `default:` gets no corresponding key seeded into context when launched directly.

## Expected Behavior

All three loop-launch paths — sub-loop `with:` binding, standalone `ll-loop run`, and `ll-loop resume` — seed `parameters:` defaults into context consistently, with existing precedence (positional input, `program.md` injection, persisted resume context, `--context` overrides) still winning over the seeded default.

## Motivation

`parameters:` with typed `default:` is the documented declaration form (FEAT-1311), but it silently does nothing outside sub-loop `with:` bindings. Loop authors work around this by duplicating the default as a `context:` literal (`rn-remediate.yaml`, `rn-decompose.yaml`), which is an undocumented `context:` shape, creates two sources of truth that can drift, and is the root cause of the Python-repr-rendering symptom the ll-console agent originally reported (see Origin). Fixing the seeding gap removes the workaround and makes `parameters.default` behave consistently across all three launch paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/context_seed.py` — add `seed_parameter_defaults()`
- `scripts/little_loops/cli/loop/run.py` — call before the `apply_context_overrides` call at line 190
- `scripts/little_loops/cli/loop/lifecycle.py` — call before line 665
- `scripts/little_loops/loops/rn-remediate.yaml` — move `max_remediation_passes` default from `context:` (line 65) to `parameters:` (line 48)
- `scripts/little_loops/loops/rn-decompose.yaml` — move `parent_depth` default from `context:` (line 51) to `parameters:` (line 42)
- `scripts/little_loops/loops/lib/common.yaml:54` — audit `max_retries` and any other `parameters:` entry whose description says "default:"

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:1090-1096` — existing sub-loop `with:` binding consumer of `ParameterSpec.default`; must stay consistent with the new shared helper
- `scripts/little_loops/fsm/schema.py:1504-1506, 1691` — `ParameterSpec.to_dict` / `ll-loop show -j` emission consumed by ll-console; unaffected by this fix per Explicit Non-Goals

### Similar Patterns
- `apply_context_overrides` — the existing shared-helper pattern `seed_parameter_defaults` should follow so the two launch paths cannot diverge

### Tests
- `scripts/tests/` — new fixture loop with integer/boolean/string `parameters:` (each `default:`, `required: false`) plus tests for standalone `ll-loop run`, `ll-loop resume`, `--context` override precedence, and `required: true` parameters without `default:`

### Documentation
- `docs/reference/CLI.md` — `ll-loop run`/`ll-loop resume` parameter-default behavior

### Configuration
- N/A

## Program Design

### Types

- (none new — reuses `ParameterSpec` from `scripts/little_loops/fsm/schema.py`)

### Signatures

- `seed_parameter_defaults(context: dict[str, Any], parameters: dict[str, ParameterSpec]) -> None` — `scripts/little_loops/fsm/context_seed.py`

### Call Path

`cli/loop/run.py:run()` -> `seed_parameter_defaults()` -> `apply_context_overrides()` (mirrored in `cli/loop/lifecycle.py` resume path)

## Implementation Steps

1. Add `seed_parameter_defaults()` to `scripts/little_loops/fsm/context_seed.py`
2. Call it from `run.py` (before line 190) and `lifecycle.py` (before line 665), following the `apply_context_overrides` shared-helper pattern
3. Move the duplicated `context:` literal defaults (rn-remediate, rn-decompose, common.yaml) into `parameters.default` and remove the `context:` duplicates
4. Optional: add an `ll-loop validate` lint warning when a `context:` value is a dict carrying a `type` key
5. Verify with the fixture loop against each Acceptance Criterion

## Impact

- **Priority**: P2 - silent context gap breaks `parameters.default` outside sub-loop `with:` bindings, but shipped loops currently mask it with the `context:` literal workaround
- **Effort**: Medium - one new helper, two call sites, plus migrating rn-remediate, rn-decompose, and common.yaml off the workaround
- **Risk**: Low - purely additive seeding via `setdefault`; existing precedence order is preserved by design
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P2

## Steps to Reproduce

1. Create a loop YAML with `parameters: {max_remediation_passes: {type: integer, default: 3}}` and a state referencing `${context.max_remediation_passes}`.
2. Run it directly with `ll-loop run <loop>.yaml` (not as a sub-loop `with:` binding).
3. Observe: the pre-run missing-key check at `run.py:278` rejects the run, or the interpolation renders empty — `max_remediation_passes` was never seeded because `run.py`/`lifecycle.py` never read `fsm.parameters`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py` and `scripts/little_loops/cli/loop/lifecycle.py`
- **Anchor**: `run.py` before the `apply_context_overrides` call (line 190); `lifecycle.py` before line 665
- **Cause**: Only the sub-loop `with:` binding path in `executor.py:1090-1096` seeds `ParameterSpec.default` into context — neither standalone launch entry point reads `fsm.parameters` at all.

## Error Messages

## Environment

## Frequency

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 1090-1096
- **Anchor**: sub-loop `with:` binding default-seeding — the only existing call site that applies `ParameterSpec.default`
- **Code**:
```
# ParameterSpec.default is read here for sub-loop `with:` bindings only;
# run.py and lifecycle.py have no equivalent call.
```

## Session Log
- `/ll:refine-issue` - 2026-09-09T20:41:28 - `505beecf-ceb4-4da8-912d-d233f746daca.jsonl`
- `/ll:format-issue` - 2026-09-09T20:37:49 - `575c8055-4eaf-4c28-a902-79bb09bf07a6.jsonl`
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
