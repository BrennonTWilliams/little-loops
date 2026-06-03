---
id: ENH-1741
title: 'Refactor `ready-to-implement-gate` to use `type: learning` states'
type: ENH
priority: P4
status: open
captured_at: '2026-05-27T18:08:06Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- FEAT-1695
- FEAT-1283
decision_needed: false
confidence_score: 96
outcome_confidence: 70
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 18
---

# ENH-1741: Refactor `ready-to-implement-gate` to use `type: learning` states

## Summary

Replace the five hand-rolled states in `ready-to-implement-gate` (`check_next`, `branch_on_verdict`, `explore`, `advance_queue`, plus their routing) with one or more `type: learning` FSM states, reducing the loop's state count and creating the first real built-in example of the `type: learning` primitive (FEAT-1283). The `type: learning` state type is documented and implemented but has zero living built-in examples — this loop is the natural home for it.

## Current Behavior

`ready-to-implement-gate` (FEAT-1695) hand-rolls the check-then-explore pattern across five states:

1. `parse_targets` — splits `context.targets` CSV into a queue.
2. `check_next` — calls `ll-learning-tests check` on the head of the queue; classifies as `proven`, `refuted`, or `needs_explore`.
3. `branch_on_verdict` — routes on `refuted` vs. `needs_explore`.
4. `explore` — calls `ll-action invoke explore-api` up to `max_retries` times; routes on `RESULT=proven` vs. fallthrough.
5. `advance_queue` — pops the head, routes back to `check_next` or to `done`.

This is exactly the behavior the `type: learning` FSM state was designed to provide: iterate targets, pass proven ones through, trigger `/ll:explore-api` for missing/stale, block on refuted. The implementation duplicates executor-level logic that `type: learning` already encapsulates.

## Expected Behavior

The loop's external contract is unchanged:

- Input: `context.targets` (comma-separated target list), `context.max_retries`
- Terminal states: `done` (all proven), `blocked` (any refuted or retries exhausted)
- Sub-loop call sites in `assumption-firewall`, `adopt-third-party-api`, and `integrate-sdk` continue to work without modification

Internally, the five probe-and-advance states collapse into one or two `type: learning` states:

```yaml
prove:
  type: learning
  learning:
    targets: <dynamic — see note>
    max_retries: "${context.max_retries}"
  on_yes: done
  on_blocked: blocked
```

**Dynamic targets constraint:** `type: learning` currently requires static targets in YAML. If the executor supports `learning.targets` as a runtime-interpolated list (from `context.targets` CSV), the refactor is a direct replacement. If not, a `parse_targets` shell state must expand the CSV into a YAML-compatible list before the `type: learning` state is entered, and the `type: learning` state reads from the captured output. This issue should verify which form the executor supports before committing to an implementation path.

## Motivation

- **`type: learning` has no built-in exemplar.** The primitive is documented in LOOPS_GUIDE.md with a synthetic code example, but no built-in loop uses it. `ready-to-implement-gate` is the canonical home — it implements exactly the behavior the primitive abstracts.
- **Reduces state count and maintenance surface.** Five states → one or two. The hand-rolled retry loop and `branch_on_verdict` routing are replaced by executor-managed behavior.
- **Signals to users how to use `type: learning`.** A developer reading `ready-to-implement-gate` YAML after this refactor will see the pattern they should copy when building their own project loops that gate on learning tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — primary target; states `parse_targets`, `check_next`, `branch_on_verdict`, `explore`, `advance_queue` to be replaced
- `scripts/tests/test_builtin_loops.py` — class `TestReadyToImplementGateLoop` (line 4659): `test_explore_uses_ll_action_invoke` and `test_parse_targets_evaluate_is_output_json_on_remaining` must be replaced with `type: learning` assertions; `test_done_is_terminal` and `test_blocked_is_terminal` are unchanged

