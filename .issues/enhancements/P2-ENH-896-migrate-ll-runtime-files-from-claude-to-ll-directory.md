---
id: ENH-896
type: ENH
priority: P2
status: open
discovered_date: 2026-03-26
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 53
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
- `.claude/CLAUDE.md:10` - `**Project config**: `.claude/ll-config.json`` → `.ll/ll-config.json`
- `.claude/CLAUDE.md:11` - `**Local overrides**: `.claude/ll.local.md`` → `.ll/ll.local.md`

### Configuration

- `hooks/hooks.json` - may need `.ll/` write permission entry
- `.claude/settings.json` - replace `Write(.claude/ll-continue-prompt.md)` with `Write(.ll/*)`
- `.gitignore` - update patterns from `.claude/ll-*` to `.ll/` (keep ll-config.json tracked)
- `config-schema.json` — references `.claude/ll-` path defaults (not in issue originally)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Exact Line References — Python Source

- `scripts/little_loops/subprocess_utils.py:32` — `CONTINUATION_PROMPT_PATH = Path(".claude/ll-continue-prompt.md")` (module-level constant)
- `scripts/little_loops/subprocess_utils.py:56` — `(repo_path or Path.cwd()) / CONTINUATION_PROMPT_PATH` (usage in `read_continuation_prompt()`)
- `scripts/little_loops/config/core.py:74-75` — `CONFIG_DIR = ".claude"` and `CONFIG_FILENAME = "ll-config.json"` (class-level constants on `BRConfig`; change `CONFIG_DIR` to `".ll"`)
- `scripts/little_loops/config/core.py:89` — `config_path = self.project_root / self.CONFIG_DIR / self.CONFIG_FILENAME` (assembled from constants; no literal to change)
- `scripts/little_loops/config/features.py:213` — `state_file: str = ".claude/ll-sync-state.json"` (dataclass field default)
- `scripts/little_loops/config/features.py:226` — `state_file=data.get("state_file", ".claude/ll-sync-state.json")` (`from_dict` default — must update both)
- `scripts/little_loops/config/__init__.py` — also contains `.claude/ll-` references (not listed in issue originally; verify before updating)

#### Exact Line References — Hook Scripts

- `hooks/scripts/lib/common.sh:184-191` — `ll_resolve_config()` function; checks `.claude/ll-config.json` first, falls back to `ll-config.json` at project root
- `hooks/scripts/context-monitor.sh:29` — `STATE_FILE` default from `ll_config_value`
- `hooks/scripts/context-monitor.sh:157` — `[ -f ".claude/ll-continue-prompt.md" ]` existence check
- `hooks/scripts/context-monitor.sh:186,244` — `precompact_file=".claude/ll-precompact-state.json"` and `rm -f` on same path
- `hooks/scripts/context-monitor.sh:316` — `HANDOFF_FILE=".claude/ll-continue-prompt.md"`
- `hooks/scripts/session-cleanup.sh:14` — `rm -f ".claude/.ll-lock" ".claude/ll-context-state.json"` (bare literals)
- `hooks/scripts/session-cleanup.sh:20` — `CONFIG_FILE=".claude/ll-config.json"` for jq read
- `hooks/scripts/session-start.sh:13` — `rm -f ".claude/ll-context-state.json"` at script top
- `hooks/scripts/session-start.sh:16` — `CONFIG_FILE=".claude/ll-config.json"` variable
- `hooks/scripts/session-start.sh:21` — `LOCAL_FILE=".claude/ll.local.md"` variable
- `hooks/scripts/session-start.sh:65,75` — paths inside embedded Python heredoc
- `hooks/scripts/session-start.sh:139` — `'.product.goals_file // ".claude/ll-goals.md"'` in jq expression
- `hooks/scripts/precompact-state.sh:28` — **KEY**: `STATE_DIR=".claude"` (change to `.ll`; lines 29-30, 33, 82 are all derived from this)
- `hooks/scripts/precompact-state.sh:29-30` — `PRECOMPACT_STATE_FILE="${STATE_DIR}/ll-precompact-state.json"` and `CONTEXT_STATE_FILE="${STATE_DIR}/ll-context-state.json"` (derived — fixed by STATE_DIR change)
- `hooks/scripts/precompact-state.sh:33` — `mkdir -p "$STATE_DIR"` (creates the directory — will auto-create `.ll/`)
- `hooks/scripts/precompact-state.sh:66` — `CONTINUE_PROMPT=".claude/ll-continue-prompt.md"` (hardcoded, not derived from STATE_DIR — must update separately)
- `hooks/scripts/precompact-state.sh:82` — hardcoded path in echo message string
- `hooks/scripts/user-prompt-check.sh` and `hooks/scripts/check-duplicate-issue-id.sh` — consume `$LL_CONFIG_FILE` set by `common.sh`; **no hardcoded paths** — automatically correct after `common.sh` update

