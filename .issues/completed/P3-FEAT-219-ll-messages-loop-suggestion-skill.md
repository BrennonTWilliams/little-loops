---
discovered_date: 2026-02-02
discovered_by: capture_issue
---

# FEAT-219: Agent Skill to suggest loops using ll-messages

## Summary

Create a new `/ll:` Agent Skill that uses `ll-messages` output to analyze user message history and suggest new FSM loops with 3-15 steps, bypassing the interactive `/ll:create-loop` wizard.

## Context

**Direct mode**: User description: "New `/ll:` Agent Skill that uses `ll-messages` to suggest new loops with 3-15 steps, bypassing `/ll:create-loop`"

The `/ll:create-loop` command provides an interactive wizard for creating FSM loops, but for users who have existing workflow patterns captured in their message history, an automated suggestion system would be more efficient.

## Current Behavior

- `/ll:create-loop` requires interactive wizard input to select paradigm, configure steps, and define evaluator behavior
- No automated analysis of existing message patterns to suggest loop configurations
- Users must manually identify repetitive workflows that could be automated as loops

## Expected Behavior

A new Agent Skill that:
1. Analyzes `ll-messages` output (user message history)
2. Identifies repetitive 3-15 step workflows
3. Suggests FSM loop configurations with:
   - Appropriate paradigm selection
   - Step definitions with tool usage
   - Evaluator configuration
   - Variable interpolation setup
4. Outputs ready-to-use loop YAML or prompts for approval

## Proposed Solution

Create a new Agent Skill `skills/loop-suggester/SKILL.md` that:

1. **Input**: User messages from `ll-messages` output (JSONL format)
2. **Analysis**: Identify repeated multi-step patterns (3-15 steps)
3. **Output**: Suggested loop YAML files with:
   - Paradigm (goal, state_machine, imperative, template)
   - Steps with tool usage patterns
   - Evaluator type and configuration
   - Max iterations based on observed behavior
   - On_handoff handler if applicable

### Key Features

- Bypass `/ll:create-loop` interactive wizard
- Suggest loops based on actual user behavior patterns
- Support all existing loop paradigms
- Generate valid YAML matching FSM schema
- Provide confidence scores for suggestions

### Integration Points

- Uses existing `ll-messages` CLI output
- Follows FSM schema from `scripts/little_loops/fsm/`
- Compatible with `ll-loop` execution engine
- Can pipe suggestions directly to loop files

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low - New skill, no changes to existing functionality

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents agents/skills structure |
| guidelines | .claude/CLAUDE.md | Development preferences (prefer Skills over Agents) |

## Labels

`feature`, `skill`, `fsm`, `loops`, `ll-messages`, `automation`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-02
- **Status**: Completed

### Changes Made
- `skills/loop-suggester/SKILL.md`: Created new skill with complete pattern detection and loop suggestion logic
- `thoughts/shared/plans/2026-02-02-FEAT-219-management.md`: Implementation plan

### Features Implemented
1. Input resolution from arguments or live ll-messages extraction
2. Pattern detection rules for all four FSM paradigms (goal, invariants, convergence, imperative)
3. Confidence scoring with frequency and session bonuses
4. YAML output schema with metadata, summary, and structured suggestions
5. Complete paradigm templates for generated loop configurations
6. Example suggestions demonstrating typical outputs
7. Guidelines and limitations documentation
8. Comparison with /ll:create-loop for user guidance

### Verification Results
- File structure: PASS (skill directory and SKILL.md created)
- Lint: PASS (no new issues introduced)
- FSM tests: PASS (433 passed)
- User messages tests: PASS (54 passed)

---

## Status

**Completed** | Created: 2026-02-02 | Completed: 2026-02-02 | Priority: P3
