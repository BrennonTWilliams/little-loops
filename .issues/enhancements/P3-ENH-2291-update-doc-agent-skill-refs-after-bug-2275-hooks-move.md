---
id: ENH-2291
type: ENH
priority: P3
status: open
captured_at: '2026-06-25T14:15:33Z'
discovered_date: 2026-06-25
discovered_by: capture-issue
parent: EPIC-2279
relates_to:
- BUG-2275
testable: false
---

# ENH-2291: Update doc/agent/skill references after BUG-2275 hooks in-package move

## Summary

Mechanical follow-up to BUG-2275. After `optimize-prompt-hook.md` and
`hooks/adapters/codex/` (including shell scripts) move into the
`little_loops/` package tree, all documentation, agent definitions, and
skill files that hard-code old repo-root paths need to be updated to reflect
the new locations.

These are path-string replacements only — no logic changes. Split from
BUG-2275 to keep that PR focused on the Python resolver fixes and `.sh` move.

## Motivation

If not updated, the docs will point to paths that no longer exist at repo
root, the `consistency-checker` agent will audit the wrong location, and the
`audit-claude-config` skill will silently miss `optimize-prompt-hook.md` in
its wave1-prompts glob. The changes are mechanical but high in count (15+
sites), which is why they're tracked separately.

## Current Behavior

Path references in 15+ files still point to the old pre-BUG-2275 locations:
- `hooks/prompts/optimize-prompt-hook.md` (moved in-package by FEAT-2274)
- `hooks/adapters/codex/` shell scripts (to be moved in-package by BUG-2275)

## Expected Behavior

All references updated to the new in-package paths
(`scripts/little_loops/hooks/prompts/` and
`scripts/little_loops/hooks/adapters/codex/`), and a final verification grep
passes with zero matches.

## Integration Map

### Files to Modify

**Documentation** (8 files):
- `docs/ARCHITECTURE.md` — directory tree lines 85, 102, 1186: update
  `hooks/prompts/optimize-prompt-hook.md` and `hooks/adapters/codex/` entries
- `docs/development/TROUBLESHOOTING.md` — lines 853-854 (`chmod` examples),
  line 1021 (`ls -la hooks/prompts/optimize-prompt-hook.md`)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — line 152: `hooks/prompts/optimize-prompt-hook.md`
- `docs/codex/getting-started.md` — rendered `bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/session-start.sh`
- `docs/codex/usage.md` — example `hooks.json` fragment with `hooks/adapters/codex/pre-tool-use.sh`
- `docs/codex/README.md` — line 24: states adapter is at `hooks/adapters/codex/`
- `docs/claude-code/write-a-hook.md` — lines 190, 324-325: references to `hooks/adapters/codex/{session-start,pre-compact}.sh` and `hooks/adapters/codex/README.md`
- `hooks/adapters/codex/README.md` — lines 19, 113, 204: `{{LL_PLUGIN_ROOT}}` substitution description, manual opt-in snippet, smoke test path (note: this is `hooks/adapters/codex/README.md`, distinct from `docs/codex/README.md`)

**Agent/skill files** (4 files):
- `agents/consistency-checker.md` — line 169: "Hooks → Prompts" table has hardcoded `hooks/prompts/optimize-prompt-hook.md`
- `.codex/agents/consistency-checker.toml` — line 143: mirrors the same table
- `skills/audit-claude-config/SKILL.md` — line 44: references `hooks/prompts/*.md` and `hooks/adapters/` as canonical audit-scope paths
- `skills/configure/areas.md` — line 890: references `hooks/adapters/codex/` as Codex adapter location

**Skill audit scope** (1 file — functional, not just cosmetic):
- `skills/audit-claude-config/wave1-prompts.md` — line 111: audit-scope glob
  `hooks/prompts/*.md` silently stops matching `optimize-prompt-hook.md` once
  it moves in-package; update glob to also check `scripts/little_loops/hooks/prompts/`
  (or replace with the in-package path only)

### Dependent Files (Callers/Importers)

- N/A — path strings in docs/config only; no Python imports or callers affected

### Similar Patterns

- N/A — no code pattern changes; pure string replacements

### Tests

- N/A — docs/config changes only; no test files require updates

### Configuration

- N/A

## Implementation Steps

1. Implement BUG-2275 first — this issue depends on BUG-2275 landing so the
   new in-package paths are confirmed.
2. Update the 8 documentation files listed above (path string replacements).
3. Update the 4 agent/skill definition files.
4. Update `skills/audit-claude-config/wave1-prompts.md` line 111 glob.
5. Run the verification grep — must exit with zero matches:
   ```bash
   grep -rn "hooks/prompts/optimize-prompt-hook\|hooks/adapters/codex" \
     docs/ agents/ skills/ hooks/adapters/codex/README.md
   ```
6. Commit as a single docs/config-only commit.

## Scope Boundaries

- Path string replacements only — no changes to hook invocation logic, shell script behavior, or Python resolver code (those are BUG-2275 scope)
- No new documentation sections or content rewrites; only path strings are updated
- Does not include structural reorganization of docs or skill files

## Impact

- **Priority**: P3 — Mechanical follow-up to BUG-2275; improves doc accuracy but has no functional impact until BUG-2275 lands
- **Effort**: Small — Pure path string replacements across 13 files; no logic changes
- **Risk**: Low — Docs and config files only; no production code or test changes
- **Breaking Change**: No

## Labels

`documentation`, `maintenance`, `captured`

## Status

**Open** | Created: 2026-06-25 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-25T14:21:47 - `9c3a5bf0-be76-4e09-80f3-6eeb965681b5.jsonl`
- `/ll:capture-issue` - 2026-06-25T14:15:33Z - `2d7d1ea6-286a-44ba-ac2e-8609d33e0c76.jsonl`
