---
id: ENH-1949
title: Add parameters block to dataset-curation.yaml for with-binding validation
type: ENH
priority: P4
status: open
captured_at: '2026-06-04T20:01:37Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
relates_to:
  - EPIC-1880
  - FEAT-1826
labels:
  - epic: EPIC-1880
  - enhancement
  - loop
  - sft
---

# ENH-1949: Add parameters block to dataset-curation.yaml for with-binding validation

## Summary

FEAT-1826's Option B decision requires `dataset-curation.yaml` to declare a `parameters:` block so `_validate_with_bindings()` can enforce the `with:` contract when `sft-corpus` hands off. The current `dataset-curation.yaml` has only a `context:` block — adding `parameters:` with defaults matching existing context values makes the contract explicit, type-checkable, and non-breaking for direct `ll-loop run dataset-curation` invocations.

## Current Behavior

`dataset-curation.yaml` defines its inputs implicitly via `context:`:
```yaml
context:
  quality_threshold: 70
  min_per_category: 2
  adversarial_cap: 0.3
  data_dir: "data/raw"
  output_dir: "data/curated"
  schema_path: "schemas/dataset.json"
```

There is no `parameters:` block. When another loop hands off via `loop: dataset-curation` with `with:` bindings, `_validate_with_bindings()` has no `ParameterSpec` declarations to validate against — the contract is enforced only by runtime interpolation, not at load time.

## Expected Behavior

`dataset-curation.yaml` declares a `parameters:` block for the subset of context keys that cross-loop handoffs are expected to bind:

```yaml
parameters:
  data_dir:
    type: string
    default: "data/raw"
    description: "Directory containing raw data items to curate"
    required: false
  output_dir:
    type: string
    default: "data/curated"
    description: "Output directory for curated dataset and manifest"
    required: false
  schema_path:
    type: string
    default: "schemas/dataset.json"
    description: "Path to JSON Schema for validation"
    required: false
```

This follows the `ParameterSpec` schema (`schema.py:208`) and the `scan-and-implement.yaml:77` pattern for `with:` bindings. `required: false` + defaults matching the existing context values ensures no breakage for direct invocations.

## Motivation

FEAT-1826's Option B wiring (`sft-corpus → dataset-curation` via `with:`) needs `_validate_with_bindings()` to verify that bound keys exist and have correct types. Without `parameters:`, the contract is implicit — typos in `with:` keys silently become runtime interpolation failures. Adding explicit `parameters:` shifts failure detection left to load time.

This is listed as FEAT-1826 wiring step 8: "Modify `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block... enables `_validate_with_bindings()` contract enforcement." It's tracked separately because it modifies `dataset-curation.yaml` (a shared, non-FEAT-1826 file) and must be non-breaking for all existing consumers.

## API/Interface

This enhancement introduces a `parameters:` block to `dataset-curation.yaml` following the `ParameterSpec` schema (`scripts/little_loops/fsm/schema.py:208`):

```yaml
parameters:
  data_dir:
    type: string
    default: "data/raw"
    description: "Directory containing raw data items to curate"
    required: false
  output_dir:
    type: string
    default: "data/curated"
    description: "Output directory for curated dataset and manifest"
    required: false
  schema_path:
    type: string
    default: "schemas/dataset.json"
    description: "Path to JSON Schema for validation"
    required: false
```

All parameters are `required: false` with defaults matching existing `context:` values — no breaking changes. The `parameters:` block is consumed by `_validate_with_bindings()` in the FSM executor when another loop hands off via `with:`.

## Implementation Steps

1. Add `parameters:` block to `dataset-curation.yaml` declaring `data_dir`, `output_dir`, `schema_path` with `required: false` and defaults matching the existing `context:` values
2. Verify `ll-loop validate dataset-curation` still reports no errors
3. Verify existing `dataset-curation` tests pass (no regression)
4. Verify `_validate_with_bindings()` now catches a misspelled `with:` key at load time (add test to `test_fsm_executor.py` following `test_with_interpolation_from_parent_context` pattern)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_validate_with_bindings()` consumes `parameters:` at handoff time
- `scripts/little_loops/loops/sft-corpus.yaml` — FEAT-1826 consumer that will bind `with:` keys validated by this block

### Similar Patterns
- `scripts/little_loops/loops/scan-and-implement.yaml:77` — reference implementation of `parameters:` with `with:` bindings

### Tests
- `scripts/tests/test_fsm_executor.py` — add test for `with:` key validation following `test_with_interpolation_from_parent_context` pattern
- Existing `dataset-curation` tests — verify no regression

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Add `parameters:` block to `dataset-curation.yaml`; verify non-breaking; add `with:` binding validation test
- **Out of scope**: Changes to `sft-corpus.yaml` (FEAT-1826); adding `parameters:` to other loops; changing `dataset-curation`'s context defaults or behavior

## Success Metrics

- **Validation**: `ll-loop validate dataset-curation` exits 0 with no errors
- **Contract enforcement**: Misspelled `with:` key in a cross-loop handoff produces a load-time `ParameterSpec` validation error (not a silent runtime interpolation failure)
- **No regression**: Existing `dataset-curation` tests pass without modification
- **Test coverage**: New test in `test_fsm_executor.py` verifies `_validate_with_bindings()` catches invalid `with:` keys

## Impact

- **Priority**: P4 — Low urgency; handoff works at runtime without this, just without contract enforcement
- **Effort**: Small — ~15 lines of YAML + test
- **Risk**: Low — `required: false` + matching defaults = non-breaking for all existing consumers
- **Breaking Change**: No
- **Depends on**: FEAT-1826 (motivates the change but doesn't block it)

## Related Key Documentation

- `docs/reference/API.md` — FSM schema reference (`ParameterSpec`)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — loop authoring guide
- `docs/ARCHITECTURE.md` — FSM executor and handoff flow

## Related

- FEAT-1826 — `sft-corpus` loop (primary consumer of the `with:` binding this enables)
- EPIC-1880 — parent epic
- `scripts/little_loops/loops/dataset-curation.yaml` — the file to modify
- `scripts/little_loops/fsm/schema.py:208` — `ParameterSpec` schema
- `scripts/little_loops/loops/scan-and-implement.yaml:77` — reference pattern for `with:` bindings

## Labels

`enhancement`, `loop`, `sft`

## Session Log
- `/ll:format-issue` - 2026-06-04T20:10:22 - `d53c2aa2-0b92-419f-9a24-0dcb7fadf635.jsonl`
- `/ll:capture-issue` - 2026-06-04T20:01:37Z - `b0ca5e28-1c3f-4a31-b1d5-f67d60516393.jsonl`

---
## Status

**Open** | Created: 2026-06-04 | Priority: P4
