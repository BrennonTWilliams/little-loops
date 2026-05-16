---
discovered_date: 2026-02-22
discovered_by: conversation-analysis
confidence_score: 95
---

# ENH-465: Audit settings files across all scopes (user, managed, project)

## Summary

The audit's config files auditor checks `.claude/settings.local.json` and `.claude/ll-config.json` but does not audit the full settings file hierarchy: `~/.claude/settings.json` (user-global), `.claude/settings.json` (project-shared), and managed-settings.json (enterprise). It also does not validate the extensive settings schema (permissions, sandbox, MCP controls, attribution, environment variables, etc.) or detect conflicts between settings at different scopes.

## Current Behavior

Wave 1 Task 3 (config files auditor) validates:
- `.claude/ll-config.json` against `config-schema.json`
- `.claude/settings.local.json` — existence and JSON syntax
- `.mcp.json` — server config validation

Not audited:
- `~/.claude/settings.json` — user-global behavioral settings
- `.claude/settings.json` — project-shared settings (distinct from settings.local.json)
- Managed settings: `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS) or `/etc/claude-code/managed-settings.json` (Linux)
- `~/.claude.json` — global preferences file where user-scope and local-scope MCP configs live

Settings keys not validated in any scope:
- `permissions.allow`, `permissions.deny`, `permissions.ask` — rule syntax validity (e.g., `Bash(npm run *)`, `Read(./.env)`, `mcp__server__tool`)
- `permissions.defaultMode` — valid mode enum
- `sandbox.*` — enabled, excludedCommands, network settings
- `env` — environment variable injection
- `attribution.commit`, `attribution.pr` — boolean
- `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers` — MCP approval controls
- `enabledPlugins` — plugin references resolve to installed plugins
- `plansDirectory` — path exists
- `model`, `availableModels` — valid model IDs
- `hooks` (inline in settings) — same validation as hooks.json

Not detected:
- Conflicts between settings at different scopes (user vs project vs local vs managed)
- Managed-only keys appearing in non-managed files (e.g., `disableBypassPermissionsMode` in project settings — would be silently ignored)
- Deprecated keys still present (e.g., `includeCoAuthoredBy`)

## Expected Behavior

1. Detect and validate all settings files in the hierarchy
2. Validate known settings keys per the documented schema
3. Flag unknown/deprecated keys
4. Detect scope conflicts (same key at multiple levels with different values)
5. Flag managed-only keys in non-managed files (silently ignored at runtime)
6. Validate permission rule syntax
7. Validate inline hooks definitions in settings files (same rules as hooks.json)

## Motivation

Settings files are the most security-sensitive configuration surface in Claude Code — `permissions.allow`/`deny` rules, `sandbox` settings, and `env` injection have direct security implications. Yet the audit only validates `.claude/settings.local.json` and misses the full file hierarchy including the shared project settings and user-global settings. Users with misconfigured permissions (e.g., overly broad `allow` rules in `.claude/settings.json`) receive no audit feedback, and conflicts between settings at different scopes are entirely invisible. Since settings errors can silently grant or deny access, comprehensive settings auditing is a security hygiene requirement.

## Proposed Solution

Extend the Wave 1 config files auditor to discover and validate all settings files in the hierarchy (`~/.claude/settings.json`, `.claude/settings.json`, `~/.claude.json`, managed-settings.json). Add validation rules for known settings keys (permissions, sandbox, attribution, MCP approval controls, inline hooks). Implement scope conflict detection — same key with different values at multiple levels. Flag managed-only keys appearing in non-managed files (silently ignored at runtime). Update `report-template.md` with a settings hierarchy section, and add Wave 2 cross-references for `enabledPlugins` → installed plugins and `plansDirectory` → path exists.

## Integration Map

### Files to Modify
- `skills/audit-claude-config/SKILL.md` — Extend Wave 1 Task 3 config auditor prompt with full settings hierarchy; add settings-specific validation rules
- `skills/audit-claude-config/report-template.md` — Add settings hierarchy section to report
- `agents/consistency-checker.md` — Add cross-references: `enabledPlugins` → installed plugins; `plansDirectory` → path exists; inline `hooks` → same validation

### Dependent Files
- `agents/codebase-locator.md` — The Wave 1 Task 3 agent; its prompt needs the expanded file list

## Implementation Steps

1. Add `~/.claude/settings.json`, `.claude/settings.json`, and managed-settings.json to Wave 1 config file list
2. Add `~/.claude.json` MCP config validation
3. Create settings key validation rules (known keys, types, value enums)
4. Add permission rule syntax validation (glob patterns, path types, MCP tool patterns)
5. Add scope conflict detection between settings files
6. Add managed-only key detection in non-managed files
7. Add deprecated key warnings
8. Update report template with settings hierarchy section
9. Update Wave 2 cross-references for settings-referenced paths

## Impact

- **Priority**: P2 — Settings misconfigurations are among the hardest to debug; permissions and sandbox settings have security implications
- **Effort**: Medium-High — Many settings keys to validate; requires understanding the full settings schema
- **Risk**: Low — Additive audit; no behavior changes
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Discovering and validating all settings files in the hierarchy; validating known settings keys; detecting scope conflicts; flagging deprecated keys; validating permission rule syntax; validating inline hooks in settings files
- **Out of scope**: Validating managed-settings content for enterprise-specific policies, suggesting settings changes, auditing non-Claude-Code config files

## Labels

`enhancement`, `captured`, `skills`, `audit-claude-config`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocks

- ENH-466

## Resolution

**Implemented** on 2026-02-23.

### Changes Made
- **`skills/audit-claude-config/SKILL.md`**: Extended Wave 1 Task 3 with full settings hierarchy (managed, user, project, local, global prefs); added comprehensive settings key validation rules for 40+ recognized keys; added permission rule syntax validation; added deprecated key detection (`includeCoAuthoredBy`); added managed-only key detection in non-managed files; added `settings` audit scope; updated Wave 1 summary and Phase 2 reference compilation; updated Wave 2 internal checker with scope conflict detection, inline hooks validation, plansDirectory/enabledPlugins cross-references; updated Wave 2 external checker with permission overlap detection, managed-only key misplacement warnings, deprecated key warnings.
- **`skills/audit-claude-config/report-template.md`**: Added Settings Hierarchy section with 6 sub-tables (file inventory, key validation, permission rules, scope conflicts, deprecated keys, managed-only keys); added Settings Scope Conflicts and Permission Overlaps tables in Wave 2; added Settings hierarchy health score category (8%); rebalanced health score weights; updated Wave 1 summary format.
- **`agents/consistency-checker.md`**: Added 7 settings-specific cross-reference checks to matrix; added settings data extraction to Step 1; added 4 settings conflict detection rules to Step 3; added 8 new output tables (scope conflicts, permission overlaps, inline hooks, plansDirectory, enabledPlugins, managed-only keys, deprecated keys); added 7 new check types to Wave 2 summary table.

---

## Status

**Completed** | Created: 2026-02-22 | Completed: 2026-02-23 | Priority: P2