### Key Files to Read Before Implementing
- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state()` at line 614: iterates `state.learning.targets` directly; no CSV splitting or interpolation occurs here
- `scripts/little_loops/fsm/schema.py` — `class LearningConfig`: `targets: list[str]`, `max_retries: int = 2`; `from_dict()` runs at YAML parse time (not at execution time)
- `scripts/tests/fixtures/fsm/learning-state-loop.yaml` — only existing `type: learning` YAML fixture; canonical schema reference for the state format

### Sub-Loop Callers (Must Not Break)
- `scripts/little_loops/loops/assumption-firewall.yaml` — state `run_gate`: invokes `ready-to-implement-gate` with `targets: "${captured.targets.output}"` (comma-separated string)
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml` — state `prove`: invokes `ready-to-implement-gate` with `targets: "${captured.targets.output}"` (comma-separated string)
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — calls via `oracles/enumerate-and-prove` (indirect, no direct changes needed)
- `scripts/little_loops/loops/integrate-sdk.yaml` — calls via `oracles/enumerate-and-prove` (indirect, no direct changes needed)

### Tests Exercising the Loop
- `scripts/tests/test_builtin_loops.py:TestReadyToImplementGateLoop` (line 4659) — structural assertions; 2 of 4 tests will need rewriting after the refactor
- `scripts/tests/test_learning_state.py` — executor-level unit tests for `type: learning` dispatch; no changes needed
- `scripts/tests/test_fsm_executor.py` — FSM executor integration tests; no changes needed if Option A extends `LearningConfig` cleanly

### Documentation
- `docs/guides/LOOPS_GUIDE.md` (~line 2725) — `type: learning` schema documentation with synthetic example; no changes required (the refactored loop will become the first real built-in example)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py` — `_validate_state_action()`: current guard `if not state.learning.targets` will reject the new `targets_csv`-only YAML (raises "type=learning requires non-empty 'learning.targets'"); must accept `targets or targets_csv` as satisfying the requirement — blocks `ll-loop validate ready-to-implement-gate` if unpatched [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — `test_state_config_learning_round_trip` and `test_state_config_learning_default_max_retries`: test `LearningConfig.from_dict()` / `to_dict()` round-trips; need additional cases for `targets_csv` population and round-trip (new field absent → `None`; present → preserved) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestReadyToImplementGateLoop::test_explore_uses_ll_action_invoke` — asserts `states.explore.action`; will break when `explore` state is removed — replace with `test_prove_state_has_type_learning` asserting `states.prove.type == "learning"` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestReadyToImplementGateLoop::test_parse_targets_evaluate_is_output_json_on_remaining` — asserts `states.parse_targets`; will break when `parse_targets` state is removed — replace with `test_prove_state_has_targets_csv_with_context_ref` asserting `states.prove.learning.targets_csv` contains `"${context.targets}"` [Agent 3 finding]
- New class in `scripts/tests/test_learning_state.py` — follow `TestLearningStateMultipleTargets` pattern; add tests for: `targets_csv` set → executor interpolates + splits; whitespace stripped; runtime-resolved list used in `learning_complete` event payload [Agent 3 finding]
- New fixture `scripts/tests/fixtures/fsm/learning-state-csv-loop.yaml` — `type: learning` state using `targets_csv: "target-a, target-b"` to enable fixture-based executor integration tests for the CSV path [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — no tests currently exercise `_validate_state_action` for the `type: learning` branch (confirmed by Agent 3: zero learning-specific guards are tested in this file); add one test case that verifies the updated guard accepts a `targets_csv`-only learning state without emitting a validation ERROR, and one that verifies a state with neither `targets` nor `targets_csv` still triggers the error [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `learning` object block at `states.*.learning`: (1) add `targets_csv` to `properties`, (2) relax `"required": ["targets"]` to allow either `targets` or `targets_csv`, (3) add `targets_csv` to the `properties` scope so `"additionalProperties": false` doesn't reject it — IDEs and YAML linters would flag the new YAML as invalid without this update [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### LearningConfig` section: add `targets_csv: str | None = None` to the Python dataclass snippet; update prose "The handler iterates `targets` in order" to describe the `targets_csv` resolution path [Agent 2 finding]
- `docs/guides/LEARNING_TESTS_GUIDE.md` — "Using Learning Tests in Loops" section (~line 158): update sentence "the executor iterates `learning.targets`" to cover `targets_csv` CSV path introduced by this issue [Agent 2 finding]

