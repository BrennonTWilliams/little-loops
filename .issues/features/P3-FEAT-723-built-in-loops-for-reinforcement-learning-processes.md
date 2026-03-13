---
id: FEAT-723
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
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

## Proposed Solution

TBD - requires investigation

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

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab9873-e77b-46a5-b50b-85782d3bc37c.jsonl`
