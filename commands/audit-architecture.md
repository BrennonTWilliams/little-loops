---
description: Analyze codebase architecture for patterns, organization, and improvements
argument-hint: "[focus-area] [flags]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash(ruff:*, wc:*, git:*)
  - Task
arguments:
  - name: focus
    description: Focus area (large-files|integration|patterns|organization|all)
    required: false
  - name: flags
    description: "Optional flags: --deep (spawn sub-agents for thorough analysis)"
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

### 0. Parse Flags

```bash
FLAGS="${flags:-}"
DEEP_MODE=false

if [[ "$FLAGS" == *"--deep"* ]]; then DEEP_MODE=true; fi
```

**Flag behavior**:
- `--deep`: Spawn parallel sub-agents (codebase-analyzer, codebase-pattern-finder) for each focus area instead of direct sequential analysis. Produces more thorough findings at the cost of longer execution time. When `--deep` is set, use the Task tool to launch analysis agents in parallel for each applicable focus area.

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

**If `--deep` flag is set**: For each focus area, spawn a Task sub-agent (subagent_type `codebase-analyzer`) with a targeted analysis prompt. Launch applicable agents in parallel for faster results. Collect findings from all agents before generating the report.

#### Large Files
- Find files over 500 lines
- Identify multiple responsibilities
- Suggest split points
- **If `--deep`**: Analyze internal complexity (cyclomatic complexity, class count, function count per file)

#### Integration Points
- Map module dependencies
- Identify coupling patterns
- Find integration seams
- **If `--deep`**: Build full import graph, detect transitive dependencies, measure coupling metrics

#### Patterns
- Detect design patterns in use
- Identify anti-patterns
- Suggest pattern improvements
- **If `--deep`**: Compare pattern implementations against best practices, find inconsistent pattern usage across modules

#### Organization
- Assess module structure
- Check naming conventions
- Review package organization
- **If `--deep`**: Analyze file placement against common Python project layouts, check for misplaced utilities

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

### 4. Issue Management

After generating the report, offer to create, update, or reopen issues for architectural findings.

#### Finding-to-Issue Mapping

| Finding Type | Severity | Issue Type | Priority |
|--------------|----------|------------|----------|
| Large file (>1000 lines) | High | ENH | P2 |
| Large file (500-1000 lines) | Medium | ENH | P3 |
| Circular dependency (blocking import) | Critical | BUG | P1 |
| Circular dependency (design smell) | Medium | ENH | P2 |
| God class anti-pattern | High | ENH | P2 |
| Other anti-patterns | Medium | ENH | P3 |
| Missing abstraction layer | Medium | FEAT | P3 |
| Missing design pattern | Low | FEAT | P4 |
| Inconsistent naming | Low | ENH | P4 |
| Missing `__all__` exports | Low | ENH | P5 |

**Classification guide**:
- **BUG**: Architectural issue causing runtime errors or blocking development
- **ENH**: Refactoring opportunity to improve existing code structure
- **FEAT**: New abstractions, patterns, or architectural components needed

#### Deduplication

Before creating issues, search for existing issues:

1. **Search by file path**:
   ```bash
   # Find issues mentioning the same file
   grep -r "services.py" .issues/bugs/ .issues/enhancements/ .issues/features/
   ```

2. **Search completed issues** for potential reopen:
   ```bash
   # Check if this architectural issue was previously addressed
   grep -r "circular dependency\|god class\|large file" .issues/completed/
   ```

3. **Match scoring**:
   - Same file + same issue type = High confidence (0.8+)
   - Same file + different type = Medium confidence (0.5-0.8)
   - Similar pattern/description = Low confidence (<0.5)

#### Deduplication Actions

| Match Score | Location | Action |
|-------------|----------|--------|
| ≥0.8 | Active issue | **Skip** or **Update** with new context |
| ≥0.5 | Active issue | **Update** existing issue |
| ≥0.5 | Completed | **Reopen** if problem recurred |
| <0.5 | - | **Create** new issue |

#### Issue File Format

```markdown
---
discovered_commit: [GIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [ISO_TIMESTAMP]
discovered_by: audit-architecture
focus_area: [large-files|integration|patterns|organization]
---

# [BUG|ENH|FEAT]-XXX: [Title describing architectural issue]

## Summary

Architectural issue found by `/ll:audit-architecture`.

## Location

- **File**: `path/to/file.py`
- **Line(s)**: 1-850 (entire file)
- **Module**: `package.module`

## Finding

### Current State

[Description of the current architecture issue]

```python
# Code example showing the problem
```

### Impact

- **Development velocity**: [How this affects development]
- **Maintainability**: [How this affects code maintenance]
- **Risk**: [Potential for bugs or failures]

## Proposed Solution

[Recommended architectural change]

### Suggested Approach

1. [Step 1]
2. [Step 2]
3. [Step 3]

## Impact Assessment

- **Severity**: [Critical|High|Medium|Low]
- **Effort**: [Small|Medium|Large]
- **Risk**: [Low|Medium|High]
- **Breaking Change**: [Yes|No]

## Labels

`bug|enhancement|feature`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: [DATE] | Priority: P[0-5]
```

