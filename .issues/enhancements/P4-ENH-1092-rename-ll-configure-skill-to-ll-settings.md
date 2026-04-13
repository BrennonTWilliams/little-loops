---
id: ENH-1092
type: ENH
priority: P4
size: XS
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 28
---

# ENH-1092: Rename /ll:configure Skill to /ll:settings

## Summary

Rename the `/ll:configure` skill to `/ll:settings` to better reflect its purpose and align with familiar terminology that users expect for configuration management.

## Current Behavior

The skill for viewing and editing little-loops configuration is invoked via `/ll:configure`.

## Expected Behavior

The skill should be invokable via `/ll:settings`, with `/ll:configure` either removed or aliased to `/ll:settings` for backwards compatibility.

## Motivation

`/ll:settings` is more intuitive and consistent with the UX patterns users encounter in VS Code, GitHub, and other developer tools. The word "settings" better conveys that this is a place to view and change options, while "configure" reads more like an action verb for initial setup.

## Proposed Solution

Rename `skills/configure/` directory to `skills/settings/` and update the SKILL.md frontmatter, trigger keywords, and all cross-references throughout commands, docs, and CLAUDE.md.

## Integration Map

### Files to Modify

**Directory rename** (this is what changes the invocation name — no `name:` field in SKILL.md):
- `skills/configure/` → `skills/settings/` via `git mv skills/configure skills/settings`

**Companion files with self-references** (update after `git mv`):
- `skills/configure/SKILL.md` — 8+ occurrences of `/ll:configure` in body (lines 142–144, 181, 309, 344, 347, 350, 353, 356); trigger keywords in frontmatter
- `skills/configure/areas.md` — 4 occurrences (lines 851, 858, 881, 885)
- `skills/configure/show-output.md` — 11 `Edit: /ll:configure <area>` footers (lines 20, 35, 51, 65, 82, 98, 114, 127, 141, 154, 170)

**Commands:**
- `commands/help.md:193,267` — skill listed in command table

**Root/config docs:**
- `.claude/CLAUDE.md:58` — `configure`^ in Session & Config skill group
- `README.md:185,469` — command table and prose description
- `CONTRIBUTING.md:135` — directory tree entry for `configure/`

**Reference docs:**
- `docs/reference/COMMANDS.md:38,50,604` — skill listed and described
- `docs/reference/CONFIGURATION.md:5,667` — references `/ll:configure` for config editing
- `docs/guides/GETTING_STARTED.md:104` — references `/ll:configure`
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:722` — references `/ll:configure`
- `docs/development/TROUBLESHOOTING.md:333` — references `/ll:configure`
- `docs/ARCHITECTURE.md:119` — directory tree lists `configure/` by name

**No changes needed:**
- `.claude-plugin/plugin.json` — skills are auto-discovered from `skills/` directory; not registered individually

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md:455,559` — references `/ll:configure` in post-init instructions
- `skills/init/interactive.md:145,213,255,442,444,734,735,736` — 8 references to `/ll:configure`

### Similar Patterns
- `P3-ENH-753-rename-confidence-check-skill-to-score-confidence.md` — precedent for skill rename workflow

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_update_skill.py:17` — hardcodes `PROJECT_ROOT / "skills" / "configure" / "SKILL.md"` as `CONFIGURE_SKILL_FILE`; 3 test methods in `TestConfigureSkillDevInstallFix` (lines 205–227) will raise `FileNotFoundError` after `git mv` — update path constant to `"skills" / "settings" / "SKILL.md"`
- `scripts/tests/test_create_extension_wiring.py:16` — hardcodes `PROJECT_ROOT / "skills" / "configure" / "areas.md"` as `CONFIGURE_AREAS`; 5 test methods in `TestConfigureAreasWiring` and `TestBug863HooksInstallRemoved` (lines 55–65, 125–145) will raise `FileNotFoundError` — update path constant to `"skills" / "settings" / "areas.md"`

### Documentation
- `docs/` — any pages listing available skills/commands
- README if it references `/ll:configure`

### Configuration
- N/A

## Implementation Steps

1. `git mv skills/configure skills/settings` — renames the directory, which is the sole source of the skill's invocation name
2. Update self-references in the renamed skill files:
   - `skills/settings/SKILL.md` — trigger keywords in frontmatter + ~8 body occurrences
   - `skills/settings/areas.md` — 4 occurrences (lines 851, 858, 881, 885)
   - `skills/settings/show-output.md` — 11 footer references (lines 20–170)
3. Update cross-skill callers: `skills/init/SKILL.md:455,559` and `skills/init/interactive.md` (8 occurrences)
4. Update commands: `commands/help.md:193,267`
5. Update root docs: `.claude/CLAUDE.md:58`, `README.md:185,469`, `CONTRIBUTING.md:135`
6. Update reference docs: `docs/reference/COMMANDS.md`, `docs/reference/CONFIGURATION.md`, `docs/guides/GETTING_STARTED.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `docs/development/TROUBLESHOOTING.md`, `docs/ARCHITECTURE.md:119`
7. Verify with `/ll:help` that `/ll:settings` appears and `/ll:configure` is gone

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_update_skill.py:17` — change `CONFIGURE_SKILL_FILE` path constant from `"skills" / "configure" / "SKILL.md"` to `"skills" / "settings" / "SKILL.md"`
9. Update `scripts/tests/test_create_extension_wiring.py:16` — change `CONFIGURE_AREAS` path constant from `"skills" / "configure" / "areas.md"` to `"skills" / "settings" / "areas.md"`
10. Update open issues that reference `skills/configure/areas.md` in their implementation steps (path will become stale after rename):
    - `.issues/features/P4-FEAT-1006-ll-logs-skills-commands-wiring.md` (lines 62, 71, 85–86, 89, 104, 132, 149, 153)
    - `.issues/features/P4-FEAT-1002-ll-logs-cli-core-implementation.md` (lines 103, 118)
    - `.issues/enhancements/P4-ENH-977-add-ll-verify-skills-cli-lint-command.md` (lines 48, 68)

## Impact

- **Priority**: P4 - Low; quality-of-life naming improvement, not blocking anything
- **Effort**: Small - mostly a file rename and cross-reference sweep
- **Risk**: Low - purely cosmetic rename with no logic changes
- **Breaking Change**: Yes (existing users invoking `/ll:configure` will need to use `/ll:settings`)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ux`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-12_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 28/100 → VERY LOW

### Outcome Risk Factors
- Wide reference surface (14+ external files) despite mechanical changes — real risk is missing a reference; use grep validation after implementation
- Tests break immediately after `git mv`: update `test_update_skill.py:17` and `test_create_extension_wiring.py:16` in the same commit as the rename
- Alias vs. remove is implicitly resolved as "remove" by the implementation steps — confirm this is intentional before starting
- ENH-753 (cited precedent) is still open — no prior skill rename has been completed in this codebase

## Session Log
- `/ll:wire-issue` - 2026-04-13T04:37:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad8a9ad0-9a73-4793-b1e6-e50aecd235da.jsonl`
- `/ll:refine-issue` - 2026-04-13T04:03:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c999cd5-2c5d-4efe-b7aa-08e541838d9e.jsonl`

- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be8d38a6-5096-4b3f-866b-c58ff412ccff.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0fdf433f-8715-497e-8e15-6a521d4707d0.jsonl`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P4
