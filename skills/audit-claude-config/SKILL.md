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
    description: Audit scope (all|managed|user|project|hooks|mcp|agents|commands|skills)
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

### Configuration Files
- **Settings**: `~/.claude/settings.json` - Claude Code settings
- **Local Settings**: `./.claude/settings.local.json` - Project overrides
- **Plugin Config**: `./.claude/ll-config.json` - Little-loops plugin config
- **Config Schema**: `config-schema.json` - Configuration validation schema
- **MCP Config**: `.mcp.json` or `~/.claude/.mcp.json` - MCP servers

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
- Recognized event types (14 official types)
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
```

#### Task 3: Config Files Auditor
```
Use Task tool with subagent_type="codebase-locator"

Prompt:
Locate and audit all configuration files:

**Files to find and validate**:
- .claude/ll-config.json (validate against config-schema.json)
- .claude/settings.local.json
- .mcp.json or ~/.claude/.mcp.json
- config-schema.json (check for completeness)

For each config file:
1. Check exists/not exists
2. Validate JSON syntax
3. Check schema compliance (where applicable)
4. Verify path references exist
5. Check for reasonable values (timeouts, worker counts)

For MCP config specifically:
- Server commands exist and are executable
- No duplicate server names
- Environment variables properly referenced
- Appropriate scope (global vs project)

Return:
- Config file inventory with status
- JSON validation results
- Schema compliance issues
- Path reference validity
- List of all server names for Wave 2
- List of all referenced paths for Wave 2
```

### Phase 2: Collect Wave 1 Results

After all Wave 1 agents complete:

1. **Merge findings** from all 3 agents
2. **Compile reference lists** for Wave 2:
   - All subagent_type values found in commands
   - All prompt file paths found in hooks
   - All @import references found in CLAUDE.md
   - All command references (/ll:X) found
   - All MCP tool/server references found
   - All file paths mentioned in configs
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

Return:
- Reference validation table with status for each
- List of missing references (CRITICAL)
- List of broken references (WARNING)
- Rules validation results (frontmatter, paths, symlinks)
- Auto memory size warnings
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
1. **CLAUDE.md → MCP**: MCP tools mentioned exist in .mcp.json
2. **CLAUDE.md → Commands**: /ll:X references have matching commands/X.md
3. **Hooks → Scripts**: Bash scripts referenced are executable
4. **Config → Paths**: File paths in config files exist in filesystem
5. **Memory Hierarchy**: Check for conflicts between managed policy, user memory, and project memory
6. **Rules Path Overlap**: Detect overlapping path patterns across rules files
7. **Local vs Project**: Check for conflicts between CLAUDE.local.md and project CLAUDE.md

Return:
- External reference validation table
- Hierarchy conflicts detected with recommended resolution
- Rules path overlap warnings
- List of missing/broken external references
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

**Warning (Should Fix)** - May cause issues:
- Missing @import files
- Conflicting instructions between managed/user/project memory
- CLAUDE.local.md not in .gitignore
- Auto memory MEMORY.md exceeds 200 lines
- Broken symlinks in rules directories
- Invalid glob patterns in rules frontmatter
- Overlapping path patterns in rules files
- Suboptimal timeout values
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
/ll:audit_claude_config

# Audit with auto-fix
/ll:audit_claude_config --fix

# Non-interactive for CI
/ll:audit_claude_config --non-interactive

# Audit specific scope
/ll:audit_claude_config project
/ll:audit_claude_config hooks
/ll:audit_claude_config agents

# Audit scope with auto-fix
/ll:audit_claude_config commands --fix

# Full audit, non-interactive
/ll:audit_claude_config all --non-interactive
```

## Related Commands

- `/ll:init` - Initialize project configuration
- `/ll:help` - List all available commands
- `/ll:audit_architecture` - Analyze code architecture
- `/ll:audit_docs` - Audit documentation
