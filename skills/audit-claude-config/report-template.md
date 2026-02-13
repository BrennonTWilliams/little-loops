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

## Wave 2: Cross-Component Consistency

### Reference Validation

| Source | Target | Reference | Status |
|--------|--------|-----------|--------|
[Table rows]

### Conflicts Detected

| Location 1 | Location 2 | Conflict | Resolution |
|------------|------------|----------|------------|
[Table rows or "None detected"]

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
| Cross-config consistency | X/10 | [Brief note] |
| **Overall** | **X/10** | [Summary] |

## Next Steps

1. [Prioritized action items based on findings]
2. [...]
```

## Health Score Calculation

### Overall Health Score
Calculate as weighted average:
- Memory file structure: 20%
- Content quality: 20%
- Memory hierarchy coverage: 10%
- Rules files quality: 10%
- Plugin components: 15%
- Hooks config: 5%
- MCP config: 5%
- Cross-config consistency: 15%

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
