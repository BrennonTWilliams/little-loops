---
name: audit-claude-config
description: Use when asked to audit Claude Code config, validate plugin settings, or diagnose plugin issues.
disable-model-invocation: true
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
metadata:
  short-description: Use when asked to audit Claude Code config, validate plugin settings, or diagnos
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
- **Hooks**: `hooks/hooks.json` + `hooks/prompts/*.md` + `scripts/little_loops/hooks/` + `hooks/adapters/` - Lifecycle hooks (Python handlers in `scripts/little_loops/hooks/`, host adapters in `hooks/adapters/<host>/`, intent handlers contributed via `LLHookIntentExtension`)

### Settings Files (Hierarchy Order - highest precedence first)
1. **Managed settings**: `/Library/Application Support/ClaudeCode/managed-settings.json` (macOS) or `/etc/claude-code/managed-settings.json` (Linux)
2. **User settings**: `~/.claude/settings.json` - Personal settings across all projects
3. **Project settings**: `.claude/settings.json` - Team-shared project settings (committed to git)
4. **Local settings**: `.claude/settings.local.json` - Personal project overrides (gitignored)
5. **Global preferences**: `~/.claude.json` - Preferences, OAuth, user/local MCP configs

### Configuration Files
- **Plugin Config**: `./.ll/ll-config.json` - Little-loops plugin config
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

`subagent_type="codebase-analyzer"` — audits all memory files across the full
memory hierarchy (managed, project, user, local, auto memory, and rules
directories). Assesses structure, content quality, best practices, performance,
rules-frontmatter validity, and auto-memory size. Returns per-file quality
scores, severity-tagged issues with line numbers, and reference lists (@imports,
/ll:X commands, MCP tools, rules symlinks, rules path patterns) for Wave 2.

See [wave1-prompts.md](wave1-prompts.md#task-1-claudemd-auditor) for the full verbatim prompt.

#### Task 2: Plugin Components Auditor

`subagent_type="plugin-config-auditor"` — audits agents (`agents/*.md`), skills
(`skills/*.md`), commands (`commands/*.md`), and hooks (`hooks/hooks.json` +
`hooks/prompts/*.md` + `scripts/little_loops/hooks/prompts/*.md`). Checks description quality, frontmatter completeness,
tool appropriateness, JSON validity, recognized event/handler types, and timeout
defaults. Returns a per-component summary table, severity-tagged issues, quality
scores, and reference lists (subagent_type values, prompt file paths, /ll:X
references in skills) for Wave 2.

See [wave1-prompts.md](wave1-prompts.md#task-2-plugin-components-auditor) for the full verbatim prompt.

#### Task 3: Config Files Auditor

`subagent_type="codebase-locator"` — locates and audits all configuration and
settings files across every scope: `.ll/ll-config.json`, `config-schema.json`,
MCP configs (`.mcp.json`, `~/.claude.json` mcpServers, `managed-mcp.json`), the
full settings hierarchy (managed/user/project/local + `~/.claude.json` prefs),
output styles, LSP servers (`.lsp.json` + plugin.json lspServers), keybindings,
`.claudeignore`, and plugin root `settings.json`. Validates JSON syntax, schema
compliance, path references, MCP transport types and `${VAR}` expansion, and
checks every settings key against the recognized-key reference table (types,
deprecated keys, managed-only keys, permission-rule syntax). Returns config and
settings inventories, validation issues, MCP server inventory per scope, and the
full set of Wave 2 reference values (permission rules, inline hooks,
`plansDirectory`, `enabledPlugins`, `outputStyle`, `respectGitignore`,
`lspServers`, output style files, `.claudeignore` status).

See [wave1-prompts.md](wave1-prompts.md#task-3-config-files-auditor) for the full verbatim prompt, including the **Recognized settings keys** reference table (key types, deprecated keys, managed-only keys, and permission-rule syntax validation).

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

## Additional Resources

- [wave1-prompts.md](wave1-prompts.md) - Verbatim Wave-1 sub-agent prompt bodies (Tasks 1-3) and the recognized-settings-key reference table.
- [report-template.md](report-template.md) - Final audit report template populated in Phase 7.
