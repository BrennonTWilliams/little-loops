---
description: |
  Evaluate the size/complexity of active issues and propose decomposition for large ones. Use this skill when issues seem too large for a single session, when sprint planning, or to audit issue backlog size.

  Trigger keywords: "issue size review", "decompose issues", "split large issues", "issue complexity", "break down issues", "audit issue sizes", "large issue check"
---

# Issue Size Review Skill

This skill evaluates active issues for complexity and proposes decomposition for those unlikely to be completed in a single session.

## When to Activate

Proactively offer or invoke this skill when the user:

- Mentions an issue seems too large or complex
- Is doing sprint planning and wants manageable chunks
- Asks to audit or review issue sizes
- Mentions context running out during issue work
- Says "this issue is too big" or similar

## How to Use

Invoke this skill to review all active issues:

```
/ll:issue-size-review
```

## Workflow

The skill follows a 5-phase workflow:

### Phase 1: Discovery

Scan all active issues:

1. Use Glob to find all `.md` files in:
   - `{{config.issues.base_dir}}/bugs/`
   - `{{config.issues.base_dir}}/features/`
   - `{{config.issues.base_dir}}/enhancements/`
2. Read each issue file to extract content
3. Parse issue metadata (ID, type, priority, title)

### Phase 2: Size Assessment

Apply scoring heuristics to each issue:

| Criterion | Points | How to Detect |
|-----------|--------|---------------|
| File count | +2 | Count file paths (patterns like `src/`, `.py`, `.ts`, `.md`) mentioned in issue |
| Section complexity | +2 | "Proposed Solution" or "Implementation" sections >300 words |
| Multiple concerns | +3 | Multiple `##` subsections in solution, or phrases like "additionally", "also need to" |
| Dependency mentions | +2 | References to other issues (BUG-/FEAT-/ENH-) or "depends on", "blocked by" |
| Word count | +2 | >800 words total in issue file |

**Maximum score: 11 points**

Issues scoring **≥5 points** are candidates for decomposition.

### Phase 3: Decomposition Proposal

For each candidate issue:

1. Identify distinct sub-tasks or concerns by analyzing:
   - Separate sections in "Proposed Solution"
   - Different files/components mentioned
   - Distinct acceptance criteria
   - Logical boundaries between concerns

2. Propose 2-N focused child issues where each:
   - Has a clear, single responsibility
   - Can be implemented independently
   - Has testable completion criteria
   - Inherits appropriate priority and type

3. Draft child issue structure:
   ```markdown
   # [TYPE]-[NNN]: [Specific Title]

   ## Summary
   [Focused description from parent issue]

   ## Parent Issue
   Decomposed from [PARENT-ID]: [Parent Title]

   [Relevant sections from parent...]
   ```

### Phase 4: User Approval

For each decomposition proposal, use AskUserQuestion:

```yaml
questions:
  - question: "Decompose [ISSUE-ID] '[Title]' (score: X/11) into N smaller issues?"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, decompose"
        description: "Create N child issues: [brief titles]"
      - label: "No, keep as-is"
        description: "Leave this issue intact"
```

Present proposals one at a time or batch (user preference).

### Phase 5: Execution

For each approved decomposition:

1. **Get next issue numbers**:
   ```bash
   # Find highest existing issue number across all directories
   find {{config.issues.base_dir}} -name "*.md" -type f | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | grep -oE "[0-9]+" | sort -n | tail -1
   ```
   Next numbers are `max + 1`, `max + 2`, etc.

2. **Create child issue files**:
   - Determine target directory based on type (bugs/, features/, enhancements/)
   - Generate filename: `P[priority]-[TYPE]-[NNN]-[slug].md`
   - Write issue content with parent reference in frontmatter

3. **Update and move parent issue**:
   Add resolution section to parent:
   ```markdown
   ---

   ## Resolution

   - **Status**: Decomposed
   - **Completed**: YYYY-MM-DD
   - **Reason**: Issue too large for single session

   ### Decomposed Into
   - [TYPE]-[NNN]: [Child title 1]
   - [TYPE]-[NNN]: [Child title 2]
   - [TYPE]-[NNN]: [Child title 3]
   ```

   Move to completed:
   ```bash
   git mv "{{config.issues.base_dir}}/[category]/[parent-file].md" \
          "{{config.issues.base_dir}}/completed/"
   ```

4. **Stage all changes**:
   ```bash
   git add {{config.issues.base_dir}}/
   ```

## Output Format

```
================================================================================
ISSUE SIZE REVIEW
================================================================================

## SUMMARY
- Issues scanned: N
- Large issues found: M (scoring ≥5)
- Decomposition candidates: K

## ASSESSMENT

### Small Issues (0-2 points)
- [ID]: [Title] (score: X)

### Medium Issues (3-4 points)
- [ID]: [Title] (score: X)

### Large Issues (5-7 points) - CANDIDATES
- [ID]: [Title] (score: X)
  Breakdown: files(+2), complexity(+2), concerns(+3)

### Very Large Issues (8+ points) - STRONG CANDIDATES
- [ID]: [Title] (score: X)
  Breakdown: [scoring details]

## PROPOSALS

### [ISSUE-ID]: [Title]
**Score**: X/11
**Breakdown**: [which criteria scored]

**Proposed decomposition into N issues:**

1. **[TYPE]-[NNN]: [Child title 1]**
   - Scope: [What this child covers]
   - Files: [Which files this affects]

2. **[TYPE]-[NNN]: [Child title 2]**
   - Scope: [What this child covers]
   - Files: [Which files this affects]

**Rationale**: [Why this split makes sense]

[AskUserQuestion prompt]

---

## RESULTS

### Decomposed
- [PARENT-ID] → [CHILD-1], [CHILD-2], [CHILD-3]

### Declined
- [ID]: User chose to keep as-is

### Created Issues
- [TYPE]-[NNN]: [Title] (from [PARENT-ID])
- [TYPE]-[NNN]: [Title] (from [PARENT-ID])

### Moved to Completed
- [PARENT-ID]: [Title]

================================================================================
```

## Examples

| User Says | Action |
|-----------|--------|
| "This issue is too big" | Run issue size review on that specific issue |
| "Audit issue sizes" | Run full issue size review |
| "Break down large issues" | Run issue size review |
| "Sprint planning - need smaller tasks" | Run issue size review |
| "Review issue complexity" | Run issue size review |
| "Can we split ENH-179?" | Run issue size review targeting ENH-179 |

## Size Thresholds

| Score | Assessment | Recommendation |
|-------|------------|----------------|
| 0-2 | Small | No action needed - good size for single session |
| 3-4 | Medium | Borderline - may benefit from split if multiple concerns |
| 5-7 | Large | Recommend decomposition |
| 8+ | Very Large | Strongly recommend decomposition |

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Where to move decomposed parents (default: `completed`)

## Best Practices

### Good Decomposition

- Each child issue has **one clear goal**
- Children are **independently implementable** (no blocking dependencies between them)
- Children have **similar size** (avoid 1 large + 2 tiny)
- Children **preserve context** from parent (link back, include relevant details)

### Avoid

- Creating too many tiny issues (cognitive overhead)
- Splitting tightly-coupled concerns that should stay together
- Losing context when decomposing (always reference parent)
- Creating circular dependencies between children

## Integration

After running issue size review:

- Review created child issues with `cat [path]`
- Validate with `/ll:ready_issue [ID]`
- Commit changes with `/ll:commit`
- Process with `/ll:manage_issue` or `/ll:create_sprint`
