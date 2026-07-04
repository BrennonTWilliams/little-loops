---
id: EPIC-1406
type: EPIC
priority: P2
status: done

captured_at: '2026-05-09T00:00:00Z'
discovered_date: '2026-05-09'
depends_on:
- FEAT-1405
confidence_score: 100
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
parent: FEAT-1389
completed_at: 2026-05-10T00:00:00Z
---

# EPIC-1406: EPIC Type — CLI Display, Sync, and Tooling Integration

## Summary

Wire EPIC into all CLI display, sync, and regex-based tooling. Depends on FEAT-1405 (type registration + parser fixes) landing first. This child covers the visible user-facing CLI work: `ll-issues list --type epic`, `ll-sync` epic-to-platform mapping, count/history tooling, and all caller files with hardcoded `(BUG|FEAT|ENH)` regexes.

## Parent Issue

Decomposed from FEAT-1389: Add EPIC as a First-Class Issue Type

## Current Behavior

CLI display tools hardcode `(BUG|FEAT|ENH)` patterns in bucket dicts, type label maps, `--type` argparse choices, and regex-based ID scanners. Any EPIC issue in the filesystem is silently dropped from `ll-issues list`, `ll-issues count`, `ll-history export`, and `ll-issues search`. `ll-sync` has no mapping for the `epic:` frontmatter field and will ignore it on push/pull. `config-schema.json` rejects `EPIC` in `label_mapping` and `cli.colors.type` properties due to `"additionalProperties": false`.

## Expected Behavior

After this feature lands, EPIC issues are fully visible and handled across all tooling:
- `ll-issues list` shows an EPIC bucket; `ll-issues list --type EPIC` filters to epics
- `ll-issues count --json` includes `"EPIC": N` in the type breakdown
- `ll-history export --type EPIC` is accepted by argparse without error
- `ll-sync` maps the `epic:` frontmatter field to the correct platform concept (GitHub milestone / Linear epic) on push/pull
- All regex-based ID scanners (`deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml`) match `EPIC-NNN` identifiers
- `config-schema.json` accepts `EPIC` in `label_mapping.default` and `cli.colors.type.properties`

## Motivation

FEAT-1405 registers EPIC as a first-class type in the data layer, but without this tooling pass users cannot see, count, or sync epic issues. The silent-drop behavior creates confusion: epics exist in the filesystem yet are invisible in every display command. This blocks the full epic workflow from FEAT-1389 and makes the new type effectively unusable in practice.

## Use Case

A developer creates `EPIC-001-auth-overhaul.md` to track a multi-sprint initiative. They run `ll-issues list` expecting to see it alongside bugs and features — it doesn't appear. They run `ll-issues count --json` to get a type breakdown for a status report — EPIC is absent. They run `ll-sync push` to mirror the epic to GitHub — the `epic:` field is silently ignored. After this feature, all three commands work correctly and EPIC issues are fully visible in the CLI.

## Proposed Solution

### Step 4 — Fix CLI display

- `scripts/little_loops/cli/issues/list_cmd.py` — `cmd_list()` has hardcoded `buckets = {"BUG": [], "FEAT": [], "ENH": []}` and `type_labels` dict; add `"EPIC"` to both so EPIC issues are not silently dropped from grouped display
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern; same fix
- `scripts/little_loops/cli/issues/__init__.py` — `--type` argument `choices=["BUG", "FEAT", "ENH"]`; add `"EPIC"`
- `scripts/little_loops/cli/output.py` — `TYPE_COLOR` dict; add `"EPIC": "35"` (purple/magenta)

### Step 6 — Update ll-sync for epic: field

- `config-schema.json` — add `"EPIC"` to `label_mapping.default` and to `cli.colors.type.properties` block (note: `"additionalProperties": false` means user config will be schema-rejected without this)
- `scripts/little_loops/sync.py` — update `GitHubSyncManager` to map `epic:` field on child issues to GitHub milestone concept in push/pull paths

