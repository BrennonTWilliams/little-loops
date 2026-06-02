---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
decision_needed: true
confidence_score: 85
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
size: Very Large
status: done
completed_at: 2026-04-21T00:00:00Z
---

# FEAT-1119: Benchmark Adapter Fragment (`lib/benchmark.yaml`)

## Summary

Add a reusable FSM loop fragment that accepts a benchmark spec (task directory + scorer command) and returns a numeric score. Start with Harbor-format compatibility so autoagent's public `tasks/` sets work out of the box. Hook the fragment into `outer-loop-eval.yaml` and `agent-eval-improve.yaml` as a pluggable scoring step.

## Current Behavior

- No loop-level benchmark adapter exists. Evaluation in loops like `outer-loop-eval.yaml` and `agent-eval-improve.yaml` is homegrown — each loop defines its own scoring via custom `run` blocks or inline `evaluator` calls.
- No shared abstraction for "run a benchmark task directory and return a score," so loops that want to gate acceptance on a numeric metric must reimplement the scoring shell each time.
- No adapter for standard external benchmark formats (Harbor, SWE-bench, TerminalBench). A user cannot point little-loops at a public benchmark suite and get a score without writing a bespoke loop.

## Expected Behavior

- New fragment `scripts/little_loops/loops/lib/benchmark.yaml` accepts:
  - `tasks_dir` — path to a Harbor-format task set
  - `scorer` — shell command (or registered scorer name) that executes a task and emits a score on stdout
  - Optional: `per_task_timeout`, `parallel`, `filter`
- Returns a numeric aggregate score (mean or configurable reducer) writable into the loop's context for downstream states to gate on.
- Registered scorer hook in `scripts/little_loops/fsm/evaluators.py` so `scorer: harbor_default` resolves to a first-party implementation without shell glue.
- `outer-loop-eval.yaml` and `agent-eval-improve.yaml` can opt into the fragment with a single `include:` / `run:` block; existing inline scoring keeps working (additive, not a breaking change).

## Motivation

This feature would:
- Unblock score-gated hill-climbing loops (harness-optimize, FEAT-1120) — those need a reusable "produce a number" primitive.
- Give little-loops credibility parity with autoagent, which uses Harbor-format benchmarks end-to-end. Users can point the harness at public benchmark suites without writing adapter code.
- Reduce duplication across existing apo/eval loops; each currently reinvents scoring.

## Use Case

**Who**: Loop author building an eval-driven or APO-style loop

**Context**: Wants to score a candidate agent/harness against a fixed task set (internal or external Harbor-format)

**Goal**: Declare `run: lib/benchmark.yaml` with `tasks_dir:` and `scorer:` and read `ctx.benchmark_score` in the next state

**Outcome**: Numeric score available to the FSM without writing per-loop scoring plumbing

## Proposed Solution

### New: `scripts/little_loops/loops/lib/benchmark.yaml`

FSM fragment (callable via the existing fragment/include mechanism used by other `lib/` fragments). States:
- `load_tasks` — enumerate task directory, respect filter
- `run_tasks` — execute scorer per task (sequential by default; honor `parallel:` if the fragment caller opts in)
- `aggregate` — combine per-task scores via configured reducer (mean, median, pass-rate)
- Emit `benchmark_score`, `benchmark_per_task`, `benchmark_run_id` into context

### `scripts/little_loops/fsm/evaluators.py`

Register a `harbor_default` scorer that knows the Harbor task schema (expected input, ground truth path, grader invocation). Keep the scorer registry extensible so future suites (SWE-bench, TerminalBench) can be added without modifying the fragment.

### `scripts/little_loops/fsm/schema.py`

No new top-level keys — the fragment consumes standard `run`/`eval` plumbing. If profiling shows per-task timeout needs a first-class field, add it in a follow-up.

### Integration touchpoints

- `outer-loop-eval.yaml` — add an optional state that calls the fragment; leave existing scoring path intact.
- `agent-eval-improve.yaml` — same.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Scorer registration — two options:**

