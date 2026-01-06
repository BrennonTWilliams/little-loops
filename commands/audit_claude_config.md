---
description: Audit CLAUDE.md and related Claude Code configuration files for consistency and best practices
arguments:
  - name: scope
    description: Audit scope (all|global|project|hooks|mcp)
    required: false
---

# Audit Claude Configuration

You are tasked with auditing CLAUDE.md files and related Claude Code configuration for consistency, best practices, and potential issues.

## Configuration Files to Audit

### CLAUDE.md Files (Priority Order)
1. **Global**: `~/.claude/CLAUDE.md` - User's private global instructions
2. **Project**: `./.claude/CLAUDE.md` - Project-specific instructions
3. **Root**: `./CLAUDE.md` - Alternative project location

### Related Configuration
- **Settings**: `~/.claude/settings.json` - Claude Code settings
- **Local Settings**: `./.claude/settings.local.json` - Project overrides
- **Plugin Config**: `./.claude/ll-config.json` - Little-loops plugin config
- **Hooks**: `hooks/hooks.json` or `.claude/hooks.json` - Event hooks
- **MCP Config**: `.mcp.json` or `~/.claude/.mcp.json` - MCP servers

## Audit Scopes

- **all**: Complete audit of all configuration (default)
- **global**: Focus on global ~/.claude/ configurations
- **project**: Focus on project .claude/ configurations
- **hooks**: Audit hooks configuration only
- **mcp**: Audit MCP server configuration only

## Process

### 1. Discover Configuration Files

```bash
SCOPE="${scope:-all}"

echo "=== CLAUDE.md Files ==="
# Global
ls -la ~/.claude/CLAUDE.md 2>/dev/null || echo "No global CLAUDE.md"

# Project (both locations)
ls -la .claude/CLAUDE.md 2>/dev/null || echo "No project .claude/CLAUDE.md"
ls -la CLAUDE.md 2>/dev/null || echo "No root CLAUDE.md"

echo "=== Related Config ==="
ls -la ~/.claude/settings.json 2>/dev/null
ls -la .claude/settings.local.json 2>/dev/null
ls -la .claude/ll-config.json 2>/dev/null
ls -la .mcp.json 2>/dev/null
ls -la hooks/hooks.json 2>/dev/null
```

### 2. Analyze CLAUDE.md Content

For each CLAUDE.md file found, check:

#### Structure
- [ ] Clear section organization
- [ ] Appropriate use of headers
- [ ] Logical instruction grouping
- [ ] No conflicting directives between global/project

#### Content Quality
- [ ] Instructions are actionable and specific
- [ ] No vague or ambiguous directives
- [ ] No contradictory rules
- [ ] References to files/paths exist

#### Best Practices
- [ ] Uses @ imports appropriately for modular config
- [ ] Does not duplicate default Claude behavior
- [ ] Project-specific overrides are clearly marked
- [ ] Sensitive information not exposed

#### Performance
- [ ] File not excessively large (>50KB warning)
- [ ] No redundant instructions
- [ ] Efficient token usage in directives

### 3. Analyze Hooks Configuration

Check hooks for:
- [ ] Valid JSON syntax
- [ ] Recognized event types (PreToolUse, PostToolUse, Stop, etc.)
- [ ] Executable scripts exist
- [ ] No dangerous patterns (arbitrary code execution)
- [ ] Timeout values are reasonable

### 4. Analyze MCP Configuration

Check MCP config for:
- [ ] Valid JSON syntax
- [ ] Server commands exist and are executable
- [ ] Environment variables properly referenced
- [ ] No duplicate server names
- [ ] Appropriate scope (global vs project)

### 5. Cross-Configuration Consistency

Check for:
- [ ] Global vs project conflicts
- [ ] Hook behavior aligns with CLAUDE.md rules
- [ ] MCP tools referenced in instructions exist
- [ ] Plugin config compatible with CLAUDE.md directives

### 6. Output Report

