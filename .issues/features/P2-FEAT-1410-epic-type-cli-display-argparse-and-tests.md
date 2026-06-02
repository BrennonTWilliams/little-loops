---
id: FEAT-1410
type: FEAT
priority: P2

confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-05-10T00:00:42Z
parent: FEAT-1409
status: done
---

# FEAT-1410: EPIC Type — CLI Display, Argparse Choices, and Tests

## Summary

Add EPIC to all CLI display paths (list, search, count), argparse `--type` choices, history CLI,
and the `add_type_arg()` help string. Update shared test fixtures and add corresponding test cases.
This child also owns the `conftest.py` fixture changes (adding `epics/` dir and `epics` config
category) used by both FEAT-1410 and FEAT-1411 tests.

## Parent Issue

Decomposed from FEAT-1409: EPIC Type — CLI Source, Regex Extensions, and Tests

## Current Behavior

CLI display tools hardcode `(BUG|FEAT|ENH)` in bucket dicts, type label maps, and `--type`
argparse choices. EPIC issues are silently dropped from `ll-issues list`, `ll-issues count`,
`ll-issues search`, and `ll-history export`. The `add_type_arg()` help string does not mention EPIC.

## Expected Behavior

After this child lands:
- `ll-issues list` shows an EPIC bucket in grouped output
- `ll-issues list --type EPIC` filters to epics
- `ll-issues count --json` includes `"EPIC": N`
- `ll-issues search --type EPIC` is accepted without error
- `ll-history export --type EPIC` and `ll-history gendocs --type EPIC` are accepted by argparse
- `add_type_arg()` help string includes EPIC in its example
- All new and existing tests pass

## Implementation Steps

### Step 1 — `cli/issues/__init__.py`

Add `"EPIC"` to all 6 subparser `--type` choices:
- `list` subparser (line 116)
- `search` subparser (line 176)
- `count` subparser (line 253)
- `sequence` subparser (line 274)
- `impact-effort` subparser (line 295)
- `refine-status` subparser (line 330)

### Step 2 — `list_cmd.py` and `search.py`

- `scripts/little_loops/cli/issues/list_cmd.py` — add `"EPIC"` to `buckets` dict and `"EPIC": "Epics"` to `type_labels` in `cmd_list()`
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern for `--format table` path

### Step 3 — `count_cmd.py`

- `scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` dict in `cmd_count()`

### Step 4 — `history.py`

- `scripts/little_loops/cli/history.py` — add `"EPIC"` to `--type` argument choices in the `export` subparser (line 172: `choices=["BUG", "FEAT", "ENH"]`). There is only **one** subparser with a `--type` argument; there is no separate `gendocs` subparser — `export` is the sole subparser to update.

### Step 5 — `cli_args.py`

- `scripts/little_loops/cli_args.py` — update `add_type_arg()` help string example text to include EPIC
- Before changing, confirm `test_cli_args.py` `TestAddTypeArg` tests do not assert on the literal help string text (they test behavior, not help text — this should be safe)

### Step 6 — `conftest.py` (shared fixture, owned here)

- `scripts/tests/conftest.py` — update `issues_dir` fixture to create `epics/` subdirectory; add `epics` category to `sample_config` fixture:
  ```python
  "epics": {"prefix": "EPIC", "dir": "epics", "action": "implement"},
  ```

### Step 7 — Tests

**`test_issues_cli.py`**:
- Add `issues_dir_with_epic` fixture mirroring `issues_dir_with_enh` (at `test_issues_cli.py:60`):
  ```python
  @pytest.fixture
  def issues_dir_with_epic(issues_dir: Path) -> Path:
      epics_dir = issues_dir / "epics"
      epics_dir.mkdir(parents=True, exist_ok=True)
      (epics_dir / "P2-EPIC-001-parent-initiative.md").write_text(
          "# EPIC-001: Parent initiative\n\n## Summary\nTop-level grouping."
      )
      return issues_dir
  ```
