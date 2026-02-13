---
description: |
  Analyze active issues to discover cross-issue dependencies based on file overlap, validate existing dependency references, and propose new relationships. Use this skill when you want to find missing dependencies between issues, check for broken dependency refs, or prepare for sprint planning.

  Trigger keywords: "map dependencies", "dependency mapping", "find dependencies", "dependency analysis", "issue dependencies", "cross-issue dependencies", "blocked by analysis", "discover dependencies"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(ll-deps:*, git:*)
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

## How to Use

Run the `ll-deps` CLI command based on user needs:

### Full Analysis

For comprehensive dependency analysis (file overlaps + validation):
```bash
ll-deps analyze
```

### With Dependency Graph

Include an ASCII dependency graph visualization:
```bash
ll-deps analyze --graph
```

### JSON Output

For programmatic access:
```bash
ll-deps analyze --format json
```

### Sprint-Scoped Analysis

Restrict analysis to only issues in a named sprint:
```bash
ll-deps analyze --sprint my-sprint
ll-deps analyze --sprint my-sprint --graph
ll-deps validate --sprint my-sprint
```

### Validation Only

Check existing dependency references for broken refs, cycles, and missing backlinks:
```bash
ll-deps validate
```

### Custom Issues Directory

If issues are not in the default `.issues` directory:
```bash
ll-deps -d path/to/issues analyze
```

## Examples

| User Says | Action |
|-----------|--------|
| "Find missing dependencies" | `ll-deps analyze` |
| "Check dependency references" | `ll-deps validate` |
| "Show dependency graph" | `ll-deps analyze --graph` |
| "Are there broken dependency links?" | `ll-deps validate` |
| "Prepare for sprint planning" | `ll-deps analyze --graph` |
| "Analyze deps for my sprint" | `ll-deps analyze --sprint <name>` |
| "Validate sprint dependencies" | `ll-deps validate --sprint <name>` |
| "Which issues conflict?" | `ll-deps analyze` |

## Interpreting Results

### Proposed Dependencies

The analysis identifies issue pairs that reference overlapping files and computes a semantic conflict score:

- **HIGH conflict (>= 0.7)**: Issues modify the same component/section — strong dependency
- **MEDIUM conflict (>= 0.4)**: Issues share files with moderate semantic overlap
- **Confidence**: Based on file overlap ratio (higher = more overlapping files)

Direction is determined by:
1. Priority: Higher priority issue blocks lower
2. Modification type: Structural blocks infrastructure blocks enhancement
3. Fallback: ID ordering with reduced confidence

### Parallel-Safe Pairs

Pairs with conflict score < 0.4 are reported as safe to run in parallel. These touch the same files but different sections/components.

### Validation Issues

- **Broken references**: `## Blocked By` entries referencing nonexistent issues
- **Missing backlinks**: A blocked by B, but B doesn't list A in Blocks
- **Cycles**: Circular dependency chains
- **Stale references**: Dependencies on already-completed issues

## Applying Proposals

After reviewing the analysis output, if you want to apply proposed dependencies:

1. Use AskUserQuestion to confirm which proposals to apply:
   - "Apply all" — write all proposed dependencies
   - "Select individually" — choose per proposal
   - "Skip all" — don't write changes

2. For each approved proposal, use the `apply_proposals()` function from `dependency_mapper.py` via Python, or manually:
   - Add target ID to source issue's `## Blocked By` section
   - Add source ID to target issue's `## Blocks` section

3. Stage changes:
```bash
git add {{config.issues.base_dir}}/
```

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Completed issues directory (default: `completed`)
- `sprints.sprints_dir` - Sprint definitions directory (default: `.sprints`)

## Integration

After running dependency mapping:

- Review changes with `git diff`
- Commit with `/ll:commit`
- Use `/ll:create_sprint` for dependency-aware sprint planning
- Run `ll-sprint show [name]` to see execution wave structure
- Use `/ll:verify_issues` to validate dependency integrity

## Best Practices

### Good Dependencies

- Based on **file overlap + semantic conflict** — issues modifying the same component/section should be sequenced
- **Priority ordering** — higher priority issues block lower priority ones
- **Modification type ordering** — structural changes block infrastructure, which blocks enhancements (at same priority)
- Dependencies represent real sequencing needs, not just related topics

### Parallel-Safe Pairs

- Issues touching the **same file but different sections** (e.g., header vs body) are identified as parallel-safe
- The conflict score threshold is 0.4 — pairs below this are not proposed as dependencies
- Review parallel-safe pairs to confirm the tool's assessment is correct for your context

### Avoid

- Creating dependencies between unrelated issues just because they have similar titles
- Circular dependencies (the tool will warn about these)
- Over-connecting — not every pair of related issues needs a dependency edge
- Overriding parallel-safe assessments without good reason — false-positive dependencies reduce sprint throughput
