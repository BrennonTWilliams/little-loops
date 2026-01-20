---
description: Scan codebase to identify bugs, enhancements, and features, then create issue files
allowed-tools:
  - Bash(git:*, gh:*)
---

# Scan Codebase

You are tasked with scanning the codebase to identify potential bugs, enhancements, and feature opportunities, then creating issue files for tracking.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Focus directories**: `{{config.scan.focus_dirs}}`
- **Exclude patterns**: `{{config.scan.exclude_patterns}}`
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`

## Process

### 0. Initialize Progress Tracking

Create a todo list to track scan progress:

```
Use TodoWrite to create:
- Gathering git metadata and repo info
- Scanning for bugs (via sub-agent)
- Scanning for enhancements (via sub-agent)
- Scanning for features (via sub-agent)
- Synthesizing and deduplicating findings
- Creating issue files
- Generating summary report
```

Update todos as each phase completes to give the user visibility into progress.

### 1. Gather Metadata

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

### 2. Spawn Parallel Scan Agents

Launch 3 sub-agents in parallel to scan different categories concurrently:

**IMPORTANT**: Spawn all 3 agents in a SINGLE message with multiple Task tool calls.

#### Agent 1: Bug Scanner
```
Use Task tool with subagent_type="codebase-analyzer"

Prompt: Scan the codebase in {{config.scan.focus_dirs}} for potential bugs:
- TODO/FIXME/BUG/HACK comments
- Error handling gaps (bare except, swallowed exceptions)
- Type mismatches and potential runtime errors
- Resource leaks (unclosed files, connections)
- Race conditions or thread safety issues

