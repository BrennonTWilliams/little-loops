---
description: |
  AI-guided sprint health check that analyzes a sprint's current state and suggests improvements - removing stale issues, adding related backlog issues, and identifying dependency or contention problems. Pairs with `ll-sprint edit` (mechanics) the way `/ll:create-sprint` pairs with `ll-sprint create` (intelligence).

  Trigger keywords: "review sprint", "sprint health", "sprint review", "check sprint", "sprint suggestions", "optimize sprint", "sprint health check", "is my sprint still good"
argument-hint: "[sprint-name]"
allowed-tools:
  - Read
  - Glob
  - Bash(ll-sprint:*)
arguments:
  - name: sprint_name
    description: Sprint name to review (e.g., "my-sprint"). If omitted, lists available sprints.
    required: false
---

# Review Sprint

This command analyzes a sprint definition and provides intelligent recommendations for improving it - identifying stale issues to remove, related backlog issues to add, dependency warnings to resolve, and wave structure optimizations.

## When to Activate

Proactively offer or invoke this command when the user:

- Asks to review or check a sprint's health
- Mentions a sprint may be outdated or stale
- Wants suggestions for improving a sprint before execution
- Is preparing for sprint execution and wants a pre-flight check
- Asks whether a sprint "still makes sense"
- Wants to know if any sprint issues are completed or missing

## Arguments

$ARGUMENTS

If arguments provided, parse as sprint name (e.g., `my-sprint`). If no arguments provided, list available sprints and ask which to review.

## How to Use

Invoke this command with a sprint name:

```
/ll:review-sprint my-sprint
```

If no sprint name is provided, list available sprints and ask which to review:

```bash
ll-sprint list
```

## Workflow

The command follows a 6-phase workflow:

### Phase 1: Load & Health Check

1. **Load the sprint** and capture its current state:
   ```bash
   ll-sprint show $SPRINT_NAME
   ```

2. **Read the sprint YAML** to extract the description/goal:
   - File: `{{config.sprints.sprints_dir}}/$SPRINT_NAME.yaml`
   - Extract: `name`, `description`, `issues` list, `created` date

3. **Parse the show output** to identify:
   - Invalid issue references (files not found)
   - Dependency cycles
   - Execution wave structure
   - File contention warnings
   - Dependency analysis warnings (missing deps, broken refs, stale completed refs)

4. **Check for completed issues** by scanning the completed directory:
   - Use Glob: `{{config.issues.base_dir}}/completed/*.md`
   - Match against sprint issue IDs
   - Any matches are candidates for removal

### Phase 2: Backlog Scan

Scan all active issues NOT currently in the sprint:

1. **Find all active issues** using Glob:
   - `{{config.issues.base_dir}}/bugs/*.md`
   - `{{config.issues.base_dir}}/features/*.md`
   - `{{config.issues.base_dir}}/enhancements/*.md`

2. **Filter out** issues already in the sprint

3. **For each backlog issue**, extract:
   - Priority (from filename prefix: P0-P5)
   - Type (from directory: bugs/features/enhancements)
   - ID (from filename)
   - Title (from first `# ` heading)

### Phase 3: Analysis

Analyze the sprint against its goal and the current backlog state:

#### 3a: Staleness Check
- How old is the sprint? (compare `created` date to today)
- How many issues are completed since creation?
- How many issue references are invalid (files moved/deleted)?

#### 3b: Goal Coherence
- Read the sprint `description` field
- For each sprint issue, check if its title/summary aligns with the sprint's stated goal
- Flag issues that seem misaligned (e.g., a "performance" sprint containing a documentation issue)

#### 3c: Priority Drift
- Compare current priorities of sprint issues against each other
- Flag if a P0/P1 issue exists in the backlog that relates to the sprint's theme but isn't included
- Flag if a sprint contains P4/P5 issues alongside P0/P1 issues (priority spread)

#### 3d: Backlog Opportunities
- Match backlog issue titles/types against the sprint description keywords
- Identify high-priority backlog issues that could replace low-priority sprint issues
- Limit suggestions to 3-5 most relevant additions

#### 3e: Wave Optimization
- Review the execution wave structure from `ll-sprint show` output
- Note any single-issue waves that could be parallelized with additions
- Note file contention warnings that could be resolved by reordering

### Phase 4: Recommendations

Generate categorized recommendations:

#### Category 1: Issues to Remove
- Completed issues (found in `completed/` directory)
- Invalid references (file not found)
- Issues misaligned with sprint goal (with explanation)
- Low-priority issues when higher-priority alternatives exist

#### Category 2: Issues to Add
- High-priority backlog issues matching sprint theme
- Issues that would fill single-issue waves for better parallelism
- Issues with dependencies on current sprint issues (should be sequenced together)

#### Category 3: Warnings
- Dependency cycles detected
- File contention between sprint issues
- Stale completed dependency references
- Missing dependency backlinks

