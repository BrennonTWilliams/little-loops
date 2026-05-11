---
id: ENH-1437
type: ENH
priority: P2
parent: ENH-1432
depends_on:
- ENH-1430
status: done
completed_at: 2026-05-11T02:11:07Z
size: Large
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1437: Validation infrastructure for new relationship fields

## Summary

Extend `ValidationResult`, `validate_dependencies()`, and `format_report()` to cover `depends_on`, `relates_to`, and `duplicate_of` broken-ref detection. Add `validate_frontmatter_fields()` for unknown-key warnings. Update `dependency_mapper/operations.py` to support `"Depends On"` and `"Relates To"` sections. Extend `format_text_graph()` to display `depends_on` edges distinctly. Wire all new `ValidationResult` fields into `cli/deps.py` text and JSON output. Depends on ENH-1430.

## Current Behavior

`validate_dependencies()` in `dependency_mapper/analysis.py` only checks `blocked_by` references — broken refs in `depends_on`, `relates_to`, and `duplicate_of` are silently ignored. `ValidationResult` has no fields for these relationship types. There is no `validate_frontmatter_fields()` function to warn about stale or deprecated frontmatter keys. `format_text_graph()` renders only `blocked_by` edges; `cli/deps.py` and `format_report()` expose only the 4 existing validation categories in both text and JSON output. `operations.py` only supports inserting into `"Blocked By"` and `"Blocks"` sections.

## Expected Behavior

`validate_dependencies()` detects broken references in `depends_on`, `relates_to`, and `duplicate_of`. `ValidationResult` exposes `broken_depends_on_refs` and `broken_relates_to_refs` fields; `has_issues` includes them. A new `validate_frontmatter_fields()` function emits `logger.warning()` for unrecognized/deprecated relationship keys (e.g., `parent_issue:`, `related:`). `format_report()` and `cli/deps.py` surface all new validation data in text and JSON output. `format_text_graph()` renders `depends_on` edges with a distinct symbol (`-->`). `operations.py` supports `"Depends On"` and `"Relates To"` section insertion.

## Parent Issue

Decomposed from ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Scope

Covers implementation steps 3, 4, 5, 6, 7, 8 (parent issue), plus wiring steps 14 and 15 from the parent's Wiring Phase. Tests: `test_dependency_mapper.py` `make_issue()` extension and broken-ref validation tests.

## Proposed Solution

### Step 3 — Extend `ValidationResult` (`dependency_mapper/models.py:54`)

Add two new fields using the same `list[tuple[str, str]]` shape as existing fields:
```python
broken_depends_on_refs: list[tuple[str, str]] = field(default_factory=list)
broken_relates_to_refs: list[tuple[str, str]] = field(default_factory=list)
```
Update `has_issues` property to include both new fields.

### Step 4 — Extend `validate_dependencies()` (`dependency_mapper/analysis.py:454`)

After the existing `blocked_by` broken-ref loop, add parallel loops for `issue.depends_on`, `issue.relates_to`, and `issue.duplicate_of`. Append findings to the new `ValidationResult` fields.

Also check: `find_file_overlaps()` at lines 267–270 reads only `issue.blocked_by` for its existing-dep skip-check — add parallel check for `depends_on` edges so they are not re-proposed.

### Step 5 — Add `validate_frontmatter_fields()` (`dependency_mapper/analysis.py`)

New function that iterates issue frontmatter keys and emits `logger.warning()` for any unrecognized relationship key (e.g., `parent_issue:`, `related:` — stale names after the ENH-1434 migration). Use `"little_loops.dependency_mapper.analysis"` logger.

Model after the deprecated-key alias pattern at `issue_parser.py:472–492`.

### Steps 6 & 7 — `dependency_mapper/operations.py`

**Step 6** (`operations.py:108` `_add_to_section()` anchor list): Extend anchor tuple from `("## Labels", "## Status")` to `("## Depends On", "## Relates To", "## Labels", "## Status")` so new sections insert before labels.

**Step 7** (`operations.py:21` `apply_proposals()`): Add `_add_to_section(path, "Depends On", id)` and `_add_to_section(path, "Relates To", id)` call-sites alongside existing `"Blocked By"` and `"Blocks"` calls.

### Step 8 — `format_text_graph()` (`dependency_mapper/formatting.py:151`)

After building the `blocked_by` adjacency dict (current `──→` edges), add a second adjacency dict for `depends_on` edges using a distinct symbol (e.g., `-->`) to distinguish from hard-block arrows.

