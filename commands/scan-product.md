---
description: Scan codebase for product-focused issues based on goals document
allowed-tools:
  - Bash(git:*, gh:*)
  - Skill
  - TodoWrite
---

# Scan Product

You are tasked with scanning the codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities, then creating issue files for tracking.

This command is the product counterpart to `/ll:scan-codebase`.

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

### 0. Initialize Progress Tracking

Create a todo list to track scan progress:

```
Use TodoWrite to create:
- Validating product analysis prerequisites
- Loading product context from goals file
- Gathering git metadata and repo info
- Running product analysis (via product-analyzer skill)
- Processing and deduplicating findings
- Creating issue files
- Generating summary report
```

Update todos as each phase completes to give the user visibility into progress.

### 1. Validate Prerequisites

Before scanning, verify product analysis is properly configured:

1. **Check product analysis is enabled**:
   - Read `.claude/ll-config.json`
   - Verify `product.enabled` is `true`
   - If false or missing, inform user and exit:
     ```markdown
     ## Product Analysis Not Enabled

     Product scanning is currently disabled.

     To enable product scanning, add to your `.claude/ll-config.json`:

     ```json
     {
       "product": {
         "enabled": true
       }
     }
     ```

     For more information, see FEAT-020: Product Analysis Opt-In Configuration.
     ```

2. **Check goals file exists**:
   - Get goals file path from `product.goals_file` (default: `.claude/ll-goals.md`)
   - Verify file exists using `test -f` or `ls`
   - If missing, inform user and exit:
     ```markdown
     ## Product Goals File Not Found

     Goals file not found: {{config.product.goals_file}}

     To use product scanning, create a goals document with your product vision,
     personas, and strategic priorities.

     For more information, see FEAT-021: Goals/Vision Ingestion Mechanism.
     ```

If either check fails, stop execution. Do not proceed with scanning.

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
   - `PERSONA_NAME`: Primary persona name
   - `PRIORITIES_COUNT`: Number of strategic priorities
   - `GOALS_CONTENT`: Full markdown for passing to skill

### 3. Gather Metadata

Collect git and repository information for traceability and GitHub permalinks:

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
- `COMMIT_HASH`: Current commit
- `BRANCH_NAME`: Current branch
- `SCAN_DATE`: ISO 8601 timestamp
- `REPO_OWNER`: GitHub owner
- `REPO_NAME`: Repository name
- `PERMALINKS_AVAILABLE`: true if on main/master or commit is pushed

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

   For product-scan issues, priority considers:
   1. **Business Value** (primary) - High/Medium/Low
   2. **Goal Alignment** (primary) - How central to strategic priorities
   3. **Effort** (secondary, inverse) - Prefer quick wins
   4. **Persona Impact** (secondary) - How much it helps target user

   Mapping:
   - High value + core goal alignment → P1-P2
   - Medium value or partial alignment → P2-P3
   - Low value or tangential → P3-P4

4. **Assign globally unique sequential numbers**:
   - Run `ll-next-id` to get the next available issue number
   - Use that value for the first new issue, increment for subsequent issues
   - Example: If `ll-next-id` prints `192`, assign 192, 193, 194, etc.

### 6. Create Issue Files

For each finding, create an issue file with product-specific frontmatter:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan-product
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
- **Line(s)**: [line numbers] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()` or `in class ClassName` or `near string "unique marker"`
- **Permalink**: [View on GitHub](https://github.com/[REPO_OWNER]/[REPO_NAME]/blob/[COMMIT_HASH]/path/to/file.ext#L[LINES])
- **Code**:
```[language]
// Relevant code snippet or context
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

**Open** | Created: [SCAN_DATE] | Priority: P[X]
```

**Note**: Only include Permalink if `PERMALINKS_AVAILABLE` is true.

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

### 7. Save Issue Files

After user confirmation:

```bash
# Create each issue file
cat > "{{config.issues.base_dir}}/[category]/P[X]-[PREFIX]-[NUM]-[slug].md" << 'EOF'
[Issue content]
EOF

# Stage new issues
git add "{{config.issues.base_dir}}/"
```

Issues are created in:
- `{{config.issues.base_dir}}/features/` for FEAT issues
- `{{config.issues.base_dir}}/enhancements/` for ENH issues

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
| P2-FEAT-192-... | P2 | High | [Priority] | [Link](...) |

### Enhancements ({{config.issues.base_dir}}/enhancements/)
| File | Priority | Business Value | Goal Alignment | Permalink |
|------|----------|----------------|----------------|-----------|
| P3-ENH-193-... | P3 | Medium | [Priority] | [Link](...) |

## Skipped Findings

| Title | Reason |
|-------|--------|
| [Title] | [duplicate_of_xxx|insufficient_evidence|out_of_scope] |

## Next Steps
1. Review created issues for accuracy
2. Adjust priorities based on business context
3. Run `/ll:manage-issue` to start processing
```

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
