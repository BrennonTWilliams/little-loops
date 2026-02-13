---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-395: Consolidate issue ID assignment to programmatic CLI

## Summary

5 commands and 1 skill duplicate the issue ID assignment logic as inline bash one-liners (`find .issues -name "*.md" | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | ...`) instead of using the existing, well-tested `get_next_issue_number()` Python function. This creates a drift risk — the bash versions hardcode `BUG|FEAT|ENH` prefixes while the Python version reads from config.

## Current Behavior

Issue ID assignment is implemented in two places:

1. **Python function** (`scripts/little_loops/issue_parser.py:39-75`): `get_next_issue_number()` — reads prefixes from config, scans all directories including completed, well-tested with unit tests.

2. **Inline bash in command/skill prompts**: Hardcoded `find | grep -oE "(BUG|FEAT|ENH)-[0-9]+"` pattern duplicated across:
   - `commands/capture_issue.md` (line 315)
   - `commands/scan_codebase.md` (line 180)
   - `commands/scan_product.md` (line 206)
   - `commands/find_dead_code.md` (line 248)
   - `commands/normalize_issues.md` (line 161)
   - `skills/issue-size-review/SKILL.md` (line 115)

Every issue creation — whether by a command prompt or a CLI tool — does a fresh filesystem scan. The bash versions hardcode category prefixes and can silently diverge from config.

## Expected Behavior

A single `ll-next-id` CLI entry point (or subcommand) wraps `get_next_issue_number()`, and all commands/skills call it instead of inlining bash. Adding or renaming a category prefix requires changing only one place.

## Motivation

- **Already caused a bug**: BUG-234 was the same class of problem — `sync.py` had its own `_get_next_issue_number()` that diverged from the canonical function. The fix was to consolidate to the single Python implementation.
- **Hardcoded prefixes**: The bash one-liners will silently miss issues if a new category prefix is added to config.
- **6 locations to maintain**: Any change to ID assignment logic (e.g., supporting 4+ digit IDs, new prefix) must be replicated across all 6 files manually.

## Proposed Solution

1. **Add a CLI entry point** `ll-next-id` to `scripts/little_loops/cli/` that prints the next globally unique issue number. Thin wrapper around `get_next_issue_number()`.

2. **Replace all 6 bash one-liners** in commands/skills with:
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
3. Update the 5 command files and 1 skill file to replace bash one-liners with `ll-next-id`
4. Add a test for the CLI entry point

## Impact

- **Scope**: 1 new CLI file, 6 prompt file edits, 1 pyproject.toml edit
- **Risk**: Low — existing behavior preserved, just consolidated
- **Dependencies**: None

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/API.md | Documents get_next_issue_number API |
| guidelines | CONTRIBUTING.md | CLI tool registration conventions |

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

## Session Log
- `/ll:capture_issue` - 2026-02-12 - conversation context
