---
description: Scan codebase to identify bugs, enhancements, and features, then create issue files
---

# Scan Codebase

You are tasked with scanning the codebase to identify potential bugs, enhancements, and feature opportunities, then creating issue files for tracking.

## Configuration

This command uses project configuration from `.claude/cl-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Focus directories**: `{{config.scan.focus_dirs}}`
- **Exclude patterns**: `{{config.scan.exclude_patterns}}`
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`

## Process

### 1. Scan for Issues

Analyze the codebase looking for:

#### Bugs
- TODO/FIXME/BUG/HACK comments
- Error handling gaps (bare except, swallowed exceptions)
- Type mismatches and potential runtime errors
- Resource leaks (unclosed files, connections)
- Race conditions or thread safety issues

#### Enhancements
- Performance bottlenecks (N+1 queries, unnecessary loops)
- Code duplication that could be refactored
- Missing abstractions or patterns
- Outdated dependencies or deprecated APIs
- Test coverage gaps

#### Features
- TODO comments describing new functionality
- Missing API endpoints or CLI commands
- Incomplete implementations
- User-facing improvements suggested in code

### 2. Categorize Findings

For each finding, determine:
- **Type**: Bug, Enhancement, or Feature
- **Priority**: P0-P5 based on impact
- **Location**: File path and line numbers
- **Description**: Clear explanation of the issue

### 3. Create Issue Files

For each finding, create an issue file:

```markdown
# [PREFIX]-[NUMBER]: [Title]

## Summary

[Clear description of the issue]

## Location

- **File**: `path/to/file.py`
- **Line(s)**: 42-45
- **Code**:
```python
# Relevant code snippet
```

## Current Behavior

[What happens now]

## Expected Behavior

[What should happen]

## Proposed Fix

[Suggested approach]

## Impact

- **Severity**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Labels

`bug|enhancement|feature`, `priority-label`

---

## Status
**Open** | Created: [DATE] | Priority: [P0-P5]
```

### 4. Save Issue Files

```bash
# Create issue file with proper naming
cat > "{{config.issues.base_dir}}/[category]/P[X]-[PREFIX]-[NUM]-[slug].md" << 'EOF'
[Issue content]
EOF

# Stage new issues
git add "{{config.issues.base_dir}}/"
```

### 5. Output Report

```markdown
# Codebase Scan Report

## Summary
- **Files scanned**: X
- **Issues found**: Y
  - Bugs: N
  - Enhancements: N
  - Features: N

## New Issues Created

### Bugs ({{config.issues.base_dir}}/bugs/)
| File | Priority | Title |
|------|----------|-------|
| P1-BUG-001-... | P1 | Description |

### Enhancements ({{config.issues.base_dir}}/enhancements/)
| File | Priority | Title |
|------|----------|-------|
| P2-ENH-001-... | P2 | Description |

### Features ({{config.issues.base_dir}}/features/)
| File | Priority | Title |
|------|----------|-------|
| P3-FEAT-001-... | P3 | Description |

## Next Steps
1. Review created issues for accuracy
2. Adjust priorities as needed
3. Run `/br:manage_issue` to start processing
```

---

## Arguments

$ARGUMENTS

No arguments required. Scans the entire codebase.

---

## Examples

```bash
# Scan codebase for issues
/br:scan_codebase

# Review created issues
ls {{config.issues.base_dir}}/*/

# Start processing issues
/br:manage_issue bug fix
```

---

## Integration

After scanning:
1. Review created issues for accuracy
2. Run `/br:prioritize_issues` if needed
3. Use `/br:manage_issue` to process issues
4. Commit new issues: `/br:commit`
