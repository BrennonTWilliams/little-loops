---
description: Analyze codebase for deprecated, unused, or dead code that can be safely removed
---

# Find Dead Code

You are tasked with analyzing the codebase to identify deprecated, unused, or dead code that can be safely removed.

## Configuration

This command uses project configuration from `.claude/cl-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Focus directories**: `{{config.scan.focus_dirs}}`
- **Exclude patterns**: `{{config.scan.exclude_patterns}}`

## Process

### 1. Initial Scan

Analyze the codebase for potential dead code in these categories:

#### Unused Imports
```bash
# Use ruff or similar to find unused imports
ruff check {{config.project.src_dir}} --select F401 --output-format text
```

#### Unused Variables
```bash
# Find unused local variables
ruff check {{config.project.src_dir}} --select F841 --output-format text
```

#### Unused Functions/Methods
Look for functions that are:
- Never called within the codebase
- Not exported via `__all__`
- Not used as callbacks or handlers
- Not part of a public API

#### Unreachable Code
Look for:
- Code after return/raise statements
- Conditions that are always True/False
- Deprecated branches guarded by version checks

### 2. Cross-Reference Analysis

For each potential dead code item:

1. **Search for usages** across the entire codebase
2. **Check for dynamic usage** (string-based imports, getattr, etc.)
3. **Verify not part of public API** (documented, exported, type stubs)
4. **Check for test coverage** (tests may be the only users)

### 3. Categorize Findings

Group findings by confidence level:

#### High Confidence (Safe to Remove)
- Unused imports with no side effects
- Unreachable code after return
- Variables assigned but never used
- Private functions with zero callers

#### Medium Confidence (Needs Review)
- Functions only called in tests
- Deprecated code with removal date passed
- Code guarded by feature flags that are always False

#### Low Confidence (Manual Verification Required)
- Potentially used via dynamic imports
- Callback handlers registered elsewhere
- API functions that may have external callers

### 4. Output Format

```markdown
# Dead Code Analysis Report

## Summary
- **Files scanned**: X
- **High confidence items**: Y
- **Medium confidence items**: Z
- **Low confidence items**: W

## High Confidence (Safe to Remove)

### Unused Imports

| File | Line | Import | Reason |
|------|------|--------|--------|
| path/to/file.py | 5 | `from x import y` | Never used |

### Unused Functions

| File | Line | Function | Reason |
|------|------|----------|--------|
| path/to/file.py | 42 | `_helper()` | Zero callers |

### Unreachable Code

| File | Lines | Description |
|------|-------|-------------|
| path/to/file.py | 100-105 | Code after return |

## Medium Confidence (Review Needed)

[Similar tables with additional context]

## Low Confidence (Manual Check)

[Similar tables with investigation notes]

## Recommended Actions

1. Run `/br:check_code` after removals
2. Run `/br:run_tests all` to verify no regressions
3. Consider deprecation warnings before removing public APIs
```

---

## Arguments

$ARGUMENTS

No arguments required. The command analyzes the entire codebase.

---

## Examples

```bash
# Find all dead code
/br:find_dead_code

# After review, remove high-confidence items
# Then run verification:
/br:check_code all
/br:run_tests all
```

---

## Integration

After finding dead code:
1. Review the report carefully
2. Start with high-confidence items
3. Run tests after each batch of removals
4. Consider deprecation for public APIs
5. Use `/br:commit` to save changes
