# BUG-402: Commands reference $ARGUMENTS inconsistently - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P4-BUG-402-commands-reference-arguments-inconsistently.md`
- **Type**: bug
- **Priority**: P4
- **Action**: fix

## Current State Analysis

Six command files declare `arguments:` in frontmatter but lack `$ARGUMENTS` in their body. The 21 other commands that accept arguments all follow an established pattern: `## Arguments` section with `$ARGUMENTS` placeholder, placed after all process instructions and before `## Examples`, bounded by `---` horizontal rules.

### Key Discoveries
- All 21 correctly-implemented commands use identical placement: `---` / `## Arguments` / `$ARGUMENTS` / parameter descriptions / `---` / `## Examples`
- The 6 affected commands use bash-style variable references (`${area}`, `${name}`, etc.) that rely on implicit append behavior
- `sync_issues.md` has an existing `## Arguments` section (line 44) but lacks `$ARGUMENTS`

## Desired End State

All 6 commands have `$ARGUMENTS` placed in a `## Arguments` section following the established pattern, positioned after process instructions and before `## Examples`.

### How to Verify
- Grep all command files for `arguments:` in frontmatter and confirm all have `$ARGUMENTS` in body
- Commands remain functional with and without arguments

## What We're NOT Doing
- Not changing bash-style variable references in process sections — they are pseudo-code for Claude
- Not modifying `docs/COMMANDS.md` — the convention is self-documenting
- Not changing any of the 21 already-correct commands

## Solution Approach

For each of the 6 affected commands, add an `## Arguments` section with `$ARGUMENTS` following the established pattern. Place it between the last process/content section and the `## Examples` section.

## Implementation Phases

### Phase 1: Add $ARGUMENTS to all 6 command files

#### Changes Required

**1. `commands/configure.md`**
Insert between line 1015 (`---`) and line 1017 (`## Examples`):
```markdown
## Arguments

$ARGUMENTS

- **area** (optional): Configuration area to modify
  - `project` - Test, lint, format, type-check, build commands
  - `issues` - Base dir, categories, templates, capture style
  - `parallel` - ll-parallel: workers, timeouts, worktree files
  - `automation` - ll-auto: workers, timeouts, streaming
  - `documents` - Key document categories for issue alignment
  - `continuation` - Session handoff: auto-detect, includes, expiry
  - `context` - Context monitoring: threshold, limits
  - `prompt` - Prompt optimization: mode, confirm, bypass
  - `scan` - Focus dirs, exclude patterns
  - `sync` - GitHub Issues sync: enabled, label mapping, priorities

- **flags** (optional): Command behavior flags
  - `--list` - Display all configuration areas with status
  - `--show` - Display current values for specified area
  - `--reset` - Remove section from config, reverting to defaults

---
```

**2. `commands/create_sprint.md`**
Insert between line 451 (end of Examples section — actually before `## Examples` at line 453):
```markdown
## Arguments

$ARGUMENTS

- **name** (optional): Sprint name following `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` pattern
  - If omitted, prompted interactively or derived from auto-grouping

- **description** (optional): Human-readable description of the sprint's purpose

- **issues** (optional): Comma-separated list of issue IDs to include
  - Example: `BUG-001,FEAT-010,ENH-042`
  - If omitted, issues are selected interactively or via auto-grouping

---
```

**3. `commands/handoff.md`**
Insert before `## Examples` section:
```markdown
## Arguments

$ARGUMENTS

- **context** (optional): Brief description of current work context
  - Provides a hint for the conversation summary
  - Example: `"Refactoring authentication module"`

- **flags** (optional): Command behavior flags
  - `--deep` - Validate and enrich with git status, todos, recent files

---
```

**4. `commands/resume.md`**
Insert before `## Examples` section:
```markdown
## Arguments

$ARGUMENTS

- **prompt_file** (optional, default: `.claude/ll-continue-prompt.md`): Path to continuation prompt file
  - If provided, reads from specified path
  - If omitted, checks default location then falls back to state file

---
```

**5. `commands/sync_issues.md`**
Replace existing `## Arguments` section (lines 44-48) with:
```markdown
## Arguments

$ARGUMENTS

- **action** (required): `push`, `pull`, or `status`
- **issue_id** (optional): Specific issue ID to sync (e.g., `BUG-123`)
  - If omitted, syncs all issues
```

**6. `commands/toggle_autoprompt.md`**
Insert before `## Examples` section:
```markdown
## Arguments

$ARGUMENTS

- **setting** (optional, default: `status`): Setting to toggle
  - `status` - Display current settings
  - `enabled` - Toggle auto-optimization on/off
  - `mode` - Toggle between quick and thorough mode
  - `confirm` - Toggle confirmation prompts on/off

---
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -rn '\$ARGUMENTS' commands/configure.md` returns a match
- [ ] `grep -rn '\$ARGUMENTS' commands/create_sprint.md` returns a match
- [ ] `grep -rn '\$ARGUMENTS' commands/handoff.md` returns a match
- [ ] `grep -rn '\$ARGUMENTS' commands/resume.md` returns a match
- [ ] `grep -rn '\$ARGUMENTS' commands/sync_issues.md` returns a match
- [ ] `grep -rn '\$ARGUMENTS' commands/toggle_autoprompt.md` returns a match
- [ ] All command files with `arguments:` in frontmatter also have `$ARGUMENTS` in body
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

- Verify all 6 files contain `$ARGUMENTS` via grep
- Cross-check: no command with `arguments:` frontmatter is missing `$ARGUMENTS` in body

## References

- Original issue: `.issues/bugs/P4-BUG-402-commands-reference-arguments-inconsistently.md`
- Pattern reference: `commands/run_tests.md:135-147` (standard $ARGUMENTS section)
- Pattern reference: `commands/manage_issue.md:689-718` (complex multi-argument)
