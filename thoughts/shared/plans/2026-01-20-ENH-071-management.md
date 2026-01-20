# ENH-071: capture_issue uses hardcoded values instead of config references - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-071-capture-issue-hardcoded-config-values.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `capture_issue.md` command uses hardcoded directory names (`bugs/`, `features/`, `enhancements/`, `completed/`) and a hardcoded prefix pattern (`BUG|FEAT|ENH`) instead of deriving these values from configuration.

### Key Discoveries

1. **Line 20**: `{{config.issues.categories}}` displays as `[object Object]` since it's an object, not a string
2. **Lines 137-139**: Hardcoded `ls` commands for each category directory
3. **Lines 157, 160**: Uses `completed/` instead of `{{config.issues.completed_dir}}`
4. **Line 258**: Uses `completed/` instead of `{{config.issues.completed_dir}}`
5. **Line 304**: Hardcoded grep pattern `(BUG|FEAT|ENH)-[0-9]+`
6. **Lines 310-312**: Hardcoded type-to-directory mapping documentation
7. **Lines 449-451**: Hardcoded type-to-directory comment

### Pattern to Follow (from ready_issue.md:54-66)

```bash
for dir in {{config.issues.base_dir}}/*/; do
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        # process directory
    fi
done
```

This pattern:
- Iterates all subdirectories dynamically
- Skips completed directory using config variable
- Does not hardcode category names

## Desired End State

- All references to `completed/` use `{{config.issues.completed_dir}}`
- Directory iteration uses glob pattern `{{config.issues.base_dir}}/*/` with completed skip
- Categories configuration display is either removed or formatted helpfully
- The command works with both default and custom category configurations

### How to Verify
- `ruff check scripts/` passes (no Python changes)
- Manual review shows consistent config variable usage
- No hardcoded `bugs/`, `features/`, `enhancements/`, or `completed/` remain (except in documentation examples)

## What We're NOT Doing

