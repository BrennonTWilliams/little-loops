---
description: |
  Analyze active issues to discover cross-issue dependencies based on file overlap, validate existing dependency references, and propose new relationships. Use this skill when you want to find missing dependencies between issues, check for broken dependency refs, or prepare for sprint planning.

  Trigger keywords: "map dependencies", "dependency mapping", "find dependencies", "dependency analysis", "issue dependencies", "cross-issue dependencies", "blocked by analysis", "discover dependencies"
---

# Map Dependencies Skill

This skill performs cross-issue dependency analysis to discover missing relationships, validate existing references, and propose new `## Blocked By` / `## Blocks` entries.

## When to Activate

Proactively offer or invoke this skill when the user:

- Asks about issue dependencies or relationships
- Wants to find which issues overlap or conflict
- Is preparing for sprint planning and needs dependency context
- Asks to validate or check existing dependency references
- Mentions missing or broken dependency links
- Wants a dependency graph visualization

## Workflow

### Phase 1: Discovery

Scan all active issues to build the analysis dataset:

1. Use Glob to find all `.md` files in:
   - `{{config.issues.base_dir}}/bugs/`
   - `{{config.issues.base_dir}}/features/`
   - `{{config.issues.base_dir}}/enhancements/`
2. Read each issue file to extract full content
3. Parse issue metadata (ID, type, priority, title, blocked_by, blocks)
4. Identify completed issue IDs from `{{config.issues.base_dir}}/completed/`

**Optional filtering**: If `--sprint [name]` is specified, load the sprint YAML and only analyze issues in that sprint.

### Phase 2: Analysis

Perform three types of analysis:

#### 2a. File Overlap Detection

For each pair of issues:
1. Extract file paths from issue content (Location sections, inline backtick references)
2. Compute the intersection of file paths between each pair
3. If overlapping files found:
   - Propose dependency: lower-priority issue `blocked_by` higher-priority issue
   - Calculate confidence score: `overlap_count / min(paths_a, paths_b)`
   - Skip pairs that already have a dependency relationship

#### 2b. Dependency Validation

Check integrity of existing dependency references:
1. **Broken references**: `## Blocked By` entries referencing nonexistent issue IDs
2. **Missing backlinks**: If A's `## Blocked By` lists B, but B's `## Blocks` doesn't list A
3. **Cycles**: Circular dependency chains (A → B → C → A)
4. **Stale references**: `## Blocked By` entries referencing completed issues (dependency already satisfied)

#### 2c. Summary Statistics

Compute:
- Total issues analyzed
- Total existing dependency edges
- Number of proposed new dependencies
- Number of validation issues found

### Phase 3: Report

Present the analysis results:

```
================================================================================
DEPENDENCY ANALYSIS REPORT
================================================================================

## SUMMARY
- Issues analyzed: N
- Existing dependencies: M
- Proposed new dependencies: P
- Validation issues: V

## PROPOSED DEPENDENCIES

| # | Source (blocked) | Target (blocker) | Reason | Confidence | Files |
|---|-----------------|-----------------|--------|------------|-------|
| 1 | FEAT-020 | FEAT-001 | file_overlap | 80% | config.py |

## VALIDATION ISSUES

### Broken References
- FEAT-042: references nonexistent BUG-999

### Missing Backlinks
- FEAT-002 blocked by FEAT-001, but FEAT-001 doesn't list FEAT-002 in Blocks

### Dependency Cycles
- FEAT-003 → ENH-010 → FEAT-003

### Stale References (completed blockers)
- BUG-015: blocked by FEAT-001 (completed)

## DEPENDENCY GRAPH

[Mermaid diagram showing existing + proposed dependencies]

================================================================================
```

### Phase 4: User Confirmation

For proposed dependencies, use AskUserQuestion:

```yaml
questions:
  - question: "Apply proposed dependencies? Review the proposals above and select an option."
    header: "Dependencies"
    multiSelect: false
    options:
      - label: "Apply all (Recommended)"
        description: "Write all proposed dependencies to issue files"
      - label: "Select individually"
        description: "Choose which proposals to apply one by one"
      - label: "Skip all"
        description: "Don't write any changes to issue files"
```

If "Select individually" is chosen, present each proposal separately:

```yaml
questions:
  - question: "Add dependency: [SOURCE] blocked by [TARGET]? (Reason: [rationale])"
    header: "[SOURCE]"
    multiSelect: false
    options:
      - label: "Yes, apply"
        description: "Add to ## Blocked By / ## Blocks sections"
      - label: "No, skip"
        description: "Don't add this dependency"
```

### Phase 5: Execution

For each approved proposal:

1. Add target ID to source issue's `## Blocked By` section
2. Add source ID to target issue's `## Blocks` section
3. If section doesn't exist, create it (before `## Labels` or `## Status`, or at end)
4. If entry already exists, skip (no duplicates)

After all changes:

```bash
git add {{config.issues.base_dir}}/
```

Show summary:

```
## CHANGES APPLIED
- Modified: [list of changed files]
- Proposals applied: X of Y
- Validation issues reported: Z (manual fix recommended)

## NEXT STEPS
- Review modified issue files
- Commit changes with /ll:commit
- Address validation issues (broken refs, missing backlinks)
```

## Output Format

```
================================================================================
DEPENDENCY MAPPING COMPLETE
================================================================================

## SUMMARY
- Issues analyzed: N
- Proposals applied: X
- Proposals skipped: Y
- Validation issues: Z

## CHANGES
- [file1.md] [MODIFIED] - Added FEAT-001 to Blocked By
- [file2.md] [MODIFIED] - Added FEAT-002 to Blocks

## GIT STATUS
- All changes staged in {{config.issues.base_dir}}/

================================================================================
```

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Completed issues directory (default: `completed`)

## Integration

After running dependency mapping:

- Review changes with `git diff`
- Commit with `/ll:commit`
- Use `/ll:create_sprint` for dependency-aware sprint planning
- Run `ll-sprint show [name]` to see execution wave structure
- Use `/ll:verify_issues` to validate dependency integrity

## Best Practices

### Good Dependencies

- Based on **file overlap** — issues touching the same code should be sequenced
- **Priority ordering** — higher priority issues block lower priority ones
- Dependencies represent real sequencing needs, not just related topics

### Avoid

- Creating dependencies between unrelated issues just because they have similar titles
- Circular dependencies (the tool will warn about these)
- Over-connecting — not every pair of related issues needs a dependency edge