### Step 13 — Update count_cmd.py

`scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` dict in `count_cmd()` so EPIC issues appear in JSON count output rather than silently dropping.

### Step 14 — Update history.py

`scripts/little_loops/cli/history.py` — add `"EPIC"` to `--type` argument `choices=["BUG", "FEAT", "ENH"]` for `ll-history export`.

### Step 15 — Update regex-based callers

Extend `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)` in:

1. `scripts/little_loops/cli/deps.py` — `_load_issues_and_contents()`: `re.search(r"(BUG|FEAT|ENH)-(\d+)", f.name)`
2. `scripts/little_loops/dependency_mapper/operations.py` — `gather_all_issue_ids()`: same hardcoded regex
3. `scripts/little_loops/workflow_sequence/analysis.py` — `ISSUE_PATTERN = re.compile(r"(?:BUG|FEAT|ENH)-\d+", re.IGNORECASE)` at module level
4. `scripts/little_loops/cli/sprint/edit.py` — `re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)` in completed directory scan
5. `scripts/little_loops/loops/recursive-refine.yaml` — inline `re.search(r'(BUG|FEAT|ENH)-(\d+)', ...)` in YAML loop script block

Also note: `scripts/little_loops/cli/auto.py` — document (or enforce via `--type BUG,FEAT,ENH` default) that `ll-auto` should skip epics since they are containers, not implementable units.

### Step 17 — Add new tests

- `scripts/tests/test_issues_search.py` — add `TestSearchTypeFilter.test_filter_epic` passing `--type EPIC` to `ll-issues search`; follow pattern of `test_filter_bug` and `test_filter_feat`
- `scripts/tests/test_issue_template.py` — add `"EPIC"` to `TestLoadIssueSections.test_load_default` parametrize list (requires `templates/epic-sections.json` from FEAT-1405 to exist)
- `scripts/tests/test_issues_cli.py` — add tests: `ll-issues list --type EPIC` shows epics with child count; `ll-issues next-id` EPIC allocation
- `scripts/tests/test_sync.py` — add test: `epic:` frontmatter field mapping to platform parent/milestone

### Step 20 — Extended verify

```bash
python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py scripts/tests/test_sync.py scripts/tests/test_cli_args.py scripts/tests/test_cli_output.py scripts/tests/test_issues_search.py scripts/tests/test_issue_template.py scripts/tests/test_config.py -v
```

## Implementation Steps

