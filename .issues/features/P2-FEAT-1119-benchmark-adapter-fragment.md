---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
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

## Session Log
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Status

Open
