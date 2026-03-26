---
id: ENH-896
type: ENH
priority: P2
status: open
discovered_date: 2026-03-26
discovered_by: capture-issue
---

# ENH-896: Migrate ll Runtime Files from `.claude/` to `.ll/` Directory

## Summary

Claude Code now enforces extra restrictions on editing files in `.claude/` without explicit user approval. All little-loops runtime and configuration files currently written to `.claude/` must be moved to a new `.ll/` directory, created on `install` or `init`.

Files to migrate (at minimum):
- `ll-config.json`
- `ll-context-state.json`
- `ll-continue-prompt.md`
- `ll-update-docs.watermark`
- `ll-sync-state.json`
- `ll-goals.md`
- `ll-precompact-state.json`
- `.ll-lock`
- `ll.local.md`
- `loop-suggestions/` (directory)

## Current Behavior

All ll runtime and configuration files are written to `.claude/`:
- `hooks/scripts/context-monitor.sh` writes `.claude/ll-context-state.json` and `.claude/ll-precompact-state.json`
- `hooks/scripts/session-cleanup.sh` deletes `.claude/.ll-lock` and `.claude/ll-context-state.json`
- `hooks/scripts/session-start.sh` reads `.claude/ll-config.json` and `.claude/ll.local.md`
- `scripts/little_loops/subprocess_utils.py` hardcodes `CONTINUATION_PROMPT_PATH = Path(".claude/ll-continue-prompt.md")`
- `scripts/little_loops/config/features.py` defaults `state_file` to `.claude/ll-sync-state.json`
- `scripts/little_loops/config/core.py` reads from `.claude/ll-config.json`
- `commands/loop-suggester.md` writes to `.claude/loop-suggestions/`
- `skills/update-docs/SKILL.md` writes `.claude/ll-update-docs.watermark`
- `skills/init/SKILL.md` creates `.claude/ll-config.json`, `.claude/ll-goals.md`
- `skills/manage-issue/SKILL.md` writes `.claude/ll-continue-prompt.md`

This causes every write to trigger a Claude Code permission prompt, blocking automated hooks and inline skill execution.

## Expected Behavior

A `.ll/` directory at the project root stores all little-loops runtime and configuration files. The directory is:
- Created automatically on `ll-init` / first run
- Added to `.gitignore` (runtime state files) with `ll-config.json` tracked
- Listed in settings permission `allow` as `Write(.ll/*)` instead of individual `.claude/` paths

All references across hooks, Python scripts, commands, and skills are updated to use `.ll/` paths.

## Motivation

Claude Code's new `.claude/` write restrictions mean every hook write (context-monitor, session-cleanup, precompact-state) now requires user approval, breaking the automated flow. Moving to `.ll/` removes the restriction entirely since `.ll/` is not a protected directory. This unblocks silent background operation of all hooks and eliminates repeated permission prompts during normal workflow.

## Scope Boundaries

- **In scope**: All `.claude/ll-*` path references in hook scripts, Python source (`subprocess_utils.py`, `config/core.py`, `config/features.py`), skills, commands, tests, and documentation
- **In scope**: Creating `.ll/` directory on `init` and hook startup via `mkdir -p .ll/` guard in `common.sh`
- **In scope**: Updating `.gitignore` patterns (ignore runtime state files, keep `ll-config.json` tracked)
- **In scope**: Replacing `Write(.claude/ll-continue-prompt.md)` permission with `Write(.ll/*)` in settings templates
- **Out of scope**: Moving `.claude/settings.json`, `CLAUDE.md`, or any Claude Code core configuration files
- **Out of scope**: Changing the `.claude/` directory structure for non-ll files
- **Out of scope**: Backward compatibility shim — users must move existing files or re-run `init`

## Success Metrics

- Zero permission prompts during automated hook execution (context-monitor, session-cleanup, precompact-state) after migration
- All existing tests pass: `python -m pytest scripts/tests/ -v`
- `ll-config.json` is tracked in git at `.ll/ll-config.json`
- No orphaned references: `grep -r "\.claude/ll-" . --include="*.md" --include="*.py" --include="*.sh"` returns 0 results in source files after migration

## Proposed Solution

1. Create a `.ll/` directory convention with a `mkdir -p .ll/` call in `init` and hook startup
2. Update all hardcoded `.claude/ll-*` paths to `.ll/` in:
   - `hooks/scripts/*.sh` (all 4 hook scripts + `lib/common.sh`)
   - `scripts/little_loops/subprocess_utils.py` (`CONTINUATION_PROMPT_PATH`)
   - `scripts/little_loops/config/core.py` (config loading path)
   - `scripts/little_loops/config/features.py` (`state_file` default)
3. Update all skill and command docs referencing `.claude/ll-*` paths
4. Update `skills/init/SKILL.md` to create `.ll/ll-config.json` and add `.ll/` to permissions
5. Update `skills/configure/areas.md` to replace `Write(.claude/ll-continue-prompt.md)` with `Write(.ll/ll-continue-prompt.md)`
6. Update `.gitignore` templates and `ll-issues next-id` gitignore suggestions
7. Add `.ll/` creation to `hooks/scripts/lib/common.sh` startup guard

## API/Interface

N/A - No public API changes. Path constants (`CONTINUATION_PROMPT_PATH`, `state_file` default, `LL_CONFIG_FILE`) are internal implementation details and not part of any public interface.

