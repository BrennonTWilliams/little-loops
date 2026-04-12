---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 78
testable: false
---

# FEAT-1049: ll-create-extension Documentation Wiring

## Summary

Register the new `ll-create-extension` CLI in all documentation and manifest files: `commands/help.md`, `skills/init/SKILL.md` (two locations), and `skills/configure/areas.md`.

## Parent Issue

Decomposed from FEAT-1044: ll-create-extension CLI and Scaffolding Templates

## Motivation

This feature would:
- Complete the `ll-create-extension` CLI rollout by ensuring all documentation and manifest registration is consistent with the new tool
- Prevent user confusion when `/ll:help` output, `/ll:init` permissions, or `/ll:configure` areas don't reflect the newly available CLI
- Enable `/ll:init` to automatically authorize `ll-create-extension` in new projects without manual configuration

## Context

After the core CLI is implemented (FEAT-1048), several documentation and manifest files must be updated so that the new command appears in help output, is included in `init` permissions scaffolding, and is counted in the configure skill's enumeration.

## Current Behavior

- `commands/help.md` CLI TOOLS block does not list `ll-create-extension`
- `skills/init/SKILL.md` permissions block does not include `"Bash(ll-create-extension:*)"`
- `skills/configure/areas.md` count shows `13` ll- CLI tools; `ll-create-extension` is not enumerated

## Expected Behavior

- `commands/help.md` lists `ll-create-extension` in the CLI TOOLS block
- `/ll:init` writes `"Bash(ll-create-extension:*)"` into `.claude/settings.local.json`
- `skills/configure/areas.md` count shows `14` ll- CLI tools with `ll-create-extension` in the list

## Use Case

**Who**: Developer who has just implemented `ll-create-extension` (FEAT-1048) and wants to confirm the new CLI is properly surfaced to users

**Context**: After the core CLI is merged, a developer runs `/ll:help`, `/ll:init`, or `/ll:configure` expecting `ll-create-extension` to appear alongside the other `ll-*` tools

**Goal**: Have the new CLI registered in all authoritative locations without requiring users to discover it manually or configure permissions by hand

**Outcome**: `ll-create-extension` appears in help output, is included in init's permissions scaffolding, and is counted correctly in configure's CLI tool enumeration

## Proposed Solution

Apply four targeted edits to documentation and manifest files:

1. `commands/help.md:230` — add `ll-create-extension` bullet to CLI TOOLS block after `ll-gitignore`
2. `skills/init/SKILL.md:441` — add `"Bash(ll-create-extension:*)"` after `ll-gitignore` entry (before `Write(...)` at line 442)
3. `skills/init/SKILL.md:523` — add `ll-create-extension` bullet to "file exists" CLAUDE.md boilerplate
4. `skills/init/SKILL.md:547` — add `ll-create-extension` bullet to "create new" CLAUDE.md boilerplate
5. `skills/configure/areas.md:793` — increment count `13` → `14`; append `ll-create-extension` to enumerated list

## Integration Map

### Files to Modify

| File | Location | Change |
|------|----------|--------|
| `commands/help.md` | Line 230 (after `ll-gitignore`) | Add `ll-create-extension` CLI bullet |
| `skills/init/SKILL.md` | Line 442 (`ll-gitignore` entry) — insert after line 442, before `Write(...)` at line 443 | Add `"Bash(ll-create-extension:*)"` |
| `skills/init/SKILL.md` | Line 523 ("file exists" CLAUDE.md block) | Add `ll-create-extension` bullet |
| `skills/init/SKILL.md` | Line 547 ("create new" CLAUDE.md block) | Add `ll-create-extension` bullet |
| `skills/configure/areas.md` | Line 793 | Increment `13` → `14`; append `ll-create-extension` |

> **Note**: `.claude-plugin/plugin.json` has NO `permissions.allow` field. The wire-issue pass incorrectly identified this as a touchpoint. Plugin.json only contains `name`, `version`, `description`, `author`, `repository`, `license`, `homepage`, `keywords`, `commands`, `skills`, `agents`. The init skill writes permissions to `.claude/settings.local.json` at install time, sourced from its own SKILL.md permissions block (the canonical list).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — new test file needed; assert `ll-create-extension` appears in `commands/help.md`, `skills/init/SKILL.md` (≥3 occurrences: permissions + 2 boilerplate blocks), and `skills/configure/areas.md` (`"Authorize all 14"`). Follow the multi-file pattern in `scripts/tests/test_update_skill.py` using `PROJECT_ROOT / "path"` + `read_text()` + `assert X in content`.

### Key References

- `commands/help.md:216-230` — CLI TOOLS block lists all `ll-*` tools; `ll-gitignore` is last at line 230
- `skills/init/SKILL.md:429-443` — Bash permissions block written to `.claude/settings.local.json`; `ll-gitignore` at line 442, `Write(.ll/ll-continue-prompt.md)` at line 443; insert new entry between them
- `skills/init/SKILL.md:511-523` — "file exists" CLAUDE.md append boilerplate
- `skills/init/SKILL.md:535-547` — "create new" CLAUDE.md write boilerplate
- `skills/configure/areas.md:793` — "Authorize all N ll- CLI tools" description with enumerated list
- **NOT `.claude-plugin/plugin.json`** — plugin.json has no `permissions.allow` field; ignore the wire-issue reference to it

### Critical Notes

