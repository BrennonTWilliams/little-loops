---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
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

- [x] CLI command runs `suggest_gitignore_patterns()` on the repo root
- [x] Displays categorized suggestions with file counts
- [x] Accepts user confirmation before modifying `.gitignore` (implemented as `--dry-run` per codebase convention)
- [x] Supports `--dry-run` flag to preview without modifying

## Implementation Steps

1. Create `scripts/little_loops/cli/gitignore.py` with `main_gitignore() -> int` following the pattern in `scripts/little_loops/cli/auto.py:15-83` — use `argparse.ArgumentParser(prog="ll-gitignore", ...)` with `add_dry_run_arg(parser)` from `scripts/little_loops/cli_args.py:14`
2. Call `suggest_gitignore_patterns()` (`git_operations.py:355`) to get a `GitignoreSuggestion`; print categorized results grouped by `pattern.category`; call `add_patterns_to_gitignore()` (`git_operations.py:441`) unless `--dry-run`
3. Add `from little_loops.cli.gitignore import main_gitignore` to `scripts/little_loops/cli/__init__.py` (following the import pattern at `__init__.py:18-32`)
4. Add `ll-gitignore = "little_loops.cli:main_gitignore"` to `scripts/pyproject.toml` under `[project.scripts]` (lines 47-60)
5. Add tests in `scripts/tests/test_gitignore_cmd.py` using `patch("sys.argv", ["ll-gitignore", ...])` + mock `suggest_gitignore_patterns` (see pattern in `scripts/tests/test_cli_sync.py:22-142`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Naming convention correction**: The codebase convention (all 12 existing commands) is `cli/<name>.py` with `main_<name>() -> int`. The issue originally proposed `gitignore_cmd.py`/`cmd_gitignore(args)` — the correct names are `gitignore.py` and `main_gitignore()`.

**No interactive confirmation prompt pattern exists** in any CLI command. The codebase exclusively uses `--dry-run` for destructive operation preview. The "accepts user confirmation" acceptance criterion should be implemented as `--dry-run` only (consistent with `ll-sync`, `ll-auto`, etc.). See `cli_args.py:14` for the shared `add_dry_run_arg()` helper and `cli/sync.py:116-117` for the `[DRY RUN]` log prefix pattern.

**Library function signatures** (from `git_operations.py`):
- `suggest_gitignore_patterns(untracked_files: list[str] | None = None, repo_root: Path | str = ".", logger: Logger | None = None) -> GitignoreSuggestion` (line 355)
- `add_patterns_to_gitignore(patterns: list[str], repo_root: Path | str = ".", logger: Logger | None = None, backup: bool = True) -> bool` (line 441)
- `GitignoreSuggestion.patterns: list[GitignorePattern]`, `.has_suggestions: bool`, `.summary: str` (line 121)
- `GitignorePattern.pattern: str`, `.category: str`, `.description: str`, `.files_matched: list[str]` (line 86)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.gitignore import main_gitignore` and add to `__all__`
- `scripts/pyproject.toml:47-60` — add `ll-gitignore = "little_loops.cli:main_gitignore"` under `[project.scripts]`

### New Files
- `scripts/little_loops/cli/gitignore.py` — `main_gitignore() -> int` entry point
- `scripts/tests/test_gitignore_cmd.py` — CLI tests

### Library Used (existing, no changes needed)
- `scripts/little_loops/git_operations.py:355` — `suggest_gitignore_patterns()`
- `scripts/little_loops/git_operations.py:441` — `add_patterns_to_gitignore()`
- `scripts/little_loops/cli_args.py:14` — `add_dry_run_arg()` shared helper

### Reference Patterns
- `scripts/little_loops/cli/auto.py:15-83` — structural template for `main_*()` function
- `scripts/little_loops/cli/sync.py:116-117` — `[DRY RUN]` log prefix pattern
- `scripts/tests/test_cli_sync.py:22-142` — `patch("sys.argv", ...)` + mock manager test pattern
- `scripts/tests/test_gitignore_suggestions.py` — existing library tests (no CLI tests yet)

## Impact

- **Priority**: P4 - Nice-to-have CLI convenience, library already exists
- **Effort**: Small - Library and tests already exist, just needs CLI wiring
- **Risk**: Low - Reusing tested code
- **Breaking Change**: No

## Labels

`feature`, `cli`, `gitignore`

## Session Log
- `/ll:ready-issue` - 2026-03-17T00:24:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d5f50f8-5dc0-463b-a7bd-4a42a1d5d9ab.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a861ad7-7c18-4f5c-a573-f74f2666d6d0.jsonl`
- `/ll:refine-issue` - 2026-03-16T23:40:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c37a65c3-7517-4674-9a0e-89b6d6a8bc27.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Completed** | Created: 2026-03-13 | Resolved: 2026-03-16 | Priority: P4

## Resolution

- **Status**: COMPLETED
- **Implementation**: Added `scripts/little_loops/cli/gitignore.py` (`main_gitignore() -> int`), registered in `scripts/little_loops/cli/__init__.py` and `scripts/pyproject.toml` as `ll-gitignore`
- **Tests**: `scripts/tests/test_gitignore_cmd.py` (8 tests, all passing)
- **Notes**: Interactive confirmation replaced with `--dry-run` flag per codebase convention (no interactive prompts exist in any CLI command)

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/git_operations.py` lines 87+ confirm `GitignorePattern`, `GitignoreSuggestion` (line 122), and `suggest_gitignore_patterns` (line 355) exist. No `scripts/little_loops/cli/gitignore_cmd.py` exists and no `ll-gitignore` entry point in `pyproject.toml`. Feature not yet implemented.