## Proposed Solution

Both options preserve the external contract (same input context variables `targets`/`max_retries`, same terminal state names `done`/`blocked`). They differ on whether to extend the executor.

### Option A: Extend Executor to Support Runtime `targets_csv` and `max_retries_expr`

> **Selected:** Option A — `interpolate()` is already in-scope in `_execute_learning_state()`, the `str | None` runtime-resolution pattern has three precedents in `evaluators.py`, and FEAT-1283/FEAT-1794/FEAT-1451 all co-landed similarly-sized executor extensions inline rather than deferring. Extended to also include `max_retries_expr` after tracing the `integrate-sdk → enumerate-and-prove → ready-to-implement-gate` call chain and confirming `context.max_retries` is a user-facing knob in `integrate-sdk` (see Decision Rationale below).

Add `targets_csv` and `max_retries_expr` keys to `LearningConfig`, both resolved at runtime inside `_execute_learning_state()`. Callers pass the existing CSV string and max-retries value unchanged. The refactored loop becomes a 3-state YAML (well below the ≤ 4 target):

```yaml
states:
  prove:
    type: learning
    learning:
      targets_csv: "${context.targets}"       # resolved + CSV-split at runtime
      max_retries_expr: "${context.max_retries}"  # resolved to int at runtime
    on_yes: done
    on_blocked: blocked
  done:
    terminal: true
  blocked:
    terminal: true
```

Required changes (3 files):
- `scripts/little_loops/fsm/schema.py:LearningConfig` — add `targets_csv: str | None = None` and `max_retries_expr: str | None = None`; `from_dict()` populates each when the key is present
- `scripts/little_loops/fsm/executor.py:_execute_learning_state()` — if `targets_csv` is set, call `interpolate(targets_csv, ctx)` and split on `","` before iterating; if `max_retries_expr` is set, resolve via `interpolate()` and `int()`-cast before using as the retry limit (fallback: `state.learning.max_retries`, default 2)
- `scripts/tests/test_learning_state.py` — add test cases for the `targets_csv` and `max_retries_expr` paths (follow `TestLearningStateMultipleTargets` pattern)

Trade-off: Technically extends `type: learning` executor capabilities, which the current Scope Boundaries call out of scope. However the change is minimal and contained to 3 files. The Scope Boundaries should be updated to allow it.

### Option B: Create Prerequisite Issue and Defer

Document the finding that `type: learning` requires static YAML targets at parse time (no runtime interpolation), create a prerequisite issue to add the `targets_csv` (or equivalent) executor extension, and block ENH-1741 on that issue.

This keeps ENH-1741 scoped strictly to the YAML refactor and avoids any executor changes here. The cost is one additional issue and a sequencing dependency before this can land.

Trade-off: Cleaner scope separation, but delays the refactor and creates a two-issue chain for what is ultimately a small end-to-end change.

**Codebase context**: The `_execute_learning_state()` path already calls `self._run_action()` (which performs interpolation on action templates). Adding CSV resolution for `targets_csv` is ~5 lines and follows the same interpolation pattern already used elsewhere in the executor.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Option A — Extend Executor to Support Runtime `targets_csv`

**Reasoning**: `interpolate()` is already imported and called within `_execute_learning_state()`, and the `str | None` config-field-with-runtime-resolution pattern is established three times in `evaluators.py` and once in `EvaluateConfig`. Three prior FSM executor dispatch extensions (FEAT-1283, FEAT-1794, FEAT-1451) all chose to co-land ~5-line inline changes rather than create prerequisite issues; Option B conflicts with this pattern and risks permanent orphaning of a P4 item in a backlog already holding 50+ `blocked_by:` chains. All nine file touchpoints are mechanical 1–4-line edits with clear codebase templates.

