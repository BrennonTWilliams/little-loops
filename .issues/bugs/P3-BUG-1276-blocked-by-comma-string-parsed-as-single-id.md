---
id: BUG-1276
type: BUG
priority: P3
title: "blocked_by comma-separated string parsed as single unknown ID"
status: done
captured_at: "2026-04-24T21:09:29Z"
completed_at: "2026-04-24T22:26:53Z"
discovered_date: "2026-04-24"
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-1276: blocked_by comma-separated string parsed as single unknown ID

## Summary

`ll-issues clusters` outputs messages like "Issue X blocked by unknown issues Issue Y and Issue Z" when the `blocked_by` frontmatter field is a comma-separated YAML string (e.g., `blocked_by: "ENH-419, ENH-422, ENH-423"`) rather than a proper YAML list. The dependency checker receives the whole string as a single ID and cannot match it against known issues.

## Current Behavior

`ll-issues clusters` (and any command invoking `build_dependency_graph`) reports "blocked by unknown issues ENH-419, ENH-422, ENH-423" — treating the entire comma-separated string as one opaque ID rather than splitting it into three individual issue IDs.

## Root Cause

**File**: `scripts/little_loops/issue_parser.py:436`

```python
fm_ids = [fm_val] if isinstance(fm_val, str) else list(fm_val)
```

When `blocked_by` is a string (as YAML allows for scalars), the code wraps the entire value in a list — e.g., `["ENH-419, ENH-422, ENH-423"]` — instead of splitting on commas to produce `["ENH-419", "ENH-422", "ENH-423"]`.

## Steps to Reproduce

1. Write an issue with frontmatter `blocked_by: "ENH-419, ENH-422, ENH-423"` (scalar string, not a list).
2. Run `ll-issues clusters` (or any command that invokes `build_dependency_graph`).
3. Observe: "blocked by unknown issues ENH-419, ENH-422, ENH-423" — treated as one opaque ID.

## Expected Behavior

When `blocked_by` is a scalar string, split on commas and strip whitespace to extract individual issue IDs, matching the behavior of a proper YAML list.

## Proposed Solution

```python
if isinstance(fm_val, str):
    fm_ids = [id.strip() for id in fm_val.split(",") if id.strip()]
else:
    fm_ids = list(fm_val)
```

Apply the same fix to the `blocks` field for consistency (same code path handles both).

## Implementation Steps

1. Edit `scripts/little_loops/issue_parser.py:436` — replace the scalar-wrap branch with split-and-strip:
   ```python
   # before:
   fm_ids = [fm_val] if isinstance(fm_val, str) else list(fm_val)
   # after:
   fm_ids = [id.strip() for id in fm_val.split(",") if id.strip()] if isinstance(fm_val, str) else list(fm_val)
   ```
   This single-line change covers both `blocked_by` and `blocks` (same loop at lines 432–449).
2. Add tests to `scripts/tests/test_issue_parser.py` inside `TestDependencyParsing` (around line 1103) using the inline `write_text` pattern (see `test_issue_parser.py:1422`):
   - `test_blocked_by_comma_string_frontmatter` — scalar `"ENH-419, ENH-422, ENH-423"` → `["ENH-419", "ENH-422", "ENH-423"]`
   - `test_blocks_comma_string_frontmatter` — same coverage for `blocks` field
   - `test_blocked_by_yaml_list_frontmatter_unchanged` — proper YAML list still works
   - `test_blocked_by_comma_string_whitespace_variants` — `" ENH-419 , ENH-422 "` strips correctly
