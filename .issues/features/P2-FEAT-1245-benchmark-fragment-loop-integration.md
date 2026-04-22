---
id: FEAT-1245
priority: P2
parent: FEAT-1119
size: Small
---

# FEAT-1245: Benchmark Fragment — Loop Integration

## Summary

Wire the `run_benchmark` fragment (delivered by FEAT-1244) into `outer-loop-eval.yaml` and `agent-eval-improve.yaml` as optional opt-in states. Update related tests to account for the new states.

## Parent Issue

Decomposed from FEAT-1119: Benchmark Adapter Fragment (`lib/benchmark.yaml`)

## Prerequisites

FEAT-1244 must be merged before this issue can be implemented — this issue depends on `lib/benchmark.yaml` and its `run_benchmark` fragment existing.

## Current Behavior

`outer-loop-eval.yaml` and `agent-eval-improve.yaml` define their own inline scoring via custom `run` blocks or inline `evaluator` calls. No shared fragment is used.

## Expected Behavior

- `outer-loop-eval.yaml` gains an opt-in state that calls `fragment: run_benchmark`; existing `llm_structured` scoring path stays intact (additive, not breaking)
- `agent-eval-improve.yaml` gains an opt-in state for `run_benchmark`; existing `score_results` → `route_quality` inline scoring must keep working
- Callers declare `tasks_dir` and `scorer` in their `context:` block to activate the fragment path
- `test_outer_loop_eval.py` updated: `REQUIRED_STATES` set and state-structure assertions reflect the new opt-in state

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — Add opt-in state: `fragment: run_benchmark` with `capture: benchmark_score`; leave existing `llm_structured` scoring path intact
- `scripts/little_loops/loops/agent-eval-improve.yaml` — Same opt-in block; preserve `score_results` → `route_quality` inline scoring
- `scripts/tests/test_outer_loop_eval.py` — Update `REQUIRED_STATES` set and state-structure assertions for the new state

### Context writeback note
`context` is read-only at `scripts/little_loops/fsm/interpolation.py:37`. The fragment writes to `captured`. Downstream states read `${captured.benchmark_score.output}`. The FEAT-1120 expected contract is:
```yaml
fragment: run_benchmark
capture: benchmark_score
evaluate:
  type: output_numeric
  source: "${captured.benchmark_score.output}"
  operator: gte
  target: "${context.pass_threshold}"
```

### Similar Patterns
- `scripts/little_loops/loops/lib/cli.yaml` — Fragment with `${context.*}` interpolation in `action:`
- `scripts/little_loops/loops/rl-coding-agent.yaml:47-92` — Composite reward via shell + `convergence` evaluator

## Implementation Steps

1. Add opt-in `run_benchmark` state block to `scripts/little_loops/loops/outer-loop-eval.yaml`; verify existing scoring path still works
2. Add same opt-in state block to `scripts/little_loops/loops/agent-eval-improve.yaml`; verify `score_results` → `route_quality` chain is unaffected
3. Update `scripts/tests/test_outer_loop_eval.py`: add new state to `REQUIRED_STATES` and any state-structure assertions
4. Run `python -m pytest scripts/tests/test_outer_loop_eval.py -v > /tmp/ll-scratch/test-results.txt 2>&1; tail -20 /tmp/ll-scratch/test-results.txt`

## Acceptance Criteria

- [ ] `outer-loop-eval.yaml` documents opt-in `run_benchmark` block with example `context:` wiring
- [ ] `agent-eval-improve.yaml` has same opt-in block; existing inline scoring untouched
- [ ] `test_outer_loop_eval.py` updated and passing
- [ ] `python -m pytest scripts/tests/` passes with no regressions

## Dependencies

Depends on: FEAT-1244 (benchmark fragment core) — must be merged first.
Enables: FEAT-1120 (harness-optimize loop) — provides the scoring primitive that loop needs.

## Session Log
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acc1b9ba-37ad-4355-95fb-ff7907feebf3.jsonl`

---

## Status

Open
