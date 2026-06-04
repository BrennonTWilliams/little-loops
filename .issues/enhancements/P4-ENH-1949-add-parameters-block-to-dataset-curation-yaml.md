---
id: ENH-1949
title: Add parameters block to dataset-curation.yaml for with-binding validation
type: ENH
priority: P4
status: done
captured_at: '2026-06-04T20:01:37Z'
completed_at: '2026-06-04T20:44:55Z'
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
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

This follows the `ParameterSpec` schema (`schema.py:209`) and the `rn-remediate.yaml:31-53` pattern for `parameters:` + `context:` with matching defaults. `required: false` + defaults matching the existing context values ensures no breakage for direct invocations.

## Motivation

FEAT-1826's Option B wiring (`sft-corpus → dataset-curation` via `with:`) needs `_validate_with_bindings()` to verify that bound keys exist and have correct types. Without `parameters:`, the contract is implicit — typos in `with:` keys silently become runtime interpolation failures. Adding explicit `parameters:` shifts failure detection left to load time.

This is listed as FEAT-1826 wiring step 8: "Modify `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block... enables `_validate_with_bindings()` contract enforcement." It's tracked separately because it modifies `dataset-curation.yaml` (a shared, non-FEAT-1826 file) and must be non-breaking for all existing consumers.

## API/Interface

This enhancement introduces a `parameters:` block to `dataset-curation.yaml` following the `ParameterSpec` schema (`scripts/little_loops/fsm/schema.py:209`):

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

All parameters are `required: false` with defaults matching existing `context:` values — no breaking changes. The `parameters:` block is consumed by `_validate_with_bindings()` in `validation.py:328` (load time) and `_execute_sub_loop()` in `executor.py:506` (runtime) when another loop hands off via `with:`.

## Implementation Steps

1. Add `parameters:` block to `dataset-curation.yaml` declaring `data_dir`, `output_dir`, `schema_path` with `required: false` and defaults matching the existing `context:` values
2. Verify `ll-loop validate dataset-curation` still reports no errors (auto-covered by `test_builtin_loops.py:test_all_validate_as_valid_fsm`)
3. Verify existing `dataset-curation` tests pass (no regression)
4. Add test to `test_fsm_executor.py` verifying `_validate_with_bindings()` catches a misspelled `with:` key at load time: write child YAML with `parameters:`, parent with misspelled `with:` key, call `load_and_validate()`, assert `ValidationError` in returned errors (follow the validation-test pattern in `test_fsm_validation.py:479-573`, not the runtime-output pattern in `test_with_interpolation_from_parent_context`)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/dataset-curation.yaml` — add `parameters:` block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py:328` — `_validate_with_bindings()` consumes `parameters:` at load time for static contract enforcement (called from `load_and_validate()` at line 1547)
- `scripts/little_loops/fsm/executor.py:506` — `_execute_sub_loop()` handles runtime `with:` binding, default application, and required-param enforcement
- `scripts/little_loops/loops/sft-corpus.yaml` — FEAT-1826 consumer that will bind `with:` keys validated by this block

### Similar Patterns
- `scripts/little_loops/loops/rn-remediate.yaml:31-53` — best reference: `parameters:` block with `required: false` + defaults matching `context:` values (identical pattern to this change)
- `scripts/little_loops/loops/recursive-refine.yaml:19-23` — `parameters:` with `required: true` for sub-loop handoff
- `scripts/little_loops/loops/oracles/research-coverage.yaml:15-31` — `parameters:` with mixed types (string, boolean) and matching context defaults

