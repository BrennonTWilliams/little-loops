# ENH-272: Add Integration Analysis to Issue Management Lifecycle - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-272-add-integration-analysis-to-issue-management.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `manage_issue` command (`commands/manage_issue.md`) orchestrates a 5-phase lifecycle:
- **Phase 1**: Find issue file
- **Phase 1.5**: Deep research (3 parallel sub-agents: codebase-locator, codebase-analyzer, codebase-pattern-finder)
- **Phase 2**: Create implementation plan using inline template
- **Phase 3**: Implement
- **Phase 4**: Verify (tests, lint, types)
- **Phase 5**: Complete (update issue, move to completed, commit)

### Key Discoveries
- Phase 1.5 spawns 3 agents at `commands/manage_issue.md:95-133` — none has an explicit "find reusable code" mandate
- Plan template at `commands/manage_issue.md:194-292` has no "Code Reuse & Integration" section
- Phase 4 at `commands/manage_issue.md:457-475` runs tests/lint/types only — flows directly to Phase 5 at line 479 with no integration review
- Research synthesis template at `commands/manage_issue.md:139-160` has no "Reusable Code" subsection
- Existing patterns: `capture_issue.md` has Jaccard-based duplicate detection, `scan_codebase.md` deduplicates findings, `ready_issue.md` produces structured validation tables

## Desired End State

Three new integration analysis touchpoints in `commands/manage_issue.md`:

1. **Phase 1.5**: A 4th research concern (reuse discovery) added to the existing pattern-finder prompt, plus a new "Reusable Code" subsection in the research synthesis template
2. **Phase 2**: A new "Code Reuse & Integration" section in the plan template requiring explicit reuse/new justification with file:line references
3. **Phase 4.5**: A new integration review step between Phase 4 (Verify) and Phase 5 (Complete) that checks for duplication and proper integration

### How to Verify
- Read `commands/manage_issue.md` and confirm all three insertion points exist
- Run `/ll:manage_issue enhancement plan ENH-XXX --plan-only` and verify the plan template includes the new section
- Run tests, lint, and types to confirm no regressions

## What We're NOT Doing

- Not creating a new sub-agent — expanding the existing `codebase-pattern-finder` prompt instead
- Not modifying agent definition files (`agents/codebase-pattern-finder.md`) — changes are only to the manage_issue command's inline prompts
- Not adding Python code or new scripts — this is entirely a command template change
- Not changing the config schema — no new configuration options needed
- Not touching the `config-schema.json` workflow settings

## Problem Analysis

The manage_issue workflow has strong correctness checks (tests, lint, types) but no integration quality checks. The `codebase-pattern-finder` agent finds patterns "to model after" but not "to reuse instead of writing new." Post-implementation verification confirms code compiles and passes tests but not that it properly integrates with existing architecture.

## Solution Approach

Make three focused edits to `commands/manage_issue.md`:

1. **Expand the codebase-pattern-finder prompt** (Phase 1.5) to add reuse discovery as a 4th search concern
2. **Add a "Reusable Code" subsection** to the research synthesis template
3. **Add "Code Reuse & Integration" section** to the plan template (Phase 2)
4. **Insert Phase 4.5: Integration Review** between Phase 4 and Phase 5

All changes are additive to the existing markdown template — no structural reorganization needed.

## Implementation Phases

### Phase 1: Expand Deep Research for Reuse Discovery

#### Overview
Expand the `codebase-pattern-finder` prompt in Phase 1.5 to explicitly search for reusable existing code, and add a "Reusable Code" subsection to the research synthesis template.

#### Changes Required

**File**: `commands/manage_issue.md`
**Changes**:
1. Add reuse-focused search items to the codebase-pattern-finder prompt (lines 123-133)
2. Add "Reusable Code" subsection to the research synthesis template (lines 139-160)

**Edit 1**: Expand codebase-pattern-finder prompt at line 123-133:

```markdown
3. **codebase-pattern-finder** - Find similar patterns and reusable code
   ```
   Find similar implementations for [ISSUE-ID]: [issue title]

   Search for:
   - Similar fixes/features in the codebase
   - Established conventions for this type of change
   - Test patterns to model after
   - Existing utility functions, helpers, and shared modules that could be reused or extended instead of writing new code
   - Similar logic elsewhere that suggests consolidation rather than duplication

   Return examples with file:line references. For reusable code, explicitly note whether to reuse as-is, extend, or justify creating new.
   ```
```

**Edit 2**: Add "Reusable Code" subsection to research synthesis template after "Patterns to Follow":

```markdown
### Reusable Code
- [Utility/module at file:line — reuse as-is / extend / justify new]
- [Shared abstraction at file:line — how it applies]
```

#### Success Criteria