1. **Add EPIC to all six `choices=` lists in `cli/issues/__init__.py`** (lines 116, 176, 253, 274, 295, 330) — each `add_argument("--type", ..., choices=["BUG", "FEAT", "ENH"])` needs `"EPIC"` appended
2. **Add EPIC to `buckets` and `type_labels` dicts in `cmd_list()` (`list_cmd.py:127`)** and `cmd_search()` (`search.py` table-format path) — `{"BUG": [], "FEAT": [], "ENH": []}` → add `"EPIC": []` and `"EPIC": "Epics"` to `type_labels`
3. **Add `"EPIC": 0` to `by_type` dict in `count_cmd.py` `cmd_count()`** so JSON output includes EPIC count
4. **Add EPIC to `--type` choices in `history.py` `main_history()` `export` subparser** (line with `choices=["BUG", "FEAT", "ENH"]`)
5. **Extend regex in all five caller files**: `deps.py:_load_issues()`, `sprint/edit.py:_cmd_sprint_edit()`, `dependency_mapper/operations.py:gather_all_issue_ids()`, `workflow_sequence/analysis.py:ISSUE_PATTERN`, `loops/recursive-refine.yaml` inline Python block — all `(BUG|FEAT|ENH)` → `(BUG|FEAT|ENH|EPIC)`
6. **Check `cli/issues/refine_status.py`** for BUG|FEAT|ENH regex and extend if found
7. **Skip `output.py`, `config-schema.json`, `sync.py`, `auto.py`** — already EPIC-aware from FEAT-1405; skip `sync.py` epic: field GitHub mapping (defer per research findings)
8. **Update `conftest.py` fixtures**: add `epics/` directory and a sample `P2-EPIC-001-test-epic.md` file to `search_issues_dir` (and/or relevant fixture), register `epics` category in the fixture config
9. **Add tests**: `test_issues_search.py:TestSearchTypeFilter.test_filter_epic` (follow `test_filter_bug` pattern with `--type EPIC`); `test_issues_cli.py` for `ll-issues list --type EPIC` and `ll-issues count --json` EPIC key; skip `test_issue_template.py` (already done) and `test_sync.py epic: field` (deferred)
10. **Run extended verify** per Step 20 verify command in Proposed Solution

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/little_loops/cli_args.py` `add_type_arg()` — add EPIC to the `--type` help string example text (cosmetic but sets user expectations)
12. Update `scripts/little_loops/issues/anchor_sweep.py` `_ACTIVE_CATEGORIES` — add `"epics"` to tuple so `ll-issues anchor-sweep` scans EPIC files; without this, all EPIC issues are silently excluded from anchor sweeps
13. Fix `scripts/tests/test_loops_recursive_refine.py:780` `build_parent_map()` — extend inline regex from `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)` to match the primary YAML change
14. Add EPIC assertions to `scripts/tests/test_issues_cli.py` — `by_type["EPIC"] == 0` in `test_count_json_output`; `"Epics (0)"` header in `test_list_grouped_output_has_headers` and `test_list_empty_groups_shown`; add `issues_dir_with_epic` fixture
15. Add `TestExportTypeScoring.test_export_type_epic` to `scripts/tests/test_issue_history_cli.py`
16. Add `epics/` dir + `P2-EPIC-001-foo.md` to `TestGatherAllIssueIds.test_scans_all_categories` in `scripts/tests/test_dependency_mapper.py`
17. Add EPIC-nnn to `TestExtractEntities.test_issue_ids` test content in `scripts/tests/test_workflow_sequence_analyzer.py`
18. Update `scripts/tests/conftest.py` `issues_dir` fixture: create `epics/` subdir; add `epics` category to `sample_config` fixture
19. Update `docs/reference/CLI.md` — add EPIC to all 10 `--type` table rows
20. Update `docs/reference/API.md` — fix 4 stale type references (~lines 151, 674, 3095, 3177)
21. Update `docs/reference/CONFIGURATION.md` — add EPIC to 4 sample config blocks
22. Update `commands/normalize-issues.md` — extend all 5 `(BUG|FEAT|ENH)` occurrences to `(BUG|FEAT|ENH|EPIC)` (critical: prevents EPIC files being marked invalid)
23. Update `commands/open-pr.md:~105`, `commands/create-sprint.md:~148`, `commands/refine-issue.md:~161,410` — extend type lists/regex to include EPIC
24. Update `skills/format-issue/templates.md:~276,314`, `skills/decide-issue/SKILL.md:~296`, `skills/issue-size-review/SKILL.md:~211` — extend `[BUG|FEAT|ENH]` template type fields to include EPIC

## Acceptance Criteria

- `ll-issues list --type EPIC` shows epics with child count column
- `ll-issues list` (no filter) includes EPIC bucket in output
- `ll-sync` maps `epic: EPIC-NNN` on child issues to GitHub milestone concept
- `ll-issues count --json` includes EPIC key in output
- `ll-history export --type EPIC` is accepted (not rejected by argparse)
- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- All new and existing tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — add EPIC to `buckets` and `type_labels` dicts in `cmd_list()`
- `scripts/little_loops/cli/issues/search.py` — same `buckets`/`type_labels` pattern
- `scripts/little_loops/cli/issues/__init__.py` — add EPIC to `--type` argparse choices
- `scripts/little_loops/cli/output.py` — add `"EPIC": "35"` to `TYPE_COLOR`
- `scripts/little_loops/cli/issues/count_cmd.py` — add `"EPIC": 0` to `by_type` in `count_cmd()`
- `scripts/little_loops/cli/history.py` — add EPIC to `--type` argparse choices
- `scripts/little_loops/cli/deps.py` — extend regex in `_load_issues_and_contents()`
- `scripts/little_loops/cli/sprint/edit.py` — extend regex in completed directory scan
- `scripts/little_loops/dependency_mapper/operations.py` — extend regex in `gather_all_issue_ids()`
- `scripts/little_loops/workflow_sequence/analysis.py` — extend `ISSUE_PATTERN` module-level constant
- `scripts/little_loops/loops/recursive-refine.yaml` — extend inline regex in script block
- `scripts/little_loops/sync.py` — update `GitHubSyncManager` push/pull paths for `epic:` field
- `config-schema.json` — add EPIC to `label_mapping.default` and `cli.colors.type.properties`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli_args.py` — update `add_type_arg()` help string example from `"BUG, FEAT, ENH"` to include EPIC (affects help text for `ll-auto`, `ll-parallel`, `ll-sprint`)
- `scripts/little_loops/issues/anchor_sweep.py` — add `"epics"` to `_ACTIVE_CATEGORIES` tuple in `sweep_issues()` so `ll-issues anchor-sweep` does not silently skip EPIC issue files