- Add `assert data["by_type"]["EPIC"] == 0` to `TestIssuesCLICount.test_count_json_output` (line 2028)
- Add `assert "Epics (0)" in captured.out` to `test_list_grouped_output_has_headers` and `test_list_empty_groups_shown` (line 95)
- Add `ll-issues list --type EPIC` test using `issues_dir_with_epic`

**`test_issues_search.py`**:
- The `search_issues_dir` fixture (defined in `test_issues_search.py:19`) creates only `bugs/`, `features/`, `completed/`, `deferred/` dirs. It must also be extended to create `epics/` and write one EPIC file (e.g. `P2-EPIC-020-...md`) — simplest to add directly to `search_issues_dir` alongside the existing bugs/features blocks.
- Add `TestSearchTypeFilter.test_filter_epic` following `test_filter_bug` pattern (line 219):
  ```python
  def test_filter_epic(self, temp_project_dir, search_issues_dir, capsys):
      with patch.object(sys, "argv", ["ll-issues", "search", "--type", "EPIC", "--config", str(temp_project_dir)]):
          result = main_issues()
      captured = capsys.readouterr()
      assert result == 0
      assert "EPIC-020" in captured.out
      assert "BUG-001" not in captured.out
      assert "FEAT-010" not in captured.out
  ```

**`test_issue_history_cli.py`**:
- Add `TestExportTypeScoring.test_export_type_epic` mirroring `test_export_type_feat` (line 642):
  ```python
  def test_export_type_epic(self, tmp_path):
      with (
          patch.object(sys, "argv", ["ll-history", "export", "cli", "--type", "EPIC", "-d", str(tmp_path / ".issues")]),
          patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
          patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
          patch("builtins.print"),
      ):
          result = main_history()
      assert result == 0
      assert mock_synth.call_args.kwargs["issue_type"] == "EPIC"
  ```

### Step 8 — Verify

