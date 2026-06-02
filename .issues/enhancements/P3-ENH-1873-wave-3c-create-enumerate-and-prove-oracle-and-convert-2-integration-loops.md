---
id: ENH-1873
title: "Wave 3c \u2014 Create `enumerate-and-prove` Oracle and Convert 2 Integration\
  \ Loops"
type: ENH
priority: P3
status: done
completed_at: 2026-06-02 05:45:46+00:00
parent: ENH-1776
depends_on: ENH-1775
size: Medium
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1873: Wave 3c — Create `enumerate-and-prove` Oracle and Convert 2 Integration Loops

## Summary

Extract the `parse_enumeration → flatten → prove` four-state chain duplicated across `adopt-third-party-api.yaml` and `integrate-sdk.yaml` into a new `oracles/enumerate-and-prove.yaml` oracle sub-loop, then convert both callers to delegate to it.

## Parent Issue

Decomposed from ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Current Behavior

`adopt-third-party-api.yaml` and `integrate-sdk.yaml` both contain nearly identical `parse_enumeration` (python3 heredoc), `flatten_targets`/`flatten_surfaces` (python3 comma-join), and delegation to `ready-to-implement-gate` — four states duplicated verbatim across both loops. A third variant exists in `assumption-firewall.yaml` (out of scope for this wave).

### Differences Between the Two `parse_enumeration` States

The two existing states are not fully identical:

| Aspect | `adopt-third-party-api` | `integrate-sdk` |
|---|---|---|
| Extra JSON fields | `domain` (derived from `urlparse(${context.input})`) | `branch`, `requires_credentials` |
| Fallback domain derivation | yes (via `urlparse`) | no |
| Flatten state name | `flatten_targets` | `flatten_surfaces` |
| `parse_enumeration` `on_no` | `failed` | `diagnose_and_block` |
| Flatten `on_error` | `failed` | `diagnose_and_block` |
| `prove` `max_retries` binding | `"2"` (literal) | `"${context.max_retries}"` (from context) |
| `prove` `on_success` | `build_playbook` | `scaffold_integration` |
| `prove` `on_failure`/`on_error` | `build_playbook_partial` | `diagnose_and_block` |

The oracle need only emit `targets`, `count`, and `rationale` — the extra fields (`domain`, `branch`, `requires_credentials`) are caller-specific and are not consumed by `ready-to-implement-gate`.

## Expected Behavior

A single `loops/oracles/enumerate-and-prove.yaml` oracle encapsulates the parse → flatten → prove chain. Both integration loops delegate to it via a single state with `with:` parameter bindings.

## Proposed Solution

### Implementation Steps

1. **Create `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`** — new oracle sub-loop:
   - `parameters:` block: `raw_enumeration` (string, required — the captured LLM output containing the `ENUMERATE_JSON:` line), `max_retries` (string, optional), `tag` (string, optional, default `ENUMERATE_JSON`)
   - States: `parse_enumeration` (fragment: `parse_tagged_json`, python3 heredoc scanning for `ENUMERATE_JSON:`, evaluate: `output_json .count gt 0`), `flatten` (action_type: shell, python3 comma-join of `data["targets"]`), `prove` (loop: `ready-to-implement-gate`, with: targets/max_retries), `done`, `failed`
   - Design note: `integrate-sdk.yaml` carries extra fields (`branch`, `requires_credentials`) in the JSON; the oracle's `flatten` state emits only comma-joined targets — extra fields are not consumed by `ready-to-implement-gate`

   **Critical `parse_tagged_json` constraint**: The `parse_tagged_json` fragment (`lib/common.yaml`) provides ONLY `action_type: shell` — it deliberately provides no default `action:` because nested interpolation (`${captured.${context.capture_var}.output}`) raises `InterpolationError`. The oracle's `parse_enumeration` state MUST supply an inline `action:` that references `${context.raw_enumeration}` directly (after `with:` binding, the `raw_enumeration` parameter lands in `context`). Callers must also supply: `capture`, `evaluate`, `on_yes`, `on_no`.

   **Correct reference structure**: Use `scripts/little_loops/loops/oracles/generator-evaluator.yaml` as the reference for the `parameters:` block and `with:` delegation pattern — NOT `oracle-capture-issue.yaml`, which uses `context_passthrough: true` and has no `parameters:` block. The `generator-evaluator` oracle declares `parameters:` with `type`, `required`, `description`, sets optional defaults in `context:`, and uses `on_handoff: spawn`.

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

