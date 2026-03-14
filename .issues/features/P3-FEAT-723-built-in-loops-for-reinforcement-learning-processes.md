---
id: FEAT-723
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 71
---

# FEAT-723: Built-in Loops for Reinforcement Learning Processes

## Summary

Add new built-in FSM loop types to `ll-loop` that support reinforcement learning (RL) workflows — enabling iterative train/evaluate/improve cycles to run autonomously as first-class loop configurations.

## Current Behavior

`ll-loop` supports general FSM-based automation loops, but has no built-in loop types designed for RL or iterative learning workflows. Users who want to run RL-style cycles (e.g., generate → evaluate → reward → update → repeat) must hand-craft FSM YAML from scratch with no guidance or scaffolding.

## Expected Behavior

Users can select from built-in RL loop templates when running `/ll:create-loop`, with pre-configured states for common RL patterns:
- **Bandit loop**: explore → exploit → reward → update
- **RLHF-style loop**: generate → evaluate → score → refine → repeat
- **Policy iteration**: act → observe → score → improve → repeat

Loops run iteratively until a convergence condition or max-iterations is reached.

## Motivation

Reinforcement learning workflows are inherently iterative and well-suited to FSM modeling. Adding RL-native loop types would make little-loops useful for ML experimentation and prompt optimization — high-value use cases that align with the tool's automation philosophy.

## Use Case

**Who**: ML researcher or automation engineer using little-loops for iterative experimentation

**Context**: They want to run a reinforcement learning-style cycle (e.g., prompt optimization, bandit experiment, or policy iteration) without manually writing FSM YAML from scratch.

**Goal**: Select a built-in RL loop template from `/ll:create-loop`, configure parameters (max iterations, convergence threshold), and launch the loop autonomously.

**Outcome**: The RL-style loop runs iteratively, tracking reward/score across episodes, and terminates when a convergence condition or `max_iterations` limit is reached.

## Acceptance Criteria

- [ ] `/ll:create-loop` wizard lists at least 3 RL loop types: `rl-bandit`, `rl-rlhf`, `rl-policy`
- [ ] Each RL loop type produces a valid, runnable FSM YAML configuration
- [ ] RL loops support a configurable `max_iterations` parameter to bound execution
- [ ] RL loops support a convergence condition (e.g., `min_improvement_threshold`) that terminates early when met
- [ ] RL loop YAML templates pass existing FSM schema validation
- [ ] Existing non-RL loop types are unaffected (no regression)

## Proposed Solution

Extend `ll-loop` and `/ll:create-loop` with built-in RL loop templates by introducing new loop type definitions following the pattern established in `P2-FEAT-712-harness-loop-type-for-create-loop.md`:

1. Audit the loop type registry in `scripts/little_loops/loop/` to understand the extension point
2. Define 3 RL YAML templates with pre-configured states (reward, convergence, iteration counter)
3. Register them in the `create-loop` wizard under a new "RL Loops" category
4. Add RL-specific field validation (`max_iterations`, `convergence_threshold`, `reward`)

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — add 3 RL options to the Step 1 `AskUserQuestion` block (lines 52-77); extend type mapping section (lines 72-77)
- `skills/create-loop/loop-types.md` — add one new H2 section per RL type (bandit, rlhf, policy), following the `## Harness Questions` section pattern (line 548+)
- `skills/create-loop/reference.md` — add state structure diagrams for each RL type (following harness diagrams at lines 89-132)
- `loops/rl-bandit.yaml` — new built-in YAML: `explore → exploit → reward → update` using `convergence` evaluator
- `loops/rl-rlhf.yaml` — new built-in YAML: `generate → evaluate → score → refine` using `llm_structured` evaluator
- `loops/rl-policy.yaml` — new built-in YAML: `act → observe → score → improve` using `convergence` evaluator

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py:46-64` — hardcoded `expected` set of built-in loop names **must** be updated to include `rl-bandit`, `rl-rlhf`, `rl-policy`; otherwise the test asserts equality and will fail

### Similar Patterns
- `skills/create-loop/loop-types.md:548-878` — `## Harness Questions` section is the direct template to follow: question flow → YAML generation → two structural variants
- `skills/create-loop/SKILL.md:67-77` — how `harness` was added as option 5; add RL types as options 6-8 (or a grouped category)
- `loops/backlog-flow-optimizer.yaml` — shows `context:` dict + `${context.<key>}` interpolation for shared RL parameters (reward target, learning rate, etc.)
- `scripts/little_loops/fsm/evaluators.py:308-370` — `convergence` evaluator with `target/progress/stall` verdicts maps directly to RL reward tracking
- `.issues/completed/P2-FEAT-712-harness-loop-type-for-create-loop.md` — completed predecessor; no Python code was added, only skill markdown + YAML files

