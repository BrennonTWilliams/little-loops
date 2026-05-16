---
id: ENH-1391
type: ENH
priority: P2
status: done
captured_at: '2026-05-09T20:26:09Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
relates_to:
- FEAT-1389
- ENH-1390
- ENH-1392
- ENH-1393
decision_needed: false
confidence_score: 91
outcome_confidence: 62
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
---

# ENH-1391: Standardize Issue Relationship Fields

## Summary

Consolidate the inconsistent `parent:` / `parent_issue:` field names and overloaded `related:` field into a minimal, platform-standard relationship vocabulary: `epic`, `parent`, `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`. Each field has a distinct semantic that maps 1:1 to relationship types in JIRA, ADO, GitHub, and Linear.

## Current Behavior

Four problems exist in the current relationship model:

1. **`parent` vs `parent_issue`** — same concept, two field names (7 issues use `parent_issue:`, 16 use `parent:`). Tooling must handle both or silently miss one.
2. **`related:` is overloaded** — used to mean "soft ordering dependency", "informational association", and "same epic cluster" depending on the issue author. No consistent semantic.
3. **`depends_on:` is partial** — exists in some deferred issues but not recognized by all tooling; not documented in the issue schema.
4. **No `duplicate_of:`** — duplicates can only be marked by closing with a comment; no machine-readable dedup field exists.

## Expected Behavior

The recognized relationship fields are exactly:

| Field | Semantic | Directional? | Platform mapping |
|---|---|---|---|
| `epic: EPIC-NNN` | Container epic this issue belongs to | one-way | JIRA: Epic Link; ADO: parent Epic; Linear: Project |
| `parent: TYPE-NNN` | Decomposition parent (same tier, e.g. issue decomposed from a larger issue) | one-way | JIRA: Sub-task parent; GitHub: parent issue |
| `blocked_by: [...]` | Cannot start until these are done | one-way | JIRA: "is blocked by"; ADO: "Predecessor"; Linear: "blocked by" |
| `depends_on: [...]` | Should follow these, but not a hard stop | one-way | JIRA: "depends on"; ADO: "Related Work"; Linear: "depends on" |
| `relates_to: [...]` | Associated — no ordering implication | symmetric | JIRA: "relates to"; GitHub: linked issues; Linear: "related" |
| `duplicate_of: TYPE-NNN` | This issue is a duplicate of another | one-way | JIRA: "duplicates"; GitHub: closing reference; Linear: "duplicate of" |

The `related:` field is deprecated and migrated to `relates_to:`.

## Motivation

- **Tooling correctness**: `ll-deps`, `ll-sprint`, and `map-dependencies` skill all traverse relationships. Inconsistent field names mean they silently miss edges.
- **Sync fidelity**: `ll-sync` can only map relationship types it recognizes. Standardizing to platform vocabulary makes the mapping trivial.
- **Sprint planning**: Distinguishing `blocked_by` (hard stop) from `depends_on` (soft ordering) from `relates_to` (informational) is essential for correct dependency-aware ordering in `ll-sprint`.
- **Dedup**: A machine-readable `duplicate_of:` enables `ll-issues` to auto-detect and skip duplicate issues during processing.

## Proposed Solution

1. Define the canonical 6-field vocabulary in `config-schema.json` and issue validation
2. Rename `parent_issue:` → `parent:` across all existing issues (automated)
3. Migrate `related:` → `relates_to:` across all existing issues (automated; the semantic is compatible for most cases)
4. Add `duplicate_of:` recognition to all tooling
5. Add `epic:` field recognition (in concert with FEAT-1389)
6. Update `ll-deps`, `ll-sprint`, `map-dependencies`, and `ll-sync` to use the canonical field set
7. Add a validation rule: `blocked_by` values must be valid issue IDs; `duplicate_of` must be a single value, not a list

## API/Interface

Frontmatter schema additions to `config-schema.json`:

```yaml
# Canonical relationship fields in issue frontmatter
epic: EPIC-NNN            # single value
parent: TYPE-NNN          # single value
blocked_by: [TYPE-NNN]    # list
depends_on: [TYPE-NNN]    # list
relates_to: [TYPE-NNN]    # list
duplicate_of: TYPE-NNN    # single value

# Deprecated (supported as aliases during migration):
parent_issue: TYPE-NNN    # → migrated to parent:
related: [TYPE-NNN]       # → migrated to relates_to:
```