```markdown
# Claude Configuration Audit Report

## Summary
- **Files audited**: X
- **Issues found**: Y
  - Critical: N
  - Warning: N
  - Info: N

## Configuration Overview

### CLAUDE.md Files

| Location | Size | Sections | Status |
|----------|------|----------|--------|
| ~/.claude/CLAUDE.md | 12KB | 8 | WARN |
| .claude/CLAUDE.md | 3KB | 4 | OK |

### Related Configuration

| File | Status | Notes |
|------|--------|-------|
| settings.json | OK | Standard settings |
| hooks.json | WARN | 1 deprecated event |
| .mcp.json | OK | 3 servers configured |
| ll-config.json | OK | Valid config |

## CLAUDE.md Analysis

### Global (~/.claude/CLAUDE.md)

#### Structure Assessment
| Aspect | Status | Notes |
|--------|--------|-------|
| Organization | GOOD | Clear sections |
| Headers | OK | H1-H3 used consistently |
| Imports | WARN | 2 missing @files |

#### Content Issues
1. **[WARNING]** Line 45: Reference to `@DEPRECATED.md` file not found
2. **[INFO]** Line 72: Instruction duplicates default behavior
3. **[WARNING]** Line 100: Potential conflict with project config

### Project (.claude/CLAUDE.md)

[Similar breakdown]

## Cross-Config Issues

### Conflicts Detected
| Global Rule | Project Rule | Resolution |
|-------------|--------------|------------|
| "Never use emojis" | "Use emojis for status" | Project overrides - OK |
| "Always run tests" | [none] | Inherited - OK |

### Missing References
- `@MCP_Custom.md` referenced but not found
- Hook script `validate.sh` not executable

## Hooks Analysis

### Event Handlers

| Event | Hook | Status | Concern |
|-------|------|--------|---------|
| PreToolUse | validate-bash | OK | None |
| PostToolUse | log-activity | WARN | Slow timeout |
| Stop | cleanup | OK | None |

### Issues
1. **[WARNING]** `log-activity` has 30s timeout (recommend <5s)
2. **[INFO]** Consider adding UserPromptSubmit hook

## MCP Configuration

### Configured Servers

| Server | Command | Status |
|--------|---------|--------|
| context7 | npx ... | OK |
| sequential | node ... | OK |
| custom-api | python ... | WARN |

### Issues
1. **[WARNING]** `custom-api` server script not found at path

## Recommendations

### Critical (Must Fix)
1. Add missing @import file: `DEPRECATED.md`
2. Fix executable permissions on `validate.sh`

### Warnings (Should Fix)
3. Reduce `log-activity` hook timeout to 5s
4. Remove duplicate instruction at line 72
5. Verify `custom-api` MCP server path

### Suggestions (Consider)
6. Split large global CLAUDE.md into modular @imports
7. Add version comment for tracking changes
8. Document project-specific overrides

## Configuration Health Score

| Category | Score | Notes |
|----------|-------|-------|
| CLAUDE.md structure | 8/10 | Good organization |
| Content quality | 7/10 | Some redundancy |
| Hooks config | 9/10 | Well configured |
| MCP config | 7/10 | Path issues |
| Cross-config consistency | 6/10 | Minor conflicts |
| **Overall** | **7.4/10** | Good, minor fixes needed |
```

---

## Arguments

$ARGUMENTS

- **scope** (optional, default: `all`): What to audit
  - `all` - Complete configuration audit
  - `global` - Global ~/.claude/ only
  - `project` - Project .claude/ only
  - `hooks` - Hooks configuration only
  - `mcp` - MCP configuration only

---

## Examples

```bash
# Full configuration audit
/ll:audit_claude_config

# Audit global config only
/ll:audit_claude_config global

# Audit project config only
/ll:audit_claude_config project

# Audit hooks only
/ll:audit_claude_config hooks

# Audit MCP servers only
/ll:audit_claude_config mcp
```

---

## Integration

After auditing:
- Fix critical issues immediately
- Use findings to improve CLAUDE.md organization
- Sync global/project configs where appropriate
- Create backup before major changes

## Related Commands

- `/ll:init` - Initialize project configuration
- `/ll:help` - List all available commands
