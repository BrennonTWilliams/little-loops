---
id: BUG-863
priority: P2
status: open
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 79
---

# BUG-863: `${CLAUDE_PLUGIN_ROOT}` Not Resolved in Hooks Installed to Settings Files

## Summary

When `/ll:init` installs hooks via the "Via CLAUDE.md" path, it copies hook entries from `hooks/hooks.json` verbatim into the project's `settings.local.json`. Those entries reference `${CLAUDE_PLUGIN_ROOT}` in their command paths. However, `${CLAUDE_PLUGIN_ROOT}` is only set by Claude Code when hooks are loaded from a registered plugin's own `hooks.json`. When hooks live in a project's `settings.local.json`, Claude Code treats them as project-level hooks with no plugin context — the variable expands to an empty string, yielding a root-relative path that does not exist.

**Confirmed error**: `Stop hook error: Failed with non-blocking status code: bash: /hooks/scripts/session-cleanup.sh: No such file or directory`

## Current Behavior

1. User runs `/ll:init` and selects "Via CLAUDE.md (install hooks)"
2. The init skill copies hook entries from `hooks/hooks.json` into `.claude/settings.local.json` verbatim
3. Hook commands retain `${CLAUDE_PLUGIN_ROOT}` references, e.g.:
   ```json
   "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-cleanup.sh"
   ```
4. When Claude Code executes the hook, `${CLAUDE_PLUGIN_ROOT}` is unset (no plugin context), expanding to empty string
5. The command becomes `bash /hooks/scripts/session-cleanup.sh` — a root-relative path that doesn't exist
6. Hook fails with a non-blocking error

## Expected Behavior

Hook commands written to `settings.local.json` should use absolute paths. The init skill should resolve `${CLAUDE_PLUGIN_ROOT}` to the actual plugin root directory (the `pwd` at init time) before writing hooks to the settings file.

**Expected result** in `settings.local.json`:
```json
"command": "bash /Users/brennon/AIProjects/lmc-voice/hooks/scripts/session-cleanup.sh"
```

## Motivation

Every user who selects the "Via CLAUDE.md" installation path during `/ll:init` ends up with broken hooks. This silently degrades all hook-based automation (session cleanup, context monitoring, etc.) without obvious indication to the user.

## Steps to Reproduce

1. Run `/ll:init --force` in a project that has `hooks/hooks.json`
2. Select "Via CLAUDE.md (install hooks)" when prompted
3. Open `.claude/settings.local.json` — hook commands contain `${CLAUDE_PLUGIN_ROOT}` literally
4. Start a new Claude Code session — Stop hook fails with path error

## Root Cause

- **Primary file**: `skills/init/SKILL.md:469-475` — Step 10.5, point 3
- **Secondary file**: `skills/configure/areas.md:901-906` — `hooks install` Step 3
- **Cause**: Both merge steps read `hooks/hooks.json` and write entries verbatim to settings files without substituting `${CLAUDE_PLUGIN_ROOT}`. The variable is only valid in plugin-owned `hooks.json` files; project-level settings hooks have no plugin context, so the variable expands to empty string at execution time.

## Proposed Solution

Apply the same resolution step to **both** affected files, inserting it between reading `hooks/hooks.json` and writing to the settings file.

**`skills/init/SKILL.md:469-475`** — replace Step 10.5, point 3:

```
3. Perform merge into the chosen target file:
   - Read target file, or start with `{}` if absent
   - Read `hooks/hooks.json` — use only the `hooks` key (ignore `description` field)
   - Resolve ${CLAUDE_PLUGIN_ROOT} in hook commands:
     - Run `bash -c 'pwd'` to get the absolute plugin root path
     - Replace every occurrence of `${CLAUDE_PLUGIN_ROOT}` in all hook command strings with this absolute path
   - Merge the `hooks` key additively: for each event in plugin hooks, append its hook groups to
     the existing list for that event (do not remove or overwrite existing non-ll entries)
   - Create `.claude/` directory first if needed
   - Write result back with 2-space indent, preserving all top-level keys
   - Set `HOOKS_INSTALLED=true` and record the target filename
```

**`skills/configure/areas.md:901-906`** — replace Step 3 of `hooks install`:

