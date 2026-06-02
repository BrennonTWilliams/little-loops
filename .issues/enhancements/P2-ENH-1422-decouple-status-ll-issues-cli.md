---
id: ENH-1422
type: ENH
priority: P2
status: done

confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
parent: ENH-1419
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1422: Decouple Issue Status — ll-issues CLI (list/show/count/search)

## Summary

Update `ll-issues list`, `show`, `count`, and `search` commands to read status from `IssueInfo.status` frontmatter instead of directory location. Depends on ENH-1417. Can run in parallel with ENH-1423, ENH-1424, ENH-1425, ENH-1426 after ENH-1417 lands.

## Parent Issue

Decomposed from ENH-1419: Decouple Issue Status — CLI, Sync, Sprint Runner, and Parallel Discovery

## Motivation

`_load_issues_with_status()` currently globs `get_completed_dir()` and `get_deferred_dir()` and assigns status by bucket name. `show.py` checks `path.parent.name == "completed"`. Removing these directory checks enables issues to live in type-scoped directories regardless of status.

## Proposed Solution

### `search.py`

- `_load_issues_with_status()` (lines 106–150): replace `get_completed_dir()` / `get_deferred_dir()` globs with scanning type dirs only; read `IssueInfo.status` directly instead of assigning `"active"` / `"completed"` / `"deferred"` by bucket
- `cmd_search()`: update `--status` filter string values from `"active"/"completed"/"deferred"` to full vocab: `open|in_progress|blocked|deferred|done|cancelled|all`

### `show.py`

- `_parse_card_fields()` (lines 138–144): replace `path.parent.name == "completed"` / `"deferred"` checks with `frontmatter.get("status", "open")` — a `frontmatter` dict is already available at line 114 from `parse_frontmatter()`; map `"done"` → `"Completed"`, `"deferred"` → `"Deferred"`, `"open"` / `"in_progress"` / `"blocked"` → `"Open"`, etc. Note: there is no `IssueInfo` object inside `_parse_card_fields()`, so use the raw `frontmatter` dict directly.
- `_resolve_issue_id()` (lines 80–82): remove explicit `get_completed_dir()` + `get_deferred_dir()` pass; search type dirs only

### `count_cmd.py`

- The `--status` choices are defined in `__init__.py:261–266` (not inside `count_cmd.py` itself) with `choices=["active", "completed", "deferred", "all"]` — update there to `open|in_progress|blocked|deferred|done|cancelled|all`
- `count_cmd.py` itself contains no direct directory references; fix propagates from `_load_issues_with_status()`

### `list_cmd.py`

- Calls `_load_issues_with_status()` at line 38 — inherits the fix from `search.py`
- **Behavioral change required at line 143**: `status_tag = f" [{stat}]" if stat != "active" else ""`  — after the vocab change `stat` will be `"open"` not `"active"`, so this predicate needs updating (e.g. `stat not in ("open", "in_progress")` to suppress the tag for active-equivalent statuses)
- Line 113 JSON output branch `"status": stat` will be corrected automatically since `stat` comes from `issue.status`

### `conftest.py`

- Add `status: open` to fixture issue file content (needed for all status-aware tests)
- Keep `"completed_dir"` / `"deferred_dir"` keys in fixture config dicts during migration period; remove after ENH-1420 lands

## Implementation Steps

1. Update `scripts/little_loops/cli/issues/search.py:_load_issues_with_status()` — scan type dirs, read `IssueInfo.status`; update status string vocab
2. Update `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` — status from `info.status`
3. Update `scripts/little_loops/cli/issues/show.py:_resolve_issue_id()` — type-dir-only search
4. Update `scripts/little_loops/cli/issues/__init__.py:261–266` — change `--status` `choices` from `["active","completed","deferred","all"]` to `["open","in_progress","blocked","deferred","done","cancelled","all"]` for all subcommands (list, search, count)
5. Update `scripts/little_loops/cli/issues/list_cmd.py:143` — change `if stat != "active"` to `if stat not in ("open", "in_progress")` (or equivalent) so the status tag is suppressed for active-equivalent statuses; no other direct directory references exist
6. Update `scripts/tests/conftest.py` — add `status: open` to fixture files; keep migration keys
7. Update `scripts/tests/test_issues_cli.py`:
   - `test_show_completed_issue` — add `status: done` frontmatter; assert status from frontmatter not path
   - `test_count_status_completed` — add `status: done` frontmatter to issue files; remove `completed/` dir setup
   - `test_count_status_deferred` — same for `status: deferred`
