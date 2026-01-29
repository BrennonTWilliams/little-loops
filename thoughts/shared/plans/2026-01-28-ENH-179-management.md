# ENH-179: Issue Size Review Skill - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-179-issue-size-review-skill.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The little-loops plugin currently has no automated way to identify and decompose large issues. Users must manually recognize when an issue is too large and manually split it into smaller issues.

### Key Discoveries
- Skills are defined as markdown files with YAML frontmatter in `skills/[skill-name]/SKILL.md`
- Issue scanning patterns exist in `scripts/little_loops/issue_parser.py:435-487` via `find_issues()`
- Issue creation patterns exist in `scripts/little_loops/issue_parser.py:37-73` via `get_next_issue_number()` and `slugify()`
- Moving to completed/ uses `git mv` for history preservation (see `issue_lifecycle.py:175-232`)
- AskUserQuestion patterns are established in commands like `capture_issue.md` and `create_sprint.md`

## Desired End State

A new skill `/ll:issue_size_review` that:
1. Scans all active issues
2. Evaluates complexity using heuristics
3. Proposes decomposition for large issues
4. Presents proposals for user approval
5. Creates child issues and closes parent with decomposition note

### How to Verify
- Run `/ll:issue_size_review` and verify it scans active issues
- Verify large issues are identified with rationale
- Verify proposals show clear decomposition plan
- Verify approved decompositions create proper child issues
- Verify parent issue is moved to completed/ with decomposition note

## What We're NOT Doing

- Not creating a Python CLI tool (keeping this as a pure skill)
- Not adding complex ML-based scoring (using simple heuristics)
- Not auto-approving any decompositions (all require user approval)
- Not modifying existing issue file format (using standard fields)

## Problem Analysis

Large issues are a common problem that leads to:
- Incomplete sessions where context runs out before completion
- Difficulty tracking progress on multi-part work
- Unclear scope and acceptance criteria

## Solution Approach

Create a skill that follows existing patterns from `capture-issue` and `analyze-history` skills:
1. Define trigger keywords for semantic activation
2. Document when to activate and workflow
3. Implement multi-phase process: discovery, assessment, proposal, approval, execution

## Implementation Phases

### Phase 1: Create Skill Directory and File

#### Overview
Create the skill definition file with proper frontmatter and documentation.

#### Changes Required

**File**: `skills/issue-size-review/SKILL.md`
**Changes**: Create new skill file

```markdown
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
/ll:issue_size_review
```

### Workflow

The skill follows a 5-phase workflow:

#### Phase 1: Discovery
- Scan all active issues in bugs/, features/, enhancements/
- Read each issue file to extract content

#### Phase 2: Size Assessment
Apply scoring heuristics to each issue:

| Criterion | Points | Description |
|-----------|--------|-------------|
| File count | +2 | >3 files mentioned |
| Section complexity | +2 | Long "Proposed Solution" or "Implementation" sections (>300 words) |
| Multiple concerns | +3 | Description mentions multiple distinct features/problems |
| Dependency mentions | +2 | Issue mentions multiple dependencies |
| Word count | +2 | >800 words total |

Issues scoring **≥5 points** are candidates for decomposition.

#### Phase 3: Decomposition Proposal
For each candidate:
- Identify distinct sub-tasks or concerns
- Propose 2-N focused child issues
- Ensure each child is independently implementable
- Preserve priority and type information

#### Phase 4: User Approval
Present each proposal with:
- Original issue ID and title
- Proposed child issues (titles and brief scope)
- Rationale for the split
- Y/N approval option

#### Phase 5: Execution
For approved decompositions:
1. Create new issue files with next available IDs
2. Link children to parent (add "Parent: [ID]" in frontmatter)
3. Move parent to completed/ with decomposition note:
   ```markdown
   ## Resolution

   Decomposed into multiple focused issues on YYYY-MM-DD:
   - ENH-180: [title]
   - ENH-181: [title]
   ```
4. Stage all changes with git

## Examples

| User Says | Action |
|-----------|--------|
| "This issue is too big" | Run issue size review |
| "Audit issue sizes" | Run issue size review |
| "Break down large issues" | Run issue size review |
| "Sprint planning - need smaller tasks" | Run issue size review |
| "Review issue complexity" | Run issue size review |

## Size Thresholds

| Score | Assessment | Action |
|-------|------------|--------|
| 0-2 | Small | No action needed |
| 3-4 | Medium | Borderline, may benefit from split |
| 5-7 | Large | Recommend decomposition |
| 8+ | Very Large | Strongly recommend decomposition |

## Output Format

The skill produces a report:

```
================================================================================
ISSUE SIZE REVIEW
================================================================================

## SUMMARY
- Issues scanned: N
- Large issues found: M
- Decomposition candidates: K

## CANDIDATES

### [ISSUE-ID]: [Title]
- Score: X/11
- Scoring: [breakdown]
- Recommendation: Decompose into N issues

Proposed split:
1. [TYPE]-[NNN]: [Child title 1]
   Scope: [brief description]
2. [TYPE]-[NNN]: [Child title 2]
   Scope: [brief description]

[Approval prompt]

## RESULTS
- Decomposed: N issues
- Created: M child issues
- Skipped: K issues (user declined)

================================================================================
```

## Configuration

Uses project configuration from `.claude/ll-config.json`:
- `issues.base_dir` - Base directory for issues
- `issues.categories` - Bug/feature/enhancement directories
- `issues.completed_dir` - Where to move decomposed parents

## Integration

After running issue size review:
- Review created child issues
- Validate with `/ll:ready_issue [ID]`
- Commit changes with `/ll:commit`
- Process with `/ll:manage_issue` or `/ll:create_sprint`
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `skills/issue-size-review/SKILL.md`
- [ ] YAML frontmatter is valid (has description field)
- [ ] Markdown renders without errors

**Manual Verification**:
- [ ] Skill appears in `/ll:help` output
- [ ] Trigger keywords activate the skill

---

### Phase 2: Test the Skill Integration

#### Overview
Verify the skill integrates properly with Claude Code and can be invoked.

#### Changes Required

No file changes - this is verification only.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Format passes: `ruff format scripts/ --check`

**Manual Verification**:
- [ ] `/ll:issue_size_review` invokes the skill
- [ ] Skill reads active issues correctly
- [ ] Scoring heuristics produce reasonable results
- [ ] AskUserQuestion prompts appear for large issues
- [ ] Approved decompositions create proper child issues
- [ ] Parent issues are moved to completed/ with decomposition note

---

## Testing Strategy

### Unit Tests
Not applicable - this is a pure skill (markdown) with no Python code.

### Integration Tests
- Manual testing of full workflow:
  1. Ensure at least one large issue exists (or create a test one)
  2. Run `/ll:issue_size_review`
  3. Verify scoring output
  4. Approve a decomposition
  5. Verify child issues created
  6. Verify parent moved to completed/

## References

- Original issue: `.issues/enhancements/P3-ENH-179-issue-size-review-skill.md`
- Similar skill pattern: `skills/capture-issue/SKILL.md`
- Similar skill pattern: `skills/analyze-history/SKILL.md`
- Issue creation pattern: `scripts/little_loops/issue_parser.py:37-73`
- Issue completion pattern: `scripts/little_loops/issue_lifecycle.py:175-232`
- AskUserQuestion pattern: `commands/capture_issue.md:186-199`