Validation rules:
- `blocked_by`, `depends_on`, `relates_to` accept lists only
- `epic`, `parent`, `duplicate_of` accept single values only
- Unknown relationship fields emit a validation warning

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — relationship field parsing
- `scripts/little_loops/cli/deps.py` — traverse canonical fields
- `scripts/little_loops/cli/issues.py` — show/sequence relationship display
- `scripts/little_loops/sync/` — relationship type mapping for each platform
- `skills/map-dependencies/SKILL.md` — use canonical vocabulary
- `config-schema.json` — relationship field definitions and validation
- All existing issue `.md` files — migrate `parent_issue:` → `parent:`, `related:` → `relates_to:`
- Migration script (new): `scripts/little_loops/cli/migrate_relationships.py`

_Corrections and additions (codebase research):_
- `scripts/little_loops/issue_parser.py` — **not** `issue_manager.py`; relationship parsing lives in `IssueInfo` dataclass and `IssueParser.parse_file()`; currently only reads `blocked_by`, `blocks`, `epic` from frontmatter
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()` and `get_execution_waves()`; currently treats ALL edges as hard blocks; needs a third pass for `depends_on` soft-ordering edges
- `scripts/little_loops/dependency_mapper/analysis.py` — `validate_dependencies()`; currently validates only `blocked_by`/`blocks` refs; extend for `depends_on`, `relates_to`, `duplicate_of`
- `scripts/little_loops/dependency_mapper/operations.py` — `_add_to_section()` / `_remove_from_section()`; currently only writes to `"Blocked By"` and `"Blocks"` sections; add `"Depends On"` and `"Relates To"`
- `scripts/little_loops/cli/issues/sequence.py` — **not** `issues.py` (that path doesn't exist); this is a submodule
- `scripts/little_loops/cli/issues/clusters.py` — cluster display using `blocked_by`/`blocks`
- `scripts/little_loops/sync.py` — **not** `sync/` directory; single file `GitHubSyncManager`; currently maps NO relationship fields to GitHub at all
- `scripts/little_loops/loops/recursive-refine.yaml` — greps for `parent_issue:` via shell; update grep pattern after migration

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — shell-greps for `parent_issue: {iid}` in `.issues/` to find child issues; must update to grep for `parent:` after migration
- `scripts/little_loops/issue_lifecycle.py` — uses `parent_issue_id` key in event payload emitted to event bus; does NOT write `parent_issue:` frontmatter directly
- `scripts/little_loops/cli/sprint/run.py` — calls `DependencyGraph.from_issues()` for wave planning; will pick up `depends_on` once graph is updated
- `scripts/little_loops/cli/sprint/create.py` — sprint creation with dependency-aware ordering; reads graph output
- `scripts/little_loops/cli/sprint/_helpers.py` — wave rendering; displays `blocked_by` relationships via `dep_graph.blocked_by.get(issue.issue_id, set())`
- `scripts/little_loops/cli/issues/sequence.py` — calls `DependencyGraph.from_issues()` then `topological_sort()` for sequencing
- `scripts/little_loops/cli/issues/clusters.py` — reads `blocked_by`/`blocks` from `IssueInfo` for cluster visualization

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/show.py` — accesses `dep_graph.blocked_by.get(issue.issue_id, set())` in sprint wave rendering; if `depends_on` edges are added to `DependencyGraph`, may need to display soft dependencies [Agent 1 finding]
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph()` iterates `issue.blocked_by` to build the ASCII graph adjacency structure; needs extending for `depends_on` edges if those should appear in ASCII output [Agent 1 finding]

### Similar Patterns
- `config-schema.json` existing field definitions — follow same JSON Schema pattern for new relationship field entries
- `scripts/little_loops/sync/` platform mappers — each already maps field names; extend same pattern for new canonical fields

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/migrate.py` — `main_migrate()`, `_set_fields()`, `_move_file()` — exact pattern to follow for the migration script; uses argparse with `--dry-run` flag, `_set_fields(content, fields)` for in-place YAML key rename without round-tripping, iterates file list and prints `[DRY RUN] MOVE ...` prefix
- `scripts/tests/test_issue_migration.py` — `_make_project()`, `_run_migrate()`, `_make_mock_run()` helpers — follow this test structure for `migrate_relationships.py` tests
- `config-schema.json` lines ~100–106 (`status` field) — pattern for enum-constrained single-value field: `type: string, description, enum, default`
- `config-schema.json` lines ~839–913 (`dependency_mapping` block) — pattern for new structured object block: nested `properties`, `additionalProperties: false`
- `config-schema.json` `worktree_copy_files` — pattern for array-of-strings field: `type: array, items: {type: string}, default: [...]`
- `scripts/little_loops/issue_parser.py` `IssueParser.parse_file()` frontmatter reconciliation loop — exact pattern to reuse for new `depends_on`/`relates_to` list fields (handles string CSV or YAML list, warns on conflict with body section)
- `scripts/little_loops/frontmatter.py` `parse_frontmatter()` / `update_frontmatter()` — read/write path for frontmatter in the migration script