```
**Step 3 — Perform merge into chosen target file**:
1. Read target file, or start with `{}` if absent
2. Read `hooks/hooks.json` — use the `hooks` key (the top-level object, not the `description` field)
3. Resolve ${CLAUDE_PLUGIN_ROOT} in hook commands:
   - Run `bash -c 'pwd'` to get the absolute plugin root path
   - Replace every occurrence of `${CLAUDE_PLUGIN_ROOT}` in all hook command strings with this absolute path
4. Merge the `hooks` key additively: for each event in the plugin hooks, append its hook groups to the existing list for that event (do not overwrite or remove existing non-ll entries)
5. Create `.claude/` directory first if needed
6. Write result back with 2-space indent, preserving all top-level keys
```

## Integration Map

### Files to Modify
- `skills/init/SKILL.md:451-480` — Entire Step 10.5 "Install Hooks" block: replace with a no-op informational note (hooks are automatic via plugin). The `pwd`-substitution fix occupies line 468 in the current state.
- `skills/configure/areas.md:877-941` — Entire `hooks install` sub-command section: replace Step 3 (lines 915-924, `pwd`-based substitution) with a note that hooks are automatic. The dry-run preview section (lines 881-894) also references `${CLAUDE_PLUGIN_ROOT}` commands and must change. The interactive menu `hooks` options block (lines 943-955) includes an "install" option that should be removed or redirected.

