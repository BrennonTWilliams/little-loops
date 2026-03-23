---
id: BUG-863
priority: P2
status: open
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
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
- `skills/init/SKILL.md:469-475` — Step 10.5, point 3: the merge step reads `hooks/hooks.json` and writes entries to settings without substituting `${CLAUDE_PLUGIN_ROOT}`
- `skills/configure/areas.md:901-906` — Step 3 of `hooks install` sub-command has the identical missing resolution step (same bug, second entry point)

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

### Documentation
- `docs/claude-code/plugins-reference.md:358` — documents `${CLAUDE_PLUGIN_ROOT}` variable and expected behavior; no update required but implementer should verify the documented behavior matches the fix
- `docs/development/TROUBLESHOOTING.md` — references `settings.local.json` and variable path issues; may warrant a "Known Issue" note until fixed

### Configuration
- N/A

## Implementation Steps

1. Edit `skills/init/SKILL.md:469-475` — replace the 5-bullet merge block in Step 10.5 point 3 with the 6-bullet version that adds `${CLAUDE_PLUGIN_ROOT}` resolution (run `pwd`, replace in all command strings) before the merge
2. Edit `skills/configure/areas.md:901-906` — replace the 5-step merge block in `hooks install` Step 3 with the 6-step version applying the same resolution
3. Verify both: run `/ll:init --force` and `/ll:configure hooks install`, then inspect `.claude/settings.local.json` — all hook commands should contain absolute paths like `/Users/brennon/AIProjects/.../hooks/scripts/session-cleanup.sh`
4. Test the resolved path is correct: confirm a new Claude Code session runs Stop hook without error

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

## Status

**Open** | Created: 2026-03-23 | Priority: P2

---

## Session Log
- `/ll:refine-issue` - 2026-03-23T21:03:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9347f1dd-86de-45fe-80c1-0777f09e8214.jsonl`
- `/ll:confidence-check` - 2026-03-23T21:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/866bb962-c943-47d7-87e5-7be36e498342.jsonl`
- `/ll:refine-issue` - 2026-03-23T20:53:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35b87f24-5f70-4b60-a5a7-ff0addd4adc0.jsonl`
- `/ll:format-issue` - 2026-03-23T20:48:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6481bfd-325d-45f8-883c-848fa8beaa77.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/855beb9e-af12-4065-bc95-c436eff3069d.jsonl`