#### Additional Files to Modify (Not in Issue Originally)

- `commands/handoff.md` — references `.claude/ll-continue-prompt.md`
- `commands/resume.md` — references `.claude/ll-continue-prompt.md`
- `skills/create-loop/loop-types.md` — references `.claude/ll-config.json`
- `scripts/little_loops/config/__init__.py` — contains `.claude/ll-` path references

**Commands — runtime reads (all `commands/*.md` files with runtime `.claude/ll-config.json` reads):**
- `commands/handoff.md:25,122,195` — reads ll-config.json for settings; writes ll-continue-prompt.md at runtime
- `commands/resume.md:8,18,26,31,32,33,151` — runtime shell var `PROMPT_FILE="${prompt_file:-.claude/ll-continue-prompt.md}"`; reads ll-config.json for prompt_expiry_hours
- `commands/tradeoff-review-issues.md:26` — numbered step "Read `.claude/ll-config.json`"
- `commands/toggle-autoprompt.md:68,84` — reads AND writes ll-config.json (core purpose)
- `commands/create-sprint.md:25,39,41,198` — "Use the Read tool to read `.claude/ll-config.json`"
- `commands/scan-product.md:17,52,74` — reads ll-config.json; resolves `product.goals_file` default `.claude/ll-goals.md`
- `commands/align-issues.md:25,34` — conditional check on ll-config.json
- `commands/manage-release.md:33` — "Read settings from `.claude/ll-config.json`"
- All remaining commands (`find-dead-code`, `scan-codebase`, `check-code`, `normalize-issues`, `cleanup-worktrees`, `verify-issues`, `prioritize-issues`, `ready-issue`, `run-tests`, `review-sprint`, `audit-architecture`, `refine-issue`) — `## Configuration` boilerplate "uses project configuration from `.claude/ll-config.json`" (update for accuracy)
- `skills/create-loop/loop-types.md:607` — runtime read of ll-config.json for test_cmd/lint_cmd/type_cmd detection

#### Loop YAML Files — Runtime Paths (Not in Issue Originally, MUST Update)

These are Python inline scripts inside FSM loop YAML files that construct the config path at runtime:

- `scripts/little_loops/loops/fix-quality-and-tests.yaml:70` — `p = pathlib.Path('.claude/ll-config.json')`
- `scripts/little_loops/loops/evaluation-quality.yaml:46` — `p = pathlib.Path('.claude/ll-config.json')`
- `scripts/little_loops/loops/rl-coding-agent.yaml:53,61` — `p = pathlib.Path('.claude/ll-config.json')` (appears twice)
- `scripts/little_loops/loops/dead-code-cleanup.yaml:67` — `p = pathlib.Path('.claude/ll-config.json')`
- `scripts/little_loops/loops/harness-single-shot.yaml:60` — `p = pathlib.Path('.claude/ll-config.json')`
- `scripts/little_loops/loops/harness-multi-item.yaml:88` — `p = pathlib.Path('.claude/ll-config.json')`
- `scripts/little_loops/loops/context-health-monitor.yaml:22` — `.claude/ll-context-state.json`

All 7 files need the path literal updated. Pattern: change `'.claude/ll-config.json'` to `'.ll/ll-config.json'` and `.claude/ll-context-state.json` to `.ll/ll-context-state.json`.

#### `config-schema.json` — Exact Line Numbers (mentioned in note above, now with lines)

- Line 502 (`context_monitor.state_file` default): `".claude/ll-context-state.json"` → `".ll/ll-context-state.json"`
- Line 582 (`product.goals_file` default): `".claude/ll-goals.md"` → `".ll/ll-goals.md"`
- Line 795 (`sync.github.state_file` default): `".claude/ll-sync-state.json"` → `".ll/ll-sync-state.json"`

#### `skills/configure/areas.md` — Exact Line Numbers

- Line 779: `Write(.claude/ll-continue-prompt.md)` in option label text → `Write(.ll/ll-continue-prompt.md)`
- Line 788: prose instruction "Remove any existing `Write(.claude/ll-continue-prompt.md)` entry" → updated path
- Line 792: "remove ... any `Write(.claude/ll-continue-prompt.md)` entry" → updated path

#### `.claude/settings.local.json` — Live Settings File (Not `settings.json`)

`.claude/settings.json` does not exist in this repo. The active settings file is `.claude/settings.local.json`.