### Tests
- `scripts/tests/test_issue_manager.py` — add tests for deprecated alias handling and canonical field parsing
- `scripts/tests/test_deps.py` — add tests for `blocked_by` (hard) vs `depends_on` (soft) traversal
- `scripts/tests/test_sync.py` — add tests for relationship type mapping per platform

_Correction (codebase research):_ The actual test files to extend are:
- `scripts/tests/test_issue_parser.py` — add tests for `depends_on`, `relates_to`, `duplicate_of`, `parent` parsing + deprecated alias handling (`parent_issue` → `parent`, `related` → `relates_to`); follow `caplog` warning pattern already used there
- `scripts/tests/test_dependency_graph.py` — add `test_depends_on_soft_ordering()` using the `make_issue()` helper; extend `make_issue()` with `depends_on: list[str] | None = None` kwarg; extend `DependencyGraph.from_issues()` soft-ordering tests
- `scripts/tests/test_dependency_mapper.py` — add validation tests for broken refs in `depends_on`, `relates_to`, `duplicate_of`; extend `make_issue()` helper with `depends_on: list[str] | None = None` kwarg
- `scripts/tests/test_cli_sync.py` — extend with relationship field mapping assertions
- `scripts/tests/test_config_schema.py` — add structural assertions for new relationship fields (follow `test_commands_rate_limits_block` pattern)
- New: `scripts/tests/test_migrate_relationships.py` — follow `_make_project()` / `_run_migrate()` / `_make_mock_run()` pattern from `test_issue_migration.py`; `_run_migrate_relationships` shim calls `main_migrate_relationships`; no `subprocess.run` mock needed if migration does in-place `file.write_text()` only

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_recursive_refine.py` — **WILL BREAK after migration**: fixture files at lines ~1029–1036 write `parent_issue: ENH-100` frontmatter; `build_parent_map()` greps for that exact string; once `recursive-refine.yaml` grep is updated to `parent:`, these fixtures must also use `parent:` [Agent 3 finding]
- `scripts/tests/test_issue_parser_properties.py` — Hypothesis strategies at `make_issue()` generate `blocked_by`/`blocks` only; after adding `depends_on`, `relates_to`, `duplicate_of`, `parent` to `IssueInfo`, extend property strategies to cover new fields [Agent 3 finding]
- `scripts/tests/test_issues_cli.py` — `test_sequence_json_output` asserts `"blocked_by" in item` and `"blocks" in item` in `ll-issues sequence --json` output but does not check `depends_on` or `relates_to`; if `cmd_sequence()` in `sequence.py` is extended to include new fields in JSON output, add corresponding assertions [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update relationship field reference section
- `CONTRIBUTING.md` — note canonical vocabulary in issue authoring guidelines
- `docs/reference/ISSUE_TEMPLATE.md` — documents `parent_issue:` at approx. line 896; update to `parent:`
- `skills/issue-size-review/SKILL.md` — currently writes `parent_issue:` to decomposed child issues; update to write `parent:` after migration

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — example frontmatter block uses `blocked_by:`; extend to show full canonical vocabulary (`depends_on:`, `relates_to:`, `duplicate_of:`) [Agent 2 finding]
- `docs/guides/SPRINT_GUIDE.md` — explains wave scheduling only via `blocked_by`; needs `depends_on` (soft ordering) vs `blocked_by` (hard stop) distinction documented [Agent 2 finding]
- `skills/audit-issue-conflicts/SKILL.md` — instructs writing `blocked_by: [ISSUE-B]` frontmatter for dependency links; update to reference the canonical 6-field vocabulary so the skill uses the right field for soft vs hard dependencies [Agent 2 finding]
- `skills/confidence-check/SKILL.md` — instructs reading `parent_issue: EPIC-NNN` for child-issue enumeration check; must update to `parent:` after migration [Agent 2 finding]

### Configuration
- `config-schema.json` — relationship field schema additions (primary change)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — add `ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"` to `[project.scripts]`; without this entry the migration CLI is not installed [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — add `main_migrate_relationships` to module exports (follow the `from .migrate import main_migrate` pattern) [Agent 1 finding]

