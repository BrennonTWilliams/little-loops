---
id: FEAT-1405
type: FEAT
priority: P2
status: open
parent_issue: FEAT-1389
captured_at: '2026-05-09T00:00:00Z'
completed_at: '2026-05-09T22:51:58Z'
discovered_date: '2026-05-09'
confidence_score: 100
outcome_confidence: 60
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
decision_needed: false
---

# FEAT-1405: EPIC Type — Core Registration and Parsing

## Summary

Register `EPIC` as a recognized issue type and fix all core parsing infrastructure. This is the foundation child that all other EPIC work builds on: the type registration, parser regex updates, IssueInfo dataclass extension, and broken-test fixes must ship before any CLI or tooling work is meaningful.

## Parent Issue

Decomposed from FEAT-1389: Add EPIC as a First-Class Issue Type

## Proposed Solution

### Step 1 — Register EPIC type

Add `"epics"` to `REQUIRED_CATEGORIES` in `scripts/little_loops/config/features.py`:

```python
REQUIRED_CATEGORIES = {
    "bugs":         {"prefix": "BUG",  "dir": "bugs",         "action": "fix"},
    "features":     {"prefix": "FEAT", "dir": "features",     "action": "implement"},
    "enhancements": {"prefix": "ENH",  "dir": "enhancements", "action": "improve"},
    "epics":        {"prefix": "EPIC", "dir": "epics",        "action": "coordinate"},
}
```

Create `.issues/epics/` directory (add a `.gitkeep` placeholder).

### Step 2 — Create epic-sections.json template

Create `templates/epic-sections.json` modeled after `templates/feat-sections.json`. Include:
- `goal` (required) — overarching objective
- `scope` (required) — what is in/out of scope
- `children` list (required) — member issue IDs
- `success_metrics` (conditional) — measurable outcomes

The template loader in `issue_template.py` derives filename as `f"{issue_type.lower()}-sections.json"` — no code change needed; just creating the file is sufficient.

### Step 3 — Fix hardcoded regexes in parser and sync

Six regex literals to extend with `EPIC` alternation:

1. `scripts/little_loops/issue_parser.py` — `_NORMALIZED_RE` (module level): `r"^P[0-5]-(BUG|FEAT|ENH)-..."` → add `EPIC`
2. `scripts/little_loops/issue_parser.py` — `_ISSUE_TYPE_RE` (module level): `r"-(BUG|FEAT|ENH)-"` → add `EPIC`
3. `scripts/little_loops/cli/issues/show.py` — `_resolve_issue_id()`: two regex literals with `(BUG|FEAT|ENH)` alternation → add `EPIC`
4. `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields()`: one regex → add `EPIC`
5. `scripts/little_loops/sync.py` — `_extract_issue_id()`: `r"(BUG|FEAT|ENH)-(\d+)"` → add `EPIC`

### Step 4 — Fix sync.py reopen_issues category_map

In `scripts/little_loops/sync.py`, `reopen_issues()` has:
```python
category_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
```
Add `"EPIC": "epics"`.

### Step 5 — Add epic: field to IssueInfo dataclass

In `scripts/little_loops/issue_parser.py`, add `epic: str | None = None` to the `IssueInfo` dataclass. Update `IssueParser.parse_file()` to read `epic:` from frontmatter. Follow the pattern of `blocked_by`/`blocks` for optional frontmatter fields.

Also add `epic:` as a valid optional field in `config-schema.json` on BUG/FEAT/ENH issue schemas.

> **Pattern clarification**: `epic:` is a **scalar** field — use `epic_id = frontmatter.get("epic")` directly (same pattern as `discovered_by` at `issue_parser.py:366`). Do NOT follow `blocked_by`/`blocks`, which are list-based with dual body+frontmatter merge logic and conflict resolution. For `epic:` there is no body-section equivalent, so no merge is needed.

### Step 11 — Update cli_args.py

In `scripts/little_loops/cli_args.py`, add `"EPIC"` to `VALID_ISSUE_TYPES` constant and the error message string in `parse_issue_types()`. Do this before any `--type EPIC` invocations, or argparse rejects them before any code runs.

### Step 12 — Update config/cli.py

In `scripts/little_loops/config/cli.py`, add `EPIC: str = "35"` field to `CliColorsTypeConfig` dataclass and `data.get("EPIC", "35")` in `from_dict()`. This is required for `output.py`'s `configure_output()` to pick up the EPIC color.