**Option A: Add `harbor_scorer` as a core evaluator type**
- Add `evaluate_harbor_scorer()` to `scripts/little_loops/fsm/evaluators.py` alongside the other leaf evaluator functions
- Add `elif eval_type == "harbor_scorer":` branch in `evaluate()` at `evaluators.py:699`
- Add `"harbor_scorer"` entry to `EVALUATOR_REQUIRED_FIELDS` dict at `scripts/little_loops/fsm/validation.py:62-71`
- Add `"harbor_scorer"` to `EvaluateConfig.type` `Literal[...]` at `scripts/little_loops/fsm/schema.py:56-65`

**Option B: Register `harbor_default` via the contributed evaluator extension mechanism**
- Wire via `wire_extensions()` called from `scripts/little_loops/cli/loop/lifecycle.py:266`
- Extension callable matches `Evaluator` type alias at `scripts/little_loops/fsm/types.py:79-82`: `Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]`
- Dispatcher at `scripts/little_loops/fsm/executor.py:780-782` checks contributed evaluators before falling through to core `evaluate()`
- Avoids modifying `evaluators.py`, `schema.py`, or `validation.py`

**Context writeback correction:** The spec says "writable into the loop's context" — this is inaccurate. Runtime `context` is read-only at `scripts/little_loops/fsm/interpolation.py:37`. All mutable runtime state accumulates in `captured`. The fragment should use `capture: benchmark_score`; downstream states read `${captured.benchmark_score.output}`.

**FEAT-1120 expected fragment contract** (from `.issues/features/P2-FEAT-1120-harness-optimize-loop.md`):
```yaml
fragment: run_benchmark
capture: benchmark_score
evaluate:
  type: output_numeric
  source: "${captured.benchmark_score.output}"
  operator: gte
  target: "${context.pass_threshold}"
```

## Integration Map

### New Files
- `scripts/little_loops/loops/lib/benchmark.yaml` — Fragment library (top-level `fragments:` key following `lib/common.yaml` pattern); must contain at minimum a `run_benchmark` fragment
- `scripts/tests/test_benchmark_fragment.py` — Unit + integration tests
- `scripts/tests/fixtures/harbor/` — 3-task Harbor-format fixture directory (no harbor fixtures exist yet)

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — Add opt-in state using `fragment: run_benchmark` (additive, leave existing `llm_structured` scoring path intact)
- `scripts/little_loops/loops/agent-eval-improve.yaml` — Same opt-in block; existing `score_results` → `route_quality` inline scoring must stay working
- `scripts/little_loops/fsm/evaluators.py` — If Option A: add `evaluate_harbor_scorer()` + `elif` branch at line 699
- `scripts/little_loops/fsm/schema.py` — If Option A: add to `EvaluateConfig.type` `Literal[...]` at line 56-65
- `scripts/little_loops/fsm/validation.py` — If Option A: add to `EVALUATOR_REQUIRED_FIELDS` at line 62-71

### Dependent Files (Callers/Importers)
- `.issues/features/P2-FEAT-1120-harness-optimize-loop.md` — blocked on this feature; expects `run_benchmark` fragment with `capture: benchmark_score`
- `scripts/little_loops/fsm/fragments.py:64` — `resolve_fragments()` already handles `lib/` imports; no changes needed
- `scripts/little_loops/fsm/executor.py:780-782` — `_contributed_evaluators` dispatch already handles Option B without changes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py:73-142` — re-exports `EvaluateConfig`, `evaluate()`, `resolve_fragments()`, `Evaluator`; if Option A adds `evaluate_harbor_scorer`, this export list must be updated
- `scripts/little_loops/cli/loop/testing.py:24` — imports and calls `evaluate()`; sees new evaluator type through dispatch, no code change needed but is an affected caller
- `scripts/little_loops/cli/loop/info.py:611-619` — `_EVALUATE_TYPE_DISPLAY` dict maps evaluator type strings to human labels; Option A requires adding `"harbor_scorer"` entry (falls back to identity string without it, no hard failure)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` — Fragment file structure and `description:` field convention
- `scripts/little_loops/loops/lib/cli.yaml` — Fragment with `${context.*}` interpolation in `action:` (e.g., `ll_loop_run`)
- `scripts/little_loops/loops/rl-coding-agent.yaml:47-92` — Composite reward via shell + `convergence` evaluator pattern
- `scripts/little_loops/loops/agent-eval-improve.yaml:64-77` — Numeric convergence gating via `output` tail extraction