- None of these wiring changes are covered by FEAT-1045 (which handles a different scope)
- All edits are documentation-only; no runtime behavior changes
- Verify exact line numbers before editing (they may have shifted since refinement)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-11):_

**Verified line numbers (confirmed current — second pass 2026-04-11):**
- `commands/help.md:230` — `ll-gitignore` at line 230; CLI TOOLS block spans lines 216–230
- `skills/init/SKILL.md:442` — `ll-gitignore` permissions entry at line 442 (shifted +1 from prior refinement); `Write(.ll/ll-continue-prompt.md)` at line 443; block spans lines 429–443
- `skills/init/SKILL.md:523` — `ll-gitignore` in "file exists" boilerplate confirmed at line 523
- `skills/init/SKILL.md:547` — `ll-gitignore` in "create new" boilerplate confirmed at line 547
- `skills/configure/areas.md:793` — count shows `13`; confirmed

**plugin.json correction (from second refinement pass):**
- `.claude-plugin/plugin.json` does NOT have a `permissions.allow` field. The file only contains: `name`, `version`, `description`, `author`, `repository`, `license`, `homepage`, `keywords`, `commands`, `skills`, `agents`. The wire-issue pass erroneously added it to the Integration Map. The init SKILL.md permissions block (lines 429–443) is the authoritative canonical list written to `.claude/settings.local.json` at install time — no change needed to `plugin.json`.

**Exact current content of `skills/configure/areas.md:793`:**
```
description: "Authorize all 13 ll- CLI tools and handoff write: ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, ll-gitignore, Write(.ll/ll-continue-prompt.md)"
```
After change (increment count, insert before `Write(...)`):
```
description: "Authorize all 14 ll- CLI tools and handoff write: ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, ll-gitignore, ll-create-extension, Write(.ll/ll-continue-prompt.md)"
```

**Suggested description text for `ll-create-extension`:**
- In `commands/help.md` (fixed-width format): `ll-create-extension   Scaffold a new ll-* extension with templates and boilerplate`
- In `skills/init/SKILL.md` boilerplate bullets: `` - `ll-create-extension` - Scaffold a new ll-* extension with templates and boilerplate ``

**Additional files that also enumerate ll-* tools (not in current issue scope):**
- `.claude/CLAUDE.md:101-116` — "CLI Tools" section lists 13 tools; count will be stale after this issue lands
- `README.md:90` — says "13 CLI tools"; lines 256–453 document each tool; both count and listing will be stale
- `docs/reference/CLI.md` — full CLI reference documentation; will need a new `ll-create-extension` section

**Out-of-scope note:**
- `scripts/pyproject.toml:48-63` — `[project.scripts]` block needs `ll-create-extension = "little_loops.cli:main_create_extension"` but this belongs to FEAT-1048 (core CLI implementation), not this issue

## Implementation Steps

1. Read `commands/help.md` around line 230 to verify `ll-gitignore` position, then insert `ll-create-extension` bullet after it
2. Read `skills/init/SKILL.md` around line 442 to verify permissions block, then insert `"Bash(ll-create-extension:*)"` entry
3. Read `skills/init/SKILL.md` around lines 523 and 547 to verify both CLAUDE.md boilerplate blocks, then insert bullets in both
4. Read `skills/configure/areas.md` around line 793 to find the count and enumeration, then increment and append

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis:_

5. ~~Update `.claude-plugin/plugin.json`~~ — **SKIP**: `plugin.json` has no `permissions.allow` field; this was a false wiring touchpoint. The init skill's SKILL.md permissions block (Step 2 above) is the authoritative source.
6. Write `scripts/tests/test_create_extension_wiring.py` — new test file guarding all acceptance criteria; use the `PROJECT_ROOT / "path"` + `read_text()` + `assert X in content` pattern from `scripts/tests/test_update_skill.py`

## API/Interface

N/A - No public API changes. All edits are documentation and manifest wiring only.

## Acceptance Criteria

- [ ] `commands/help.md` CLI TOOLS block includes `ll-create-extension`
- [ ] `skills/init/SKILL.md` permissions block includes `"Bash(ll-create-extension:*)"`
- [ ] Both CLAUDE.md boilerplate blocks in `skills/init/SKILL.md` include `ll-create-extension`
- [ ] `skills/configure/areas.md` count shows `14` with `ll-create-extension` in the list
- [ ] `scripts/tests/test_create_extension_wiring.py` exists and passes

## Impact

- **Priority**: P4 - Follows core implementation; low risk
- **Effort**: Small - Four targeted text edits
- **Risk**: Very Low - Documentation only
- **Breaking Change**: No
- **Depends On**: FEAT-1048 (core CLI must be implemented first, but this issue can be refined/reviewed in parallel)

## Labels

`feat`, `extension-api`, `developer-experience`, `docs`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P4

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b31ab27-dd0b-4234-b84f-a3ce2c230248.jsonl`
- `/ll:refine-issue` - 2026-04-12T03:42:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1492d40c-e557-4d15-9905-5486157b0414.jsonl`
- `/ll:wire-issue` - 2026-04-12T03:26:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d67326fc-67ca-4141-a32a-78e3d068216f.jsonl`
- `/ll:refine-issue` - 2026-04-12T03:20:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/636ffdeb-1965-4412-b783-a2735eedd643.jsonl`
- `/ll:format-issue` - 2026-04-12T03:17:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/583c0fb7-c66b-4b73-ac75-21056880b737.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/641c5bf7-b7c1-42cd-b701-507df2a51df9.jsonl`