### Step 13 — Update cli/output.py

In `scripts/little_loops/cli/output.py`:

1. Add `"EPIC": "35"` to the module-level `TYPE_COLOR` dict (lines 41–45):
   ```python
   TYPE_COLOR: dict[str, str] = {
       "BUG": "38;5;208",
       "FEAT": "32",
       "ENH": "34",
       "EPIC": "35",   # add this
   }
   ```

2. Add `"EPIC": config.colors.type.EPIC` inside `configure_output()`'s `TYPE_COLOR.update(...)` call (lines 81–86):
   ```python
   TYPE_COLOR.update({
       "BUG": config.colors.type.BUG,
       "FEAT": config.colors.type.FEAT,
       "ENH": config.colors.type.ENH,
       "EPIC": config.colors.type.EPIC,   # add this
   })
   ```

`configure_output()` names each field explicitly — adding a field to `CliColorsTypeConfig` does **not** automatically flow through. Both sites need updating.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 5 gap — `IssueInfo.to_dict()` and `from_dict()` also need updating:**
`IssueInfo.to_dict()` (~line 263) and `from_dict()` (~line 300) are explicit field-by-field mappings. When adding `epic: str | None = None` to the dataclass, both methods must be updated: `"epic": self.epic` in `to_dict()`, and `epic=data.get("epic")` in `from_dict()`. The frontmatter read in `parse_file()` should use `frontmatter.get("epic")` directly (simpler than `blocked_by`/`blocks` since there is no body-section equivalent — no conflict resolution needed).

**Additional `BUG|FEAT|ENH` hardcoded sites (out-of-scope — belong to FEAT-1406):**
Research found 12+ additional sites not listed in this issue. They are in scope for FEAT-1406, not here:
- `cli/issues/__init__.py` lines 116, 176, 253, 274, 295, 330 — `choices=["BUG", "FEAT", "ENH"]` in 6 subcommand parsers
- `cli/issues/count_cmd.py:44`, `cli/issues/list_cmd.py:127,133`, `cli/issues/search.py:432,438` — display bucket/label dicts
- `cli/deps.py:50`, `cli/sprint/edit.py:77` — filename regex patterns
- `cli/history.py:172` — `choices` in `ll-history gendocs` subparser
- `config/features.py:332,346` — `label_mapping` in `GitHubSyncConfig`
- `dependency_mapper/operations.py:280`, `workflow_sequence/analysis.py:28` — regex patterns
- `loops/recursive-refine.yaml:686` — inline Python regex in YAML

### Step 16 — Fix breaking tests (before CI runs)

Two test files will fail immediately on main with EPIC changes:

- `scripts/tests/test_cli_args.py` — `TestValidIssueTypes.test_contains_expected_types` asserts `VALID_ISSUE_TYPES == {"BUG", "FEAT", "ENH"}` (exact equality); update to include `"EPIC"`; also add `test_parse_epic_type` following pattern of `TestParseIssueTypes`
- `scripts/tests/test_cli_output.py` — `TestConfigureOutput.setup_method` and `teardown_method` call `TYPE_COLOR.update({"BUG":..., "FEAT":..., "ENH":...})`; when EPIC is added, this reset is incomplete and leaves EPIC dirty between tests; update both to include `"EPIC"` reset; add `TestOrangeDefaultColors.test_type_epic_has_color` asserting `TYPE_COLOR["EPIC"] == "35"`

### Step 8 — Add core parser tests

Pre-written tests are already in `scripts/tests/test_issue_parser.py` (see `TestIssueInfo::test_epic_roundtrip`, `test_epic_in_to_dict`, `test_epic_from_dict`, `test_epic_from_dict_missing`, `test_epic_default_none`, and `TestIssueParser::test_parse_epic_from_frontmatter`, `test_parse_no_epic`). These will fail until Step 5 is implemented — use them as your pass/fail signal.

Additional tests to add (following pattern of `test_parse_feature_issue`):
- EPIC type routing and directory creation
- ID allocation (EPIC-NNN from global counter)

In `scripts/tests/test_config.py`, following pattern of `test_required_categories_merged_with_custom`:
- EPIC registered in REQUIRED_CATEGORIES with correct prefix/dir/action

### Step 10 — Verify tests

```bash
python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_cli_args.py scripts/tests/test_cli_output.py scripts/tests/test_config.py -v
```