**Automated Verification**:
- [ ] No syntax/formatting errors in `commands/manage_issue.md`

**Manual Verification**:
- [ ] The codebase-pattern-finder prompt now includes reuse-focused search items
- [ ] The research synthesis template includes a "Reusable Code" subsection

---

### Phase 2: Add Code Reuse & Integration Section to Plan Template

#### Overview
Add a required "Code Reuse & Integration" section to the plan template in Phase 2, between "Solution Approach" and "Implementation Phases".

#### Changes Required

**File**: `commands/manage_issue.md`
**Changes**: Insert new section in plan template after "Solution Approach" (line 233) and before "Implementation Phases" (line 235)

```markdown
## Code Reuse & Integration

- **Reusable existing code**: [list utilities/modules to leverage with file:line refs]
- **Patterns to follow**: [established conventions this implementation must match]
- **New code justification**: [what's genuinely new and why existing code doesn't cover it]
```

#### Success Criteria

**Automated Verification**:
- [ ] No syntax/formatting errors in `commands/manage_issue.md`

**Manual Verification**:
- [ ] Plan template includes "Code Reuse & Integration" between "Solution Approach" and "Implementation Phases"

---

### Phase 3: Insert Post-Implementation Integration Review (Phase 4.5)

#### Overview
Add a new "Phase 4.5: Integration Review" between Phase 4 (Verify) and Phase 5 (Complete). This step checks for duplication and proper integration after tests/lint/types pass.

#### Changes Required

**File**: `commands/manage_issue.md`
**Changes**: Insert new section between line 477 ("---" after Phase 4) and line 479 ("## Phase 5")

```markdown
## Phase 4.5: Integration Review

After verification passes, review new/modified code for integration quality before completing the issue.

**Skip this phase if**:
- Action is `verify` (verification-only mode)

### Review Checklist

For each file created or substantially modified during implementation:

1. **Duplication check**: Search for similar logic elsewhere in the codebase. Flag any new code that duplicates existing utility functions, helpers, or shared modules.
2. **Shared module usage**: Verify that new code imports from and uses existing shared modules where appropriate, rather than reimplementing equivalent functionality.
3. **Pattern conformance**: Confirm new code follows established project patterns for naming, structure, error handling, and abstraction boundaries.
4. **Integration points**: Verify new code connects to existing architecture (uses existing config, follows existing data flow patterns) rather than creating parallel pathways.

### Integration Report

Produce a structured report:

```
INTEGRATION REVIEW: [ISSUE-ID]

| Check              | Status | Details                                    |
|--------------------|--------|--------------------------------------------|
| Duplication        | PASS/WARN | [Details or "No duplication detected"]  |
| Shared module use  | PASS/WARN | [Details or "Properly uses shared code"] |
| Pattern conformance| PASS/WARN | [Details or "Follows project patterns"]  |
| Integration points | PASS/WARN | [Details or "Well-integrated"]           |

Overall: PASS / WARN (with actionable findings)
```

### Handling Warnings

- **PASS**: Proceed to Phase 5
- **WARN**: Document findings in the plan file's iteration log. If warnings are minor (naming differences, style preferences), proceed. If warnings indicate significant duplication or missed reuse opportunities, fix before proceeding.
```

Also update the Final Report template to include integration review status in the VERIFICATION section.

#### Success Criteria

**Automated Verification**:
- [ ] No syntax/formatting errors in `commands/manage_issue.md`
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Phase 4.5 exists between Phase 4 and Phase 5 in the command
- [ ] Integration report format is structured and actionable
- [ ] Final report includes integration review status

## Testing Strategy

### Unit Tests
- No Python code changes, so no new unit tests needed
- Existing tests should continue to pass (the change is to a markdown command template)

### Integration Tests
- Verify the template renders correctly by running `/ll:manage_issue enhancement plan ENH-XXX --plan-only` on a test issue

## Code Reuse & Integration

- **Reusable existing code**: No Python utilities to reuse — this is a pure markdown template change
- **Patterns to follow**:
  - Research agent prompt structure at `commands/manage_issue.md:99-133` — follow same format for expanded prompt
  - Plan template section structure at `commands/manage_issue.md:194-292` — follow same `##` level heading pattern
  - Structured report format from `commands/check_code.md:137-155` and `commands/ready_issue.md:274-285` — follow table-based reporting pattern
- **New code justification**: All changes are additive markdown template sections — no new abstractions or utilities needed

## References

- Original issue: `.issues/enhancements/P2-ENH-272-add-integration-analysis-to-issue-management.md`
- manage_issue command: `commands/manage_issue.md`
- Pattern-finder agent: `agents/codebase-pattern-finder.md`
- check_code report format: `commands/check_code.md:137-155`
- ready_issue validation table: `commands/ready_issue.md:274-285`
