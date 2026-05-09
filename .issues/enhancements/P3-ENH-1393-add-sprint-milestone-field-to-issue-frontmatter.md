---
id: ENH-1393
type: ENH
priority: P3
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [FEAT-1389, ENH-1390, ENH-1391, ENH-1392]
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

### Similar Patterns
- `scripts/little_loops/issue_manager.py` — see how `status:`, `priority:`, `relates_to:` are parsed; follow the same pattern for `milestone:`
- `scripts/little_loops/sync/` — see how existing frontmatter fields map to platform concepts

### Tests
- `scripts/tests/test_sprint.py` — add tests for `milestone:` backwrite on sprint assignment/removal
- `scripts/tests/test_sprint_integration.py` — integration test for sprint→issue milestone field
- `scripts/tests/test_issue_manager.py` — add tests for `milestone:` field parsing
- `scripts/tests/test_sync.py` — add tests for milestone→platform field mapping

### Documentation
- `docs/reference/API.md` — document `milestone:` field in issue schema reference

### Configuration
- `config-schema.json` — new optional `milestone:` string field

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
- `/ll:format-issue` - 2026-05-09T20:39:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe6a87fd-be36-4a41-80cb-e4a8262d6fa1.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
