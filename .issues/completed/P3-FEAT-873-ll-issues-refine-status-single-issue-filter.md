---
id: FEAT-873
type: FEAT
priority: P3
discovered_date: 2026-03-24
discovered_by: /ll:capture-issue
confidence_score: 100
outcome_confidence: 100
---

# FEAT-873: ll-issues refine-status ISSUE-ID single-issue filter

## Summary

Add an optional positional `ISSUE-ID` argument to `ll-issues refine-status` so users can retrieve the refine-status info for a specific issue rather than scanning the entire active backlog.

## Current Behavior

`ll-issues refine-status` always shows the refinement depth table for **all** active issues (optionally filtered by `--type`). There is no way to query the refinement state of a single issue by ID.

## Expected Behavior

```
ll-issues refine-status FEAT-873
```

Returns the refinement row for that specific issue — same columns as the full table (source, norm, fmt, command columns, ready, conf, total) but scoped to one issue. The command should exit with an error message if the issue ID is not found among active issues.

## Motivation

When implementing or reviewing a single issue, the user wants to quickly check its refinement depth (which `/ll:*` skills have been applied, confidence scores, etc.) without wading through the full backlog table. This makes the command composable with loops and scripts that operate issue-by-issue.

## Use Case

A user is about to run `/ll:manage-issue` on `BUG-525` and wants to confirm it has been refined and confidence-scored before proceeding:

```
ll-issues refine-status BUG-525
```

The single-row output confirms `verify ✓  refine 2  ready 82  conf 74  total 6` — enough to proceed with confidence.

## Acceptance Criteria

- `ll-issues refine-status FEAT-873` prints a one-row table (header + separator + data row + key) for the specified issue.
- `ll-issues refine-status BUG-525 --no-key` suppresses the key section.
- `ll-issues refine-status FEAT-873 --json` outputs a single JSON object (not an array).
- `ll-issues refine-status FEAT-873 --format json` outputs one NDJSON line.
- `ll-issues refine-status FEAT-999` (non-existent ID) prints an error to stderr and exits 1.
- `--type` filter still works when no ISSUE-ID is provided (existing behavior unchanged).
- When ISSUE-ID is provided, `--type` is ignored (or validated to be consistent) to avoid confusing conflicts.

## API/Interface

```python
# __init__.py: add positional arg to refine_s subparser
refine_s.add_argument(
    "issue_id",
    nargs="?",
    metavar="ISSUE-ID",
    default=None,
    help="Filter to a single issue by ID (e.g. FEAT-873, BUG-525)",
)

# cmd_refine_status signature unchanged; reads args.issue_id
# When args.issue_id is set, filter issues list to the single match
```

## Proposed Solution

1. Add `issue_id` optional positional arg to the `refine-status` subparser in `scripts/little_loops/cli/issues/__init__.py`.
2. In `cmd_refine_status` (`refine_status.py`), after `find_issues(...)`, filter to `[i for i in issues if i.issue_id == args.issue_id]` when `args.issue_id` is set.
3. If the filtered list is empty, print `"Error: issue '{id}' not found in active issues."` to stderr and return 1.
4. For JSON output with a single issue, emit a single object (not a one-element array) when `--json` is used and ISSUE-ID was provided. Or keep array for consistency — decide based on existing `ll-issues show` convention.
5. Update the epilog examples in `__init__.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — add positional arg to `refine-status` subparser + update epilog
- `scripts/little_loops/cli/issues/refine_status.py` — filter logic + single-issue error handling

### Dependent Files (Callers/Importers)
- `scripts/tests/test_refine_status.py` — add test cases for single-issue filtering, missing ID error

### Similar Patterns
- `scripts/little_loops/cli/issues/show.py` — uses `find_issues` + filters to a single issue by `args.issue_id`; follow the same pattern for ID parsing/matching

### Tests
- `scripts/tests/test_refine_status.py` — extend with single-issue filter tests

### Documentation
- `docs/reference/API.md` — `ll-issues` CLI documented at line ~2846; `refine-status` subcommand at ~2861

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Subparser registration** (`__init__.py:242-267`):
- `refine-status` subparser has: `--type`, `--format`, `--no-key`, `--json`, `--config` — no positional arg yet.
- Epilog at lines 60-63 documents 4 examples; add `%(prog)s refine-status FEAT-873` there.
- Established `nargs="?"` pattern at `__init__.py:124-129` (the `search` subcommand's optional `query` arg) — use identical registration.

**Exact insertion point** (`refine_status.py:246-251`):
```python
type_prefixes = {args.type} if getattr(args, "type", None) else None  # :246
issues = find_issues(config, type_prefixes=type_prefixes)              # :247
                                                                       # :248
if not issues:                                                         # :249
    print("No active issues found.")                                   # :250
    return 0                                                           # :251