### Step 14 (Wiring) — `format_report()` (`dependency_mapper/formatting.py`)

Add `if v.broken_depends_on_refs:` and `if v.broken_relates_to_refs:` rendering sections alongside existing `broken_refs`, `cycles`, `missing_backlinks`, `stale_completed_refs` sections (lines ~86–119). Without this, new validation data is silently absent from the markdown report.

### Step 15 (Wiring) — `main_deps()` in `cli/deps.py`

Add display blocks for `result.broken_depends_on_refs` and `result.broken_relates_to_refs` in the text output path. Add `"broken_depends_on_refs"` and `"broken_relates_to_refs"` keys to the `--format json` validation dict. Without this, computed data is silently dropped from `ll-deps validate` output.

## Files to Modify

- `scripts/little_loops/dependency_mapper/models.py` — `ValidationResult` dataclass
- `scripts/little_loops/dependency_mapper/analysis.py` — `validate_dependencies()`, new `validate_frontmatter_fields()`
- `scripts/little_loops/dependency_mapper/operations.py` — anchor list, `apply_proposals()` call-sites
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_text_graph()`, `format_report()`
- `scripts/little_loops/cli/deps.py` — text and JSON output for new fields
- `scripts/little_loops/dependency_mapper/__init__.py` — add `validate_frontmatter_fields` to `from .analysis import (...)` block, `__all__`, and "Public exports" docstring [wiring pass]

## Dependent Files (Callers — no code change required)

- `scripts/little_loops/cli/sprint/_helpers.py` — `_display_dependency_analysis()` renders `ValidationResult` fields by name; new fields will appear automatically once wiring step 14+15 is in place
- `scripts/little_loops/cli/sprint/show.py` — `_render_dependency_graph()` accesses only `dep_graph.blocked_by`; `depends_on_edges` display is out-of-scope here (would require ENH-1436 to land first)

**Note (wiring pass):** `_display_dependency_analysis()` in `_helpers.py` directly reads only `broken_refs`, `stale_completed_refs`, and `missing_backlinks` — not `cycles`, and not the new fields. Once `has_issues` becomes True for broken `depends_on`/`relates_to` refs, the sprint display block will open but produce no output for those new fields. This is an **accepted in-scope gap** (sprint rendering of these fields is not part of ENH-1437's scope), but callers of `has_issues` from sprint context should be aware of this silent behavior.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified line references — `models.py`:**
- `ValidationResult` dataclass at lines 54–74; `has_issues` property at line 69
- Current 4 fields: `broken_refs`, `missing_backlinks`, `cycles`, `stale_completed_refs` — all `blocked_by`-scoped

**Verified line references — `analysis.py`:**
- `logger = logging.getLogger(__name__)` at line 26 → logger name `"little_loops.dependency_mapper.analysis"`
- `validate_dependencies()` starts at line 414; broken-ref loop for `blocked_by` at lines 453–458
- Existing-dep skip-check in `find_file_overlaps()` at lines 267–270 (reads only `issue.blocked_by`)
- `validate_frontmatter_fields()` does not yet exist anywhere in the codebase

**Verified line references — `formatting.py`:**
- `format_report()` validation section at lines 84–119 (renders exactly 4 subsections)
- `format_text_graph()` starts at line 128; `blocked_by` adjacency dict built at lines 151–155

**Verified line references — `operations.py`:**
- `apply_proposals()` starts at line 21; writes only `"Blocked By"` and `"Blocks"` sections
- `_add_to_section()` anchor list at lines 108–116: current tuple is `("## Labels", "## Status")`

**Verified line references — `cli/deps.py`:**
- `main_deps()` `validate` branch text output at lines 334–357
- JSON `"validation"` dict at lines 304–310: serializes 4 keys + `has_issues`; no `depends_on`/`relates_to` keys

**ENH-1430 dependency status:**
- `IssueInfo.depends_on: list[str]` already exists at `issue_parser.py:251`
- `IssueInfo.relates_to: list[str]` already exists at `issue_parser.py:252`
- `IssueInfo.duplicate_of: str | None` already exists at `issue_parser.py:253`
- The fields this issue depends on are already in the codebase; ENH-1430 is a tracking dependency only

## Tests

- `scripts/tests/test_dependency_mapper.py:30` — extend `make_issue()` helper: add `depends_on: list[str] | None = None` kwarg
- Add broken-ref validation tests for `depends_on`, `relates_to`, `duplicate_of` — assert new `ValidationResult` fields are populated
- Add `validate_frontmatter_fields()` tests using `caplog.at_level(logging.WARNING, logger="little_loops.dependency_mapper.analysis")`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`make_issue()` current signature** (`test_dependency_mapper.py:30`):
```python
def make_issue(
    issue_id: str,
    priority: str = "P1",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
    title: str | None = None,
) -> IssueInfo:
```
Extend with: `depends_on: list[str] | None = None`, `relates_to: list[str] | None = None`, `duplicate_of: str | None = None`
— use the same `or []` / `or None` guard pattern already used by `blocked_by`

**Note on `duplicate_of`**: It is `str | None` (scalar), not `list[str]`. The broken-ref check for it collapses to `if issue.duplicate_of and issue.duplicate_of not in all_known: ...` rather than a list loop.

**Broken-ref assertion pattern** (model from `TestValidateDependencies`, lines 531–624):
```python
issues = [make_issue("FEAT-001", depends_on=["BUG-999"])]
result = validate_dependencies(issues)
assert ("FEAT-001", "BUG-999") in result.broken_depends_on_refs
```

**`caplog` assertion pattern for `validate_frontmatter_fields()`** (model from `test_issue_parser.py:1679–1707`):
```python
with caplog.at_level(logging.WARNING, logger="little_loops.dependency_mapper.analysis"):
    validate_frontmatter_fields(issues)
