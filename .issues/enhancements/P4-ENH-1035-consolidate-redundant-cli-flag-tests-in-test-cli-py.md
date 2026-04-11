---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# ENH-1035: Consolidate Redundant CLI Flag Tests in test_cli.py

## Summary

`test_cli.py` has ~24 redundant test pairs where every CLI flag is tested twice — once as `test_<flag>_flag_long` and once as `test_<flag>_flag_short`. Argparse handles both forms identically; testing both adds no value. Consolidate these pairs using `@pytest.mark.parametrize` or remove the `_short` variants.

## Current Behavior

Every CLI flag has two nearly identical test functions:
- `test_<flag>_flag_long` — tests `--flag`
- `test_<flag>_flag_short` — tests `-f`

Argparse maps both forms to the same attribute; neither test exercises custom logic.

## Expected Behavior

Each flag tested once (or via a single parametrized test covering both forms). ~24 tests reduced to ~12, with no loss of behavioral coverage.

## Motivation

These tests inflate the test count without exercising any real logic. They test Python's argparse library, not our code. Removing them makes the suite faster and easier to reason about.

## Proposed Solution

Option A (preferred): Convert pairs to a single `@pytest.mark.parametrize("flag", ["--verbose", "-v"])` test.
Option B: Delete the `_short` variant (keeping `_long` which is more readable) for each pair.

## Integration Map

### Files to Modify
- `scripts/tests/test_cli.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_cli.py` — the file being modified

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Identify all `test_<flag>_flag_long` / `test_<flag>_flag_short` pairs (~12 pairs)
2. For each pair, replace with a single parametrized test covering both flag forms
3. Run `python -m pytest scripts/tests/test_cli.py -v --tb=short` and confirm all pass
4. Verify test count drops by ~12

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small - Mechanical refactor within one file
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_cli`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`
