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
2. **Checks reference**: `skills/review-loop/reference.md` - catalog of all checks with severity and fix templates (following `skills/create-loop/reference.md` naming convention)
3. **Workflow**:
   - Step 0: Resolve loop name (argument or `AskUserQuestion` to pick from `ll-loop list`)
   - Step 1: Load YAML via `Read`, detect if paradigm or raw FSM (discriminator: has `paradigm` but lacks `initial`)
   - Step 2a: Run `ll-loop validate <name>` as a first pass — surfaces ERROR/WARNING `ValidationError` objects from `validate_fsm()` at `validation.py:194-303`
   - Step 2b: Run quality checks from `reference.md` that `ll-loop validate` doesn't cover (max_iterations values, missing `on_error`, action_type mismatches, capture suggestions)
   - Step 3: Display findings grouped by severity (Error, Warning, Suggestion)
   - Step 4: For each proposed change, show diff and ask approval
   - Step 5: Apply approved changes and write file
   - Step 6: Run `ll-loop validate <name>` to confirm result is valid

## Integration Map

### Files to Modify
- `skills/review-loop/SKILL.md` (new) — interactive review workflow
- `skills/review-loop/reference.md` (new) — catalog of all checks with severity levels and fix templates
- `docs/guides/LOOPS_GUIDE.md` — add `/ll:review-loop` to CLI Quick Reference table
- `skills/create-loop/SKILL.md` — add cross-reference in Step 5 success message

> **Note**: No changes to `.claude-plugin/plugin.json` — skills are auto-discovered from the `./skills/` directory. Creating `skills/review-loop/SKILL.md` is sufficient for registration.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` handles name resolution; searches `<loops_dir>/<name>.fsm.yaml`, then `<loops_dir>/<name>.yaml`, then the built-in `loops/` directory
- `scripts/little_loops/fsm/validation.py:194-303` — `validate_fsm()` returns all `ValidationIssue` objects with `severity` (ERROR/WARNING); the skill's first-pass check should invoke `ll-loop validate` to surface these before adding quality checks
- `scripts/little_loops/cli/loop/info.py:22-34` — `_load_loop_meta()` reads `paradigm` and `description` fields quickly without full parse; useful for the loop-selection list

### Similar Patterns
- `skills/create-loop/SKILL.md` — primary Skill structure pattern to follow (numbered steps, AskUserQuestion wizards, `ll-loop validate` invocation at end)
- `commands/ready-issue.md` — quality-review pattern: severity-grouped findings table, per-finding approval, auto-correction with `--auto` flag (this is a flat command, not a skill directory)
- `skills/audit-claude-config/SKILL.md:562-590` — CRITICAL/WARNING/SUGGESTION severity rendering pattern
- `skills/issue-size-review/SKILL.md:97-110` — per-item `AskUserQuestion` approval loop pattern

### Tests
- `scripts/tests/test_review_loop.py` (new) — modeled on `test_create_loop.py`; suggested test classes:
  - `TestReviewLoopChecks` — validate each quality check detects the target issue using `validate_fsm()` + fixture YAMLs
  - `TestReviewLoopAutoFix` — verify `--auto` applies non-breaking fixes and `ll-loop validate` passes after
  - `TestReviewLoopDryRun` — verify `--dry-run` produces no file writes
  - Use fixture files from `scripts/tests/fixtures/fsm/` including `loop-with-unreachable-state.yaml`
  - Use factory helpers from `test_ll_loop_errors.py:24-72` (`make_test_fsm`, `make_test_state`)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add `/ll:review-loop` to CLI Quick Reference table

### Configuration
- N/A — reads from existing `loops.loops_dir` config (default `.loops`, defined in `config-schema.json:606-617`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Format detection** (`cli/loop/config_cmds.py:70`): paradigm format = YAML has `"paradigm"` key but lacks `"initial"` key. Raw FSM format = has `"initial"` (regardless of `"paradigm"` presence). The skill must branch its check logic on this discriminator.
- **`validate_fsm` already covers** (`validation.py:194-303`): unreachable states, missing outgoing transitions on non-terminal states, evaluator required fields, `max_iterations > 0`, invalid state references. Returns `list[ValidationError]` (class at `validation.py:38`). The skill should run `ll-loop validate` first and present those findings, then layer its own quality checks (e.g., suspiciously high `max_iterations`, missing `on_error` routing, `action_type` mismatches).
- **`ValidationSeverity` enum** (`validation.py`) already has `ERROR`/`WARNING` tiers; the skill's quality checks can introduce a third tier (`SUGGESTION`) for improvements that aren't correctness issues.
- **Built-in loop examples** at `loops/issue-refinement.yaml` and `loops/fix-quality-and-tests.yaml` — both use `paradigm: fsm` with explicit `initial`, making them raw FSM format despite the `paradigm` field. Good reference for what production loops look like.
- **User loop example** at `.loops/issue-refinement-git.yaml` — real project loop for reference.

## Implementation Steps

1. Create `skills/review-loop/reference.md` cataloging all FSM quality checks with severity levels and fix templates (following `skills/create-loop/reference.md` structure)
2. Create `skills/review-loop/SKILL.md` implementing the interactive review workflow, structured like `skills/create-loop/SKILL.md` with numbered steps and AskUserQuestion approval loops (see `skills/issue-size-review/SKILL.md:97-110` for the per-item approval pattern)
3. Update `docs/guides/LOOPS_GUIDE.md` to add `/ll:review-loop` to the CLI Quick Reference table
4. Add cross-reference from `skills/create-loop/SKILL.md` (Step 5 success message) suggesting `/ll:review-loop` after creation
5. Write `scripts/tests/test_review_loop.py` using `make_test_fsm`/`make_test_state` helpers from `test_ll_loop_errors.py:24-72` and fixtures from `scripts/tests/fixtures/fsm/`

> No changes to `.claude-plugin/plugin.json` needed — skills are auto-discovered from `./skills/`.

## Impact

- **Priority**: P3 - Improves loop quality and user confidence; not blocking but high value for users with growing loop libraries
- **Effort**: Medium - New skill following established patterns; main complexity is the checks catalog
- **Risk**: Low - Read-only analysis by default; writes only with explicit user approval
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/create-loop/reference.md` | FSM compilation reference; structure template for `review-loop/reference.md` |
| `skills/create-loop/SKILL.md` | Primary Skill structure pattern to follow |
| `commands/ready-issue.md` | Quality-review command pattern (severity grouping, per-finding approval, `--auto`) |
| `scripts/little_loops/fsm/validation.py:194-303` | `validate_fsm()` — first-pass check; review skill layers on top of this |
| `scripts/little_loops/cli/loop/_helpers.py:86-107` | `resolve_loop_path()` — how to find loop files by name |
| `docs/guides/LOOPS_GUIDE.md` | Loop system overview and evaluator reference |

