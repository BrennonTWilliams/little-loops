---
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 68
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/settings.local.json:12-23` — project's own live `Bash(ll-*:*)` permissions block; currently 12 entries, `"Bash(ll-gitignore:*)"` is absent — patch directly or re-run `/ll:configure` after the skill edits land [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No existing tests cover `skills/configure/areas.md`, `skills/init/SKILL.md`, or `commands/help.md` — no tests will break and no new tests are required for correctness [Agent 3 finding]
- Optional: add content assertions to `scripts/tests/test_update_skill.py` following the `content = SKILL_FILE.read_text(); assert "ll-gitignore" in content` pattern to guard against future regressions [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current codebase:_

**`skills/configure/areas.md:793`** — confirmed absent, current line reads:
```
description: "Authorize all 12 ll- CLI tools and handoff write: ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, Write(.ll/ll-continue-prompt.md)"
```

**`skills/init/SKILL.md:441`** — `ll-check-links` is at line 441, `Write(.ll/ll-continue-prompt.md)` at line 442. New entry inserts between them.

**`commands/help.md:224`** — `ll-check-links` is at line 224, blank line at 225, `================...` at 226. New entry inserts at line 225.

**`ll-gitignore` description** — confirmed from `scripts/little_loops/cli/gitignore.py:27` argparse help text (word-for-word match to CLAUDE.md): `"Suggest and apply .gitignore patterns based on untracked files"`

**Console script** — registered in `pyproject.toml:61` as `ll-gitignore = "little_loops.cli:main_gitignore"`. Tool is fully implemented and installable.

## Implementation Steps

1. Edit `skills/configure/areas.md` line 793: change `12` → `13`, add `ll-gitignore` before the `Write(...)` entry in the description list.
2. Edit `skills/init/SKILL.md`: add `"Bash(ll-gitignore:*)",` after the `"Bash(ll-check-links:*)",` line (currently line 441).
3. Edit `commands/help.md`: add `ll-gitignore      Suggest and apply .gitignore patterns based on untracked files` after the `ll-check-links` line (currently line 224).
4. Verify: `grep -n "ll-gitignore" skills/configure/areas.md skills/init/SKILL.md commands/help.md` — should return 3 matches.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `.claude/settings.local.json` — add `"Bash(ll-gitignore:*)"` to the live permissions block at lines 12–23 to keep this project's own settings in sync with the updated template.

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

`completed`

## Resolution

Implemented 2026-04-10. Four targeted edits — no behavioral changes:

1. `skills/configure/areas.md:793` — count updated 12→13, `ll-gitignore` added to tool list
2. `skills/init/SKILL.md:442` — `"Bash(ll-gitignore:*)"` added to canonical permissions block
3. `commands/help.md:225` — `ll-gitignore` listed in CLI TOOLS section
4. `.claude/settings.local.json:24` — `"Bash(ll-gitignore:*)"` added to live permissions block

## Session Log
- `/ll:ready-issue` - 2026-04-11T03:58:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:58:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:58:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:58:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:57:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:ready-issue` - 2026-04-11T03:57:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a06a74f-24df-42e9-bd65-e3ce402c9e15.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/56b0e02d-f361-4e35-b50c-1f5dfb058991.jsonl`
- `/ll:wire-issue` - 2026-04-11T03:53:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e51bea29-2b9d-4728-8f88-7c6d58f54681.jsonl`
- `/ll:refine-issue` - 2026-04-11T03:48:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5662d17-af99-45da-a0a1-f0553c452c17.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eba12ede-7d68-4165-af6c-e13830e98af5.jsonl`