- Line 25: `"Write(.claude/ll-continue-prompt.md)"` → `"Write(.ll/ll-continue-prompt.md)"`

This is the currently-installed permission entry. The issue's Integration Map and Proposed Solution reference `Write(.claude/ll-continue-prompt.md)` in `.claude/settings.json` — the correct target is `settings.local.json`.

#### `scripts/little_loops/config/__init__.py` — Confirmed Documentation Only

- Line 4: module docstring `Configuration is read from .claude/ll-config.json` — update for accuracy, no runtime impact

#### Additional Documentation Files (Not in Issue Originally)

- `docs/reference/CONFIGURATION.md` — documents `.claude/ll-config.json` and `.claude/ll-sync-state.json`
- `docs/reference/API.md` — references `.claude/ll-` paths
- `docs/reference/CLI.md` — references `.claude/ll-config.json`
- `docs/guides/SESSION_HANDOFF.md` — references `.claude/ll-continue-prompt.md` and `.claude/ll-context-state.json`
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `.claude/ll-config.json`
- `docs/guides/SPRINT_GUIDE.md` — references `.claude/ll-config.json`
- `docs/ARCHITECTURE.md` — references `.claude/ll-context-state.json`
- `docs/development/TROUBLESHOOTING.md` — references `.claude/ll-context-state.json` and `.claude/ll-precompact-state.json`
- `docs/demo/README.md:11` — references `.claude/ll-context-state.json` in cleanup description
- `docs/research/claude-cli-integration-mechanics.md:90,189` — research doc; references `CONTINUATION_PROMPT_PATH` and `.claude/ll-context-state.json` (low-priority update for accuracy)
- `README.md` — references `.claude/ll-` paths
- `CHANGELOG.md` — add migration note under `## [Unreleased]` using `### Changed` or `### Migration` header (format: Keep a Changelog 1.1.0)

#### Additional Skills/Commands Not in Integration Map

- `skills/audit-claude-config/SKILL.md:50,236` — hardcodes `.claude/ll-config.json` path in table cell and validation checklist (runtime reads); update both lines
- `skills/capture-issue/SKILL.md:28,269,275` — boilerplate Configuration header + two runtime reads of `ll-config.json` for `documents` feature; update for accuracy
- `skills/capture-issue/templates.md:224` — data value `.claude/ll-goals.md` in table row (not boilerplate); update path
- `skills/audit-docs/SKILL.md:26` — boilerplate Configuration section
- `skills/format-issue/SKILL.md:24` — boilerplate Configuration section
- `skills/issue-size-review/SKILL.md:307` — boilerplate Configuration section
- `skills/map-dependencies/SKILL.md:170` — boilerplate Configuration section
- `agents/consistency-checker.md:69` — table row: `| .claude/ll-config.json | config-schema.json | Values match schema types |`; update key path
- `.claude/commands/analyze_log.md:15` — boilerplate Configuration section (note: lives in `.claude/commands/`, not `commands/`)

#### Additional Commands — Not Previously Listed (found in 2nd pass)

- `commands/sync-issues.md:27` — runtime instruction text "add to `.claude/ll-config.json`" → `.ll/ll-config.json` (not boilerplate; user-facing instruction)
- `commands/help.md:118` — description text "(or .claude/ll-update-docs.watermark)" → `.ll/ll-update-docs.watermark` (accuracy update)
- `commands/help.md:226` — footer line "Configuration: .claude/ll-config.json" → `.ll/ll-config.json`
- `commands/help.md:279` — footer bullet "Plugin configuration: `.claude/ll-config.json`" → `.ll/ll-config.json`

#### Corrections to Previous Categorization

- `commands/normalize-issues.md` was listed as boilerplate-only in Step 5, but also has:
  - Line 345: runtime conditional "documents.enabled is not true in `.claude/ll-config.json`" (non-boilerplate, needs updating)
  - Line 390: table example row shows `.claude/ll-goals.md` as a data value (update for accuracy)

#### Exact Test Assertions (with Line Numbers)

- `scripts/tests/test_subprocess_utils.py:185-187` — `assert CONTINUATION_PROMPT_PATH == Path(".claude/ll-continue-prompt.md")`
- `scripts/tests/test_subprocess_utils.py:47` — fixture constructs `temp_repo / ".claude" / "ll-continue-prompt.md"` (must also update)
- `scripts/tests/test_hooks_integration.py:1035-1042` — `assert result.stdout.strip() == ".claude/ll-config.json"` (tests `ll_resolve_config()`)
- `scripts/tests/test_config.py:886-893` — `assert config.state_file == ".claude/ll-sync-state.json"` (string equality)
- `scripts/tests/test_merge_coordinator.py:493-534` — fixture constructs `claude_dir / "ll-context-state.json"` (no path string assertion; update fixture directory)