### Step 14 — Grep sweep (post-implementation)

After all changes are applied, run this to catch any `BUG|FEAT|ENH` alternations that were missed:

```bash
grep -rn "BUG|FEAT|ENH" scripts/ hooks/ --include="*.py" --include="*.sh" | grep -v "EPIC"
```

Any line in the output is a missed touchpoint. The sweep should return no results before merging.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Fix `hooks/scripts/check-duplicate-issue-id.sh` — extend `(BUG|FEAT|ENH)` regex patterns at lines 64 and 110 to include `EPIC`; update error message at line 123 to list `BUG/FEAT/ENH/EPIC`
15. Fix `hooks/scripts/check-duplicate-issue-id-post.sh` — same extension at lines 52 and 71; without this EPIC files bypass duplicate ID detection entirely
16. Fix `scripts/little_loops/issue_history/parsing.py` — extend hardcoded `r"(BUG|ENH|FEAT)-(\d+)"` in `parse_completed_issue()` (~line 51) and `scan_active_issues()` (~line 485) to include `EPIC`; otherwise EPIC completed issues return `issue_type="UNKNOWN"`
17. Fix `scripts/little_loops/parallel/worker_pool.py` — extend `_is_foreign_file()` lowercase regex `r"(?:bug|enh|feat)-\d+"` (~line 1000) to include `epic`; without this EPIC issues are invisible to overlap detection
18. Update `scripts/tests/test_sync.py` — add EPIC case for `_extract_issue_id` (following `test_extract_issue_id_bug` pattern) and EPIC reopen test exercising `category_map` path in `reopen_issues()` (following `test_reopen_specific_issue_in_completed`)
19. Update `scripts/tests/test_issue_template.py` — add `"EPIC"` to `@pytest.mark.parametrize("issue_type", ["BUG", "FEAT", "ENH"])` in `test_load_default`
20. Update `scripts/tests/test_issue_parser_fuzz.py` — add `"EPIC"` to `st.sampled_from(["BUG", "FEAT", "ENH"])` strategy at lines 102 and 107
21. Update `scripts/tests/test_issue_parser_properties.py` — add `"epics"` to `st.sampled_from(["bugs", "features", "enhancements"])` at line 75

## Acceptance Criteria

- `REQUIRED_CATEGORIES["epics"]` exists with `prefix="EPIC"`, `dir="epics"`, `action="coordinate"`
- `.issues/epics/` directory exists
- `templates/epic-sections.json` exists with goal, scope, children, success_metrics sections
- `_NORMALIZED_RE` and `_ISSUE_TYPE_RE` in issue_parser.py match EPIC filenames
- `IssueInfo` has `epic: str | None = None` field; parse_file() reads it from frontmatter
- `VALID_ISSUE_TYPES` in cli_args.py includes `"EPIC"`
- `CliColorsTypeConfig` has `EPIC` field defaulting to `"35"`
- All 4 test files above pass with no new failures

## Files to Touch

- `scripts/little_loops/config/features.py`
- `scripts/little_loops/issue_parser.py` (2 regex + IssueInfo dataclass + parse_file)
- `scripts/little_loops/cli/issues/show.py` (3 regex)
- `scripts/little_loops/sync.py` (1 regex + category_map)
- `scripts/little_loops/cli_args.py`
- `scripts/little_loops/config/cli.py`
- `scripts/little_loops/cli/output.py` (TYPE_COLOR dict + configure_output() — research gap, not in original list)
- `config-schema.json`
- `templates/epic-sections.json` (new)
- `.issues/epics/.gitkeep` (new)
- `scripts/tests/test_cli_args.py`
- `scripts/tests/test_cli_output.py`
- `scripts/tests/test_issue_parser.py`
- `scripts/tests/test_config.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py:13-17` — add `"epics"` entry to `REQUIRED_CATEGORIES`
- `scripts/little_loops/config/features.py:346` — add `"EPIC": "epics"` to `GitHubSyncConfig.label_mapping` default dict (same file, different function — wiring pass)
- `scripts/little_loops/issue_parser.py:29-30` — extend `_NORMALIZED_RE` and `_ISSUE_TYPE_RE` with `|EPIC`
- `scripts/little_loops/issue_parser.py` (~line 202, `IssueInfo`) — add `epic: str | None = None`; update `to_dict()` (~line 263) and `from_dict()` (~line 300)
- `scripts/little_loops/issue_parser.py` (`parse_file()`, ~line 344) — add `frontmatter.get("epic")` and pass to `IssueInfo(epic=...)`
- `scripts/little_loops/cli/issues/show.py:57,64` — extend 2 regex patterns in `_resolve_issue_id()`
- `scripts/little_loops/cli/issues/show.py:122` — extend 1 regex pattern in `_parse_card_fields()`
- `scripts/little_loops/sync.py:296` — extend `_extract_issue_id()` regex
- `scripts/little_loops/sync.py:1081` — add `"EPIC": "epics"` to `reopen_issues()` `category_map`
- `scripts/little_loops/cli_args.py:266` — add `"EPIC"` to `VALID_ISSUE_TYPES`
- `scripts/little_loops/config/cli.py:57-72` — add `EPIC: str = "35"` to `CliColorsTypeConfig`; add `EPIC` to `from_dict()`
- `scripts/little_loops/cli/output.py:41-45` — add `"EPIC": "35"` to module-level `TYPE_COLOR` dict
- `scripts/little_loops/cli/output.py:81-86` — add `"EPIC": config.colors.type.EPIC` to `configure_output()` `TYPE_COLOR.update(...)` call
- `config-schema.json` — add `epic:` as optional field on BUG/FEAT/ENH schemas

