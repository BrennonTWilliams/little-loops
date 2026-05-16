---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# ENH-179: Issue Size Review Skill

## Summary

Create a new skill `/ll:issue-size-review` that evaluates the size/complexity of active issues, identifies those unlikely to be completed in a single session, and proposes decomposition into multiple smaller issues with user approval.

## Context

**Direct mode**: User description: "New Skill `/ll:issue-size-review` that evaluates the size of each Active Issue. For substantial Issues (unlikely to be completed within a single session), propose decomposition of the Issue into multiple. Present all proposals for user review with (y/n) approval. If approved, create decomposed Issues and move each original large Issue to completed with a note that it was broken down into multiple Issues with a list of each Issue ID/name it was decomposed into."

## Current Behavior

There is no automated way to identify and decompose large issues. Users must manually recognize when an issue is too large and manually split it into smaller issues.

## Expected Behavior

The `/ll:issue-size-review` skill should:

1. **Scan all active issues** across all categories (bugs, features, enhancements)
2. **Evaluate size/complexity** using heuristics such as:
   - Number of proposed changes or steps
   - Multiple file locations mentioned
   - Multiple subsystems affected
   - Estimated scope based on description complexity
   - Presence of multiple distinct concerns
3. **Identify substantial issues** that are unlikely to be completed in a single Claude Code session
4. **Propose decomposition** for each large issue into 2-N smaller, focused issues
5. **Present proposals** to user with clear breakdown showing:
   - Original issue ID and title
   - Proposed child issues (titles and scope)
   - Rationale for the split
6. **Request approval** using AskUserQuestion with y/n for each proposal
7. **Execute approved decompositions**:
   - Create new issue files for each child issue
   - Link child issues to original parent (in frontmatter or description)
   - Move original issue to completed with note:
     ```markdown
     ## Resolution

     Decomposed into multiple focused issues on YYYY-MM-DD:
     - ENH-180: [title]
     - ENH-181: [title]
     - ENH-182: [title]
     ```

## Proposed Solution

Create a new skill at `skills/issue-size-review/SKILL.md` with the following workflow:

### Phase 1: Discovery
- Find all active issues (not in completed/)
- Read each issue file
- Parse structure and content

### Phase 2: Size Assessment
Apply scoring heuristics:
- **File count**: >3 files = +2 points
- **Section complexity**: Long "Proposed Solution" or "Implementation" sections = +2 points
- **Multiple concerns**: Description mentions multiple distinct features/problems = +3 points
- **Dependency chain**: Issue has multiple dependencies = +2 points
- **Word count**: >800 words = +2 points

Issues scoring ≥5 points are candidates for decomposition.

### Phase 3: Decomposition Proposals
For each candidate, use Claude's reasoning to propose a logical split:
- Identify distinct sub-tasks or concerns
- Create 2-N focused child issues
- Ensure each child is independently implementable
- Preserve priority and type information

### Phase 4: User Approval
Present each proposal using AskUserQuestion:
```yaml
questions:
  - question: "Decompose ENH-123 into 3 smaller issues?"
    header: "ENH-123"
    options:
      - label: "Yes, decompose"
        description: "Create 3 child issues and close parent"
      - label: "No, keep as-is"
        description: "Leave this issue intact"
```

### Phase 5: Execution
For approved decompositions:
1. Create new issue files using standard naming (next available IDs)
2. Link children to parent (add "Parent: ENH-123" in frontmatter)
3. Move parent to completed/ with decomposition note
4. Stage all changes with git

## Impact

- **Priority**: P3 - Nice to have for issue management workflow
- **Effort**: Medium - New skill with complex analysis logic
- **Risk**: Low - Read-heavy with user approval gates

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Skill development patterns |
| architecture | docs/ARCHITECTURE.md | Issue file format and lifecycle |

## Labels

`enhancement`, `skill`, `issue-management`, `workflow-automation`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-28
- **Status**: Completed

### Changes Made
- `skills/issue-size-review/SKILL.md`: Created new skill with 5-phase workflow (discovery, size assessment, decomposition proposal, user approval, execution)

### Implementation Details
- Skill uses heuristic scoring (0-11 points) based on: file count, section complexity, multiple concerns, dependency mentions, word count
- Issues scoring ≥5 points are candidates for decomposition
- Uses AskUserQuestion for user approval before any changes
- Creates child issues with parent reference and moves parent to completed/ with decomposition note

### Verification Results
- YAML frontmatter: PASS
- Skill structure: PASS (follows existing skill patterns)
