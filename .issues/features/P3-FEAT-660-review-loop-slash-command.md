---
discovered_date: 2026-03-09
discovered_by: capture-issue
---

# FEAT-660: New `/ll:review-loop` Slash Command

## Summary

Add a `/ll:review-loop` slash command that analyzes an existing FSM loop configuration for quality, correctness, consistency, and potential improvements. The command inspects all states and transitions, identifies issues (unreachable states, missing error handling, poor naming, suboptimal structure), and proposes changes interactively with user approval before applying them.

## Current Behavior

There is no dedicated command for reviewing or auditing existing loop configurations. Users must manually inspect `.loops/*.yaml` files and cross-reference the FSM documentation to evaluate quality. The `ll-loop validate` CLI only checks schema correctness, not quality or best practices.

## Expected Behavior

Running `/ll:review-loop [name]` (or `/ll:review-loop` to select from a list) opens an interactive review session that:

1. Loads and parses the loop YAML
2. Analyzes FSM structure for correctness and quality issues
3. Presents findings by severity (errors, warnings, suggestions)
4. Uses `AskUserQuestion` for any ambiguous findings or decisions
5. Proposes specific changes with before/after diffs
6. Asks user for approval before writing any changes
7. Saves the updated loop file and reports what changed

## Motivation

Loop configurations can become complex over time, especially raw FSM YAML with many states. Without a review tool, quality issues accumulate silently:
- Unreachable states that waste iterations
- Missing `on_error` handlers that cause silent failures
- Overly high `max_iterations` values that let broken loops run indefinitely
- Inconsistent action types (e.g., shell commands used where prompts are needed)
- Loops that would benefit from `capture:` or `scope:` but don't use them

This command gives users the same quality guidance for loops that `/ll:ready-issue` gives for issues.

## Use Case

**Who**: A developer who has accumulated several FSM loop configurations over months of use

**Context**: Returning to a `fix-types` loop created 3 months ago before running it again — unsure if it still reflects current best practices or has structural gaps

**Goal**: Audit the loop for correctness and quality issues without manually cross-referencing FSM documentation

**Outcome**: The command identifies that `on_error` is missing from the evaluate state (so type-check crashes are silently treated as failures), proposes adding it with a before/after diff, and updates the loop file in place after user approval

## Acceptance Criteria

- [ ] Command accepts an optional loop name argument; if omitted, shows a list to select from
- [ ] Loads loop from `.loops/<name>.yaml` (or configured `loops_dir`)
- [ ] Detects and reports the following check categories:
  - **Structure**: Unreachable states, states with no outgoing transitions (non-terminal), missing initial state
  - **Error handling**: States missing `on_error` when using shell evaluators, convergence states without stall handling
  - **Configuration**: `max_iterations` suspiciously low (<3) or high (>100), missing `scope` when touching specific dirs
  - **Action quality**: Actions that look like prompts but lack `action_type: prompt`, shell commands with hardcoded paths
  - **Best practices**: States that could use `capture:` to pass data, suggestions for `on_handoff` in long loops
- [ ] Uses `AskUserQuestion` for ambiguous findings (e.g., "Is this action intentionally a shell command or a prompt?")
- [ ] Groups findings by severity: **Error** (correctness), **Warning** (best practice), **Suggestion** (improvement)
- [ ] Proposes concrete YAML changes with before/after diff display
- [ ] Asks user approval before writing any change
- [ ] Supports `--auto` flag for non-interactive mode (applies all non-breaking suggestions automatically)
- [ ] Works with both paradigm YAML and raw FSM YAML

## API/Interface

```bash
# Interactive review
/ll:review-loop [name]

# Non-interactive auto-fix mode
/ll:review-loop fix-types --auto

# Review without modifying (report only)
/ll:review-loop fix-types --dry-run
```

Skill file: `skills/review-loop/SKILL.md`
Command alias: `/ll:review-loop` -> `skills/review-loop/`

## Proposed Solution

Implement as a Skill (not an Agent) following the `create-loop` pattern:

1. **Skill file**: `skills/review-loop/SKILL.md` - defines the interactive workflow
2. **Checkers reference**: `skills/review-loop/checks.md` - catalog of all checks with severity and fix templates
3. **Workflow**:
   - Step 0: Resolve loop name (argument or `AskUserQuestion` to pick from `ll-loop list`)
   - Step 1: Load YAML via `Read`, detect if paradigm or raw FSM
   - Step 2: Run all applicable checks from `checks.md`
   - Step 3: Display findings grouped by severity
   - Step 4: For each proposed change, show diff and ask approval
   - Step 5: Apply approved changes and write file
   - Step 6: Run `ll-loop validate <name>` to confirm result is valid

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` (new)
- `skills/review-loop/checks.md` (new)
- `.claude-plugin/plugin.json` - register new skill
- `commands/help.md` or skill listing - add to help output

### Dependent Files (Callers/Importers)
- `skills/create-loop/SKILL.md` - could reference review-loop as a post-creation step
- `docs/guides/LOOPS_GUIDE.md` - mention new command in CLI Quick Reference

### Similar Patterns
- `skills/create-loop/` - same Skill structure pattern to follow
- `skills/ready-issue/` - similar quality-review pattern for issues
- `commands/audit-docs.md` - similar audit/review command pattern

### Tests
- `scripts/tests/test_review_loop.py` (new) - following `test_create_loop.py` pattern: validate that checks.md YAML examples produce expected findings, that `ll-loop validate` passes after auto-fixes are applied, and that `--dry-run` produces no file modifications

### Documentation
- `docs/guides/LOOPS_GUIDE.md` - add `/ll:review-loop` to CLI Quick Reference table

### Configuration
- N/A - reads from existing `loops_dir` config

## Implementation Steps

1. Create `skills/review-loop/checks.md` cataloging all FSM quality checks with severity levels and fix templates
2. Create `skills/review-loop/SKILL.md` implementing the interactive review workflow
3. Register skill in `.claude-plugin/plugin.json`
4. Update `docs/guides/LOOPS_GUIDE.md` to mention the new command
5. Add cross-reference from `skills/create-loop/SKILL.md` (Step 5 success message) suggesting review

## Impact

- **Priority**: P3 - Improves loop quality and user confidence; not blocking but high value for users with growing loop libraries
- **Effort**: Medium - New skill following established patterns; main complexity is the checks catalog
- **Risk**: Low - Read-only analysis by default; writes only with explicit user approval
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/create-loop/reference.md` | FSM compilation reference used by review checks |
| `skills/create-loop/SKILL.md` | Pattern to follow for skill structure |
| `docs/guides/LOOPS_GUIDE.md` | Loop system overview and evaluator reference |

## Labels

`feature`, `loops`, `developer-experience`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e68dcdd-ad82-4f6e-bd53-991924de9cc1.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/193aaada-601b-494a-b190-36540128d028.jsonl`

---

**Open** | Created: 2026-03-09 | Priority: P3
