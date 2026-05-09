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

## API/Interface

New frontmatter field:

```yaml
labels: [fsm, cli, quick-win]
```

CLI additions:

```bash
ll-issues list --label <value>        # filter issues by label
ll-auto --label <value>               # scope processing to matching issues
ll-sprint --label <value>             # scope sprint to matching issues
```

Platform sync mapping:
- GitHub → `labels` array on issue
- JIRA → `labels` field
- ADO → `tags` field (semicolon-delimited)
- Linear → `labelIds` array

## Scope Boundaries

- **In scope**: adding `labels:` as an optional list field; `--label` filter for `ll-issues list`, `ll-auto`, `ll-sprint`; `ll-sync` platform mapping; migration of freeform `## Labels` Markdown sections to frontmatter
- **Out of scope**: enforced label vocabulary (starter labels are documented, not validated); label hierarchies or namespacing beyond simple prefix convention (`component:`, `area:`, `effort:`); automatic label inference or ML-based tagging; label-based routing or access control; any UI for label management

## Success Metrics

- `ll-issues list --label <value>` returns only issues whose `labels:` list contains that value
- Labels survive a `ll-sync` round-trip (push to GitHub and pull back preserves all labels)
- Migration script converts freeform `## Labels` content to `labels:` frontmatter for at least 90% of existing issues (remainder flagged for manual review)
- No regressions in `ll-issues list`, `ll-auto`, or `ll-sprint` when `--label` is omitted

## Integration Map

### Files to Modify
- `config-schema.json` — add `labels:` list field (optional, items: string)
- `scripts/little_loops/issue_manager.py` — parse `labels:` from frontmatter into `Issue` dataclass
- `scripts/little_loops/cli/issues.py` — add `--label` filter to `list` command (`filter_by_label` predicate)
- `scripts/little_loops/cli/auto.py` — add `--label` scope filter (reuse same predicate as `list`)
- `scripts/little_loops/cli/sprint.py` — add `--label` scope filter
- `scripts/little_loops/sync/` — update platform mappers (`github.py`, `jira.py`, `ado.py`, `linear.py`) to include `labels:` field

### Dependent Files (Callers/Importers)
- Any code that constructs `Issue` objects from frontmatter will receive the new `labels` attribute — grep `Issue(` and `issue_manager` imports for call sites
- `ll-sprint` YAML definition files reference issue IDs; no format change needed but `--label` filter applies at load time

### Similar Patterns
- `priority` field in frontmatter: same pattern (schema field → parser → CLI filter) — follow the same validation-free, additive approach used for `priority`
- `relates_to` list field: existing list-typed frontmatter field; `labels:` should follow the same YAML list serialization convention

### Tests
- `scripts/tests/test_issue_manager.py` — add tests for `labels:` parsing (present, absent, empty list)
- `scripts/tests/test_cli_issues.py` — add tests for `--label` filter (match, no-match, multiple labels)
- `scripts/tests/test_sync_*.py` — add sync mapping tests for each platform mapper
- Migration script needs its own test with sample issues containing `## Labels` sections

### Documentation
- `docs/reference/API.md` — document `labels:` field and its type/usage
- `CONTRIBUTING.md` — document starter label vocabulary (`component:`, `area:`, `effort:` prefixes)

### Configuration
- `config-schema.json` — schema change is additive; no breaking change to existing configs

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
- `/ll:format-issue` - 2026-05-09T20:38:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe6a87fd-be36-4a41-80cb-e4a8262d6fa1.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