## Implementation Steps

1. Define canonical relationship fields in `config-schema.json` with descriptions and value constraints
2. Update `issue_manager.py` field parser to recognize all 6 fields (and `parent_issue:` as deprecated alias)
3. Write migration script: `parent_issue:` → `parent:`, `related:` → `relates_to:` in all `.issues/**/*.md`
4. Update `ll-deps` CLI to traverse `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`
5. Update `ll-sprint` dependency ordering to use `blocked_by` (hard) and `depends_on` (soft) separately
6. Update `ll-sync` platform mappers for each relationship type
7. Add validation: warn on unknown relationship field names in issue frontmatter
8. Update `skills/map-dependencies/SKILL.md` with canonical vocabulary
9. Update docs

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file anchors for each step:_

1. **`config-schema.json` schema additions** — add 5 fields to the `issues.properties` block (skip `epic` — deferred to FEAT-1389): `parent` (type: string, single value), `blocked_by` / `depends_on` / `relates_to` (type: array, items: {type: string}), `duplicate_of` (type: string, single value). Follow the `worktree_copy_files` array pattern and the `status` enum pattern. Then add structural assertions in `scripts/tests/test_config_schema.py` following `test_commands_rate_limits_block`.

2. **`issue_parser.py` — `IssueInfo` and `IssueParser.parse_file()`** (not `issue_manager.py`) — add `parent: str | None = None`, `depends_on: list[str] = field(default_factory=list)`, `relates_to: list[str] = field(default_factory=list)`, `duplicate_of: str | None = None` to `IssueInfo`. Extend the existing frontmatter reconciliation loop (currently `for fm_key, body_ids in (("blocked_by", blocked_by), ("blocks", blocks)):`) to also handle `depends_on` and `relates_to` as list fields using the identical pattern. Add alias reads: `frontmatter.get("parent_issue")` → populate `parent`; `frontmatter.get("related")` → populate `relates_to`. Add to `to_dict()` and `from_dict()` symmetrically.

3. **Migration script `scripts/little_loops/cli/migrate_relationships.py`** — follow `scripts/little_loops/cli/migrate.py` structure: `_set_fields(content, {"parent": value})` for in-place rename (no YAML round-trip), `main_migrate_relationships()` entry point with `--dry-run` flag, glob `.issues/**/*.md`, detect `parent_issue:` and `related:` keys via `parse_frontmatter()` from `scripts/little_loops/frontmatter.py`. Register as `ll-migrate-relationships` in `pyproject.toml` console scripts. Test following `scripts/tests/test_issue_migration.py` `_make_project()` / `_run_migrate()` helpers. Also update `scripts/little_loops/loops/recursive-refine.yaml` grep pattern from `parent_issue:` to `parent:`.

4. **`dependency_mapper/analysis.py` `validate_dependencies()`** and **`dependency_mapper/operations.py`** — extend validation to check broken refs in `depends_on`, `relates_to`, `duplicate_of` (same broken-ref logic as `blocked_by`). Add `_add_to_section(path, "Depends On", id)` and `_add_to_section(path, "Relates To", id)` call-sites in `operations.py`.

5. **`dependency_graph.py` `DependencyGraph.from_issues()`** — add a third pass for `issue.depends_on`: build a separate `depends_on_edges` dict (soft ordering); update `get_execution_waves()` to place `depends_on` targets in earlier waves but not block the dependent's wave entry. No change to `blocked_by` hard-stop semantics. Tests go in `scripts/tests/test_dependency_graph.py` using the existing `make_issue()` helper and `caplog` warning pattern.

6. **`sync.py` `GitHubSyncManager._push_single_issue()`** — GitHub has no native relationship API; map `blocked_by` to a `blocked-by` label and `duplicate_of` to a closing comment reference. Note: `ll-sync` currently maps NO relationship fields — this step is new territory.

7. **Validation for unknown relationship fields** — add a check in `dependency_mapper/analysis.py` (or a new `validate_frontmatter_fields()` helper) that warns via `logger.warning()` when an issue's frontmatter contains an unrecognized relationship key (e.g., `parent_issue:` after migration, `related:` after migration). Pattern: `caplog`-testable `logger.warning(...)`.

8. **`skills/map-dependencies/SKILL.md`** + **`skills/issue-size-review/SKILL.md`** — update vocabulary references; `issue-size-review` writes `parent_issue:` to child issues — change to `parent:`.

