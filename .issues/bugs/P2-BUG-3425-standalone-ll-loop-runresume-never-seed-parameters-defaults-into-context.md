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

## Proposed Fix

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

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

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

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
