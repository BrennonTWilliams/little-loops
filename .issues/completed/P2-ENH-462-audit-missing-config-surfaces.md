---
discovered_date: 2026-02-22
discovered_by: conversation-analysis
---

# ENH-462: Audit missing configuration surfaces (output styles, LSP, keybindings, .claudeignore)

## Summary

`/ll:audit-claude-config` does not audit several Claude Code configuration surfaces that exist as of February 2026: output styles, LSP servers, keybindings, `.claudeignore`, and plugin-level `settings.json`. These are legitimate config surfaces that users can misconfigure, and the audit tool should at minimum detect their presence and validate basic structure.

## Current Behavior

The audit's three Wave 1 agents scan CLAUDE.md hierarchy, plugin components (agents/skills/commands/hooks), and config files (ll-config.json, settings.local.json, .mcp.json). The following surfaces are entirely absent:

1. **Output Styles** — `.claude/output-styles/` and `~/.claude/output-styles/` directories. Custom output style markdown files with YAML frontmatter (`name`, `description`, `keep-coding-instructions`). The `outputStyle` setting in `.claude/settings.local.json` that references them.
2. **LSP Servers** — `.lsp.json` in plugin root and `lspServers` field in `plugin.json`. JSON config with `command`, `args`, `transport`, `extensionToLanguage`, timeout settings.
3. **Keybindings** — `~/.claude/keybindings.json` with context-scoped key bindings across 16+ contexts.
4. **`.claudeignore`** — Gitignore-syntax file that controls what Claude can see. Misconfiguration here is invisible and hard to debug.
5. **Plugin `settings.json`** — Plugin-root `settings.json` for default agent settings.

## Expected Behavior

Each missing surface should be added to the audit with at minimum:

| Surface | Existence Check | Syntax Validation | Semantic Check | Cross-Reference |
|---|---|---|---|---|
| Output Styles | Dir exists, list files | YAML frontmatter parses | `keep-coding-instructions` is boolean | `outputStyle` setting → file exists |
| LSP Servers | `.lsp.json` exists | Valid JSON | Commands exist, timeouts reasonable | `lspServers` in plugin.json → .lsp.json |
| Keybindings | File exists | Valid JSON, `$schema` present | Contexts are valid (16 known), actions exist | N/A (user-global only) |
| `.claudeignore` | File exists | Valid gitignore syntax | No overly broad patterns (e.g., `*`) | `respectGitignore` setting alignment |
| Plugin settings.json | File exists | Valid JSON | Only supported keys (`agent`) | N/A |

## Motivation

Five configuration surfaces added to Claude Code—output styles, LSP servers, keybindings, `.claudeignore`, and plugin `settings.json`—are entirely invisible to `/ll:audit-claude-config`. Users who misconfigure these surfaces receive no actionable feedback, making debugging harder. As Claude Code adds new configuration capabilities, the audit must keep pace to remain a reliable correctness signal rather than an incomplete check that gives false assurance.

## Proposed Solution

Extend the `skills/audit-claude-config` Wave 1 Task 3 (config files auditor) and Wave 2 (consistency checker) to cover the five missing surfaces. For each surface, add at minimum an existence check, syntax/schema validation, and semantic checks (e.g., `outputStyle` setting cross-referenced against output style files; `lspServers` in `plugin.json` cross-referenced with `.lsp.json`). Update `report-template.md` with report sections for each new surface. Optionally add `output-styles`, `lsp`, `keybindings` scope values to the audit's scope argument.

## Integration Map

### Files to Modify
- `skills/audit-claude-config/SKILL.md` — Add audit scope for each surface; extend Wave 1 Task 3 (config files auditor) or add a new Wave 1 task
- `skills/audit-claude-config/report-template.md` — Add report sections for new surfaces
- `agents/codebase-locator.md` — May need prompt updates if Task 3 agent is extended

### Dependent Files
- `agents/consistency-checker.md` — Wave 2 cross-references need new reference types (outputStyle → file, lspServers → .lsp.json)

### Configuration
- `skills/audit-claude-config/SKILL.md` scope argument — consider adding `output-styles`, `lsp`, `keybindings` scope values

## Implementation Steps

1. Add output styles detection and validation to Wave 1 config auditor
2. Add LSP server config detection and validation
3. Add keybindings file detection and validation
4. Add .claudeignore detection and validation
5. Add plugin settings.json detection
6. Extend Wave 2 consistency checker with new cross-references (outputStyle → file, lspServers → plugin.json)
7. Update report template with new sections
8. Update scope argument to support new surface names

## Impact

- **Priority**: P2 — These are real config surfaces users can misconfigure with no feedback
- **Effort**: Medium — Mostly prompt additions to existing agents; no architectural changes
- **Risk**: Low — Additive; existing audit logic untouched
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding audit logic for the five missing config surfaces (output styles, LSP servers, keybindings, .claudeignore, plugin settings.json); adding Wave 2 cross-references for new surface types; updating report template
- **Out of scope**: Auditing surfaces from other tools (non-Claude Code configs), deep semantic analysis of output style content, suggesting keybinding improvements

## Labels

`enhancement`, `captured`, `skills`, `audit-claude-config`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`
- `/ll:manage-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff26efc-756f-45c9-b95d-159619b176d9.jsonl`

---

## Resolution

**Completed** | 2026-02-22

All five missing configuration surfaces have been added to the audit:

1. **Output Styles** — Added to SKILL.md Task 3 with existence check, YAML frontmatter validation, `keep-coding-instructions` boolean check, and `outputStyle` setting extraction for Wave 2 cross-reference. Report template and Wave 2 external checker extended.
2. **LSP Servers** — Added to SKILL.md Task 3 with .lsp.json existence check, JSON validation, command/transport/timeout checks, and `lspServers`→`.lsp.json` cross-reference in Wave 2 internal checker.
3. **Keybindings** — Added to SKILL.md Task 3 with `~/.claude/keybindings.json` existence check, JSON validation, `$schema` presence, and context/action field validation.
4. **.claudeignore** — Added to SKILL.md Task 3 with existence check, syntax validation, broad-pattern detection, and `respectGitignore` alignment in Wave 2 external checker.
5. **Plugin settings.json** — Added to SKILL.md Task 3 with existence check, JSON validation, and unrecognized keys detection.

### Files Changed
- `skills/audit-claude-config/SKILL.md` — Updated scope argument, Configuration Files list, Audit Scopes, Task 3 prompt, Phase 2 reference compilation, Wave 1 summary table, Wave 2 Task 1 (LSP cross-ref), Wave 2 Task 2 (outputStyle + respectGitignore cross-refs)
- `skills/audit-claude-config/report-template.md` — Added report sections for all 5 surfaces; updated health score table (added "Extended config surfaces" row) and weight calculation; updated Wave 1 summary format
- `agents/consistency-checker.md` — Added 3 rows to Cross-Reference Matrix; added 5 extraction steps to Step 1; added 3 new output subsections (Output Styles, LSP, .claudeignore); added 3 rows to Summary table

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-22 | Priority: P2
