---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# FEAT-174: Automatic sprint grouping in create_sprint command

## Summary

Add automatic sprint grouping to `/ll:create-sprint` that analyzes active issues and suggests natural sprint cohorts based on priority, category, dependencies, or theme patterns.

## Context

**Conversation mode**: Identified from conversation discussing: "Does our `/ll:create-sprint` command (or skill?) accept an optional title or description of the sprint that determines what Issue files to include?"

User asked if the command automatically identifies sprint groupings from existing Active Issues. The current implementation only offers interactive selection when `--issues` is omitted — it doesn't proactively suggest sprint groupings.

## Current Behavior

When `/ll:create-sprint` is run without the `--issues` argument:
- Requires a sprint name upfront (no auto-suggestion)
- Offers interactive selection: "Select from active issues", "Enter manually", "Select by priority"
- Does not analyze or suggest natural groupings

## Expected Behavior

When `/ll:create-sprint` is run without arguments:
1. Analyze all active issues
2. Identify patterns and suggest 2-3 sprint groupings:
   - By priority: "All P0-P1 critical issues", "All P2 bugs"
   - By category: "All active features", "All bug fixes"
   - By dependencies: "Issues that can be done in parallel (no blocking)"
   - By theme: "Performance-related issues", "Security fixes"
3. Present suggested sprint names and issue lists for user approval

### Example Output

```markdown
## Suggested Sprint Groupings

Based on 23 active issues, here are natural groupings:

### Option 1: critical-fixes (4 issues)
All P0-P1 bugs and blocking issues
- BUG-001: Login fails on Safari
- BUG-015: Data loss on logout
- FEAT-040: FSM schema validation

### Option 2: q1-features (6 issues)
All active feature work
- FEAT-041: Paradigm compilers
- FEAT-042: Variable interpolation
- FEAT-043: Deterministic evaluators
- FEAT-044: LLM evaluator
- FEAT-045: FSM executor
- FEAT-047: ll-loop CLI

### Option 3: test-coverage (8 issues)
All test coverage enhancements
- ENH-004: Orchestrator test coverage
- ENH-146: Work verification test coverage
- ENH-147: Lifecycle test coverage
- ENH-053: Loop integration tests
...
```

## Proposed Solution

1. **Analyze active issues**: Read all issues from active categories (bugs/, features/, enhancements/)
2. **Group by dimensions**:
   - Priority clusters (P0-P1, P2, P3-P5)
   - Type clusters (bugs, features, enhancements)
   - Dependency graph (parallelizable groups)
   - Keyword/theme analysis (e.g., "test", "performance", "security")
3. **Generate sprint names**: Auto-generate names like `critical-fixes`, `q1-features`, `test-coverage`
4. **Present options**: Use AskUserQuestion to let user select a suggested grouping
5. **Create sprint**: Proceed with selected grouping

### Implementation Notes

- Use existing dependency graph from FEAT-030 (issue-dependency-parsing-and-graph)
- Simple keyword matching for theme detection (words in title/summary)
- Keep suggestions limited to top 3-4 most distinct groupings

## Impact

- **Priority**: P3
- **Effort**: Medium - requires issue analysis and clustering logic
- **Risk**: Low - enhancement to existing command

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Mentions sprint and issue management systems |
| guidelines | .claude/CLAUDE.md | Workflow automation goals |

## Labels

`feature`, `sprint`, `automation`, `enhancement`

---

## Status

**Open** | Created: 2026-01-28 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-28
- **Status**: Completed

### Changes Made
- `commands/create_sprint.md`: Added Section 1.5 "Suggest Sprint Groupings (Optional)" with three sub-steps:
  - Step 1.5.1: Scan Active Issues - Glob patterns to find and parse issues
  - Step 1.5.2: Generate Grouping Suggestions - Four strategies (priority, type, parallelizable, theme)
  - Step 1.5.3: Present Suggestions - AskUserQuestion with grouping options
- `commands/create_sprint.md`: Updated Step 2 to check if issues were pre-filled from grouping selection

### Verification Results
- Types: PASS
- Lint: Pre-existing unrelated error in test file (not touched)