## Labels

`feature`, `loops`, `developer-experience`, `captured`

## Resolution

**Status**: Completed
**Completed**: 2026-03-09

### Changes Made

- Created `skills/review-loop/SKILL.md` — interactive 6-step review workflow (Step 0: resolve name, Step 1: load+detect format, Step 2a: ll-loop validate first pass, Step 2b: quality checks QC-1 through QC-7, Step 3: findings display, Step 4: fix approval, Step 5: write+validate, Step 6: summary)
- Created `skills/review-loop/reference.md` — catalog of all quality checks (V-series from validate_fsm, QC-1 through QC-7 skill-specific), fix templates, auto-apply rules
- Updated `docs/guides/LOOPS_GUIDE.md` — added `/ll:review-loop` to Further Reading section
- Updated `skills/create-loop/SKILL.md` — added `/ll:review-loop` cross-reference tip in Step 6 success messages
- Created `scripts/tests/test_review_loop.py` — 36 tests across TestReviewLoopChecks (V-series via validate_fsm), TestReviewLoopQualityChecks (QC heuristic logic), TestReviewLoopAutoFix, TestReviewLoopDryRun

### Acceptance Criteria

- [x] Command accepts an optional loop name argument; if omitted, shows a list to select from
- [x] Loads loop from `.loops/<name>.yaml` (or configured `loops_dir`)
- [x] Detects and reports check categories: Structure, Error handling, Configuration, Action quality, Best practices
- [x] Uses `AskUserQuestion` for ambiguous findings
- [x] Groups findings by severity: Error, Warning, Suggestion
- [x] Proposes concrete YAML changes with before/after diff display
- [x] Asks user approval before writing any change
- [x] Supports `--auto` flag for non-interactive mode
- [x] Works with both paradigm YAML and raw FSM YAML

## Session Log

- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e68dcdd-ad82-4f6e-bd53-991924de9cc1.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/193aaada-601b-494a-b190-36540128d028.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bc8b254-8ac0-409d-b79d-9795de6dc39e.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8b2b96f-f861-4b5d-90ff-b3c03d39592f.jsonl`
- `/ll:manage-issue feature add FEAT-660` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

**Completed** | Created: 2026-03-09 | Priority: P3
