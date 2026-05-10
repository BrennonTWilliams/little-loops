---
id: ENH-1427
type: ENH
priority: P2
status: done
parent_issue: ENH-1422
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-05-10T17:22:15Z
---

# ENH-1427: Decouple Issue Status — ll-issues CLI Code Changes

## Summary

Update production code and tests for `ll-issues list`, `show`, `count`, `search`, and `skip` commands to read status from `IssueInfo.status` frontmatter instead of directory location. Covers all implementation steps 1–12 from ENH-1422.

## Parent Issue

Decomposed from ENH-1422: Decouple Issue Status — ll-issues CLI (list/show/count/search)

## Current Behavior

`_load_issues_with_status()` in `search.py` globs `get_completed_dir()` and `get_deferred_dir()` and hardcodes status strings by bucket (`"active"`, `"completed"`, `"deferred"`). `show.py:_parse_card_fields()` checks `path.parent.name == "completed"` / `"deferred"` to determine display status. `skip.py` guards on `parent_name in ("completed", "deferred")`. The CLI `--status` choices for `list`, `search`, and `count` are `["active", "completed", "deferred", "all"]`, mismatched from `IssueInfo.status` vocabulary.

## Expected Behavior

`_load_issues_with_status()` scans type dirs only and reads `IssueInfo.status` from frontmatter. `show.py:_parse_card_fields()` reads `frontmatter.get("status", "open")` instead of inspecting `path.parent.name`. `skip.py` reads the issue's frontmatter `status` field. CLI `--status` choices expand to `["open", "in_progress", "blocked", "deferred", "done", "cancelled", "all"]` with default `"open"`. All updated tests pass with zero calls to `get_completed_dir()` or `get_deferred_dir()` in the affected functions.

## Motivation

`_load_issues_with_status()` currently globs `get_completed_dir()` and `get_deferred_dir()` and assigns status by bucket name. `show.py` checks `path.parent.name == "completed"`. Removing these directory checks enables issues to live in type-scoped directories regardless of status.

## Proposed Solution

### `search.py`

- `_load_issues_with_status()` (lines 106–150): replace `get_completed_dir()` / `get_deferred_dir()` globs with scanning type dirs only; read `IssueInfo.status` directly instead of assigning `"active"` / `"completed"` / `"deferred"` by bucket
- `cmd_search()`: update `--status` filter string values from `"active"/"completed"/"deferred"` to full vocab: `open|in_progress|blocked|deferred|done|cancelled|all`

### `show.py`

- `_parse_card_fields()` (lines 138–144): replace `path.parent.name == "completed"` / `"deferred"` checks with `frontmatter.get("status", "open")` — a `frontmatter` dict is already available at line 114 from `parse_frontmatter()`; map `"done"` → `"Completed"`, `"deferred"` → `"Deferred"`, `"open"` / `"in_progress"` / `"blocked"` → `"Open"`, etc.
- `_resolve_issue_id()` (lines 80–82): remove explicit `get_completed_dir()` + `get_deferred_dir()` pass; search type dirs only

### `count_cmd.py`

- Lines 26–29: change `include_active = status in ("active", "all")`, `include_completed = status in ("completed", "all")`, `include_deferred = status in ("deferred", "all")` to match the new `--status` vocabulary (e.g. `include_open = status in ("open", "in_progress", "blocked", "all")`, `include_done = status in ("done", "cancelled", "all")`, `include_deferred = status in ("deferred", "all")`)

### `list_cmd.py`

- Line 143: `status_tag = f" [{stat}]" if stat != "active" else ""` — change to `if stat not in ("open", "in_progress")` to suppress the tag for active-equivalent statuses
- Filter logic analogous to `count_cmd.py` — update `include_active/completed/deferred` comparisons to new vocabulary

### `__init__.py`

- Lines 261–266: update `--status` `choices` from `["active","completed","deferred","all"]` to `["open","in_progress","blocked","deferred","done","cancelled","all"]` for all subcommands (list, search, count)

### `skip.py`

- Line 39: replace `if parent_name in ("completed", "deferred"):` with a frontmatter-based check: read the issue file's `status` frontmatter field and guard on `status in ("done", "cancelled", "deferred")` instead of the directory name

### Tests

