---
id: ENH-1432
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1430
status: done
confidence_score: 98
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Summary

Update `dependency_graph.py`, `dependency_mapper/`, `sync.py`, and `formatting.py` to traverse and validate all canonical relationship fields. Adds `depends_on` soft-ordering to wave planning, maps relationship types in GitHub sync, and warns on unknown field names in frontmatter. Depends on ENH-1430 (new `IssueInfo` fields must exist). Can run in parallel with ENH-1431.

## Parent Issue

Decomposed from ENH-1391: Standardize Issue Relationship Fields

## Scope

Covers implementation steps 4, 5, 6, 7, and 13 from the parent.

## Proposed Solution

### Step 4 — `dependency_mapper/analysis.py` and `dependency_mapper/operations.py`

**`analysis.py` `validate_dependencies()`:**
- Extend to check broken refs in `depends_on`, `relates_to`, `duplicate_of` using same broken-ref logic as `blocked_by`

**`operations.py`:**
- Add `_add_to_section(path, "Depends On", id)` and `_add_to_section(path, "Relates To", id)` call-sites alongside the existing `"Blocked By"` and `"Blocks"` sections

### Step 5 — `dependency_graph.py` `DependencyGraph.from_issues()`

Add a third pass for `issue.depends_on` (soft ordering):
- Build a separate `depends_on_edges` dict (does NOT block wave entry)
- Update `get_execution_waves()` to place `depends_on` targets in earlier waves without hard-blocking the dependent
- No change to `blocked_by` hard-stop semantics
- Extend `make_issue()` helper in tests with `depends_on: list[str] | None = None` kwarg

### Step 6 — `sync.py` `GitHubSyncManager._push_single_issue()`

GitHub has no native relationship API; map relationship fields as:
- `blocked_by` → add a `blocked-by` label
- `duplicate_of` → append a closing comment reference

Note: `ll-sync` currently maps NO relationship fields — this is new territory.

### Step 7 — Unknown field validation

Add `validate_frontmatter_fields()` helper (in `dependency_mapper/analysis.py` or new file) that warns via `logger.warning()` when an issue's frontmatter contains an unrecognized relationship key (e.g., `parent_issue:` or `related:` after migration). Pattern: `caplog`-testable `logger.warning(...)`.

### Step 13 — `dependency_mapper/formatting.py` `format_text_graph()`

Decide whether `depends_on` edges should appear in the ASCII graph output and extend `format_text_graph()` accordingly. Current: iterates only `issue.blocked_by` for edges. Recommended: show `depends_on` edges with a distinct marker (e.g., `-->` vs `==>` for `blocked_by`).

## Files to Modify

- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`, `get_execution_waves()`
- `scripts/little_loops/dependency_mapper/analysis.py` — `validate_dependencies()`, new `validate_frontmatter_fields()`
- `scripts/little_loops/dependency_mapper/models.py` — `ValidationResult` dataclass (add `broken_depends_on_refs`, `broken_relates_to_refs` fields)
- `scripts/little_loops/dependency_mapper/operations.py` — new section call-sites; `_add_to_section()` anchor list
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph()` edge display
- `scripts/little_loops/sync.py` — `GitHubSyncManager._get_labels_for_issue()` (label mapping), `_push_single_issue()` (`duplicate_of` comment)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify (with line anchors)

