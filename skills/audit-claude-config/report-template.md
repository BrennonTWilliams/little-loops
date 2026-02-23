# Audit Report Template

This file contains the format and structure for the final audit report generated in Phase 7.

## Report Structure

```markdown
# Claude Configuration Audit Report

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Health | X/10 |
| Files Audited | N |
| Critical Issues | N |
| Warnings | N |
| Suggestions | N |
| Fixes Applied | N |
| Fixes Pending | N |

## Wave 1: Individual Component Audits

### Memory Files

#### Managed Policy
| Location | Exists | Size | Health | Issues |
|----------|--------|------|--------|--------|
| /Library/Application Support/ClaudeCode/CLAUDE.md (macOS) or /etc/claude-code/CLAUDE.md (Linux) | Yes/No | XKB | X/10 | N |

#### Project Memory
| Location | Exists | Size | Sections | Health | Issues |
|----------|--------|------|----------|--------|--------|
| .claude/CLAUDE.md | Yes/No | XKB | N | X/10 | N |
| ./CLAUDE.md | Yes/No | XKB | N | X/10 | N |
| ./CLAUDE.local.md | Yes/No | XKB | N | X/10 | N |

#### Project Rules
| File | Frontmatter | Paths Pattern | Symlink | Health |
|------|-------------|---------------|---------|--------|
[Table rows for each .claude/rules/*.md file]

#### User Memory
| Location | Exists | Size | Sections | Health | Issues |
|----------|--------|------|----------|--------|--------|
| ~/.claude/CLAUDE.md | Yes/No | XKB | N | X/10 | N |

#### User Rules
| File | Frontmatter | Paths Pattern | Health |
|------|-------------|---------------|--------|
[Table rows for each ~/.claude/rules/*.md file]

#### Auto Memory
| File | Lines | Topic Files | Health |
|------|-------|-------------|--------|
| MEMORY.md | N (warn if >200) | N files | X/10 |

> Note: Parent directory traversal is runtime-dependent, not audited statically.

#### Issues Found
[List issues with severity, file:line, description]

### Plugin Components

#### Agents (N files)
| File | Description | Tools | Model | Issues |
|------|-------------|-------|-------|--------|
[Table rows]

#### Skills (N files)
| File | Description | Structure | Issues |
|------|-------------|-----------|--------|
[Table rows]

#### Commands (N files)
| File | Frontmatter | Args | Examples | Issues |
|------|-------------|------|----------|--------|
[Table rows]

#### Hooks (N hooks)
| Event | Type | Timeout | Target | Status |
|-------|------|---------|--------|--------|
[Table rows]

### Config Files

| File | Exists | Valid | Schema | Issues |
|------|--------|-------|--------|--------|
[Table rows]

### Settings Hierarchy

#### Settings File Inventory
| Scope | File | Exists | Valid JSON | Keys Found | Issues |
|-------|------|--------|------------|------------|--------|
| Managed | /Library/Application Support/ClaudeCode/managed-settings.json (macOS) or /etc/claude-code/managed-settings.json (Linux) | Yes/No | Yes/No | [list] | N |
| User | ~/.claude/settings.json | Yes/No | Yes/No | [list] | N |
| Project | .claude/settings.json | Yes/No | Yes/No | [list] | N |
| Local | .claude/settings.local.json | Yes/No | Yes/No | [list] | N |
| Global | ~/.claude.json | Yes/No | Yes/No | N/A (syntax only) | N |

#### Settings Key Validation
| Key | Scope | Expected Type | Actual Type/Value | Status |
|-----|-------|---------------|-------------------|--------|
[Table rows for keys with validation issues: unknown keys, type mismatches, deprecated, managed-only in wrong scope]

#### Permission Rules
| Scope | Rule Type | Rule | Syntax Valid | Issues |
|-------|-----------|------|-------------|--------|
[Table rows for permission rules across all scopes, or "No permission rules defined"]

#### Scope Conflicts
| Key | Higher Scope | Higher Value | Lower Scope | Lower Value | Effective |
|-----|-------------|-------------|-------------|-------------|-----------|
[Table rows for same key at multiple scopes with different values, or "No scope conflicts detected"]

#### Deprecated Keys
| Key | Scope | Replacement | Status |
|-----|-------|-------------|--------|
[Table rows, or "No deprecated keys found"]

#### Managed-Only Keys in Non-Managed Files
| Key | Found In | Expected In | Status |
|-----|----------|-------------|--------|
[Table rows, or "No misplaced managed-only keys"]

### Output Styles

| File | Exists | Frontmatter | name | description | keep-coding-instructions | Issues |
|------|--------|-------------|------|-------------|--------------------------|--------|
[Table rows for .claude/output-styles/*.md and ~/.claude/output-styles/*.md, or "No output style files found"]

| Setting | Location | Value | Target File | Status |
|---------|----------|-------|-------------|--------|
| outputStyle | .claude/settings.local.json | [value or not set] | [resolved path or N/A] | OK/MISSING/NOT_SET |

### LSP Servers

| File | Exists | Valid JSON | Issues |
|------|--------|------------|--------|
| .lsp.json | Yes/No | Yes/No | N |

| Server | command | transport | extensionToLanguage | timeout | Status |
|--------|---------|-----------|---------------------|---------|--------|
[Table rows, or "No .lsp.json found"]

### Keybindings

| File | Exists | Valid JSON | $schema | Bindings | Issues |
|------|--------|------------|---------|----------|--------|
| ~/.claude/keybindings.json | Yes/No | Yes/No | Yes/No | N | N |

| Context | Bindings Count | Invalid Contexts |
|---------|---------------|-----------------|
[Table rows per context]

### .claudeignore

| File | Exists | Syntax Valid | Broad Patterns | Issues |
|------|--------|-------------|----------------|--------|
| .claudeignore | Yes/No | Yes/No | [list or none] | N |

| Setting | Location | Value | .claudeignore Exists | Alignment |
|---------|----------|-------|----------------------|-----------|
| respectGitignore | .claude/settings.local.json | [value or not set] | Yes/No | OK/WARNING |

### Plugin settings.json

| File | Exists | Valid JSON | Recognized Keys | Unrecognized Keys | Issues |
|------|--------|------------|-----------------|-------------------|--------|
| settings.json | Yes/No | Yes/No | [list] | [list or none] | N |

## Wave 2: Cross-Component Consistency

### Reference Validation

| Source | Target | Reference | Status |
|--------|--------|-----------|--------|
[Table rows]

### Conflicts Detected

| Location 1 | Location 2 | Conflict | Resolution |
|------------|------------|----------|------------|
[Table rows or "None detected"]

### Settings Scope Conflicts

| Key | Scopes | Values | Effective Value | Severity |
|-----|--------|--------|-----------------|----------|
[Table rows or "No settings scope conflicts detected"]

### Settings Permission Overlaps

| Pattern | Allow Scope | Deny Scope | Effective | Severity |
|---------|-------------|------------|-----------|----------|
[Table rows or "No permission rule overlaps detected"]

### Missing References

[List or "None"]

## Wave 3: Fix Suggestions

### Critical (Must Fix)
[Numbered list with details]

### Warnings (Should Fix)
[Numbered list with details]

### Suggestions (Consider)
[Numbered list with details]

## Fixes Applied

[List of fixes applied during this session, or "None"]

## Configuration Health Score

| Category | Score | Notes |
|----------|-------|-------|
| Memory file structure | X/10 | [Brief note] |
| Content quality | X/10 | [Brief note] |
| Memory hierarchy coverage | X/10 | [Are all locations checked] |
| Rules files quality | X/10 | [Frontmatter, paths, symlinks] |
| Plugin components | X/10 | [Brief note] |
| Hooks config | X/10 | [Brief note] |
| MCP config | X/10 | [Brief note] |
| Settings hierarchy | X/10 | [Key validation, scope conflicts, deprecated/managed-only keys, permission rules] |
| Cross-config consistency | X/10 | [Brief note] |
| Extended config surfaces | X/10 | [Output styles, LSP, keybindings, .claudeignore, plugin settings] |
| **Overall** | **X/10** | [Summary] |

## Next Steps

1. [Prioritized action items based on findings]
2. [...]
```