- `conftest.py`: add `status: open` to fixture issue file content; keep `"completed_dir"` / `"deferred_dir"` keys in fixture config dicts during migration period
- `test_issues_cli.py:test_show_completed_issue` — add `status: done` frontmatter; assert status from frontmatter not path
- `test_issues_cli.py:test_count_status_completed` — add `status: done` frontmatter to issue files; remove `completed/` dir setup
- `test_issues_cli.py:test_count_status_deferred` — same for `status: deferred`
- `test_issues_path.py` — `_resolve_issue_id()` type-dir-only lookup
- `test_issues_search.py:TestSearchStatusFilter` (lines 373–461) — move completed issues to type dirs with `status: done` frontmatter; remove physical `completed/` dir usage in `search_issues_dir` fixture
- `test_cli_output.py:291–292` — remove `get_completed_dir` / `get_deferred_dir` mocks

## Implementation Steps

1. Update `scripts/little_loops/cli/issues/search.py:_load_issues_with_status()` — scan type dirs, read `IssueInfo.status`; update status string vocab
2. Update `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` — status from frontmatter dict
3. Update `scripts/little_loops/cli/issues/show.py:_resolve_issue_id()` — type-dir-only search
4. Update `scripts/little_loops/cli/issues/__init__.py:261–266` — change `--status` `choices` to `["open","in_progress","blocked","deferred","done","cancelled","all"]` for all subcommands
5. Update `scripts/little_loops/cli/issues/list_cmd.py:143` — change `if stat != "active"` to `if stat not in ("open", "in_progress")`; also update filter logic analogous to count_cmd.py
6. Update `scripts/little_loops/cli/issues/count_cmd.py:26–29` — change `include_active/completed/deferred` comparisons to new vocab
7. Update `scripts/little_loops/cli/issues/skip.py:39` — replace directory-name guard with frontmatter `status` check; add `IssueParser(config).parse_file(path)` call before the guard (parser not currently imported in skip.py — add `from little_loops.issue_parser import IssueParser`)
8. Update `scripts/tests/conftest.py` — add `status: open` to fixture files; keep `completed_dir` / `deferred_dir` keys in `sample_config["issues"]` during migration period
9. Update `scripts/tests/test_issues_cli.py` — `test_show_completed_issue`, `test_count_status_completed`, `test_count_status_deferred`
10. Update `scripts/tests/test_issues_path.py` — `_resolve_issue_id()` type-dir-only lookup
11. Update `scripts/tests/test_issues_search.py:TestSearchStatusFilter` — move completed issues to type dirs with `status: done` frontmatter
12. Update `scripts/tests/test_cli_output.py:291–292` — remove `get_completed_dir` / `get_deferred_dir` lambda entries from the inline config dict in `TestIssueListNoColor.test_no_color_produces_plain_text`
13. Add `scripts/tests/test_issues_cli.py:test_skip_done_issue` — write issue with `status: done` frontmatter in a type dir (not `completed/`); assert `cmd_skip` returns error with appropriate message (no existing test covers the frontmatter-based guard path)

## Scope Boundaries

- Documentation changes for the loops guide (`LOOPS_GUIDE.md`) and CLI reference are out of scope; owned by ENH-1428
- Changes to `IssueParser` / `issue_parser.py` are out of scope; the parser already populates `IssueInfo.status` correctly
- Physical migration of `completed/` and `deferred/` directories is out of scope; handled by ENH-1423
- The `ll-sync` command (GitHub sync) is out of scope for this sub-issue

## Impact

- **Priority**: P2 — child issue of ENH-1422; required for issues to live in type-scoped dirs regardless of status
- **Effort**: Large — 13 implementation steps across 11 files (5 source, 6 test), with a new test (step 13)
- **Risk**: Medium — broad test file changes; existing test suite validates behavior; no external API surface changes
- **Breaking Change**: Yes — CLI `--status` vocabulary changes; any caller passing `active`/`completed` values will need updating

## Labels

`enhancement`, `cli`, `status-decoupling`, `testing`

## Files to Modify

