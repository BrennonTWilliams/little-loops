---
id: FEAT-1244
priority: P2
parent: FEAT-1119
decision_needed: true
size: Large
confidence_score: 80
outcome_confidence: 36
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 0
score_change_surface: 18
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

## Design Decision Required

**Resolve Option A vs B before implementation** (run `/ll:decide-issue FEAT-1244`):

**Option A: Add `harbor_scorer` as a core evaluator type**
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

## Implementation Steps

1. Define Harbor task fixture format (each task = a directory with at minimum a task spec file and expected result file; document the structure in `fixtures/harbor/README.md`); create `scripts/tests/fixtures/harbor/` with 3 minimal task directories
2. Create `scripts/little_loops/loops/lib/benchmark.yaml` with a `run_benchmark` fragment; each fragment is a single-state construct (deep-merged into a caller state); choose between: (a) one `run_benchmark` fragment whose shell action runs all phases inline, or (b) three named fragments `load_tasks`/`run_tasks`/`aggregate` that consumers compose; use `action_type: shell`, `capture: benchmark_score`; model after `lib/common.yaml:14-72`
3. Resolve Option A vs B; implement accordingly — note both options require updating `validation.py:EVALUATOR_REQUIRED_FIELDS` and `schema.py:EvaluateConfig.type Literal`; Option A also adds `evaluators.py` leaf function + elif; Option B adds an extension class
4. Write `scripts/tests/test_benchmark_fragment.py` covering: task enumeration, scorer dispatch, aggregation (mean, median, pass-rate), missing-tasks-dir error; follow Shape B (`_write_lib` + `resolve_fragments`, `test_fsm_fragments.py:300-515`) and Shape D (`load_and_validate` integration, `test_fsm_fragments.py:670-741`) patterns
5. If Option A: update `schema.py`, `validation.py`, `evaluators.py`, `__init__.py`, `info.py`, `test_fsm_schema_fuzz.py`, `test_fsm_schema.py`
6. Update fragment library docs: `README.md`, `LOOPS_GUIDE.md`, `AUDIT_REPORT.md`, `CLI.md`; if Option A: `docs/generalized-fsm-loop.md`
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

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/lib/benchmark.yaml` loads and validates under existing loop schema checks
- [ ] Unit tests cover task enumeration, scorer dispatch, aggregation reducers, missing-tasks-dir error
- [ ] Integration test: fragment against 3-task Harbor fixture asserts expected score
- [ ] `python -m pytest scripts/tests/` passes with no regressions
- [ ] Fragment library docs updated to list `lib/benchmark.yaml`

## Dependencies

Blocks: FEAT-1245 (loop integration) — that issue wires this fragment into existing loops.
Blocks: FEAT-1120 (harness-optimize loop) — needs this fragment as its scoring step.

## Session Log
- `/ll:wire-issue` - 2026-04-21T23:54:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da57548e-ff8e-44e0-a3f7-da5dfbdd9e89.jsonl`
- `/ll:refine-issue` - 2026-04-21T23:48:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8d696c9-774d-426c-af80-044a2fdce014.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acc1b9ba-37ad-4355-95fb-ff7907feebf3.jsonl`

---

## Status

Open