## Integration Map

### Files to Modify

**Hook scripts:**
- `hooks/scripts/context-monitor.sh` - STATE_FILE, ll-precompact-state.json, ll-continue-prompt.md
- `hooks/scripts/session-cleanup.sh` - .ll-lock, ll-context-state.json, ll-config.json path
- `hooks/scripts/session-start.sh` - ll-config.json, ll.local.md, ll-goals.md
- `hooks/scripts/precompact-state.sh` - ll-continue-prompt.md
- `hooks/scripts/lib/common.sh` - LL_CONFIG_FILE default

**Python source:**
- `scripts/little_loops/subprocess_utils.py` - CONTINUATION_PROMPT_PATH constant
- `scripts/little_loops/config/core.py` - config file path
- `scripts/little_loops/config/features.py` - state_file default

**Skills/Commands:**
- `skills/init/SKILL.md` - create .ll/ instead of .claude/
- `skills/init/interactive.md` - references to .claude/ll-config.json
- `skills/configure/SKILL.md` - config file path references
- `skills/configure/areas.md` - Write(.claude/ll-continue-prompt.md) permission
- `skills/configure/show-output.md` - state_file display
- `skills/manage-issue/SKILL.md` - ll-continue-prompt.md path
- `skills/manage-issue/templates.md` - ll-continue-prompt.md path
- `skills/update-docs/SKILL.md` - ll-update-docs.watermark path
- `skills/update-docs/templates.md` - ll-update-docs.watermark path
- `skills/product-analyzer/SKILL.md` - ll-goals.md path
- `commands/loop-suggester.md` - loop-suggestions/ output path
- `hooks/prompts/continuation-prompt-template.md` - ll-continue-prompt.md references

**Tests:**
- `scripts/tests/test_subprocess_utils.py` - hardcoded .claude/ll-continue-prompt.md assertions
- `scripts/tests/test_hooks_integration.py` - config path assertions
- `scripts/tests/test_config.py` - state_file default assertion
- `scripts/tests/test_merge_coordinator.py` - ll-context-state.json path

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/merge_coordinator.py` - checks `ll-context-state.json` path
- `scripts/little_loops/issue_manager.py` - references ll-continue-prompt.md in comment
- `scripts/little_loops/cli/sync.py` - references .claude/ll-config.json in error message

### Similar Patterns

- Existing `.claude/` → project root migration: none in this repo, but `loop-suggestions/` was `.claude/loop-suggestions/` from the start

### Tests

- `scripts/tests/test_subprocess_utils.py:187` - asserts `CONTINUATION_PROMPT_PATH == Path(".claude/ll-continue-prompt.md")`
- `scripts/tests/test_hooks_integration.py:1042` - asserts config path is `.claude/ll-config.json`
- `scripts/tests/test_config.py:893` - asserts `state_file == ".claude/ll-sync-state.json"`

### Documentation

- `docs/reference/COMMANDS.md` - loop-suggestions output path
- `docs/generalized-fsm-loop.md` - loop-suggestions path reference
- `docs/guides/GETTING_STARTED.md` - likely references .claude/ll-config.json
- `CONTRIBUTING.md` - setup instructions
- `CLAUDE.md` - project instructions referencing .claude/ll-config.json

### Configuration

- `hooks/hooks.json` - may need `.ll/` write permission entry
- `.claude/settings.json` - replace `Write(.claude/ll-continue-prompt.md)` with `Write(.ll/*)`
- `.gitignore` - update patterns from `.claude/ll-*` to `.ll/` (keep ll-config.json tracked)

## Implementation Steps

1. **Create `.ll/` directory convention** - add `mkdir -p .ll/` guard to `hooks/scripts/lib/common.sh` and `skills/init/SKILL.md`
2. **Update Python source** - change hardcoded paths in `subprocess_utils.py`, `config/core.py`, `config/features.py`
3. **Update hook scripts** - replace all `.claude/ll-*` and `.claude/.ll-lock` references in 4 hook scripts
4. **Update skills and commands** - find/replace `.claude/ll-` with `.ll/` across all skill/command docs
5. **Update `.gitignore`** - adjust patterns; keep `ll-config.json` tracked, ignore runtime state files
6. **Update permissions** - replace `Write(.claude/ll-continue-prompt.md)` with `Write(.ll/*)` in settings templates and configure/areas.md
7. **Update tests** - fix hardcoded path assertions
8. **Add migration note** - add upgrade note to CHANGELOG for existing users to move files

## Impact

- **Priority**: P2 - Functional blocker for hook-based automation under new Claude Code restrictions
- **Effort**: Medium - Many files to update but changes are mechanical find/replace
- **Risk**: Medium - Wide surface area; need to catch all references. Tests will catch regressions.
- **Breaking Change**: Yes - Existing `.claude/ll-config.json` won't be auto-detected after upgrade; users need to move it or init will re-create it

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`, `hooks`, `config`, `breaking-change`

## Status

**Open** | Created: 2026-03-26 | Priority: P2

---

## Session Log
- `/ll:format-issue` - 2026-03-26T21:14:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/184fd12a-1de3-4eba-9d21-0c994ea1a12d.jsonl`
- `/ll:capture-issue` - 2026-03-26T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09734997-4b5e-4d15-a3cc-89e8eb882723.jsonl`
