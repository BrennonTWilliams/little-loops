---
id: BUG-2764
type: bug
priority: P4
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
---

# BUG-2764: configure skill's ll- CLI permission allowlist is stale (31 of 46 tools)

## Summary

`skills/configure/areas.md` offers a permission preset described as authorizing
"all 31 ll- CLI tools," but `scripts/pyproject.toml` now declares 46 console
entry points. Fifteen current tools are missing from the preset, so a user who
accepts it still gets permission prompts for them — and the "all" in the
description is wrong.

## Steps to Reproduce

1. `sed -n '/\[project.scripts\]/,/^\[/p' scripts/pyproject.toml | grep -c "="` → `46`
2. `sed -n '849p' skills/configure/areas.md | grep -oE 'll-[a-z-]+' | sort -u | wc -l` → `31`
3. Diff the two sets and observe 15 entry points absent from the preset.

## Current Behavior

The preset's description claims completeness ("all 31 ll- CLI tools") while
omitting:

`ll-adapt-agents-for-codex`, `ll-adapt-skills-for-codex`, `ll-artifact`,
`ll-code`, `ll-compact-session`, `ll-config`, `ll-generate-schemas`, `ll-init`,
`ll-migrate-labels`, `ll-queue`, `ll-verify-decisions`, `ll-verify-kinds`,
`ll-verify-package-data`, `ll-verify-skill-budget`, `ll-verify-triggers`,
plus the `mcp-call` entry point.

## Expected Behavior

The preset covers every current `[project.scripts]` entry point (or explicitly
scopes itself and drops the word "all"), and does not silently drift as tools
are added.

## Root Cause

- **File**: `skills/configure/areas.md`
- **Anchor**: the permissions preset at ~line 849
- **Cause**: The list is a hand-maintained literal with a hardcoded count in its
  own description. Nothing ties it to `scripts/pyproject.toml`, and no test
  compares the two, so every new entry point since it was written has drifted out.

## Motivation

The preset exists specifically to eliminate permission prompts during automation
runs. A preset that covers two-thirds of the tools delivers prompts anyway at
exactly the moments automation cannot answer them — and the "all" wording means
users won't think to check. This is also a representative instance of the
hand-maintained-inventory drift that FEAT-2763 aims to detect systematically.

## Proposed Solution

Regenerate the list from `scripts/pyproject.toml` and drop the hardcoded count
from the prose (say "all ll- CLI tools", not "all 31"), so the description
cannot go stale independently of the list.

Then prevent recurrence with a pytest gate that parses `[project.scripts]` and
asserts every entry point appears in the preset — cost-free, runs in the
existing `python -m pytest scripts/tests/` suite, and consistent with the
`ll-verify-*` family's convention. Decide during implementation whether
maintainer-only tools (`ll-generate-schemas`, `ll-adapt-*-for-codex`) and the
non-`ll-` `mcp-call` belong in a user-facing preset, and encode that decision as
an explicit exclusion list in the test rather than a silent omission.

## Integration Map

### Files to Modify
- `skills/configure/areas.md` — the preset list and its description

### Dependent Files (Callers/Importers)
- `skills/configure/SKILL.md` — surfaces the preset
- `.claude/settings.local.json` — where the preset is applied

### Similar Patterns
- `.claude/CLAUDE.md` § CLI Tools — another hand-maintained inventory of the same
  entry points; check it for the same drift
- `commands/help.md` — CLI listing

### Tests
- New gate in `scripts/tests/` comparing `[project.scripts]` to the preset

### Documentation
- `docs/reference/CLI.md` — verify it lists all 46 tools

### Configuration
- `scripts/pyproject.toml` — the source of truth to generate from

## Implementation Steps

1. Decide the inclusion policy for maintainer-only and non-`ll-` entry points.
2. Regenerate the preset from `[project.scripts]`; remove the hardcoded count.
3. Add the pytest gate with an explicit, commented exclusion list.
4. Sweep `.claude/CLAUDE.md` and `docs/reference/CLI.md` for the same drift.

## Impact

- **Priority**: P4 - Causes avoidable permission prompts, not incorrect behavior.
- **Effort**: Small - Regenerate a list plus a short test.
- **Risk**: Low - Broadening a permission preset the user opts into explicitly;
  the only real consideration is whether maintainer-only tools should be
  auto-authorized for all users.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Canonical CLI tools list (check for the same drift) |
| `docs/reference/CLI.md` | Per-tool CLI reference |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
