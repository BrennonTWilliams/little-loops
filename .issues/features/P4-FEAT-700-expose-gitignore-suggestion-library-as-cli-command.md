---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-700: Expose gitignore suggestion library as CLI command

## Summary

`git_operations.py` contains a complete, tested gitignore suggestion subsystem

## Motivation

A fully-featured gitignore suggestion library exists with 30+ patterns across 10 categories, with tests — but it is invisible to users because there is no CLI entry point. Exposing it as a command makes this existing investment immediately useful for day-to-day developer setup. (`GitignorePattern`, `GitignoreSuggestion`, `suggest_gitignore_patterns`, `add_patterns_to_gitignore`) with 30+ pre-defined patterns across 10 categories. This functionality is fully tested but has no CLI entry point — it exists only as a library.

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

## Proposed Solution

Add an `ll-gitignore` entry point in `scripts/pyproject.toml` that calls a new `cmd_gitignore` function. The function calls `suggest_gitignore_patterns()`, presents categorized suggestions, prompts for confirmation (or skips with `--dry-run`), then calls `add_patterns_to_gitignore()` on approved patterns.

## Acceptance Criteria

- [ ] CLI command runs `suggest_gitignore_patterns()` on the repo root
- [ ] Displays categorized suggestions with file counts
- [ ] Accepts user confirmation before modifying `.gitignore`
- [ ] Supports `--dry-run` flag to preview without modifying

## Implementation Steps

1. Create `scripts/little_loops/cli/gitignore_cmd.py` with `cmd_gitignore(args)` calling `suggest_gitignore_patterns()` and `add_patterns_to_gitignore()`
2. Add `--dry-run` argument to the argparse parser
3. Add `ll-gitignore = "little_loops.cli.gitignore_cmd:main"` to `scripts/pyproject.toml` entry points
4. Wire confirmation prompt before applying patterns
5. Add tests in `scripts/tests/test_gitignore_cmd.py`

## Integration Map

- **New file**: `scripts/little_loops/cli/gitignore_cmd.py` — `cmd_gitignore()` entry point
- **Library used**: `scripts/little_loops/git_operations.py` — `suggest_gitignore_patterns()` (line 86+), `add_patterns_to_gitignore()` (line ~300+)
- **Config**: `scripts/pyproject.toml` — new `ll-gitignore` entry point

## Impact

- **Priority**: P4 - Nice-to-have CLI convenience, library already exists
- **Effort**: Small - Library and tests already exist, just needs CLI wiring
- **Risk**: Low - Reusing tested code
- **Breaking Change**: No

## Labels

`feature`, `cli`, `gitignore`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