Exclude: {{config.scan.exclude_patterns}}

Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Stable anchor (function name, class name, or unique nearby string that won't change)
- Code snippet showing the issue
- Severity assessment (High/Medium/Low)
- Brief explanation of the problem
- Reproduction steps (how to trigger the bug)

IMPORTANT: Do NOT include related issue IDs or their status in findings.
Related issues will be resolved dynamically during validation.

IMPORTANT: Before reporting each finding, VERIFY:
- File paths exist (use Read tool to confirm)
- Line numbers are accurate (check the actual file)
- Code snippets match current code
Only report VERIFIED issues with accurate references.
```

#### Agent 2: Enhancement Scanner
```
Use Task tool with subagent_type="codebase-analyzer"

Prompt: Scan the codebase in {{config.scan.focus_dirs}} for enhancement opportunities:
- Performance bottlenecks (N+1 queries, unnecessary loops)
- Code duplication that could be refactored
- Missing abstractions or patterns
- Outdated dependencies or deprecated APIs
- Test coverage gaps

Exclude: {{config.scan.exclude_patterns}}

Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Stable anchor (function name, class name, or unique nearby string that won't change)
- Code snippet showing the area
- Effort estimate (Small/Medium/Large)
- Current behavior (what the code does now)
- Expected behavior (what the code should do after improvement)
- Proposed solution (suggested approach to implement the enhancement)

IMPORTANT: Do NOT include related issue IDs or their status in findings.
Related issues will be resolved dynamically during validation.

IMPORTANT: Before reporting each finding, VERIFY:
- File paths exist (use Read tool to confirm)
- Line numbers are accurate (check the actual file)
- Any referenced functions/classes exist
Only report VERIFIED findings with accurate references.
```

#### Agent 3: Feature Scanner
```
Use Task tool with subagent_type="codebase-analyzer"

Prompt: Scan the codebase in {{config.scan.focus_dirs}} for feature opportunities:
- TODO comments describing new functionality
- Missing API endpoints or CLI commands
- Incomplete implementations
- User-facing improvements suggested in code

Exclude: {{config.scan.exclude_patterns}}

Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Stable anchor (function name, class name, or unique nearby string that won't change)
- Code snippet or context
- Scope estimate (Small/Medium/Large)
- Brief explanation of the feature

IMPORTANT: Do NOT include related issue IDs or their status in findings.
Related issues will be resolved dynamically during validation.

IMPORTANT: Before reporting each finding, VERIFY:
- File paths exist (use Read tool to confirm)
- Any TODOs or comments you reference are still present
- Line numbers are accurate
Only report VERIFIED findings.
```

### 3. Synthesize Findings

After ALL sub-agents complete:

1. **Collect results** from all 3 agents
2. **Deduplicate** against existing issues in `{{config.issues.base_dir}}/`
3. **Assign priorities** (P0-P5) based on:
   - P0: Critical bugs, security issues, data loss risk
   - P1: High-impact bugs, blocking issues
   - P2: Medium bugs, important enhancements
   - P3: Low-priority bugs, nice-to-have enhancements
   - P4: Minor improvements, code cleanup
   - P5: Future considerations, low-priority features
4. **Assign globally unique sequential numbers**:
   - Scan ALL `.issues/` subdirectories INCLUDING `{{config.issues.base_dir}}/completed/`
   - Find the highest existing number across ALL issue types (BUG, FEAT, ENH)
   - Use `global_max + 1` for each new issue regardless of type
   - Example: If BUG-003, FEAT-005, and ENH-010 exist, next issue is 011 (e.g., BUG-011 or FEAT-011)

### 4. Create Issue Files

For each finding, create an issue file with YAML frontmatter:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_codebase
---

# [PREFIX]-[NUMBER]: [Title]

## Summary

[Clear description of the issue]

## Location

- **File**: `path/to/file.py`
- **Line(s)**: 42-45 (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function process_issue()` or `in class IssueManager` or `near string "unique marker"`
- **Permalink**: [View on GitHub](https://github.com/[REPO_OWNER]/[REPO_NAME]/blob/[COMMIT_HASH]/path/to/file.py#L42-L45)
- **Code**:
```python
# Relevant code snippet
```

## Current Behavior

[What happens now]

## Expected Behavior

[What should happen]

## Reproduction Steps

[For bugs only - steps to reproduce the issue]
1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Proposed Solution

[Suggested approach to implement the enhancement or fix]

## Impact

- **Severity**: [High/Medium/Low]
- **Effort**: [Small/Medium/Large]
- **Risk**: [Low/Medium/High]

## Labels

`bug|enhancement|feature`, `priority-label`

---

## Status
**Open** | Created: [SCAN_DATE] | Priority: [P0-P5]
```

**Note**: Only include Permalink if `PERMALINKS_AVAILABLE` is true.

### 4.5. Confirm Issue Creation

Before creating any files, present a summary to the user:

```markdown
## Issues to Create

| Category | Count | Priority Range |
|----------|-------|----------------|
| Bugs | N | P0-P3 |
| Enhancements | N | P2-P4 |
| Features | N | P3-P5 |

[List each issue briefly: priority, type, title]
```

Ask: "Create these [N] issue files? (y/n)"

Only proceed to save files if user confirms.

### 5. Save Issue Files

```bash
# Create issue file with proper naming
cat > "{{config.issues.base_dir}}/[category]/P[X]-[PREFIX]-[NUM]-[slug].md" << 'EOF'
[Issue content]
EOF

# Stage new issues
git add "{{config.issues.base_dir}}/"
```

### 6. Output Report

```markdown
# Codebase Scan Report

## Scan Metadata
- **Commit**: [COMMIT_HASH]
- **Branch**: [BRANCH_NAME]
- **Date**: [SCAN_DATE]
- **Repository**: [REPO_OWNER]/[REPO_NAME]

## Summary
- **Files scanned**: X
- **Issues found**: Y
  - Bugs: N
  - Enhancements: N
  - Features: N
- **Duplicates skipped**: Z

## New Issues Created

### Bugs ({{config.issues.base_dir}}/bugs/)
| File | Priority | Title | Permalink |
|------|----------|-------|-----------|
| P1-BUG-001-... | P1 | Description | [Link](...) |

### Enhancements ({{config.issues.base_dir}}/enhancements/)
| File | Priority | Title | Permalink |
|------|----------|-------|-----------|
| P2-ENH-001-... | P2 | Description | [Link](...) |

### Features ({{config.issues.base_dir}}/features/)
| File | Priority | Title | Permalink |
|------|----------|-------|-----------|
| P3-FEAT-001-... | P3 | Description | [Link](...) |

## Next Steps
1. Review created issues for accuracy
2. Adjust priorities as needed
3. Run `/ll:manage_issue` to start processing
```

---

## Examples

```bash
# Scan codebase for issues
/ll:scan_codebase

# Review created issues
ls {{config.issues.base_dir}}/*/

# Start processing issues
/ll:manage_issue bug fix
```

---

## Integration

After scanning:
1. Review created issues for accuracy
2. Run `/ll:prioritize_issues` if needed
3. Use `/ll:manage_issue` to process issues
4. Commit new issues: `/ll:commit`
