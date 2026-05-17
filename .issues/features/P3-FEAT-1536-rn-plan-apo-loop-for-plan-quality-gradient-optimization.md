---
id: FEAT-1536
type: FEAT
priority: P3
captured_at: "2026-05-17T01:43:21Z"
discovered_date: "2026-05-17"
discovered_by: capture-issue
status: open
relates_to:
  - FEAT-1534
  - FEAT-766
  - FEAT-1120
labels:
  - loops
  - automation
  - apo
  - planning
---

# FEAT-1536: rn-plan-apo Loop for Plan-Quality Gradient Optimization

## Summary

Add a new built-in FSM loop `rn-plan-apo.yaml` that applies TextGrad-style gradient optimization to the **plan-decomposition prompts** used by the in-flight `rn-plan` recursive task planner (FEAT-1534). Unlike `apo-textgrad` (which gradients prompt text against labeled I/O pairs) and unlike `harness-optimize` (which hill-climbs file mutations against a benchmark score), `rn-plan-apo` computes its gradient over **plan-quality signals**: subtask success rate, plan depth vs. task complexity, redundant subtasks, missing subtasks, and rework loops detected in the recursive expansion.

## Current Behavior

`rn-plan` (FEAT-1534, in progress) decomposes a task into subtasks via a planning prompt and recurses. The planning prompt is hand-authored and static. There is no mechanism to:

- Score the **quality of a decomposition** against downstream subtask outcomes
- Compute a gradient over decomposition failures (over-splitting, under-splitting, scope creep, missed dependencies)
- Iteratively refine the planning prompt based on that gradient

`apo-textgrad` cannot fill this gap because its contract is `prompt_file + labeled examples → better prompt_file` — plan decompositions don't have ground-truth "expected outputs," they have downstream-observed quality signals.

## Expected Behavior

Running `ll-loop run rn-plan-apo --context plan_prompt_file=<path> --context tasks_file=<path>` should:

1. **Execute** `rn-plan` on each task in `tasks_file`, capturing the full recursive plan tree.
2. **Score** each plan tree on plan-quality dimensions:
   - Subtask success rate (do leaves complete cleanly?)
   - Depth/complexity ratio (excessive recursion on simple tasks; insufficient on complex)
   - Redundancy (duplicate or near-duplicate subtasks within a plan)
   - Coverage gaps (subtasks reference work that was never assigned a subtask)
   - Rework signal (later iterations revisit earlier subtasks)
3. **Compute gradient**: structured failure pattern + root cause + refinement instruction targeted at the planning prompt — same shape as `apo-textgrad`'s gradient, but the failures come from plan-quality scoring instead of labeled-example comparison.
4. **Apply gradient** to `plan_prompt_file` and repeat until convergence (target plan-quality score) or `max_iterations`.

## Motivation

**Why**: `rn-plan`'s value depends entirely on the quality of its planning prompt. Without a feedback loop, that prompt is whatever the maintainer hand-wrote, with no systematic way to improve it as plan-quality data accumulates. `apo-textgrad`'s contract doesn't fit (no labeled I/O for plans), and `harness-optimize` is too coarse (whole-file hill-climbing with a single score discards the structural information in the plan tree). A dedicated loop with plan-quality scoring is the right shape.

**How to apply**: This is a companion to FEAT-1534 — only meaningful once `rn-plan` is shipped and has produced at least a small corpus of real plan trees to score against. Not relevant for non-planning prompts.

## Integration Map

### Files to Create

- `scripts/little_loops/loops/rn-plan-apo.yaml` — new FSM loop, `from: lib/apo-base`
- `scripts/little_loops/loops/lib/score-plan-quality.yaml` — new scoring fragment (first `lib/score-*.yaml` in the codebase — no existing template)
- `scripts/tests/test_rn_plan_apo.py` — structural + behavioral tests

### Files to Modify

- `scripts/tests/test_builtin_loops.py:65` — add `"rn-plan-apo"` to `TestBuiltinLoopFiles.test_expected_loops_exist`'s `expected` set (inventory registration)
- `docs/guides/LOOPS_GUIDE.md` — three places:
  - Summary table near line 719 (add row)
  - New `### rn-plan-apo` subsection under `## Prompt Optimization Loops (APO)` (anchor at line 1353)
  - "Choosing Between APO Loops" trigger table near line 1712 and comparative feature matrix near line 1722
