# Wave-1 Audit Sub-Agent Prompts

This file holds the verbatim prompt bodies for the three Wave-1 audit
sub-agents spawned by `audit-claude-config`, plus the recognized-settings-key
reference table used by the Config Files Auditor. The SKILL.md operational flow
points here so each Task can be issued with its full prompt without inflating
the main skill file.

Spawn all three Wave-1 agents in a SINGLE message with multiple Task tool
calls.

---

## Task 1: CLAUDE.md Auditor

```
Use Task tool with subagent_type="codebase-analyzer"

Prompt:
Audit all memory files for this project across the full Claude Code memory hierarchy:

Files to check:
- Managed policy (macOS: /Library/Application Support/ClaudeCode/CLAUDE.md, Linux: /etc/claude-code/CLAUDE.md)
- Project memory: .claude/CLAUDE.md and ./CLAUDE.md
- Project rules: .claude/rules/*.md (recursive, including subdirectories)
- User memory: ~/.claude/CLAUDE.md
- User rules: ~/.claude/rules/*.md (recursive, including subdirectories)
- Project memory (local): ./CLAUDE.local.md
- Auto memory: ~/.claude/projects/<project>/memory/MEMORY.md and topic files

For each file found, analyze:

1. **Structure Assessment**:
   - Clear section organization with headers
   - Logical instruction grouping
   - Appropriate use of H1/H2/H3 hierarchy
   - @import usage for modularity (max 5 hops recursive; relative paths resolve from containing file; not evaluated in code blocks)

2. **Content Quality**:
   - Instructions are actionable and specific
   - No vague or ambiguous directives
   - No contradictory rules within the file
   - References to files/paths are accurate

3. **Best Practices**:
   - Does not duplicate default Claude behavior
   - Project-specific overrides are clearly marked
   - Sensitive information not exposed
   - Efficient token usage

4. **Performance Check**:
   - File size (warn if >50KB)
   - Redundant instructions identified
   - Unnecessary verbosity

5. **Rules-Specific Validation** (for .claude/rules/*.md and ~/.claude/rules/*.md):
   - YAML frontmatter parses correctly
   - `paths` field, if present, is an array of strings
   - Glob patterns in `paths` use valid syntax
   - Symlink resolution: symlinked files resolve to existing targets
   - No circular symlinks

6. **Auto Memory Checks** (for ~/.claude/projects/<project>/memory/):
   - MEMORY.md line count (warn if >200 lines, as only first 200 are loaded)
   - List topic files present in the memory directory

Return structured findings with:
- File path, size, section count
- Memory type label per file (managed/project/user/auto/local)
- Quality score (1-10) per file
- Issues found with severity (CRITICAL/WARNING/INFO)
- Line numbers for each issue
- Rules directory summary (files found, symlinks detected, frontmatter parse results)
- Auto memory size check results
- List of all @import references for Wave 2
- List of all command references (/ll:X) for Wave 2
- List of all MCP tool references for Wave 2
- List of all symlinks in rules directories for Wave 2
- List of all rules path patterns for Wave 2
```

---

## Task 2: Plugin Components Auditor

```
Use Task tool with subagent_type="plugin-config-auditor"

Prompt:
Audit all plugin component definitions:

**Agents** (agents/*.md):
- Description quality and trigger keywords
- allowed_tools appropriateness for stated purpose
- Model selection justification
- Example quality and relevance
- System prompt clarity

**Skills** (skills/*.md):
- Description with trigger keywords
- Content structure and progressive disclosure
- Actionable guidance quality

**Commands** (commands/*.md):
- Frontmatter completeness (description, arguments)
- Argument definitions with types and requirements
- Example section quality and coverage
- Process/workflow clarity
- Integration documentation

**Hooks** (hooks/hooks.json + hooks/prompts/*.md + scripts/little_loops/hooks/prompts/*.md):
- Valid JSON syntax
- Recognized event types (17 official types)
- Handler types: command, prompt, agent
- Timeout values (defaults: 600s command, 30s prompt, 60s agent)
- Script/prompt file existence
- No dangerous patterns

Return structured findings with:
- Per-component type summary table
- Issues found with severity
- Quality scores per component type
- List of all subagent_type references for Wave 2
- List of all prompt file references for Wave 2
- List of all /ll:X command references found in skill files for Wave 2
```

---

## Task 3: Config Files Auditor

