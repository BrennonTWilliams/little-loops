---
id: FEAT-1244
priority: P2
parent: FEAT-1119
decision_needed: false
size: Large
confidence_score: 100
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-04-23T16:12:30Z
---

# FEAT-1244: Benchmark Fragment — Core FSM Fragment & Scorer Registration

## Summary

Create `scripts/little_loops/loops/lib/benchmark.yaml` as a reusable FSM fragment that accepts a task directory and scorer command, runs the benchmark, and emits `benchmark_score` into `captured`. Implement scorer registration (Option A or B) and ship the fragment with Harbor-format fixtures and tests.

## Parent Issue

Decomposed from FEAT-1119: Benchmark Adapter Fragment (`lib/benchmark.yaml`)

## Current Behavior

No loop-level benchmark adapter exists. Each eval loop reinvents scoring via custom `run` blocks or inline `evaluator` calls. No shared "run a benchmark task directory and return a score" abstraction.

## Expected Behavior

- `scripts/little_loops/loops/lib/benchmark.yaml` loads and validates under existing loop schema checks
- Fragment exposes a `run_benchmark` fragment callable with `tasks_dir`, `scorer`, and optional `per_task_timeout`, `parallel`, `filter` inputs
- Fragment emits `benchmark_score`, `benchmark_per_task`, `benchmark_run_id` into `captured` (not `context`, which is read-only)
- `scorer: harbor_default` resolves to a first-party Harbor-format scorer (Option A or B)
- Unit + integration tests in `scripts/tests/test_benchmark_fragment.py` cover: task enumeration, scorer dispatch, aggregation reducers, missing-tasks-dir error
- All existing tests pass (no regressions)

## Use Case

An eval loop author wants to benchmark a set of Harbor-format task directories and route on the result (pass/fail). They import `lib/benchmark.yaml`, add a `run_benchmark` state that supplies their scorer command, and receive a `benchmark_score` in `captured` — no custom evaluator or shell scaffolding required. The same fragment can be reused across multiple eval loops (FEAT-1245, FEAT-1120) without duplicating scoring logic.

## Design Decision Required

**Resolve Option A vs B before implementation** (run `/ll:decide-issue FEAT-1244`):

**Option A: Add `harbor_scorer` as a core evaluator type**
> **Selected:** Option A — establishes `harbor_scorer` as a first-class evaluator type using the same four-file pattern followed by all 8 existing evaluators.
- Add `evaluate_harbor_scorer()` to `scripts/little_loops/fsm/evaluators.py` alongside other leaf evaluator functions
- Add `elif eval_type == "harbor_scorer":` branch in `evaluate()` at `evaluators.py:699`
- Add `"harbor_scorer"` entry to `EVALUATOR_REQUIRED_FIELDS` dict at `scripts/little_loops/fsm/validation.py:62-71`
- Add `"harbor_scorer"` to `EvaluateConfig.type` `Literal[...]` at `scripts/little_loops/fsm/schema.py:56-65`

**Option B: Register `harbor_default` via the contributed evaluator extension mechanism**
- Wire via `wire_extensions()` called from `scripts/little_loops/cli/loop/lifecycle.py:266`
- Extension callable matches `Evaluator` type alias at `scripts/little_loops/fsm/types.py:79-82`: `Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]`
- Dispatcher at `scripts/little_loops/fsm/executor.py:780-782` checks contributed evaluators before falling through to core `evaluate()`
- Avoids modifying `evaluators.py` only — `validation.py` and `schema.py` still require changes (see below)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option B validation gap (critical)**: Option B does NOT fully avoid modifying core files. `_validate_evaluator()` at `validation.py:116-125` checks `evaluate.type not in set(EVALUATOR_REQUIRED_FIELDS.keys())` and returns an ERROR-severity `ValidationError` for any unrecognized type — this happens at loop-load time, before `wire_extensions()` is called. A loop using `harbor_scorer` will be rejected unless `"harbor_scorer"` is added to `EVALUATOR_REQUIRED_FIELDS` in `validation.py`. Additionally, `schema.py`'s `EvaluateConfig.type: Literal[...]` (lines 56-65) would produce mypy errors without an update.

True differences between options:
| | Option A | Option B |
|---|---|---|
| `evaluators.py` | Modified (add leaf function + elif branch) | Not modified |
| `validation.py` | Modified (`EVALUATOR_REQUIRED_FIELDS`) | Modified (`EVALUATOR_REQUIRED_FIELDS`) |
| `schema.py` | Modified (`Literal` type) | Modified (`Literal` type) or mypy errors |
| `extension.py` mechanism | Not used | Used (new extension class implementing `EvaluatorProviderExtension`) |