- `scripts/little_loops/loops/README.md` — append entry to built-in loop list
- `README.md`, `CONTRIBUTING.md` — bump built-in loop count if these reference a hard-coded total (verify before editing)
- `CHANGELOG.md` — add entry at release time (per `feedback_changelog_no_unreleased`: promote into a concrete `## [X.Y.Z] - DATE` section during release prep, not `[Unreleased]`)

### Templates to Mirror (do not modify)

- `scripts/little_loops/loops/apo-textgrad.yaml` — **direct structural template** for the 4-state graph (test → gradient → route → apply); FEAT-1536's state graph mirrors this exactly, swapping `test_on_examples` for `run_planner` + `score_plans` (5 operative states instead of 4)
- `scripts/little_loops/loops/lib/apo-base.yaml` — parent inherited via `from:`; contributes `category: apo`, `max_iterations: 20`, `timeout: 3600`, `on_handoff: spawn`, `context.prompt_file: system.md`, and the `done: {terminal: true}` state
- `scripts/little_loops/loops/svg-textgrad.yaml` — richer variant with multi-dimension scoring + plateau-based convergence detection (read scores.md, detect 3-iteration flatline before emitting CONVERGED); the closer behavioral analogue for plan-quality scoring across multiple dimensions
- `scripts/little_loops/loops/lib/benchmark.yaml` — `fragments:` block format to follow when authoring `lib/score-plan-quality.yaml`

### Dependent Files (Callers/Discovery)

- `scripts/little_loops/cli/loop/_helpers.py:122` — `get_builtin_loops_dir()` + `resolve_loop_path()`; new YAML auto-discovered by glob, no registration call needed
- `scripts/little_loops/fsm/fragments.py` — `resolve_inheritance()` resolves `from: lib/apo-base` via `_deep_merge`; child wins at every nesting level
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` enforces `max_iterations` and `timeout` inherited from `apo-base`; `_run_action()` stores captures as `{output, stderr, exit_code, duration_ms}` keyed by `state.capture` — every `${captured.X.output}` reference depends on this shape
- `scripts/little_loops/fsm/evaluators.py:609` — `evaluate_output_contains()`: regex `re.search` first, substring fallback; matches `CONVERGED` token
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.from_dict()` parses and validates the merged YAML

### Test Templates

- `scripts/tests/test_builtin_loops.py` — `TestSvgTextgradLoop` (closest template: gradient + route_convergence + apply_gradient + score recording) and `TestEvaluationQualityLoop` (multi-threshold context block pattern)
- `scripts/tests/test_harness_optimize.py` — example per-loop test file with context defaults, state validation, fragment usage patterns
- `scripts/tests/test_loops_recursive_refine.py` — `_bash(script, cwd)` helper for testing shell-state snippets in isolation (relevant only if `score_plans` or `run_planner` uses a shell state)
- `scripts/tests/test_fsm_executor.py:31-88` — `MockActionRunner` pattern for unit-testing convergence and max-iteration termination without invoking the host CLI

### Documentation

