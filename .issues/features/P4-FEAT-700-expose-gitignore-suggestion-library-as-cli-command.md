---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-700: Expose gitignore suggestion library as CLI command

## Summary

`git_operations.py` contains a complete, tested gitignore suggestion subsystem (`GitignorePattern`, `GitignoreSuggestion`, `suggest_gitignore_patterns`, `add_patterns_to_gitignore`) with 30+ pre-defined patterns across 10 categories. This functionality is fully tested but has no CLI entry point — it exists only as a library.

## Location

- **File**: `scripts/little_loops/git_operations.py`
- **Line(s)**: 86-340 (at scan commit: 3e9beea)
- **Anchor**: Classes `GitignorePattern`, `GitignoreSuggestion`; functions `suggest_gitignore_patterns`, `add_patterns_to_gitignore`

## Current Behavior

The gitignore suggestion API is a library-only feature. No CLI command exposes it. Users cannot run it from the command line.

## Expected Behavior

A new CLI command (e.g., `ll-issues gitignore` or a standalone `ll-gitignore`) that scans for untracked files, suggests `.gitignore` patterns, and optionally applies them.

## Use Case

A developer runs `ll-gitignore` after adding new build tools or dependencies. The command identifies untracked files matching common patterns (coverage reports, `.env` files, editor configs) and offers to add them to `.gitignore`.

## Acceptance Criteria

- [ ] CLI command runs `suggest_gitignore_patterns()` on the repo root
- [ ] Displays categorized suggestions with file counts
- [ ] Accepts user confirmation before modifying `.gitignore`
- [ ] Supports `--dry-run` flag to preview without modifying

## Impact

- **Priority**: P4 - Nice-to-have CLI convenience, library already exists
- **Effort**: Small - Library and tests already exist, just needs CLI wiring
- **Risk**: Low - Reusing tested code
- **Breaking Change**: No

## Labels

`feature`, `cli`, `gitignore`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