**Fragment structure**: Each entry in `fragments:` in a lib YAML is a single-state construct (fields that get deep-merged into one consuming state). The `lib/common.yaml` pattern has 5 named fragments (`shell_exit`, `retry_counter`, etc.), each mapping to one state's fields. If `run_benchmark` is a single fragment, the "states: `load_tasks`, `run_tasks`, `aggregate`" noted in the summary likely refers to phases within one shell action script — not separate FSM states. Alternatively, `benchmark.yaml` could define three named fragments (`load_tasks`, `run_tasks`, `aggregate`) that consumers compose into three sequential states.

**Contributed evaluator callable signature**: The extension's `provided_evaluators()` must return `{"harbor_scorer": callable}` where callable matches `Evaluator = Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]`. The executor passes `(state.evaluate, eval_input_str, exit_code, ctx)` at `executor.py:781-785`.

**Harbor format**: No existing Harbor format definition found in the codebase. The fixture format must be defined as part of this issue's implementation. A minimal Harbor-format task directory likely needs at minimum a task specification file and an expected output; the exact structure is an UNKNOWN gap — the implementer must define it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-23.

**Selected**: Option A — Add `harbor_scorer` as a core evaluator type

**Reasoning**: Option A is the established pattern for all 8 existing evaluator types — the most recently added type (`mcp_result`) is a direct structural template requiring identical four-file changes. Option B's primary selling point (avoiding `evaluators.py` modification) does not materialize: `validation.py` and `schema.py` must be modified under either option since `_validate_evaluator()` runs before `wire_extensions()` at load time. Option B additionally requires a new `HarborScorerExtension` class with no production precedent, adding complexity with no compensating benefit.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (core evaluator type) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B (extension mechanism) | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- Option A: `evaluate_mcp_result` (`evaluators.py:468-525`) is a direct structural template; the elif dispatch chain at `evaluators.py:699-836` and `EVALUATOR_REQUIRED_FIELDS` at `validation.py:62-71` have absorbed 8 types using this exact pattern.
- Option B: `_validate_evaluator()` at `validation.py:116-125` rejects unknown types with ERROR severity at loop-load time — before `wire_extensions()` is called at `run.py:257` — meaning `validation.py` and `schema.py` still require modification, eliminating Option B's core advantage.

## Integration Map