### Phase 5: Interactive Approval

Present recommendations to the user in batches using AskUserQuestion.

#### 5a: Removal Recommendations (if any)

For completed/invalid issues (clear-cut removals):

```yaml
questions:
  - question: "These sprint issues are completed or invalid. Prune them?"
    header: "Prune"
    multiSelect: false
    options:
      - label: "Yes, prune all (Recommended)"
        description: "Remove N completed/invalid issues via ll-sprint edit --prune"
      - label: "Review individually"
        description: "I'll list each one for you to decide"
      - label: "Skip"
        description: "Keep all issues as-is"
```

For goal-misaligned or low-priority removals (judgment calls):

```yaml
questions:
  - question: "Remove [ISSUE-ID] '[Title]' (P[X])? Reason: [misalignment reason]"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, remove"
        description: "Remove from sprint via ll-sprint edit --remove"
      - label: "No, keep"
        description: "Leave in sprint"
```

#### 5b: Addition Recommendations (if any)

```yaml
questions:
  - question: "Add [ISSUE-ID] '[Title]' (P[X]) to the sprint? Reason: [alignment reason]"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, add"
        description: "Add to sprint via ll-sprint edit --add"
      - label: "No, skip"
        description: "Don't add to sprint"
```

#### 5c: Summary Confirmation

After all individual decisions, present a summary of pending changes before applying:

```yaml
questions:
  - question: "Apply these changes to [SPRINT_NAME]? Removing: [IDs]. Adding: [IDs]."
    header: "Confirm"
    multiSelect: false
    options:
      - label: "Apply all (Recommended)"
        description: "Execute all accepted changes"
      - label: "Cancel"
        description: "Discard all changes"
```

### Phase 6: Apply Changes

Execute accepted changes using `ll-sprint edit`:

1. **Prune completed/invalid** (if accepted):
   ```bash
   ll-sprint edit $SPRINT_NAME --prune
   ```

2. **Remove specific issues** (if any accepted):
   ```bash
   ll-sprint edit $SPRINT_NAME --remove ISSUE-1,ISSUE-2
   ```

3. **Add new issues** (if any accepted):
   ```bash
   ll-sprint edit $SPRINT_NAME --add ISSUE-3,ISSUE-4
   ```

4. **Revalidate** after all changes:
   ```bash
   ll-sprint edit $SPRINT_NAME --revalidate
   ```

5. **Show updated sprint**:
   ```bash
   ll-sprint show $SPRINT_NAME
   ```

## Output Format

```
================================================================================
SPRINT REVIEW: [sprint-name]
================================================================================

## HEALTH CHECK
- Sprint age: N days (created: YYYY-MM-DD)
- Total issues: N
- Valid: N | Invalid: N | Completed: N
- Dependency cycles: None / [cycle details]
- File contention: None / [contention details]

## RECOMMENDATIONS

### Remove (N issues)
- [ISSUE-ID]: [Title] - [Reason: completed/invalid/misaligned/low-priority]

### Add (N issues)
- [ISSUE-ID]: [Title] (P[X]) - [Reason: theme match/priority/parallelism]

### Warnings
- [Warning description]

## CHANGES APPLIED
- Pruned: [IDs]
- Removed: [IDs]
- Added: [IDs]
- Revalidated: Yes/No

## UPDATED SPRINT
[ll-sprint show output after changes]

================================================================================
```

## Examples

| User Says | Action |
|-----------|--------|
| "Review my sprint" | Ask which sprint, then run full review |
| "Is sprint-improvements still good?" | Run review on sprint-improvements |
| "Check sprint health" | Ask which sprint, then run review |
| "Sprint pre-flight check" | Ask which sprint, then run review |
| "Any stale issues in my sprint?" | Run review focused on staleness |
| "Optimize sprint-improvements" | Run review on sprint-improvements |

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Completed issues directory (default: `completed`)
- `sprints.sprints_dir` - Sprint definitions directory (default: `.sprints`)

## Integration

After reviewing a sprint:

- Execute with `ll-sprint run [name]`
- Map dependencies with `/ll:map-dependencies`
- Create a fresh sprint with `/ll:create-sprint`
- Commit sprint changes with `/ll:commit`
- Check issue sizes with `/ll:issue-size-review`

## Best Practices

### Good Reviews

- Run before sprint execution to catch stale issues
- Pay attention to priority drift - the backlog may have shifted since sprint creation
- Consider sprint age - sprints older than a week benefit most from review
- Use the revalidation step to confirm dependency health after changes

### Avoid

- Blindly accepting all addition recommendations - keep sprints focused
- Over-stuffing sprints with too many issues (diminishing returns on parallelism)
- Removing issues just because they're low priority - they may still be in scope
- Running review on a sprint currently being executed (wait for completion)