- `scripts/little_loops/dependency_graph.py:52` — `DependencyGraph.from_issues()`: two existing passes at lines 93–124; add third pass reading `issue.depends_on`; internal fields are `blocked_by: dict[str, set[str]]` and `blocks: dict[str, set[str]]` — add parallel `depends_on_edges: dict[str, set[str]]`
- `scripts/little_loops/dependency_graph.py:154` — `get_execution_waves()`: BFS loop calling `get_ready_issues()`; `depends_on` soft-ordering should place targets in earlier waves without blocking dependents; the loop at lines 154–201 is the insertion point
- `scripts/little_loops/dependency_mapper/analysis.py:414` — `validate_dependencies()`: broken-ref loop at line 454 iterates only `issue.blocked_by`; extend with parallel loops for `depends_on`, `relates_to`, `duplicate_of`; `find_file_overlaps()` at lines 267–270 also reads only `issue.blocked_by` for its existing-dep skip-check — may need a parallel update so `depends_on` edges are not re-proposed
- `scripts/little_loops/dependency_mapper/models.py:53` — `ValidationResult` dataclass: four `list[tuple[str, str]]` fields; must add `broken_depends_on_refs` and `broken_relates_to_refs` fields using the same shape; also update `has_issues` property
- `scripts/little_loops/dependency_mapper/operations.py:21` — `apply_proposals()`: hardcodes `"Blocked By"` and `"Blocks"` section names; add `"Depends On"` and `"Relates To"` call-sites alongside them
- `scripts/little_loops/dependency_mapper/operations.py:108` — `_add_to_section()` anchor list: currently only `("## Labels", "## Status")`; must add `"## Depends On"` and `"## Relates To"` to the anchor list so the new sections are inserted in the right place
- `scripts/little_loops/dependency_mapper/formatting.py:128` — `format_text_graph()`: adjacency dict built at line 151 from `issue.blocked_by` only; current edge symbols are `──→` (existing blocked_by) and `-.→` (proposed); add `depends_on` edges with a distinct symbol (e.g., `-->`)
- `scripts/little_loops/sync.py:298` — `GitHubSyncManager._get_labels_for_issue()`: label attachment follows `args.extend(["--label", label])` pattern in `_create_github_issue()` at line 419; add `blocked-by` label here when `issue.blocked_by` is non-empty
- `scripts/little_loops/sync.py:374` — `GitHubSyncManager._push_single_issue()`: currently sends only title + body + labels; add `duplicate_of` closing-comment logic here (no native GitHub relationship API)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/dependency_mapper/formatting.py` `format_report()` — renders `ValidationResult` fields in named sections (lines ~86–119); must add `if v.broken_depends_on_refs:` and `if v.broken_relates_to_refs:` sections alongside existing `broken_refs`, `cycles`, etc. — otherwise new validation output is silently absent from the markdown report (only `format_text_graph()` was listed as changing in `formatting.py`)
- `scripts/little_loops/cli/deps.py` `main_deps()` validate branch — explicitly iterates named `ValidationResult` fields (`result.broken_refs`, `result.cycles`, etc.) and constructs a hardcoded JSON dict; new fields must be added to both text and `--format json` code paths or they are silently omitted from `ll-deps validate` output

#### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/deps.py` — `ll-deps` command uses dependency mapper directly; impacted by validation output changes
- `scripts/little_loops/sprint.py` — sprint wave planning uses `get_execution_waves()`; soft-ordering will propagate automatically
- `scripts/little_loops/cli/sprint/run.py` — sprint runner; consumes wave output

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/_helpers.py` — `_display_dependency_analysis()` renders `ValidationResult` fields one-by-one by name; `_render_execution_plan()` reads `dep_graph.blocked_by` for `"blocked by: ..."` annotations — both will silently omit new broken-ref data without explicit handling
- `scripts/little_loops/cli/sprint/show.py` — `_render_dependency_graph()` accesses `dep_graph.blocks`/`dep_graph.blocked_by` only; `depends_on_edges` will not appear in the sprint ASCII graph without extension
- `scripts/little_loops/cli/sync.py` — direct consumer of `GitHubSyncManager`; no code change required but is the surface where label and comment output changes will be observable

#### Similar Patterns

- `dependency_graph.py:93–124` — blocked_by/blocks two-pass pattern: exact model for the `depends_on` third pass (skip completed, skip unknown with `logger.warning`, build edges bidirectionally)
- `issue_parser.py:503–530` — frontmatter reconciliation loop already includes `depends_on` and `relates_to` — the parser is ready; only the consumers need updating
- `issue_parser.py:472–492` — deprecated-key alias pattern with `logger.warning("%s: deprecated ...", issue_path.name)` — model for `validate_frontmatter_fields()` warning style

#### Tests

- `scripts/tests/test_dependency_graph.py:14` — `make_issue()` helper (4 kwargs: `issue_id`, `priority`, `blocked_by`, `blocks`); add `depends_on: list[str] | None = None` kwarg and pass to `IssueInfo(depends_on=depends_on or [])`
- `scripts/tests/test_dependency_mapper.py:30` — `make_issue()` helper (same 4 kwargs + `title`); same `depends_on` kwarg extension needed
- `scripts/tests/test_dependency_graph.py:82` — caplog pattern for warning assertions: `assert "text" in caplog.text` (no `at_level` scoping)
- `scripts/tests/test_issue_parser.py:1603` — caplog pattern with logger scoping: `caplog.at_level(logging.WARNING, logger="little_loops.issue_parser")`; use `"little_loops.dependency_mapper.analysis"` for `validate_frontmatter_fields()` tests

## Tests

- `scripts/tests/test_dependency_graph.py` — add `test_depends_on_soft_ordering()` using `make_issue()` helper; extend `make_issue()` with `depends_on` kwarg; extend `get_execution_waves()` tests
- `scripts/tests/test_dependency_mapper.py` — add validation tests for broken refs in `depends_on`, `relates_to`, `duplicate_of`; extend `make_issue()` helper with `depends_on` kwarg
- `scripts/tests/test_cli_sync.py` — extend with relationship field mapping assertions (`blocked-by` label, `duplicate_of` comment)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_sync.py` — unit-level tests for `GitHubSyncManager._push_single_issue()` and `_get_labels_for_issue()`; add `test_get_labels_for_issue_with_blocked_by_adds_label()` and `test_push_single_issue_adds_duplicate_of_comment()` following the existing `test_push_single_issue_creates_new` / `test_get_labels_for_issue` patterns (note: `test_cli_sync.py` mocks `GitHubSyncManager` entirely and won't exercise this behavior)

## Implementation Steps

1. **Add `depends_on_edges` to `DependencyGraph`** (`dependency_graph.py:32`): add `depends_on_edges: dict[str, set[str]]` field alongside `blocked_by` and `blocks`; populate in `from_issues()` as a third pass at lines 93–124 following the exact same skip-completed/skip-unknown/`logger.warning` pattern
2. **Update `get_execution_waves()`** (`dependency_graph.py:154`): after each wave is collected, check whether any `depends_on` targets of remaining issues are not yet in `processed`; if so, reorder those targets to the earliest possible wave without introducing hard blocks
3. **Extend `ValidationResult`** (`dependency_mapper/models.py:53`): add `broken_depends_on_refs: list[tuple[str, str]] = field(default_factory=list)` and `broken_relates_to_refs: list[tuple[str, str]] = field(default_factory=list)`; update `has_issues` property to include both new fields
4. **Extend `validate_dependencies()`** (`dependency_mapper/analysis.py:454`): add parallel broken-ref loops for `issue.depends_on`, `issue.relates_to`, and `issue.duplicate_of` after the existing `blocked_by` loop; append to the new `ValidationResult` fields
5. **Add `validate_frontmatter_fields()`** (`dependency_mapper/analysis.py`): new function that iterates `IssueInfo` frontmatter keys and emits `logger.warning()` for any unrecognized relationship key (e.g., `parent_issue`, `related`); use `"little_loops.dependency_mapper.analysis"` logger
6. **Update `_add_to_section()` anchor list** (`dependency_mapper/operations.py:108`): extend the anchor tuple from `("## Labels", "## Status")` to `("## Depends On", "## Relates To", "## Labels", "## Status")` so new sections insert before labels
7. **Add `apply_proposals()` call-sites** (`dependency_mapper/operations.py:21`): add `_add_to_section(path, "Depends On", id)` and `_add_to_section(path, "Relates To", id)` alongside existing `"Blocked By"` and `"Blocks"` calls
8. **Extend `format_text_graph()`** (`dependency_mapper/formatting.py:151`): after building the `blocked_by` adjacency dict (current `──→` edges), add a second adjacency dict for `depends_on` edges using a distinct symbol (e.g., `-->`) to distinguish from hard-block arrows
9. **Map `blocked_by` to GitHub label** (`sync.py:298` `_get_labels_for_issue()`): when `issue.blocked_by` is non-empty, append `"blocked-by"` to the returned labels list; label attachment follows `args.extend(["--label", label])` in `_create_github_issue()` at line 419
10. **Add `duplicate_of` closing comment** (`sync.py:374` `_push_single_issue()`): after creating/updating the issue on GitHub, if `issue.duplicate_of` is set, post a closing comment referencing the duplicate target
11. **Extend `make_issue()` test helpers** (`test_dependency_graph.py:14`, `test_dependency_mapper.py:30`): add `depends_on: list[str] | None = None` kwarg; pass `depends_on=depends_on or []` to `IssueInfo` constructor
12. **Write new tests**: `test_depends_on_soft_ordering()` in `test_dependency_graph.py`; broken-ref validation tests for `depends_on`/`relates_to`/`duplicate_of` in `test_dependency_mapper.py`; label/comment mapping assertions in `test_cli_sync.py`
13. **Verify**: `python -m pytest scripts/tests/test_dependency_graph.py scripts/tests/test_dependency_mapper.py scripts/tests/test_cli_sync.py scripts/tests/test_sync.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. **Update `format_report()` in `formatting.py`** — add `if v.broken_depends_on_refs:` and `if v.broken_relates_to_refs:` rendering sections alongside the existing `broken_refs`, `cycles`, `missing_backlinks`, `stale_completed_refs` sections (lines ~86–119); otherwise new validation data is silently absent from the markdown report output
15. **Update `main_deps()` in `cli/deps.py`** — add display blocks for `result.broken_depends_on_refs` and `result.broken_relates_to_refs` in the text output path; add `"broken_depends_on_refs"` and `"broken_relates_to_refs"` keys to the `--format json` validation dict; these fields are computed but silently dropped without this change
16. **Add unit tests in `test_sync.py`** — `test_get_labels_for_issue_with_blocked_by_adds_label()` asserting `"blocked-by" in labels`; `test_push_single_issue_adds_duplicate_of_comment()` asserting a second `_run_gh_command` call for the closing comment

## Acceptance Criteria

- `DependencyGraph.from_issues()` builds soft-ordering edges from `depends_on` without treating them as hard blocks
- `get_execution_waves()` respects `depends_on` for soft ordering (target in earlier wave, not required)
- `validate_dependencies()` reports broken refs in `depends_on`, `relates_to`, `duplicate_of`
- `validate_frontmatter_fields()` emits `logger.warning()` for any unrecognized relationship key (`parent_issue:`, `related:`, etc.)
- `GitHubSyncManager` maps `blocked_by` to label and `duplicate_of` to closing comment
- `format_text_graph()` displays `depends_on` edges distinctly from `blocked_by`
- All new tests pass

## Scope Boundaries

- **In scope**: `dependency_graph.py`, `dependency_mapper/*`, `sync.py`, `formatting.py` changes and their tests
- **Out of scope**: Schema/parser (ENH-1430), migration script (ENH-1431), docs/skills (ENH-1433)
- **Depends on**: ENH-1430 — `IssueInfo.depends_on`, `.relates_to`, `.duplicate_of` fields must exist

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Broad caller surface across 6 downstream consumers**: `get_execution_waves()` and `ValidationResult` are consumed by sprint planning and CLI rendering layers; additive changes are safe, but 2 callers (`cli/sprint/_helpers.py`, `cli/sprint/show.py`) are explicitly out of scope and will silently omit new broken-ref data — track as follow-up
- **Wave soft-ordering logic requires BFS understanding**: Step 2 ("check whether any depends_on targets of remaining issues are not yet in processed; if so, reorder") has no exact code template to copy — the wave BFS loop (lines 154–201) needs careful reading before writing the reorder logic
- **Minor symbol/location choices to make during implementation**: depends_on edge marker ("`-->`" vs "`==>`") and whether `validate_frontmatter_fields()` goes in `analysis.py` or a new file — both resolvable in-flight

## Session Log
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `9b6b5119-a8d7-4a04-a179-aa73a8fe69af.jsonl`
- `/ll:refine-issue` - 2026-05-11T00:43:34 - `f84d544c-8201-4996-88fc-a05e83f88fd0.jsonl`
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00 - `current.jsonl`
- `/ll:issue-size-review` - 2026-05-10T23:55:00Z - `49b56280-19ff-42e9-bb93-088d6e560fa2.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- ENH-1436: DependencyGraph soft-ordering via `depends_on`
- ENH-1437: Validation infrastructure for new relationship fields
- ENH-1438: GitHub sync relationship field mapping