- Not dynamically deriving the prefix pattern from config (would require config to be evaluated at runtime, which these templates don't support)
- Not changing the fundamental behavior of the command
- Not modifying any Python code
- Not refactoring other commands - focusing only on capture_issue.md

## Problem Analysis

The `capture_issue.md` command was written with hardcoded values that work with the default configuration but would break if users customize their `issues.categories` or `issues.completed_dir` settings. The ready_issue.md command demonstrates the correct pattern using glob iteration and config variable references.

## Solution Approach

1. Replace `{{config.issues.categories}}` display with a note that categories are configurable
2. Replace hardcoded directory listing with glob iteration pattern
3. Replace all `completed/` references with `{{config.issues.completed_dir}}`
4. Update documentation to use config variable format consistently
5. Add a note about the prefix pattern being based on config defaults

## Implementation Phases

### Phase 1: Fix Configuration Section (Line 20)

#### Overview
Fix the categories display that renders as `[object Object]`

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Replace line 20's unusable categories display

**Before (line 20):**
```markdown
- **Categories**: `{{config.issues.categories}}`
```

**After:**
```markdown
- **Completed dir**: `{{config.issues.completed_dir}}`
```

This follows the pattern in manage_issue.md which lists base_dir, categories, and completed_dir but categories only as reference name, not the object itself.

#### Success Criteria

**Automated Verification**:
- [ ] File saves without syntax errors

**Manual Verification**:
- [ ] Configuration section is clear and useful

---

### Phase 2: Fix Phase 2 Duplicate Detection (Lines 133-160)

#### Overview
Replace hardcoded directory listing with dynamic glob pattern

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Lines 131-161 - Replace hardcoded ls commands with glob iteration

**Before (lines 131-140):**
```markdown
#### Search Active Issues

Search in `{{config.issues.base_dir}}/{bugs,features,enhancements}/`:

```bash
# List all active issues for analysis
ls -la {{config.issues.base_dir}}/bugs/*.md 2>/dev/null || true
ls -la {{config.issues.base_dir}}/features/*.md 2>/dev/null || true
ls -la {{config.issues.base_dir}}/enhancements/*.md 2>/dev/null || true
```
```

**After:**
```markdown
#### Search Active Issues

Search in all active category directories (excluding completed):

```bash
# List all active issues for analysis
for dir in {{config.issues.base_dir}}/*/; do
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        ls -la "$dir"*.md 2>/dev/null || true
    fi
done
```
```

**Before (lines 155-161):**
```markdown
#### Search Completed Issues

Search in `{{config.issues.base_dir}}/completed/`:

```bash
ls -la {{config.issues.base_dir}}/completed/*.md 2>/dev/null || true
```
```

**After:**
```markdown
#### Search Completed Issues

Search in `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/`:

```bash
ls -la {{config.issues.base_dir}}/{{config.issues.completed_dir}}/*.md 2>/dev/null || true
```
```

#### Success Criteria

**Automated Verification**:
- [ ] File saves without syntax errors

**Manual Verification**:
- [ ] Directory iteration pattern matches ready_issue.md style
- [ ] completed_dir variable is used consistently

---

### Phase 3: Fix Phase 3 References (Lines 258)

#### Overview
Fix completed directory reference in duplicate handling section

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Line 258 - Use config variable

**Before (line 258):**
```markdown
- **Path**: `{{config.issues.base_dir}}/completed/[filename].md`
```

**After:**
```markdown
- **Path**: `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[filename].md`
```

#### Success Criteria

**Automated Verification**:
- [ ] File saves without syntax errors

---

### Phase 4: Fix Phase 4 Issue Number Extraction (Line 304)

#### Overview
Add documentation note about prefix pattern while keeping the functional pattern

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Lines 299-307 - Add note about prefix pattern source

The grep pattern `(BUG|FEAT|ENH)-[0-9]+` cannot be dynamically derived from config in these templates. Add a note explaining this uses the default category prefixes.

**Before (lines 299-307):**
```markdown
1. **Get next globally unique issue number:**

   Scan ALL issue directories including completed to find highest existing number:
   ```bash
   # Find all issue files and extract numbers
   find {{config.issues.base_dir}} -name "*.md" -type f | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | grep -oE "[0-9]+" | sort -n | tail -1
   ```

   The next issue number is `max_found + 1`. Format as 3 digits (e.g., 071).
```

**After:**
```markdown
1. **Get next globally unique issue number:**

   Scan ALL issue directories including completed to find highest existing number:
   ```bash
   # Find all issue files and extract numbers
   # Note: Pattern uses default category prefixes (BUG, FEAT, ENH)
   find {{config.issues.base_dir}} -name "*.md" -type f | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | grep -oE "[0-9]+" | sort -n | tail -1
   ```

   The next issue number is `max_found + 1`. Format as 3 digits (e.g., 071).
```

#### Success Criteria

**Automated Verification**:
- [ ] File saves without syntax errors

---

### Phase 5: Fix Phase 4 Reopen Action (Lines 446-452)

#### Overview
Fix completed directory reference in reopen action

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Lines 446-452 - Use config variable for completed directory

**Before (lines 446-452):**
```markdown
1. **Move from completed/ to active category directory:**

```bash
# Determine target directory from issue type in filename
# BUG-XXX -> bugs/, FEAT-XXX -> features/, ENH-XXX -> enhancements/
git mv "{{config.issues.base_dir}}/completed/[filename]" "{{config.issues.base_dir}}/[category]/"
```
```

**After:**
```markdown
1. **Move from {{config.issues.completed_dir}}/ to active category directory:**

```bash
# Determine target directory from issue type in filename
# Note: Uses default category mapping (BUG->bugs, FEAT->features, ENH->enhancements)
git mv "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[filename]" "{{config.issues.base_dir}}/[category]/"
```
```

#### Success Criteria

**Automated Verification**:
- [ ] File saves without syntax errors

---

### Phase 6: Verify All Changes

#### Overview
Verify all hardcoded references have been addressed

#### Success Criteria

**Automated Verification**:
- [ ] `grep -n "completed/" commands/capture_issue.md` shows no unaddressed hardcoded completed/ paths
- [ ] `ruff check scripts/` passes (no Python changes to break)

**Manual Verification**:
- [ ] Review diff shows all expected changes
- [ ] Remaining hardcoded category names are only in documentation/examples that can't use variables

## Testing Strategy

### Unit Tests
- No Python changes, so no unit tests needed

### Integration Tests
- Manual review of the command file for consistency with other commands

## References

- Original issue: `.issues/enhancements/P3-ENH-071-capture-issue-hardcoded-config-values.md`
- Pattern reference: `commands/ready_issue.md:54-66` - directory iteration pattern
- Pattern reference: `commands/manage_issue.md:27-29` - config section format