**`max_retries_expr` addition**: Tracing the `integrate-sdk → enumerate-and-prove → ready-to-implement-gate` call chain confirmed that `context.max_retries` is a documented user-facing knob in `integrate-sdk` (`max_retries: "2"  # Per-surface explore-api retries in ready-to-implement-gate`). Hardcoding `max_retries: 2` in the refactored loop would silently ignore user-supplied values — the loop would block earlier than requested with no error. `max_retries_expr: str | None = None` is added following the identical `str | None` pattern as `targets_csv`; both callers today pass the default `"2"`, so no behavior change for existing invocations.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (extend executor with `targets_csv`) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (prerequisite issue + defer) | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Option A**: `interpolate()` already imported and called at executor.py:687; `EvaluateConfig.tolerance: str | None` is a direct structural precedent; FEAT-1283/FEAT-1794/FEAT-1451 all co-landed inline executor dispatch extensions; `TestLearningStateMultipleTargets` is the exact test template
- **Option B**: FEAT-1695 deliberately documented the parse-time constraint as an architectural choice but explicitly anticipated a future enhancement that "could collapse this loop into a thin wrapper" — ENH-1741 is that enhancement; zero existing built-in loops use `type: learning`, so no other callers benefit from further deferral

## Investigation Findings

All three open questions from the original issue have been answered against the current codebase:

**Q1: Does `learning.targets` support runtime interpolation (e.g., `"${context.targets}"`)? → No.**
`LearningConfig.from_dict()` in `scripts/little_loops/fsm/schema.py` stores `targets: list[str]` at YAML parse time. `_execute_learning_state()` in `scripts/little_loops/fsm/executor.py:614` iterates `state.learning.targets` directly — neither `interpolate()` nor `_interpolate_list()` is called on the list before iteration. A literal `"${context.targets}"` in the YAML list would be passed to `check_learning_test()` verbatim.

**Q2: Does the executor support reading targets from a prior captured shell output? → No.**
`LearningConfig.targets` is populated once at YAML parse time by `from_dict()`. There is no `targets_from_capture` or equivalent key in `LearningConfig`. Once the YAML is loaded, the list is fixed for the lifetime of the executor run.

**Q3: Minimum shim to bridge a CSV string into `type: learning`? → Executor extension required.**
The only viable path is to extend `LearningConfig` with a `targets_csv` field resolved at runtime (Option A above). This is ~5 lines in the executor and 1 field in the dataclass. No alternative "parse_targets + type: learning" approach works: even with a preceding shell state that expands the CSV, the `type: learning` state can only read from its static `learning.targets` list.

## Implementation Steps