assert any("parent_issue" in r.message for r in caplog.records)
assert any("deprecated" in r.message for r in caplog.records)
```

**`format_report()` test pattern** (model from `TestFormatReport`, lines 765–824):
```python
report = DependencyReport(
    validation=ValidationResult(broken_depends_on_refs=[("FEAT-001", "BUG-999")]),
    issue_count=1,
)
text = format_report(report)
assert "BUG-999" in text
```

**`format_text_graph()` test pattern** for new `depends_on` edges (model from `TestFormatTextGraph`, lines 904–949):
```python
# Current arrow symbols: blocked_by = "──→", proposed = "-.→"
# Suggested new symbol for depends_on: "-->"
issues = [make_issue("FEAT-001"), make_issue("FEAT-002", depends_on=["FEAT-001"])]
text = format_text_graph(issues)
assert "FEAT-001 --> FEAT-002" in text
```

**Existing test class locations** to add new tests alongside:
- `TestValidateDependencies` at `test_dependency_mapper.py:531`
- `TestFormatReport` at `test_dependency_mapper.py:765`
- `TestFormatTextGraph` at `test_dependency_mapper.py:904`

### Tests — Wiring Pass

_Wiring pass added by `/ll:wire-issue`:_

**Test to update (will break after Step 8):**
- `scripts/tests/test_dependency_mapper.py::TestFormatTextGraph.test_no_edges()` (line ~941) — currently asserts `"──→" not in text` and `"-.→" not in text`; after Step 8 adds `-->` for `depends_on` edges, must also assert `"-->" not in text` to document that a graph with no edges shows no arrows at all.

**Documentation tests (no existing counterpart in test_dependency_mapper.py):**
- `TestMainCLI` — add `test_validate_text_output_includes_broken_depends_on_refs()`: set up issue with a broken `depends_on` ref, run `ll-deps validate`, assert text contains the ref
- `TestMainCLI` — add `test_validate_json_output_includes_new_fields()`: run `ll-deps analyze --format json`, assert `"broken_depends_on_refs"` and `"broken_relates_to_refs"` appear as keys in the `"validation"` dict

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md` — "ValidationResult" subsection enumerates all four current fields in a table; add `broken_depends_on_refs` and `broken_relates_to_refs` rows. Also add a new `validate_frontmatter_fields()` function entry under the `little_loops.dependency_mapper` section.
- `docs/reference/OUTPUT_STYLING.md` — "Dependency Map" section describes arrow symbols (`──→` blocked-by, `-.→` proposed); add row for `depends_on` edge symbol (`-->`).
- `skills/map-dependencies/SKILL.md` — "Validation Issues" subsection lists categories as bullet points ("Broken references", "Missing backlinks", "Cycles", "Stale references"); add new bullets for "Broken depends-on references" and "Broken relates-to references" to keep the skill's "Interpreting Results" guidance current.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

