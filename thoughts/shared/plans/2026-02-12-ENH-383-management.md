# ENH-383: Add Direct Fix Option to audit_docs Review - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-383-add-direct-fix-option-to-audit-docs-review.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:audit-docs` command (`commands/audit_docs.md`) is a prompt template with 8 phases:

1. Find documentation files
2. Audit each document (accuracy, completeness, consistency, currency)
3. Test code examples
4. **Output report** — already generates "Recommended Fixes" with old/new content (lines 118-131) and "Auto-Fixable Issues" (lines 133-139)
5. Issue management — maps findings to issue types via severity matrix
6. Deduplication — checks for existing issues
7. **User Approval** — `AskUserQuestion` with only "Create all" / "Skip" / "Select items" (lines 311-317)
8. Execute issue changes — creates/updates/reopens issues

### Key Discoveries
- The report already includes specific fix content (old/new values) at `audit_docs.md:120-127`
- The "Auto-Fixable Issues" section at `audit_docs.md:133-139` mentions `--fix` but this flag is not implemented
- `audit_claude_config.md:390-444` has a complete direct-fix pattern with severity waves and per-fix approval
- `tradeoff_review_issues.md:174-206` shows per-item AskUserQuestion with 3 action choices
- `align_issues.md:241-271` distinguishes auto-fixable vs non-auto-fixable findings

### Patterns to Follow
- `audit_claude_config` severity-tiered fix session (Critical → Warning → Suggestion waves)
- `tradeoff_review_issues` per-item 3-option prompt pattern
- `align_issues` auto-fixable vs non-auto-fixable distinction

## Desired End State

After implementation, `/ll:audit-docs` will:
1. Present findings with a new "Action Selection" phase offering **three paths**: Fix directly, Create issues, or Skip
2. For "Fix directly": apply auto-fixable corrections in-place, show diffs, stage files
3. For "Create issues": continue with existing issue management flow unchanged
4. Support `--fix` flag for auto-applying all auto-fixable corrections without prompting

### How to Verify
- Read the modified `commands/audit_docs.md` and verify the new phase is present with proper structure
- Verify `--fix` argument is added to the arguments section
- Verify the existing issue creation flow is preserved unchanged
- Verify the new phase follows established patterns from `audit_claude_config`

## What We're NOT Doing

- Not changing how findings are detected (Phases 1-4 remain unchanged)
- Not modifying the issue file format (Phase 5-6 issue format unchanged)
- Not adding Python code — this is a prompt template modification only
- Not changing the deduplication logic
- Not implementing complex fixes (rewrites, new sections) — only mechanical corrections

## Solution Approach

Insert a new **Phase 4.5: Direct Fix Option** between the report output (Phase 4) and issue management (Phase 5). This phase:
1. Classifies each finding as "auto-fixable" or "needs-issue"
2. Presents findings with per-category action options
3. For auto-fixable items chosen for direct fix: applies edits, stages files
4. Remaining findings flow to the existing issue management pipeline

The `--fix` flag auto-applies all auto-fixable corrections, skipping the prompt.

## Code Reuse & Integration

- **Pattern from `audit_claude_config.md:390-444`**: Severity-tiered fix waves with diff preview
- **Pattern from `tradeoff_review_issues.md:174-206`**: Per-item AskUserQuestion with 3 options
- **Existing in `audit_docs.md:118-139`**: Report already generates fix content (old/new) — this data feeds directly into the new phase

## Implementation Phases

### Phase 1: Add `--fix` Argument to Command Frontmatter and Arguments Section

#### Overview
Register the `--fix` flag in the command definition so it can be parsed.

#### Changes Required

**File**: `commands/audit_docs.md`

1. Add `fix` flag argument to frontmatter (after line 6):

```yaml
arguments:
  - name: scope
    description: Audit scope (full|readme|file:<path>)
    required: false
  - name: fix
    description: Auto-apply fixable corrections without prompting
    required: false
```

2. Add `--fix` to the Arguments section (after line 350):

```markdown
- **--fix** (optional, flag): Automatically apply all auto-fixable corrections without prompting. Skips the action selection prompt for fixable items and applies them directly. Non-fixable findings still flow to issue management.
```

3. Add `--fix` to the Examples section:

```markdown
# Auto-fix documentation issues
/ll:audit-docs --fix

# Full audit with auto-fix
/ll:audit-docs full --fix
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "fix" commands/audit_docs.md` returns multiple matches confirming the flag is referenced

### Phase 2: Insert Phase 4.5 — Finding Classification and Direct Fix

#### Overview
Add a new phase between Phase 4 (Output Report) and Phase 5 (Issue Management) that classifies findings and offers direct-fix options.

#### Changes Required

**File**: `commands/audit_docs.md`

Insert after line 140 (end of Phase 4) and before line 142 (Phase 5):

```markdown
### 4.5. Direct Fix Option

After generating the report, classify each finding and offer direct fixes for auto-fixable items.

#### Finding Classification

Classify each finding from the report:

| Category | Criteria | Examples |
|----------|----------|----------|
| **Auto-fixable** | Specific old/new content known, mechanical replacement | Wrong counts, outdated paths, broken relative links, incorrect version numbers, wrong command syntax |
| **Needs issue** | Requires investigation, writing, or design decisions | Missing sections, incomplete docs, content rewrites, new examples needed |

#### Action Selection

**If `--fix` flag is set**: Skip the prompt. Auto-apply all auto-fixable corrections and output progress:

```
Applying auto-fixes...
Fix 1/N: [description] in [file:line]... done
Fix 2/N: [description] in [file:line]... done
...
Applied: X fixes
Remaining: Y findings (need issue tracking)
```

Then proceed to Phase 5 with only the non-fixable findings.

**Otherwise**: Present findings grouped by fixability:

```markdown
## Auto-Fixable Findings (N)