```bash
python -m pytest scripts/tests/test_issues_cli.py scripts/tests/test_issues_search.py \
  scripts/tests/test_issue_history_cli.py scripts/tests/test_cli_args.py \
  scripts/tests/test_config.py -v
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add `test_sequence_type_filter_epic` to `test_issues_cli.py` — pass `--type EPIC` to sequence subparser, assert exit 0 (mirrors `test_sequence_type_filter_no_matches` pattern at line 663)
10. Add `test_count_filter_by_type_epic` to `test_issues_cli.py` — pass `--type EPIC` to count subparser, assert exit 0 and output "0" (mirrors `test_count_filter_by_type` at line 1958)
11. Add `test_impact_effort_type_epic` to `test_issues_cli.py` — pass `--type EPIC` to impact-effort subparser, assert exit 0 (mirrors `test_impact_effort_filter_by_type` at line 879)
12. Confirm documentation ownership: verify whether `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/OUTPUT_STYLING.md`, `docs/reference/CONFIGURATION.md`, and `.claude/CLAUDE.md` type-list updates belong to this child or FEAT-1407; update accordingly

## Integration Map

### Files to Modify (Source)
- `scripts/little_loops/cli/issues/__init__.py:116,176,253,274,295,330` — add `"EPIC"` to `choices=` in 6 subparsers (`list`, `search`, `count`, `sequence`, `impact-effort`, `refine-status`)
- `scripts/little_loops/cli/issues/list_cmd.py:127,133` — `buckets` dict + `type_labels` dict in `cmd_list()`
- `scripts/little_loops/cli/issues/search.py:432,438` — `buckets` dict + `type_labels` dict in `cmd_search()` table branch
- `scripts/little_loops/cli/issues/count_cmd.py:44` — `by_type` dict in `cmd_count()`
- `scripts/little_loops/cli/history.py:172` — `choices=` in `export` subparser (only one `--type` block exists)
- `scripts/little_loops/cli_args.py:323` — `add_type_arg()` help string

### Files to Modify (Tests)
- `scripts/tests/conftest.py:81,125` — `sample_config` `epics` category + `issues_dir` `epics/` subdir
- `scripts/tests/test_issues_cli.py:60,95,241,2028` — `issues_dir_with_epic` fixture + list header + count assertions
- `scripts/tests/test_issues_search.py:19,218` — extend `search_issues_dir` with epic file; add `TestSearchTypeFilter.test_filter_epic`
- `scripts/tests/test_issue_history_cli.py:615` — add `TestExportTypeScoring.test_export_type_epic`

### Already EPIC-aware (No Changes Needed)
- `scripts/little_loops/cli_args.py:266` — `VALID_ISSUE_TYPES` already contains `"EPIC"` (added by FEAT-1409)
- `scripts/little_loops/cli/output.py:41` — `TYPE_COLOR` already has `"EPIC": "35"` (added by FEAT-1405)
- `scripts/tests/test_cli_args.py` — `TestValidIssueTypes` and `TestParseIssueTypes` already cover EPIC; `TestAddTypeArg` does not assert on help string text (safe to update)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `history.py` has **one** `--type` choices block: only the `export` subparser at line 172; no `gendocs` subparser exists.
- `search_issues_dir` fixture in `test_issues_search.py:19` creates its own dirs independently from `conftest.py`'s `issues_dir` — it must be extended directly to include `epics/` and a sample EPIC file for `test_filter_epic` to assert on.
- `TestAddTypeArg` (4 tests) asserts only on parsed `args.type` values, never on help string literal text — safe to update the help string in `add_type_arg()`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The `add_type_arg()` help string update in `cli_args.py` auto-propagates to these callers — **no code changes needed**, informational only:
- `scripts/little_loops/cli/parallel.py` — calls `add_type_arg()` via `add_common_parallel_args()` in `main_parallel()`
- `scripts/little_loops/cli/sprint/__init__.py` — calls `add_type_arg(create_parser)` and `add_type_arg(run_parser)` directly in `main_sprint()`
- `scripts/little_loops/cli/auto.py` — calls `add_type_arg()` via `add_common_auto_args()`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

These doc files list `--type {BUG,FEAT,ENH}` without EPIC and will be stale after this issue lands. May be owned by FEAT-1407 (skills/commands/docs); confirm ownership before including in this child's scope.
- `docs/reference/CLI.md` — 6 subcommand `--type` option table rows (list, count, search, sequence, impact-effort, refine-status) and `ll-history export` row; all read `BUG, FEAT, ENH` without EPIC
- `docs/reference/API.md` — 4 stale locations: `cli.colors.type.*` description (line 151), `is_normalized()` regex doc (line 674), `ll-issues search --type` options (line 3095), `ll-history export --type` options (line 3177)
- `docs/reference/OUTPUT_STYLING.md` — describes `cmd_list` grouping as `BUG/FEAT/ENH` in the Issue List section
- `docs/reference/CONFIGURATION.md` — `cli.colors.type` table lists only BUG, FEAT, ENH color keys (EPIC is already in the JSON schema and `output.py`, but the doc table is stale)
- `.claude/CLAUDE.md` — `## Issue File Format` section: `Types: \`BUG\`, \`FEAT\`, \`ENH\`` — should add EPIC

### Tests

_Wiring pass added by `/ll:wire-issue`:_

Additional test gaps beyond Step 7 (which already covers `test_list_grouped_output_has_headers`, `test_list_empty_groups_shown`, `test_count_json_output`, `test_filter_epic`, and `test_export_type_epic`):
- `scripts/tests/test_issues_cli.py` — add `test_sequence_type_filter_epic` mirroring `TestIssuesCLISequence.test_sequence_type_filter_no_matches` (line 663): pass `--type EPIC`, assert exit 0 and "No active issues" in output
- `scripts/tests/test_issues_cli.py` — add `test_count_filter_by_type_epic` mirroring `TestIssuesCLICount.test_count_filter_by_type` (line 1958): pass `--type EPIC`, assert exit 0 and count output of "0"
- `scripts/tests/test_issues_cli.py` — add `test_impact_effort_type_epic` mirroring `TestIssuesCLIImpactEffort.test_impact_effort_filter_by_type` (line 879): pass `--type EPIC`, assert exit 0
- `scripts/tests/test_cli_e2e.py` — `_get_test_config()` (line 80) and `_create_issue_directories()` (line 119) only create bugs/features/enhancements dirs; no EPIC E2E coverage. Low priority for this child but worth noting for integration completeness.

