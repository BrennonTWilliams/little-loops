---
discovered_date: 2026-02-13
discovered_by: capture_issue
---

# ENH-407: Add theme-based sprint grouping options to create_sprint

## Summary

Enhance `/ll:create-sprint` to offer traditional sprint-style grouping options that organize issues by themes or focus areas (e.g., "performance", "developer experience", "documentation"), in addition to the existing `parallel-ready` and issue type options.

## Current Behavior

When `/ll:create-sprint` is run with no argument, the user is presented with:
- A `parallel-ready` option (group by parallelizability)
- An Issue Type option (e.g., "enhancements", "bugs", "features")

These are useful but purely mechanical groupings. There is no option to create a sprint organized around a **theme** or **focus area** — the way traditional sprints are typically scoped (e.g., "Sprint: API Reliability", "Sprint: CLI Polish", "Sprint: Test Coverage").

## Expected Behavior

When `/ll:create-sprint` is run with no argument, in addition to current options, suggest theme-based sprint groupings such as:

1. **Keyword/topic clusters** - Analyze issue titles and summaries to detect natural themes (e.g., "performance", "testing", "CLI tools", "documentation", "sprint system")
2. **Component-based groupings** - Group issues by which part of the codebase they touch (e.g., "hooks system", "issue management", "sprint tooling")
3. **Goal-aligned sprints** - If `ll-goals.md` exists, align groupings to product goals

### Example Output

```
## Suggested Sprint Groupings

### Theme-Based
1. "cli-polish" (5 issues) - CLI tool improvements and flag standardization
   - ENH-387, ENH-276, ENH-346, ...
2. "config-cleanup" (4 issues) - Configuration and manifest fixes
   - ENH-374, ENH-370, ENH-377, ...
3. "sprint-improvements" (3 issues) - Sprint system enhancements
   - ENH-308, ENH-396, ...

### Existing Options
4. "parallel-ready" (12 issues) - All issues safe to run in parallel
5. "enhancements" (30 issues) - All active enhancements
```

## Motivation

Traditional sprints are typically organized around themes or goals — "this sprint we focus on reliability" or "this sprint is about developer experience." The current create_sprint options are mechanical (by type, by parallelizability) which works well for automated processing but doesn't support intentional, focused sprint planning. Adding theme-based options bridges the gap between automated issue processing and thoughtful sprint planning.

## Scope Boundaries

- **Out of scope**: Replacing the existing grouping strategies (priority, type, parallel-ready) — this is additive only
- **Out of scope**: Auto-creating sprints without user confirmation — all groupings remain suggestions
- **Out of scope**: ML/NLP-based clustering — use simple keyword and file-path matching

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- `commands/create_sprint.md` — Section 1.5.2 "Generate Grouping Suggestions", specifically Grouping Strategy 4 (Theme Cluster) and potentially new strategies

### Dependent Files (Callers/Importers)
- `skills/create_sprint.md` — skill wrapper that invokes the command
- No Python code changes expected (grouping logic lives in the command prompt)

### Similar Patterns
- FEAT-174 added the grouping framework (Step 1.5); this extends Strategy 4 with richer clustering and adds component-based/goal-aligned strategies

### Tests
- N/A — command is a Claude Code prompt, not Python code

### Documentation
- N/A — command is self-documenting

### Configuration
- Optional: `ll-goals.md` for goal-aligned grouping (Strategy 3)

## Implementation Steps

1. Analyze the current create_sprint grouping logic (added by FEAT-174)
2. Add keyword/topic clustering from issue titles and summaries
3. Add component-based grouping by analyzing file paths in issues
4. Optionally integrate with `ll-goals.md` for goal-aligned suggestions
5. Present theme groupings alongside existing options in AskUserQuestion
6. Verify with test sprint creation

## Impact

- **Priority**: P3 - Useful workflow improvement, not blocking
- **Effort**: Medium - Requires text clustering logic and integration with existing grouping framework
- **Risk**: Low - Additive enhancement to existing command
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system design |
| guidelines | .claude/CLAUDE.md | Sprint commands and workflow |

## Labels

`enhancement`, `sprint`, `captured`

## Resolution

- **Action**: implement
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `commands/create_sprint.md`: Extended Step 1.5.1 to extract Summary, File Paths, and Goal Alignment from issue content
- `commands/create_sprint.md`: Expanded Strategy 4 (Theme Cluster) with 9 keyword themes, title+summary matching, and multi-cluster output
- `commands/create_sprint.md`: Added Strategy 5 (Component Cluster) for directory-based issue grouping
- `commands/create_sprint.md`: Added Strategy 6 (Goal-Aligned) for product goal-based grouping with graceful skip
- `commands/create_sprint.md`: Updated Scoring & Selection to prefer a mix of mechanical + theme-based groupings (up to 4)
- `commands/create_sprint.md`: Updated example output to show theme-based groupings

### Verification Results
- Tests: PASS (2728 passed)
- Lint: PASS

## Session Log
- `/ll:capture-issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc5517c3-2785-4593-a080-7f98d0e59836.jsonl`
- `/ll:manage-issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ea9ac4f-8c05-4d6f-98c3-8e1abe0a4fd8.jsonl`

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P3