_Line numbers verified against current file state by `/ll:refine-issue` — 2026-04-12._

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — source of 7 hook definitions using `${CLAUDE_PLUGIN_ROOT}` at lines: 10 (SessionStart), 22 (UserPromptSubmit), 35 (PreToolUse), 48 (PostToolUse/*), 59 (PostToolUse/Bash), 71 (Stop), 84 (PreCompact)

### Similar Patterns
- `skills/manage-issue/SKILL.md:292` — uses `$(pwd)` for absolute path derivation: `$(pwd)/.claude/ll-continue-prompt.md`; same pattern applies here
- `skills/configure/areas.md:833` — the `hooks show` command already describes "expanding `${CLAUDE_PLUGIN_ROOT}`" for display validation; the install path needs the same expansion when writing
- `hooks/scripts/user-prompt-check.sh:81` — existing defensive fallback: `${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}` (shows the runtime fallback pattern, but not applicable to write-time resolution)
- `hooks/scripts/lib/common.sh:122-129` — `safe_substitute()` bash function using `${template//$placeholder/$value}` for all-occurrences replacement; not used by init/configure (prose instructions, not bash), but confirms the replacement approach

### Tests
- No automated tests for init skill or hook installation; manual verification required
- Manual verification: run `/ll:init --force`, select "Via CLAUDE.md", inspect `.claude/settings.local.json` for absolute paths

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — new test class needed; assert old `pwd`-substitution prose absent from `skills/init/SKILL.md` and new no-op note present; assert old `hooks install` Step 3 prose absent from `skills/configure/areas.md` and new no-op note present; assert `install` option absent from interactive menu in `areas.md`. Follow `TestConfigureSkillDevInstallFix` pattern in `scripts/tests/test_update_skill.py:194-211` [Agent 3 finding]

### Documentation
- `docs/claude-code/plugins-reference.md:358` — documents `${CLAUDE_PLUGIN_ROOT}` variable and expected behavior; no update required but implementer should verify the documented behavior matches the fix
- `docs/development/TROUBLESHOOTING.md` — references `settings.local.json` and variable path issues; may warrant a "Known Issue" note until fixed

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:48` — says "installs/shows/validates ll- lifecycle hooks in Claude Code settings files"; `hooks install` is being removed, so change to "shows/validates" [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Edit `skills/init/SKILL.md:469-475` — replace the 5-bullet merge block in Step 10.5 point 3 with the 6-bullet version that adds `${CLAUDE_PLUGIN_ROOT}` resolution (run `pwd`, replace in all command strings) before the merge
2. Edit `skills/configure/areas.md:901-906` — replace the 5-step merge block in `hooks install` Step 3 with the 6-step version applying the same resolution
3. Verify both: run `/ll:init --force` and `/ll:configure hooks install`, then inspect `.claude/settings.local.json` — all hook commands should contain absolute paths like `/Users/brennon/AIProjects/.../hooks/scripts/session-cleanup.sh`
4. Test the resolved path is correct: confirm a new Claude Code session runs Stop hook without error

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/COMMANDS.md:48` — change "installs/shows/validates" → "shows/validates" to reflect that `hooks install` is no longer a valid sub-command
6. Write regression tests in `scripts/tests/test_create_extension_wiring.py` — new class asserting old `pwd`-substitution prose absent from `skills/init/SKILL.md`, new no-op note present, old `hooks install` Step 3 absent from `skills/configure/areas.md`, and `install` option absent from interactive menu

## Impact

- **Priority**: P2 — Every "Via CLAUDE.md" init produces broken hooks; silent failure
- **Effort**: Small — Single text substitution step added to skill instructions
- **Risk**: Low — Only affects how hooks are written; no runtime behavior change beyond correct paths
- **Breaking Change**: No

## Related Key Documentation

- `docs/claude-code/plugins-reference.md:358` — authoritative definition of `${CLAUDE_PLUGIN_ROOT}`: "Contains the absolute path to your plugin directory. Use this in hooks, MCP servers, and scripts to ensure correct paths regardless of installation location." Also line 634 documents the failure mode: "MCP server fails | Missing `${CLAUDE_PLUGIN_ROOT}` | Use variable for all plugin paths"

### Implementation Note: Paths with Spaces

_Added by `/ll:refine-issue` — based on codebase analysis:_

The proposed solution resolves `${CLAUDE_PLUGIN_ROOT}` with `pwd`. If the resolved path contains spaces (e.g. `/Users/brennon/My Projects/little-loops`), the simple string substitution will produce an unquoted path in the command string:

```json
"command": "bash /Users/brennon/My Projects/little-loops/hooks/scripts/session-cleanup.sh"
```

This will fail at execution. The fix should wrap the resolved path in quotes when substituting, or verify this is not a concern in practice for the target user base. The current test case in the issue (`/Users/brennon/AIProjects/lmc-voice/...`) has no spaces, so this edge case won't surface in basic testing.

## Labels

`bug`, `hooks`, `init`, `captured`

## Resolution

**Fixed** in `skills/init/SKILL.md:469-479` and `skills/configure/areas.md:901-910`.

Added a `${CLAUDE_PLUGIN_ROOT}` resolution step in both merge blocks. Before writing hooks to the settings file, the skill now runs `bash -c 'pwd'` to obtain the absolute plugin root and replaces every occurrence of `${CLAUDE_PLUGIN_ROOT}` in all hook command strings with that value. Paths containing spaces are wrapped in single quotes.

## Status

**Completed** | Created: 2026-03-23 | Resolved: 2026-03-23 | Priority: P2

---

## Session Log
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70494509-dcbf-4a7d-9c33-38b2acf1602c.jsonl`
- `/ll:wire-issue` - 2026-04-12T21:41:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe704b8-ebc5-45d8-8fb7-81c53b3abe43.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:30:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34932e3c-e378-4fd7-9886-68460b918395.jsonl`
- `hook:posttooluse-git-mv` - 2026-04-12T21:19:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4eedc92-7d36-48db-b6c4-024d421aeb96.jsonl`
- `/ll:ready-issue` - 2026-03-23T21:06:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/175d1c25-3bc3-4807-a0b7-0511897a7a1a.jsonl`
- `/ll:refine-issue` - 2026-03-23T21:03:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9347f1dd-86de-45fe-80c1-0777f09e8214.jsonl`
- `/ll:confidence-check` - 2026-03-23T21:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/866bb962-c943-47d7-87e5-7be36e498342.jsonl`
- `/ll:refine-issue` - 2026-03-23T20:53:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35b87f24-5f70-4b60-a5a7-ff0addd4adc0.jsonl`
- `/ll:format-issue` - 2026-03-23T20:48:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6481bfd-325d-45f8-883c-848fa8beaa77.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/855beb9e-af12-4065-bc95-c436eff3069d.jsonl`
- `/ll:manage-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Reopened

- **Date**: 2026-04-12
- **By**: capture-issue
- **Reason**: Original fix (pwd substitution) was incorrect and unreliable; issue recurred in external projects

### New Findings

The previous resolution added a `${CLAUDE_PLUGIN_ROOT}` → `pwd` substitution step to `skills/init/SKILL.md` and `skills/configure/areas.md`. This approach has two compounding failures:

1. **`pwd` is the wrong path**: In an external project (e.g. `loop-viz`), `pwd` is the project directory — not the plugin cache at `~/.claude/plugins/cache/little-loops/ll/<version>/`. Substituting `pwd` writes a broken absolute path.
2. **Prose substitution is unreliable**: The LLM executing the skill skips the substitution step and writes `${CLAUDE_PLUGIN_ROOT}` literally (confirmed: `loop-viz` had the literal string in its `settings.local.json`).

**Root cause reframe**: The hooks installation step itself is unnecessary. When `ll@little-loops` is globally enabled in `~/.claude/settings.json`, the plugin's own `hooks/hooks.json` already fires all hooks with correct `${CLAUDE_PLUGIN_ROOT}` resolution. Writing hooks to `settings.local.json` is redundant AND broken.

**Real fix** (from plan `cryptic-yawning-otter.md`):
1. `skills/init/SKILL.md` — Replace Step 10.5 with a no-op informational note: hooks are automatic via the plugin, no `settings.local.json` entry needed.
2. `skills/configure/areas.md` — Replace the `hooks install` Step 3 merge block with a note that hooks are automatic; direct user to `/ll:configure hooks show` to verify.
3. Update this issue: `status: open` → `status: completed` with the correct resolution note after implementing.

- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff137a9f-150a-48ed-bb35-e478eb4b4fb4.jsonl`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-12):_

#### Current File State

Both files have the old (wrong) `pwd`-substitution fix applied; neither has the real fix yet.

**`skills/init/SKILL.md:451-480`** — The merge block at lines 465-471 contains the shorter-form `pwd` substitution at line 468:
```
- Resolve `${CLAUDE_PLUGIN_ROOT}` by substituting the absolute path of the current working directory (wrap in single quotes if path contains spaces)
```
The full Step 10.5 block (lines 451-480) is what needs to be replaced.

**`skills/configure/areas.md:877-941`** — The full-form 6-step `pwd` substitution occupies lines 915-924. The scope of the fix is broader than Step 3 alone:
- Lines 877-941: Entire `hooks install` sub-command — replace with no-op note
- Lines 881-894: Dry-run preview section also lists `${CLAUDE_PLUGIN_ROOT}` commands — remove or redirect
- Lines 943-955: Interactive `hooks` menu includes "install" option — remove or redirect to `show`

**`skills/init/interactive.md`** — Has a separate interactive init flow that also references hooks installation. Verify this file does not have its own hooks-copy step that would need the same treatment.

#### Stale Plan Reference

The Reopened section references `thoughts/plans/cryptic-yawning-otter.md` as the source of the "Real fix." That file does not exist in the repository. The only file in `thoughts/plans/` is `2026-01-09-analyze-log-command-design.md`. Implementation should proceed based on the description in the Reopened section above, not a plan file.

#### Concrete Replacement Prose

**For `skills/init/SKILL.md:451-480`** — replace the entire Step 10.5 block with:

```markdown
### 10.5. Hooks Note

ll plugin hooks fire automatically when `ll@little-loops` is globally enabled in `~/.claude/settings.json`. The plugin's own `hooks/hooks.json` handles all hook events with correct `${CLAUDE_PLUGIN_ROOT}` resolution — no manual installation into project settings files is needed or correct.

To verify hooks are active after init: `/ll:configure hooks show`

**Always proceed to Step 11.**
```

**For `skills/configure/areas.md:877-941`** — replace the entire `hooks install` sub-command section with:

```markdown
### Sub-command: install

> **Note**: Manual hook installation is not needed. When `ll@little-loops` is globally enabled as a Claude Code plugin, all hooks in `hooks/hooks.json` fire automatically with correct `${CLAUDE_PLUGIN_ROOT}` resolution. Writing hooks to project settings files produces broken paths because `${CLAUDE_PLUGIN_ROOT}` is only set when hooks load from a registered plugin's own `hooks.json`.
>
> To verify hooks are active: `/ll:configure hooks show`
```

**For `skills/configure/areas.md:943-955`** — update the interactive `hooks` menu to remove the "install" option (or replace its description with the above note).

#### Related Completed Issue

`P4-BUG-864-init-asks-about-hook-loading-method-for-plugin-users.md` — companion issue from the same period; may have relevant context about how init handles the plugin-already-loaded case.