## Files to Modify (Source)

- `scripts/little_loops/cli/issues/__init__.py` — 6 `choices=["BUG", "FEAT", "ENH"]` at lines 116, **176**, 253, 274, 295, 330 (search subparser is 176, not 174)
- `scripts/little_loops/cli/issues/list_cmd.py` — `buckets` (line 127) + `type_labels` (line 133)
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern
- `scripts/little_loops/cli/issues/count_cmd.py` — `by_type` (line 44)
- `scripts/little_loops/cli/history.py` — `--type` choices in export + gendocs subparsers (line 172)
- `scripts/little_loops/cli_args.py` — help string in `add_type_arg()`

## Files to Modify (Tests)

- `scripts/tests/conftest.py` — `issues_dir` fixture + `sample_config` (shared, owned here)
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_issues_search.py`
- `scripts/tests/test_issue_history_cli.py`

## Use Case

A developer has EPIC-type issues in their `.issues/epics/` directory. When they run `ll-issues list`, those issues are currently silently dropped — no Epics bucket appears. After this issue lands, `ll-issues list` shows an Epics bucket alongside Bugs, Features, and Enhancements, and `ll-issues list --type EPIC` filters to only EPIC issues. Argparse also accepts `--type EPIC` for `count`, `search`, `sequence`, `impact-effort`, and `refine-status`, and `ll-history export --type EPIC` exits 0.

## Impact

- **Priority**: P2 — Additive extension of EPIC type support to CLI display layer; unblocks EPIC visibility in day-to-day issue management
- **Effort**: Small — All changes are trivial additive insertions (`"EPIC"` into existing dicts/choices); 10 locations across 6 source + 4 test files
- **Risk**: Low — All changes are additive; no existing behavior is modified
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `epic-type`, `display`

## Acceptance Criteria

- `ll-issues list` includes EPIC bucket in grouped output
- `ll-issues list --type EPIC` shows epics only
- `ll-issues count --json` includes `"EPIC": 0`
- `ll-history export --type EPIC` exits 0
- `ll-history gendocs --type EPIC` exits 0
- `add_type_arg()` help string mentions EPIC
- All new and existing tests pass

## Skipped (Already Done by FEAT-1405)

- `output.py` TYPE_COLOR — already has `"EPIC": "35"`
- `config-schema.json` — already has EPIC in label_mapping and cli.colors.type
- `auto.py` — already fully EPIC-aware

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Spread across 10 files (6 source + 4 test): all changes are trivial additive insertions, but touching 10 locations increases the risk of omitting one `"EPIC"` entry — verify each of the 6 `choices=` blocks in `__init__.py` after implementation.
- Documentation ownership is unresolved: doc updates for `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/OUTPUT_STYLING.md`, `docs/reference/CONFIGURATION.md`, and `.claude/CLAUDE.md` may belong to FEAT-1407 rather than this issue — confirm before closing.

## Resolution

All 10 source locations updated (6 `choices=` in `__init__.py`, `buckets`/`type_labels` in `list_cmd.py` and `search.py`, `by_type` in `count_cmd.py`, `choices=` in `history.py`, help string in `cli_args.py`). Shared fixtures updated (`conftest.py` adds `epics/` dir and `epics` category to `sample_config`). 10 new test cases added across 4 test files. 477 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-10T00:00:42Z - `current.jsonl`
- `/ll:ready-issue` - 2026-05-09T23:55:30 - `26301779-5759-4e6e-aadd-d261c4d18698.jsonl`
- `/ll:wire-issue` - 2026-05-09T23:49:12 - `0400bf5c-e7b1-45d1-9498-ee4262bc98e8.jsonl`
- `/ll:refine-issue` - 2026-05-09T23:42:36 - `0665047f-590b-4b6b-af84-2a5dc369d475.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `62980d84-6316-4d76-811c-87774aefc470.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `ec917a4b-6188-4adc-9920-6c61e1a5e624.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
