---
id: FEAT-1409
type: FEAT
priority: P2

confidence_score: 100
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
parent: FEAT-1406
---

# FEAT-1409: EPIC Type — CLI Source, Regex Extensions, and Tests

## Summary

Implement all source code and test changes to wire EPIC into CLI display, regex-based tooling, and the test suite. This is the primary implementation child of FEAT-1406, covering every `.py` and `.yaml` edit plus the corresponding test additions. Documentation propagation is handled by FEAT-1410.

## Parent Issue

Decomposed from FEAT-1406: EPIC Type — CLI Display, Sync, and Tooling Integration

## Current Behavior

CLI display tools hardcode `(BUG|FEAT|ENH)` patterns in bucket dicts, type label maps, `--type` argparse choices, and regex-based ID scanners. EPIC issues are silently dropped from `ll-issues list`, `ll-issues count`, `ll-history export`, and `ll-issues search`. Regex callers in `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, and `recursive-refine.yaml` do not match `EPIC-NNN` identifiers.

## Expected Behavior

After this child lands:
- `ll-issues list` shows an EPIC bucket; `ll-issues list --type EPIC` filters to epics
- `ll-issues count --json` includes `"EPIC": N` in the type breakdown
- `ll-history export --type EPIC` is accepted by argparse without error
- All regex-based ID scanners match `EPIC-NNN` identifiers
- `ll-issues anchor-sweep` scans EPIC issue files
- All new and existing tests pass

## Proposed Solution

### Step 4 — Fix CLI display

- `scripts/little_loops/cli/issues/list_cmd.py` — add `"EPIC"` to `buckets` dict and `"EPIC": "Epics"` to `type_labels` in `cmd_list()`
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern for `--format table` path
- `scripts/little_loops/cli/issues/__init__.py` — add `"EPIC"` to all 6 subparser `--type` choices (list line 116, search line 176, count line 253, sequence line 274, impact-effort line 295, refine-status line 330)
- `scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` dict in `cmd_count()`

### Step 14 — Update history.py

- `scripts/little_loops/cli/history.py` — add `"EPIC"` to `--type` argument choices in `main_history()` **both** the `export` subparser and the `gendocs` subparser (line 172: `choices=["BUG", "FEAT", "ENH"]` appears in both)

### Step 15 — Update regex-based callers

Extend `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)` in:

1. `scripts/little_loops/cli/deps.py` — `_load_issues()` (line 50): `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)`
2. `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()` (line 280): `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)`
3. `scripts/little_loops/workflow_sequence/analysis.py` — module-level constant (line 28): `ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)`
4. `scripts/little_loops/cli/sprint/edit.py` — `_cmd_sprint_edit()` `--prune` branch (line 77): `re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)`
5. `scripts/little_loops/loops/recursive-refine.yaml` — `build_parent_map()` inside `done` state inline Python (line 686): `re.search(r'(BUG|FEAT|ENH)-(\d+)', os.path.basename(f))`

`scripts/little_loops/cli/issues/refine_status.py` — **Confirmed: no `BUG|FEAT|ENH` regex present.** File delegates type filtering via `type_prefixes` set; no hardcoded regex. No action needed here.

### Wiring items 11-18 (from /ll:wire-issue)

11. `scripts/little_loops/cli_args.py` — update `add_type_arg()` help string example text to include EPIC
12. `scripts/little_loops/issues/anchor_sweep.py` — add `"epics"` to `_ACTIVE_CATEGORIES` tuple in `sweep_issues()`

### Tests (Step 17 + Wiring 13-18)

- `scripts/tests/conftest.py` — update `issues_dir` fixture to create `epics/` subdirectory; add `epics` category to `sample_config` fixture
- `scripts/tests/test_issues_search.py` — add `TestSearchTypeFilter.test_filter_epic` following `test_filter_bug` pattern with `--type EPIC`
- `scripts/tests/test_issues_cli.py`:
  - Add `assert data["by_type"]["EPIC"] == 0` to `TestIssuesCLICount.test_count_json_output`
  - Add `assert "Epics (0)" in captured.out` to `test_list_grouped_output_has_headers` and `test_list_empty_groups_shown`
  - Add `issues_dir_with_epic` fixture mirroring `issues_dir_with_enh`
  - Add `ll-issues list --type EPIC` test
- `scripts/tests/test_issue_history_cli.py` — add `TestExportTypeScoring.test_export_type_epic` mirroring `test_export_type_feat`
- `scripts/tests/test_dependency_mapper.py` — update `TestGatherAllIssueIds.test_scans_all_categories` to include `epics/` subdir with `P2-EPIC-001-foo.md` and assert `"EPIC-001"` in returned ids
- `scripts/tests/test_workflow_sequence_analyzer.py` — update `TestExtractEntities.test_issue_ids` to include `EPIC-001` in test content and assert it is extracted
- `scripts/tests/test_loops_recursive_refine.py:780` — extend inline `build_parent_map()` regex from `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`

### Step 20 — Extended verify

```bash
python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py scripts/tests/test_sync.py scripts/tests/test_cli_args.py scripts/tests/test_cli_output.py scripts/tests/test_issues_search.py scripts/tests/test_issue_template.py scripts/tests/test_config.py scripts/tests/test_issue_history_cli.py scripts/tests/test_dependency_mapper.py scripts/tests/test_workflow_sequence_analyzer.py scripts/tests/test_loops_recursive_refine.py -v
```

## Implementation Steps

1. Add EPIC to all 6 `choices=` lists in `cli/issues/__init__.py`
2. Add EPIC to `buckets` and `type_labels` dicts in `cmd_list()` (`list_cmd.py`) and `cmd_search()` (`search.py` table-format path)
3. Add `"EPIC": 0` to `by_type` dict in `count_cmd.py`
4. Add EPIC to `--type` choices in `history.py` export subparser
5. Extend regex in `deps.py`, `sprint/edit.py`, `dependency_mapper/operations.py`, `workflow_sequence/analysis.py` (ISSUE_PATTERN constant), `loops/recursive-refine.yaml`
6. Check `refine_status.py` for BUG|FEAT|ENH regex; extend if found
7. Update `cli_args.py` `add_type_arg()` help string
8. Add `"epics"` to `_ACTIVE_CATEGORIES` in `anchor_sweep.py`
9. Update `conftest.py` fixtures to create `epics/` dir and `epics` config category
10. Add all test cases per Wiring items 13-18
11. Run extended verify

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. In `cli/history.py` — extend EPIC to the `gendocs` subparser choices at line 172 in addition to the `export` subparser (both use `choices=["BUG", "FEAT", "ENH"]`)
13. Verify `scripts/tests/test_sprint.py` (`TestSprintEdit`) — the `_cmd_sprint_edit()` prune regex change is additive and should not break existing tests; add an EPIC prune test case if the fixture is easily extended with `epics/`
14. Before changing `cli_args.py` `add_type_arg()` help string, confirm `test_cli_args.py` `TestAddTypeArg` tests do not assert on the literal help string text (they test behavior, not help text, so this is likely safe)

## Skipped (Already Done by FEAT-1405)

Per codebase research findings in FEAT-1406:
- `output.py` TYPE_COLOR — already has `"EPIC": "35"`
- `config-schema.json` — already has EPIC in label_mapping and cli.colors.type
- `sync.py` epic: field GitHub mapping — deferred (recommend option c: skip sync of epic: field with doc note)
- `auto.py` — already fully EPIC-aware

## Acceptance Criteria

- `ll-issues list --type EPIC` shows epics with child count column
- `ll-issues list` (no filter) includes EPIC bucket in output
- `ll-issues count --json` includes EPIC key
- `ll-history export --type EPIC` accepted by argparse
- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- `ll-issues anchor-sweep` scans EPIC files
- All new and existing tests pass

## Integration Map

### Files to Modify (Source)
- `scripts/little_loops/cli/issues/list_cmd.py` — `buckets` (line 127): `{"BUG": [], "FEAT": [], "ENH": []}` + `type_labels` (line 133)
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern (table-format path)
- `scripts/little_loops/cli/issues/__init__.py` — 6 `choices=["BUG", "FEAT", "ENH"]` at lines 116, 174, 253, 274, 295, 330
- `scripts/little_loops/cli/issues/count_cmd.py` — `by_type` (line 44): `{"BUG": 0, "FEAT": 0, "ENH": 0}`
- `scripts/little_loops/cli/history.py` — `--type` choices in export subparser and gendocs subparser (line 172)
- `scripts/little_loops/cli/deps.py` — regex in `_load_issues()` (line 50)
- `scripts/little_loops/dependency_mapper/operations.py` — regex in `gather_all_issue_ids()` (line 280)
- `scripts/little_loops/workflow_sequence/analysis.py` — `ISSUE_PATTERN` constant (line 28)
- `scripts/little_loops/cli/sprint/edit.py` — regex in `_cmd_sprint_edit()` (line 77)
- `scripts/little_loops/loops/recursive-refine.yaml` — regex in `build_parent_map()` inside `done` state (line 686)
- `scripts/little_loops/cli_args.py` — help string in `add_type_arg()`
- `scripts/little_loops/issues/anchor_sweep.py` — `_ACTIVE_CATEGORIES = ("bugs", "features", "enhancements")` (line 29)

### Files to Modify (Tests)
- `scripts/tests/conftest.py`
- `scripts/tests/test_issues_search.py`
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_issue_history_cli.py`
- `scripts/tests/test_dependency_mapper.py`
- `scripts/tests/test_workflow_sequence_analyzer.py`
- `scripts/tests/test_loops_recursive_refine.py`
- `scripts/tests/test_sprint.py` — covers `_cmd_sprint_edit()` prune path (the same function being regex-patched in `cli/sprint/edit.py`); verify `TestSprintEdit._setup_edit_project()` is not broken by the regex change and add an EPIC-aware prune scenario if the fixture supports it

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_args.py` — already tests `VALID_ISSUE_TYPES == {"BUG", "FEAT", "ENH", "EPIC"}` and `parse_issue_types()` including EPIC; verify `add_type_arg()` help string change (Step 7) doesn't break `TestAddTypeArg` assertions

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Test Patterns to Follow

**`issues_dir_with_epic` fixture** (model after `issues_dir_with_enh` at `test_issues_cli.py:60`):
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

**`test_filter_epic`** (model after `TestSearchTypeFilter.test_filter_bug` at `test_issues_search.py:219`):
```python
def test_filter_epic(self, temp_project_dir, search_issues_dir, capsys):
    with patch.object(sys, "argv", ["ll-issues", "search", "--type", "EPIC", "--config", str(temp_project_dir)]):
        result = main_issues()
    captured = capsys.readouterr()
    assert result == 0
    # assert EPIC ID in output; assert BUG/FEAT IDs not in output
