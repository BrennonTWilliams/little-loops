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

1. Add `"EPIC"` to display buckets, type_labels, argparse choices, and TYPE_COLOR in CLI display files
2. Update `config-schema.json` to accept EPIC in label_mapping and cli.colors.type
3. Update `GitHubSyncManager` in `sync.py` to handle `epic:` frontmatter field
4. Extend `(BUG|FEAT|ENH)` regex to `(BUG|FEAT|ENH|EPIC)` in all five caller files
5. Document `ll-auto` epic-skip behavior in `auto.py`
6. Add test coverage for EPIC type in search, template, CLI, and sync test files
7. Run extended verify suite and confirm all tests pass

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

### Documentation
- N/A

### Configuration
- `config-schema.json` — must add EPIC before user configs referencing it will validate

## Impact

- **Priority**: P2 — Unblocks the full epic workflow from FEAT-1389; without this, EPIC type is registered but completely invisible
- **Effort**: Medium — 13 files touched, but all changes are surgical additions to existing patterns (no new architecture)
- **Risk**: Low — All changes are additive (new dict keys, extended regex alternations, new argparse choices); existing behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `epic-support`, `cli`, `tooling`

## Session Log
- `/ll:format-issue` - 2026-05-09T22:58:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c185e3de-8e61-493a-b17d-4c388fffb4cc.jsonl`
- `/ll:issue-size-review` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adfa30cd-8f9d-48b3-9e4b-2a81bf6caa05.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
