# ENH-389: Re-prioritize option when all issues already prioritized - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-389-reprioritize-option-when-all-issues-already-prioritized.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `prioritize_issues` command (`commands/prioritize_issues.md:29-44`) scans issue directories for files lacking `P[0-5]-` prefixes. When all issues already have priority prefixes, the bash loop produces no "Unprioritized:" output and the command silently has nothing to do — no prompt, no report.

### Key Discoveries
- Detection logic uses `^P[0-5]-` regex at `commands/prioritize_issues.md:38`
- The `completed/` directory is included in the glob `{{config.issues.base_dir}}/*/` — needs exclusion for re-prioritization
- Line 130 already says "Re-evaluate priorities periodically" but has no mechanism for it
- No existing "nothing to do → offer redo" pattern exists in commands; this will be the first
- AskUserQuestion patterns exist in `tradeoff_review_issues.md:176-206` and `capture_issue.md:272-285`
- Before/after change table patterns exist in `align_issues.md:350-354` and `normalize_issues.md:327-331`

### Patterns to Follow
- `tradeoff_review_issues.md:176-206` — single-select yes/no AskUserQuestion pattern
- `align_issues.md:350-354` — `Original | Fixed To` change table
- `prioritize_issues.md:70-74` — existing `git mv` rename pattern (adapt for prefix replacement)

## Desired End State

When all active issues already have `P[0-5]-` prefixes:
1. The command detects this state
2. Prompts the user: "All issues are already prioritized. Would you like to re-evaluate priorities?"
3. If approved, re-assesses all active issues using the same criteria as initial prioritization
4. Reports changes in a before/after table (e.g., "P3 → P2: ENH-389 - reason")
5. If declined, exits with a summary of current priority distribution

### How to Verify
- Run `/ll:prioritize-issues` when all issues have priority prefixes → should prompt for re-evaluation
- Approve re-evaluation → should re-assess and report changes
- Decline re-evaluation → should exit cleanly with summary

## What We're NOT Doing

- Not changing the prioritization criteria/algorithm itself
- Not adding automatic periodic re-prioritization
- Not re-prioritizing completed issues
- Not adding CLI flags or arguments to the command
- Not modifying any Python code (this is a command prompt modification only)

## Solution Approach

Modify `commands/prioritize_issues.md` to add a conditional branch after the unprioritized scan:
- If unprioritized issues found → proceed with existing flow (no change)
- If all already prioritized → prompt user with AskUserQuestion, then either re-evaluate or exit

## Code Reuse & Integration

- **Reuse**: Existing priority assessment criteria at `prioritize_issues.md:56-66`
- **Reuse**: Existing `git mv` rename pattern at `prioritize_issues.md:70-74`
- **Follow**: AskUserQuestion pattern from `tradeoff_review_issues.md:176-206`
- **Follow**: Change report table from `align_issues.md:350-354`
- **New code justification**: The "all-prioritized detection + prompt" branch is new logic — no existing equivalent

## Implementation Phases

### Phase 1: Add Re-prioritize Flow to prioritize_issues.md

#### Overview
Add a new section between step 1 (Find Unprioritized Issues) and step 2 (Analyze Each Issue) that handles the "all already prioritized" case.

#### Changes Required

**File**: `commands/prioritize_issues.md`

1. **Add Step 1.5** — After the unprioritized scan (line 44), add a conditional check:
   - Count issues with and without priority prefixes (excluding `completed/` directory)
   - If unprioritized count > 0, continue to existing Step 2
   - If unprioritized count == 0, proceed to re-prioritize prompt

2. **Add re-prioritize prompt** — Use AskUserQuestion with options:
   - "Re-evaluate all" — Re-assess all active issue priorities
   - "View current" — Show current priority distribution and exit

3. **Add re-prioritize flow** — If user approves:
   - Read each active issue file
   - Re-assess priority using the same criteria as Step 2
   - Use `git mv` to rename files where priority changed (strip old `P[X]-` prefix, add new `P[Y]-`)
   - Skip issues where priority stays the same

4. **Add re-prioritize report** — Show changes in before/after format:
   - Summary of changes vs unchanged
   - Table with: Issue ID | Old Priority | New Priority | Reason
   - Only list issues that actually changed

5. **Update existing report** — Adapt Step 4 report to also work for re-prioritize mode

6. **Update commit message** — For re-prioritize, use: `chore(issues): re-prioritize issues`

#### Success Criteria

**Automated Verification**:
- [ ] Command file is valid markdown with proper frontmatter
- [ ] No syntax errors in bash code blocks

**Manual Verification**:
- [ ] Running `/ll:prioritize-issues` with all-prioritized issues shows AskUserQuestion prompt
- [ ] Selecting "Re-evaluate all" triggers re-assessment of all active issues
- [ ] Selecting "View current" shows priority distribution and exits
- [ ] Priority changes are reported with before/after values
- [ ] Files are renamed correctly with `git mv`
- [ ] Commit message reflects re-prioritization

## Testing Strategy

### Manual Tests
- Run `/ll:prioritize-issues` when all issues have `P[0-5]-` prefixes → verify prompt appears
- Run `/ll:prioritize-issues` when some issues lack prefixes → verify existing behavior unchanged
- Approve re-evaluation → verify changes are applied and reported
- Decline re-evaluation → verify clean exit

## References

- Original issue: `.issues/enhancements/P3-ENH-389-reprioritize-option-when-all-issues-already-prioritized.md`
- Command file: `commands/prioritize_issues.md`
- AskUserQuestion pattern: `commands/tradeoff_review_issues.md:176-206`
- Change report pattern: `commands/align_issues.md:350-354`