- `docs/guides/LOOPS_GUIDE.md:2545` — explicit description of the `from: lib/apo-base` merge rule (useful when documenting the new loop's inheritance)
- `docs/reference/loops.md` — loop YAML reference and state graph documentation
- `docs/generalized-fsm-loop.md` — FSM loop conceptual documentation

## Implementation Steps

1. **Define plan-quality scoring fragment** at `scripts/little_loops/loops/lib/score-plan-quality.yaml`: ingests a plan tree (JSON) and outputs per-dimension scores + an aggregate.
2. **Author `rn-plan-apo.yaml`** FSM mirroring `apo-textgrad`'s state graph but with `score_plans` replacing `test_on_examples`:
   - `run_planner` → executes `rn-plan` over `tasks_file`, captures plan trees to `${captured.plans.output}`
   - `score_plans` → invokes the scoring fragment, captures per-tree scores + aggregate
   - `compute_gradient` → same shape as `apo-textgrad` but consumes plan-quality scores instead of pass/fail
   - `route_convergence` → CONVERGED gate
   - `apply_gradient` → overwrites `plan_prompt_file`
3. **Add test** at `scripts/tests/test_rn_plan_apo.py` with a fixture `tasks_file` and a stubbed planner that returns deterministic plan trees so scoring is testable.
4. **Document** in `docs/guides/LOOPS_GUIDE.md` alongside the `apo-*` loop family, and reference from `rn-plan`'s entry once FEAT-1534 lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete shapes derived from `apo-textgrad.yaml`, `lib/apo-base.yaml`, and `svg-textgrad.yaml`:_

**Inheritance scaffolding (free from `from: lib/apo-base`)** — do NOT re-declare in the child:
- `category: apo`, `max_iterations: 20`, `timeout: 3600`, `on_handoff: spawn`
- `context.prompt_file: system.md` (deep-merged; child adds `plan_prompt_file`, `tasks_file`, `target_plan_quality` on top)
- `states.done: {terminal: true}` — inherited terminal state

**State graph invariants** (verified against `apo-textgrad.yaml` and asserted in `TestSvgTextgradLoop`):
- Every operative `action_type: prompt` state must declare `on_blocked: done` (BLOCKED-signal safety exit)
- `compute_gradient` must have `capture: gradient` and `next: route_convergence`
- `route_convergence` must have NO `action:` — it is pure evaluator; the `source: "${captured.gradient.output}"` field on `evaluate` is **mandatory** (without it, the evaluator reads the empty current-state output instead of the prior capture). This invariant is asserted in `test_builtin_loops.py::TestSvgTextgradLoop::test_route_convergence_evaluator_source` and the equivalent test for `rn-plan-apo` should mirror it
- `route_convergence.on_yes: done`, `on_no: apply_gradient`, `on_error: <fallback to score_plans or run_planner>`
- `apply_gradient.next: <first scoring state>` (closes the cycle); apply_gradient has no `capture:` (the only artifact is the overwritten prompt file on disk)

**Convergence is LLM-emitted, not numerically gated**: `compute_gradient`'s action prompt must include the literal sentence "If <plan-quality aggregate exceeds ${context.target_plan_quality}>, output CONVERGED on its own line instead." The FSM does not parse the numeric score itself — convergence is a string-match on `CONVERGED` in the captured gradient output. (See `apo-textgrad.yaml::compute_gradient` and `svg-textgrad.yaml::compute_gradient` for the two variants.)

**File-write semantics for `apply_gradient`**: the `plan_prompt_file` overwrite happens via the LLM agent's tool calls inside the host subprocess (Read + Write), not by the FSM executor. The AC requirement "loop overwrites `plan_prompt_file` only on accepted refinements" is satisfied structurally because `apply_gradient` is unreachable from `route_convergence` when the LLM emits `CONVERGED` (the `on_yes: done` branch fires) — the prompt file is only touched on the `on_no` branch.

**FEAT-1534 blocker is real**: `rn-plan.yaml` does not exist on disk today. `run_planner` cannot delegate to `ll-loop run rn-plan ...` until FEAT-1534 lands. The scoring fragment and FSM scaffold can be authored against a stubbed planner (per AC step 3), but live execution waits on FEAT-1534.

**Plan-quality scoring is novel**: `lib/score-*.yaml` does not exist yet — `lib/` currently holds `apo-base.yaml`, `benchmark.yaml`, `cli.yaml`, `common.yaml`. The new fragment is the first of its kind; follow `lib/benchmark.yaml`'s `fragments:` + per-fragment `description:` + `action_type:` + `evaluate:` shape.

**Per-iteration score history** (optional but recommended): `svg-textgrad.yaml` writes scores to `scores.md` and gradients to `gradients.md` per iteration, then uses 3-iteration flatline detection to declare convergence and escalates the gradient when the same ROOT_CAUSE recurs ≥2 times. For multi-dimension plan quality (4+ dimensions per AC) this is the more robust pattern than `apo-textgrad`'s single-shot threshold — consider mirroring `svg-textgrad`'s `record_scores` + `append_gradient` shell states rather than `apo-textgrad`'s simpler graph.

## API/Interface

New loop config:

```yaml
# scripts/little_loops/loops/rn-plan-apo.yaml
name: rn-plan-apo
from: lib/apo-base
context:
  plan_prompt_file: <path-to-rn-plan-planning-prompt>
  tasks_file: <path-to-task-list-json>
  target_plan_quality: 80
```

New scoring fragment:

```yaml
# scripts/little_loops/loops/lib/score-plan-quality.yaml
# Inputs: ${context.plan_trees}
# Outputs: per-tree scores + aggregate PLAN_QUALITY=<integer 0-100>
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete YAML scaffolding derived from `apo-textgrad.yaml` + `lib/apo-base.yaml`:_

**Full `rn-plan-apo.yaml` skeleton** (the bits that must mirror `apo-textgrad.yaml` exactly; child-specific lines marked):

```yaml
name: rn-plan-apo                     # child
from: lib/apo-base                    # child — inherits scaffolding (see below)
description: |                        # child
  ...
initial: run_planner                  # child — required, no default in apo-base
context:                              # child — deep-merged with apo-base.context
  plan_prompt_file: .ll/prompts/rn-plan-planning.md
  tasks_file: benchmarks/rn-plan-tasks.json
  target_plan_quality: 80
states:
  run_planner:
    action_type: prompt
    timeout: 300
    action: |
      Execute the rn-plan loop over ${context.tasks_file} using the planning
      prompt at ${context.plan_prompt_file}. Capture each plan tree as JSON.
      Output: one JSON object per task on its own line, then on the final
      line: PLANS_GENERATED=<integer>.
    capture: plans
    on_blocked: done
    next: score_plans
  score_plans:
    action_type: prompt        # or fragment: score_plan_quality once lib/score-plan-quality.yaml exists
    timeout: 300
    action: |
      Score each plan tree from ${captured.plans.output} on:
      - subtask_success_rate (0-100)
      - depth_complexity_ratio (0-100)
      - redundancy (0-100, higher = less redundant)
      - coverage_gaps (0-100, higher = fewer gaps)
      For each plan output: "Plan N: <dim>=<int>, <dim>=<int>, ..."
      On the final line output: PLAN_QUALITY=<integer 0-100> (aggregate)
    capture: plan_scores
    on_blocked: done
    next: compute_gradient
  compute_gradient:
    action_type: prompt
    timeout: 300
    action: |
      Analyze plan-quality scores to compute a text gradient:
      ${captured.plan_scores.output}
      Output:
      1. FAILURE_PATTERN: <common plan-quality issue across all plans>
      2. ROOT_CAUSE: <what is wrong in the planning prompt>
      3. GRADIENT: <precise instruction for how to change the planning prompt>
      If PLAN_QUALITY exceeds ${context.target_plan_quality}, output
      CONVERGED on its own line instead.
    capture: gradient
    on_blocked: done
    next: route_convergence
  route_convergence:
    evaluate:
      type: output_contains
      source: "${captured.gradient.output}"   # MANDATORY — no action on this state
      pattern: "CONVERGED"
    on_yes: done
    on_no: apply_gradient
    on_error: run_planner
  apply_gradient:
    action_type: prompt
    timeout: 300
    action: |
      Apply this text gradient to improve the planning prompt:
      Current prompt: (read from ${context.plan_prompt_file})
      Gradient: ${captured.gradient.output}
      Produce a refined planning prompt that addresses the ROOT_CAUSE and
      follows the GRADIENT instruction. Output the full refined prompt, then
      overwrite ${context.plan_prompt_file} with it.
    on_blocked: done
    next: run_planner
  # `done: {terminal: true}` inherited from lib/apo-base — do not re-declare
```

**Fragment shape for `lib/score-plan-quality.yaml`** (follows `lib/benchmark.yaml`'s `fragments:` convention):

```yaml
# Import in any loop with:
#   import:
#     - lib/score-plan-quality.yaml
# Then reference in a state:
#   score_plans:
#     fragment: score_plan_quality
#     action: |
#       (caller supplies the scoring prompt body)
fragments:
  score_plan_quality:
    description: |
      Score a set of rn-plan plan trees on 4 dimensions: subtask success rate,
      depth/complexity ratio, redundancy, and coverage gaps. Emits per-plan
      lines and a final aggregate PLAN_QUALITY=<integer 0-100>.
      Caller must supply: action (scoring prompt body), capture.
      Caller may supply: timeout, on_blocked, next.
    action_type: prompt
    timeout: 300
```

## Use Case

**Who**: A maintainer who has shipped `rn-plan` (FEAT-1534) and wants the planner's decomposition prompt to improve as more plan trees are generated.

**Context**: After running `rn-plan` on a set of representative tasks, the maintainer has noticed systematic plan-quality issues (e.g., over-splitting trivial tasks, or skipping dependency analysis).

**Goal**: Run `ll-loop run rn-plan-apo --context plan_prompt_file=.ll/prompts/rn-plan-planning.md --context tasks_file=benchmarks/rn-plan-tasks.json` and walk away with an improved planning prompt that targets the observed failure pattern.

**Outcome**: The planning prompt converges to a state where plan-quality score exceeds the target, with a recorded gradient history explaining what changed and why.

## Related Key Documentation

| Doc | Why relevant |
|-----|--------------|
| `scripts/little_loops/loops/apo-textgrad.yaml` | Direct structural template — 4-state graph (test → gradient → route → apply); mirror exactly, swapping the scoring states |
| `scripts/little_loops/loops/svg-textgrad.yaml` | Richer pattern: multi-dimension scoring + plateau-based CONVERGED detection (read scores.md across 3 iterations); behavioral analogue for plan-quality |
| `scripts/little_loops/loops/lib/apo-base.yaml` | Base config inherited via `from:`; contributes `category`, `max_iterations: 20`, `timeout: 3600`, `on_handoff: spawn`, `context.prompt_file`, and `done: {terminal: true}` |
| `scripts/little_loops/loops/lib/benchmark.yaml` | `fragments:` block format to follow when authoring `lib/score-plan-quality.yaml` |
| `scripts/little_loops/fsm/fragments.py` | `resolve_inheritance()` and `_deep_merge()` define how `from:` merges parent + child |
| `scripts/little_loops/fsm/executor.py` | `FSMExecutor._run_action()` defines the `{output, stderr, exit_code, duration_ms}` capture shape that every `${captured.X.output}` reference depends on |
| `scripts/tests/test_builtin_loops.py` | Contains `TestSvgTextgradLoop` (closest test template) and `TestBuiltinLoopFiles.test_expected_loops_exist:65` (must register `"rn-plan-apo"` in the expected set) |
| `.issues/features/P2-FEAT-1534-add-rn-plan-built-in-fsm-loop-for-recursive-task-planning.md` | Defines `rn-plan` and its planning prompt — the artifact this loop optimizes; rn-plan.yaml does not exist on disk yet |
| `docs/guides/LOOPS_GUIDE.md` | Where the new loop must be documented: APO section (line 1353), summary table (line 719), Choosing-Between table (line 1712), feature matrix (line 1722) |

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/rn-plan-apo.yaml` exists and extends `lib/apo-base`
- [ ] `scripts/little_loops/loops/lib/score-plan-quality.yaml` scores plan trees on at least 4 dimensions (success rate, depth/complexity, redundancy, coverage gaps)
- [ ] Loop converges on a fixture task set with a deterministic stubbed planner (score rises monotonically until target reached or max_iterations hit)
- [ ] Loop overwrites `plan_prompt_file` only on accepted refinements; rejected refinements leave the file untouched
- [ ] `test_rn_plan_apo.py` covers: scoring fragment, convergence path, max-iteration termination, and prompt-file persistence
- [ ] `test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` updated to include `"rn-plan-apo"` in the `expected` set (inventory registration)
- [ ] Test asserts the `route_convergence.evaluate.source == "${captured.gradient.output}"` invariant (mirrors `TestSvgTextgradLoop::test_route_convergence_evaluator_source`) — without `source:`, the evaluator reads the empty current-state output
- [ ] Documented in `docs/guides/LOOPS_GUIDE.md` and cross-linked from FEAT-1534's rn-plan entry once that ships

## Impact

- **Priority**: P3 — valuable optimization tool but blocked by FEAT-1534 (`rn-plan`); not user-facing until that ships and accumulates plan-tree data.
- **Effort**: Medium — one new loop YAML (mirrors `apo-textgrad` state graph), one new scoring fragment, one test file, and docs updates. No new infrastructure; reuses `lib/apo-base` and existing FSM machinery.
- **Risk**: Low — additive only. New loop file, new fragment, new test; does not modify `apo-textgrad`, `harness-optimize`, or `rn-plan` itself. Worst case: loop produces poor refinements, which leave `plan_prompt_file` untouched (gated on acceptance per AC).
- **Scope**: Limited to plan-decomposition prompts used by `rn-plan`. Not a general-purpose plan optimizer.

## Dependencies

- **FEAT-1534** (`rn-plan` built-in loop) must ship first — `rn-plan-apo` has no artifact to optimize until then.

## Session Log
- `/ll:refine-issue` - 2026-05-17T01:54:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/21a23601-8801-4478-b899-816a89ded470.jsonl`
- `/ll:format-issue` - 2026-05-17T01:46:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1772a9c9-375e-4635-9d23-f8a61e7e3c7f.jsonl`

- `/ll:capture-issue` - 2026-05-17T01:43:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ff744fb-fd2c-4c52-b59d-5acb13e9557a.jsonl`

- `/ll:refine-issue` - 2026-05-17T02:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b9595aa-5604-4993-8970-761fc7eda533.jsonl`

---

## Status

- **Status**: open
- **Discovered**: 2026-05-17
