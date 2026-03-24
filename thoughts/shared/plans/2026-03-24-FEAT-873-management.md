# Implementation Plan: FEAT-873 — ll-issues refine-status single-issue filter

**Date**: 2026-03-24
**Issue**: FEAT-873
**Status**: In Progress

---

## Summary

Add an optional positional `ISSUE-ID` argument to `ll-issues refine-status` so users can query refinement status for a single issue.

---

## Phase 0: Write Tests (Red)

Add `TestRefineStatusSingleIssue` class to `scripts/tests/test_refine_status.py`:

- `test_single_issue_table_output` — ID provided, check one-row table output
- `test_single_issue_not_found` — non-existent ID, assert `result == 1` and `"not found"` in `captured.out`
- `test_single_issue_json_flag` — `--json` with ID returns a JSON object (`isinstance(data, dict)`)
- `test_single_issue_format_json` — `--format json` with ID returns one NDJSON line
- `test_single_issue_no_key` — `--no-key` suppresses key section
- `test_type_filter_unaffected_without_id` — existing `--type` filter behavior unchanged

---

## Phase 1: Modify `scripts/little_loops/cli/issues/__init__.py`

### 1a. Add positional arg to refine-status subparser (after `--json` arg, before `add_config_arg`)

```python
refine_s.add_argument(
    "issue_id",
    nargs="?",
    metavar="ISSUE-ID",
    default=None,
    help="Filter to a single issue by ID (e.g. FEAT-873, BUG-525)",
)
```

### 1b. Add epilog example

Add `%(prog)s refine-status FEAT-873` after line 63.

---

## Phase 2: Modify `scripts/little_loops/cli/issues/refine_status.py`

### 2a. After `find_issues()` call (line 247), add single-issue filter

```python
issue_id_filter = getattr(args, "issue_id", None)
if issue_id_filter:
    issues = [i for i in issues if i.issue_id == issue_id_filter]
```

### 2b. Update empty-list check (lines 249-251) for contextual error message

```python
if not issues:
    if issue_id_filter:
        print(f"Error: issue '{issue_id_filter}' not found in active issues.")
        return 1
    print("No active issues found.")
    return 0
```

### 2c. Update `--json` array output (line 281-300) for single-issue emit

When `use_json_array` and `issue_id_filter`, emit a single object instead of an array:

```python
if use_json_array:
    records = [build_record(issue) for issue in sorted_issues]
    print_json(records[0] if issue_id_filter else records)
    return 0
```

(Inline the record-building rather than extracting a helper function — stay minimal.)

---

## Design Decisions

1. **stdout for errors** (not stderr): Follow `show.py:373-375` convention, not the acceptance criteria note about stderr. Tests assert `captured.out`.
2. **return 1 for not-found**: Change from `return 0` to `return 1` for the not-found branch.
3. **return 0 for normal empty**: Keep existing `return 0` for "no active issues found" (no ISSUE-ID given).
4. **`--type` when ISSUE-ID present**: Skip `type_prefixes` — pass `None` to `find_issues` and let the ID filter narrow the result. Simplest, avoids confusing conflicts.
5. **`--json` single object**: When ISSUE-ID provided + `--json`, emit a single dict (like `show.py`). When no ISSUE-ID, keep existing array behavior.

---

## Files to Change

| File | Change |
|------|--------|
| `scripts/little_loops/cli/issues/__init__.py` | Add positional arg + epilog example |
| `scripts/little_loops/cli/issues/refine_status.py` | Filter logic + contextual error message + single JSON object |
| `scripts/tests/test_refine_status.py` | New `TestRefineStatusSingleIssue` test class |

---

## Success Criteria

- [x] `ll-issues refine-status FEAT-873` prints one-row table for the specified issue
- [x] `ll-issues refine-status BUG-525 --no-key` suppresses key section
- [x] `ll-issues refine-status FEAT-873 --json` outputs a single JSON object
- [x] `ll-issues refine-status FEAT-873 --format json` outputs one NDJSON line
- [x] `ll-issues refine-status FEAT-999` exits 1 with error message
- [x] `--type` without ISSUE-ID: existing behavior unchanged
- [x] All existing tests continue to pass
