---
description: Comprehensive audit of Claude Code plugin configuration with parallel sub-agents
argument-hint: "[scope]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - Bash(git:*)
arguments:
  - name: scope
    description: Audit scope (all|managed|user|project|hooks|mcp|agents|commands|skills|output-styles|lsp|keybindings|claudeignore|plugin-settings|settings)
    required: false
  - name: flags
    description: "Optional flags: --non-interactive (no prompts), --fix (auto-apply safe fixes)"
    required: false
---

# Audit Claude Configuration

You are tasked with performing a comprehensive audit of CLAUDE.md files and Claude Code plugin configuration using a three-wave parallel sub-agent architecture.

## Configuration Files to Audit

### Memory Files (Hierarchy Order)
1. **Managed policy**: Organization-wide instructions
   - macOS: `/Library/Application Support/ClaudeCode/CLAUDE.md`
   - Linux: `/etc/claude-code/CLAUDE.md`
2. **Project memory**: `./.claude/CLAUDE.md` or `./CLAUDE.md` - Team-shared instructions
3. **Project rules**: `./.claude/rules/*.md` - Modular project instructions (supports `paths` frontmatter for conditional loading, subdirectories, symlinks)
4. **User memory**: `~/.claude/CLAUDE.md` - Personal preferences for all projects
5. **User rules**: `~/.claude/rules/*.md` - Personal modular rules (loaded before project rules)
6. **Project memory (local)**: `./CLAUDE.local.md` - Personal project preferences (auto-gitignored)
7. **Auto memory**: `~/.claude/projects/<project>/memory/MEMORY.md` - Claude's automatic notes (first 200 lines loaded at startup; topic files loaded on-demand)

### Plugin Components
- **Agents**: `agents/*.md` - Sub-agent definitions
- **Skills**: `skills/*.md` - Skill definitions
- **Commands**: `commands/*.md` - Slash command definitions
- **Hooks**: `hooks/hooks.json` + `hooks/prompts/*.md` - Lifecycle hooks

### Settings Files (Hierarchy Order - highest precedence first)
1. **Managed settings**: `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS) or `/etc/claude-code/managed-settings.json` (Linux)
2. **User settings**: `~/.claude/settings.json` - Personal settings across all projects
3. **Project settings**: `.claude/settings.json` - Team-shared project settings (committed to git)
4. **Local settings**: `.claude/settings.local.json` - Personal project overrides (gitignored)
5. **Global preferences**: `~/.claude.json` - Preferences, OAuth, user/local MCP configs

### Configuration Files
- **Plugin Config**: `./.claude/ll-config.json` - Little-loops plugin config
- **Config Schema**: `config-schema.json` - Configuration validation schema
- **MCP Config**: `.mcp.json` (project), `~/.claude.json` mcpServers (user/local), `managed-mcp.json` (managed) - MCP servers across all scopes
- **Output Styles**: `.claude/output-styles/` and `~/.claude/output-styles/` - Custom output style markdown files with YAML frontmatter
- **LSP Servers**: `.lsp.json` (plugin root) - LSP server config; `lspServers` field in `.claude-plugin/plugin.json`
- **Keybindings**: `~/.claude/keybindings.json` - Context-scoped key bindings
- **.claudeignore**: `.claudeignore` - Gitignore-syntax file controlling what Claude can see
- **Plugin settings**: `settings.json` (plugin root) - Default agent settings

## Audit Scopes

- **all**: Complete audit of all configuration (default)
- **managed**: Focus on managed policy (organization-wide CLAUDE.md)
- **user**: Focus on user memory (~/.claude/CLAUDE.md) and user rules (~/.claude/rules/)
- **project**: Focus on project memory, project rules, and local overrides
- **hooks**: Audit hooks configuration only
- **mcp**: Audit MCP server configuration only
- **agents**: Audit agent definitions only
- **commands**: Audit command definitions only
- **skills**: Audit skill definitions only
- **output-styles**: Audit output style files and outputStyle setting cross-reference
- **lsp**: Audit LSP server configuration (.lsp.json and lspServers in plugin.json)
- **keybindings**: Audit keybindings file (~/.claude/keybindings.json)
- **claudeignore**: Audit .claudeignore file and respectGitignore setting alignment
- **plugin-settings**: Audit plugin root settings.json
- **settings**: Audit all settings files across scopes (managed, user, project, local) with key validation and conflict detection

## Flags

- **--non-interactive**: Skip all prompts, report only (for CI/automation)
- **--fix**: Auto-apply safe fixes with progress display

$ARGUMENTS

---

## Process

### Phase 0: Initialize

```
Parse arguments:
- SCOPE="${scope:-all}"
- NON_INTERACTIVE=false (set true if flags contains "--non-interactive")
- AUTO_FIX=false (set true if flags contains "--fix")
```

Create a todo list to track audit progress:

```
Use TodoWrite to create:
- Discover configuration files
- Wave 1: Audit CLAUDE.md files
- Wave 1: Audit plugin components
- Wave 1: Audit config files
- Wave 2: Check internal consistency
- Wave 2: Check external consistency
- Wave 3: Generate fix suggestions
- Interactive fix session (unless --non-interactive)
- Generate final report
```

### Phase 1: Wave 1 - Individual Component Audits (Parallel)

**IMPORTANT**: Spawn all 3 agents in a SINGLE message with multiple Task tool calls.

Based on SCOPE, spawn the relevant agents:

#### Task 1: CLAUDE.md Auditor
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

#### Task 2: Plugin Components Auditor
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

**Hooks** (hooks/hooks.json + hooks/prompts/*.md):
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

#### Task 3: Config Files Auditor
```
Use Task tool with subagent_type="codebase-locator"

