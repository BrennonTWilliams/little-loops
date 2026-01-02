---
description: Analyze codebase architecture for patterns, organization, and improvements
arguments:
  - name: focus
    description: Focus area (large-files|integration|patterns|organization|all)
    required: false
---

# Audit Architecture

You are tasked with analyzing the codebase architecture to identify patterns, integration points, and potential improvements.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Focus directories**: `{{config.scan.focus_dirs}}`

## Focus Areas

- **large-files**: Find files that are too large and should be split
- **integration**: Analyze how modules integrate with each other
- **patterns**: Identify design patterns in use
- **organization**: Assess directory and file organization
- **all**: Complete architectural audit (default)

## Process

### 1. Gather Metrics

```bash
# File sizes
find {{config.project.src_dir}} -name "*.py" -exec wc -l {} \; | sort -n

# Directory structure
tree {{config.project.src_dir}} -d -L 3

# Import graph
# Analyze imports to understand dependencies
```

### 2. Analyze by Focus Area

#### Large Files
- Find files over 500 lines
- Identify multiple responsibilities
- Suggest split points

#### Integration Points
- Map module dependencies
- Identify coupling patterns
- Find integration seams

#### Patterns
- Detect design patterns in use
- Identify anti-patterns
- Suggest pattern improvements

#### Organization
- Assess module structure
- Check naming conventions
- Review package organization

### 3. Output Report

```markdown
# Architecture Audit Report

## Summary
- **Files analyzed**: X
- **Total lines**: Y
- **Modules**: Z
- **Patterns detected**: N

## Focus: {focus}

### Large Files (>500 lines)

| File | Lines | Concern | Recommendation |
|------|-------|---------|----------------|
| path/to/file.py | 850 | Multiple classes | Split by responsibility |

### Module Dependencies

```
module_a
  -> module_b
  -> module_c
     -> module_d

Circular: module_x <-> module_y
```

### Design Patterns Detected

| Pattern | Location | Quality |
|---------|----------|---------|
| Repository | data/repo.py | Well implemented |
| Factory | core/factory.py | Could use ABC |
| Singleton | config.py | Consider DI |

### Anti-Patterns Found

| Anti-Pattern | Location | Impact | Fix |
|--------------|----------|--------|-----|
| God class | services.py | High | Split responsibilities |
| Circular import | a <-> b | Medium | Extract common |

### Organization Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| Package structure | GOOD | Clear separation |
| Naming conventions | WARN | Inconsistent in tests/ |
| File placement | GOOD | Logical grouping |
| Init files | OK | Some missing __all__ |

## Recommendations

### High Priority
1. Split `services.py` (850 lines) into focused modules
2. Resolve circular dependency between a and b
3. Add __all__ exports to public packages

### Medium Priority
4. Consider dependency injection for singletons
5. Extract common base classes for patterns
6. Standardize test file naming

### Low Priority
7. Add type hints to legacy modules
8. Document architecture in README
9. Create architecture diagram
```

---

## Arguments

$ARGUMENTS

- **focus** (optional, default: `all`): Area to focus on
  - `large-files` - Find oversized files
  - `integration` - Analyze module coupling
  - `patterns` - Detect design patterns
  - `organization` - Assess structure
  - `all` - Complete audit

---

## Examples

```bash
# Full architecture audit
/ll:audit_architecture

# Focus on large files
/ll:audit_architecture large-files

# Analyze patterns
/ll:audit_architecture patterns
```

---

## Integration

After auditing:
- Create enhancement issues for major refactors
- Prioritize high-impact improvements
- Use findings to guide new development
