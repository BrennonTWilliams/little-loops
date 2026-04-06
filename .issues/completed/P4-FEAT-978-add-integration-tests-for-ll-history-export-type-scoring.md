---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# FEAT-978: Add integration tests for `ll-history export --type` and `--scoring` options

## Summary

The `ll-history export` subcommand accepts `--type` (BUG/FEAT/ENH) and `--scoring` (intersection/bm25/hybrid) flags that are forwarded to `synthesize_docs`. The existing `test_issue_history_cli.py` tests cover `-o` and `-S` short forms but do not verify that `--type` or `--scoring` reach `synthesize_docs` with the correct values. Adding these tests catches any future argument-wiring regressions.

## Location

- **File**: `scripts/little_loops/cli/history.py`
- **Line(s)**: 245–275
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

- [x] Test for `export --type BUG` asserts `synthesize_docs` called with `issue_type="BUG"`
- [x] Test for `export --type FEAT` asserts `synthesize_docs` called with `issue_type="FEAT"`
- [x] Test for `export --scoring bm25` asserts `synthesize_docs` called with `scoring="bm25"`
- [x] Test for `export --scoring hybrid` asserts `synthesize_docs` called with `scoring="hybrid"`
- [x] Test for `export` without `--type` asserts `synthesize_docs` called with `issue_type=None` (default)
- [x] All tests follow the existing mock pattern in `test_issue_history_cli.py`

## Proposed Solution

Follow the existing `test_export_output_short_form` / `test_export_since_short_form` pattern from `test_issue_history_cli.py:551-612` — the codebase does **not** use Click's CliRunner; tests patch `sys.argv` and call `main_history()` directly.

**Critical wiring details** (verified from `history.py:120-266`):
- `export` takes a required positional `topic` argument before any flags (history.py:125)
- `--type` stores to `args.issue_type` via `dest="issue_type"` (history.py:172), forwarded as `issue_type=args.issue_type` (history.py:264)
- `--scoring` defaults to `"intersection"`, not `None` (history.py:179)
- Correct patch target: `"little_loops.issue_history.synthesize_docs"` (imported inside `main_history()`, so patching `little_loops.cli.history.synthesize_docs` has no effect)
- Must also patch `"little_loops.issue_history.analysis._load_issue_contents"` (always present in existing export tests)