```
Add the single-issue filter **between line 247 and line 249** (after `find_issues()`, before the empty-list check) so the empty check doubles as the "ID not found" path.

**`IssueFile.issue_id` attribute** — returns `"TYPE-NNN"` format (e.g., `"FEAT-873"`, `"BUG-001"`). The inline filter `[i for i in issues if i.issue_id == args.issue_id]` will work directly; no secondary ID resolution needed.

**`--type` + `ISSUE-ID` conflict** — simplest resolution: when `args.issue_id` is set, skip the `type_prefixes` kwarg entirely (pass `None`) and let the ID filter do the narrowing. Alternatively, pass `--type` down to `find_issues` but silently override with the ID filter after. Either way the outcome is identical since `find_issues` across all types is cheap.

**Error output — stdout vs stderr discrepancy**:
- The issue's acceptance criteria says "prints an error to stderr and exits 1".
- `show.py:373-375` (the referenced pattern) prints to **stdout** (no `file=sys.stderr`), and `test_issues_cli.py:998` asserts on `captured.out`.
- Recommendation: **use stdout** to stay consistent with `show.py`, and update the acceptance criteria error note accordingly. Use: `print(f"Error: issue '{args.issue_id}' not found in active issues.")`.

**JSON single-object convention**:
- `show.py:378-381` calls `print_json(fields)` with a `dict` → emits a single JSON object (not array). `test_issues_cli.py:1402` asserts `isinstance(data, dict)`.
- `print_json` is in `scripts/little_loops/cli/output.py:97-99`.
- For `--json` + ISSUE-ID: emit `print_json(record_dict)` instead of `print_json([record_dict])`.
- For `--format json` + ISSUE-ID: behavior unchanged (NDJSON emits one line per issue anyway; a single issue naturally produces one line).

**Test helpers** (use in new test class `TestRefineStatusSingleIssue`):
- `_write_config(temp_project_dir, sample_config)` at `test_refine_status.py:14-16`
- `_make_issue(directory, filename, title, *, confidence_score, outcome_confidence, session_commands)` at `test_refine_status.py:19-53`
- `temp_project_dir`, `sample_config`, `issues_dir` fixtures from `conftest.py:55-157`
- Invocation pattern: `patch.object(sys, "argv", ["ll-issues", "refine-status", "FEAT-873", "--config", str(temp_project_dir)])` then `main_issues()`

## Implementation Steps

1. **`__init__.py:260-261`** — Add optional positional arg after the `--no-key` arg in the `refine-status` subparser:
   ```python
   refine_s.add_argument("issue_id", nargs="?", metavar="ISSUE-ID", default=None,
                         help="Filter to a single issue by ID (e.g. FEAT-873, BUG-525)")
   ```
   Also add `%(prog)s refine-status FEAT-873` to the epilog examples.

2. **`refine_status.py:247-248`** — After the `find_issues()` call, add single-issue filter:
   ```python
   issue_id_filter = getattr(args, "issue_id", None)
   if issue_id_filter:
       issues = [i for i in issues if i.issue_id == issue_id_filter]
   ```

3. **`refine_status.py:249-251`** — The existing empty-list check naturally covers the "not found" case; update its message to distinguish the two scenarios:
   ```python
   if not issues:
       if issue_id_filter:
           print(f"Error: issue '{issue_id_filter}' not found in active issues.")
       else:
           print("No active issues found.")
       return 1  # change from 0 to 1 for the not-found error case
   ```
   Note: print to **stdout** (consistent with `show.py:373-375` convention, not stderr).

4. **`refine_status.py:278-300`** — For `--json` + ISSUE-ID, emit a single object instead of an array:
   ```python
   if use_json_array:
       payload = [build_record(issue) for issue in sorted_issues]
       print_json(payload[0] if issue_id_filter else payload)
       return 0
   ```

5. **`test_refine_status.py`** — Add `TestRefineStatusSingleIssue` class with tests:
   - `test_single_issue_table_output` — ID provided, check one-row table output
   - `test_single_issue_not_found` — non-existent ID, assert `result == 1` and `"not found"` in `captured.out`
   - `test_single_issue_json_flag` — `--json` with ID returns a JSON object (`isinstance(data, dict)`)
   - `test_single_issue_format_json` — `--format json` with ID returns one NDJSON line
   - `test_single_issue_no_key` — `--no-key` suppresses key section
   - `test_type_filter_unaffected_without_id` — existing `--type` filter behavior unchanged

## Impact

- **Priority**: P3 — Useful ergonomic improvement; not blocking any workflow
- **Effort**: Small — Minimal change: one new argparse arg + one filter + one error branch
- **Risk**: Low — Purely additive; existing behavior unchanged when no ISSUE-ID provided
- **Breaking Change**: No

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| `.claude/CLAUDE.md` | guidelines | CLI tool conventions and dev workflow |
| `docs/reference/API.md` | architecture | ll-issues CLI reference |

## Resolution

**Status**: Completed
**Completed**: 2026-03-24

### Changes Made

- `scripts/little_loops/cli/issues/__init__.py` — added optional positional `issue_id` arg (`nargs="?"`) to `refine-status` subparser; added `%(prog)s refine-status FEAT-873` epilog example.
- `scripts/little_loops/cli/issues/refine_status.py` — after `find_issues()`, filter issues to single match when `issue_id_filter` is set; contextual error message + `return 1` for not-found case; `--json` with ISSUE-ID emits a single dict instead of an array.
- `scripts/tests/test_refine_status.py` — added `TestRefineStatusSingleIssue` class with 6 tests covering all acceptance criteria.

### Verification

- All 47 tests pass (`python -m pytest scripts/tests/test_refine_status.py`)
- `ruff check` passes on all changed files

## Labels

`feature`, `cli`, `ll-issues`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-03-24T18:24:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ace4e01f-4c8d-4421-be0c-70020100086c.jsonl`
- `/ll:refine-issue` - 2026-03-24T18:13:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee327176-76a1-4c19-ab0a-e4d93de266c2.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/61ffe931-e9d1-47a8-a026-62fbb9ca756f.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/134f1b03-a3a9-4307-be17-0dfb2df69a25.jsonl`
- `/ll:manage-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Completed** | Created: 2026-03-24 | Priority: P3
