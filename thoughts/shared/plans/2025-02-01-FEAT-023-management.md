# FEAT-023: Product Scanning Integration - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-023-product-scanning-integration.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `commands/scan_codebase.md` (lines 1-348): Complete reference for command structure, patterns for parallel agent spawning, progress tracking with TodoWrite, metadata gathering, and reporting format
- `skills/product-analyzer/SKILL.md` (lines 1-276): Fully implemented skill with comprehensive analysis framework, YAML output structure, and guardrails
- `config-schema.json` (lines 500-546): Product configuration schema with `product.enabled`, `product.goals_file`, `product.analyze_user_impact`, `product.analyze_business_value`
- Highest issue number is 191 (ENH-191), so next new issue would be 192

### Existing Patterns to Follow

**Command Structure** (from `scan_codebase.md`):
- YAML frontmatter with `description` and `allowed-tools`
- Configuration section showing template variable usage
- Process phases with numbered steps
- Progress tracking using TodoWrite
- Git metadata gathering with Bash commands
- Parallel agent spawning with Task tool
- Synthesis and deduplication phase
- User confirmation before file creation (section 4.5)
- Structured report output

**Skill Integration**:
- Use `Skill` tool with `skill="product-analyzer"`
- Pass prompt with analysis instructions
- Skill returns YAML structured findings
- Skill has built-in guardrails for disabled product and missing goals

**Issue File Format** (from `scan_codebase.md` lines 188-246):
- YAML frontmatter with git metadata
- Title, Summary, Location sections
- Proposed Solution for features
- Impact assessment (Severity/Effort/Risk)
- Labels and Status sections

## Desired End State

A new `commands/scan_product.md` file that:
1. Validates product analysis is enabled and goals file exists
2. Loads product context from goals file
3. Invokes product-analyzer skill
4. Processes findings into FEAT/ENH issues with product context
5. Creates issue files in appropriate directories
6. Outputs a structured scan report

### How to Verify
- Command file exists at `commands/scan_product.md`
- Command gracefully handles `product.enabled: false`
- Command gracefully handles missing goals file
- Command follows same structure as `scan_codebase.md`
- Command integrates with `product-analyzer` skill via Skill tool

## What We're NOT Doing

- Not modifying `commands/scan_codebase.md` - remains unchanged per issue specification
- Not modifying the `product-analyzer` skill - already implemented
- Not modifying config schema - product configuration already exists from FEAT-020
- Not creating test cases - out of scope for this issue
- Not creating documentation updates - command is self-documenting

## Problem Analysis

**Root Issue**: No product-focused scanning capability exists. Users must manually analyze codebase against product goals.

**Solution**: Create dedicated `/ll:scan-product` command that:
1. Is the product counterpart to `/ll:scan-codebase`
2. Maintains clean separation between technical and product workflows
3. Is opt-in via `product.enabled` configuration
4. Leverages the existing `product-analyzer` skill

## Solution Approach

Create a single new command file following the established pattern from `scan_codebase.md`, but:
- Replaces the 3 parallel technical agents with 1 call to the `product-analyzer` skill
- Uses product-specific frontmatter fields in created issues
- Outputs goal-alignment summary instead of technical categories

## Implementation Phases

### Phase 1: Create Command File Structure

#### Overview
Create the `commands/scan_product.md` file with YAML frontmatter, configuration section, and initial process structure.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Create new file with command structure

```markdown
---
description: Scan codebase for product-focused issues based on goals document
allowed-tools:
  - Bash(git:*, gh:*)
---

# Scan Product

You are tasked with scanning the codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities, then creating issue files for tracking.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Focus directories**: `{{config.scan.focus_dirs}}`
- **Exclude patterns**: `{{config.scan.exclude_patterns}}`
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Product enabled**: `{{config.product.enabled}}`
- **Goals file**: `{{config.product.goals_file}}`
- **Analyze user impact**: `{{config.product.analyze_user_impact}}`
- **Analyze business value**: `{{config.product.analyze_business_value}}`

## Process

[... continue with process steps ...]
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/scan_product.md`
- [ ] File is valid markdown with YAML frontmatter

**Manual Verification**:
- [ ] Command structure follows `scan_codebase.md` pattern
- [ ] Configuration section correctly references product config keys

---

### Phase 2: Implement Prerequisites Validation

#### Overview
Add validation logic for product analysis prerequisites before proceeding with scan.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 1 with validation logic