### Tests
- `scripts/tests/test_fsm_fragments.py` — Fragment test patterns to model: Shape A (inline unit), Shape B (tmp_path lib write), Shape C (real-file validation), Shape D (`load_and_validate` integration)
- `scripts/tests/test_fsm_evaluators.py` — Evaluator function test patterns (if Option A)
- `scripts/tests/test_builtin_loops.py` — Already validates built-in loop structure; `benchmark.yaml` goes in `loops/lib/` (not `loops/`) so glob at line 22 does NOT auto-discover it — `test_expected_loops_exist` at line 46 is unaffected

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema_fuzz.py:44-51` — hardcoded `valid_types` list (`exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `llm_structured`); Option A requires adding `"harbor_scorer"` to this list or the fuzz test never exercises the new type [UPDATE]
- `scripts/tests/test_outer_loop_eval.py` — dedicated structure tests for `outer-loop-eval.yaml`; if the opt-in `run_benchmark` state is added to that loop, `REQUIRED_STATES` set and state-structure assertions will need new entries [UPDATE when opt-in state is added]
- `scripts/tests/test_fsm_schema.py` (`TestEvaluatorValidation` class) — has per-type required-field tests; Option A requires adding `test_harbor_scorer_requires_*` tests mirroring `test_output_numeric_requires_operator` pattern [UPDATE if Option A]
- `scripts/tests/test_fsm_executor.py` — imports `EvaluateConfig`, exercises `_contributed_evaluators` dispatch; no breakage but contains `TestContributedEvaluatorDispatch` which is the right place to add an Option B contributed-evaluator dispatch test

