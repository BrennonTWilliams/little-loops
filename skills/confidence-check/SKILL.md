---
description: |
  Pre-implementation confidence check that validates readiness before coding begins. Evaluates 5 criteria: no duplicate implementations, architecture compliance, root cause identified, issue well-specified, and dependencies satisfied. Produces a score (0-100) with go/no-go recommendation.

  Complementary to /ll:ready_issue (which validates the issue file) — this skill validates the implementation approach and codebase readiness.

  Trigger keywords: "confidence check", "pre-implementation check", "ready to implement", "implementation readiness", "confidence score"
---

# Confidence Check Skill

Pre-implementation assessment that validates readiness to begin coding. Uses research findings from Phase 1.5 (or standalone research) to evaluate whether the proposed approach is sound.

## When to Activate

- Before implementation in `/ll:manage_issue` (recommended step in Phase 2)
- When unsure whether an issue is ready for coding
- After deep research, to evaluate whether findings support the approach
- User asks "is this ready to implement?" or similar

## Arguments

$ARGUMENTS

If arguments provided, parse as issue ID (e.g., `ENH-277`). Otherwise, expect to be invoked within a manage_issue context where research findings are already available.

## Workflow

### Phase 1: Gather Context

If invoked standalone (not within manage_issue):
1. Read the issue file
2. Use Glob/Grep to find related files mentioned in the issue
3. Check for existing implementations

If invoked within manage_issue: use the research findings already gathered in Phase 1.5.

### Phase 2: Five-Point Assessment

Evaluate each criterion and assign a score (0-20 points each):

#### Criterion 1: No Duplicate Implementations (0-20 points)

**What to check**: Whether code already exists that solves this problem.

**Detection method**:
1. Extract key terms from the issue title and summary (function names, feature names, concepts)
2. Use Grep to search for those terms in `{{config.project.src_dir}}`
3. Check `{{config.issues.base_dir}}/completed/` for previously resolved issues with similar titles
4. Search for TODO/FIXME comments that reference the same problem

**Scoring**:
| Finding | Score |
|---------|-------|
| No existing implementation found | 20 |
| Related code exists but doesn't solve the problem | 15 |
| Partial implementation exists (needs extension, not duplication) | 10 |
| Near-complete implementation already exists | 0 |

#### Criterion 2: Architecture Compliance (0-20 points)

**What to check**: Whether the proposed approach fits existing patterns.

**Detection method**:
1. Identify what type of component is being added/modified (skill, command, script, hook, config)
2. Find 2-3 existing examples of the same component type
3. Compare the proposed approach against established patterns:
   - File location matches convention (e.g., skills go in `skills/`, commands in `commands/`)
   - Naming follows project convention (kebab-case directories, SKILL.md/command.md files)
   - Integration points use established mechanisms (Skill tool, Task tool, config references)
4. Check if the issue's "Files to Modify" section aligns with where similar changes were made

**Scoring**:
| Finding | Score |
|---------|-------|
| Approach matches established patterns completely | 20 |
| Mostly matches, minor deviations justified | 15 |
| Partially matches, some concerns about fit | 10 |
| Contradicts established patterns or creates parallel pathways | 0 |

#### Criterion 3: Root Cause Identified (0-20 points)

**What to check**: Whether the actual problem is understood (not just symptoms).

**Detection method**:
1. For **bugs**: Check issue has a "Problem Analysis" or "Root Cause" section with specific file:line references
2. For **features**: Check issue has clear requirements (not just "add X" but "add X that does Y when Z")
3. For **enhancements**: Check issue explains what's wrong with current behavior and what specifically should change
4. Verify claims in the issue against actual code (do referenced files/functions exist? do they behave as described?)

**Scoring**:
| Finding | Score |
|---------|-------|
| Root cause clearly identified with code references that check out | 20 |
| Root cause described but code references not fully verified | 15 |
| Symptoms described but root cause is inferred/assumed | 10 |
| Only symptoms described, no analysis of underlying cause | 0 |

#### Criterion 4: Issue Well-Specified (0-20 points)

**What to check**: Whether the issue has enough detail to implement without guessing.

**Detection method**:
1. Check for acceptance criteria or "Expected Behavior" section
2. Check for specific files to modify (not just "update the code")
3. Check for scope boundaries ("What We're NOT Doing" or "Out of scope")
4. Check that implementation steps are actionable (not vague like "improve performance")

**Scoring**:
| Finding | Score |
|---------|-------|
| Clear acceptance criteria, specific files, defined scope | 20 |
| Most details present, 1-2 minor gaps fillable from context | 15 |
| Key details missing but inferrable from codebase research | 10 |
| Vague requirements, significant guesswork needed | 0 |

#### Criterion 5: Dependencies Satisfied (0-20 points)

**What to check**: Whether blocking issues are resolved and required infrastructure exists.

**Detection method**:
1. Check issue for "Blocked By" or "Dependencies" sections
2. If dependencies listed, verify they exist in `{{config.issues.base_dir}}/completed/`
3. Check that files/modules referenced in the issue actually exist
4. Verify any required configuration or infrastructure is in place

**Scoring**:
| Finding | Score |
|---------|-------|
| No dependencies, or all dependencies satisfied | 20 |
| Minor dependencies unresolved but non-blocking | 15 |
| Some dependencies unresolved, workarounds possible | 10 |
| Critical dependencies unresolved, cannot proceed | 0 |

### Phase 3: Score and Recommend

Sum all criterion scores (max 100):

| Total Score | Recommendation | Action |
|-------------|---------------|--------|
| **90-100** | PROCEED | Begin implementation |
| **70-89** | PROCEED WITH CAUTION | List specific concerns, then proceed |
| **50-69** | STOP — ADDRESS GAPS | List gaps that must be resolved before implementation |
| **0-49** | STOP — NOT READY | Mark issue as NOT_READY with specific reasons |

## Output Format

```
================================================================================
CONFIDENCE CHECK: [ISSUE-ID]
================================================================================

## SCORES

| Criterion                  | Score | Details                    |
|---------------------------|-------|----------------------------|
| No duplicate implementations | XX/20 | [Brief finding]           |
| Architecture compliance     | XX/20 | [Brief finding]           |
| Root cause identified       | XX/20 | [Brief finding]           |
| Issue well-specified        | XX/20 | [Brief finding]           |
| Dependencies satisfied      | XX/20 | [Brief finding]           |

**TOTAL: XX/100**

## RECOMMENDATION: [PROCEED | PROCEED WITH CAUTION | STOP — ADDRESS GAPS | STOP — NOT READY]

### Concerns (if any)
- [Specific concern with reference]

### Gaps to Address (if score < 70)
- [Gap 1: what's missing and how to fix]
- [Gap 2: what's missing and how to fix]

================================================================================
```

## Integration with /ll:manage_issue

This skill is referenced in `/ll:manage_issue` Phase 2 as a recommended pre-planning step. When invoked within manage_issue:

- Uses research findings from Phase 1.5 (no redundant searching)
- Score >=70: proceed to plan creation
- Score <70: stop and report gaps (manage_issue marks as INCOMPLETE)
- Non-blocking by default — can be skipped if user prefers

## Examples

| Scenario | Expected Outcome |
|----------|-----------------|
| Well-researched bug with clear root cause | 85-100: PROCEED |
| Feature request with vague "improve X" | 40-60: STOP — needs clearer requirements |
| Enhancement with existing partial implementation | 70-80: PROCEED WITH CAUTION — note existing code |
| Issue blocked by unresolved dependency | 50-65: STOP — dependency must be resolved first |
