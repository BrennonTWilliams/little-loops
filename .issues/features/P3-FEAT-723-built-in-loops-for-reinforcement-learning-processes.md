---
id: FEAT-723
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 73
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
- `scripts/little_loops/loop/` - add RL loop type definitions
- `skills/create-loop/SKILL.md` - expose RL loop types in creation wizard
- `templates/` - add RL loop YAML templates

### Dependent Files (Callers/Importers)
- TBD - use grep to find loop type registry

### Similar Patterns
- `P2-FEAT-712-harness-loop-type-for-create-loop.md` - existing built-in loop type pattern to follow
- `P3-FEAT-659-hierarchical-fsm-loops.md` - related FSM loop extension

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A

## Implementation Steps

1. Audit existing loop type definitions and `create-loop` wizard to understand extension points
2. Design 2-3 RL loop YAML templates (bandit, RLHF-style, policy iteration)
3. Register new loop types in `create-loop` selection flow
4. Add validation for RL-specific state fields (reward, convergence, max_iterations)
5. Write tests and update docs

## API/Interface

```python
# Example loop type registration
BUILTIN_LOOP_TYPES = {
    "rl-bandit": BanditLoopTemplate,
    "rl-rlhf": RLHFLoopTemplate,
    "rl-policy": PolicyIterationTemplate,
}
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
