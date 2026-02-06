---
discovered_date: 2026-02-05
discovered_by: capture_issue
---

# FEAT-257: Add /ll:tradeoff_review_issues Skill for Issue Utility vs Complexity Evaluation

## Summary

Create a new Command `/ll:tradeoff_review_issues` in the little-loops plugin that sense-checks active Issues before implementation by evaluating their utility vs complexity trade-offs. The command launches subagents in waves to review all active Issues, scoring each on multiple dimensions, then presents recommendations to the user for approval before executing any changes.

## Context

**Direct mode**: User description: "Create a new Command in our `ll@little-loops` (`ll`) custom claude code plugin `/ll:tradeoff_review_issues` to sense-check Issues before implementation by evaluating their utility vs complexity trade-offs. The Command should launch subagents in waves to review all active Issues (as defined in `ll-config` file, default Issue folders are `.issues/bugs/`, `.issues/enhancements/`, and `.issues/features/`). Subagents should evaluate utility to the project, implementation effort, complexity added, technical debt added, maintenance overhead added, etc., on a LOW, MEDIUM, HIGH scale, then make a final determination on if the Issue should be implemented, updated/changed first, or closed as low-value/deferred. The command should present the changes to the user as a final step before executing changes to Issue files, with 'y/n' style review and approval."

## User Story

As a solo developer using little-loops, I want to periodically review my issue backlog so I can prune low-value items before they accumulate.

## Acceptance Criteria

- [ ] Command discovers all `.md` issue files in configured issue directories (default: `.issues/bugs/`, `.issues/enhancements/`, `.issues/features/`), excluding `completed/`
- [ ] Each issue is scored LOW/MEDIUM/HIGH on all five dimensions: utility to project, implementation effort, complexity added, technical debt risk, and maintenance overhead
- [ ] A formatted summary table of all evaluations and recommendations is presented to the user before any file changes occur
- [ ] No file mutations (closing, moving, or annotating issues) happen without explicit user approval per recommendation
- [ ] Approved closures move issues to `completed/` with a utility review resolution note
- [ ] Approved update recommendations append review notes to the issue file
- [ ] All changes are staged with git after execution

## Current Behavior

There is no automated way to evaluate whether active issues are worth implementing. Users must manually assess utility vs complexity trade-offs for each issue, which is time-consuming and inconsistent. Low-value issues can accumulate in the backlog without being identified or closed.

## Expected Behavior

The `/ll:tradeoff_review_issues` command should:

1. **Discover active issues** from configured issue directories (default: `.issues/bugs/`, `.issues/enhancements/`, `.issues/features/`)
2. **Launch subagents in waves** to review issues in parallel batches (to manage context and API load)
3. **Evaluate each issue** on a LOW/MEDIUM/HIGH scale across dimensions:
   - **Utility to project**: How much value does this provide to users/developers?
   - **Implementation effort**: How much work is required to implement?
   - **Complexity added**: How much complexity does this add to the codebase?
   - **Technical debt risk**: How likely is this to create or increase tech debt?
   - **Maintenance overhead**: How much ongoing maintenance will this require?
4. **Make a recommendation** for each issue:
   - **Implement**: Good utility-to-complexity ratio, proceed as-is
   - **Update first**: Issue has merit but needs refinement before implementation
   - **Close/Defer**: Low value relative to complexity, close or defer indefinitely
5. **Present all recommendations** in a summary table to the user
6. **Allow y/n review and approval** per-issue or in bulk before executing any file changes
7. **Execute approved changes**: Close low-value issues (move to completed with reason), add notes to issues flagged for updates

## Proposed Solution

Create a new skill at `skills/tradeoff-review-issues/SKILL.md` (per project preference for Skills over Agents/Commands for new functionality) with the following workflow:

### Phase 1: Discovery
- Read `ll-config.json` for issue directory configuration
- Scan all active issue directories (excluding completed)
- Collect all `.md` issue files

### Phase 2: Wave-Based Subagent Review
- Batch issues into waves (e.g., 3-5 issues per wave)
- Launch parallel subagents per wave using Task tool
- Each subagent reads assigned issue files and evaluates on the scoring dimensions
- Subagents return structured evaluation results

### Phase 3: Aggregation & Recommendation
- Collect all subagent results
- Apply recommendation logic based on score combinations
- Sort by recommendation category (close/defer first, then update, then implement)

### Phase 4: User Presentation & Approval
- Display summary table with all evaluations and recommendations
- Use AskUserQuestion for per-issue or bulk approval
- Allow user to override any recommendation

### Phase 5: Execution
- For approved closures: move to completed/ with utility review resolution note
- For approved updates: append review notes to issue file
- For implement recommendations: no changes needed (issue stays as-is)
- Stage all changes with git

## Edge Cases

- **Empty backlog**: If no active issues are found in any configured directory, print a message ("No active issues found") and exit gracefully
- **Malformed issue files**: If an issue file cannot be parsed (missing frontmatter, unreadable, etc.), log a warning for that file and continue reviewing valid issues; include skipped files in the final summary
- **Large backlogs**: No limit on the number of issues reviewed per run; all active issues are processed regardless of count
- **Subagent failure/timeout**: If a subagent fails or times out during evaluation, retry once; if the retry also fails, skip that issue with a "could not evaluate" warning and continue with the remaining issues
- **Duplicate recommendations**: If multiple issues overlap significantly, each is still evaluated independently (deduplication is out of scope for this feature)

## Impact

- **Priority**: P3
- **Effort**: Medium - New command with subagent orchestration
- **Risk**: Low - Read-heavy with user approval gates before any mutations

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Command structure and subagent patterns |
| guidelines | .claude/CLAUDE.md | Command development conventions |

## Overlap Note

The existing `/ll:issue_size_review` skill (in `skills/issue-size-review/SKILL.md`) evaluates issue **size/complexity** and proposes decomposition. This new feature evaluates **utility vs complexity trade-offs** to decide whether issues should be implemented, updated, or closed. The two are complementary: `issue-size-review` asks "is this too big?" while `tradeoff-review-issues` asks "is this worth doing?" Implementation should reference the existing skill as a pattern for subagent wave orchestration and user approval flow.

## Implementation Note

Per project convention (CLAUDE.md: "Prefer Skills over Agents"), this should be implemented as a **Skill** at `skills/tradeoff-review-issues/SKILL.md`, not as a Command in `commands/`. The existing command directory uses flat `.md` files (e.g., `commands/manage_issue.md`), not subdirectories with `COMMAND.md`.

## Labels

`feature`, `skill`, `issue-management`, `workflow-automation`

---

## Status

**Completed** | Created: 2026-02-05 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-05
- **Status**: Completed

### Changes Made
- `skills/tradeoff-review-issues/SKILL.md`: New skill file with 5-phase workflow (Discovery, Wave-Based Evaluation, Aggregation, User Approval, Execution)

### Verification Results
- Tests: PASS (2455 passed)
- Lint: PASS
- Types: N/A (no Python code added)
- YAML frontmatter: Valid