8. Update `scripts/tests/test_issues_path.py` — `_resolve_issue_id()` type-dir-only lookup
9. Update `scripts/tests/test_issues_search.py:TestSearchStatusFilter` (lines 373–461) — move completed issues to type dirs with `status: done` frontmatter; remove physical `completed/` dir usage in `search_issues_dir` fixture (lines 20–72)
10. Update `scripts/tests/test_cli_output.py:291–292` — remove `get_completed_dir` / `get_deferred_dir` mocks

## Files to Modify

- `scripts/little_loops/cli/issues/search.py`
- `scripts/little_loops/cli/issues/show.py`
- `scripts/little_loops/cli/issues/__init__.py` (--status choices for all subcommands)
- `scripts/little_loops/cli/issues/count_cmd.py` — lines 26–29: `include_active = status in ("active", "all")`, `include_completed = status in ("completed", "all")`, `include_deferred = status in ("deferred", "all")` — these compare the raw argparse `--status` value and must be updated to new vocabulary (`"open"/"in_progress"/"blocked"` → active; `"done"/"cancelled"` → completed)
- `scripts/little_loops/cli/issues/list_cmd.py` (line 143 tag predicate; also `include_active/completed/deferred` filter logic analogous to count_cmd.py)
- `scripts/little_loops/cli/issues/skip.py` — line 39: `if parent_name in ("completed", "deferred"):` uses directory name to guard against skipping a closed issue; must change to read frontmatter `status` field instead
- `scripts/tests/conftest.py`
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_issues_path.py`
- `scripts/tests/test_issues_search.py`
- `scripts/tests/test_cli_output.py`
- `docs/reference/CLI.md` (--status choices tables and examples)
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` ("Directory location determines CLI bucketing" statement)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/little_loops/cli/issues/count_cmd.py:26–29` — change `include_active = status in ("active", "all")`, `include_completed = status in ("completed", "all")`, `include_deferred = status in ("deferred", "all")` to match the new `--status` vocabulary (e.g. `include_open = status in ("open", "in_progress", "blocked", "all")`, `include_done = status in ("done", "cancelled", "all")`, `include_deferred = status in ("deferred", "all")`)
12. Update `scripts/little_loops/cli/issues/skip.py:39` — replace `if parent_name in ("completed", "deferred"):` with a frontmatter-based check: read the issue file's `status` frontmatter field and guard on `status in ("done", "cancelled", "deferred")` instead of the directory name
13. Update `docs/reference/CLI.md` — change `--status` choices in all three subcommand tables (list, search, count) from `active/completed/deferred/all` to the new vocabulary; update `ll-issues count --status completed` example to `--status done`
14. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — revise "Directory location determines CLI bucketing" to describe frontmatter-based status; update vocabulary table and any directory-move instructions

## Acceptance Criteria

- `ll-issues list` defaults to showing `open` + `in_progress`; `--status deferred` and `--status done` filters work
- `ll-issues show` displays correct status from `IssueInfo.status` frontmatter
- `ll-issues count --status done` returns correct count without reading `completed/` dir
- `_load_issues_with_status()` makes zero calls to `get_completed_dir()` or `get_deferred_dir()`
- All updated tests pass

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/set_scores.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/check_flag.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/check_readiness.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/path_cmd.py` — imports `_resolve_issue_id()` from `show.py`; no changes needed if signature is unchanged
- `scripts/little_loops/cli/issues/skip.py` — imports `_resolve_issue_id()` AND has its own directory guard at line 39: `if parent_name in ("completed", "deferred"):` — **this is a separate coupling that needs its own fix** (see Wiring Phase in Implementation Steps)

### Key Anchors

