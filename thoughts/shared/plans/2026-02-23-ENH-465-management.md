# ENH-465: Audit Settings Files Across All Scopes

## Plan Date: 2026-02-23

## Research Findings

### Current State
- Wave 1 Task 3 (codebase-locator) only audits: `.claude/ll-config.json`, `.claude/settings.local.json`, `.mcp.json`, `config-schema.json`
- Only two settings keys are validated: `outputStyle` and `respectGitignore` from `settings.local.json`
- No validation of `~/.claude/settings.json`, `.claude/settings.json`, managed-settings.json, or `~/.claude.json`
- No settings key schema validation, scope conflict detection, or deprecated key warnings

### Settings Hierarchy (from docs)
1. **Managed** (highest): `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS) / `/etc/claude-code/managed-settings.json` (Linux)
2. **User**: `~/.claude/settings.json`
3. **Project**: `.claude/settings.json`
4. **Local**: `.claude/settings.local.json`
5. **Global prefs**: `~/.claude.json` (MCP configs, preferences)

### Known Settings Keys (from official docs)
- `permissions.allow/deny/ask` — permission rule arrays
- `permissions.defaultMode` — enum: default, acceptEdits, dontAsk, bypassPermissions, plan
- `permissions.additionalDirectories` — array of paths
- `permissions.disableBypassPermissionsMode` — managed-only, value "disable"
- `sandbox.*` — enabled, autoAllowBashIfSandboxed, excludedCommands, allowUnsandboxedCommands, network.*
- `env` — object of env vars
- `attribution.commit`, `attribution.pr` — strings
- `includeCoAuthoredBy` — deprecated (use attribution instead)
- `hooks` — inline hook definitions
- `disableAllHooks` — boolean
- `allowManagedHooksOnly` — managed-only
- `allowManagedPermissionRulesOnly` — managed-only
- `model` — string model ID
- `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers` — MCP approval
- `allowedMcpServers`, `deniedMcpServers` — managed-only MCP allowlist/denylist
- `strictKnownMarketplaces` — managed-only
- `plansDirectory` — path string
- `outputStyle`, `respectGitignore`, `statusLine`, `fileSuggestion` — UI settings
- `apiKeyHelper`, `otelHeadersHelper`, `awsAuthRefresh`, `awsCredentialExport` — script helpers
- `forceLoginMethod`, `forceLoginOrgUUID` — login controls (managed)
- `alwaysThinkingEnabled`, `showTurnDuration`, `language` — preferences
- `autoUpdatesChannel`, `spinnerVerbs`, `spinnerTipsEnabled`, `terminalProgressBarEnabled`, `prefersReducedMotion` — UI
- `cleanupPeriodDays`, `companyAnnouncements`, `teammateMode` — misc

### Managed-Only Keys
Keys that only function in managed-settings.json:
- `disableBypassPermissionsMode`
- `allowManagedHooksOnly`
- `allowManagedPermissionRulesOnly`
- `allowedMcpServers`
- `deniedMcpServers`
- `strictKnownMarketplaces`
- `forceLoginMethod`
- `forceLoginOrgUUID`
- `companyAnnouncements`

### Deprecated Keys
- `includeCoAuthoredBy` — replaced by `attribution`

## Implementation Plan

### Files to Modify (3 files)

1. **`skills/audit-claude-config/SKILL.md`** — Extend Wave 1 Task 3 prompt with full settings hierarchy and settings key validation
2. **`skills/audit-claude-config/report-template.md`** — Add settings hierarchy section to report
3. **`agents/consistency-checker.md`** — Add cross-references for settings scope conflicts, enabledPlugins → installed, plansDirectory → path exists, inline hooks validation

### Phase 1: Extend SKILL.md Wave 1 Task 3

1. Add settings hierarchy files to Task 3's "Files to find and validate" list
2. Add settings key validation rules for each scope
3. Add permission rule syntax validation
4. Add deprecated key detection
5. Add managed-only key detection in non-managed files
6. Update the Return section with new Wave 2 data
7. Add `settings` scope option
8. Update Wave 1 summary table with Settings Hierarchy row
9. Update Phase 2 reference compilation with settings data

### Phase 2: Update report-template.md

1. Add "Settings Hierarchy" section after existing Config Files section
2. Add scope conflict table in Wave 2
3. Update health score to include settings validation

### Phase 3: Update consistency-checker.md

1. Add settings scope conflict detection to cross-reference matrix
2. Add `enabledPlugins` → installed plugins check
3. Add `plansDirectory` → path exists check
4. Add inline `hooks` in settings → same validation rules
5. Add managed-only key detection cross-check
6. Update output format with settings-specific tables
7. Update Wave 2 summary table with new check types

## Success Criteria

- [ ] All settings file scopes discovered and validated in Wave 1
- [ ] Known settings keys validated per documented schema
- [ ] Unknown/deprecated keys flagged
- [ ] Scope conflicts detected in Wave 2
- [ ] Managed-only keys in non-managed files flagged
- [ ] Permission rule syntax validated
- [ ] Inline hooks in settings validated
- [ ] Report template updated with settings hierarchy section
- [ ] Wave 1 and Wave 2 summary tables updated
- [ ] All tests pass
- [ ] Linting passes