```markdown
### 1. Validate Prerequisites

Before scanning, verify product analysis is properly configured:

1. **Check product analysis is enabled**:
   - Read `.claude/ll-config.json`
   - Verify `product.enabled` is `true`
   - If false, inform user and exit:
     ```markdown
     Product analysis is not enabled.

     To enable product scanning, add to your `.claude/ll-config.json`:
     ```json
     {
       "product": {
         "enabled": true
       }
     }
     ```

     See FEAT-020 for more information.
     ```

2. **Check goals file exists**:
   - Get goals file path from `product.goals_file` (default: `.claude/ll-goals.md`)
   - Verify file exists using `ls` or `test -f`
   - If missing, inform user and exit:
     ```markdown
     Product goals file not found: {{config.product.goals_file}}

     To use product scanning, create a goals document with your product vision,
     personas, and strategic priorities.

     See FEAT-021 for more information.
     ```

If either check fails, stop execution. Do not proceed with scanning.
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Validation logic correctly references config keys
- [ ] Error messages are clear and actionable
- [ ] Both checks stop execution appropriately

---

### Phase 3: Implement Product Context Loading

#### Overview
Add logic to load and parse the goals file for product context.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 2 for loading product context

```markdown
### 2. Load Product Context

Read and parse the goals file to provide context for analysis:

1. **Read the goals file**:
   ```bash
   # Read goals file
   cat {{config.product.goals_file}}
   ```

2. **Extract key information**:
   - Persona definition (id, name, role)
   - Strategic priorities (id, name)
   - Full markdown content for skill context

3. **Store for later use**:
   - PERSONA_NAME: Primary persona name
   - PRIORITIES_COUNT: Number of strategic priorities
   - GOALS_CONTENT: Full markdown for passing to skill
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Step correctly references goals file from config
- [ ] Extraction logic covers persona, priorities, and full content

---

### Phase 4: Implement Metadata Gathering

#### Overview
Add git and repository metadata collection for traceability.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 3 for metadata gathering

```markdown
### 3. Gather Metadata

Collect git and repository information for traceability:

```bash
# Git metadata
git rev-parse HEAD                    # Current commit hash
git branch --show-current             # Current branch name
date -u +"%Y-%m-%dT%H:%M:%SZ"         # ISO timestamp

# Repository info for permalinks
gh repo view --json owner,name        # Get owner and repo name

# Check if permalinks are possible (on main or pushed)
git status                            # Check if ahead of remote
```

Store these values for use in issue files:
- COMMIT_HASH: Current commit
- BRANCH_NAME: Current branch
- SCAN_DATE: ISO 8601 timestamp
- REPO_OWNER: GitHub owner
- REPO_NAME: Repository name
- PERMALINKS_AVAILABLE: true if on main/master or commit is pushed
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Commands match pattern from `scan_codebase.md`
- [ ] All required metadata fields are captured

---

### Phase 5: Implement Product Analysis via Skill

#### Overview
Invoke the product-analyzer skill with appropriate prompt.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 4 for skill invocation

```markdown
### 4. Run Product Analysis

Invoke the product-analyzer skill to perform comprehensive product analysis:

```
Use Skill tool with skill="product-analyzer"

Prompt: Perform comprehensive product analysis of this codebase.

## Goals Document

{{GOALS_CONTENT}}

## Analysis Scope

Please analyze:

1. **Strategic Alignment Audit**
   - Score each strategic priority: Implemented | Partial | Missing
   - Identify code supporting each priority
   - Flag priorities with no supporting code

2. **User Journey Mapping**
   - For the primary persona, trace their workflows
   - Identify friction points and missing steps
   - Suggest improvements from user perspective

3. **Opportunity Identification**
   - Quick wins (small effort, high value)
   - Missing features (gaps vs. goals)
   - Underexposed capabilities

## Output Requirements

Return structured findings following your output format with:
- Each finding linked to goal/persona
- Issue type (FEAT or ENH) for each finding
- Business value and effort estimates
- Deduplication against existing .issues/
- File:line evidence for every finding
```

Wait for the skill to complete and capture its YAML output.
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Skill invocation uses correct skill name
- [ ] Prompt includes goals content
- [ ] Prompt specifies analysis scope
- [ ] Prompt specifies output requirements

---

### Phase 6: Implement Findings Processing

#### Overview
Process skill findings to assign issue numbers and priorities.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 5 for processing findings