16. Add `validate_frontmatter_fields` to `scripts/little_loops/dependency_mapper/__init__.py` — add to the `from .analysis import (...)` block, the `__all__` list, and the "Public exports" docstring section. (The function is currently absent from all three; without this, callers must use the sub-module path rather than the package-level import.)
17. Update `docs/reference/API.md` — add `broken_depends_on_refs` and `broken_relates_to_refs` to the "ValidationResult" field table; add a `validate_frontmatter_fields()` function entry.
18. Update `docs/reference/OUTPUT_STYLING.md` — add the new `-->` `depends_on` edge arrow to the arrow-symbol table in the "Dependency Map" section.
19. Update `skills/map-dependencies/SKILL.md` — add "Broken depends-on references" and "Broken relates-to references" bullets to the "Validation Issues" subsection.
20. Update `scripts/tests/test_dependency_mapper.py::TestFormatTextGraph.test_no_edges()` — add `assert "-->" not in text` alongside the existing arrow-symbol absence assertions.

## Acceptance Criteria

- `ValidationResult` has `broken_depends_on_refs` and `broken_relates_to_refs` fields; `has_issues` includes them
- `validate_dependencies()` reports broken refs in `depends_on`, `relates_to`, `duplicate_of`
- `validate_frontmatter_fields()` emits `logger.warning()` for unrecognized relationship keys
- `format_report()` renders new broken-ref sections in the markdown report
- `cli/deps.py` shows and JSON-encodes new fields in `ll-deps validate` output
- `format_text_graph()` shows `depends_on` edges with distinct marker
- `operations.py` supports `"Depends On"` and `"Relates To"` section insertion
- All new tests pass; all existing dependency mapper tests pass

## Scope Boundaries

- **In scope**: `dependency_mapper/*`, `cli/deps.py`, and their tests
- **Out of scope**: `dependency_graph.py` wave planning (ENH-1436), `sync.py` (ENH-1438)
- **Depends on**: ENH-1430 — `IssueInfo.depends_on`, `.relates_to`, `.duplicate_of` fields must exist

## Impact

- **Priority**: P2 — Dependency validation is incomplete without covering all relationship fields; broken refs in `depends_on`/`relates_to` are silently dropped, misleading users
- **Effort**: Large — Multiple files across the dependency mapper stack (`models.py`, `analysis.py`, `operations.py`, `formatting.py`, `cli/deps.py`, `__init__.py`) plus tests and docs
- **Risk**: Low — Additive changes to the existing validation framework; no breaking changes to existing fields or CLI contracts
- **Breaking Change**: No

## Labels

`enhancement`, `dependency-mapper`, `validation`, `relationship-fields`

## Status

**Done** | Priority: P2

## Resolution

Implemented all steps (3–8, 14–15, 16–19) from the issue specification:

- `ValidationResult` extended with `broken_depends_on_refs` and `broken_relates_to_refs` fields; `has_issues` updated
- `validate_dependencies()` now checks `depends_on`, `relates_to`, and `duplicate_of` broken refs
- `find_file_overlaps()` skip-check extended to include `depends_on` edges
- `validate_frontmatter_fields()` added — reads raw file frontmatter and warns about deprecated keys (`parent_issue:`, `related:`)
- `operations.py` anchor list extended to `("## Depends On", "## Relates To", "## Labels", "## Status")`; `apply_proposals()` routes by `reason` to the correct section
- `format_text_graph()` renders `depends_on` edges with `-->` symbol and updates the legend
- `format_report()` renders new `Broken Depends-On References` and `Broken Relates-To References` subsections
- `cli/deps.py` text and JSON output include both new fields
- `__init__.py` exports `validate_frontmatter_fields`
- 20 new tests added across `TestValidateDependenciesNewFields`, `TestValidateFrontmatterFields`, `TestFormatReportNewFields`, `TestFormatTextGraphDependsOn`, and `TestMainCLI`; `test_no_edges` updated with `"-->" not in text` assertion
- Docs updated: `API.md` (ValidationResult table + `validate_frontmatter_fields` entry), `OUTPUT_STYLING.md` (new `-->` arrow row), `skills/map-dependencies/SKILL.md` (new validation bullets)

## Session Log
- `/ll:ready-issue` - 2026-05-11T01:37:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/056c07a7-25fa-45fa-882b-bf254f412bf4.jsonl`
- `/ll:refine-issue` - 2026-05-11T01:22:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a23cd4a-172a-4bc4-bdec-31781fb6813a.jsonl`
- `/ll:issue-size-review` - 2026-05-10T23:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49b56280-19ff-42e9-bb93-088d6e560fa2.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3056e4af-db90-4852-aa0f-e61167d2053e.jsonl`
- `/ll:manage-issue` - 2026-05-11T02:11:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
