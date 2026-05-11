---
id: ENH-1393
type: ENH
priority: P3
status: done
captured_at: '2026-05-09T20:26:09Z'
completed_at: '2026-05-11T03:51:06Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
relates_to:
- FEAT-1389
- ENH-1390
- ENH-1391
- ENH-1392
confidence_score: 90
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1393: Add Sprint/Milestone Field to Issue Frontmatter

## Summary

Add a `milestone:` field to issue frontmatter so issues carry a bidirectional link to the sprint or milestone they belong to. Currently sprint files reference issues, but issues have no back-reference — making it invisible to platform sync and requiring full sprint file parsing to answer "which sprint is this issue in?".

## Current Behavior

Sprint definitions (`.ll/sprints/`) list issue IDs, but individual issue files have no `milestone:` or `sprint:` field. The relationship is one-directional: sprint → issues. To find which sprint an issue belongs to, you must scan all sprint files. When syncing to GitHub, JIRA, ADO, or Linear, there is no source field to populate the platform's milestone/sprint/cycle assignment.

## Expected Behavior

- `milestone: sprint-name` (or `milestone: MILESTONE-NNN`) is a recognized frontmatter field on issues
- `ll-issues list` supports `--milestone <name>` filter
- When `ll-sprint` assigns an issue to a sprint, it writes the `milestone:` field back to the issue file
- `ll-sync` maps `milestone:` to the platform's sprint/milestone/cycle concept:
  - GitHub: milestone
  - JIRA: sprint (via Agile API)
  - ADO: iteration path
  - Linear: cycle
- The field is optional — issues not in a sprint have no `milestone:` field

## Motivation

- **Sync completeness**: Without `milestone:` on the issue, `ll-sync` cannot assign issues to GitHub milestones or JIRA sprints. The platform shows unassigned issues even though sprint planning was done locally.
- **Discoverability**: "What sprint is FEAT-1389 in?" currently requires grepping sprint files. With `milestone:` it's `ll-issues show FEAT-1389`.
- **Bidirectional consistency**: If `ll-sprint` modifies which issues are in a sprint, it should update both the sprint file and the issue's `milestone:` field atomically.
- **Platform compatibility**: GitHub milestones, JIRA sprints, ADO iterations, and Linear cycles all associate issues to a sprint/milestone via a field on the issue, not a separate file.

## Proposed Solution

1. Add `milestone:` as a recognized frontmatter field in `config-schema.json`
2. Update `ll-sprint` to write `milestone:` back to issue files when assigning to a sprint
3. Add `--milestone` filter to `ll-issues list`
4. Update `ll-sync` to populate platform sprint/milestone from the `milestone:` field
5. Add a consistency check in `ll-issues verify`: warn if an issue's `milestone:` doesn't match any sprint definition that lists it

## Integration Map

### Files to Modify
- `config-schema.json` — add `milestone:` field
- `scripts/little_loops/issue_manager.py` — parse `milestone:` field
- `scripts/little_loops/cli/issues.py` — `--milestone` filter
- `scripts/little_loops/cli/sprint.py` — write `milestone:` when assigning issues to sprint
- `scripts/little_loops/sync/` — map `milestone:` to platform sprint/milestone/cycle
- `scripts/little_loops/cli/verify_docs.py` — consistency check for `milestone:` vs sprint files

### Dependent Files (Callers/Importers)
- TBD — use grep: `grep -r "issue_manager\|IssueManager" scripts/`
- `scripts/little_loops/cli/sprint.py` — imports `issue_manager.py` for issue file writes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields()` reads frontmatter fields for the `ll-issues show` card display; needs `frontmatter.get("milestone")` added to display `milestone:` in the rendered card via `_render_card()` [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/issue_manager.py` — see how `status:`, `priority:`, `relates_to:` are parsed; follow the same pattern for `milestone:`
- `scripts/little_loops/sync/` — see how existing frontmatter fields map to platform concepts