```
Use Task tool with subagent_type="codebase-locator"

Prompt:
Locate and audit all configuration files:

**Files to find and validate**:
- .ll/ll-config.json (validate against config-schema.json)
- config-schema.json (check for completeness)
- .mcp.json (project-scope MCP servers)
- ~/.claude.json → mcpServers field (user-scope MCP servers)
- ~/.claude.json → projects → <project-path> → mcpServers (local-scope MCP servers per project)
- managed-mcp.json at managed settings directory (macOS: /Library/Application Support/ClaudeCode/managed-mcp.json, Linux: /etc/claude-code/managed-mcp.json)

**Settings Hierarchy** (audit all scopes, highest precedence first):
- Managed: /Library/Application Support/ClaudeCode/managed-settings.json (macOS) or /etc/claude-code/managed-settings.json (Linux)
- User: ~/.claude/settings.json
- Project: .claude/settings.json
- Local: .claude/settings.local.json
- Global prefs: ~/.claude.json (MCP configs at user/local scope — extract mcpServers and per-project mcpServers for MCP audit; preferences — validate JSON syntax only)

For each settings file found:
1. Check exists/not exists
2. Validate JSON syntax
3. Validate known top-level keys against the recognized key list (see below)
4. Flag unknown top-level keys as WARNING
5. Flag deprecated keys with replacement guidance
6. Flag managed-only keys appearing in non-managed files as WARNING (silently ignored at runtime)

**Recognized settings keys** (validate types when present):
- `permissions.allow` — array of strings (permission rules)
- `permissions.deny` — array of strings (permission rules)
- `permissions.ask` — array of strings (permission rules)
- `permissions.defaultMode` — must be one of: `default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan`
- `permissions.additionalDirectories` — array of strings (paths)
- `permissions.disableBypassPermissionsMode` — managed-only; value must be `"disable"`
- `sandbox.enabled` — boolean
- `sandbox.autoAllowBashIfSandboxed` — boolean
- `sandbox.excludedCommands` — array of strings
- `sandbox.allowUnsandboxedCommands` — boolean
- `sandbox.network.allowUnixSockets` — array of strings (paths)
- `sandbox.network.allowAllUnixSockets` — boolean
- `sandbox.network.allowLocalBinding` — boolean
- `sandbox.network.allowedDomains` — array of strings
- `sandbox.network.httpProxyPort` — number
- `sandbox.network.socksProxyPort` — number
- `sandbox.enableWeakerNestedSandbox` — boolean
- `env` — object (string keys → string values)
- `attribution.commit` — string
- `attribution.pr` — string
- `hooks` — object (inline hook definitions; same validation rules as hooks.json)
- `disableAllHooks` — boolean
- `allowManagedHooksOnly` — managed-only; boolean
- `allowManagedPermissionRulesOnly` — managed-only; boolean
- `model` — string
- `enableAllProjectMcpServers` — boolean
- `enabledMcpjsonServers` — array of strings
- `disabledMcpjsonServers` — array of strings
- `allowedMcpServers` — managed-only; array of objects with `serverName`
- `deniedMcpServers` — managed-only; array of objects with `serverName`
- `strictKnownMarketplaces` — managed-only; array of objects
- `plansDirectory` — string (path; record for Wave 2 path existence check)
- `outputStyle` — string (record for Wave 2 cross-reference)
- `respectGitignore` — boolean (record for Wave 2 cross-reference)
- `statusLine` — object with `type` and `command` fields
- `fileSuggestion` — object with `type` and `command` fields
- `apiKeyHelper` — string (script path)
- `otelHeadersHelper` — string (script path)
- `awsAuthRefresh` — string
- `awsCredentialExport` — string
- `forceLoginMethod` — managed-only; must be `"claudeai"` or `"console"`
- `forceLoginOrgUUID` — managed-only; string (UUID format)
- `companyAnnouncements` — managed-only; array of strings
- `alwaysThinkingEnabled` — boolean
- `showTurnDuration` — boolean
- `language` — string
- `autoUpdatesChannel` — must be `"stable"` or `"latest"`
- `cleanupPeriodDays` — number (≥0)
- `spinnerVerbs` — object with `mode` (string) and `verbs` (array)
- `spinnerTipsEnabled` — boolean
- `terminalProgressBarEnabled` — boolean
- `prefersReducedMotion` — boolean
- `teammateMode` — must be `"auto"`, `"in-process"`, or `"tmux"`
- `$schema` — string (informational, always valid)

**Deprecated keys** (flag with WARNING and replacement guidance):
- `includeCoAuthoredBy` — deprecated, use `attribution` instead

**Managed-only keys** (flag WARNING if found in non-managed files — silently ignored at runtime):
- `disableBypassPermissionsMode`, `allowManagedHooksOnly`, `allowManagedPermissionRulesOnly`
- `allowedMcpServers`, `deniedMcpServers`, `strictKnownMarketplaces`
- `forceLoginMethod`, `forceLoginOrgUUID`, `companyAnnouncements`

**Permission rule syntax validation** (for `permissions.allow`, `permissions.deny`, `permissions.ask` arrays):
- Each rule must match format: `ToolName` or `ToolName(specifier)`
- Valid tool names include: `Bash`, `Read`, `Edit`, `Write`, `WebFetch`, `WebSearch`, `Task`, `mcp__*` (MCP tool pattern)
- Specifier can contain `*` wildcards for glob matching
- Flag rules with empty specifiers `Tool()` as WARNING
- Flag rules with unrecognized tool names as WARNING

For each config file (non-settings):
1. Check exists/not exists
2. Validate JSON syntax
3. Check schema compliance (where applicable)
4. Verify path references exist
5. Check for reasonable values (timeouts, worker counts)

For MCP config across ALL scopes (project, user, local, managed):
- Discover MCP servers at each scope:
  - Project: .mcp.json at project root
  - User: ~/.claude.json top-level mcpServers field
  - Local: ~/.claude.json → projects → <project-path> → mcpServers (per-project local overrides)
  - Managed: managed-mcp.json at system directory (macOS: /Library/Application Support/ClaudeCode/, Linux: /etc/claude-code/)
- For each server, detect transport type from fields present:
  - stdio transport (has `command` field): verify command exists and is executable; validate optional `args` (array), `env` (object), `cwd` (string)
  - http/sse transport (has `url` field): verify url is well-formed (valid URL format); validate optional `headers` (object of string key-value pairs)
  - Flag entries with neither `command` nor `url` as WARNING (unknown transport)
- No duplicate server names within a single scope
- ${VAR} and ${VAR:-default} environment variable expansion validation:
  - Scan `command`, `args`, `env`, `url`, `headers` fields for ${...} patterns
  - Valid syntax: ${VAR_NAME} or ${VAR_NAME:-default_value} (no nested expansions)
  - INFO if referenced env var is not currently set (may be set at runtime)
  - WARNING for malformed syntax (e.g., ${}, ${VAR:-}, unclosed ${, nested ${${...}})
- Record per-scope server inventory for Wave 2: server name, scope, transport type

**Output Styles** (.claude/output-styles/ and ~/.claude/output-styles/):
- Check if directory exists; list all .md files found
- For each file, validate YAML frontmatter parses correctly
- Verify `name` and `description` fields are present
- Verify `keep-coding-instructions` field, if present, is boolean
- Read `outputStyle` key from .claude/settings.local.json; record value for Wave 2 cross-reference

**LSP Servers** (.lsp.json at plugin root and lspServers in .claude-plugin/plugin.json):
- Check if .lsp.json exists; validate JSON syntax
- For each server entry: verify `command` array elements exist as executables, `transport` field is valid ("stdio" or "tcp"), `extensionToLanguage` map is well-formed, timeout values are reasonable (>0)
- Read `lspServers` field from .claude-plugin/plugin.json; record for Wave 2 cross-reference

**Keybindings** (~/.claude/keybindings.json):
- Check if file exists; validate JSON syntax
- Verify `$schema` field is present
- For each binding, verify `context` is one of the known valid contexts (16+ defined contexts such as: default, editor, terminal, sidebar, commandPalette, chatInput, chatHistory, fileTree, diffEditor, searchResults, notifications, statusBar, modalDialog, completionMenu, contextMenu, codeActions)
- Verify `action` field is non-empty for each binding
- Report count of bindings per context

**.claudeignore** (.claudeignore at project root):
- Check if file exists
- Validate gitignore syntax (no unrecognized directives)
- Flag overly broad patterns (bare `*` or `**` without path prefix)
- Read `respectGitignore` key from .claude/settings.local.json; record for Wave 2 cross-reference

**Plugin settings.json** (settings.json at plugin root):
- Check if file exists; validate JSON syntax
- Verify only supported keys are present (`agent` is the documented key)
- Report any unrecognized top-level keys as warnings

Return:
- Config file inventory with status
- JSON validation results
- Schema compliance issues
- Path reference validity
- MCP server inventory per scope (server name, scope, transport type) for Wave 2
- MCP env var expansion issues found for Wave 2
- List of all referenced paths for Wave 2
- Settings hierarchy inventory: which files exist at each scope (managed/user/project/local) for Wave 2
- Per-scope settings key inventory: all keys found in each settings file for Wave 2
- Settings key validation issues: unknown keys, type mismatches, deprecated keys, managed-only keys in wrong scope
- Permission rules found (all scopes) with syntax validation results for Wave 2
- Inline hooks definitions found in settings files (all scopes) for Wave 2
- plansDirectory value (if set, from any scope) for Wave 2 path existence check
- enabledPlugins values (if set, from any scope) for Wave 2 cross-reference
- outputStyle setting value (effective, considering scope precedence) for Wave 2
- respectGitignore setting value (effective, considering scope precedence) for Wave 2
- lspServers field presence (from plugin.json) for Wave 2
- Output style files found (paths) for Wave 2
- .claudeignore existence status for Wave 2
```
