---
id: ENH-1392
type: ENH
priority: P3
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [FEAT-1389, ENH-1390, ENH-1391, ENH-1393]
---

# ENH-1392: Add Labels Field to Issue Frontmatter

## Summary

Add a `labels:` list field to issue frontmatter for cross-cutting classification by component, area, or concern. Labels enable queries like "all open issues touching the FSM runtime" that cut across issue types and epics — a capability absent from the current model and present in every major platform.

## Current Behavior

There is no label or tag system. Cross-cutting classification is only possible by grepping issue filenames or content. You cannot ask "which issues affect the CLI layer?" or "what work is tagged quick-win?" without manual inspection. The `## Labels` section exists as a Markdown section in some issues but it is freeform, unstructured, and not machine-readable.

## Expected Behavior

- `labels:` is a recognized frontmatter field: `labels: [fsm, cli, quick-win]`
- A defined vocabulary of well-known label prefixes exists: `component:`, `area:`, `effort:`
- `ll-issues list --label fsm` filters issues by label
- `ll-issues list --label quick-win` shows all issues tagged for batch execution
- Labels are preserved and mapped during `ll-sync` (GitHub labels, JIRA labels, ADO tags, Linear labels)
- The freeform `## Labels` Markdown section is removed or migrated to frontmatter

## Motivation

- **Discovery**: "Show me all quick-win issues across types" is a common sprint planning question. Without labels it requires reading every issue.
- **Component ownership**: Teams using ADO or JIRA assign labels by component to route issues to the right person. `ll-sync` cannot populate these without a source `labels:` field.
- **Querying**: `ll-auto` and `ll-sprint` could accept `--label` filters to scope processing to a specific component or effort tier.
- **Platform compatibility**: All major platforms (GitHub labels, JIRA labels, ADO tags, Linear labels) treat labels as a standard first-class field.

## Proposed Solution

1. Add `labels:` as a recognized frontmatter list field in `config-schema.json`
2. Define a starter vocabulary of well-known labels (documented, not enforced): component labels (`fsm`, `cli`, `session`, `testing`, `sync`, `docs`), effort labels (`quick-win`, `spike`), area labels (`issue-model`, `loop-runtime`, `parallel`)
3. Update `ll-issues list` to support `--label <value>` filter
4. Update `ll-auto` and `ll-sprint` to accept `--label` scope filter
5. Update `ll-sync` to map `labels:` to platform-native label/tag fields
6. Migrate the freeform `## Labels` Markdown section in existing issues to `labels:` frontmatter (automated)

## Integration Map

### Files to Modify
- `config-schema.json` — add `labels:` list field
- `scripts/little_loops/issue_manager.py` — parse `labels:` field
- `scripts/little_loops/cli/issues.py` — `--label` filter for `list` command
- `scripts/little_loops/cli/auto.py` and `sprint.py` — `--label` scope filter
- `scripts/little_loops/sync/` — map `labels:` to each platform
- `docs/reference/API.md` — document `labels:` field

## Implementation Steps

1. Add `labels:` to `config-schema.json` as an optional list of strings
2. Update issue parser to read `labels:` from frontmatter
3. Add `--label` filter to `ll-issues list`
4. Add `--label` scope filter to `ll-auto` and `ll-sprint`
5. Update `ll-sync` platform mappers to include labels
6. Write migration script to move freeform `## Labels` content to frontmatter where parseable
7. Document the starter label vocabulary in CONTRIBUTING.md or a dedicated labels reference
8. Add tests for label filtering and sync mapping

## Impact

- **Priority**: P3 — valuable but not blocking; sync and epic work (P2) come first
- **Effort**: Small — mostly additive; `--label` filter is a simple predicate
- **Risk**: Low — purely additive; existing issues are unaffected until migration

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `schema`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