1. Read `scripts/little_loops/loops/ready-to-implement-gate.yaml` and `scripts/little_loops/fsm/executor.py:_execute_learning_state` (line 614) to understand the current implementation and `type: learning` dispatch.
2. Extend `LearningConfig` in `scripts/little_loops/fsm/schema.py` with `targets_csv: str | None = None` and `max_retries_expr: str | None = None`; update `_execute_learning_state()` in `scripts/little_loops/fsm/executor.py:614` to resolve and split `targets_csv`, and to resolve and `int()`-cast `max_retries_expr` when set (falling back to `state.learning.max_retries`, default 2).
3. Draft the refactored `ready-to-implement-gate.yaml` — a 3-state YAML (`prove`, `done`, `blocked`) using `targets_csv` and `max_retries_expr`; see the Proposed Solution section for the exact schema.
4. Run `ll-loop validate ready-to-implement-gate` until no ERRORs.
5. Run `scripts/tests/test_builtin_loops.py::TestReadyToImplementGateLoop` — replace `test_explore_uses_ll_action_invoke` and `test_parse_targets_evaluate_is_output_json_on_remaining` with assertions checking `prove.type == "learning"` and `prove.learning.max_retries_expr == "${context.max_retries}"`; `test_done_is_terminal` and `test_blocked_is_terminal` are unchanged.
6. Run `scripts/tests/test_learning_state.py` — add `targets_csv` and `max_retries_expr` path tests following `TestLearningStateMultipleTargets` (line 271); also add `LearningConfig` serialization round-trip cases to `TestLearningConfigSerialization` (line 346, same file) for `from_dict({"targets_csv": "a,b"})` and `from_dict({"targets_csv": "a,b", "max_retries_expr": "3"})` scenarios.
7. Manually verify that `assumption-firewall` and `oracles/enumerate-and-prove` sub-loop invocations still route correctly (both pass `targets` as a CSV string; verify the new executor path splits it correctly).
8. Add a one-line comment to the loop YAML noting it is the canonical `type: learning` built-in example.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/little_loops/fsm/validation.py:_validate_state_action` — change `if not state.learning.targets` guard to `if not state.learning.targets and not state.learning.targets_csv` so a `targets_csv`-only YAML passes validation (required for acceptance criterion `ll-loop validate ready-to-implement-gate` to pass)
10. Update `scripts/little_loops/fsm/fsm-loop-schema.json` — in the `learning` object block: add `targets_csv` and `max_retries_expr` to `properties`, remove the top-level `"required": ["targets"]` clause, and replace it with an `anyOf` (following the `target` field's existing `oneOf` pattern at line ~488). Exact diff shape:
    ```json
    "properties": {
      "targets": { ... (unchanged) ... },
      "targets_csv": {
        "type": "string",
        "description": "Comma-separated target identifiers resolved at runtime via interpolate(). Alternative to 'targets' for loops that pass targets as a context CSV string (e.g., \"${context.targets}\")."
      },
      "max_retries": { ... (unchanged) ... },
      "max_retries_expr": {
        "type": "string",
        "description": "Runtime-interpolated retry limit. Resolved via interpolate() and int()-cast at execution time. Alternative to the static 'max_retries' integer for loops that pass max_retries as a context string (e.g., \"${context.max_retries}\")."
      }
    },
    "additionalProperties": false,
    "anyOf": [
      { "required": ["targets"] },
      { "required": ["targets_csv"] }
    ]
    ```
    Remove the existing `"required": ["targets"]` key at the same level (line ~420). Note: `max_retries_expr` needs no `anyOf` — `max_retries` retains its default of 2 and `max_retries_expr` is purely additive.
11. Fix event payload in `scripts/little_loops/fsm/executor.py:_execute_learning_state` (line ~685) — `learning_complete` event currently emits `list(state.learning.targets)`, which is `[]` when only `targets_csv` is used; capture the runtime-resolved targets list and emit that instead
12. Update `docs/reference/API.md:LearningConfig` section — add `targets_csv: str | None = None` and `max_retries_expr: str | None = None` to the Python snippet; update the "iterates targets in order" prose to describe CSV resolution and the `max_retries_expr` runtime-cast path
13. Update `docs/guides/LEARNING_TESTS_GUIDE.md` "Using Learning Tests in Loops" section — update the "executor iterates `learning.targets`" sentence to cover both `targets_csv` and `max_retries_expr` paths
14. Update `scripts/tests/test_fsm_schema.py` — add `targets_csv` and `max_retries_expr` round-trip cases to `TestStateConfig` (line 246; this is the class that contains `test_state_config_learning_round_trip` at line 2714 and `test_state_config_learning_default_max_retries` at line 2740): `from_dict({"targets_csv": "a,b"})` populates `targets_csv`; `from_dict({"targets_csv": "a,b", "max_retries_expr": "${context.max_retries}"})` populates both; `to_dict()` emits each when set, `None` when absent
15. Create `scripts/tests/fixtures/fsm/learning-state-csv-loop.yaml` — `type: learning` fixture using `targets_csv: "target-a, target-b"` and `max_retries_expr: "3"` for fixture-based executor integration tests of both runtime-resolution paths
16. Add test cases to `scripts/tests/test_fsm_validation.py` for the updated `_validate_state_action` learning-branch guard (step 9): one case asserting no ERROR when `targets_csv` is set and `targets` is empty; one case asserting ERROR when both `targets` and `targets_csv` are absent — this file has zero coverage for the learning validation path

## Acceptance Criteria

- `ll-loop validate ready-to-implement-gate` reports no ERRORs after refactor.
- External contract unchanged: same input context variables, same terminal state names (`done`, `blocked`).
- Sub-loop callers (`assumption-firewall`, `adopt-third-party-api`, `integrate-sdk`) pass existing tests unchanged.
- The `type: learning` state is used in the refactored YAML.
- State count in the refactored loop is ≤ 4 (down from 7 in the original).
- `TestReadyToImplementGateLoop` passes with updated state assertions.

## Scope Boundaries

- **In scope**: Replacing the five hand-rolled states (`check_next`, `branch_on_verdict`, `explore`, `advance_queue`, and `parse_targets`) in `ready-to-implement-gate.yaml` with one or two `type: learning` states; updating `TestReadyToImplementGateLoop` test assertions for the removed states
- **Out of scope**: Modifying sub-loop callers (`assumption-firewall`, `adopt-third-party-api`, `integrate-sdk`); changing the external contract (input context variables `targets`/`max_retries`, terminal state names `done`/`blocked`). Note: executor extension via `targets_csv` and `max_retries_expr` (originally out-of-scope) is now **in scope** per the Option A decision.

## Impact

- **Priority**: P4 - Low; existing behavior is correct, this is a maintenance refactor to reduce state count and provide a canonical `type: learning` exemplar
- **Effort**: Medium - Requires understanding `type: learning` dispatch in `fsm_executor.py`, modifying `ready-to-implement-gate.yaml`, and updating test state assertions
- **Risk**: Low - External contract is preserved; sub-loop callers require no modification
- **Breaking Change**: No

## Labels

`enh`, `loop`, `learning-tests`, `fsm`, `refactor`, `type-learning-exemplar`

---

**Open** | Created: 2026-05-27 | Priority: P4

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-03 (prior runs: 2026-06-03, 2026-06-02)_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- **Wide change surface across 4 subsystems (12 sites)**: YAML loop, 3 Python FSM modules, JSON schema, 3 test files, 1 new fixture, 2 docs — while each individual change is mechanical-to-local, coordinating 12 co-deliverables increases the chance of a missed file or integration gap. Use the 15-step implementation plan as a strict checklist.

## Session Log
- `/ll:wire-issue` - 2026-06-03T01:19:37 - `c248cfd7-99e1-4fef-ade0-380ad5d3bf4b.jsonl`
- `/ll:refine-issue` - 2026-06-03T01:13:07 - `53ca8bcc-0ece-4614-b419-050afc9172cb.jsonl`
- `/ll:confidence-check` - 2026-06-03T01:00:00Z - `5bcea9e3-d849-448e-883c-cb3ab8ad842a.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:49:25 - `316c0ad1-6dc5-41ee-86d4-d59514abec59.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:42:45Z - `255e0c2b-935a-474d-b91e-187cb706a7ac.jsonl`
- `/ll:decide-issue` - 2026-06-03T00:39:12 - `17557f51-d1e7-48ab-8c75-d04f0cc19f24.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00 - `5b268ae9-6748-479c-8957-26f628059249.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:30:40 - `54f65d4f-1a02-4225-91b7-4bda9970528f.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:21:36 - `0467dd38-23d6-4a11-9d93-1a10ed0c40c9.jsonl`
- `/ll:format-issue` - 2026-06-03T00:13:06 - `b7c7a708-237c-4305-a9e6-3f4df11cc3cb.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:34 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:17 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