### 5. Reopen Logic

If a completed architectural issue matches a new finding:

1. **Verify recurrence**:
   - Same file and similar line count (for large files)
   - Same modules involved (for circular dependencies)
   - Same anti-pattern detected

2. **Check if regression or new occurrence**:
   - Compare with previous resolution
   - Check git history for when issue reappeared

3. **Reopen process**:
   ```bash
   git mv .issues/completed/P2-ENH-XXX-refactor-services.md .issues/enhancements/
   ```

4. **Append Reopened section**:
   ```markdown
   ---

   ## Reopened

   - **Date**: [TODAY]
   - **By**: audit-architecture
   - **Reason**: Architectural issue recurred

   ### New Findings

   Previous fix: Split services.py into 3 modules (2024-06-01)
   Current state: services.py has grown back to 920 lines

   ### Analysis

   The file has accumulated new functionality since the original split.
   Consider another round of refactoring or establishing size limits.
   ```

### 6. User Approval

Present comprehensive summary before making changes:

```markdown
## Proposed Issue Changes

Based on architecture audit findings:

### New Issues to Create

#### Bugs (N)

| Priority | Title | Location | Finding |
|----------|-------|----------|---------|
| P1 | Circular import blocks startup | auth <-> users | ImportError |

#### Enhancements (N)

| Priority | Title | Location | Finding |
|----------|-------|----------|---------|
| P2 | Refactor services.py (850 lines) | src/services.py | God class |
| P3 | Extract common base from handlers | src/handlers/ | Duplication |

#### Features (N)

| Priority | Title | Location | Finding |
|----------|-------|----------|---------|
| P3 | Add repository abstraction layer | src/data/ | Missing pattern |

### Existing Issues to Update (N)

| Issue | Type | Update Reason |
|-------|------|---------------|
| ENH-015 | Enhancement | Additional large file found |

### Completed Issues to Reopen (N)

| Issue | Type | Reopen Reason |
|-------|------|---------------|
| ENH-008 | Enhancement | services.py grew back to 920 lines |
| BUG-003 | Bug | Circular dependency returned |

---

```

Use the AskUserQuestion tool with single-select:
- Question: "Proceed with issue changes?"
- Options:
  - "Create all" - Create/update/reopen all listed issues
  - "Skip" - Keep report only, no issue changes
  - "Select items" - Choose specific items to process

Wait for user selection before modifying any files.

### 7. Execute Issue Changes

After approval:

1. **Create new BUG issues** in `.issues/bugs/`
2. **Create new ENH issues** in `.issues/enhancements/`
3. **Create new FEAT issues** in `.issues/features/`
4. **Update existing issues** by appending Architecture Audit Results section
5. **Reopen completed issues** by moving and appending Reopened section
6. **Stage changes**:
   ```bash
   git add .issues/
   ```
7. **Output summary**:
   ```
   Issue changes complete:
   - Created: 4 issues (1 BUG, 2 ENH, 1 FEAT)
   - Updated: 1 issue
   - Reopened: 2 issues

   Run `/ll:commit` to commit these changes.
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

- **flags** (optional): Modify audit behavior
  - `--deep` - Spawn sub-agents for thorough analysis with complexity metrics and cross-module checks

---

## Examples

```bash
# Full architecture audit
/ll:audit-architecture

# Focus on large files
/ll:audit-architecture large-files

# Analyze patterns
/ll:audit-architecture patterns

# Deep audit with sub-agent analysis
/ll:audit-architecture --deep

# Deep audit focused on integration points
/ll:audit-architecture integration --deep
```

---

## Integration

After auditing:
1. Review the architecture audit report
2. **Manage issues** (create BUG/ENH/FEAT, update existing, reopen completed) with user approval
3. Prioritize high-impact improvements (P0-P2 first)
4. Use findings to guide new development

Works well with:
- `/ll:scan-codebase` - May find related code issues
- `/ll:find-dead-code` - Remove dead code before refactoring
- `/ll:check-code` - Verify code quality after architectural changes
- `/ll:manage-issue` - Process created architectural issues
