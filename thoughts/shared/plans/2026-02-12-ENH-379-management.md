# ENH-379: Rename refine_issue to format_issue - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-379-rename-refine-issue-to-format-issue.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The `/ll:refine_issue` command exists at `commands/refine_issue.md` and is registered via directory convention (plugin.json reads all `.md` files from `./commands`). The command is referenced in 12 active files with ~42 total occurrences.

### Key Discoveries
- Commands registered by directory convention — renaming file is sufficient for plugin registration
- No hooks, agents, or Python source code reference `refine_issue`
- FEAT-380 explicitly depends on this rename to free the `refine_issue` name
- `--template-align-only` flag at lines 8, 35, 47, 59, 194, 258, 260, 586, 684 should be removed
- `commands/ready_issue.md`, `commands/capture_issue.md`, `commands/manage_issue.md` do NOT reference `refine_issue` (contrary to issue file claims)

## Desired End State

- `commands/format_issue.md` exists with all self-references updated
- `commands/refine_issue.md` no longer exists
- `--template-align-only` flag removed from the command
- All active docs, tests, and config reference `format_issue`
- `grep -r 'refine_issue' .` returns 0 hits outside `.issues/completed/`, `.git/`, `thoughts/`, `CHANGELOG.md`, and FEAT-380

## What We're NOT Doing

- Not changing command behavior/logic
- Not modifying completed issues, historical plans, or CHANGELOG.md
- Not modifying FEAT-380 (it correctly references the rename)
- Not adding deprecation aliases

## Implementation Phases

### Phase 1: Rename command file and update internal content
1. `git mv commands/refine_issue.md commands/format_issue.md`
2. Update frontmatter description
3. Update title, usage strings, examples, integration workflows
4. Remove `--template-align-only` flag and all its references

### Phase 2: Update all cross-references
1. `.claude/CLAUDE.md` — command listing (line 52)
2. `commands/help.md` — detailed listing (lines 53-54) and quick reference (line 186)
3. `templates/issue-sections.json` — `_meta.description` (line 4)
4. `skills/issue-workflow/SKILL.md` — workflow reference (line 71)
5. `README.md` — command table (line 110)
6. `docs/COMMANDS.md` — section header, table, workflow (lines 60-69, 278, 321)
7. `docs/ISSUE_TEMPLATE.md` — 4 inline references (lines 526, 533, 841, 853)
8. `CONTRIBUTING.md` — example (line 298)
9. `scripts/tests/test_session_log.py` — test strings (lines 86, 92, 112, 117)
10. `IMPLEMENTATION_SUMMARY.md` — 6 references
11. `affected-components-proposal.md` — 1 reference (line 247)

### Phase 3: Verify
- Run tests
- Run grep to confirm no stray references
- Run lint

## Testing Strategy
- Run `python -m pytest scripts/tests/test_session_log.py` to confirm test updates work
- Run full test suite
- Grep verification for stray references
