---
discovered_date: 2026-02-07
discovered_by: capture_issue
---

# ENH-272: Add Integration Analysis to Issue Management Lifecycle

## Summary

Add integration analysis checks to the issue management workflow to ensure (A) new implementation code reuses existing codebase utilities, patterns, and abstractions where appropriate rather than reinventing them, and (B) completed implementation code is properly integrated with the existing codebase architecture rather than sitting alongside it in isolation.

## Context

Identified from conversation discussing a gap in the issue management system. The current workflow has strong validation infrastructure — duplicate detection, regression checks, dependency mapping, code quality gates (lint/types/tests) — but no explicit checkpoint that asks "should this reuse existing code?" before implementation or "is this properly integrated?" after implementation.

The `codebase-pattern-finder` agent finds similar patterns during deep research (Phase 1.5 of `manage_issue`), but its mandate is "find patterns to model after," not "find code you should reuse instead of writing new." Post-implementation verification checks correctness (tests pass, types check) but not integration quality (did you use shared modules? did you introduce duplication? does it follow established abstraction boundaries?).

Without this, the risk is gradual codebase divergence: each issue solved correctly in isolation, but over time accumulating parallel implementations, missed abstractions, and code that sits *next to* the architecture rather than *within* it.

## Current Behavior

- **Deep Research (Phase 1.5)**: 3 sub-agents find files, analyze code, discover patterns — but none explicitly checks for reusable existing code
- **Planning (Phase 2)**: Plan template has no "Code Reuse & Integration" section requiring justification of new vs. reuse decisions
- **Post-Implementation (Phase 4)**: Verification checks tests/lint/types but not integration quality — no review for introduced duplication, missed shared utilities, or architectural misalignment
- **No explicit gate** requiring implementers to justify creating new code when similar functionality exists

## Expected Behavior

### A) Pre-Implementation: Reuse Discovery

During deep research or planning, explicitly identify:
- Existing utility functions, helpers, and shared modules relevant to the issue
- Similar logic elsewhere in the codebase that could be abstracted or extended
- Established patterns/conventions the implementation should follow
- A documented decision for each: reuse, extend, or justify creating new

### B) Post-Implementation: Integration Review

After implementation passes tests/lint/types but before completion:
- Check for newly introduced code duplication against existing codebase
- Verify new code imports from and integrates with shared modules where appropriate
- Confirm new code follows established project patterns and abstraction boundaries
- Flag any "parallel implementation" concerns (new utility that duplicates existing one)

## Proposed Solution

Three insertion points in the `manage_issue` workflow:

### 1. Deep Research Enhancement (Phase 1.5)

Add a 4th concern to the existing research phase — or expand the `codebase-pattern-finder` agent's mandate — to explicitly search for:
- Reusable utilities in the codebase relevant to the issue
- Existing abstractions that could be extended
- Similar implementations that suggest consolidation opportunities

### 2. Plan Template Addition (Phase 2)

Add a required section to implementation plans:

```markdown
## Code Reuse & Integration
- **Reusable existing code**: [list utilities/modules to leverage with file:line refs]
- **Patterns to follow**: [established conventions this implementation must match]
- **New code justification**: [what's genuinely new and why existing code doesn't cover it]
```

### 3. Post-Implementation Integration Review (between Phase 4 and 5)

Add a review step after verification passes:
- Scan new/modified files for potential duplication against existing codebase
- Verify imports use shared modules where they exist
- Check that new public interfaces follow established naming/structure conventions
- Produce integration report with pass/warn/fail status

## Acceptance Criteria

- [ ] Deep research phase (Phase 1.5) includes a reuse discovery step that identifies existing utilities, abstractions, and shared modules relevant to the issue
- [ ] Implementation plans (Phase 2) include a "Code Reuse & Integration" section with reuse/new justification and file:line references
- [ ] Implementation plans (Phase 2) include a "Unit and Integration Tests" section
- [ ] Post-implementation integration review (between Phase 4 and 5) runs after verification, checking for duplication and proper integration with existing codebase
- [ ] Integration review produces a structured pass/warn/fail report with actionable findings

## Success Metrics

- **Duplication detected**: Integration review catches cases of duplicated logic in test implementations
- **Reuse in plans**: Implementation plans consistently include reuse decisions with file:line references to existing code
- **Fewer parallel implementations**: Over time, reduced instances of parallel/duplicate implementations in the codebase
- **Workflow coverage**: All three insertion points (research, plan, review) are implemented and active in the manage_issue workflow

## Impact

- **Priority**: P2
- **Effort**: Medium — touches manage_issue skill, plan template, adds review step
- **Risk**: Low — purely additive, enhances existing workflow without changing it

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Defines system patterns and module boundaries |
| guidelines | CONTRIBUTING.md | Establishes code conventions and patterns |

## Relates To

- FEAT-261: Issue Dependency Mapping (completed — addresses inter-issue dependencies; this issue addresses intra-codebase integration)
- ENH-240: Consolidate Duplicated Work Verification Code (completed — was itself an example of the duplication this check would catch)

## Labels

`enhancement`, `workflow`, `code-quality`, `manage-issue`

---

## Status

**Open** | Created: 2026-02-07 | Priority: P2
