---
id: ENH-1392
type: ENH
priority: P3
status: done
captured_at: '2026-05-09T20:26:09Z'
completed_at: '2026-05-11T03:35:38Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
relates_to:
- FEAT-1389
- ENH-1390
- ENH-1391
- ENH-1393
confidence_score: 90
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
missing_artifacts: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Key discovery — partial implementation already exists:**
1. `IssueInfo.labels: list[str]` already exists at `issue_parser.py:271` with `field(default_factory=list)` — the field is declared but never populated from frontmatter in `IssueParser.parse_file()`; task is wiring, not adding a new field
2. `_parse_labels_from_content()` at `search.py:83` already parses backtick-wrapped labels from the `## Labels` body section — use this function as the migration source
3. `--label` filter already works on `ll-issues search` (registered at `issues/__init__.py:205`) — the `list` subparser (`ls`) just doesn't have it yet

**Concrete implementation guidance:**
- **Schema (Step 1)**: `config-schema.json` has `"additionalProperties": false` in the issues section — add `"labels": {"type": "array", "items": {"type": "string"}}` alongside `blocked_by`/`depends_on`/`relates_to` (around line 228)
- **Parser (Step 2)**: Extend the `fm_key` loop at `issue_parser.py:504-530` to include `("labels", labels)` where `labels` is a new local `list[str]`; pass `labels=labels` into the `IssueInfo(...)` constructor call
- **`ll-issues list --label` (Step 3)**: Add `--label` to the `ls` subparser in `issues/__init__.py` following the `sr` subparser pattern at lines 205–210; apply filter in `list_cmd.py:cmd_list()` using the existing `_parse_labels_from_content()` import
- **`ll-auto`/`ll-sprint --label` (Step 4)**: Add `add_label_arg()` to `cli_args.py` near `add_priority_arg():305`; call it from `add_common_auto_args()` so `ll-auto` and `ll-parallel` both inherit it; add label predicate to `issue_manager.py:AutoManager._get_next_issue():1042`; for sprint, label filter in `sprint/run.py:_cmd_sprint_run()` requires loading `IssueInfo` before applying (string-level filtering runs before IssueInfo load)
- **Sync push (Step 5)**: In `sync.py:_get_labels_for_issue():298`, append `labels.extend(fm.get("labels", []))` after the `blocked_by` block; for the pull path at lines 700–702, also write fetched labels to the `labels:` frontmatter key (in addition to or instead of the `## Labels` body section)
- **Migration (Step 6)**: Follow `cli/migrate_relationships.py` pattern; use `_parse_labels_from_content()` to extract labels from body; write to frontmatter with `write_frontmatter()`; remove the `## Labels` body section after migration

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/migrate_labels.py` (new file) — migration script; follow `cli/migrate_relationships.py` pattern; entry point `main_migrate_labels()` [Agent 2 finding]
- `scripts/little_loops/cli/issues/show.py` — `_extract_show_fields()` has an independent inline `## Labels` body-section regex; update to read `IssueInfo.labels` via `parse_file()` so `ll-issues show` displays labels after migration removes body sections [Agent 2 finding]