These can be corrected directly:

| # | File:Line | Finding | Fix |
|---|-----------|---------|-----|
| 1 | README.md:45 | Outdated install command | `old-syntax` → `new-syntax` |
| 2 | README.md:72 | Broken relative link | `docs/guide.md` → `docs/user-guide.md` |

## Findings Needing Issues (M)

These require investigation or design:

| # | File:Line | Finding | Suggested Issue Type |
|---|-----------|---------|---------------------|
| 3 | README.md:100 | Missing example output | ENH (P4) |
| 4 | docs/api.md:30 | Incomplete API docs | ENH (P3) |
```

Use the AskUserQuestion tool with single-select:
- Question: "How would you like to handle the auto-fixable findings?"
- Header: "Doc fixes"
- Options:
  - label: "Fix all now"
    description: "Apply all N auto-fixable corrections directly to the documentation files"
  - label: "Create issues for all"
    description: "Skip direct fixes - create issues for all findings (auto-fixable and non-fixable)"
  - label: "Review each"
    description: "Decide per-finding whether to fix now, create issue, or skip"

#### Fix All Now

For each auto-fixable finding:
1. Apply the edit using the Edit tool (old_string → new_string)
2. Report: `Fixed: [description] in [file:line]`

After all fixes applied:
```bash
git add [fixed files]
```

Output:
```
Direct fixes applied: N
- [file:line]: [description]
- [file:line]: [description]

Files staged. Run `/ll:commit` to commit, or continue to create issues for remaining findings.
```

Proceed to Phase 5 with only the non-fixable findings (skip issue management entirely if no non-fixable findings remain).

#### Create Issues for All

Skip direct fixes. Proceed to Phase 5 with all findings (both auto-fixable and non-fixable).

#### Review Each

For each auto-fixable finding, use the AskUserQuestion tool with single-select:
- Question: "Finding: [description] in [file:line]. Old: `[old]` → New: `[new]`"
- Header: "[file]:[line]"
- Options:
  - label: "Fix now"
    description: "Apply this correction directly"
  - label: "Create issue"
    description: "Create an issue for this finding instead"
  - label: "Skip"
    description: "Ignore this finding"

Apply fixes for "Fix now" selections, collect "Create issue" selections for Phase 5, discard "Skip" selections.

After review:
```bash
git add [fixed files]
```

Proceed to Phase 5 with findings marked "Create issue" plus all non-fixable findings.
```

#### Success Criteria

**Automated Verification**:
- [ ] Phase 4.5 section exists in `commands/audit_docs.md`
- [ ] Three action paths documented: "Fix all now", "Create issues for all", "Review each"
- [ ] `--fix` flag handling documented in the new phase

### Phase 3: Update Phase 5-8 to Handle Reduced Finding Set

#### Overview
Modify the existing issue management phases to gracefully handle the case where some/all findings were already fixed directly.

#### Changes Required

**File**: `commands/audit_docs.md`

1. Add a note at the start of Phase 5 (Issue Management, line 142):

```markdown
### 5. Issue Management

**Note**: If findings were fixed directly in Phase 4.5, only the remaining unfixed findings are processed in this phase. If all findings were fixed directly, skip to Phase 8's summary output.

After generating the report, offer to create, update, or reopen issues for documentation problems.
```

2. Update Phase 8 summary output (around line 331) to include direct fix counts:

```markdown
5. **Output summary**:
   ```
   Audit complete:
   - Fixed directly: N findings
   - Created: N issues (N BUG, N ENH)
   - Updated: N issues
   - Reopened: N issues
   - Skipped: N findings

   Run `/ll:commit` to commit these changes.
   ```
```

3. Update the Integration section (line 369) to mention the new direct-fix flow:

```markdown
## Integration

After auditing:
1. Review the audit report
2. **Fix directly** auto-fixable issues (counts, paths, links) or create issues
3. **Manage issues** (create/update/reopen) for remaining findings with user approval
4. Use `/ll:commit` to save all changes (direct fixes + issue files)
```

#### Success Criteria

**Automated Verification**:
- [ ] Phase 5 includes note about reduced finding set
- [ ] Phase 8 summary includes "Fixed directly" count
- [ ] Integration section mentions direct-fix flow

---

## Testing Strategy

### Manual Verification
- Run `/ll:audit-docs` on README.md and verify the new Phase 4.5 prompt appears
- Test `--fix` flag to confirm auto-fixable items are applied without prompting
- Test "Review each" to confirm per-finding prompts work
- Verify "Create issues for all" still produces issues as before
- Verify findings already fixed directly are excluded from issue management

## References

- Original issue: `.issues/enhancements/P3-ENH-383-add-direct-fix-option-to-audit-docs-review.md`
- Primary file: `commands/audit_docs.md` (lines 118-139 for existing fix content, lines 311-317 for user approval)
- Pattern reference: `commands/audit_claude_config.md:390-444` (severity-tiered fix session)
- Pattern reference: `commands/tradeoff_review_issues.md:174-206` (per-item 3-option prompt)
- Pattern reference: `commands/align_issues.md:241-271` (auto-fixable distinction)