#### .gitignore Line-Level Changes

- Line 53: `.claude/ll.local.md` → `.ll/ll.local.md`
- Line 54: `.claude/loop-suggestions/` → `.ll/loop-suggestions/`
- Line 56: `.claude/ll-continue-prompt.md` → `.ll/ll-continue-prompt.md`
- Line 84: `.claude/ll-context-state.json` → `.ll/ll-context-state.json`
- Line 85: `.claude/ll-sync-state.json` → `.ll/ll-sync-state.json`

#### Dependent Files — Implementation Notes

- `scripts/little_loops/parallel/merge_coordinator.py:193` — uses `endswith("ll-context-state.json")` suffix match; **robust to directory change — does not need updating**
- `scripts/little_loops/cli/sync.py:120` — path appears in error message string only; update for accuracy but no functional impact
- `scripts/little_loops/issue_manager.py:201` — path appears in comment only; update for accuracy but no functional impact

## Implementation Steps

1. **Create `.ll/` directory convention** - add `mkdir -p .ll/` guard to `hooks/scripts/lib/common.sh` (line 184-191 `ll_resolve_config()`) and `skills/init/SKILL.md`; also add to `precompact-state.sh:33` which already runs `mkdir -p "$STATE_DIR"` (just change `STATE_DIR` to `.ll`)
2. **Update Python source** - change hardcoded paths in `subprocess_utils.py:32`, `config/core.py:74` (`CONFIG_DIR = ".claude"` → `".ll"`), `config/features.py:213,226`; update docstring in `config/__init__.py:4`
3. **Update loop YAML files** - change `'.claude/ll-config.json'` to `'.ll/ll-config.json'` in 7 YAML files: `fix-quality-and-tests.yaml:70`, `evaluation-quality.yaml:46`, `rl-coding-agent.yaml:53,61`, `dead-code-cleanup.yaml:67`, `harness-single-shot.yaml:60`, `harness-multi-item.yaml:88`, `context-health-monitor.yaml:22`
4. **Update hook scripts** - replace all `.claude/ll-*` and `.claude/.ll-lock` references in 4 hook scripts + `lib/common.sh` (see exact line references in Codebase Research Findings above)
5. **Update skills and commands** - find/replace `.claude/ll-` with `.ll/` across all skill/command docs (all commands update for accuracy; `handoff.md`, `resume.md`, `toggle-autoprompt.md`, `create-sprint.md`, `scan-product.md`, `align-issues.md`, `tradeoff-review-issues.md`, `manage-release.md`, `skills/create-loop/loop-types.md:607` are runtime reads that must update)
6. **Update `config-schema.json`** - change 3 defaults at lines 503, 582, 795
7. **Update `.gitignore`** - adjust 5 patterns at lines 53, 54, 56, 84, 85; keep `ll-config.json` tracked, ignore runtime state files
8. **Update permissions** - replace `Write(.claude/ll-continue-prompt.md)` with `Write(.ll/ll-continue-prompt.md)` in `skills/configure/areas.md:779,788,792` AND `.claude/settings.local.json:24` (note: `settings.json` does not exist; active file is `settings.local.json`)
9. **Update tests** - fix hardcoded path assertions at `test_subprocess_utils.py:47,185-187`, `test_hooks_integration.py:1035-1042`, `test_config.py:886-893`, `test_merge_coordinator.py` fixture directory
10. **Add migration note** - add upgrade note to CHANGELOG for existing users to move files

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
- `/ll:ready-issue` - 2026-03-31T16:20:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15b8c31c-0cd9-4489-9637-959697fdd1b4.jsonl`
- `/ll:refine-issue` - 2026-03-26T21:46:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:confidence-check` - 2026-03-26T23:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:refine-issue` - 2026-03-26T21:40:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:confidence-check` - 2026-03-26T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:refine-issue` - 2026-03-26T21:34:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:confidence-check` - 2026-03-26T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:refine-issue` - 2026-03-26T21:29:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:confidence-check` - 2026-03-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60805218-5038-4a93-a36c-b69a86db157c.jsonl`
- `/ll:refine-issue` - 2026-03-26T21:19:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a144f8f6-b87d-4e3d-84c3-177d86c2baca.jsonl`
- `/ll:format-issue` - 2026-03-26T21:14:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/184fd12a-1de3-4eba-9d21-0c994ea1a12d.jsonl`
- `/ll:capture-issue` - 2026-03-26T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09734997-4b5e-4d15-a3cc-89e8eb882723.jsonl`