### Dependent Files (Callers/Importers)
- Any code that constructs `Issue` objects from frontmatter will receive the new `labels` attribute — grep `Issue(` and `issue_manager` imports for call sites
- `ll-sprint` YAML definition files reference issue IDs; no format change needed but `--label` filter applies at load time

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py` — `_extract_show_fields()` has its own inline `## Labels` body-section regex that reads independently of `IssueInfo.labels`; after migration removes the `## Labels` body section, `ll-issues show` will display empty labels unless this is updated to read `IssueInfo.labels` (populated by the updated `parse_file()`)
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` builds its own arg list and does NOT call `add_common_auto_args()`; `ll-parallel` will NOT inherit `--label` automatically — needs an explicit `add_label_arg(parser)` call and `ParallelOrchestrator._scan_issues()` / `ParallelConfig` must gain a `label_filter` field; alternatively, document `ll-parallel --label` as out-of-scope for this issue
- `scripts/little_loops/cli/sprint/__init__.py` — subparser registration site for `ll-sprint run`; the `--label` arg declaration must be added here (not only in `sprint/run.py`) for it to appear in `ll-sprint run --help`
- `scripts/little_loops/cli/__init__.py` — must import `main_migrate_labels` and add it to `__all__` alongside `main_migrate_relationships`

### Similar Patterns
- `priority` field in frontmatter: same pattern (schema field → parser → CLI filter) — follow the same validation-free, additive approach used for `priority`
- `relates_to` list field: existing list-typed frontmatter field; `labels:` should follow the same YAML list serialization convention

### Tests
- `scripts/tests/test_issue_manager.py` — add tests for `labels:` parsing (present, absent, empty list)
- `scripts/tests/test_cli_issues.py` — add tests for `--label` filter (match, no-match, multiple labels)
- `scripts/tests/test_sync_*.py` — add sync mapping tests for each platform mapper
- Migration script needs its own test with sample issues containing `## Labels` sections

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_migrate_labels.py` (new file) — migration script tests; follow `test_issue_migration.py` pattern (`_make_project`/`_run_migrate`/class-based structure at lines 36–139); cover: `## Labels` body → frontmatter rewrite, already-has-labels skip/merge, `--dry-run` no-op [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — add new `TestAutoManagerLabelFilter` class mirroring `TestAutoManagerPriorityFilter` at line 632; no `label_filter` tests exist yet [Agent 3 finding]
- `scripts/tests/test_cli_args.py` — add `TestAddLabelArg` class (mirror `TestAddPriorityArg` at line 528); update `TestAddCommonAutoArgs.test_adds_all_expected_arguments` (line 563) to assert `label` is in the arg set [Agent 3 finding]
- `scripts/tests/test_issues_cli.py` — add `test_list_filter_by_label` (mirror `test_list_filter_by_priority` at line 226); update `test_list_json_output` (line 319) to assert `"labels"` key appears in JSON output [Agent 3 finding]
- `scripts/tests/test_sprint.py` — `argparse.Namespace(...)` constructions at lines 724, 760, 926, 2130, 2163, 2204, 2303 lack `label`; use `getattr(args, "label", None)` in `_cmd_sprint_run` implementation to avoid breaking these [Agent 3 finding]
- `scripts/tests/test_sync.py` — update `test_get_labels_for_issue` (~line 412) to test with `labels: [quick-win]` frontmatter asserting `quick-win` in returned labels; add pull-path test that `labels:` frontmatter is written when receiving GitHub labels [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — document `labels:` field and its type/usage
- `CONTRIBUTING.md` — document starter label vocabulary (`component:`, `area:`, `effort:` prefixes)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md` — `## Frontmatter Fields` table lacks a `labels:` row; add alongside `blocked_by`/`depends_on`/`relates_to` [Agent 2 finding]
- `docs/reference/CLI.md` — three updates needed: (1) `ll-issues list` flags table missing `--label`; (2) shared flags table for `ll-auto`/`ll-sprint`/`ll-parallel` needs `--label` row; (3) add `ll-migrate-labels` section following the `ll-migrate-relationships` section as the model [Agent 2 finding]
- `.claude/CLAUDE.md` — CLI Tools list needs `ll-migrate-labels` entry alongside `ll-migrate-relationships` [Agent 2 finding]
- `README.md` — add `### ll-migrate-labels` section following the `### ll-migrate-relationships` section pattern [Agent 2 finding]
- `commands/sync-issues.md` — shows a pull-created file template with `## Labels` as a body section; if the pull path is updated to write `labels:` frontmatter instead, update this template [Agent 2 finding]

### Configuration
- `config-schema.json` — schema change is additive; no breaking change to existing configs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — add `ll-migrate-labels = "little_loops.cli:main_migrate_labels"` to `[project.scripts]` alongside `ll-migrate-relationships` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrections to the file list above:**
- `IssueInfo` dataclass is in `scripts/little_loops/issue_parser.py`, not `issue_manager.py` (which contains `AutoManager`)
- No `sync/` directory exists; all sync logic lives in `scripts/little_loops/sync.py` (GitHub only; no JIRA/ADO/Linear mappers implemented yet)

**Existing partial implementation:**
- `IssueInfo.labels: list[str]` at `issue_parser.py:271` — field exists, `to_dict()`/`from_dict()` are already wired; only `parse_file()` needs updating
- `_parse_labels_from_content()` at `search.py:83` — regex parser for `## Labels` body section; already called by `cmd_list()` (JSON output only) and `cmd_search()` (label filter)
- `--label` argument at `issues/__init__.py:205` — registered on `sr` (search) subparser; absent from `ls` (list) subparser

**Specific touch points:**
- `issue_parser.py:IssueParser.parse_file():504` — fm-key loop (`blocked_by`, `blocks`, `depends_on`, `relates_to`) is the exact pattern to extend with `labels`
- `issues/__init__.py:main_issues()` — `ls` subparser is where `--label` flag goes; `sr` subparser at line 205 is the model
- `list_cmd.py:cmd_list()` — apply label predicate here; `_parse_labels_from_content()` is already imported
- `cli_args.py:add_common_auto_args()` — add `add_label_arg()` call here so `ll-auto` and `ll-parallel` both get `--label`
- `issue_manager.py:AutoManager._get_next_issue():1042` — list comprehension; add `and (self.label_filter is None or any(l in i.labels for l in self.label_filter))`
- `sync.py:GitHubSyncManager._get_labels_for_issue():298` — append `labels.extend(fm.get("labels", []))` after the `blocked_by` block
- `sync.py:700-702` — pull path writes GitHub labels to `## Labels` body; update to also write `labels:` frontmatter key
- `sprint/run.py:_cmd_sprint_run()` — string-level type/skip/only filtering runs before `IssueInfo` load; label filter must be applied after loading `IssueInfo`

**Test files (confirmed to exist):**
- `scripts/tests/test_issue_parser.py:test_parse_depends_on_from_frontmatter:1631` — exact pattern for new `labels:` parsing tests
- `scripts/tests/test_issue_parser.py:test_parse_relates_to_from_frontmatter:1655` — second reference
- `scripts/tests/test_issues_cli.py:test_list_filter_by_priority:226` — pattern for `--label` filter tests on `list`
- `scripts/tests/test_issues_search.py:TestSearchLabelFilter.test_filter_by_label:466` — existing search `--label` test (reference)
- `scripts/tests/test_frontmatter.py:test_block_sequence_parsed_as_list:121` — list serialization round-trip pattern

## Implementation Steps

1. Add `labels:` to `config-schema.json` as an optional list of strings
2. Update issue parser to read `labels:` from frontmatter
3. Add `--label` filter to `ll-issues list`
4. Add `--label` scope filter to `ll-auto` and `ll-sprint`
5. Update `ll-sync` platform mappers to include labels
6. Write migration script to move freeform `## Labels` content to frontmatter where parseable
7. Document the starter label vocabulary in CONTRIBUTING.md or a dedicated labels reference
8. Add tests for label filtering and sync mapping

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete file references for each step:

1. **Schema**: Add `"labels": {"type": "array", "items": {"type": "string"}}` to `config-schema.json` inside `properties.issues` alongside `blocked_by`/`depends_on`/`relates_to` (~line 228)
2. **Parser**: Extend the fm-key loop at `issue_parser.py:504` to include `("labels", labels)`; initialize `labels: list[str] = []` before the loop; pass `labels=labels` to `IssueInfo(...)` constructor
3. **`ll-issues list --label`**: Add `--label` argument to `ls` subparser in `issues/__init__.py` (copy declaration from `sr` subparser at line 205); apply filter in `list_cmd.py:cmd_list()` using `_parse_labels_from_content()` (already imported)
4. **`ll-auto`/`ll-sprint --label`**: Add `add_label_arg()` to `cli_args.py` near `add_priority_arg():305`; call from `add_common_auto_args()`; add `label_filter` param to `AutoManager.__init__()` and predicate to `_get_next_issue():1042`; for sprint in `sprint/run.py:_cmd_sprint_run()`, apply label filter after `IssueInfo` objects are loaded
5. **Sync push**: `sync.py:_get_labels_for_issue():298` — append `labels.extend(fm.get("labels", []))`; `sync.py:700-702` (pull path) — also write `labels:` to frontmatter when receiving GitHub labels
6. **Migration**: Follow `cli/migrate_relationships.py` pattern; parse `## Labels` body via `_parse_labels_from_content()` from `search.py:83`; write to frontmatter via `write_frontmatter()`; strip `## Labels` section from body
7. **Docs**: `docs/reference/API.md` — add `labels:` field; `CONTRIBUTING.md` — add starter label vocabulary
8. **Tests**: `test_issue_parser.py:1631` for parser; `test_issues_cli.py:226` for list filter; `test_issues_search.py:466` for search reference; `test_sync.py` for GitHub label round-trip

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Create `scripts/little_loops/cli/migrate_labels.py` with `main_migrate_labels()` entry point — follow `cli/migrate_relationships.py` exactly; use `_parse_labels_from_content()` from `search.py:83` as the migration source; call `write_frontmatter()` to write `labels:`; strip `## Labels` body section after migration
10. Register `ll-migrate-labels`: add `ll-migrate-labels = "little_loops.cli:main_migrate_labels"` to `scripts/pyproject.toml` `[project.scripts]`; add `from .migrate_labels import main_migrate_labels` and `__all__` entry in `scripts/little_loops/cli/__init__.py`
11. Update `scripts/little_loops/cli/issues/show.py` — `_extract_show_fields()` uses an independent inline regex against the `## Labels` body section; replace with a read from `IssueInfo.labels` (which `parse_file()` will populate) so `ll-issues show` displays labels after body migration
12. **Include `ll-parallel --label` in scope**: `cli/parallel.py:main_parallel()` already adds `--priority` and `--type` explicitly (lines 66, 137) and wires them into `create_parallel_config()` — follow the same pattern; call `add_label_arg(parser)` explicitly in `main_parallel()`, pass `label_filter` into `create_parallel_config()` alongside `priority_filter`, update `ParallelConfig` to hold the new field, and apply the predicate in `ParallelOrchestrator._scan_issues()` (or equivalent filter site)
13. Update `cli/sprint/__init__.py` — subparser arg declaration for `ll-sprint run --label` must be added here (not only in `sprint/run.py`); use `getattr(args, "label", None)` pattern in `_cmd_sprint_run` to avoid breaking existing `argparse.Namespace` test fixtures
14. Update docs: `docs/reference/ISSUE_TEMPLATE.md` (add `labels:` row to Frontmatter Fields table); `docs/reference/CLI.md` (three sections: `ll-issues list` flags, shared auto flags, `ll-migrate-labels` section); `.claude/CLAUDE.md` CLI Tools list; `README.md` migration section

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-10.

**Selected**: Include `ll-parallel --label` in scope (explicit arg addition pattern)

**Reasoning**: `parallel.py` already adds `--priority` (line 66) and `--type` (line 137) explicitly and wires them through `create_parallel_config()`, so adding `--label` via the same pattern is mechanical. Excluding it would leave `ll-parallel` inconsistently less capable than `ll-auto` and `ll-sprint` with no technical justification. `ParallelConfig` already holds a `priority_filter` field, confirming the dataclass is designed for per-run filter params.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Include ll-parallel --label | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Exclude (document as out-of-scope) | 1/3 | 3/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Include: `parallel.py:66` — `--priority` and `--type` already added explicitly; `parallel.py:197` — `priority_filter` already wired into `create_parallel_config()`; pattern is fully established
- Exclude: no existing precedent for partial filter support across run modes; would create user-visible inconsistency

## Impact

- **Priority**: P3 — valuable but not blocking; sync and epic work (P2) come first
- **Effort**: Small — mostly additive; `--label` filter is a simple predicate
- **Risk**: Low — purely additive; existing issues are unaffected until migration

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `schema`, `captured`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- **Coordination breadth**: 16+ distinct change sites penalize Complexity Breadth (0/12); each individual change is mechanical-to-local, but missing any one site (especially `cli/__init__.py`, `pyproject.toml`, `sprint/__init__.py`, or `show.py`) will cause a silent regression — implement step-by-step against the Integration Map.
- **New file scope**: `cli/migrate_labels.py` and `test_migrate_labels.py` do not yet exist and must be created from scratch; `migrate_relationships.py` is an exact pattern guide, but this adds volume beyond code-only edits.

## Session Log
- `/ll:ready-issue` - 2026-05-11T03:18:20 - `82d6b35a-8155-48a3-8d78-66be4e2069b8.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `cfb07734-959c-4a53-9fae-e51a41074ba4.jsonl`
- `/ll:decide-issue` - 2026-05-11T03:12:03 - `fe60117f-d096-4a7d-b5b5-6280dd0dffb5.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:wire-issue` - 2026-05-11T03:05:04 - `cfa1ff52-c092-4166-8c6a-c31118c28f8a.jsonl`
- `/ll:refine-issue` - 2026-05-11T02:57:22 - `fc0fc370-4b82-4dde-a68c-03a3ef65226d.jsonl`
- `/ll:format-issue` - 2026-05-09T20:38:42 - `fe6a87fd-be36-4a41-80cb-e4a8262d6fa1.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P3
