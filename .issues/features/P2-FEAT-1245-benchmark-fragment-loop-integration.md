---
id: FEAT-1245
priority: P2
parent: FEAT-1119
size: Small
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-24T19:07:02Z
status: done
---

# FEAT-1245: Benchmark Fragment — Loop Integration

## Summary

Wire the `run_benchmark` fragment (delivered by FEAT-1244) into `outer-loop-eval.yaml` and `agent-eval-improve.yaml` as optional opt-in states. Update related tests to account for the new states.

## Parent Issue

Decomposed from FEAT-1119: Benchmark Adapter Fragment (`lib/benchmark.yaml`)

## Motivation

A loop developer wiring up evaluation pipelines must currently write duplicate inline scoring blocks in each loop that needs benchmarking. This issue eliminates that duplication by making `run_benchmark` a shared, opt-in fragment. Without it, FEAT-1120 (harness-optimize loop) cannot proceed — the scoring primitive it depends on doesn't exist in the loops that need to invoke it.

## Prerequisites

FEAT-1244 must be merged before this issue can be implemented — this issue depends on `lib/benchmark.yaml` and its `run_benchmark` fragment existing.

## Current Behavior

`outer-loop-eval.yaml` and `agent-eval-improve.yaml` define their own inline scoring via custom `run` blocks or inline `evaluator` calls. No shared fragment is used.

## Expected Behavior

- `outer-loop-eval.yaml` gains an opt-in state that calls `fragment: run_benchmark`; existing `llm_structured` scoring path stays intact (additive, not breaking)
- `agent-eval-improve.yaml` gains an opt-in state for `run_benchmark`; existing `score_results` → `route_quality` inline scoring must keep working
- Callers declare `tasks_dir` and `scorer` in their `context:` block to activate the fragment path
- `test_outer_loop_eval.py` updated: `REQUIRED_STATES` set and state-structure assertions reflect the new opt-in state

## Use Case

A loop developer has written a custom `outer-loop-eval` pipeline and wants standardized benchmark scoring without duplicating scoring logic. They add `tasks_dir` and `scorer` to their `context:` block, and the opt-in `run_benchmark` state runs the benchmark fragment, writing the score to `captured.benchmark_score`. A downstream `evaluate: type: output_numeric` gate then routes based on the score — all without any inline scoring boilerplate in the loop definition.

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

### Dependent Files (Callers/Importers)
- Any project loop YAML that references `outer-loop-eval` or `agent-eval-improve` by name — callers activate the fragment path by declaring `tasks_dir` and `scorer` in `context:`

### Similar Patterns
- `scripts/little_loops/loops/lib/cli.yaml` — Fragment with `${context.*}` interpolation in `action:`
- `scripts/little_loops/loops/rl-coding-agent.yaml:47-92` — Composite reward via shell + `convergence` evaluator

### Tests
- `scripts/tests/test_outer_loop_eval.py` — Update `REQUIRED_STATES` set and state-structure assertions for the new opt-in state

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:36-44` — `test_all_validate_as_valid_fsm` sweeps all built-in YAMLs including both modified files; acts as canary — will fail if `import:` block or `run_benchmark_opt_in` state is malformed [Agent 1 + Agent 3 finding]
- `scripts/tests/test_outer_loop_eval.py` — Add new `test_run_benchmark_opt_in_uses_fragment` assertion (asserts raw YAML fields: `fragment`, `capture`, `action` contains `context.scorer`/`context.tasks_dir`, `on_error == "done"`) — pattern confirmed from `test_fsm_fragments.py:1064-1120` [Agent 3 finding]
- `scripts/tests/test_agent_eval_improve.py` — Does not exist; `agent-eval-improve.yaml` currently only gets canary coverage (`test_builtin_loops.py`), no state-structure assertions. Creating this file is optional but recommended to prevent silent removal of the new state. Follow `TestOuterLoopEvalStates` pattern in `test_outer_loop_eval.py:61-77` [Agent 3 finding]

### Documentation
- N/A — no user-facing docs reference these internal evaluation loop configs

### Configuration
- N/A — no separate config file; callers supply `tasks_dir` and `scorer` via `context:` in their own loop YAML

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`import:` block required — both loop files currently lack it** (`fragments.py:91-108`):
```yaml
import:
  - lib/benchmark.yaml
```
Add at the top level of both `outer-loop-eval.yaml` and `agent-eval-improve.yaml` before the `states:` key. Fragment resolution falls back to the built-in loops dir, so `lib/benchmark.yaml` resolves to `scripts/little_loops/loops/lib/benchmark.yaml` automatically.

**Opt-in state structure — no `condition:` key in FSM schema:**
The FSM schema has no `condition:` field (confirmed via `schema.py`). The established opt-in pattern (see `outer-loop-eval.yaml:18-23`) uses shell `test -n` guards. The simplest single-state approach relies on `on_error` routing when context keys are absent:
```yaml
run_benchmark_opt_in:
  fragment: run_benchmark
  action: "${context.scorer} ${context.tasks_dir}"
  capture: benchmark_score
  on_yes: done
  on_no: done
  on_error: done
