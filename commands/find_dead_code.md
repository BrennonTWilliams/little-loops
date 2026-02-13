---
description: Analyze codebase for deprecated, unused, or dead code that can be safely removed
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ruff:*)
---

# Find Dead Code

You are tasked with analyzing the codebase to identify deprecated, unused, or dead code that can be safely removed.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
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

1. Run `/ll:check_code` after removals
2. Run `/ll:run_tests all` to verify no regressions
3. Consider deprecation warnings before removing public APIs
```

### 5. Issue Creation (Optional)

After generating the report, offer to create enhancement issues for tracking dead code cleanup tasks.

#### Issue Type and Priority

All dead code findings create **ENH** (enhancement) issues:

| Finding Confidence | Priority | Rationale |
|-------------------|----------|-----------|
| High confidence (safe to remove) | P4 | Low-risk cleanup |
| Medium confidence (needs review) | P5 | Requires investigation |
| Low confidence | Skip | Manual verification first |

**Note**: Low confidence findings do NOT create issues automatically - they require human verification before tracking.

#### Grouping Strategy

Group related findings into single issues to avoid issue spam:

| Dead Code Type | Grouping Strategy | Example Title |
|----------------|-------------------|---------------|
| Unused imports (same file) | Per file | "Remove 5 unused imports from `module.py`" |
| Unused imports (same package) | Per package | "Clean up unused imports in `utils/` package" |
| Unused private functions | Per file | "Remove unused private functions in `helpers.py`" |
| Unused public functions | Individual | "Consider removing unused function `calculate_legacy()`" |
| Unreachable code | Individual | "Remove unreachable code after return in `parser.py:142`" |

#### Issue File Format

Created issues follow the standard format with audit metadata:

```markdown
---
discovered_commit: [GIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [ISO_TIMESTAMP]
discovered_by: find_dead_code
confidence: [high|medium]
---

# ENH-XXX: [Title based on grouping]

## Summary

Dead code cleanup task identified by `/ll:find_dead_code`.

## Location

- **File**: `path/to/file.py`
- **Line(s)**: 42-45

## Findings

| Item | Type | Confidence | Reason |
|------|------|------------|--------|
| `unused_import` | Import | High | Never referenced |
| `_old_helper()` | Function | High | Zero callers |

## Proposed Solution

Remove the identified dead code items.

## Verification

After removal:
1. Run `/ll:check_code all`
2. Run `/ll:run_tests`

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low (high confidence items)

## Labels

`enhancement`, `cleanup`, `dead-code`, `auto-generated`

---

## Status

**Open** | Created: [DATE] | Priority: P4
```

### 6. User Approval

Before creating issues, present a summary for user approval:

```markdown
## Proposed Issue Creation

Based on dead code analysis, the following ENH issues will be created:

### Issues to Create (N)

| Priority | Title | Findings | Files |
|----------|-------|----------|-------|
| P4 | Remove unused imports from `utils.py` | 5 imports | 1 |
| P4 | Remove unused function `_legacy_calc()` | 1 function | 1 |
| P5 | Review potentially unused `api_handler()` | 1 function | 1 |

### Skipped (Low Confidence)

The following findings require manual verification and will NOT create issues:
- `dynamic_loader()` in `plugins.py` - may be used via getattr
- `callback_handler()` in `events.py` - registered externally

---

**Create these enhancement issues?**
- [y] Create all listed issues
- [n] Skip issue creation, keep report only
- [s] Select specific issues to create
```

Wait for user confirmation before writing any issue files.

### 7. Create Issue Files

After user approval:

1. **Get next issue number** (globally unique across ALL types):
   ```bash
   ll-next-id
   ```

2. **Generate filenames** using the pattern: `P[4-5]-ENH-[NNN]-[slug].md`

3. **Write files** to `.issues/enhancements/`

4. **Stage for commit**:
   ```bash
   git add .issues/enhancements/
   ```

5. **Output summary**:
   ```
   Created N enhancement issues:
   - P4-ENH-015-remove-unused-imports-utils.md
   - P4-ENH-016-remove-unused-function-legacy-calc.md
   - P5-ENH-017-review-api-handler.md

   Run `/ll:commit` to commit these issues.
   ```

---

## Examples

```bash
# Find all dead code
/ll:find_dead_code

# After review, remove high-confidence items
# Then run verification:
/ll:check_code all
/ll:run_tests all
```

---

## Integration

After finding dead code:
1. Review the report carefully
2. **Create ENH issues** for tracking (optional, requires approval)
3. Start with high-confidence items
4. Run tests after each batch of removals
5. Consider deprecation for public APIs
6. Use `/ll:commit` to save changes

Works well with:
- `/ll:scan_codebase` - May find overlapping issues
- `/ll:check_code` - Verify code quality after removals
- `/ll:run_tests` - Ensure no regressions