9. **Docs** — `docs/reference/ISSUE_TEMPLATE.md` (~line 896, `parent_issue:` field), `docs/reference/API.md` (`IssueInfo` field list), `CONTRIBUTING.md` (issue authoring guidelines).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Register `ll-migrate-relationships` in `scripts/pyproject.toml` under `[project.scripts]`: `ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"` — without this the migration CLI is not installed after `pip install -e ./scripts`
11. Export `main_migrate_relationships` from `scripts/little_loops/cli/__init__.py` (follow the `from .migrate import main_migrate` pattern)
12. Update `scripts/tests/test_loops_recursive_refine.py` — fixture files use `parent_issue: ENH-100`; update to `parent:` in sync with the `recursive-refine.yaml` grep pattern change (step 3)
13. Update `scripts/little_loops/dependency_mapper/formatting.py` `format_text_graph()` — currently iterates only `issue.blocked_by` for edges; decide whether `depends_on` edges should also appear in ASCII graph output and extend accordingly
14. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` and `docs/guides/SPRINT_GUIDE.md` with canonical vocabulary and `blocked_by` (hard) vs `depends_on` (soft) distinction (step 9 extension)
15. Update `skills/audit-issue-conflicts/SKILL.md` and `skills/confidence-check/SKILL.md` — replace `parent_issue:` with `parent:` references and align `blocked_by` instructions with canonical vocabulary

## Success Metrics

- Zero `.issues/**/*.md` files containing `parent_issue:` field after migration
- Zero `.issues/**/*.md` files containing `related:` field after migration
- All 6 canonical fields (`epic`, `parent`, `blocked_by`, `depends_on`, `relates_to`, `duplicate_of`) traversed correctly by `ll-deps`, `ll-sprint`, `map-dependencies`, and `ll-sync`
- `ll-issues` validation flags unknown relationship field names with a warning

## Scope Boundaries

- **In scope**: Defining the 6 canonical relationship fields in `config-schema.json`, automating migration of `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files, updating `ll-deps` / `ll-sprint` / `map-dependencies` / `ll-sync` to use canonical fields, adding validation warnings for unknown field names
- **Out of scope**: Adding relationship types beyond the 6 defined (e.g., `conflicts_with`, `supersedes`), platform-specific relationship extensions not in the canonical set, UI/visual display of relationship graphs, changes to how relationships affect auto-prioritization logic, `ll-sync` full bidirectional sync (covered by FEAT-1389)

## Impact

- **Priority**: P2 — incorrect relationship traversal affects sprint planning and sync correctness today
- **Effort**: Small-Medium — field renaming is mechanical; logic changes in `ll-deps` and `ll-sprint` are targeted
- **Risk**: Low — automated rename is reversible; field additions are backwards-compatible

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `sync-compatibility`, `schema`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 91/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Outcome Risk Factors
- **Broad enumeration across 16+ code sites** — 16+ files touched across parsers, graph, mappers, sync, skills, docs, config; track progress per-file to avoid missed wiring
- **Broad change surface with 6-10 IssueInfo/DependencyGraph callers** — changes are additive (new fields), not breaking, but each consumer needs a review pass to ensure `None`/empty defaults for new fields are handled
- **Minor ambiguity: formatting.py decision** — `format_text_graph()` edge display for `depends_on` not resolved; can be deferred or defaulted to "show them" during implementation

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1430: Standardize Relationship Fields — Schema & Parser Foundation
- ENH-1431: Standardize Relationship Fields — Migration Script
- ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation
- ENH-1433: Standardize Relationship Fields — Skills, Docs & Display

## Session Log
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee9c4627-ed9e-44bb-8b76-04ed284de14b.jsonl`
- `/ll:wire-issue` - 2026-05-10T22:30:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c447f1c-5113-415c-848e-ebad295f164c.jsonl`
- `/ll:refine-issue` - 2026-05-10T22:20:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a885b057-c352-4700-aa70-a7f967da7928.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:format-issue` - 2026-05-09T20:38:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf87852d-ec5b-4a4d-959f-57a040534f19.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): The `epic:` relationship field defined in the canonical vocabulary table above maps to JIRA Epic Link / ADO parent Epic / Linear Project. However, the formal implementation of `epic:` field parsing, config-schema registration, and tooling wiring is owned by FEAT-1389 (Add EPIC as first-class issue type). ENH-1391 establishes the vocabulary entry and platform mapping; it must NOT implement `epic:` field parsing in `issue_manager.py` or register the field in `config-schema.json` — defer those to FEAT-1389. Add FEAT-1389 as a dependency when sequencing this issue.