### Tests
- `scripts/tests/test_builtin_loops.py:46-64` — add `"rl-bandit"`, `"rl-rlhf"`, `"rl-policy"` to the `expected` set (required — test will fail without this)
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles` — new YAML files are automatically picked up by `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm`; no additional test code needed beyond the set update
- `scripts/tests/test_create_loop.py` — may need RL type option coverage if tests enumerate wizard options

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — lists built-in loops with `ll-loop install <name>`; add RL loop entries
- `skills/create-loop/loop-types.md` — primary doc for the wizard; add RL sections here
- `skills/create-loop/reference.md` — state diagrams for UI preview; add RL diagrams

### Configuration
- N/A — no schema changes needed; `convergence` evaluator already registered in `validation.py:61-69` and `schema.py:25-79`

## Implementation Steps

1. Read `skills/create-loop/loop-types.md:548-878` (harness section) and `skills/create-loop/SKILL.md:52-77` to understand the exact extension point format
2. Add 3 RL options to the Step 1 `AskUserQuestion` in `skills/create-loop/SKILL.md:52-77` and type-mapping entries following the harness pattern at lines 72-77
3. Add a `## RL Loops` question/YAML section in `skills/create-loop/loop-types.md` for each type:
   - `rl-bandit`: `context` dict for epsilon/reward, states `explore → exploit → reward → update`, `convergence` evaluator routing `target: done, progress: exploit, stall: explore`
   - `rl-rlhf`: states `generate → evaluate → score → refine → repeat`, `llm_structured` evaluator for score, convergence on score value
   - `rl-policy`: states `act → observe → score → improve`, `convergence` evaluator toward target reward
4. Create `loops/rl-bandit.yaml`, `loops/rl-rlhf.yaml`, `loops/rl-policy.yaml` — valid YAML conforming to `fsm-loop-schema.json`; at minimum must have `name`, `initial`, `states` with one `terminal: true` state
5. Update `scripts/tests/test_builtin_loops.py:46-64` — add `"rl-bandit"`, `"rl-rlhf"`, `"rl-policy"` to `expected` set
6. Add state diagrams to `skills/create-loop/reference.md` following harness diagram pattern at lines 89-132
7. Update `docs/guides/LOOPS_GUIDE.md` to list the new RL built-ins with `ll-loop install rl-bandit` etc.
8. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to verify all 3 new YAML files parse and validate

## API/Interface

> **Note**: No Python loop type registry exists. The "registry" is the `AskUserQuestion` options block in `skills/create-loop/SKILL.md:52-77`. Adding a new loop type means adding to that block + a new section in `loop-types.md` + optionally a built-in YAML file in `loops/`.

RL loop YAML shape (using `convergence` evaluator for reward tracking):

```yaml
name: rl-bandit
description: "Epsilon-greedy bandit loop — explore vs exploit toward a reward target"
initial: explore
max_iterations: 50
context:
  reward_target: 0.8
  epsilon: 0.1
states:
  explore:
    action: "<explore action>"
    action_type: shell
    capture: explore_result
    on_success: reward
    on_failure: reward
  exploit:
    action: "<exploit action>"
    action_type: shell
    capture: exploit_result
    on_success: reward
    on_failure: reward
  reward:
    action: "<compute reward score 0-1>"
    action_type: shell
    evaluate:
      type: convergence
      target: "${context.reward_target}"
      direction: maximize
      tolerance: 0.05
    route:
      target: done
      progress: exploit
      stall: explore
  done:
    terminal: true
```

## Impact

- **Priority**: P3 - Useful ML/automation capability, not blocking
- **Effort**: Medium - Requires loop type registry design + 3 templates
- **Risk**: Low - Additive, no existing behavior changed
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `ml`, `captured`

## Status

**Open** | Created: 2026-03-13 | Priority: P3

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- No RL loop YAML files (`rl-bandit`, `rl-rlhf`, `rl-policy`, etc.) exist in `loops/`. `skills/create-loop/SKILL.md` lists only 4 loop types with no RL category. Feature not yet implemented.

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab9873-e77b-46a5-b50b-85782d3bc37c.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09173b5b-d72c-42cc-87ef-609e8e998bce.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