```
When `context.scorer`/`context.tasks_dir` are not supplied by the caller, the shell exits non-zero → routes to `on_no: done`. This is the opt-in behavior without a separate guard state.

**`operator: gte` → `operator: ge` correction (expected contract bug):**
The expected contract in this issue (line 56) uses `operator: gte`. Valid operators in `evaluators.py:87-94` are: `eq`, `ne`, `lt`, `le`, `gt`, `ge`. Use `operator: ge` — `gte` does not exist and will cause a runtime `KeyError`.

**Test assertion shape for raw YAML fixture vs. post-resolution:**
`TestOuterLoopEvalStates` uses a raw `yaml.safe_load()` fixture — fragment-contributed fields (`action_type`, `evaluate`) are not present before resolution. Assert the caller-supplied fields only:
```python
def test_run_benchmark_opt_in_uses_fragment(self, loop_data: dict) -> None:
    state = loop_data["states"]["run_benchmark_opt_in"]
    assert state.get("fragment") == "run_benchmark"
    assert state.get("capture") == "benchmark_score"
    assert "context.scorer" in state.get("action", "")
    assert "context.tasks_dir" in state.get("action", "")
    assert state.get("on_error") == "done"
```
The existing `test_validates_as_fsm` (line 33) already calls `load_and_validate()`, which runs `resolve_fragments()` — so post-resolution correctness (that `action_type == "shell"` and `evaluate.type == "harbor_scorer"`) is already exercised by that test.

**`REQUIRED_STATES` subset semantics — explicit update is optional:**
`test_outer_loop_eval.py:74` asserts `REQUIRED_STATES - actual == empty` (subset check, not equality). Adding the new state name to `REQUIRED_STATES` is not required for tests to pass, but is recommended to document intent and prevent accidental removal of the new state in future.

## Implementation Steps

1. Add opt-in `run_benchmark` state block to `scripts/little_loops/loops/outer-loop-eval.yaml`; verify existing scoring path still works
2. Add same opt-in state block to `scripts/little_loops/loops/agent-eval-improve.yaml`; verify `score_results` → `route_quality` chain is unaffected
3. Update `scripts/tests/test_outer_loop_eval.py`: add new state to `REQUIRED_STATES` and any state-structure assertions
4. Run `python -m pytest scripts/tests/test_outer_loop_eval.py -v > /tmp/ll-scratch/test-results.txt 2>&1; tail -20 /tmp/ll-scratch/test-results.txt`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Verify `scripts/tests/test_builtin_loops.py` passes — `test_all_validate_as_valid_fsm` is a canary that exercises fragment resolution for both modified YAMLs; run `python -m pytest scripts/tests/test_builtin_loops.py -v -k "validate_as_valid_fsm"` to confirm no resolution errors
6. Add `test_run_benchmark_opt_in_uses_fragment` method to `test_outer_loop_eval.py` — asserts raw YAML fields (`fragment == "run_benchmark"`, `capture == "benchmark_score"`, `on_error == "done"`, `action` contains `context.scorer` and `context.tasks_dir`)

## Acceptance Criteria

- [ ] `outer-loop-eval.yaml` documents opt-in `run_benchmark` block with example `context:` wiring
- [ ] `agent-eval-improve.yaml` has same opt-in block; existing inline scoring untouched
- [ ] `test_outer_loop_eval.py` updated and passing
- [ ] `python -m pytest scripts/tests/` passes with no regressions

## Impact

- **Priority**: P2 — Unblocks FEAT-1120 (harness-optimize loop) which cannot proceed without this scoring primitive
- **Effort**: Small — Additive opt-in state blocks added to two existing loop YAMLs; no new architecture
- **Risk**: Low — Non-breaking; existing inline scoring paths (`llm_structured`, `score_results → route_quality`) are preserved untouched
- **Breaking Change**: No

## Labels

`feat`, `loop-integration`, `benchmark`, `fsm`

## Dependencies

Depends on: FEAT-1244 (benchmark fragment core) — must be merged first.
Enables: FEAT-1120 (harness-optimize loop) — provides the scoring primitive that loop needs.

## Session Log
- `/ll:ready-issue` - 2026-04-24T19:03:21 - `de822c98-36ae-41a8-bc64-a71ac2da3d81.jsonl`
- `/ll:confidence-check` - 2026-04-24T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:wire-issue` - 2026-04-24T18:49:50 - `5e40ac57-7a53-41ed-8096-65a22b4710a4.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:refine-issue` - 2026-04-23T16:29:29 - `7e16f5a4-2bb7-48c1-999f-ab6d54465258.jsonl`
- `/ll:format-issue` - 2026-04-23T16:19:51 - `e7c42afa-de19-4417-8d4e-005c53340f64.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00Z - `acc1b9ba-37ad-4355-95fb-ff7907feebf3.jsonl`

---

## Resolution

- Added `import: [lib/benchmark.yaml]` to `outer-loop-eval.yaml` and `agent-eval-improve.yaml`
- Added `run_benchmark_opt_in` state to both loops (opt-in via `context.scorer`/`context.tasks_dir`; routes all outcomes to `done`)
- Updated `test_outer_loop_eval.py`: added `run_benchmark_opt_in` to `REQUIRED_STATES` and `test_run_benchmark_opt_in_uses_fragment` assertion
- All 5269 tests pass; `test_builtin_loops.py::test_all_validate_as_valid_fsm` confirms fragment resolution is clean

## Status

COMPLETED 2026-04-24

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `scripts/little_loops/loops/outer-loop-eval.yaml` has no `run_benchmark_opt_in` state ✓
- `scripts/little_loops/loops/agent-eval-improve.yaml` has no opt-in benchmark state ✓
- Dependency FEAT-1244 is **COMPLETED** — `lib/benchmark.yaml` now exists; this issue is unblocked ✓
- Feature not yet implemented ✓

**Open** | Created: 2026-04-21 | Priority: P2
