---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-335: Organize docs with command and skill groupings

## Summary

Update README and related project docs to organize CLI commands, slash commands, and skills under logical capability groupings instead of flat lists. This makes the project's features and capabilities clearer and easier to understand for new and existing users.

## Current Behavior

Commands, skills, and CLI tools are listed in flat tables or alphabetical order across README and docs, making it hard to understand what capabilities exist for a given workflow (e.g., "what tools help me with issues?").

## Expected Behavior

All commands, skills, and CLI tools are organized under these groupings:

1. **Issue Discovery** - capture_issue, audit_architecture + skills: issue-workflow, issue-size-review, map-dependencies
2. **Issue Refinement** - normalize_issues, prioritize_issues, align_issues, refine_issue, verify_issues, tradeoff_review_issues, ready_issue + skills: issue-size-review, map-dependencies
3. **Planning & Implementation** - create_sprint, manage_issue + CLI: ll-auto, ll-parallel, ll-sprint
4. **Scanning & Discovery** - scan_codebase, scan_product, find_dead_code + skills: product-analyzer
5. **Code Quality** - check_code, run_tests, audit_docs
6. **Git & Release** - commit, open_pr, describe_pr, manage_release, sync_issues, cleanup_worktrees + CLI: ll-sync
7. **Automation & Loops** - create_loop, loop-suggester + skills: workflow-automation-proposer + CLI: ll-loop
8. **Meta-Analysis** - audit_claude_config, analyze-workflows + skills: analyze-history + CLI: ll-history, ll-workflows
9. **Session & Config** - init, configure, handoff, resume, help, toggle_autoprompt

## Motivation

The project has grown to 30+ commands, skills, and CLI tools. Without logical grouping, users struggle to discover relevant capabilities and understand the overall workflow. Grouping by function makes the project more approachable and self-documenting.

## Proposed Solution

TBD - requires investigation of which docs need updates. Likely targets:
- `README.md` - main command/skill tables
- `docs/ARCHITECTURE.md` - system design sections
- `.claude/CLAUDE.md` - project instructions
- `/ll:help` skill output

## Integration Map

### Files to Modify
- `README.md`
- `docs/ARCHITECTURE.md`
- `.claude/CLAUDE.md`
- `commands/help.md` (`/ll:help` command definition)

### Dependent Files (Callers/Importers)
- N/A (documentation-only change)

### Similar Patterns
- N/A

### Tests
- N/A (documentation-only change)

### Documentation
- This IS the documentation change

### Configuration
- N/A

## Scope Boundaries

- Out of scope: Changing command/skill names, moving files, or altering any code behavior
- Out of scope: Creating new documentation files — only updating existing ones
- Out of scope: Changing the `/ll:help` command logic itself (only its output text)

## Implementation Steps

1. Audit all docs that list commands/skills/CLI tools
2. Reorganize each doc's listings under the 9 groupings above
3. Ensure consistency across all docs
4. Verify no commands/skills/CLI tools are missing from groupings

## Impact

- **Priority**: P3 - Improves usability but not blocking
- **Effort**: Medium - Multiple docs to update consistently
- **Risk**: Low - Documentation-only, no code changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Lists commands and skills |
| project | README.md | Primary user-facing doc |

## Labels

`enhancement`, `documentation`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
