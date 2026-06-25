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
- `agents/consistency-checker.md` — **two locations** require updating:
  - line 68: Cross-Reference Matrix row `| hooks/hooks.json | hooks/prompts/*.md | ...` — the glob needs to reflect the new in-package location
  - line 169: "Hooks → Prompts" output example table has hardcoded `hooks/prompts/optimize-prompt-hook.md` resolved-path column
- `.codex/agents/consistency-checker.toml` — mirrors both locations above (lines ~42 and ~143); update in lock-step or re-run `ll-adapt-agents-for-codex` after fixing the `.md`
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

_Wiring pass added by `/ll:wire-issue`:_
- No existing tests break from ENH-2291 changes (doc/config path strings only). `testable: false` remains correct.
- `scripts/tests/test_wiring_skills_and_commands.py` — has a `DOC_STRINGS_ABSENT` list with `test_string_absent_from_doc` parametrized test; after wave-1 implementation, add absence assertions to prevent regression:
  ```python
  ("agents/consistency-checker.md", "hooks/prompts/optimize-prompt-hook.md", "ENH-2291"),
  (".codex/agents/consistency-checker.toml", "hooks/prompts/optimize-prompt-hook.md", "ENH-2291"),
  ```
  These are optional post-implementation guards; without them the acceptance-criterion grep (step 18) is the only regression check.
- `scripts/tests/test_init_tui.py:631–645` — xfail markers (BUG-2275 scope, not ENH-2291); remove after BUG-2275 lands and `install_codex_adapter()` path is fixed

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**BUG-2275 partial landing status**: As of this writing, `hooks.json` has already moved to `scripts/little_loops/hooks/adapters/codex/hooks.json`. The four bash shim scripts (`session-start.sh`, `pre-compact.sh`, `prompt-submit.sh`, `post-tool-use.sh`) still live at `hooks/adapters/codex/*.sh` — BUG-2275's shell-script portion is pending. References to `hooks.json` at the old path are stale now; references to `.sh` files become stale only after BUG-2275 fully lands.

**Files already updated (remove from scope)**:
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:152` — already shows `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md`; no action needed
- `docs/development/TROUBLESHOOTING.md:1021` — already shows `ls -la scripts/little_loops/hooks/prompts/optimize-prompt-hook.md`; no action needed

**Correction — `docs/ARCHITECTURE.md` line 1186**: The issue notes this line as having `hooks/prompts/optimize-prompt-hook.md`. It actually references `continuation-prompt-template.md` (which legitimately stays at `hooks/prompts/`). Only lines 85 and 99–104 of ARCHITECTURE.md are stale.

**Additional files not in original Integration Map** (confirmed stale by research):
- `docs/development/TESTING.md:903` — `hooks/adapters/codex/<event>.sh` call reference; needs updating after BUG-2275 `.sh` move
- `docs/reference/HOST_COMPATIBILITY.md:260` — link `hooks/adapters/codex/` for Codex entry; needs updating after BUG-2275
- `docs/reference/API.md:6800` — `hooks/adapters/codex/session-start.sh` and `pre-compact.sh` reference; needs updating after BUG-2275
- `docs/development/TROUBLESHOOTING.md:1122` — `hooks/adapters/codex/pre-compact.sh` in pre_compact handler description; needs updating after BUG-2275

**hooks/adapters/codex/README.md line 19**: References `./hooks.json` (relative link) — stale NOW because `hooks.json` already moved in-package. This can be updated immediately, independent of BUG-2275.

**Total scope correction**: 13 files in original scope → 4 already updated or not stale, 1 correction (line 1186), 4 additional files = net **13 files** with changes, but the wave-1 (optimize-prompt-hook.md only, doable now) vs. wave-2 (codex .sh move, after BUG-2275) split is important for sequencing.

## Implementation Steps

### Wave 1 — Doable now (optimize-prompt-hook.md move already landed via FEAT-2274)

1. Update `docs/ARCHITECTURE.md` line 85 directory tree entry: `hooks/prompts/optimize-prompt-hook.md` → `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` (lines 99–104 for codex adapter tree are wave-2)
2. Update `agents/consistency-checker.md` — two locations:
   - line 68 Cross-Reference Matrix row: `hooks/prompts/*.md` → `scripts/little_loops/hooks/prompts/*.md` (or extend to list both `hooks/prompts/` for continuation template AND `scripts/little_loops/hooks/prompts/` for optimize-prompt-hook)
   - line 169 Hooks → Prompts example table resolved-path: `hooks/prompts/optimize-prompt-hook.md` → `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md`
3. Update `.codex/agents/consistency-checker.toml` — same two locations (lines ~42 and ~143); update in lock-step with step 2
4. Update `skills/audit-claude-config/wave1-prompts.md` line 111 glob: extend or replace `hooks/prompts/*.md` to also cover `scripts/little_loops/hooks/prompts/` (only `continuation-prompt-template.md` remains at `hooks/prompts/`)
5. Update `skills/audit-claude-config/SKILL.md` line 44: adjust the `hooks/prompts/*.md` reference to reflect split between `hooks/prompts/` (continuation template only) and `scripts/little_loops/hooks/prompts/` (optimize-prompt-hook.md)
6. Update `hooks/adapters/codex/README.md` line 19: fix relative link `./hooks.json` to `../../scripts/little_loops/hooks/adapters/codex/hooks.json` (already moved; stale now regardless of BUG-2275)

### Wave 2 — After BUG-2275 lands (shell script move to in-package)

7. Update `docs/ARCHITECTURE.md` lines 99–104 directory tree: `hooks/adapters/codex/*.sh` entries → `scripts/little_loops/hooks/adapters/codex/`
8. Update `docs/development/TROUBLESHOOTING.md` lines 853–854 (chmod examples) and line 1122 (pre_compact handler note)
9. Update `docs/codex/getting-started.md` lines 69, 118, 131
10. Update `docs/codex/usage.md` line 66 (`bash {{LL_PLUGIN_ROOT}}/hooks/adapters/codex/pre-tool-use.sh`)
11. Update `docs/codex/README.md` line 24
12. Update `docs/claude-code/write-a-hook.md` lines 190, 325
13. Update `docs/development/TESTING.md` line 903
14. Update `docs/reference/HOST_COMPATIBILITY.md` line 260
15. Update `docs/reference/API.md` line 6800
16. Update `hooks/adapters/codex/README.md` lines 113, 201
17. Update `skills/configure/areas.md` line 890
18. Run the verification grep — must exit with zero matches:
    ```bash
    grep -rn "hooks/prompts/optimize-prompt-hook\|hooks/adapters/codex" \
      docs/ agents/ skills/ hooks/adapters/codex/README.md
    ```
19. Commit wave-1 and wave-2 as separate docs/config-only commits.

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
- `/ll:wire-issue` - 2026-06-25T14:48:37 - `d2156314-5c57-4a4a-a962-c97a00142626.jsonl`
- `/ll:refine-issue` - 2026-06-25T14:38:39 - `03ab1b2b-04bc-4023-8ad7-999a9f5fcd1c.jsonl`
- `/ll:format-issue` - 2026-06-25T14:21:47 - `9c3a5bf0-be76-4e09-80f3-6eeb965681b5.jsonl`
- `/ll:capture-issue` - 2026-06-25T14:15:33Z - `2d7d1ea6-286a-44ba-ac2e-8609d33e0c76.jsonl`