### New Files
- `scripts/little_loops/loops/lib/benchmark.yaml` — Fragment library (`run_benchmark` fragment; model after `lib/common.yaml`)
- `scripts/tests/test_benchmark_fragment.py` — Unit + integration tests
- `scripts/tests/fixtures/harbor/` — 3-task Harbor-format fixture directory

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — If Option A: add `evaluate_harbor_scorer()` + `elif` branch at line 699
- `scripts/little_loops/fsm/schema.py` — If Option A: add `"harbor_scorer"` to `EvaluateConfig.type` Literal at lines 56-65
- `scripts/little_loops/fsm/validation.py` — If Option A: add `"harbor_scorer"` to `EVALUATOR_REQUIRED_FIELDS` at lines 62-71
- `scripts/little_loops/fsm/__init__.py:73-142` — If Option A: add `evaluate_harbor_scorer` to re-export list
- `scripts/little_loops/cli/loop/info.py:611-619` — If Option A: add `"harbor_scorer"` to `_EVALUATE_TYPE_DISPLAY` dict
- `scripts/tests/test_fsm_schema_fuzz.py:44-51` — If Option A: add `"harbor_scorer"` to hardcoded `valid_types` list
- `scripts/tests/test_fsm_schema.py` (`TestEvaluatorValidation`) — If Option A: add `test_harbor_scorer_requires_*` tests
- `scripts/little_loops/loops/README.md:117-121` — Add row for `lib/benchmark.yaml` in fragment library table
- `docs/guides/LOOPS_GUIDE.md:2045-2098` — Change "Two libraries" to "Three libraries"; add fragment table entry
- `docs/guides/AUDIT_REPORT.md:90` — Add `lib/benchmark.yaml` to fragment library enumeration
- `docs/reference/CLI.md:431-432` — Add `ll-loop fragments lib/benchmark.yaml` as a third example
- `docs/generalized-fsm-loop.md:455` — If Option A: add `harbor_scorer` subsection to Evaluator Types section
- `scripts/little_loops/extension.py:90-98,188-258` — If Option B: add `HarborScorerExtension` class implementing `EvaluatorProviderExtension` protocol; `provided_evaluators()` returns `{"harbor_scorer": evaluate_harbor_scorer_fn}` [Wiring pass: Option B registration file not previously listed]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:780-786,793` — checks `_contributed_evaluators` then calls `evaluate()`; auto-supports new types once dispatch is wired; **no modification needed** but confirms Option B path already works
- `scripts/little_loops/cli/loop/testing.py:24-27` — calls `evaluate()` and `evaluate_exit_code()` in test/simulate subcommands; **no modification needed** but a caller of the dispatcher being changed
- `scripts/little_loops/fsm/types.py` — defines `Evaluator = Callable[[EvaluateConfig, ...], EvaluationResult]` type alias; imports `EvaluateConfig` under `TYPE_CHECKING`; **no modification needed** but defines the callable signature that Option B extension must match
- `scripts/little_loops/fsm/fragments.py:38,93-109` — resolves `lib/*.yaml` via `_BUILTIN_LOOPS_DIR` fallback; `benchmark.yaml` in `lib/` is auto-discoverable via `import: [lib/benchmark.yaml]` — **no registration needed**

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py` — **PRIMARY evaluator dispatcher test file** (not mentioned in issue); add `test_dispatch_harbor_scorer()` under `TestEvaluateDispatcher` class following the `test_dispatch_*` pattern; **will fail at runtime if Option A elif branch is tested without this**
- `scripts/tests/test_fsm_validation.py` — covers `_validate_evaluator()` which reads `EVALUATOR_REQUIRED_FIELDS`; add test asserting `harbor_scorer` accepts valid config and rejects missing required fields
- `scripts/tests/test_ll_loop_display.py` — tests `_EVALUATE_TYPE_DISPLAY`; add assertion for `harbor_scorer` display entry added in `info.py:611-619`
- `scripts/tests/test_fsm_fragments.py::TestBuiltinLoopMigration` (lines 880-891) — add `"benchmark.yaml"` (or the actual loop file using the fragment) to `migration_targets` once the fragment ships; ensures `load_and_validate` passes end-to-end
- `scripts/tests/test_extension.py` — Option B: add test verifying a `HarborScorerExtension` registers `harbor_scorer` via `wire_extensions()` and the executor dispatches it correctly

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3877-3884` — `EvaluateConfig` type listing already missing `diff_stall` and `mcp_result`; if Option A, add `harbor_scorer` here to keep API docs current
- `docs/generalized-fsm-loop.md:246-248` — inline YAML comment enumerates evaluator types: `# exit_code, output_numeric, output_json, output_contains, llm_structured, convergence, diff_stall, mcp_result` — if Option A, add `harbor_scorer` to this comment (distinct from the subsection at line 455 already listed)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` — Fragment file structure and `description:` field convention
- `scripts/little_loops/loops/lib/cli.yaml` — Fragment with `${context.*}` interpolation
- `scripts/tests/test_fsm_fragments.py` — Fragment test patterns: Shape B (tmp_path lib write), Shape D (`load_and_validate` integration)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`evaluate_harbor_scorer()` function specification** — direct template is `evaluate_mcp_result` at `evaluators.py:468-525`:
- Signature: `def evaluate_harbor_scorer(output: str, exit_code: int) -> EvaluationResult:`
- Reads no fields from `EvaluateConfig` — inputs arrive from dispatcher as positional args (same pattern as `mcp_result`)
- elif dispatch to add at `evaluators.py:833` (immediately after `elif eval_type == "mcp_result":` block): `elif eval_type == "harbor_scorer": return evaluate_harbor_scorer(output=output, exit_code=exit_code)`
- **Verdict logic (decided — exit-code based)**: `exit_code != 0 → verdict="no"`; `exit_code == 0` but stdout not parseable as float → `verdict="error"`; `exit_code == 0` and stdout parses as float → `verdict="yes"` with `details={"score": score, "exit_code": 0}`. No `threshold` field needed; `EVALUATOR_REQUIRED_FIELDS["harbor_scorer"] = []` (empty, same as `mcp_result`). Scorer determines pass/fail via its own exit code; the evaluator only interprets the result.

**`EVALUATOR_REQUIRED_FIELDS["harbor_scorer"]`**: Should be `[]` (empty list) following `"mcp_result": []` at `validation.py:70`. Add as 9th entry: `"harbor_scorer": [],`. Only add field names if the evaluator reads fields from `EvaluateConfig` (e.g., `"threshold"`).

**`__init__.py` export — correction**: `evaluate_mcp_result` and `evaluate_diff_stall` are NOT exported from `fsm/__init__.py` — the import block at lines 77-88 exports only 5 named evaluators (`evaluate_convergence`, `evaluate_exit_code`, `evaluate_llm_structured`, `evaluate_output_contains`, `evaluate_output_json`, `evaluate_output_numeric`). **Do NOT add `evaluate_harbor_scorer` to `__init__.py`** — follow the `mcp_result` precedent. The step in "Files to Modify" (`__init__.py:73-142`) is incorrect; skip it.

**`_EVALUATE_TYPE_DISPLAY` in `info.py:611-619`**: Dict has only 7 entries; `mcp_result` and `diff_stall` are both absent. The fallback at line 623 returns the raw string for missing keys. Adding `"harbor_scorer"` is optional — without it, display renders as `"harbor_scorer"` which is acceptable.

**`benchmark.yaml` fragment structure (decided — single fragment)** — follow `numeric_gate` pattern (`common.yaml:64-72`); one `run_benchmark` fragment that deep-merges into a single consuming state:
```yaml
description: Benchmark runner fragment library
fragments:
  run_benchmark:
    description: |
      Run a Harbor-format benchmark task directory.
      Caller must supply: action (scorer command), on_yes, on_no.
      Caller may supply: capture: benchmark_score.
      Scorer stdout must be valid JSON: {"score": float, "per_task": [...], "run_id": "..."}.
      Multi-field access via ${captured.benchmark_score.output} parsed as JSON.
    action_type: shell
    evaluate:
      type: harbor_scorer
    # NOTE: capture_fields does NOT exist in StateConfig; use capture: + JSON stdout instead.
    # Three-fragment design (load_tasks/run_tasks/aggregate) was considered and rejected.
```

**Test pattern exact locations** (confirmed via codebase analysis):
- Shape B (`_write_lib` + `resolve_fragments`): `test_fsm_fragments.py:300-515` — write lib YAML to `tmp_path / "lib"`, build raw dict inline, call `resolve_fragments(raw, tmp_path)`, assert `state["action_type"]` and `state["evaluate"]["type"]`
- Shape D (`load_and_validate`): `test_fsm_fragments.py:670-741` — write full `.yaml` to `tmp_path`, call `load_and_validate(loop_yaml)` → `(fsm, warnings)`, assert `fsm.states["run"].action_type` and `fsm.states["run"].evaluate.type`
- Dispatch test template: `test_fsm_evaluators.py:1201-1214` (`test_dispatch_mcp_result`) — `EvaluateConfig(type="harbor_scorer")`, call `evaluate(config, output, exit_code, ctx)`, assert `result.verdict`
- Schema required-field test template: `test_fsm_schema.py:1733-1744` (`test_mcp_result_evaluator_type_is_valid`) — for `harbor_scorer` with no required fields: assert `EvaluateConfig(type="harbor_scorer").type == "harbor_scorer"` and round-trip via `to_dict()`/`from_dict()`
- Fuzz list: `test_fsm_schema_fuzz.py:44-51` — add `"harbor_scorer"` to `valid_types` list

## Implementation Steps

1. Create Harbor-format fixture directory `scripts/tests/fixtures/harbor/` with 3 task directories (`task_01/`, `task_02/`, `task_03/`), each containing `task.md` (task instructions in markdown) and `expected.json` (`{"score": float, "criteria": [str]}`); document the format in `fixtures/harbor/README.md`
2. Create `scripts/little_loops/loops/lib/benchmark.yaml` with a single `run_benchmark` fragment following the `numeric_gate` model (`lib/common.yaml:64-72`): two runtime fields — `action_type: shell` and `evaluate.type: harbor_scorer`; caller supplies `action`, `on_yes`, `on_no`, and optionally `capture: benchmark_score` (scorer stdout must be JSON: `{"score": float, "per_task": [...], "run_id": "..."}`)
3. Implement `evaluate_harbor_scorer(output: str, exit_code: int) -> EvaluationResult` in `evaluators.py` after `evaluate_mcp_result` at line 525 — verdict: `exit_code != 0 → "no"`; stdout not parseable as float → `"error"`; exit 0 + parseable float → `"yes"` with `details={"score": score, "exit_code": 0}`; add elif branch at `evaluators.py:833`; update `validation.py` (`"harbor_scorer": []`), `schema.py` (Literal); **skip `__init__.py`** (follows `mcp_result` precedent — not exported)
4. Write `scripts/tests/test_benchmark_fragment.py` covering: fragment resolution (Shape B: `_write_lib` + `resolve_fragments`, `test_fsm_fragments.py:300-515`), load-and-validate integration (Shape D: `test_fsm_fragments.py:670-741`), scorer dispatch (exit-code verdict: 0→"yes", non-0→"no"), JSON output parsing, missing-tasks-dir error
5. Update evaluator-related files: `schema.py` (Literal), `validation.py` (`"harbor_scorer": []`), `evaluators.py` (function + elif), `test_fsm_schema_fuzz.py` (valid_types), `test_fsm_schema.py` (`test_harbor_scorer_*`), `test_fsm_evaluators.py` (`test_dispatch_harbor_scorer`), `test_fsm_validation.py`; skip `__init__.py` and optionally skip `info.py`
6. Update fragment library docs: `loops/README.md`, `LOOPS_GUIDE.md`, `AUDIT_REPORT.md`, `CLI.md`; add `harbor_scorer` subsection to `docs/generalized-fsm-loop.md:455` and inline comment at `docs/generalized-fsm-loop.md:246-248`
7. Run `python -m pytest scripts/tests/ > /tmp/ll-scratch/test-results.txt 2>&1; tail -20 /tmp/ll-scratch/test-results.txt`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_fsm_evaluators.py` — add `test_dispatch_harbor_scorer()` under `TestEvaluateDispatcher`; this is the primary evaluator dispatcher test file and was not listed in the issue; follow existing `test_dispatch_*` patterns in the class
9. Update `scripts/tests/test_fsm_validation.py` — add test for `harbor_scorer` in `_validate_evaluator()`: valid config passes, missing required field returns ERROR-severity error
10. If Option B: add `HarborScorerExtension(EvaluatorProviderExtension)` class to `scripts/little_loops/extension.py`; `provided_evaluators()` must return `{"harbor_scorer": callable}` matching the `Evaluator` type alias at `types.py:79-82`
11. Update `scripts/tests/test_extension.py` (Option B) — add test verifying `HarborScorerExtension` wires correctly via `wire_extensions()` and the executor dispatches `harbor_scorer` without error
12. Update `scripts/tests/test_fsm_fragments.py::TestBuiltinLoopMigration` — add any consuming loop YAML (or `benchmark.yaml` itself if it has an evaluate block) to `migration_targets` at lines 880-891 once the fragment ships
13. Update `docs/reference/API.md:3877-3884` — add `harbor_scorer` to `EvaluateConfig` type listing (Option A only)
14. Update `scripts/tests/test_ll_loop_display.py` — add assertion for `harbor_scorer` display name in `_EVALUATE_TYPE_DISPLAY` after `info.py` is updated

### Implementation Research Findings

_Added by `/ll:refine-issue` — clarifications from codebase analysis:_

- **Step 3 (stale)**: "Resolve Option A vs B" is resolved — Option A is selected. Implement directly: add `evaluate_harbor_scorer()` function after `evaluate_mcp_result` at `evaluators.py:525`, add elif branch at `evaluators.py:833`, update the three core files (`schema.py`, `validation.py`, `evaluators.py`).
- **Step 5 (correction)**: Remove `__init__.py` from the modification list — `evaluate_mcp_result` is NOT in `__init__.py` exports; `evaluate_harbor_scorer` should not be added either. All other files in step 5 still apply.
- **Step 5 (clarification)**: `_EVALUATE_TYPE_DISPLAY` update in `info.py` is optional — `mcp_result` and `diff_stall` are both absent from the dict and render via fallback. Only add if a human-readable display name is desired.
- **Steps 1-3 resolved (2026-04-23)**: Harbor fixture format = `task.md` + `expected.json` per task dir. Fragment design = single `run_benchmark` fragment. Verdict logic = exit-code based. `capture_fields` does not exist in the codebase — use `capture: benchmark_score` with JSON-encoded scorer stdout.

## Impact

- **Priority**: P2 — Blocks FEAT-1245 (loop integration) and FEAT-1120 (harness-optimize loop); without this fragment both downstream issues cannot proceed
- **Effort**: Large — New evaluator type across 3 core FSM files, new fragment YAML, Harbor fixture format definition, and tests spanning evaluator dispatch, fragment resolution, schema validation, and display
- **Risk**: Medium — Modifies `evaluators.py`, `schema.py`, and `validation.py` (well-tested core files); new `harbor_scorer` type follows established `mcp_result` pattern exactly; risk is low per-file but surface is wide
- **Breaking Change**: No — additive only; new evaluator type and new lib YAML; no changes to existing evaluator behavior

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/lib/benchmark.yaml` loads and validates under existing loop schema checks
- [ ] Unit tests cover task enumeration, scorer dispatch, aggregation reducers, missing-tasks-dir error
- [ ] Integration test: fragment against 3-task Harbor fixture asserts expected score
- [ ] `python -m pytest scripts/tests/` passes with no regressions
- [ ] Fragment library docs updated to list `lib/benchmark.yaml`

## Dependencies

Blocks: FEAT-1245 (loop integration) — that issue wires this fragment into existing loops.
Blocks: FEAT-1120 (harness-optimize loop) — needs this fragment as its scoring step.

## Labels

`feature`, `benchmark`, `fsm`, `evaluator`, `fragment`, `harbor`

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-23T16:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4ee2422-6ef4-4b8d-87df-99cb7d580718.jsonl`
- `/ll:ready-issue` - 2026-04-23T16:03:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f53b5b9-ab9d-439a-9dc3-99baadda2091.jsonl`
- `/ll:confidence-check` - 2026-04-23T16:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b35255f7-b6b6-46d3-af77-efb623ea0ed7.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:39:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2e64653-610d-4248-b1f2-429ccbd66f0c.jsonl`
- `/ll:refine-issue` - 2026-04-23T15:21:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/469627b2-baca-42d7-992d-8bdee85ebf48.jsonl`
- `/ll:decide-issue` - 2026-04-23T15:04:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07e9009f-4f75-414d-9885-0866e07cd4e6.jsonl`
- `/ll:wire-issue` - 2026-04-21T23:54:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da57548e-ff8e-44e0-a3f7-da5dfbdd9e89.jsonl`
- `/ll:refine-issue` - 2026-04-21T23:48:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8d696c9-774d-426c-af80-044a2fdce014.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acc1b9ba-37ad-4355-95fb-ff7907feebf3.jsonl`

---

## Resolution

**Status**: Completed — 2026-04-23

**Changes**:
- Added `evaluate_harbor_scorer()` to `scripts/little_loops/fsm/evaluators.py` (after `evaluate_mcp_result`): verdict logic `exit_code != 0 → "no"`, stdout not parseable as float → `"error"`, exit 0 + float → `"yes"` with `details={"score": score, "exit_code": 0}`
- Added `elif eval_type == "harbor_scorer"` dispatch branch in `evaluators.py`
- Added `"harbor_scorer"` to `EvaluateConfig.type` Literal in `schema.py`
- Added `"harbor_scorer": []` to `EVALUATOR_REQUIRED_FIELDS` in `validation.py`
- Created `scripts/little_loops/loops/lib/benchmark.yaml` with `run_benchmark` fragment (single fragment following `numeric_gate` pattern)
- Created `scripts/tests/fixtures/harbor/` with 3 task directories (`task.md` + `expected.json` each)
- Created `scripts/tests/test_benchmark_fragment.py` covering evaluator verdicts, fragment resolution (Shape B), load-and-validate (Shape D), schema, and fixture sanity
- Updated `test_fsm_evaluators.py`, `test_fsm_schema.py`, `test_fsm_validation.py`, `test_fsm_schema_fuzz.py`, `test_fsm_fragments.py` with harbor_scorer tests
- Updated docs: `loops/README.md`, `LOOPS_GUIDE.md`, `AUDIT_REPORT.md`, `CLI.md`, `generalized-fsm-loop.md`, `API.md`

**Acceptance Criteria**:
- [x] `scripts/little_loops/loops/lib/benchmark.yaml` loads and validates under existing loop schema checks
- [x] Unit tests cover task enumeration, scorer dispatch, aggregation reducers, missing-tasks-dir error
- [x] Integration test: fragment against 3-task Harbor fixture asserts expected score
- [x] `python -m pytest scripts/tests/` passes with no regressions (414 tests pass)
- [x] Fragment library docs updated to list `lib/benchmark.yaml`

## Status

Completed
