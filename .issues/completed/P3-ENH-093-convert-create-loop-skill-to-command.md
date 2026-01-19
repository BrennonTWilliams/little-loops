# Convert create-loop Skill to Slash Command

## Summary

The `/ll:create-loop` functionality is currently implemented as a Skill but should be a Slash Command based on its usage pattern.

## Current State

- Location: `skills/create-loop/SKILL.md`
- ~500 lines of detailed workflow instructions
- Interactive wizard using `AskUserQuestion`
- Only user-triggered (never auto-triggered)

## Rationale

Per the plugin-dev documentation:

| Aspect | Skills | Commands |
|--------|--------|----------|
| Primary purpose | Specialized knowledge/domain expertise | Frequently-used prompts/workflows |
| Triggering | Auto-triggered by keywords OR user-invoked | User-invoked only |
| Design model | "Onboarding guide" - provides knowledge | "Instructions for Claude" - what to do |

**Why Command is better fit:**

1. **Only user-triggered** - Skills are designed for auto-triggering based on context keywords. This wizard is only manually invoked.

2. **It's a workflow, not domain knowledge** - The create-loop wizard is a specific procedure to execute, not specialized knowledge that Claude references while working on other tasks.

3. **Single responsibility** - Commands are explicitly for "one command, one task" - fits an interactive wizard.

4. **Simpler structure** - Commands are the standard pattern for user-invoked functionality.

## Implementation Plan

1. Create `commands/create_loop.md` with:
   - Frontmatter (description, argument-hint if needed)
   - Core workflow instructions
   - Reference to detailed paradigm templates if needed

2. Consider extracting verbose paradigm templates to a reference file:
   - `docs/create-loop-paradigms.md` or similar
   - Command can use `@${CLAUDE_PLUGIN_ROOT}/docs/...` to include

3. Remove `skills/create-loop/` directory

4. Update any documentation referencing the skill

## Acceptance Criteria

- [x] `/ll:create-loop` works as a command
- [x] Interactive wizard flow preserved
- [x] All four paradigms supported (goal, invariants, convergence, imperative)
- [x] Skill directory removed
- [x] Documentation updated

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-18
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Created new command file with full wizard workflow (518 lines)
- `skills/create-loop/`: Removed entire skill directory
- `docs/generalized-fsm-loop.md`: Updated references from "skill" to "command"

### Verification Results
- Tests: PASS (1345 passed)
- Lint: PASS (ruff check scripts/)
- Types: PASS (mypy scripts/little_loops/)
