---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-395: Consolidate issue ID assignment to programmatic CLI

## Summary

3 commands and 1 skill duplicate the issue ID assignment logic as inline bash one-liners (`find .issues -name "*.md" | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | ...`), and 2 additional commands describe the same algorithm in prose — instead of using the existing, well-tested `get_next_issue_number()` Python function. This creates a drift risk — the bash versions hardcode `BUG|FEAT|ENH` prefixes while the Python version reads from config.

## Current Behavior

Issue ID assignment is implemented in two places:

1. **Python function** (`scripts/little_loops/issue_parser.py:39-75`): `get_next_issue_number()` — reads prefixes from config, scans all directories including completed, well-tested with unit tests.

2. **Inline bash in command/skill prompts** (4 locations with bash one-liners):
   - `commands/capture_issue.md` (line 315)
   - `commands/find_dead_code.md` (line 248)
   - `commands/normalize_issues.md` (lines 161-165)
   - `skills/issue-size-review/SKILL.md` (line 115)

3. **Prose instructions describing the same algorithm** (2 locations):
   - `commands/scan_codebase.md` (lines 178-182) — natural language instructions for the agent to find highest ID
   - `commands/scan_product.md` (lines 204-208) — same prose-based algorithm

Every issue creation — whether by a command prompt or a CLI tool — does a fresh filesystem scan. The bash versions hardcode category prefixes and can silently diverge from config.

## Expected Behavior

A single `ll-next-id` CLI entry point (or subcommand) wraps `get_next_issue_number()`, and all commands/skills call it instead of inlining bash. Adding or renaming a category prefix requires changing only one place.

## Motivation

- **Already caused a bug**: BUG-234 was the same class of problem — `sync.py` had its own `_get_next_issue_number()` that diverged from the canonical function. The fix was to consolidate to the single Python implementation.
- **Hardcoded prefixes**: The bash one-liners will silently miss issues if a new category prefix is added to config.
- **6 locations to maintain**: Any change to ID assignment logic (e.g., supporting 4+ digit IDs, new prefix) must be replicated across 4 bash snippets and 2 prose descriptions manually.

## Proposed Solution

1. **Add a CLI entry point** `ll-next-id` to `scripts/little_loops/cli/` that prints the next globally unique issue number. Thin wrapper around `get_next_issue_number()`.

2. **Replace all 6 inline ID-assignment snippets/instructions** in commands/skills with:
   ```bash
   ll-next-id
   ```

3. **Register the entry point** in `pyproject.toml` alongside other `ll-*` tools.

### Anchor

- `in function get_next_issue_number` at `scripts/little_loops/issue_parser.py`
- `in pyproject.toml` console_scripts section

## Implementation Steps

1. Create `scripts/little_loops/cli/next_id.py` with a `main()` that loads config and calls `get_next_issue_number()`
2. Register `ll-next-id` entry point in `pyproject.toml`
3. Update the 4 command/skill files with bash one-liners to use `ll-next-id`
4. Update the 2 command files with prose instructions to reference `ll-next-id`
5. Add a test for the CLI entry point

## Scope Boundaries

- **In scope**: New `ll-next-id` CLI entry point, replacing bash one-liners in 4 files, updating prose instructions in 2 files to reference the CLI tool
- **Out of scope**: Changing the `get_next_issue_number()` algorithm itself, adding new ID formats, modifying the existing Python function signature

## Impact

- **Priority**: P3 - Reduces maintenance burden and drift risk, but current behavior works correctly in most cases
- **Effort**: Small - Thin CLI wrapper around existing function, mechanical find-and-replace in prompt files
- **Risk**: Low — existing behavior preserved, just consolidated; `get_next_issue_number()` is already well-tested
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/API.md | Documents get_next_issue_number API |
| guidelines | CONTRIBUTING.md | CLI tool registration conventions |

## Labels

`enhancement`, `maintenance`, `cli`

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/next_id.py`: Created `main_next_id()` CLI entry point wrapping `get_next_issue_number()`
- `scripts/little_loops/cli/__init__.py`: Added `main_next_id` to re-exports
- `scripts/pyproject.toml`: Registered `ll-next-id` console script
- `commands/capture_issue.md`: Replaced inline bash with `ll-next-id`
- `commands/find_dead_code.md`: Replaced inline bash with `ll-next-id`
- `commands/normalize_issues.md`: Replaced inline bash with `ll-next-id`
- `skills/issue-size-review/SKILL.md`: Replaced inline bash with `ll-next-id`
- `commands/scan_codebase.md`: Replaced prose instructions with `ll-next-id`
- `commands/scan_product.md`: Replaced prose instructions with `ll-next-id`
- `scripts/tests/test_cli_next_id.py`: Added unit and integration tests

### Verification Results
- Tests: PASS (2716 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS (ll-next-id returns 396 correctly)

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-02-12 - conversation context
- `/ll:manage-issue` - 2026-02-12T18:00:00Z - implementation session