### Callers / Importers
- `scripts/little_loops/issue_template.py:20` (`load_issue_sections()`) — auto-resolves `epic-sections.json` via `f"{issue_type.lower()}-sections.json"`; no code change needed
- `scripts/tests/test_issue_template.py:34` — `@pytest.mark.parametrize("issue_type", ["BUG", "FEAT", "ENH"])` for `test_load_default`; add `"EPIC"` here (could be FEAT-1406 scope)

### Similar Patterns (Modeling References)
- `scripts/little_loops/issue_parser.py:442-466` — `blocked_by`/`blocks` frontmatter parsing in `parse_file()` — model for `epic:` field (scalar, no conflict resolution needed)
- `scripts/tests/test_issue_parser.py:418` — `test_parse_feature_issue` in `TestIssueParser` — EPIC test model
- `scripts/tests/test_config.py:948` — `test_required_categories_merged_with_custom` — add `"epics"` assertion
- `scripts/tests/test_cli_args.py:137` — `TestParseIssueTypes` — model for `test_parse_epic_type`
- `templates/feat-sections.json` — model for `epic-sections.json` structure (`_meta`, `common_sections`, `type_sections`, `creation_variants`, `quality_checks`)

### Tests to Update
- `scripts/tests/test_cli_args.py:178` — `TestValidIssueTypes.test_contains_expected_types` — update set equality to include `"EPIC"`
- `scripts/tests/test_cli_args.py:171` — `TestParseIssueTypes.test_all_types` — currently asserts `== {"BUG", "FEAT", "ENH"}`; update to include `"EPIC"` alongside adding `test_parse_epic_type`
- `scripts/tests/test_cli_output.py:161` — `TestConfigureOutput.setup_method` and `teardown_method` — add `"EPIC"` to `TYPE_COLOR` reset in both; add `test_type_epic_has_color`
- `scripts/tests/test_issue_parser.py` — add EPIC type routing, ID allocation, and `epic:` frontmatter round-trip tests
- `scripts/tests/test_config.py` — add EPIC assertion to `test_required_categories_merged_with_custom`
- `scripts/tests/test_config.py:140,169,607` — `len(config.categories) == 3` assertions will break when `REQUIRED_CATEGORIES` gains `"epics"` — update to 4 [wiring pass]; line 140 is in `test_from_dict_with_all_options()`, line 169 in `test_from_dict_with_defaults()`, line 607 in `test_load_config_no_file()`
- `scripts/tests/test_config.py` — `TestGitHubSyncConfigDefaults.test_from_dict_with_defaults()` asserts exact `label_mapping == {"BUG": ..., "FEAT": ..., "ENH": ...}` — will break if `GitHubSyncConfig.label_mapping` default is extended to include EPIC [wiring pass]

### Hook Files

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/check-duplicate-issue-id.sh:64,110` — `grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}'` and `grep -qE "(BUG|FEAT|ENH)-${ISSUE_NUM}"` silently pass EPIC files through; line 123 error message omits EPIC from valid-type list
- `hooks/scripts/check-duplicate-issue-id-post.sh:52,71` — same patterns; without extension, EPIC files bypass all duplicate ID detection on write