- `scripts/little_loops/cli/issues/search.py`
- `scripts/little_loops/cli/issues/show.py`
- `scripts/little_loops/cli/issues/__init__.py`
- `scripts/little_loops/cli/issues/count_cmd.py`
- `scripts/little_loops/cli/issues/list_cmd.py`
- `scripts/little_loops/cli/issues/skip.py`
- `scripts/tests/conftest.py`
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_issues_path.py`
- `scripts/tests/test_issues_search.py`
- `scripts/tests/test_cli_output.py`

## Acceptance Criteria

- `ll-issues list` defaults to showing `open` + `in_progress`; `--status deferred` and `--status done` filters work
- `ll-issues show` displays correct status from `IssueInfo.status` frontmatter
- `ll-issues count --status done` returns correct count without reading `completed/` dir
- `_load_issues_with_status()` makes zero calls to `get_completed_dir()` or `get_deferred_dir()`
- `skip.py` guards on frontmatter `status`, not directory name
- All updated tests pass

## Integration Map

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `cli/issues/search.py` | `_load_issues_with_status()` | globs `get_completed_dir()` / `get_deferred_dir()` | 106–150 |
| `cli/issues/show.py` | `_parse_card_fields()` | `path.parent.name == "completed"` | 137–144 |
| `cli/issues/show.py` | `_resolve_issue_id()` | searches `get_completed_dir()` + `get_deferred_dir()` | 77–82 |
| `cli/issues/skip.py` | guard | `parent_name in ("completed", "deferred")` | 39 |

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/set_scores.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/check_flag.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/check_readiness.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/path_cmd.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged

### Tests

_Wiring pass added by `/ll:wire-issue`:_

Tests confirmed in scope that are **not explicitly named** in Implementation Steps 9–12 but will break:

**`scripts/tests/test_issues_cli.py`** (additional methods beyond the 3 named in Step 9):
- `test_count_status_all` — fixture places issues in physical `completed/` and `deferred/` dirs with old-vocab defaults; must migrate to type dirs + `status:` frontmatter [Agent 3]
- `test_count_status_active_default_unchanged` — relies on `"active"` default concept; test intent must map to `"open"` vocabulary [Agent 3]
- `test_count_json_includes_status` — passes `--status completed` CLI arg (invalid post-argparse change) and asserts `data["status"] == "completed"` (must change to `"done"`) [Agent 3]
- `test_list_status_short` — passes `-S active` which will be rejected by argparse after choices change [Agent 3]
- `test_show_displays_completed_at_for_completed_issue` — creates issue in `completed/` dir with no `status:` frontmatter; asserts `"Status: Completed" in out` via dir-based `_parse_card_fields` logic [Agent 3]
- `test_show_json_includes_timestamps` — creates issue in `completed/` dir; exercises `_parse_card_fields` JSON path [Agent 3]

**`scripts/tests/test_issues_search.py`** — `TestSearchStatusFilter` specific breakages (beyond "move to type dirs"):
- `test_include_completed` (line 374) — asserts `"[completed]"` in `status_tag` output; after fix `stat` is `"done"` so tag becomes `"[done]"` [Agent 3]
- `test_status_completed_only` (line 414) — passes `--status completed` (invalid argparse choice post-change) [Agent 3]
- `test_text_query_with_include_completed` (line 434) — `--include-completed` flag maps to `include_completed=True` in `_load_issues_with_status`; must be re-mapped to new vocabulary [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/LOOPS_GUIDE.md:1161` — YAML loop action uses `ll-issues list --status active`; `"active"` will be an invalid `--status` choice post-change; owned by ENH-1428 but must change before ENH-1427 ships [Agent 2]

### Similar Patterns

- `scripts/tests/test_issue_parser.py:TestIssueInfoStatus` lines 2308–2428 — canonical test pattern; fixture uses `---\nstatus: blocked\n---\n`
- `scripts/tests/test_issue_parser_properties.py:82` — valid status vocabulary: `["open", "in_progress", "blocked", "deferred", "done", "cancelled"]`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Line number corrections (off by 1):**
- `show.py:_parse_card_fields()` status block: actual start is line 137, not 138 (confirmed by read)
- `show.py:_resolve_issue_id()` dir list: actual block is lines 77–82, not 80–82
- `__init__.py` `--status` choices for `count`: actual start is line 260, not 261 (list and search equivalents are at lines 123–129 and 191–196)

**`skip.py:cmd_skip()` does not call `IssueParser.parse_file()`** — it calls `_resolve_issue_id()` to get the `Path`, then reads `path.parent.name`. To guard on frontmatter status instead, the implementation must add a `IssueParser(config).parse_file(path)` call to obtain an `IssueInfo` object, then check `issue_info.status in ("done", "cancelled", "deferred")`. The parser import is not currently present in `skip.py`.

**`_load_issues_with_status()` signature parameters must also change** — the function signature is `(config, include_active: bool, include_completed: bool, include_deferred: bool)`. After the refactor, the `include_active` / `include_completed` parameter names no longer match the new status vocabulary. All three call sites (`cmd_list` at `list_cmd.py:47`, `cmd_count` at `count_cmd.py:31`, `cmd_search` at `search.py`) must be updated together with the signature.