4. **Update breaking tests in `scripts/tests/test_builtin_loops.py`** (see Integration Map for exact line numbers):
   - `TestAdoptThirdPartyApiLoop::test_prove_delegates_to_ready_to_implement_gate` (line 4897) — update to assert delegation to `oracles/enumerate-and-prove` instead of `ready-to-implement-gate`
   - `TestAdoptThirdPartyApiLoop::test_prove_with_contains_targets_and_max_retries` (line 4904) — asserts `data["states"]["prove"]["with"]` contains `targets`/`max_retries`; `prove` state is removed, update to check the new delegation state's `with:` bindings
   - `TestIntegrateSdkLoop::test_prove_delegates_to_ready_to_implement_gate` (line 4942) — update to assert delegation to `oracles/enumerate-and-prove`
   - `TestIntegrateSdkLoop::test_prove_with_contains_targets_and_max_retries` (line 4949) — same as above for `integrate-sdk`
   - `TestIntegrateSdkLoop::test_prove_failure_routes_to_non_retry_state` (line 4967) — asserts `data["states"]["prove"]["on_failure"] == "diagnose_and_block"`; `prove` state removed, update to assert `on_failure` on the new oracle delegation state
   - `TestIntegrateSdkLoop::test_scan_branches_to_both_enumerate_states` — this test checks `scan_existing_usage.on_yes == "enumerate_from_code"` and `scan_existing_usage.on_no == "enumerate_from_docs"`, which are upstream of the `parse_enumeration` state and are NOT changing; this test needs NO update

5. **Add `TestEnumerateAndProveOracle`** class to `scripts/tests/test_builtin_loops.py` following the `TestGeneratorEvaluatorOracle` pattern (line 5166):
   - `LOOP_FILE = BUILTIN_LOOPS_DIR / "oracles/enumerate-and-prove.yaml"`
   - Test required states (`parse_enumeration`, `flatten`, `prove`, `done`, `failed`)
   - Test that `parameters` block has `raw_enumeration` as required
   - Test that `parse_enumeration` uses `fragment: parse_tagged_json`
   - Test that `prove` delegates to `ready-to-implement-gate` (not to `oracles/enumerate-and-prove` — the oracle calls the gate, not itself)
   - Test that `done` is terminal

6. **Add `test_enumerate_and_prove_is_runnable`** to `scripts/tests/test_doc_counts.py` in class `TestIsRunnableLoop`, following the `test_generator_evaluator_is_runnable` pattern (line 137):
   ```python
   def test_enumerate_and_prove_is_runnable(self) -> None:
       from pathlib import Path as _Path
       oracle = (
           _Path(__file__).resolve().parents[1]
           / "little_loops" / "loops" / "oracles" / "enumerate-and-prove.yaml"
       )
       if oracle.exists():
           assert is_runnable_loop(oracle) is True
   ```

7. **Update `scripts/little_loops/loops/README.md`** — add an entry for the new oracle sub-loop under the oracles section, following the existing `generator-evaluator` and `oracle-capture-issue` entries.

8. **Update `README.md` (root, line 163)** — change `**66 FSM loops**` to `**67 FSM loops**`; adding the oracle increases the count discovered by `verify_documentation()` via `loops_dir.rglob("*.yaml")` filtered by `is_runnable_loop()`; `ll-verify-docs` will fail if this is not updated

9. Run `ll-loop validate` on `enumerate-and-prove.yaml`, `adopt-third-party-api.yaml`, `integrate-sdk.yaml`

10. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_doc_counts.py -v --tb=short`

11. Run `ll-verify-docs` to confirm the loop count in `README.md` matches the actual filesystem count

## Integration Map

### Files to Create
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — new oracle sub-loop

### Files to Modify
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — replace 3 states with delegation to oracle
- `scripts/little_loops/loops/integrate-sdk.yaml` — replace 3 states with delegation to oracle
- `scripts/tests/test_builtin_loops.py` — update 5 breaking tests (lines ~4897, ~4904, ~4942, ~4949, ~4967); add `TestEnumerateAndProveOracle` class following `TestGeneratorEvaluatorOracle` (line 5166)
- `scripts/tests/test_doc_counts.py` — add `test_enumerate_and_prove_is_runnable` following `test_generator_evaluator_is_runnable` (line 137)
- `scripts/little_loops/loops/README.md` — add oracle entry for `enumerate-and-prove`
- `README.md` — update loop count from `66` to `67` (line 163: `**66 FSM loops**` → `**67 FSM loops**`); required for `ll-verify-docs` to pass

### Dependent Files (read-only)
- `scripts/little_loops/fsm/validation.py:_validate_with_bindings()` — validates `with:` param bindings for sub-loop invocations; no changes needed
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — **correct** reference structure for oracle with `parameters:` block and `with:` binding (use this, not `oracle-capture-issue`)
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — alternate oracle shape (uses `context_passthrough: true`, no `parameters:` block); reference for `max_iterations: 1` and `on_handoff: spawn` fields
- `scripts/little_loops/loops/lib/common.yaml` — contains `parse_tagged_json` fragment (provides only `action_type: shell`; callers must supply their own `action:`)
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — the sub-loop the oracle delegates to; no `parameters:` block, accepts input via `context:` merging from `with:` bindings
- `scripts/little_loops/loops/assumption-firewall.yaml` — third enumerate-prove variant; out of scope for this wave but demonstrates pattern generalizability
- `scripts/little_loops/fsm/__init__.py` — exports `is_runnable_loop()` used in `test_doc_counts.py`

### Similar Patterns
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — oracle with `parameters:` block; required/optional params with defaults in `context:`; `on_handoff: spawn`
- `scripts/little_loops/loops/assumption-firewall.yaml:run_gate` — `loop: ready-to-implement-gate` with `with: {targets: ..., max_retries: "2"}`, `on_success/on_failure` routing

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — 5 tests to update when `prove` state is removed from both loops:
  - `TestAdoptThirdPartyApiLoop::test_prove_delegates_to_ready_to_implement_gate` (line 4897)
  - `TestAdoptThirdPartyApiLoop::test_prove_with_contains_targets_and_max_retries` (line 4904) — asserts on `prove.with`; will break
  - `TestIntegrateSdkLoop::test_prove_delegates_to_ready_to_implement_gate` (line 4942)
  - `TestIntegrateSdkLoop::test_prove_with_contains_targets_and_max_retries` (line 4949) — asserts on `prove.with`; will break
  - `TestIntegrateSdkLoop::test_prove_failure_routes_to_non_retry_state` (line 4967) — asserts `prove.on_failure == "diagnose_and_block"`; will break
- `scripts/tests/test_builtin_loops.py` — `TestGeneratorEvaluatorOracle` (line 5166) — reference pattern for new `TestEnumerateAndProveOracle`
- `scripts/tests/test_doc_counts.py` — `TestIsRunnableLoop::test_generator_evaluator_is_runnable` (line 137) — reference pattern for new `test_enumerate_and_prove_is_runnable`

## Success Metrics

- `enumerate-and-prove.yaml` oracle passes `ll-loop validate`
- Both integration loops pass `ll-loop validate` after conversion
- `TestEnumerateAndProveOracle` passes
- `test_enumerate_and_prove_is_runnable` passes
- 2 previously-breaking tests updated and passing (`test_prove_delegates_*` in both loop test classes)
- `test_scan_branches_to_both_enumerate_states` passes unchanged (upstream routing unaffected)

## Impact

- **Priority**: P3 - Eliminates 3-state duplication across 2 integration loops; part of Wave 3 harness centralization
- **Effort**: Medium - New oracle YAML, 2 caller rewrites, 5 breaking test updates, 1 new test class, doc updates
- **Risk**: Low - Oracle extraction preserves existing behavior; `parse_tagged_json` constraint is well-documented; test suite validates the oracle and both callers
- **Breaking Change**: No (5 tests updated in same PR to reflect delegation to oracle)

## Scope Boundaries

**In scope**: Creating `oracles/enumerate-and-prove.yaml`; converting `adopt-third-party-api.yaml` and `integrate-sdk.yaml` to delegate to the oracle; updating 5 breaking tests; adding `TestEnumerateAndProveOracle`; adding `test_enumerate_and_prove_is_runnable`; updating `loops/README.md` and root `README.md` loop count.

**Out of scope**: The third `parse_enumeration` variant in `assumption-firewall.yaml` (explicitly deferred). No behavioral changes to `ready-to-implement-gate`, `parse_tagged_json`, or any other oracle sub-loops.

## Labels

`loops`, `harness`, `enhancements`, `wave-3`, `refactor`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-02T05:39:39 - `2975b682-7b2b-4fc3-a150-6aa1cca6a4f8.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `cf7d46f8-0693-42f7-bbf2-eb4e79d868ba.jsonl`
- `/ll:wire-issue` - 2026-06-02T05:33:42 - `d7a0523a-92e1-4f82-a770-b521a62d2a74.jsonl`
- `/ll:refine-issue` - 2026-06-02T05:28:23 - `f4543fa6-a57e-4d9c-8505-1d077507a549.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:refine-issue` - 2026-06-02T00:00:00Z - `auto`
