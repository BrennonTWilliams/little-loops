---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# ENH-486: Add early break and compiled regex in `get_next_issue_number`

## Summary

`get_next_issue_number` in `issue_parser.py` has an O(D*F*P) triple-nested loop that iterates through all prefixes for each file, without breaking early after a match. It also compiles a new regex on each inner iteration.

## Current Behavior

For each `.md` file, the code iterates through all configured prefixes and runs `re.search(rf"{prefix}-(\d+)", file.name)`. Once a prefix matches, the loop continues to the next prefix (no `break`). The regex is compiled per iteration.

## Expected Behavior

After a match is found for a given file, the inner prefix loop breaks early. A single pre-compiled union regex replaces P individual regex calls.

## Motivation

`get_next_issue_number` is called from `_generate_id_from_filename` and `_create_local_issue` on every issue that lacks an explicit ID. With many issue files, the unnecessary extra iterations add up.

## Proposed Solution

1. Add `break` after the `max_num = num` assignment at line 73
2. Optionally, pre-compile a single union regex: `re.compile(r"(" + "|".join(all_prefixes) + r")-(\d+)")`

## Scope Boundaries

- **In scope**: Adding early break and optional regex pre-compilation
- **Out of scope**: Changing the issue numbering scheme

## Implementation Steps

1. Add `break` after match in the inner prefix loop
2. Pre-compile union regex with all configured prefixes
3. Verify existing `test_issue_parser.py` tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `get_next_issue_number`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `_generate_id_from_filename`
- `scripts/little_loops/sync.py` — `_create_local_issue`

### Similar Patterns
- N/A

### Tests
- Existing `test_issue_parser.py` tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Minor performance improvement
- **Effort**: Small — Add `break` statement and optional regex refactor
- **Risk**: Low — Logic-preserving optimization
- **Breaking Change**: No

## Labels

`enhancement`, `performance`, `issue-parser`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
