---
id: FEAT-1406
type: FEAT
priority: P2
status: open
parent_issue: FEAT-1389
captured_at: '2026-05-09T00:00:00Z'
discovered_date: '2026-05-09'
depends_on:
- FEAT-1405
---

# FEAT-1406: EPIC Type — CLI Display, Sync, and Tooling Integration

## Summary

Wire EPIC into all CLI display, sync, and regex-based tooling. Depends on FEAT-1405 (type registration + parser fixes) landing first. This child covers the visible user-facing CLI work: `ll-issues list --type epic`, `ll-sync` epic-to-platform mapping, count/history tooling, and all caller files with hardcoded `(BUG|FEAT|ENH)` regexes.

## Parent Issue

Decomposed from FEAT-1389: Add EPIC as a First-Class Issue Type

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

## Acceptance Criteria

- `ll-issues list --type EPIC` shows epics with child count column
- `ll-issues list` (no filter) includes EPIC bucket in output
- `ll-sync` maps `epic: EPIC-NNN` on child issues to GitHub milestone concept
- `ll-issues count --json` includes EPIC key in output
- `ll-history export --type EPIC` is accepted (not rejected by argparse)
- `deps.py`, `operations.py`, `analysis.py`, `sprint/edit.py`, `recursive-refine.yaml` all match EPIC-NNN IDs
- All new and existing tests pass

## Files to Touch

- `scripts/little_loops/cli/issues/list_cmd.py`
- `scripts/little_loops/cli/issues/search.py`
- `scripts/little_loops/cli/issues/__init__.py`
- `scripts/little_loops/cli/output.py`
- `scripts/little_loops/cli/issues/count_cmd.py`
- `scripts/little_loops/cli/history.py`
- `scripts/little_loops/cli/deps.py`
- `scripts/little_loops/cli/sprint/edit.py`
- `scripts/little_loops/dependency_mapper/operations.py`
- `scripts/little_loops/workflow_sequence/analysis.py`
- `scripts/little_loops/loops/recursive-refine.yaml`
- `scripts/little_loops/sync.py` (epic: platform mapping + label_mapping)
- `config-schema.json` (label_mapping.default + cli.colors.type.properties)
- `scripts/tests/test_issues_search.py`
- `scripts/tests/test_issue_template.py`
- `scripts/tests/test_issues_cli.py`
- `scripts/tests/test_sync.py`

## Session Log
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