### Tests
- `scripts/tests/test_fsm_executor.py:6318` — add test for load-time `with:` key validation (misspelled key → `ValidationError`); the existing `test_with_interpolation_from_parent_context` tests *runtime* output, while the new test must exercise the *load-time* error path in `_validate_with_bindings()`
- `scripts/tests/test_fsm_validation.py:479-573` — existing `TestParameterValidation` and `TestWithBindingValidation` classes; no changes needed
- `scripts/tests/test_builtin_loops.py:25-51` — `test_all_validate_as_valid_fsm` auto-validates `dataset-curation.yaml` after modification (covers Step 2 regression check)
- Existing `dataset-curation` tests — verify no regression

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue --auto --full-rewrite` — based on codebase analysis:_

- **Validation flow**: `_validate_with_bindings()` in `validation.py:328` silently skips children without `parameters:` (line 356: `if not child_fsm.parameters: continue`). Adding `parameters:` activates three validations: unknown `with:` keys (line 362), missing required params (line 375), and static type mismatches (line 388). The runtime executor (`executor.py:530-545`) separately applies defaults and enforces required params at execution time — adding `parameters:` enables both stages.

- **Best reference pattern**: `rn-remediate.yaml:31-53` is the canonical reference — it declares `parameters:` with `required: false`, `default` values matching its `context:` block, and `description` for each parameter. `scan-and-implement.yaml` (previously cited) does NOT have a `parameters:` block; it only uses `with:` as a *caller*. Seven other loops have `parameters:` blocks: `recursive-refine.yaml`, `rn-remediate.yaml`, `rn-decompose.yaml`, and four oracles (`enumerate-and-prove.yaml`, `generator-evaluator.yaml`, `research-coverage.yaml`, `implement-issue-chain.yaml`).

- **Parameter subset rationale**: The issue proposes `parameters:` for only 3 of 6 context keys (`data_dir`, `output_dir`, `schema_path`). The remaining 3 (`quality_threshold`, `min_per_category`, `adversarial_cap`) are intentionally excluded — they are internal tuning knobs, not cross-loop handoff values. FEAT-1826's `sft-corpus` only needs to bind the data I/O paths when handing off to `dataset-curation`. This is consistent with how other loops scope their `parameters:` blocks to cross-loop contract values only.

- **Auto-validation coverage**: `test_builtin_loops.py:TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` iterates all runnable loop YAMLs through `load_and_validate()` + `validate_fsm()`. After modification, this test automatically verifies `dataset-curation.yaml` adds no errors — no separate regression test needed for structural validity.

- **Test shape for Step 4**: Existing `test_with_interpolation_from_parent_context` (line 6318) tests the *runtime* path — it asserts child output matches an interpolated value. The new test must exercise the *load-time* error path: write a child YAML with `parameters:`, construct a parent with a misspelled `with:` key, call `load_and_validate()`, and assert the returned errors list contains a `ValidationError` about the unknown key. See `test_fsm_validation.py:479-573` for test patterns that call validation functions directly.

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
- `scripts/little_loops/fsm/schema.py:209` — `ParameterSpec` dataclass
- `scripts/little_loops/fsm/validation.py:328` — `_validate_with_bindings()` (load-time contract enforcement)
- `scripts/little_loops/fsm/executor.py:524` — `_execute_sub_loop()` (runtime default application and required-param check)
- `scripts/little_loops/loops/rn-remediate.yaml:31-53` — reference pattern for `parameters:` + `context:` with matching defaults

## Labels

`enhancement`, `loop`, `sft`

## Session Log
- `/ll:ready-issue` - 2026-06-04T20:37:39 - `b0fa08d8-9115-4291-b5b8-2275195a2199.jsonl`
- `/ll:refine-issue` - 2026-06-04T20:23:34 - `290d65e6-31fc-40b7-be73-cb30cfaf5b3c.jsonl`
- `/ll:format-issue` - 2026-06-04T20:10:22 - `d53c2aa2-0b92-419f-9a24-0dcb7fadf635.jsonl`
- `/ll:capture-issue` - 2026-06-04T20:01:37Z - `b0ca5e28-1c3f-4a31-b1d5-f67d60516393.jsonl`
- `/ll:confidence-check` - 2026-06-04T20:48:00Z - `75ed56a7-8537-4df3-a892-521e35659eed.jsonl`
- `/ll:manage-issue` - 2026-06-04T20:44:55Z - `<current-session>`

---
## Resolution

**Completed**: Added `parameters:` block to `dataset-curation.yaml` declaring `data_dir`, `output_dir`, `schema_path` with `required: false` and defaults matching the existing `context:` values. Added `test_load_and_validate_catches_misspelled_with_key` in `test_fsm_executor.py` to verify `_validate_with_bindings()` catches misspelled `with:` keys at load time. All 3212 tests pass (1 pre-existing unrelated failure), `ll-loop validate dataset-curation` exits 0.

### Changes Made
- `scripts/little_loops/loops/dataset-curation.yaml` — added `parameters:` block (lines 23-37)
- `scripts/tests/test_fsm_executor.py` — added `test_load_and_validate_catches_misspelled_with_key` + imports (`pytest`, `load_and_validate`)

### Verification
- `ll-loop validate dataset-curation` → valid, exit 0
- `python -m pytest scripts/tests/` → 3212 passed, 1 pre-existing failure (unrelated)
- `ruff check scripts/tests/test_fsm_executor.py` → all checks passed
- New test: `test_load_and_validate_catches_misspelled_with_key` → passes

---
## Status

**Done** | Created: 2026-06-04 | Priority: P4
