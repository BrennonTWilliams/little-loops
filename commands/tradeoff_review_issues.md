---
description: |
  Evaluate active issues for utility vs complexity trade-offs and recommend which to implement, update, or close. Use this skill to sense-check your backlog before implementation, prune low-value issues, or during sprint planning to focus on high-value work.

  Trigger keywords: "tradeoff review", "review issues", "utility review", "prune backlog", "issue tradeoff", "sense check issues", "evaluate issues", "backlog review", "worth implementing", "low value issues"
---

# Issue Tradeoff Review

You are tasked with evaluating active issues by scoring utility vs complexity trade-offs, then recommending whether each issue should be implemented as-is, updated first, or closed/deferred. All changes require explicit user approval.

## Workflow

The command follows a 5-phase workflow:

### Phase 1: Discovery

Scan all active issues:

1. Read `.claude/ll-config.json` for issue directory configuration
2. Use Glob to find all `.md` files in:
   - `{{config.issues.base_dir}}/bugs/`
   - `{{config.issues.base_dir}}/features/`
   - `{{config.issues.base_dir}}/enhancements/`
3. Exclude the `{{config.issues.completed_dir}}/` directory
4. Read each issue file to extract content
5. Parse issue metadata from filename and content:
   - ID (e.g., `BUG-042`, `FEAT-257`)
   - Type (`BUG`, `FEAT`, `ENH`)
   - Priority (`P0`-`P5`)
   - Title (from `# heading`)
   - Summary section content

If no active issues are found, output "No active issues found to review." and stop.

If any issue file cannot be parsed (missing content, unreadable), log a warning for that file and continue with valid issues. Include skipped files in the final summary.

### Phase 2: Wave-Based Evaluation

Batch issues into waves of 3-5 issues each. For each wave, launch a subagent using the Task tool:

**IMPORTANT**: Spawn all subagents for a wave in a SINGLE message with multiple Task tool calls.

Each subagent receives a batch of issue summaries and evaluates them. Use the following prompt template for each subagent:

```
Evaluate the following issues on utility vs complexity dimensions.

For each issue, read the full issue file and score on these dimensions using LOW, MEDIUM, or HIGH:

1. **Utility to project**: How much value does this provide to users/developers?
   - HIGH: Core functionality, user-facing improvement, addresses real pain point
   - MEDIUM: Nice-to-have, improves developer experience, moderate user impact
   - LOW: Marginal benefit, edge case, cosmetic, or speculative

2. **Implementation effort**: How much work is required?
   - LOW: <1 hour, simple change, few files
   - MEDIUM: 1-4 hours, moderate complexity, several files
   - HIGH: >4 hours, significant complexity, many files or architectural changes

3. **Complexity added**: How much complexity does this add to the codebase?
   - LOW: Isolated change, follows existing patterns
   - MEDIUM: New patterns or moderate integration points
   - HIGH: New abstractions, cross-cutting concerns, architectural impact

4. **Technical debt risk**: How likely is this to create or increase tech debt?
   - LOW: Clean implementation, well-defined scope
   - MEDIUM: Some risk of shortcuts or incomplete abstraction
   - HIGH: Likely to require rework, unclear scope, or quick-fix temptation

5. **Maintenance overhead**: How much ongoing maintenance will this require?
   - LOW: Set-and-forget, minimal upkeep
   - MEDIUM: Occasional updates needed, moderate dependency surface
   - HIGH: Frequent updates, external dependencies, breaking change exposure

6. **Blocking bottleneck**: How many other issues depend on this one?
   - HIGH: Blocks 3+ other issues (critical bottleneck)
   - MEDIUM: Blocks 1-2 other issues
   - LOW: Blocks no other issues

   To determine this:
   - Read all active issue files and check their `## Blocked By` sections
   - Count how many issues reference this issue ID in their `## Blocked By`
   - Issues that block many others have higher effective utility regardless of their standalone value

Then make a recommendation:
- **Implement**: Good utility-to-complexity ratio (high utility, manageable cost)
- **Update first**: Has merit but needs refinement (unclear scope, missing details, or scope too broad)
- **Close/Defer**: Low value relative to complexity (low utility with medium/high cost, or speculative)

**Adjusted recommendation for blocking bottleneck**: If an issue scores HIGH on blocking (blocks 3+ issues), boost its recommendation by one tier:
- Close/Defer with HIGH blocking → Update first (it unblocks others)
- Update first with HIGH blocking → Implement (it unblocks others)

Issues to evaluate:

[For each issue in the batch:]
- **File**: [path]
- **ID**: [ISSUE-ID]
- **Type**: [BUG/FEAT/ENH]
- **Priority**: [P0-P5]
- **Title**: [title]
- **Summary**: [first 200 chars of summary]

Return results as a structured list:

For each issue:
- issue_id: [ID]
- file_path: [path]
- utility: [LOW/MEDIUM/HIGH]
- effort: [LOW/MEDIUM/HIGH]
- complexity: [LOW/MEDIUM/HIGH]
- tech_debt: [LOW/MEDIUM/HIGH]
- maintenance: [LOW/MEDIUM/HIGH]
- blocking: [LOW/MEDIUM/HIGH]
- recommendation: [Implement/Update first/Close/Defer]
- rationale: [1-2 sentence explanation]
```

**Subagent failure handling**: If a subagent fails or times out, retry once. If the retry also fails, skip those issues with a "could not evaluate" warning and continue with remaining waves.

Wait for all subagents in a wave to complete before launching the next wave.

### Phase 3: Aggregation & Recommendation

Collect all subagent results and organize by recommendation:

1. Group results into three categories:
   - **Close/Defer** (present first - these are actionable changes)
   - **Update first** (present second - these need attention)
   - **Implement** (present last - no changes needed)

2. Within each group, sort by priority (P0 first, P5 last)

3. Compile the summary table

### Phase 4: User Presentation & Approval

#### 4a: Present Summary Table

Display the full evaluation results:

```
================================================================================
ISSUE TRADEOFF REVIEW
================================================================================

## SUMMARY
- Issues reviewed: N
- Recommend implement: X
- Recommend update first: Y
- Recommend close/defer: Z
- Could not evaluate: W

## CLOSE/DEFER RECOMMENDATIONS

| ID | Title | Utility | Effort | Complexity | Tech Debt | Maintenance | Blocking | Rationale |
|----|-------|---------|--------|------------|-----------|-------------|----------|-----------|
| [ID] | [Title] | LOW | HIGH | HIGH | MEDIUM | HIGH | LOW | [Brief reason] |

## UPDATE FIRST RECOMMENDATIONS

| ID | Title | Utility | Effort | Complexity | Tech Debt | Maintenance | Blocking | Rationale |
|----|-------|---------|--------|------------|-----------|-------------|----------|-----------|
| [ID] | [Title] | MEDIUM | MEDIUM | MEDIUM | LOW | MEDIUM | LOW | [Brief reason] |

## IMPLEMENT RECOMMENDATIONS (no changes needed)

| ID | Title | Utility | Effort | Complexity | Tech Debt | Maintenance | Blocking |
|----|-------|---------|--------|------------|-----------|-------------|----------|
| [ID] | [Title] | HIGH | LOW | LOW | LOW | LOW | LOW |
```

#### 4b: Per-Issue Approval

For each issue recommended for **Close/Defer**, use AskUserQuestion:

```yaml
questions:
  - question: "Close [ISSUE-ID] '[Title]' as low-value/deferred?"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, close"
        description: "Move to completed/ with tradeoff review resolution note"
      - label: "No, keep active"
        description: "Leave this issue as-is in the backlog"
      - label: "Update instead"
        description: "Keep active but add review notes for refinement"
```

For each issue recommended for **Update first**, use AskUserQuestion:

```yaml
questions:
  - question: "Add review notes to [ISSUE-ID] '[Title]'?"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, add notes"
        description: "Append tradeoff review findings to the issue file"
      - label: "No, skip"
        description: "Leave this issue unchanged"
      - label: "Close instead"
        description: "Close this issue as low-value/deferred"
```

Issues recommended for **Implement** require no user action (they stay as-is).

### Phase 5: Execution

Execute all approved changes:

#### For Approved Closures

1. Add resolution section to the issue file:

```markdown

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: YYYY-MM-DD
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: [score]
- Implementation Effort: [score]
- Complexity Added: [score]
- Technical Debt Risk: [score]
- Maintenance Overhead: [score]

### Rationale
[Subagent rationale for closure recommendation]
```

2. Move to completed:
```bash
git mv "{{config.issues.base_dir}}/[category]/[file].md" \
       "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
```

#### For Approved Updates

Append review notes to the issue file:

```markdown

---

## Tradeoff Review Note

**Reviewed**: YYYY-MM-DD by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | [score] |
| Implementation effort | [score] |
| Complexity added | [score] |
| Technical debt risk | [score] |
| Maintenance overhead | [score] |

### Recommendation
Update first - [specific suggestion from rationale]
```

#### Stage All Changes

```bash
git add {{config.issues.base_dir}}/
```

## Output Format

```
================================================================================
ISSUE TRADEOFF REVIEW COMPLETE
================================================================================

## SUMMARY
- Issues reviewed: N
- Closed (approved): X
- Updated (approved): Y
- Kept as-is: Z
- Skipped (could not evaluate): W

## CLOSED ISSUES
- [ID]: [Title] → moved to {{config.issues.base_dir}}/{{config.issues.completed_dir}}/

## UPDATED ISSUES
- [ID]: [Title] → review notes appended

## UNCHANGED ISSUES
- [ID]: [Title] → implement (no changes needed)
- [ID]: [Title] → user declined recommendation

## SKIPPED ISSUES
- [file]: Could not evaluate (parse error / subagent failure)

## GIT STATUS
- All changes staged in {{config.issues.base_dir}}/

================================================================================
```

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Where to move closed issues (default: `completed`)

## Overlap with Issue Size Review

This command complements `/ll:issue_size_review`:
- **Issue size review** asks: "Is this too big?" (decompose large issues)
- **Tradeoff review** asks: "Is this worth doing?" (prune low-value issues)

Both can be run as part of backlog grooming. Run tradeoff review first to prune, then size review to decompose remaining issues.

## Integration

After running tradeoff review:
- Review closed issues in `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/`
- Review updated issues with review notes appended
- Commit changes with `/ll:commit`
- Process remaining issues with `/ll:manage_issue` or `/ll:create_sprint`