```

**`test_export_type_epic`** (model after `TestExportTypeScoring.test_export_type_feat` at `test_issue_history_cli.py:642`):
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

**`test_count_json_output`** — add `assert data["by_type"]["EPIC"] == 0` alongside existing assertions (at `test_issues_cli.py:2028`).

**`test_list_grouped_output_has_headers`** — add `assert "Epics (0)" in captured.out`; total count unchanged since EPIC bucket is empty (at `test_issues_cli.py:95`).

**`conftest.py` `sample_config`** (line 65) — `categories` dict currently only has `bugs` and `features`. Add:
```python
"epics": {"prefix": "EPIC", "dir": "epics", "action": "implement"},
```

**`TestGatherAllIssueIds.test_scans_all_categories`** (at `test_dependency_mapper.py:635`) — add `epics/` subdir creation and `P2-EPIC-001-foo.md` file; assert `"EPIC-001" in ids`.

**`TestExtractEntities.test_issue_ids`** (at `test_workflow_sequence_analyzer.py:61`) — add `EPIC-001` to the test content string and assert `"EPIC-001" in entities`.

**`test_loops_recursive_refine.py:780`** — the inline `build_parent_map()` regex is: `re.search(r'(BUG|FEAT|ENH)-(\d+)', os.path.basename(f))`. Change to `r'(BUG|FEAT|ENH|EPIC)-(\d+)'`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- **High file count inflates complexity score**: 19 files touched, but every change is a trivial string addition to a list or regex alternation. Practical risk is missing one touchpoint — work through the integration map sequentially and verify each step.
- **test_sprint.py EPIC prune test is conditional**: Wiring item 13 says "add EPIC prune scenario if the fixture is easily extended with epics/." Investigate `_setup_edit_project()` fixture at test_sprint.py:1451 before skipping — it creates a real directory tree, and adding `epics/` is likely a one-liner.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-09T23:37:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62980d84-6316-4d76-811c-87774aefc470.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a2148c1-474b-4f4b-ae8e-a4d6d5a820ee.jsonl`
- `/ll:refine-issue` - 2026-05-09T23:24:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1cff3e7-0ad2-4324-9519-ae5959cbec9c.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc6cf2a8-dd50-4817-9fa7-649612acf79b.jsonl`
- `/ll:wire-issue` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fde16374-687e-47dc-8e0a-90c0abbfa1e1.jsonl`
- `/ll:issue-size-review` - 2026-05-09T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62980d84-6316-4d76-811c-87774aefc470.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-09
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1410: EPIC Type — CLI Display, Argparse Choices, and Tests
- FEAT-1411: EPIC Type — Regex-Based Callers, Anchor Sweep, and Tests

---

**Decomposed** | Created: 2026-05-09 | Priority: P2
