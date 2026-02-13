# ENH-395: Consolidate issue ID assignment to programmatic CLI - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-395-consolidate-issue-id-assignment-to-programmatic-cli.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

Issue ID assignment is duplicated in 6 locations beyond the canonical Python function:
- 4 bash one-liners with hardcoded `(BUG|FEAT|ENH)` prefixes
- 2 prose descriptions of the same algorithm
- All bypass the config-driven `get_next_issue_number()` at `issue_parser.py:39-75`

### Key Discoveries
- `get_next_issue_number()` reads prefixes dynamically from config (`issue_parser.py:56`)
- Bash variants hardcode prefixes, creating drift risk
- `normalize_issues.md` uses `[0-9]{3,}` (3+ digits) while others use `[0-9]+` — inconsistency
- `find_dead_code.md` hardcodes `.issues` instead of using `{{config.issues.base_dir}}`
- BUG-234 was a prior instance of this same class of problem

## Desired End State

A single `ll-next-id` CLI entry point wraps `get_next_issue_number()`, and all 6 locations reference it instead of inlining bash/prose.

## What We're NOT Doing

- Not changing the `get_next_issue_number()` algorithm
- Not adding new ID formats or modifying the function signature
- Not adding `--count N` flag for batch IDs (defer to future enhancement)

## Solution Approach

1. Create thin CLI wrapper following `docs.py` pattern (simplest existing CLI)
2. Register in `pyproject.toml` and `__init__.py`
3. Mechanical replacement of 6 inline snippets
4. Add tests following `test_issue_history_cli.py` pattern (sys.argv patching)

## Implementation Phases

### Phase 1: Create CLI entry point

**File**: `scripts/little_loops/cli/next_id.py`
- `main_next_id()` function that loads config, calls `get_next_issue_number()`, prints result
- Uses `add_config_arg()` from `cli_args.py`
- Zero-padded to 3 digits (matching existing convention)

### Phase 2: Register entry point

- Add to `scripts/little_loops/cli/__init__.py`
- Add `ll-next-id` to `scripts/pyproject.toml` console_scripts

### Phase 3: Replace 4 bash one-liners

- `commands/capture_issue.md` (lines 309-318)
- `commands/find_dead_code.md` (lines 245-249)
- `commands/normalize_issues.md` (lines 155-168)
- `skills/issue-size-review/SKILL.md` (lines 112-117)

### Phase 4: Replace 2 prose instructions

- `commands/scan_codebase.md` (lines 178-182)
- `commands/scan_product.md` (lines 204-208)

### Phase 5: Add tests

- Unit test for argument parsing
- Integration test with sys.argv patching and temp project dir

### Phase 6: Verify

- `python -m pytest scripts/tests/`
- `ruff check scripts/`
- `python -m mypy scripts/little_loops/`
