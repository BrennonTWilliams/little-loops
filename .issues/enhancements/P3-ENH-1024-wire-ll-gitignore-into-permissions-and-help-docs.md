---
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# ENH-1024: Wire ll-gitignore into permissions and help docs

## Summary

`ll-gitignore` is a fully implemented CLI tool but is missing from 3 wiring locations: the `configure` skill's permission authorization description, the `init` skill's canonical `Bash(ll-*:*)` permissions block, and `help.md`'s CLI TOOLS section. Users who run `/ll:init` or `/ll:configure` to set up permissions will not get ll-gitignore pre-authorized, and `/ll:help` does not list it among the available CLI tools.

## Current Behavior

1. `skills/configure/areas.md` line 793: describes "Authorize all **12** ll- CLI tools" and lists 12 tools — `ll-gitignore` is absent.
2. `skills/init/SKILL.md` lines 430–441: the canonical JSON permissions block has 12 `Bash(ll-*:*)` entries — `"Bash(ll-gitignore:*)"` is absent.
3. `commands/help.md` CLI TOOLS section (lines 211–225): 12 CLI tools listed — `ll-gitignore` is absent.

## Expected Behavior

1. `configure/areas.md`: count updated to **13**, `ll-gitignore` added to the tool list in the description.
2. `init/SKILL.md`: `"Bash(ll-gitignore:*)"` appended to the canonical permissions block.
3. `help.md`: `ll-gitignore` listed in the CLI TOOLS section with its description.

## Motivation

`ll-gitignore` was added as FEAT-700 but wiring was incomplete. Without these changes, users who set up permissions via `/ll:init` or `/ll:configure` will hit permission prompts when Claude tries to run `ll-gitignore`, and `/ll:help` gives an incomplete picture of available tools.

## Proposed Solution

Three small, targeted edits — no behavioral changes, purely documentation and permission wiring:

1. **`skills/configure/areas.md` line 793** — update count and append tool name:
   ```
   "Authorize all 13 ll- CLI tools and handoff write: ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, ll-gitignore, Write(.ll/ll-continue-prompt.md)"
   ```

2. **`skills/init/SKILL.md` line 441** — add after `ll-check-links`:
   ```json
   "Bash(ll-gitignore:*)",
   ```

3. **`commands/help.md`** — add after `ll-check-links` (line 224):
   ```
   ll-gitignore      Suggest and apply .gitignore patterns based on untracked files
   ```

## Integration Map

- `skills/configure/areas.md:793` — permission list description (count + tool name)
- `skills/init/SKILL.md:441` — canonical Bash(ll-*:*) permissions block
- `commands/help.md:224` — CLI TOOLS section (insert after ll-check-links)

## Implementation Steps

1. Edit `skills/configure/areas.md` line 793: change `12` → `13`, add `ll-gitignore` before the `Write(...)` entry in the description list.
2. Edit `skills/init/SKILL.md`: add `"Bash(ll-gitignore:*)",` after the `"Bash(ll-check-links:*)",` line (currently line 441).
3. Edit `commands/help.md`: add `ll-gitignore      Suggest and apply .gitignore patterns based on untracked files` after the `ll-check-links` line (currently line 224).
4. Verify: `grep -n "ll-gitignore" skills/configure/areas.md skills/init/SKILL.md commands/help.md` — should return 3 matches.

## Impact

- **Scope**: 3 files, 1 line change each
- **Behavior change**: None — permissions and help text only
- **Risk**: Very low

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Lists ll-gitignore in CLI Tools section (source of truth for tool descriptions) |
| `CONTRIBUTING.md` | Documents ll-generate-schemas as required dev step; same pattern applies here |

## Labels

`wiring`, `permissions`, `help-docs`, `ll-gitignore`

---

## Status

`backlog`

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eba12ede-7d68-4165-af6c-e13830e98af5.jsonl`
