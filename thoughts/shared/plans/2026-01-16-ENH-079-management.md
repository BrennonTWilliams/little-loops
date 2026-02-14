# ENH-079: Commands Audit Recommendations - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-079-commands-audit-recommendations.md
- **Type**: enhancement
- **Priority**: P3 (Low-Medium)
- **Action**: improve

## Current State Analysis

### Key Discoveries
- `commands/commit.md:38` - Contains typo "PATTERMS_LIST" should be "PATTERNS_LIST"
- `commands/describe_pr.md` - Missing `$ARGUMENTS` block in body (has Integration section at lines 120-126)
- `commands/verify_issues.md` - Missing Arguments section (has Integration section at lines 133-139)
- `commands/check_code.md:161` - Documents default in body ("optional, default: `all`") - good pattern
- `commands/run_tests.md:139` - Documents default in body ("optional, default: `all`") - good pattern
- `commands/toggle_autoprompt.md:5` - Documents default in frontmatter description only
- `commands/toggle_autoprompt.md:152-157` - Already HAS Integration section (issue item #11 incorrect)
- `commands/help.md` - Missing Integration section
- `commands/commit.md` - Missing Integration section

### Patterns to Follow
- Arguments section pattern from `commands/run_tests.md:135-146`:
  ```markdown
  ## Arguments

  $ARGUMENTS

  - **scope** (optional, default: `all`): Description
    - `option1` - Description
    - `option2` - Description
  ```
- Integration section pattern from `commands/verify_issues.md:133-139`:
  ```markdown
  ## Integration

  Works well with:
  - `/ll:command_name` - Brief description
  ```

## Desired End State

1. Fix typo in commit.md
2. Add Arguments section to describe_pr.md with optional `base_branch` argument
3. Add Arguments section to verify_issues.md with optional `issue_id` and `--verbose` parameters
4. Add Integration sections to commit.md and help.md
5. Verify toggle_autoprompt.md already has Integration section (no action needed)

### How to Verify
- Grep for "PATTERMS" should return no results
- All modified files should have proper markdown structure
- Integration sections should follow consistent pattern

## What We're NOT Doing

- Not adding --dry-run flags (item #4) - Medium effort, defer to separate issue
- Not documenting exit codes (item #5) - Medium effort, defer to separate issue
- Not adding --verbose flag (item #9) - Medium effort, defer to separate issue
- Not implementing dynamic help generation (item #8) - Large effort, defer
- Not adding command aliases (item #10) - Medium effort, defer
- Not standardizing example counts (item #12) - Low value, commands have appropriate examples for their complexity
- Not changing argument frontmatter schema (item #3) - Current body documentation pattern is clear and consistent

## Problem Analysis

The commands were written at different times with inconsistent patterns. The audit identified several small fixes and pattern standardizations that can improve consistency without major refactoring.

## Solution Approach

Focus on quick fixes that provide immediate value:
1. Fix the typo (high impact, minimal effort)
2. Add missing Arguments sections (enables better discoverability)
3. Add missing Integration sections (improves workflow guidance)

## Implementation Phases

### Phase 1: Fix Typo in commit.md

#### Overview
Fix the "PATTERMS_LIST" typo at line 38.

#### Changes Required

**File**: `commands/commit.md`
**Changes**: Line 38 - change "PATTERMS_LIST" to "PATTERNS_LIST"

```diff
-                description: "Add {PATTERN_COUNT} pattern(s) to .gitignore: {PATTERMS_LIST}"
+                description: "Add {PATTERN_COUNT} pattern(s) to .gitignore: {PATTERNS_LIST}"
```

#### Success Criteria

**Automated Verification**:
- [ ] No "PATTERMS" typo: `grep -r "PATTERMS" commands/` (should return nothing)

---

### Phase 2: Add Arguments Section to describe_pr.md

#### Overview
Add `$ARGUMENTS` section with optional `base_branch` argument.

#### Changes Required

**File**: `commands/describe_pr.md`
**Changes**: Add frontmatter arguments and body Arguments section before Examples

```yaml
---
description: Generate comprehensive PR descriptions following repository templates
arguments:
  - name: base_branch
    description: Base branch for comparison (default: auto-detect from origin/HEAD)
    required: false
---
```

Add before Examples section (line ~107):
```markdown
---

## Arguments

$ARGUMENTS

- **base_branch** (optional, default: auto-detect): Base branch for PR comparison
  - If provided, uses specified branch as comparison target
  - If omitted, auto-detects from `refs/remotes/origin/HEAD` (usually `main` or `master`)

---
```

#### Success Criteria

**Automated Verification**:
- [ ] Has Arguments section: `grep -c "## Arguments" commands/describe_pr.md` (should be 1)
- [ ] Has $ARGUMENTS: `grep -c '\$ARGUMENTS' commands/describe_pr.md` (should be 1)

---

### Phase 3: Add Arguments Section to verify_issues.md

#### Overview
Add Arguments section with optional `issue_id` parameter (like `ready_issue` command).

#### Changes Required

**File**: `commands/verify_issues.md`
**Changes**:
1. Add frontmatter arguments
2. Add body Arguments section before Examples

Add to frontmatter:
```yaml
arguments:
  - name: issue_id
    description: Optional specific issue ID to verify
    required: false
```

Add before Examples section (around line 116):
```markdown
---

## Arguments

$ARGUMENTS

- **issue_id** (optional): Specific issue ID to verify
  - If provided, verifies only that specific issue
  - If omitted, verifies all open issues

---
```

#### Success Criteria

**Automated Verification**:
- [ ] Has Arguments section: `grep -c "## Arguments" commands/verify_issues.md` (should be 1)
- [ ] Has $ARGUMENTS: `grep -c '\$ARGUMENTS' commands/verify_issues.md` (should be 1)

---

### Phase 4: Add Integration Section to commit.md

#### Overview
Add Integration section following the established pattern.

#### Changes Required

**File**: `commands/commit.md`
**Changes**: Add Integration section at end of file

```markdown
---

## Integration

This command creates commits for work done in the current session.

Works well with:
- `/ll:check-code` - Run before committing to ensure code quality
- `/ll:run-tests` - Verify tests pass before committing
- `/ll:describe-pr` - After committing, generate PR description
```

#### Success Criteria

**Automated Verification**:
- [ ] Has Integration section: `grep -c "## Integration" commands/commit.md` (should be 1)

---

### Phase 5: Add Integration Section to help.md

#### Overview
Add Integration section to help.md.

#### Changes Required

**File**: `commands/help.md`
**Changes**: Add Integration section at end of file

```markdown
---

## Integration

This command is typically used when:
- Starting a new session to remember available commands
- Looking up command syntax and arguments
- Discovering workflow patterns

Related documentation:
- Plugin configuration: `.claude/ll-config.json`
- Issue tracking: `.issues/` directory
- Project documentation: `CONTRIBUTING.md`
```

#### Success Criteria

**Automated Verification**:
- [ ] Has Integration section: `grep -c "## Integration" commands/help.md` (should be 1)

---

## Testing Strategy

### Verification Commands
```bash
# Verify typo is fixed
grep -r "PATTERMS" commands/

# Verify Arguments sections added
grep -c "## Arguments" commands/describe_pr.md
grep -c "## Arguments" commands/verify_issues.md

# Verify Integration sections added
grep -c "## Integration" commands/commit.md
grep -c "## Integration" commands/help.md

# Verify markdown structure is valid (basic check)
for f in commands/commit.md commands/describe_pr.md commands/verify_issues.md commands/help.md; do
  echo "Checking $f..."
  grep -c "^#" "$f"
done
```

### Manual Verification
- Review each modified file for consistent formatting
- Verify no broken markdown structure

## References

- Original issue: `.issues/enhancements/P3-ENH-079-commands-audit-recommendations.md`
- Argument pattern: `commands/run_tests.md:135-146`
- Integration pattern: `commands/verify_issues.md:133-139`
