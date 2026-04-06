---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# FEAT-978: Add integration tests for `ll-history export --type` and `--scoring` options

## Summary

The `ll-history export` subcommand accepts `--type` (BUG/FEAT/ENH) and `--scoring` (intersection/bm25/hybrid) flags that are forwarded to `synthesize_docs`. The existing `test_issue_history_cli.py` tests cover `-o` and `-S` short forms but do not verify that `--type` or `--scoring` reach `synthesize_docs` with the correct values. Adding these tests catches any future argument-wiring regressions.

## Location

- **File**: `scripts/little_loops/cli/history.py`
- **Line(s)**: 246–274 (at scan commit: 96d74cda)
- **Anchor**: `in function main_history` — `if args.command == "export":` branch
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/cli/history.py#L246-L274)
- **Code**:
```python
if args.command == "export":
    result = synthesize_docs(
        ...
        issue_type=args.type,       # forwarded from --type
        scoring=args.scoring,       # forwarded from --scoring
    )
```

## Current Behavior

`--type` and `--scoring` are accepted by argparse (verified by short-form tests) but no test verifies they are forwarded to `synthesize_docs` with correct values. A wiring bug — e.g., passing `args.type` as a positional instead of keyword argument — would go undetected.

## Expected Behavior

Tests confirm that `synthesize_docs` is called with `issue_type="BUG"` when `--type BUG` is passed, and with `scoring="bm25"` when `--scoring bm25` is passed.

## Motivation

`ll-history export` is used to generate documentation from completed issue history. The `--type` filter is particularly important for focused reports. Argument-wiring tests are cheap to write and catch the most common category of CLI regression.

## Use Case

A developer runs `ll-history export --type BUG -o bugs-report.md` to generate a bug-focused summary. The test verifies `synthesize_docs` receives `issue_type="BUG"` and not `None` (the default).

## Acceptance Criteria

- [ ] Test for `export --type BUG` asserts `synthesize_docs` called with `issue_type="BUG"`
- [ ] Test for `export --type FEAT` asserts `synthesize_docs` called with `issue_type="FEAT"`
- [ ] Test for `export --scoring bm25` asserts `synthesize_docs` called with `scoring="bm25"`
- [ ] Test for `export --scoring hybrid` asserts `synthesize_docs` called with `scoring="hybrid"`
- [ ] Test for `export` without `--type` asserts `synthesize_docs` called with `issue_type=None` (default)
- [ ] All tests follow the existing mock pattern in `test_issue_history_cli.py`

## Proposed Solution

Follow the existing `test_export_*` test pattern in `test_issue_history_cli.py`:

```python
def test_export_type_filter_bug(mock_synthesize):
    with patch("little_loops.cli.history.synthesize_docs", return_value=...) as mock_synth:
        runner.invoke(main_history, ["export", "--type", "BUG", "-o", "out.md"])
    mock_synth.assert_called_once()
    call_kwargs = mock_synth.call_args.kwargs
    assert call_kwargs["issue_type"] == "BUG"

def test_export_scoring_bm25(mock_synthesize):
    with patch("little_loops.cli.history.synthesize_docs", return_value=...) as mock_synth:
        runner.invoke(main_history, ["export", "--scoring", "bm25", "-o", "out.md"])
    mock_synth.assert_called_once()
    assert mock_synth.call_args.kwargs["scoring"] == "bm25"
```

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_history_cli.py` — add export `--type`/`--scoring` test cases

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py` — code under test (no changes needed)

### Similar Patterns
- `test_export_output_short_form` and `test_export_since_short_form` in `test_issue_history_cli.py` — follow these

### Tests
- `scripts/tests/test_issue_history_cli.py` — only file to modify

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the `test_export_*` test class in `test_issue_history_cli.py`
2. Add parametrized or individual tests for `--type` (BUG, FEAT, ENH, None) and `--scoring` (intersection, bm25, hybrid)
3. Run `python -m pytest scripts/tests/test_issue_history_cli.py -v -k export` to confirm

## Impact

- **Priority**: P4 — Test coverage gap; no behavioral change
- **Effort**: Small — Following established test patterns in the same file
- **Risk**: Low — Test-only change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `testing`, `history`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
