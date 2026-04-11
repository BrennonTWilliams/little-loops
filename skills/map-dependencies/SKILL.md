---
description: |
  Use when the user wants to find dependencies between issues, check for broken dependency refs, discover cross-issue file overlaps, or prepare dependency-aware sprint plans.

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

## Arguments

$ARGUMENTS

Parse arguments for flags:

```bash
AUTO_MODE=false
CHECK_MODE=false

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]; then AUTO_MODE=true; fi

# Explicit flags
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
```

- **flags** (optional):
  - `--auto` - Non-interactive mode: apply all HIGH-confidence dependency proposals (≥0.7 conflict score) without prompting. Skip MEDIUM-confidence proposals.
  - `--check` — Check-only mode for FSM loop evaluators. Run dependency analysis without applying changes, print `[ID] deps: N unmapped dependencies` per issue with unmapped deps, exit 1 if any unmapped, exit 0 if all mapped. Implies `--auto`.

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
| "Map deps non-interactively" | `/ll:map-dependencies --auto` |
| "Check if all deps are mapped" | `/ll:map-dependencies --check` |

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

After reviewing the analysis output, apply proposed dependencies using `ll-deps apply`:

```bash
ll-deps apply                           # Apply all proposals >= 0.7 confidence
ll-deps apply --min-confidence 0.5      # Lower threshold
ll-deps apply --dry-run                 # Preview without writing
ll-deps apply --sprint my-sprint        # Sprint-scoped apply
ll-deps apply FEAT-001 blocks FEAT-002  # Manual explicit pair
```

`ll-deps apply` writes only the `## Blocked By` direction. Run `ll-deps fix` afterward to add missing `## Blocks` backlinks, then `ll-deps validate` to confirm a clean state.

### Auto Mode Behavior

**When `AUTO_MODE` is true**: Skip the AskUserQuestion prompt below. Run `ll-deps apply` automatically (default threshold 0.7). Emit one status line per applied proposal: `[SOURCE-ID] → [TARGET-ID]: dependency added (confidence: HIGH)`

### Check Mode Behavior (--check)

**When `CHECK_MODE` is true**: Run dependency analysis without applying any changes. For each issue with unmapped dependencies (HIGH-confidence proposals not yet in `## Blocked By`), print `[ID] deps: N unmapped dependencies`. After all issues analyzed, if any had unmapped deps: print `N issues with unmapped dependencies`, then `exit 1`. If all mapped: print `All dependencies mapped`, then `exit 0`. This integrates with FSM `evaluate: type: exit_code` routing.

### Interactive Mode (default)

1. Use AskUserQuestion to confirm which proposals to apply:
   - "Apply all" — run `ll-deps apply`
   - "Select individually" — run `ll-deps apply <source> blocks <target>` per pair
   - "Skip all" — don't write changes

2. After applying, fix backlinks and validate:
```bash
ll-deps fix
ll-deps validate
```

3. Stage changes:
```bash
git add {{config.issues.base_dir}}/
```

## Configuration

Uses project configuration from `.ll/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Completed issues directory (default: `completed`)
- `sprints.sprints_dir` - Sprint definitions directory (default: `.sprints`)

## Integration

After running dependency mapping:

- Review changes with `git diff`
- Commit with `/ll:commit`
- Use `/ll:create-sprint` for dependency-aware sprint planning
- Run `ll-sprint show [name]` to see execution wave structure
- Use `/ll:verify-issues` to validate dependency integrity

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