```python
class TestExportTypeScoring:
    """Tests for --type and --scoring wiring in ll-history export (FEAT-978)."""

    def test_export_type_bug(self, tmp_path: Path) -> None:
        """--type BUG is forwarded to synthesize_docs as issue_type='BUG'."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-history", "export", "cli", "--type", "BUG", "-d", str(tmp_path / ".issues")],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history
            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["issue_type"] == "BUG"

    def test_export_type_feat(self, tmp_path: Path) -> None:
        """--type FEAT is forwarded to synthesize_docs as issue_type='FEAT'."""
        ...  # same pattern, assert issue_type == "FEAT"

    def test_export_type_default_none(self, tmp_path: Path) -> None:
        """export without --type passes issue_type=None to synthesize_docs."""
        ...  # omit --type from argv, assert issue_type is None

    def test_export_scoring_bm25(self, tmp_path: Path) -> None:
        """--scoring bm25 is forwarded to synthesize_docs as scoring='bm25'."""
        ...  # same pattern with --scoring bm25, assert scoring == "bm25"

    def test_export_scoring_hybrid(self, tmp_path: Path) -> None:
        """--scoring hybrid is forwarded to synthesize_docs as scoring='hybrid'."""
        ...  # same pattern, assert scoring == "hybrid"
```

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_history_cli.py` — add export `--type`/`--scoring` test cases

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py` — code under test (no changes needed)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/doc_synthesis.py:143-152` — defines `synthesize_docs` with signature `(topic, issues, contents, format, min_relevance, since, issue_type: str | None = None, scoring: str = "intersection")`; confirms that `issue_type` and `scoring` are the exact keyword argument names to assert on via `call_args.kwargs` [Agent 1/2 finding]
- `scripts/little_loops/issue_history/__init__.py` — re-exports `synthesize_docs` and `_load_issue_contents` (via `analysis`); this re-export is why the patch target `"little_loops.issue_history.synthesize_docs"` resolves correctly [Agent 1 finding]
- `scripts/tests/test_cli.py:2663-2812` — also imports and calls `main_history` in a dedicated test class; not affected by new tests [Agent 1 finding]
- `scripts/tests/test_doc_synthesis.py:229,279,305` — unit-level coverage of `synthesize_docs` with `issue_type="FEAT"` (line 229) and `scoring="hybrid"`/`"bm25"` (lines 279, 305); new CLI-wiring tests in FEAT-978 complement rather than duplicate these [Agent 1/3 finding]

### Similar Patterns
- `test_export_output_short_form` and `test_export_since_short_form` in `test_issue_history_cli.py` — follow these

### Tests
- `scripts/tests/test_issue_history_cli.py` — only file to modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_synthesis.py:229,279,305,428-488` — existing unit and CLI-level tests for `issue_type` and `scoring`; no update needed, but serves as proof that the parameters work at the function level; FEAT-978 tests only the CLI argument-wiring layer [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/tests/test_issue_history_cli.py` and add a new `TestExportTypeScoring` class after `TestExportShortForms` (line 548)
2. Add 5 test methods following the pattern from `test_export_since_short_form` (lines 583-612):
   - Use `patch.object(sys, "argv", ["ll-history", "export", "<topic>", ...flags..., "-d", str(tmp_path / ".issues")])`
   - Always patch both `"little_loops.issue_history.analysis._load_issue_contents"` and `"little_loops.issue_history.synthesize_docs"`
   - Include `patch("builtins.print")` when not writing to a file
   - Assert on `mock_synth.call_args.kwargs["issue_type"]` or `mock_synth.call_args.kwargs["scoring"]`
3. Run `python -m pytest scripts/tests/test_issue_history_cli.py -v -k export` to confirm all pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. **Capture the `synthesize_docs` mock** — the critical difference from existing export stubs is using `patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth` and then asserting `mock_synth.call_args.kwargs["issue_type"] == "BUG"` (etc.). The existing `TestExportShortForms` tests use the same patch but never capture or assert on the mock — FEAT-978 tests require capturing it.
5. **`--scoring` default is `"intersection"`, not `None`** — per `history.py:179` and `doc_synthesis.py:152`. The 5th AC item tests `--type` default (`issue_type=None`). If a default-scoring test is added, assert `scoring == "intersection"`, not `scoring is None`.
6. **`from little_loops.cli import main_history`** must be done inside the `with` block on every test method (not at module level) — this is the pattern used in all export tests in `test_issue_history_cli.py`.

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
- `/ll:ready-issue` - 2026-04-06T19:53:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10a66d29-5307-47ea-8903-f7abe84520b1.jsonl`
- `/ll:confidence-check` - 2026-04-06T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b757c13-9fa6-46d5-adc8-41469f3d50af.jsonl`
- `/ll:wire-issue` - 2026-04-06T19:47:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/debd6d1f-97c9-4122-a56e-7ef00bfe4414.jsonl`
- `/ll:refine-issue` - 2026-04-06T19:42:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb9359c5-37f9-4a27-9a64-8ba21767ecda.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Resolution

Added `TestExportTypeScoring` class to `scripts/tests/test_issue_history_cli.py` with 5 test methods covering all acceptance criteria. Tests patch `little_loops.issue_history.synthesize_docs` and assert on `call_args.kwargs` to verify CLI argument wiring. All 39 tests in the file pass.

## Status

**Completed** | Created: 2026-04-06 | Completed: 2026-04-06 | Priority: P4