Prompt:
Locate and audit all configuration files:

**Files to find and validate**:
- .claude/ll-config.json (validate against config-schema.json)
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

### Phase 2: Collect Wave 1 Results

After all Wave 1 agents complete:

1. **Merge findings** from all 3 agents
2. **Compile reference lists** for Wave 2:
   - All subagent_type values found in commands
   - All prompt file paths found in hooks
   - All @import references found in CLAUDE.md
   - All command references (/ll:X) found in CLAUDE.md
   - All command references (/ll:X) found in skill files
   - All MCP tool/server references found
   - MCP server inventory per scope (server name, scope, transport type)
   - MCP approval settings: enableAllProjectMcpServers, enabledMcpjsonServers, disabledMcpjsonServers, allowedMcpServers, deniedMcpServers (from settings audit)
   - All file paths mentioned in configs
   - Settings hierarchy inventory (which files exist per scope, all keys per file)
   - Settings scope conflict data (same key at multiple scopes with different values)
   - Permission rules from all settings scopes (for syntax and overlap analysis)
   - Inline hooks from settings files (for validation against hooks.json rules)
   - `plansDirectory` value (from any scope) for path existence check
   - `enabledPlugins` values (from any scope) for cross-reference
   - `outputStyle` setting value (effective, considering scope precedence) and output style files found
   - `respectGitignore` setting value (effective, considering scope precedence) and .claudeignore existence
   - `lspServers` field presence in plugin.json and .lsp.json existence
3. **Calculate preliminary scores**:
   - CLAUDE.md health: X/10
   - Plugin components health: X/10
   - Config files health: X/10

Present Wave 1 summary:

```
Wave 1 Analysis Complete

| Category | Files | Issues | Health |
|----------|-------|--------|--------|
| CLAUDE.md | X | Y | Z/10 |
| Agents | X | Y | Z/10 |
| Skills | X | Y | Z/10 |
| Commands | X | Y | Z/10 |
| Hooks | X | Y | Z/10 |
| Config | X | Y | Z/10 |
| Settings Hierarchy | X | Y | Z/10 |
| Output Styles | X | Y | Z/10 |
| LSP Servers | X | Y | Z/10 |
| Keybindings | X | Y | Z/10 |
| .claudeignore | X | Y | Z/10 |
| Plugin settings | X | Y | Z/10 |

Critical issues: N
Warnings: N
Info: N

```

Proceed directly to Wave 2 consistency checks.

### Phase 3: Wave 2 - Cross-Component Consistency (Parallel)

**IMPORTANT**: Spawn both agents in a SINGLE message with multiple Task tool calls.