| File | Function | Directory Logic | Line(s) |
|------|----------|-----------------|---------|
| `cli/issues/search.py` | `_load_issues_with_status()` | globs `get_completed_dir()` / `get_deferred_dir()` | 106–150 |
| `cli/issues/show.py` | `_parse_card_fields()` | `path.parent.name == "completed"` | 138–144 |
| `cli/issues/show.py` | `_resolve_issue_id()` | searches `get_completed_dir()` + `get_deferred_dir()` | 80–82 |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `--status` choices listed as `active` (default), `completed`, `deferred`, `all` in three tables (lines ~501, ~515, ~546) and example `ll-issues count --status completed` at line ~691; all must be updated to new vocabulary
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — explicitly states "**Directory location determines CLI bucketing.**" at line ~118; this is the precise invariant being invalidated and must be updated to describe frontmatter-based status

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_output.py::TestIssueListNoColor.test_no_color_produces_plain_text` — directly calls `cmd_list` with a hand-built mock config; mock-returned `IssueInfo` objects may need `status` field populated if `cmd_list` reads `IssueInfo.status` for filtering or display after the change

### Similar Patterns

- `scripts/tests/test_issue_parser.py:TestIssueInfoStatus` lines 2308–2428 — canonical test pattern; fixture uses `---\nstatus: blocked\n---\n`
- `scripts/tests/test_issue_parser_properties.py:82` — valid status vocabulary: `["open", "in_progress", "blocked", "deferred", "done", "cancelled"]`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional directory-status locations (not in Key Anchors above):**
- `scripts/little_loops/cli/issues/__init__.py:261–266` — `--status` `choices=["active","completed","deferred","all"]` for list/search/count; this is the argparse definition, separate from `count_cmd.py`
- `scripts/little_loops/cli/issues/list_cmd.py:143` — `status_tag = f" [{stat}]" if stat != "active" else ""` — hardcoded `"active"` sentinel; after vocab change `stat` will be `"open"`, so tag will appear for all open issues unless updated
- `scripts/little_loops/cli/issues/list_cmd.py:113` — JSON output `"status": stat` (auto-corrected by `_load_issues_with_status()` fix, no separate change needed)

**`_load_issues_with_status()` current return contract:**
- Returns `list[tuple[IssueInfo, str]]` where `str` is hardcoded `"active"` / `"completed"` / `"deferred"` by directory branch
- After fix: `str` element becomes `issue.status` value from frontmatter (`"open"`, `"in_progress"`, `"blocked"`, `"done"`, etc.)
- All three consumers (`cmd_list`, `cmd_count`, `cmd_search`) use this tuple's second element for display and filtering

**`_parse_card_fields()` implementation detail:**
- Already calls `parse_frontmatter(path)` at line 114 and stores result as `frontmatter` dict
- Lines 138–144 then ignore `frontmatter["status"]` and derive status from `path.parent.name`
- Fix: `status_raw = frontmatter.get("status", "open")` then map to display string (no `IssueInfo` object available in this function)

**Test fixture current state (confirmed by analysis):**
- `conftest.py:issues_dir` fixture (lines 126–160): writes plain markdown without any YAML frontmatter — `status: open` must be added per step 6
- `test_issues_search.py:search_issues_dir` fixture (lines 19–72): `P1-BUG-003-fixed-login.md` written to `completed/` with no `status:` frontmatter — must move to a type dir with `status: done` in step 9
- `test_issues_cli.py:test_show_completed_issue` (line 1228): writes file directly to `completed/` dir, asserts `"Status: Completed"` — no `status:` frontmatter currently
- `test_issues_cli.py:test_count_status_completed` (line 2232), `test_count_status_deferred` (line 2263): write files directly into `completed_dir` / `deferred_dir` without `status:` frontmatter
- `test_cli_output.py:291–292`: uses lambda-based `get_completed_dir` / `get_deferred_dir` inline mocks on a dynamically-built config object

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Broad change surface (13 files, Local per-site depth)**: Vocabulary transition from `"active"/"completed"/"deferred"` to `"open"/"in_progress"/"blocked"/"done"/"cancelled"` touches 6 production files and 4 test files; each predicate must be individually updated — any missed `status in ("active", ...)` comparison will silently misfilter without a compile error
- **`list_cmd.py:146` cosmetic gap**: Footer string `"Total: N active issues"` is hardcoded and not addressed in the implementation steps; after the vocab change it remains technically accurate but semantically inconsistent with the new status model

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-10T16:47:36 - `8de4dc0e-8a1e-41f5-94a2-7daaa289459e.jsonl`
- `/ll:refine-issue` - 2026-05-10T16:35:02 - `cd815340-befe-4ac6-be99-c7eb1fcf40df.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `c6b1dd20-403d-4bd6-8144-216e44129420.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00Z
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `3bd3fb7c-c4db-4606-aebf-3f3a746fba7b.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `8de4dc0e-8a1e-41f5-94a2-7daaa289459e.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1427: Decouple Issue Status — ll-issues CLI Code Changes
- ENH-1428: Decouple Issue Status — ll-issues CLI Documentation Updates

---

**Decomposed** | Created: 2026-05-10 | Priority: P2