### Documentation
- `docs/ARCHITECTURE.md` — FSM loop execution model; may need note on benchmark fragment
- `docs/reference/API.md` — `fsm/evaluators.py` extension points; update if Option A adds a new type

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md:117-121` — fragment library table explicitly lists only `lib/common.yaml` and `lib/cli.yaml`; add row for `lib/benchmark.yaml` [UPDATE]
- `docs/guides/LOOPS_GUIDE.md:2045-2098` — "Two libraries ship with little-loops" statement at line 2045; fragment tables at lines 2047-2098 cover only `lib/common.yaml` and `lib/cli.yaml`; needs third entry [UPDATE]
- `docs/guides/AUDIT_REPORT.md:90` — audit table explicitly enumerates the two fragment libraries; add `lib/benchmark.yaml` [UPDATE]
- `docs/reference/CLI.md:431-432` — `ll-loop fragments` command examples list `lib/common.yaml` and `lib/cli.yaml`; add `lib/benchmark.yaml` example [UPDATE]
- `docs/generalized-fsm-loop.md:455` — Evaluator Types section documents all types; add `harbor_scorer` subsection (Option A only; under Option B no change needed since it's externally registered) [UPDATE if Option A]

## Implementation Steps

1. Create `scripts/little_loops/loops/lib/benchmark.yaml` with a `run_benchmark` fragment (model after `lib/common.yaml`; use `action: "${context.scorer} ${context.tasks_dir}"`, `action_type: shell`, `capture: benchmark_score`)
2. Decide Option A vs B for scorer registration (see Proposed Solution options above); implement accordingly
3. Create `scripts/tests/fixtures/harbor/` with a 3-task minimal Harbor-format fixture (task directories with expected input and ground truth files)
4. Write `scripts/tests/test_benchmark_fragment.py` covering: task enumeration, scorer dispatch, aggregation, missing-tasks-dir error; follow Shape B + Shape D patterns from `test_fsm_fragments.py`; include an all-fragments-have-description test mirroring `test_fsm_fragments.py:997-1023`
5. Add opt-in state block to `scripts/little_loops/loops/outer-loop-eval.yaml` and `scripts/little_loops/loops/agent-eval-improve.yaml` (import + optional `run_benchmark` state; existing scoring paths unchanged); callers must declare `tasks_dir` and `scorer` in their `context:` block
6. Run `python -m pytest scripts/tests/ > /tmp/ll-scratch/test-results.txt 2>&1; tail -20 /tmp/ll-scratch/test-results.txt` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/loops/README.md:117-121` — add row for `lib/benchmark.yaml` in the fragment library table
8. Update `docs/guides/LOOPS_GUIDE.md:2045-2098` — change "Two libraries ship with little-loops" to "Three libraries"; add `lib/benchmark.yaml` fragment table section
9. Update `docs/guides/AUDIT_REPORT.md:90` — add `lib/benchmark.yaml` to the fragment library enumeration
10. Update `docs/reference/CLI.md:431-432` — add `ll-loop fragments lib/benchmark.yaml` as a third example
11. (Option A only) Update `scripts/little_loops/fsm/__init__.py:73-142` — add `evaluate_harbor_scorer` to the re-export list alongside other `evaluate_*` functions
12. (Option A only) Update `scripts/little_loops/cli/loop/info.py:611-619` — add `"harbor_scorer"` display label to `_EVALUATE_TYPE_DISPLAY` dict
13. (Option A only) Update `docs/generalized-fsm-loop.md:455` — add `harbor_scorer` subsection to the Evaluator Types section
14. (Option A only) Update `scripts/tests/test_fsm_schema_fuzz.py:44-51` — add `"harbor_scorer"` to the hardcoded `valid_types` list
15. (Option A only) Update `scripts/tests/test_fsm_schema.py` (`TestEvaluatorValidation`) — add `test_harbor_scorer_requires_*` tests mirroring `test_output_numeric_requires_operator` pattern
16. Update `scripts/tests/test_outer_loop_eval.py` — after adding opt-in state to `outer-loop-eval.yaml`, update the `REQUIRED_STATES` set and any state-structure assertions to account for the new state

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop execution model, fragment mechanism |
| `docs/reference/API.md` | `fsm/evaluators.py` extension points |

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/lib/benchmark.yaml` loads and validates under existing loop schema checks
- [ ] Unit tests in `scripts/tests/test_benchmark_fragment.py` cover: task enumeration, scorer dispatch, aggregation reducers, missing-tasks-dir error path
- [ ] Integration test: run fragment against a 3-task Harbor fixture (committed under `scripts/tests/fixtures/harbor/`), assert score matches expected
- [ ] `outer-loop-eval.yaml` gains a documented opt-in block showing how to wire the fragment
- [ ] No regression: `python -m pytest scripts/tests/` passes; existing apo/eval loops unchanged

## Dependencies

Blocks: FEAT-1120 (harness-optimize loop) — that loop needs this fragment as its scoring step.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 63/100 → MODERATE

### Concerns
- **Unresolved design decision** (`decision_needed: true`): Option A vs Option B for scorer registration is not chosen. Forks implementation at Step 2 and conditionally affects 8 of 16 implementation steps. Run `/ll:decide-issue FEAT-1119` before starting.

### Outcome Risk Factors
- Broad file surface (10-15 files): doc updates across LOOPS_GUIDE.md, AUDIT_REPORT.md, CLI.md, README.md plus conditional test updates add regression risk.
- Option A schema change: adding `harbor_scorer` to `EvaluateConfig.type` Literal in schema.py affects all evaluate config validation; test_fsm_schema_fuzz.py:44-51 must be updated before Option A tests pass.
- Harbor fixture design: no Harbor-format fixtures exist yet; fixture schema must be researched before test_benchmark_fragment.py can be written.

## Session Log
- `/ll:confidence-check` - 2026-04-21T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5445125b-16af-4867-a8b4-4eda163c469f.jsonl`
- `/ll:wire-issue` - 2026-04-21T23:39:21 - `5445125b-16af-4867-a8b4-4eda163c469f.jsonl`
- `/ll:refine-issue` - 2026-04-21T23:31:54 - `20ec0632-13d1-41e5-9b0b-3e8353102c81.jsonl`
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `acc1b9ba-37ad-4355-95fb-ff7907feebf3.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-21
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1244: Benchmark Fragment — Core FSM Fragment & Scorer Registration
- FEAT-1245: Benchmark Fragment — Loop Integration

---

## Status

Open