#### Task 1: Internal Consistency Checker
```
Use Task tool with subagent_type="consistency-checker"

Prompt:
Using these references from Wave 1, check internal plugin consistency:

References to validate:
[INSERT COMPILED REFERENCE LISTS FROM WAVE 1]

Check:
1. **Commands → Agents**: Every subagent_type value has matching agents/X.md
2. **Hooks → Prompts**: Every prompt path in hooks.json resolves to existing file
3. **Config → Schema**: ll-config.json values comply with config-schema.json types
4. **CLAUDE.md → @imports**: Every @import reference resolves to existing file
5. **Rules → Frontmatter**: YAML frontmatter in .claude/rules/*.md and ~/.claude/rules/*.md parses correctly
6. **Rules → Paths**: Glob patterns in `paths` fields are syntactically valid
7. **Rules → Symlinks**: All symlinks in rules directories resolve to existing targets
8. **Auto Memory → Size**: MEMORY.md ≤ 200 lines (only first 200 loaded at startup)
9. **Skills → Commands**: /ll:X references in skill files have matching commands/X.md or are valid skill names (skills/X/SKILL.md exists)
10. **LSP → Config**: If `lspServers` field is present in plugin.json, verify .lsp.json exists at plugin root; if .lsp.json exists, verify `lspServers` is referenced in plugin.json
11. **Settings → Scope Conflicts**: Detect same key set at multiple scopes with different values; report which scope wins per precedence (managed > local > project > user)
12. **Settings → Inline Hooks**: If `hooks` key is present in any settings file, validate using same rules as hooks.json (event types, handler types, timeout defaults)
13. **Settings → plansDirectory**: If `plansDirectory` is set in any scope, verify the path exists or note it will be created on first use
14. **Settings → enabledPlugins**: If `enabledPlugins` is set, cross-reference against installed plugin directories

Return:
- Reference validation table with status for each
- List of missing references (CRITICAL)
- List of broken references (WARNING)
- Rules validation results (frontmatter, paths, symlinks)
- Auto memory size warnings
- Skills → Commands validation results
- LSP cross-reference results
- Settings scope conflict table (key, scopes, values, effective value)
- Settings inline hooks validation results
- Settings path reference results (plansDirectory, enabledPlugins)
- Internal consistency score
```

#### Task 2: External Consistency Checker
```
Use Task tool with subagent_type="consistency-checker"

Prompt:
Using these references from Wave 1, check external consistency:

References to validate:
[INSERT COMPILED REFERENCE LISTS FROM WAVE 1]

Check:
1. **CLAUDE.md → MCP**: MCP tools mentioned exist in any MCP scope (project, user, local, managed)
2. **MCP Scope Conflicts**: Detect same server name defined at multiple scopes; report which scope takes precedence (managed > local > project > user)
3. **MCP Approval → Servers**: Cross-reference enabledMcpjsonServers/disabledMcpjsonServers against actual server names in .mcp.json; flag references to non-existent servers as WARNING
4. **MCP Managed Policy → Servers**: If allowedMcpServers/deniedMcpServers present in managed settings, cross-reference against all discovered server names across all scopes; flag servers blocked by managed deny that are configured in project/user scope as WARNING
5. **CLAUDE.md → Commands**: /ll:X references have matching commands/X.md
6. **Hooks → Scripts**: Bash scripts referenced are executable
7. **Config → Paths**: File paths in config files exist in filesystem
8. **Memory Hierarchy**: Check for conflicts between managed policy, user memory, and project memory
9. **Rules Path Overlap**: Detect overlapping path patterns across rules files
10. **Local vs Project**: Check for conflicts between CLAUDE.local.md and project CLAUDE.md
11. **outputStyle → Output Style File**: If `outputStyle` is set in any settings scope, verify the referenced output style file exists in .claude/output-styles/ or ~/.claude/output-styles/ (use effective value considering scope precedence)
12. **respectGitignore → .claudeignore**: If `respectGitignore` is false (or absent) but .claudeignore exists, warn about potential confusion; if `respectGitignore` is true but no .claudeignore or .gitignore exists, note that ignore file may be missing
13. **Settings → Permission Overlap**: Detect permission rules at different scopes that may conflict (e.g., `allow` at user scope contradicted by `deny` at project scope for same pattern)
14. **Settings → Managed-Only Keys**: Flag managed-only keys (`disableBypassPermissionsMode`, `allowManagedHooksOnly`, `allowManagedPermissionRulesOnly`, `allowedMcpServers`, `deniedMcpServers`, `strictKnownMarketplaces`, `forceLoginMethod`, `forceLoginOrgUUID`, `companyAnnouncements`) found in non-managed settings files — these are silently ignored at runtime
15. **Settings → Deprecated Keys**: Flag `includeCoAuthoredBy` in any settings file with guidance to use `attribution` instead

Return:
- External reference validation table
- Hierarchy conflicts detected with recommended resolution
- Rules path overlap warnings
- List of missing/broken external references
- MCP scope conflict table (server name, scopes, precedence winner)
- MCP approval cross-reference results (enabledMcpjsonServers/disabledMcpjsonServers vs actual servers)
- MCP managed policy results (allowedMcpServers/deniedMcpServers vs configured servers)
- outputStyle cross-reference result
- respectGitignore alignment result
- Settings permission overlap warnings
- Settings managed-only key misplacement warnings
- Settings deprecated key warnings
- External consistency score
```

