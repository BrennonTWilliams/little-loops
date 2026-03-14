---
id: FEAT-722
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# FEAT-722: Built-in Loops for Automatic Prompt Optimization (APO) Techniques

## Summary

Add new built-in FSM loop configurations that implement Automatic Prompt Optimization (APO) techniques, enabling users to iteratively improve prompts using established optimization strategies (e.g., gradient-free optimization, feedback-driven refinement, meta-prompting) without writing custom loops from scratch.

## Current Behavior

`ll-loop` supports custom FSM loop configurations but has no built-in loops targeting prompt optimization workflows. Users who want to run APO-style iterative improvement on their prompts must design the FSM from scratch.

## Expected Behavior

A set of built-in loop configurations (ship with `ll-loop` or discoverable via `ll-loop list --builtin`) that implement common APO techniques:
- Feedback-driven prompt refinement (run → evaluate → refine → repeat)
- Contrastive prompt optimization (generate candidates → score → select best → iterate)
- Meta-prompting loops (use a prompt to improve a prompt, iterate until stable)
- Possibly: DSPy-style few-shot bootstrapping loops

## Motivation

APO is a well-established research area with practical, automatable workflows. Little-loops already has the FSM loop infrastructure — adding built-in APO loop templates lowers the barrier significantly for users who want to systematically improve their prompts. This positions little-loops as a practical tool for prompt engineering workflows, not just code automation.

## Use Case

A developer has a system prompt for a Claude-powered feature that produces inconsistent outputs. They run:

```bash
ll-loop run --builtin apo-feedback-refinement --var prompt_file=system.md --var eval_dataset=examples.json
```

The loop generates improved prompt candidates, evaluates them against the dataset, selects the best-performing variant, and repeats for N iterations — surfacing the optimized prompt at the end.

## Acceptance Criteria

- [ ] At least 2 built-in APO loop configurations ship with little-loops (e.g., `apo-feedback-refinement`, `apo-contrastive`)
- [ ] Built-ins are discoverable via `ll-loop list --builtin` or equivalent
- [ ] Each built-in documents its technique, required variables, and expected outputs
- [ ] Built-ins are parameterized (users can pass in their prompt file, eval criteria, iteration count, etc.)
- [ ] `ll-loop run --builtin <name>` loads and executes the built-in without a user-managed YAML file
- [ ] Documentation explains each APO technique and when to use it

## API/Interface

```bash
# Discover available built-ins
ll-loop list --builtin

# Run a built-in with variable overrides
ll-loop run --builtin apo-feedback-refinement --var iterations=5 --var prompt=my-prompt.md

# Show built-in definition (for inspection/customization)
ll-loop show --builtin apo-contrastive
```

## Proposed Solution

1. Define a `builtins/` directory inside the `ll-loop` package (e.g., `scripts/little_loops/loop/builtins/`)
2. Each built-in is a YAML loop config with documented variable substitution placeholders
3. Extend `ll-loop run` with a `--builtin <name>` flag that resolves the YAML from the package's builtin directory
4. Extend `ll-loop list` with `--builtin` to enumerate available built-ins with descriptions
5. APO loop states would use Claude API calls (via `claude` CLI or subprocess) to generate/evaluate prompt variants

## Integration Map

### Files to Modify
- `scripts/little_loops/loop/` - core loop execution engine
- `scripts/little_loops/cli/loop.py` - CLI entry point for `ll-loop`

### Dependent Files (Callers/Importers)
- TBD - use grep to find `ll-loop` invocations in skills and hooks

### Similar Patterns
- Existing FSM loop YAML configs in user projects (reference structure)
- `P3-FEAT-659-hierarchical-fsm-loops.md` - related loop enhancement

### Tests
- `scripts/tests/` - add tests for builtin resolution and `--builtin` flag

### Documentation
- `docs/reference/API.md` - document new `--builtin` flag
- Loop documentation or README section on APO built-ins

### Configuration
- N/A (built-ins are package-level, not user-config)

## Implementation Steps

1. Research 2-3 APO techniques and design their FSM state machines
2. Create `scripts/little_loops/loop/builtins/` with YAML configs for each technique
3. Extend `ll-loop run` to support `--builtin <name>` flag
4. Extend `ll-loop list` with `--builtin` enumeration
5. Add `ll-loop show --builtin` for inspection
6. Write tests for builtin loading and execution
7. Document APO techniques and usage examples

## Impact

- **Priority**: P3 - High value for prompt engineering workflows; not blocking but expands use cases significantly
- **Effort**: Large - Requires APO technique research, FSM design, CLI extension, and documentation
- **Risk**: Medium - New subsystem (builtins directory + CLI flags); core loop engine unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Loop system architecture |
| `docs/reference/API.md` | CLI reference for `ll-loop` |

## Labels

`feature`, `loops`, `apo`, `prompt-engineering`, `captured`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- No APO loop YAML files exist in `loops/` (confirmed by filename search). No `builtins/` directory exists under `scripts/little_loops/`. `ll-loop list` and `ll-loop run` have no `--builtin` flag. Feature not yet implemented.

## Session Log

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab9873-e77b-46a5-b50b-85782d3bc37c.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2503a31-5075-415e-95d5-959cac6eec58.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