```markdown
### 5. Process Findings

After the product-analyzer skill completes:

1. **Parse skill output**:
   - Extract findings from YAML structure
   - Count findings by type (feature_gap, ux_improvement, business_value)
   - Identify any skipped issues and reasons

2. **Deduplicate against existing issues**:
   - The skill performs initial deduplication
   - Review `duplicate_of` field in findings
   - Remove findings marked as duplicates

3. **Assign priorities** based on product-aware criteria:
   ```
   For product-scan issues, priority considers:
   1. Business Value (primary) - High/Medium/Low
   2. Goal Alignment (primary) - How central to strategic priorities
   3. Effort (secondary, inverse) - Prefer quick wins
   4. Persona Impact (secondary) - How much it helps target user

   Mapping:
   - High value + core goal alignment → P1-P2
   - Medium value or partial alignment → P2-P3
   - Low value or tangential → P3-P4
   ```

4. **Assign globally unique sequential numbers**:
   - Scan ALL `.issues/` subdirectories INCLUDING `{{config.issues.base_dir}}/completed/`
   - Find the highest existing number across ALL issue types (BUG, FEAT, ENH)
   - Use `global_max + 1` for each new issue regardless of type
   - Example: If BUG-191 exists, next issue is 192 (e.g., FEAT-192 or ENH-192)
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Priority mapping matches issue specification
- [ ] Issue number assignment logic matches `scan_codebase.md` pattern
- [ ] Deduplication handles skill's `duplicate_of` field

---

### Phase 7: Implement Issue File Creation

#### Overview
Define issue file format with product-specific frontmatter.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 6 for issue creation

```markdown
### 6. Create Issue Files

For each finding, create an issue file with product-specific frontmatter:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_product
goal_alignment: [priority-id]
persona_impact: [persona-id]
business_value: [high|medium|low]
---

# [FEAT|ENH]-[NUMBER]: [Title]

## Summary

[Description of the product-focused finding]

## Product Context

### Goal Alignment
- **Strategic Priority**: [Which priority this supports]
- **Alignment**: [How this advances the goal]

### User Impact
- **Persona**: [Primary persona affected]
- **User Need**: [What problem this solves]
- **Expected Benefit**: [How users benefit]

### Business Value
- **Value Score**: [High | Medium | Low]
- **Rationale**: [Why this value assessment]

## Evidence

[File:line references showing the gap or opportunity]
- **File**: `path/to/file.ext`
- **Line(s)**: [line numbers]
- **Permalink**: [View on GitHub](...)
- **Code**:
```[language]
// Relevant code snippet
```

## Proposed Approach

[High-level implementation direction]

## Impact

- **Business Value**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Labels

`product-scan`, `[goal-id]`, `[persona-id]`

---

## Status

**Open** | Created: [DATE] | Priority: P[X]
```

**Note**: Only include Permalink if `PERMALINKS_AVAILABLE` is true.
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Issue format matches issue specification
- [ ] Product context fields are included
- [ ] Labels include product-scan identifier

---

### Phase 8: Implement Confirmation Step

#### Overview
Add user confirmation before creating issue files.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 6.5 for confirmation

```markdown
### 6.5. Confirm Issue Creation

Before creating any files, present a summary to the user:

```markdown
## Product Scan: Issues to Create

### Scan Context
- **Goals File**: {{config.product.goals_file}}
- **Persona**: [PERSONA_NAME]
- **Priorities Analyzed**: [PRIORITIES_COUNT]

### Findings Summary

| Priority | Type | Title | Business Value | Effort |
|----------|------|-------|----------------|--------|
| P2 | FEAT | [Title] | High | Medium |
| P3 | ENH | [Title] | Medium | Small |

### Strategic Alignment Summary

| Priority | Alignment | Issues Created |
|----------|-----------|----------------|
| [Priority 1] | Partial | 2 |
| [Priority 2] | Strong | 0 |

Total: [N] issues to create
```

Ask: "Create these [N] issue files? (y/n)"

Only proceed to save files if user confirms.
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Confirmation prompt includes scan context
- [ ] Confirmation prompt includes findings summary
- [ ] Confirmation prompt includes strategic alignment summary
- [ ] Command waits for user input

---

### Phase 9: Implement File Saving

#### Overview
Add logic to save issue files to appropriate directories.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 7 for file saving

```markdown
### 7. Save Issue Files

After user confirmation:

```bash
# Create each issue file
for each finding in findings:
    cat > "{{config.issues.base_dir}}/[category]/P[X]-[PREFIX]-[NUM]-[slug].md" << 'EOF'
[Issue content]
EOF