### Phase 4: Collect Wave 2 Results

Merge Wave 2 findings:
1. Combine internal and external consistency results
2. Deduplicate overlapping findings
3. Update health scores with consistency factors

### Phase 5: Wave 3 - Generate Fix Suggestions (Sequential)

Synthesize all findings from Waves 1 and 2 into prioritized fix suggestions:

#### Categorize by Severity

**Critical (Must Fix)** - Will cause failures:
- Missing agent files referenced by commands
- Missing prompt files referenced by hooks
- Invalid JSON in config files
- Missing required config keys
- Broken MCP server paths
- MCP servers blocked by managed deny policy while configured in project/user scope

**Warning (Should Fix)** - May cause issues:
- Missing @import files
- Conflicting instructions between managed/user/project memory
- CLAUDE.local.md not in .gitignore
- Auto memory MEMORY.md exceeds 200 lines
- Broken symlinks in rules directories
- Invalid glob patterns in rules frontmatter
- Overlapping path patterns in rules files
- Suboptimal timeout values
- MCP scope conflicts (same server name at multiple scopes)
- MCP approval settings referencing non-existent servers
- Malformed ${VAR} expansion syntax in MCP configs
- Missing command examples
- Incomplete agent descriptions

**Suggestion (Consider)** - Improvements:
- Redundant instructions
- Style inconsistencies
- Missing optional sections
- Naming convention violations

#### Generate Fix Details

For each issue, generate:
```
Fix #N: [Title]
- Severity: CRITICAL/WARNING/SUGGESTION
- Location: [file:line]
- Issue: [What's wrong]
- Fix: [Specific action - create file, edit line, remove section, etc.]
- Automatable: Yes/No
- Diff (if applicable):
  - [old content]
  + [new content]
```

### Phase 6: Interactive Fix Session

**If --non-interactive is set**: Skip to Phase 7

**If --fix is set**: Apply fixes automatically with progress:
```
Applying fixes...
Fix 1/N: [Title]... done
Fix 2/N: [Title]... done
...
Applied: X fixes
Skipped: Y (require manual intervention)
```

**Otherwise (interactive mode)**:

Present fixes in waves by severity:

```
=== Wave 1: Critical Fixes (N issues) ===

These issues may cause failures and should be fixed:

Fix 1/N: [Title]
  File: [path]
  Issue: [description]

  Suggested fix:
  - [old]
  + [new]

  Apply? [Y/n/skip-all]

[Continue for each critical fix]

---

=== Wave 2: Warning Fixes (N issues) ===

These issues may cause unexpected behavior:

[Similar format]

Apply all warning fixes? [Y/n/select]

---

=== Wave 3: Suggestions (N issues) ===

These are optional improvements:

[Similar format]

Apply suggestions? [Y/n/select]
```

### Phase 7: Generate Final Report

When generating the final audit report, read the template format from [report-template.md](report-template.md) and populate it with the findings from all waves.

---

## Exit Codes (for --non-interactive)

| Code | Meaning |
|------|---------|
| 0 | Healthy - no critical or warning issues |
| 1 | Warnings - issues found but not critical |
| 2 | Critical - critical issues require attention |

---

## Examples

```bash
# Full interactive audit
/ll:audit-claude-config

# Audit with auto-fix
/ll:audit-claude-config --fix

# Non-interactive for CI
/ll:audit-claude-config --non-interactive

# Audit specific scope
/ll:audit-claude-config project
/ll:audit-claude-config hooks
/ll:audit-claude-config agents

# Audit scope with auto-fix
/ll:audit-claude-config commands --fix

# Full audit, non-interactive
/ll:audit-claude-config all --non-interactive
```

## Related Commands

- `/ll:init` - Initialize project configuration
- `/ll:help` - List all available commands
- `/ll:audit-architecture` - Analyze code architecture
- `/ll:audit-docs` - Audit documentation