## Health Score Calculation

### Overall Health Score
Calculate as weighted average:
- Memory file structure: 16%
- Content quality: 16%
- Memory hierarchy coverage: 8%
- Rules files quality: 8%
- Plugin components: 14%
- Hooks config: 5%
- MCP config: 5%
- Settings hierarchy: 8% (key validation, scope conflicts, deprecated/managed-only keys, permission rules)
- Cross-config consistency: 13%
- Extended config surfaces: 7% (output styles, LSP, keybindings, .claudeignore, plugin settings)

### Individual Category Scores
Rate each category 1-10 based on:
- **10**: No issues, best practices followed
- **8-9**: Minor suggestions only
- **6-7**: Some warnings but no critical issues
- **4-5**: Multiple warnings or 1-2 critical issues
- **2-3**: Many warnings or several critical issues
- **1**: Severe problems, multiple critical issues

## Wave Output Formats

### Wave 1 Summary Format
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

### Wave 2 Summary Format
```
Wave 2 Consistency Checks Complete

Internal Consistency: X/10
External Consistency: X/10

Missing references: N
Broken references: N
Hierarchy conflicts: N
```

## Fix Suggestion Formats

### Fix Detail Format
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

### Interactive Fix Prompt Format
```
=== Wave [N]: [Category] Fixes (N issues) ===

[Description of severity level]

Fix N/Total: [Title]
  File: [path]
  Issue: [description]

  Suggested fix:
  - [old]
  + [new]

  Apply? [Y/n/skip-all]
```

### Auto-Fix Progress Format
```
Applying fixes...
Fix 1/N: [Title]... done
Fix 2/N: [Title]... done
...
Applied: X fixes
Skipped: Y (require manual intervention)
```