# Stage new issues
git add "{{config.issues.base_dir}}/"
```

Issues are created in:
- `{{config.issues.base_dir}}/features/` for FEAT issues
- `{{config.issues.base_dir}}/enhancements/` for ENH issues
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] File saving uses correct directories
- [ ] Files are staged with git add

---

### Phase 10: Implement Report Output

#### Overview
Add final scan report with goal alignment summary.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Process Step 8 for report output

```markdown
### 8. Output Report

Generate a comprehensive product scan report:

```markdown
# Product Scan Report

## Scan Context
- **Commit**: [COMMIT_HASH]
- **Branch**: [BRANCH_NAME]
- **Date**: [SCAN_DATE]
- **Repository**: [REPO_OWNER]/[REPO_NAME]
- **Goals File**: {{config.product.goals_file}}
- **Persona**: [PERSONA_NAME]
- **Priorities Analyzed**: [PRIORITIES_COUNT]

## Summary
- **Findings**: [N]
  - Features: [N]
  - Enhancements: [N]
- **Duplicates skipped**: [N]
- **Issues created**: [N]

## Strategic Alignment Summary

| Priority | Alignment | Issues Created |
|----------|-----------|----------------|
| [Priority 1] | [Strong|Partial|Weak|Missing] | [N] |
| [Priority 2] | [Strong|Partial|Weak|Missing] | [N] |

## New Issues Created

### Features ({{config.issues.base_dir}}/features/)
| File | Priority | Business Value | Goal Alignment | Permalink |
|------|----------|----------------|----------------|-----------|
| P2-FEAT-001-... | P2 | High | [Priority] | [Link](...) |

### Enhancements ({{config.issues.base_dir}}/enhancements/)
| File | Priority | Business Value | Goal Alignment | Permalink |
|------|----------|----------------|----------------|-----------|
| P3-ENH-001-... | P3 | Medium | [Priority] | [Link](...) |

## Skipped Findings

| Title | Reason |
|-------|--------|
| [Title] | [duplicate_of_xxx|insufficient_evidence|out_of_scope] |

## Next Steps
1. Review created issues for accuracy
2. Adjust priorities based on business context
3. Run `/ll:manage-issue` to start processing
```
```

#### Success Criteria

**Automated Verification**:
- [ ] YAML frontmatter is valid
- [ ] Markdown syntax is correct

**Manual Verification**:
- [ ] Report includes scan context
- [ ] Report includes strategic alignment summary
- [ ] Report includes findings by type
- [ ] Report includes skipped findings
- [ ] Report includes next steps

---

### Phase 11: Add Examples and Integration Sections

#### Overview
Add usage examples and integration guidance.

#### Changes Required

**File**: `commands/scan_product.md`
**Changes**: Add Examples and Integration sections

```markdown
---

## Examples

```bash
# Scan codebase for product issues
/ll:scan-product

# Review created issues
ls {{config.issues.base_dir}}/*/

# Start processing issues
/ll:manage-issue feature implement
```

---

## Integration

After scanning:
1. Review created issues for accuracy
2. Adjust priorities based on business context
3. Use `/ll:manage-issue` to process issues
4. Commit new issues: `/ll:commit`

## Workflow Separation

Product and technical workflows remain cleanly separated:

```
Technical Workflow (all users):
  /ll:scan-codebase → BUG/FEAT/ENH issues → /ll:manage-issue

Product Workflow (product-enabled users):
  /ll:scan-product → FEAT/ENH issues with product context → /ll:manage-issue
```

Both workflows feed into the same issue management commands, but discovery is separate.
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown
- [ ] YAML frontmatter is valid

**Manual Verification**:
- [ ] Examples show realistic usage
- [ ] Integration section provides next steps
- [ ] Workflow separation diagram is clear

---

## Testing Strategy

### Manual Testing
- Test with `product.enabled: false` - should show helpful error
- Test with missing goals file - should show helpful error
- Test with valid config - should complete scan
- Verify issue files are created in correct directories
- Verify issue files contain product context frontmatter

### Integration Testing
- Verify `/ll:scan-codebase` still works unchanged
- Verify `product-analyzer` skill is invoked correctly
- Verify findings are processed into issues

## References

- Original issue: `.issues/features/P2-FEAT-023-product-scanning-integration.md`
- Command pattern: `commands/scan_codebase.md:1-348`
- Product skill: `skills/product-analyzer/SKILL.md:1-276`
- Config schema: `config-schema.json:500-546`