### Tests — New (to Write)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_sync.py` — add `test_extract_issue_id_epic` following `TestGitHubSyncManager.test_extract_issue_id_bug`; add EPIC reopen test exercising `category_map["EPIC"] == "epics"` path in `reopen_issues()`
- `scripts/tests/test_issue_template.py` — add `"EPIC"` to `test_load_default` parametrize list; EPIC template loading is auto-wired via `issue_template.py` but has zero test coverage
- `scripts/tests/test_issue_parser_fuzz.py` — extend `st.sampled_from(["BUG", "FEAT", "ENH"])` at lines 102, 107 to include `"EPIC"`
- `scripts/tests/test_issue_parser_properties.py` — extend `st.sampled_from(["bugs", "features", "enhancements"])` at line 75 to include `"epics"`

### Infrastructure Files

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/parsing.py:51,485` — `parse_completed_issue()` and `scan_active_issues()` contain standalone hardcoded `r"(BUG|ENH|FEAT)-(\d+)"` regex; EPIC completed issues return `issue_type="UNKNOWN"` without fix (this file has no dependency on `_ISSUE_TYPE_RE`)
- `scripts/little_loops/parallel/worker_pool.py:983-1012` — `_has_other_issue_id()` uses lowercase `r"(?:bug|enh|feat)-\d+"` pattern at line 1000; EPIC issues are invisible to overlap detection across parallel workers (note: issue previously named this `_is_foreign_file()` — incorrect; the actual function is `_has_other_issue_id()`)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 60/100 → MODERATE

### Outcome Risk Factors
- **Width over depth (22+ files, 6+ subsystems)**: Every individual change is trivial (add `|EPIC` to a regex, add one field to a dataclass), but the count means a missed touchpoint will silently pass CI and fail at runtime on EPIC-prefixed files. Follow the Integration Map step-by-step — the wiring pass already found 8 sites the original spec missed; treat the Proposed Solution steps as a secondary guide, not the primary one.
- **IssueInfo change surface (21+ importers)**: Adding `epic: str | None = None` is backward-compatible, but `to_dict()` (~line 263) and `from_dict()` (~line 300) are explicit field-by-field maps — verify both are updated before running any parser tests. Use the pre-written `test_epic_roundtrip` as your integration signal.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-09T22:52:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed8c7dae-b8ca-4e7d-b2dc-1671f93fa9c2.jsonl`
- `/ll:ready-issue` - 2026-05-09T22:38:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/556bec38-41e8-423e-be05-a8efa32eee62.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a11adf41-8e63-4023-93fa-bc93379326a7.jsonl`
- `/ll:confidence-check` - 2026-05-09T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43665bb5-b08a-4083-80d6-5bfcdabc4d8c.jsonl`
- `/ll:refine-issue` - 2026-05-09T22:26:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efbb9709-7a24-4905-85fd-8a5a0825d700.jsonl`
- `/ll:wire-issue` - 2026-05-09T22:17:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc3e84b1-c81c-4b29-8f56-73dba03552dc.jsonl`
- `/ll:refine-issue` - 2026-05-09T22:09:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/139c849b-af93-4a61-b279-7b129b6ed004.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/262d7f0c-fdf5-444e-8731-71e5edbeb646.jsonl`

---

**Completed** | Created: 2026-05-09 | Priority: P2 | Completed: 2026-05-09

## Resolution

All steps from the Proposed Solution implemented:
- Registered `EPIC` in `REQUIRED_CATEGORIES` with prefix/dir/action
- Created `.issues/epics/.gitkeep` and `templates/epic-sections.json`
- Extended `_NORMALIZED_RE` and `_ISSUE_TYPE_RE` in `issue_parser.py`
- Extended regexes in `cli/issues/show.py` (3), `sync.py` (1), hooks (4)
- Added `epic: str | None = None` to `IssueInfo` with `to_dict`/`from_dict`/`parse_file` wiring
- Added `"EPIC"` to `VALID_ISSUE_TYPES` in `cli_args.py`
- Added `EPIC: str = "35"` to `CliColorsTypeConfig` and `configure_output()`
- Updated `GitHubSyncConfig.label_mapping` default with `"EPIC": "epic"`
- Fixed `issue_history/parsing.py` and `parallel/worker_pool.py` regex wiring
- All 529 tests pass