### Tests
- `scripts/tests/test_sprint.py` — add tests for `milestone:` backwrite on sprint assignment/removal
- `scripts/tests/test_sprint_integration.py` — integration test for sprint→issue milestone field
- `scripts/tests/test_issue_manager.py` — add tests for `milestone:` field parsing
- `scripts/tests/test_sync.py` — add tests for milestone→platform field mapping

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — add `test_list_filter_by_milestone_match`, `test_list_filter_by_milestone_no_match`, `test_list_json_output_contains_milestone_key`; follow pattern from `TestIssuesCLIList.test_list_filter_by_label_match()` (line ~518) [Agent 3 finding]
- `scripts/tests/test_sprint.py` (**will break**) — ~15+ test methods in `TestSprintErrorHandling`, `TestSprintDependencyAnalysis`, `TestSprintOnlyFlag`, `TestSprintWaveCleanStart` construct `argparse.Namespace` without `milestone`; if `_cmd_sprint_run()` reads `args.milestone`, these raise `AttributeError` — either add `milestone=None` to each Namespace or use `getattr(args, "milestone", None)` in `_cmd_sprint_run()` [Agent 3 finding]
- `scripts/tests/test_sprint_integration.py` (**will break**) — same `argparse.Namespace` pattern across `TestMultiWaveExecution`, `TestErrorRecovery`, `TestEdgeCases`, `TestDependencyHandling` [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — `test_from_dict_defaults_empty_new_relationship_fields()` (line ~1772) tests backward-compat defaults; append `assert info.milestone is None` [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — document `milestone:` field in issue schema reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` — add `milestone` row to the Frontmatter Fields table (follow `labels` row pattern added in ENH-1392) [Agent 2 finding]
- `docs/reference/CLI.md` — three updates: (1) add `--milestone <name>` row to `ll-issues list` flags table; (2) add note under `ll-sprint run` that it writes `milestone:` back to issue frontmatter on assignment; (3) add note under `ll-sync push` that `milestone:` maps to GitHub milestone by title [Agent 2 finding]

### Configuration
- `config-schema.json` — new optional `milestone:` string field

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected file paths** (several paths in the map above have incorrect module locations):
- `scripts/little_loops/cli/issues.py` → split: `scripts/little_loops/cli/issues/__init__.py` (arg registration in `main_issues()`) and `scripts/little_loops/cli/issues/list_cmd.py` (filter logic in `cmd_list()`)
- `scripts/little_loops/cli/sprint.py` → split: `scripts/little_loops/cli/sprint/__init__.py` and `scripts/little_loops/cli/sprint/run.py` (write-back goes in `_cmd_sprint_run()`)
- `scripts/little_loops/sync/` (directory) → `scripts/little_loops/sync.py` (single file, `GitHubSyncManager` class)
- `scripts/little_loops/cli/verify_docs.py` → does not exist; consistency check belongs in `cli/issues/__init__.py` as a new `ll-issues verify` subcommand

**Additional files to modify:**
- `scripts/little_loops/issue_parser.py` — add `milestone: str | None = None` to `IssueInfo` dataclass; update `parse_file()`, `to_dict()`, `from_dict()` (follow `labels` pattern added in ENH-1392)
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` is the write-back utility needed for sprint→issue backwrite; import and use, no modification needed

**Key constraint:**
- `config-schema.json` has `additionalProperties: false` in the `issues` properties block; `milestone:` must be declared there or the schema will reject it

**Sprint write-back touch point:**
- `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` — has resolved issue file paths via `valid[issue_id]` after `validate_issues()`; call `update_frontmatter(content, {"milestone": sprint.name})` before the wave execution loop; follow same pattern as `sync.py:_update_local_frontmatter()` which calls `update_frontmatter()` from `frontmatter.py`
- No existing sprint-to-issue write-back pattern exists — this is new

**Callers that will receive `milestone` transparently once `IssueInfo` is updated:**
- `scripts/little_loops/cli/issues/list_cmd.py:cmd_list()` — reads `IssueInfo`; needs `--milestone` filter wired to `issue.milestone`
- `scripts/little_loops/parallel/orchestrator.py` — loads issues via `issue_manager.py`; no changes needed

## API/Interface

### Frontmatter Field

```yaml
milestone: sprint-2026-q2  # optional string; matches a sprint definition name or milestone ID
```

### CLI Flag

```bash
ll-issues list --milestone <sprint-name>
```

### Sync Mapping

| Platform | Field |
|----------|-------|
| GitHub | `milestone` (title match) |
| JIRA | sprint (`customfield_10020` via Agile API) |
| ADO | iteration path |
| Linear | cycle |

## Implementation Steps

1. Add `milestone:` to `config-schema.json` as an optional string field
2. Update `ll-sprint` to set `milestone: <sprint-name>` on issue files when building sprint
3. Update `ll-sprint` to clear `milestone:` when an issue is removed from a sprint
4. Add `--milestone` filter to `ll-issues list`
5. Update `ll-sync` mappers for GitHub, JIRA/ADO, Linear
6. Add consistency check in `ll-issues verify`: issues in sprint file but missing `milestone:` field (and vice versa)
7. Add tests for sprint→issue backwrite and sync mapping

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file/function references:_

1. **`config-schema.json` issues properties** — add `"milestone": {"type": "string", "description": "Sprint or milestone name this issue is assigned to"}` following the `parent`/`duplicate_of` scalar pattern (around lines 200–235)
2. **`scripts/little_loops/issue_parser.py:IssueInfo`** — add `milestone: str | None = None`; update `parse_file()` with `milestone = frontmatter.get("milestone")`; add to `to_dict()` and `from_dict()` (5-touchpoint pattern used for `labels` in ENH-1392)
3. **`scripts/little_loops/cli/issues/__init__.py:main_issues()`** — add `ls.add_argument("--milestone", dest="milestone", metavar="MILESTONE", help="Filter by milestone name")` following `--label` append pattern (~line 163); also wire to `ll-auto` label-filter equivalent in `issue_manager.py:AutoManager._get_next_issue()`
4. **`scripts/little_loops/cli/issues/list_cmd.py:cmd_list()`** — extend filter list comprehension with `and (not milestone_filter or issue.milestone == milestone_filter)`
5. **`scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()`** — after `valid` is populated by `validate_issues()`, iterate resolved paths and call `update_frontmatter(content, {"milestone": sprint.name})` from `frontmatter.py`; clear field with `{"milestone": None}` when removing an issue (see `sprint/edit.py` or `sprint/manage.py`)
6. **`scripts/little_loops/sync.py:GitHubSyncManager._create_github_issue()` and `_update_github_issue()`** — append `"--milestone"` and `frontmatter["milestone"]` to the `gh issue create/edit` args list when `frontmatter.get("milestone")` is truthy
7. **Tests** — follow `test_parse_labels_from_frontmatter` pattern in `scripts/tests/test_issue_parser.py` (lines ~2620–2686); write 3 cases: present-with-value, absent (default `None`), explicit-null

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/cli/issues/show.py` — in `_parse_card_fields()`, add `"milestone": frontmatter.get("milestone")` to the returned field dict; in `_render_card()`, render it as a detail line when non-None (follow the `labels` display pattern)
9. Update `scripts/tests/test_sprint.py` and `scripts/tests/test_sprint_integration.py` — add `milestone=None` to all ~15+ `argparse.Namespace(...)` constructors that call `_cmd_sprint_run()`; alternatively, use `getattr(args, "milestone", None)` inside `_cmd_sprint_run()` to make it safe
10. Update `scripts/tests/test_issue_parser.py` — append `assert info.milestone is None` to `test_from_dict_defaults_empty_new_relationship_fields()`
11. Add milestone tests to `scripts/tests/test_issues_cli.py` — `test_list_filter_by_milestone_match`, `test_list_filter_by_milestone_no_match`, `test_list_json_output_contains_milestone_key`
12. Update `docs/reference/ISSUE_TEMPLATE.md` — add `milestone` row to Frontmatter Fields table
13. Update `docs/reference/CLI.md` — add `--milestone` to `ll-issues list` flag table; note sprint write-back; note sync mapping

## Scope Boundaries

- **In scope**: `milestone:` frontmatter field; `ll-issues list --milestone` filter; `ll-sprint` backwrite on assign/remove; `ll-sync` mapping to GitHub milestone, JIRA sprint, ADO iteration, Linear cycle; consistency check in `ll-issues verify`
- **Out of scope**: Retroactive population of `milestone:` on existing issues not assigned to any sprint; multi-milestone support (one milestone per issue); sprint board or Gantt visualization; remote milestone/cycle *creation* via sync (assign to existing only); UI for sprint assignment

## Impact

- **Priority**: P3 — improves sync fidelity but not blocking; depends on ENH-1390 (status field) being stable first
- **Effort**: Small — field addition + targeted updates to sprint and sync tooling
- **Risk**: Low — additive field; `ll-sprint` backwrite is the most invasive change

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `sprint`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-05-11T03:51:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-11T03:44:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe72425c-a94f-4479-9a2f-dc8b9fbb684f.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68bdc5c1-2a99-4faf-9201-5e06c1424aa6.jsonl`
- `/ll:wire-issue` - 2026-05-11T03:39:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20c5c5c8-7eb0-45b9-b45b-fbdb88d9ae44.jsonl`
- `/ll:refine-issue` - 2026-05-11T03:31:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e006011d-56c3-4487-bbf9-c1b93cacc895.jsonl`
- `/ll:format-issue` - 2026-05-09T20:39:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe6a87fd-be36-4a41-80cb-e4a8262d6fa1.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
