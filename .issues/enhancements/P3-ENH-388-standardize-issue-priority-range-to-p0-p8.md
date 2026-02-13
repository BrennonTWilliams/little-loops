---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-388: Standardize issue priority range to P0-P8

## Summary

The project currently uses a P0-P5 priority range for issues, but this should be standardized to P0-P8 to provide finer-grained priority levels. All references to "P0-P5" across the codebase (CLAUDE.md, issue templates, skill definitions, commands, scripts, and documentation) need to be updated to reflect the new P0-P8 range.

## Context

User description: "Standardize Issue Priority range to P0-P8, not P0-P5"

## Current Behavior

Priority range is documented and enforced as P0-P5 throughout the codebase, including:
- CLAUDE.md issue file format section
- Issue template creation templates (e.g., `issue-sections.json` Impact and Status sections)
- Skill and command definitions that reference priority levels
- Python scripts that parse or validate priority levels

## Expected Behavior

All references to issue priority should use the P0-P8 range, allowing for more granular prioritization of issues across the backlog.

## Motivation

A wider priority range (P0-P8) provides more granularity for triaging and ordering work. With P0-P5, there are only 6 levels to distinguish between critical production issues and nice-to-have improvements. P0-P8 gives 9 levels, reducing the need to group dissimilar issues at the same priority.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis (grep for "P0-P5" and priority range references)

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- `scripts/tests/test_issue_id.py` — update priority validation tests for P0-P8 range
- `scripts/tests/test_issue_scanner.py` — update any priority parsing/filtering tests
- `scripts/tests/test_prioritize.py` — update priority assignment tests for expanded range

### Documentation
- `.claude/CLAUDE.md` — update "P0 (critical) to P5 (low)" to P0-P8
- `docs/ISSUE_TEMPLATE.md` — update priority references and examples
- `CONTRIBUTING.md` — update priority range references
- `docs/ARCHITECTURE.md` — update issue management priority scheme

### Configuration
- N/A or list config files

## Implementation Steps

1. Audit all references to "P0-P5" across the codebase
2. Update documentation, templates, and schema references to P0-P8
3. Update Python code that validates or parses priority levels
4. Verify no tests or scripts break with the expanded range

## Impact

- **Priority**: P3 - Standardization improvement, not blocking
- **Effort**: Medium - Many files reference the priority range
- **Risk**: Low - Expanding range is backwards-compatible with existing P0-P5 issues
- **Breaking Change**: No

## Success Metrics

- All references to priority range say P0-P8 instead of P0-P5
- Existing P0-P5 issues continue to work without modification
- New issues can be created at P6-P8 levels

## Scope Boundaries

- Out of scope: Retroactively re-prioritizing existing issues to use P6-P8
- Out of scope: Adding semantic meaning to P6-P8 levels (that can be a follow-up)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Documents current P0-P5 priority range in Issue File Format section |
| guidelines | CONTRIBUTING.md | May reference priority levels |
| architecture | docs/ARCHITECTURE.md | May reference issue management priority scheme |

## Labels

`enhancement`, `captured`

## Blocked By

- ENH-386: add command cross-reference validation to audit_claude_config (shared CONTRIBUTING.md)
- ENH-368: plugin-config-auditor missing hook event and handler types (shared docs/ARCHITECTURE.md)
- ENH-384: manage_issue --resume should invoke /ll:resume (shared CONTRIBUTING.md, docs/ARCHITECTURE.md)
- BUG-403: dependency graph renders empty nodes without edges (shared ARCHITECTURE.md)

## Blocks

- ENH-357: update CLAUDE.md date and skills count (shared CLAUDE.md)
- ENH-279: audit skill vs command allocation (shared docs/ARCHITECTURE.md)
- BUG-392: dependency validator false nonexistent cross-type references (shared ARCHITECTURE.md)

## Session Log
- `/ll:capture_issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb9342d2-9c23-4b31-8822-f890ead72957.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
