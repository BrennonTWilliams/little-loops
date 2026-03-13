---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 86
---

# FEAT-712: Add "Harness" Loop Type to create-loop

## Summary

Add a 5th loop type to `/ll:create-loop` — "Harness a skill or prompt" — that auto-generates plan-evaluate-iterate FSM loops wrapping skills or arbitrary prompts. The harness inspects skill metadata (`SKILL.md`), project configuration (`ll-config.json`), and codebase structure to auto-derive layered evaluation states (tool-based gates, LLM-as-judge, diff invariants) with project-aware quality criteria and auto-calculated convergence defaults.

## Current Behavior

`/ll:create-loop` supports four loop types: fix-until-clean, maintain-constraints, drive-metric, and run-sequence. Creating iterative loops that wrap a skill or prompt with evaluation requires hand-authoring the FSM YAML. There is no automated introspection of skill definitions or project tooling to generate evaluation states.

## Expected Behavior

A new loop type "Harness a skill or prompt" appears in the Step 1 type selection. When selected:

1. **Target selection**: User picks from available skills (listed from `skills/*/SKILL.md`) or enters an arbitrary prompt
2. **Work-item discovery**: User specifies how targets are found (glob pattern, issue list, manual, single-shot)
3. **Auto-evaluation generation**: The generator reads `ll-config.json` for `test_cmd`, `lint_cmd`, `type_cmd` and generates a multi-phase evaluation:
   - Phase 1 (tool-based): Shell states using `exit_code` for available project tools
   - Phase 2 (LLM-as-judge): `llm_structured` evaluator for prompt-based actions, with prompt derived from skill description
   - Phase 3 (diff invariants): Shell state checking `git diff --stat` for scope violations and runaway changes
4. **Convergence defaults**: Auto-calculated `max_iterations`, per-item retry limits, stall detection based on action type and estimated work items
5. The generated FSM follows the existing naming, preview, save, validate, test flow (Steps 3-5)

## Motivation

Hand-authoring evaluation loops for skills is tedious and error-prone. The existing built-in loops (e.g., `issue-refinement.yaml`, `fix-quality-and-tests.yaml`) demonstrate common patterns that could be generated automatically. This feature lets users create sophisticated iterative workflows by describing *what* to do, not *how* to evaluate it — the generator handles project-specific quality gates.

## Use Case

A developer wants to refine all active issues using `/ll:refine-issue`. Instead of hand-writing a 120-line YAML (like `issue-refinement.yaml`), they run `/ll:create-loop`, select "Harness a skill", pick `refine-issue`, specify "all active issues" as work items, and get a generated FSM with: issue discovery state, refine execution, confidence-check evaluation, per-item retry limits, periodic commits, and terminal state. The generated loop handles stall detection and convergence automatically.

## Acceptance Criteria

- [ ] New "Harness a skill or prompt" option in Step 1 of create-loop wizard
- [ ] Skill introspection: reads `SKILL.md` to infer action type and description
- [ ] Project-aware evaluation: uses `ll-config.json` tool commands to generate concrete quality gates
- [ ] Work-item discovery state generated based on user's target selection
- [ ] Multi-phase evaluation states generated (tool-based + LLM-judge + diff invariants, based on availability)
- [ ] Auto-calculated convergence defaults (max_iterations, timeouts) based on action type
- [ ] Generated YAML passes `ll-loop validate`
- [ ] Generated YAML can run successfully via `ll-loop test`

## API/Interface

New section in `skills/create-loop/loop-types.md`:

```yaml
# Step 1 new option:
- label: "Harness a skill or prompt"
  description: "Wrap a skill/prompt with plan-evaluate-iterate. Auto-generates evaluation from project context."

# Generated FSM template structure:
name: "<loop-name>"
initial: discover
states:
  discover:
    action: "<work-item-discovery-command>"
    action_type: shell
    capture: "items"
    on_success: execute
    on_failure: done
  execute:
    action: "<skill-or-prompt> ${captured.items.current}"
    action_type: prompt
    next: check_concrete
  check_concrete:
    action: "<test_cmd/lint_cmd from config>"
    action_type: shell
    on_success: check_semantic
    on_failure: execute
  check_semantic:
    evaluate:
      type: llm_structured
      prompt: "<auto-derived from skill description>"
    on_success: check_invariants
    on_failure: execute
  check_invariants:
    action: "<diff-based scope/size check>"
    action_type: shell
    on_success: advance
    on_failure: execute
  advance:
    action: "<update work-item list>"
    next: discover
  done:
    terminal: true
```

## Proposed Solution

Extend `create-loop` as a 5th loop type rather than a separate skill. Add a "Harness Questions" section to `loop-types.md` following the same pattern as the existing four types. The question flow:

1. **What to harness**: List available skills from `skills/*/SKILL.md`, or "Custom prompt"
2. **Work items**: "How are targets discovered?" — glob, issue list, single-shot, manual
3. **Evaluation preview**: Show auto-detected evaluation layers, let user add/remove
4. **Iteration budget**: Per-item retries, total iterations, timeout

For skill targets, introspect `SKILL.md` for description and `allowed-tools` to infer what the skill does and what evaluation makes sense. For arbitrary prompts, ask the user what "done" looks like (same as existing evaluator selection flow).

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` — Add 5th option to Step 1
- `skills/create-loop/loop-types.md` — Add "Harness Questions" section with question flow and FSM template

### Dependent Files (Callers/Importers)
- `skills/create-loop/reference.md` — May need harness-specific reference entries
- `skills/create-loop/templates.md` — Could add pre-built harness templates

### Similar Patterns
- Existing loop type sections in `loop-types.md` (fix-until-clean, maintain-constraints, drive-metric, run-sequence)
- `issue-refinement.yaml` — Real-world example of what a generated harness would produce

### Tests
- Skill is markdown-based; validate generated FSM YAML via `ll-loop validate <generated-file>`
- Manual test: generate harnesses for `refine-issue` and `check-code` skills, confirm valid + runnable via `ll-loop test`

### Documentation
- `skills/create-loop/reference.md` — Add harness type reference
- `commands/help.md` — Update if loop type list is mentioned

### Configuration
- `.claude/ll-config.json` — Read `project.test_cmd`, `project.lint_cmd`, etc. for evaluation generation (read-only)

## Implementation Steps

1. Add "Harness" option to Step 1 in `skills/create-loop/SKILL.md`
2. Write "Harness Questions" section in `loop-types.md` with question flow and FSM YAML template
3. Implement skill introspection logic (list skills, read SKILL.md, extract description/tools)
4. Implement project-config-aware evaluation generation (read ll-config.json tool commands)
5. Add harness-specific templates to `templates.md` (optional, for template creation mode)
6. Test by generating harnesses for `refine-issue` and `check-code` skills

## Impact

- **Priority**: P2 - Significant productivity gain for loop creation; builds on well-established infrastructure
- **Effort**: Medium - Primarily markdown authoring in loop-types.md with question flows; no runtime changes needed
- **Risk**: Medium - Evaluation quality is the key risk; auto-generated eval states may be too loose or strict
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM system architecture |
| `docs/reference/API.md` | FSM module API reference |

## Labels

`fsm-loops`, `create-loop`, `automation`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b28391f-b086-4d28-86cb-448201c8b40e.jsonl`
- `/ll:format-issue` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/611a4ae6-c639-4f26-8bd4-6c9cc190fff8.jsonl`
- `/ll:verify-issues` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/611a4ae6-c639-4f26-8bd4-6c9cc190fff8.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/611a4ae6-c639-4f26-8bd4-6c9cc190fff8.jsonl`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P2