### Dependent Files (Callers/Importers)
- Any code importing `TYPE_COLOR` from `output.py` will automatically gain EPIC color support
- `ll-issues list`, `ll-issues search`, `ll-issues count`, `ll-history export` — all become EPIC-aware via their respective CLI files
- `ll-deps`, `ll-sprint` — become EPIC-aware via `deps.py` and `sprint/edit.py` regex fixes

### Similar Patterns
- All regex extensions follow the same `(BUG|FEAT|ENH)` → `(BUG|FEAT|ENH|EPIC)` pattern — update consistently across all five sites
- Bucket/type_label dict additions follow the same pattern in `list_cmd.py` and `search.py`

### Tests
- `scripts/tests/test_issues_search.py` — add `test_filter_epic`
- `scripts/tests/test_issue_template.py` — add EPIC to `test_load_default` parametrize list
- `scripts/tests/test_issues_cli.py` — add `ll-issues list --type EPIC` and next-id EPIC tests
- `scripts/tests/test_sync.py` — add `epic:` field mapping test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_recursive_refine.py:780` — update inline `build_parent_map()` regex from `(BUG|FEAT|ENH)` to `(BUG|FEAT|ENH|EPIC)`; **will silently drop EPIC child issue IDs if not fixed**
- `scripts/tests/test_issues_cli.py` — add `assert data["by_type"]["EPIC"] == 0` to `TestIssuesCLICount.test_count_json_output`; add `assert "Epics (0)" in captured.out` to `TestIssuesCLIList.test_list_grouped_output_has_headers` and `test_list_empty_groups_shown`; add `issues_dir_with_epic` fixture mirroring `issues_dir_with_enh`
- `scripts/tests/test_issue_history_cli.py` — add `TestExportTypeScoring.test_export_type_epic` mirroring `test_export_type_feat` pattern (assert `--type EPIC` forwards `issue_type='EPIC'` to `synthesize_docs`)
- `scripts/tests/test_dependency_mapper.py` — update `TestGatherAllIssueIds.test_scans_all_categories` to create `epics/` subdir with a sample `P2-EPIC-001-foo.md` file and assert `"EPIC-001"` appears in returned ids
- `scripts/tests/test_workflow_sequence_analyzer.py` — update `TestExtractEntities.test_issue_ids` to include `EPIC-001` in test content and assert it is extracted
- `scripts/tests/conftest.py` — update `issues_dir` fixture to create `epics/` subdirectory; add `epics` category entry to `sample_config` fixture (required by new `test_filter_epic` and EPIC list/count tests)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — 10 `--type` flag description table rows list `BUG, FEAT, ENH` without EPIC: `ll-issues list`, `ll-issues search`, `ll-issues count`, `ll-issues sequence`, `ll-issues impact-effort`, `ll-issues refine-status`, `ll-history export`, `ll-auto`, `ll-parallel`, `ll-sprint` tables, and the common flags table at top
- `docs/reference/API.md` — 4 stale references: `cli.colors.type.*` description row (line ~151), `is_normalized()` Returns: regex doc (line ~674), `ll-issues search --type` options (line ~3095), `ll-history export --type` options (line ~3177)
- `docs/reference/CONFIGURATION.md` — 4 sample config blocks missing EPIC: `issues.categories` example, `label_mapping` example, `cli.colors.type` example, `cli.colors.type` section table rows

### Configuration
- `config-schema.json` — must add EPIC before user configs referencing it will validate

### CLI/Command Coupling

_Wiring pass added by `/ll:wire-issue`:_
- `commands/normalize-issues.md` — 5 occurrences of `(BUG|FEAT|ENH)` in bash snippets and prose (scan grep ~line 148, ID extraction ~line 166, category mapping table ~lines 232–234, validation regex ~line 451, type misclassification pseudocode ~line 210); EPIC files would be incorrectly flagged as invalid without these updates
- `commands/open-pr.md:~105` — auto-link regex `(BUG|FEAT|ENH)-[0-9]+` misses EPIC branch names (e.g. `feature/EPIC-42-description`)
- `commands/create-sprint.md:~148` — "Is Normalized" prose documents filename pattern as `^P[0-5]-(BUG|FEAT|ENH)-…`, omitting EPIC
- `commands/refine-issue.md:~161,410` — output template field `Type: [BUG|FEAT|ENH]` would not produce `EPIC` as a type value
- `skills/format-issue/templates.md:~276,314` — same `Type: [BUG|FEAT|ENH]` template field
- `skills/decide-issue/SKILL.md:~296` — type template field omits EPIC
- `skills/issue-size-review/SKILL.md:~211` — type template field omits EPIC

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Already done by FEAT-1405 (skip these, no changes needed):**
- `scripts/little_loops/cli/output.py` — `TYPE_COLOR` already has `"EPIC": "35"`; `CliColorsTypeConfig` in `config/cli.py` also has it; `configure_output()` already merges it. **Remove from Files to Modify.**
- `config-schema.json` — `sync.github.label_mapping` default already has `"EPIC": "epic"` and `cli.colors.type` already has `"EPIC": "35"`. **Remove from Files to Modify.**
- `scripts/little_loops/sync.py` `_extract_issue_id()` regex already uses `(BUG|FEAT|ENH|EPIC)`; `category_map` in `reopen_issues()` already has `"EPIC": "epics"`. The label-mapping push/pull path works via `_get_labels_for_issue()` + `_determine_issue_type()` since `label_mapping` already includes EPIC.
- `templates/epic-sections.json` — already exists with `Goal`, `Scope`, `Children`, `Success Metrics` sections.
- `scripts/tests/test_issue_template.py` `TestLoadIssueSections.test_load_default` — already parametrizes `["BUG", "FEAT", "ENH", "EPIC"]`. **No new test needed.**
- `scripts/tests/test_sync.py` — `test_extract_issue_id_epic` and `test_reopen_epic_from_completed` already exist.
- `scripts/little_loops/cli/auto.py` — already fully EPIC-aware via `VALID_ISSUE_TYPES` and `AutoManager._get_next_issue()`. **No changes needed.**

**Expanded scope (additional files not in the original Integration Map):**
- `scripts/little_loops/cli/issues/__init__.py` has **6 subparsers** with `choices=["BUG", "FEAT", "ENH"]`, not 3: `list` (line 116), `search` (line 176), `count` (line 253), `sequence` (line 274), `impact-effort` (line 295), `refine-status` (line 330). All six need `"EPIC"` added.
- `scripts/little_loops/cli/issues/refine_status.py` — contains a BUG|FEAT|ENH regex; verify if it needs extending (check during implementation).
- `scripts/tests/conftest.py` — `sample_config` / `search_issues_dir` fixtures do not include an `epics` category directory. New EPIC tests (`test_filter_epic`, `ll-issues list --type EPIC`) will need the fixture updated to create an `epics/` subdirectory with a sample EPIC issue file and register `epics` in the fixture config.

**Clarifications on ambiguous items:**
- `scripts/little_loops/cli/issues/search.py` table-format drop is partial: only the `--format table` (default) path drops EPIC issues; `--format ids` and `--format list` paths do not use `buckets` and already output EPIC issues correctly.
- `scripts/little_loops/sync.py` `epic:` frontmatter field: GitHub Issues has no native "epic" field. Storing the parent EPIC reference on child issues (the `epic: EPIC-NNN` frontmatter) would require either (a) a custom label like `parent:EPIC-001`, (b) encoding it in the body, or (c) skipping sync of this field entirely with a doc note. Recommend option (c) for now — the `epic:` field round-trips through local frontmatter correctly already; GitHub-side representation is a scope concern for a later issue.

## Impact

- **Priority**: P2 — Unblocks the full epic workflow from FEAT-1389; without this, EPIC type is registered but completely invisible
- **Effort**: Medium — 13 files touched, but all changes are surgical additions to existing patterns (no new architecture)
- **Risk**: Low — All changes are additive (new dict keys, extended regex alternations, new argparse choices); existing behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `epic-support`, `cli`, `tooling`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-09_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- Wide file surface: 22+ files touched across source, tests, docs, and commands/skills — each individual change is a 1-2 line additive edit, but the breadth creates coordination risk (missing a site leaves a silent inconsistency in EPIC visibility)
- `ISSUE_PATTERN` in `workflow_sequence/analysis.py` is imported by 6+ modules (`dependency_mapper/__init__.py`, `operations.py`, `issue_history/__init__.py`, `history.py`, `workflow_sequence/__init__.py`) — the `re.IGNORECASE` flag means the extension is safe, but worth verifying no caller depends on case-sensitive matching

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-09T23:19:49 - `bc6cf2a8-dd50-4817-9fa7-649612acf79b.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `02774f34-2c4a-488f-b0f8-7452c10aac7c.jsonl`
- `/ll:wire-issue` - 2026-05-09T23:13:29 - `db074448-0206-4278-9820-40c4b715203c.jsonl`
- `/ll:refine-issue` - 2026-05-09T23:05:43 - `b5ea299e-2cb3-4a1e-b837-cc4bdbabbd71.jsonl`
- `/ll:format-issue` - 2026-05-09T22:58:07 - `c185e3de-8e61-493a-b17d-4c388fffb4cc.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `bc6cf2a8-dd50-4817-9fa7-649612acf79b.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-09
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1409: EPIC Type — CLI Source, Regex Extensions, and Tests
- FEAT-1407: EPIC Type — Skills, Commands, and Documentation Updates (pre-existing sibling covers wiring items 19-24)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `cli/output.py` (TYPE_COLOR dict) and `config-schema.json` were both implemented by FEAT-1405, not this issue. Remove these from any future re-implementation of FEAT-1406. The canonical owner is FEAT-1405; FEAT-1406's integration map entries for these files are stale. All documentation updates (`docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/OUTPUT_STYLING.md`, `docs/reference/CONFIGURATION.md`, `.claude/CLAUDE.md`) are owned by FEAT-1407 — do not re-implement here.

---

**Open** | Created: 2026-05-09 | Priority: P2
