---
id: ENH-1873
title: "Wave 3c — Create `enumerate-and-prove` Oracle and Convert 2 Integration Loops"
type: ENH
priority: P3
parent: ENH-1776
depends_on: ENH-1775
size: Medium
---

# ENH-1873: Wave 3c — Create `enumerate-and-prove` Oracle and Convert 2 Integration Loops

## Summary

Extract the `parse_enumeration → flatten → prove` four-state chain duplicated across `adopt-third-party-api.yaml` and `integrate-sdk.yaml` into a new `oracles/enumerate-and-prove.yaml` oracle sub-loop, then convert both callers to delegate to it.

## Parent Issue

Decomposed from ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Current Behavior

`adopt-third-party-api.yaml` and `integrate-sdk.yaml` both contain nearly identical `parse_enumeration` (python3 heredoc), `flatten_targets`/`flatten_surfaces` (python3 comma-join), and delegation to `ready-to-implement-gate` — four states duplicated verbatim across both loops. A third variant exists in `assumption-firewall.yaml` (out of scope for this wave).

## Expected Behavior

A single `loops/oracles/enumerate-and-prove.yaml` oracle encapsulates the parse → flatten → prove chain. Both integration loops delegate to it via a single state with `with:` parameter bindings.

## Proposed Solution

### Implementation Steps

1. **Create `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`** — new oracle sub-loop:
   - `parameters:` block: `raw_enumeration` (string, required — the captured LLM output containing the `ENUMERATE_JSON:` line), `max_retries` (string, optional), `tag` (string, optional, default `ENUMERATE_JSON`)
   - States: `parse_enumeration` (fragment: `parse_tagged_json`, python3 heredoc scanning for `ENUMERATE_JSON:`, evaluate: `output_json .count gt 0`), `flatten` (action_type: shell, python3 comma-join of `data["targets"]`), `prove` (loop: `ready-to-implement-gate`, with: targets/max_retries), `done`, `failed`
   - Design note: `integrate-sdk.yaml` carries extra fields (`branch`, `requires_credentials`) in the JSON; the oracle's `flatten` state emits only comma-joined targets — extra fields are not consumed by `ready-to-implement-gate`
   - Reference structure: `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` (existing oracle with `parameters:` block and `max_iterations: 1`)

2. **Convert `scripts/little_loops/loops/adopt-third-party-api.yaml`** — replace `parse_enumeration` + `flatten_targets` + `prove` states with a single delegation state:
   - `loop: oracles/enumerate-and-prove`
   - `with: { raw_enumeration: "${captured.raw_enumeration.output}", max_retries: "2" }`
   - `on_success: build_playbook`
   - `on_failure/on_error: build_playbook_partial`

3. **Convert `scripts/little_loops/loops/integrate-sdk.yaml`** — replace `parse_enumeration` + `flatten_surfaces` + `prove` states with delegation state:
   - `loop: oracles/enumerate-and-prove`
   - `with: { raw_enumeration: "${captured.raw_enumeration.output}", max_retries: "${context.max_retries}" }`
   - `on_success: scaffold_integration`
   - `on_failure/on_error: diagnose_and_block`

4. **Update breaking tests in `scripts/tests/test_builtin_loops.py`**:
   - `TestAdoptThirdPartyApiLoop::test_prove_delegates_to_ready_to_implement_gate` — update to assert delegation to `oracles/enumerate-and-prove` instead of `ready-to-implement-gate`
   - `TestIntegrateSdkLoop::test_prove_delegates_to_ready_to_implement_gate` — same
   - `TestIntegrateSdkLoop::test_scan_branches_to_both_enumerate_states` — update routing target assertions if state name changes

5. **Add `TestEnumerateAndProveOracle`** class to `scripts/tests/test_builtin_loops.py`:
   - Required states (`parse_enumeration`, `flatten`, `prove`, `done`, `failed`)
   - `parameters` block has `raw_enumeration` as required
   - `done` is terminal
   - Oracle loads with `is_runnable_loop()`

6. **Add `test_enumerate_and_prove_is_runnable`** to `scripts/tests/test_doc_counts.py` following the `test_generator_evaluator_is_runnable` pattern.

7. Run `ll-loop validate` on `enumerate-and-prove.yaml`, `adopt-third-party-api.yaml`, `integrate-sdk.yaml`

8. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_doc_counts.py -v --tb=short`

## Integration Map

### Files to Create
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — new oracle sub-loop

### Files to Modify
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — replace 3 states with delegation to oracle
- `scripts/little_loops/loops/integrate-sdk.yaml` — replace 3 states with delegation to oracle
- `scripts/tests/test_builtin_loops.py` — update 3 breaking tests; add `TestEnumerateAndProveOracle` class
- `scripts/tests/test_doc_counts.py` — add `test_enumerate_and_prove_is_runnable`

### Dependent Files (read-only)
- `scripts/little_loops/fsm/validation.py:_validate_with_bindings()` — validates `with:` param bindings for sub-loop invocations; no changes needed
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — reference structure for oracle design
- `scripts/little_loops/loops/assumption-firewall.yaml` — third enumerate-prove variant; out of scope for this wave but demonstrates pattern generalizability

### Similar Patterns
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — existing oracle sub-loop with `parameters:` and `max_iterations: 1`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — oracle with `with:` delegation pattern

## Success Metrics

- `enumerate-and-prove.yaml` oracle passes `ll-loop validate`
- Both integration loops pass `ll-loop validate` after conversion
- `TestEnumerateAndProveOracle` passes
- `test_enumerate_and_prove_is_runnable` passes
- 3 previously-breaking tests updated and passing

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