3. Run `python -m pytest scripts/tests/test_issue_parser.py::TestDependencyParsing -v` to verify new tests pass
4. Run full suite `python -m pytest scripts/tests/ -x` to confirm no regressions in `test_dependency_graph.py`, `test_issues_cli.py`, or `test_cli.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `build_dependency_graph` function, `blocked_by`/`blocks` parsing (line ~436)

### Dependent Files (Callers/Importers)

Consumers of `IssueInfo.blocked_by` / `IssueInfo.blocks` that will silently receive bad data until this is fixed:

- `scripts/little_loops/dependency_graph.py:94` — `DependencyGraph.from_issues()` loops `for blocker_id in issue.blocked_by`; opaque string fails ID lookup → unknown-issue warning + edge skipped
- `scripts/little_loops/dependency_mapper/analysis.py:450–464` — `validate_dependencies()` iterates `issue.blocked_by`; comma-string ID flagged as broken ref
- `scripts/little_loops/dependency_mapper/analysis.py:497` — `analyze_dependencies()` counts `len(issue.blocked_by)` — count inflated to 1 instead of N
- `scripts/little_loops/dependency_mapper/formatting.py:153` — `format_text_graph()` renders each `blocked_by` entry; renders garbage ID in ASCII graph
- `scripts/little_loops/issue_manager.py:824` — `AutoManager.__init__` builds `DependencyGraph` on startup
- `scripts/little_loops/cli/issues/clusters.py:193` — calls `DependencyGraph.from_issues()` → produces wrong cluster groupings
- `scripts/little_loops/cli/issues/sequence.py` — uses `DependencyGraph` for implementation ordering
- `scripts/little_loops/cli/deps.py:57` — `ll-deps` CLI entry point for dependency validation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — imports `DependencyGraph`; sprint waves built from dependency edges, silently receives wrong groupings with comma-string IDs [Agent 1 finding]
- `scripts/little_loops/cli/sprint/show.py` — imports `DependencyGraph`; sprint display affected by incorrect dependency resolution [Agent 1 finding]
- `scripts/little_loops/cli/sprint/manage.py` — imports `DependencyGraph`; sprint management commands impacted by corrupt dependency graph [Agent 1 finding]
- `scripts/little_loops/cli/sprint/_helpers.py` — uses `DependencyGraph`, `WaveContentionNote`; wave contention logic receives wrong blocked-by counts [Agent 1 finding]

### Similar Patterns

- `scripts/little_loops/frontmatter.py:67–69` — existing comma-split logic for `[...]` flow sequences; same strip-and-split approach applies here for bare/quoted scalar strings
- `scripts/little_loops/issue_parser.py:405–412` — `isinstance(fm_val, str)` branch for `testable` boolean coercion (same pattern, different semantics; confirms no other list fields need this fix)

### Tests

- `scripts/tests/test_issue_parser.py:1103` — `TestDependencyParsing` class: add two new test methods using inline `write_text` with frontmatter (not fixture files — no fixtures cover frontmatter `blocked_by` yet)
- `scripts/tests/test_dependency_graph.py:32` — `TestDependencyGraphConstruction`: if adding graph-level coverage, use `make_issue()` helper at line 14 to bypass the parser
- Follow **inline frontmatter pattern** from `test_issue_parser.py:1422–1474` (scalar fields via `write_text`): write `"---\nblocked_by: \"ENH-419, ENH-422, ENH-423\"\n---\n# BUG-...\n"` and assert `info.blocked_by == ["ENH-419", "ENH-422", "ENH-423"]`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py:TestIssuesCLIClusters` — integration test gap: the class at line 3042 tests `ll-issues clusters` end-to-end but all fixtures use `## Blocked By` body-section format; consider adding a test with a comma-string frontmatter `blocked_by` to verify the fix propagates through the full CLI stack [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [x] `ll-issues clusters` resolves individual IDs from a comma-separated `blocked_by` string
- [x] `ll-issues clusters` resolves individual IDs from a comma-separated `blocks` string
- [x] Proper YAML lists (`blocked_by: [ENH-419, ENH-422]`) continue to work unchanged
- [x] Unit test: both scalar string and list forms produce identical `IssueInfo.blocked_by`

## Impact

- **Priority**: P3 — Affects dependency graph display; workaround exists (use YAML list syntax)
- **Effort**: Small — Single-line fix applied to two fields; one unit test to add
- **Risk**: Low — Well-isolated parsing change; proper YAML list form is unaffected
- **Breaking Change**: No

## Labels

`bug`, `issue-parser`, `dependency-graph`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

---

## Session Log
- `/ll:manage-issue` - 2026-04-24T22:26:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e78fef57-05f1-4ce5-8326-26b6ffb52829.jsonl`
- `/ll:ready-issue` - 2026-04-24T22:22:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e78fef57-05f1-4ce5-8326-26b6ffb52829.jsonl`
- `/ll:confidence-check` - 2026-04-24T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a569ccc4-9bd7-423a-9431-4a4a4eaaffc5.jsonl`
- `/ll:wire-issue` - 2026-04-24T22:19:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e89548a9-8365-4739-88ca-be1c7bce6417.jsonl`
- `/ll:refine-issue` - 2026-04-24T22:13:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/285ca5b2-ab93-4805-8e70-e634e974ebf0.jsonl`
- `/ll:format-issue` - 2026-04-24T21:11:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/baf6354e-f895-4724-a14b-8b08bc94c4ee.jsonl`
- `/ll:capture-issue` - 2026-04-24T21:09:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6dacfdc-344c-4b81-a7b8-929038236222.jsonl`
