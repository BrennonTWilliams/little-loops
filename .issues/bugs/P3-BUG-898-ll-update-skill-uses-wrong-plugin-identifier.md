---
id: BUG-898
type: BUG
priority: P3
status: open
discovered_date: 2026-03-30
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-898: ll:update skill uses wrong plugin identifier

## Summary

The `ll:update` skill runs `claude plugin update ll` which fails with "Plugin 'll' not found" because the plugin is registered as `ll@little-loops`. The fallback error message already suggests the correct identifier, but the primary command path uses the wrong one.

## Current Behavior

Running `/ll:update` executes `claude plugin update ll`, which fails because no plugin with the bare name `ll` exists. The user sees a "Plugin 'll' not found" error and must manually run the correct command.

## Expected Behavior

The skill should run `claude plugin update ll@little-loops` — the fully qualified identifier matching how the plugin is registered.

## Steps to Reproduce

1. Install the little-loops plugin via `claude plugin install ll@little-loops`
2. Run `/ll:update`
3. Observe: the skill attempts `claude plugin update ll` and fails with "Plugin 'll' not found"

## Root Cause

- **File**: `skills/update/SKILL.md`
- **Anchor**: In the plugin update command references (lines 34, 151, 156)
- **Cause**: The skill was authored with the short name `ll` instead of the fully qualified `ll@little-loops` identifier. The fallback/error hint at line 161 already uses the correct name, but the primary execution paths do not.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The fully-qualified identifier `ll@little-loops` is composed from `plugin.json` `"name": "ll"` + `marketplace.json` `"name": "little-loops"`
- No centralized constant exists for the composed identifier — every occurrence is a hardcoded literal
- Line 161 (`skills/update/SKILL.md`) already uses the correct `ll@little-loops` in the failure fallback message, confirming the correct format

## Error Messages

```
Plugin 'll' not found
```

## Motivation

Users hitting this bug must manually copy-paste the correct command from the fallback message, defeating the purpose of the `/ll:update` convenience skill.

## Proposed Solution

Replace `claude plugin update ll` with `claude plugin update ll@little-loops` in 3 locations within `skills/update/SKILL.md`:

1. **Flag description** (line 34): Update the inline command reference
2. **Dry-run message** (line 151): Update `[DRY-RUN] Would run:` text
3. **Actual command** (line 156): Update `Run:` command

Also update:
- `scripts/tests/test_update_skill.py` (lines 81-85): Update assertion and docstring to expect `"claude plugin update ll@little-loops"`
- `docs/reference/COMMANDS.md` (line 56): Update `--plugin` flag description from `claude plugin update ll` to `claude plugin update ll@little-loops`

## Integration Map

### Files to Modify
- `skills/update/SKILL.md:34,151,156` — 3 string replacements (`claude plugin update ll` → `claude plugin update ll@little-loops`)
- `scripts/tests/test_update_skill.py:81-85` — update assertion substring and docstring
- `docs/reference/COMMANDS.md:56` — update `--plugin` flag description

### Dependent Files (Callers/Importers)
- N/A — skill is invoked by user via `/ll:update`, no code callers

### Similar Patterns
- `skills/update/SKILL.md:161` — failure fallback already uses correct `ll@little-loops` identifier
- `README.md:33,43` — installation instructions use `/plugin install ll@little-loops`
- `docs/guides/GETTING_STARTED.md:26,33` — install steps use `ll@little-loops`

### Tests
- `scripts/tests/test_update_skill.py:80-86` — `test_skill_references_claude_plugin_update()` asserts `"claude plugin update ll"` substring; note that `"claude plugin update ll@little-loops"` contains this substring, so the test would pass either way — but the docstring (line 81) and assertion message (line 85) should be updated for accuracy

### Documentation
- `docs/reference/COMMANDS.md:56` — `--plugin` flag description also uses bare `ll` identifier

### Configuration
- `.claude-plugin/plugin.json:2` — defines plugin name `"ll"`
- `.claude-plugin/marketplace.json:2` — defines marketplace name `"little-loops"` (together form `ll@little-loops`)

## Implementation Steps

1. Update 3 occurrences of `claude plugin update ll` → `claude plugin update ll@little-loops` in `skills/update/SKILL.md` (lines 34, 151, 156)
2. Update `docs/reference/COMMANDS.md:56` — change `claude plugin update ll` → `claude plugin update ll@little-loops` in `--plugin` flag description
3. Update `scripts/tests/test_update_skill.py:81-85` — update docstring and assertion to reference `ll@little-loops`
4. Run `python -m pytest scripts/tests/test_update_skill.py -v` to verify

## Impact

- **Priority**: P3 - Skill is broken but has a manual workaround via the fallback message
- **Effort**: Small - 5 string replacements across 3 files
- **Risk**: Low - Straightforward text substitution, no logic changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [CLAUDE.md](.claude/CLAUDE.md) | Lists `update` skill and plugin configuration |

## Labels

`bug`, `skills`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-03-31T04:03:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eadfffc5-73ef-4cac-96b3-ff9bc033307c.jsonl`
- `/ll:format-issue` - 2026-03-31T03:59:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eadfffc5-73ef-4cac-96b3-ff9bc033307c.jsonl`
- `/ll:capture-issue` - 2026-03-30T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00032768-5efc-466a-aad1-02f0fb698fb3.jsonl`
- `/ll:confidence-check` - 2026-03-30T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eadfffc5-73ef-4cac-96b3-ff9bc033307c.jsonl`

---

## Status

**Open** | Created: 2026-03-30 | Priority: P3