**`search.py` has a separate `--include-completed` flag** — in addition to `--status`, the `search` subcommand has an `--include-completed` boolean flag (visible in `TestSearchStatusFilter.test_include_completed`). This flag is passed to `_load_issues_with_status()` as `include_completed=True`. It must be updated alongside the `--status completed` → `--status done` rename.

**`IssueInfo.status` is already populated by `parse_file()`** — `issue_parser.py:445` reads `frontmatter.get("status", "open")` and assigns it to `IssueInfo.status` (declared at line 255 with default `"open"`). No changes needed to the parser itself.

**Vocabulary mismatch already present in the codebase**: CLI `--status` default is `"active"`; `IssueInfo.status` default is `"open"`. These are different strings for the same concept. Step 4 (`__init__.py` choices update) must change the default from `"active"` to `"open"` in addition to expanding the choices list.

**Test pattern for `skip.py`** — no existing test exercises the frontmatter-based guard path. A new test will be needed in `test_issues_cli.py` that writes an issue with `status: done` frontmatter inside a type dir (not `completed/`) and asserts the skip command returns an error.

### `_load_issues_with_status()` contract change

Current: Returns `list[tuple[IssueInfo, str]]` where `str` is hardcoded `"active"` / `"completed"` / `"deferred"` by directory branch.
After fix: `str` element becomes `issue.status` value from frontmatter (`"open"`, `"in_progress"`, `"blocked"`, `"done"`, etc.). All three consumers (`cmd_list`, `cmd_count`, `cmd_search`) use this tuple's second element for display and filtering.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Update `scripts/little_loops/cli/issues/search.py:cmd_search()` — also has `status_tag = f" [{stat}]" if stat != "active" else ""` (line ~450); change guard to `if stat not in ("open", "in_progress")` — same pattern as Step 5 for `list_cmd.py:143`; not covered by Step 1's `_load_issues_with_status()` description [Agent 2]
15. Update `scripts/tests/test_issues_cli.py` — add the 6 additional breaking tests to Step 9's scope: `test_count_status_all`, `test_count_status_active_default_unchanged`, `test_count_json_includes_status`, `test_list_status_short`, `test_show_displays_completed_at_for_completed_issue`, `test_show_json_includes_timestamps` [Agent 3]
16. Update `scripts/tests/test_issues_search.py:TestSearchStatusFilter` — beyond the fixture migration in Step 11, also update specific assertions: `test_include_completed` (`"[completed]"` tag → `"[done]"`), `test_status_completed_only` (`--status completed` → `--status done`), `test_text_query_with_include_completed` (re-map `--include-completed` to new vocab) [Agent 3]

## Resolution

All 16 implementation steps completed (13 original + 3 wiring-phase additions):

- `search.py`: `_load_issues_with_status()` now scans type dirs only and reads `IssueInfo.status`; signature changed to `(config, include_open, include_done, include_deferred)`; `cmd_search()` maps new `--status` vocab; status tag uses `not in ("open", "in_progress")`
- `show.py`: `_parse_card_fields()` reads `frontmatter.get("status", "open")` with display map (`done`→`Completed` etc.); `_resolve_issue_id()` searches type dirs only
- `skip.py`: guards on `IssueParser(config).parse_file(path).status in ("done", "cancelled", "deferred")`
- `count_cmd.py`, `list_cmd.py`: updated to new `include_open/done/deferred` vocabulary
- `__init__.py`: `--status` choices expanded to `["open","in_progress","blocked","deferred","done","cancelled","all"]` with default `"open"` for list/search/count
- All 11 test files updated; 211 tests pass; 1 pre-existing unrelated failure (`test_marketplace_top_level_version_matches_plugin`)

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T17:22:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b452f5d-0bb3-45eb-b714-8b5472820152.jsonl`
- `/ll:ready-issue` - 2026-05-10T17:08:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2f985c5-455e-4780-9a03-a1b07ee53f38.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbdb0f18-2fde-4290-bc98-ee1851af4af9.jsonl`
- `/ll:wire-issue` - 2026-05-10T17:00:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7dad6dd1-b723-4db0-9063-554e8d0e16fd.jsonl`
- `/ll:refine-issue` - 2026-05-10T16:52:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/100dd3ca-3a8f-4f99-ae7d-8543ece55707.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8de4dc0e-8a1e-41f5-94a2-7daaa289459e.jsonl`
- `/ll:manage-issue` - 2026-05-10T17:22:15Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Open** | Created: 2026-05-10 | Priority: P2
