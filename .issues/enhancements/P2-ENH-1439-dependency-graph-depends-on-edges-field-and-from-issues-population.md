---
id: ENH-1439
type: ENH
priority: P2
parent: ENH-1436
depends_on:
- ENH-1430
status: done
completed_at: 2026-05-11T03:40:58Z
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1439: Add `depends_on_edges` field to DependencyGraph and populate in `from_issues()`

## Summary

Add `depends_on_edges: dict[str, set[str]] = field(default_factory=dict)` to the `DependencyGraph` dataclass and implement the third-pass population loop in `from_issues()`. This is Step 1 of ENH-1436: purely additive — no behavioral change to wave generation. Includes test helper extensions and field-level tests.

## Current Behavior

The `DependencyGraph` dataclass has no `depends_on_edges` field. The `from_issues()` method does not process `IssueInfo.depends_on` lists, so soft dependency relationships between issues are not tracked as directed graph edges.

## Expected Behavior

`DependencyGraph` has a `depends_on_edges: dict[str, set[str]]` field (default empty dict). After calling `from_issues()`, the field is populated from each issue's `IssueInfo.depends_on` list using the same 4-guard pattern as the `blocked_by`/`blocks` passes. Completed-target and unknown-target guards behave identically to the existing implementation.

## Motivation

This enhancement is Step 1 of ENH-1436 (DependencyGraph soft-ordering via `depends_on`). Without `depends_on_edges`:
- ENH-1440 cannot implement `get_execution_waves()` changes that respect soft dependencies
- The `depends_on` relationship field in issue frontmatter has no runtime representation in the graph

This step is purely additive — no behavioral change to wave generation — making it low-risk and safe to land independently.

## Parent Issue

Decomposed from ENH-1436: DependencyGraph soft-ordering via `depends_on`

## Scope Boundaries

Step 1 from ENH-1436 plus the `test_dependency_graph.py` helper extensions and field-level test cases. Does **not** include `get_execution_waves()` changes (those are ENH-1440).

## Proposed Solution

### Step 1 — Add `depends_on_edges` to `DependencyGraph` (`dependency_graph.py:32`)

Add field alongside `blocked_by` and `blocks`:

```python
depends_on_edges: dict[str, set[str]] = field(default_factory=dict)
```

Populate in `from_issues()` as a third pass (after the existing two-pass blocked_by/blocks loop at lines 93–124), following the exact same 4-guard pattern:
1. Skip completed issues
2. Skip unknown issue IDs in `all_issue_ids` with `logger.warning()`
3. Use suppression via `all_known_ids` to avoid double-warnings
4. Build directional edges: `A depends_on B` → `depends_on_edges["A"] = {"B"}`

`depends_on` is one-directional (dependent → target). Do **not** build a reverse `dependents_of` edge in this issue.

### Warning String

Use: `f"Issue {issue.issue_id} has depends_on unknown issue {target_id}"` — this substring must NOT contain `"blocked by unknown issue"` or `"blocks unknown issue"` to avoid false matches in existing caplog tests.

### Similar Pattern (exact model)

`dependency_graph.py:92–124` — blocked_by/blocks two-pass pattern: same 4-guard structure.

## Implementation Steps

1. Add `depends_on_edges: dict[str, set[str]] = field(default_factory=dict)` to `DependencyGraph` dataclass alongside `blocked_by` and `blocks`
2. Implement third-pass population loop in `from_issues()` with 4-guard pattern (skip completed, warn unknown, suppress double-warnings, build directional edges)
3. Extend `make_issue()` and `_make_issue_with_content()` test helpers with `depends_on` kwarg
4. Add 3 new test cases: `test_depends_on_edges_populated`, `test_depends_on_completed_target_skipped`, `test_depends_on_unknown_target_warns`
5. Run full test suite to verify all existing `test_dependency_graph.py` tests still pass
6. Update `docs/reference/API.md` — add `depends_on_edges: dict[str, set[str]]` row to the `DependencyGraph` Attributes table alongside `blocked_by` and `blocks`

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` dataclass, `from_issues()`
- `scripts/tests/test_dependency_graph.py` — helper extensions + 3 new test cases

### Dependent Files (Callers/Importers)
All callers of `DependencyGraph.from_issues()` — none require changes for this issue (additive field). ENH-1440 will be the first to consume `depends_on_edges`:
- `scripts/little_loops/issue_manager.py:1003` — `DependencyGraph.from_issues()` for issue lifecycle management
- `scripts/little_loops/dependency_mapper/analysis.py:481` — `DependencyGraph.from_issues()` for cycle detection
- `scripts/little_loops/cli/sprint/run.py:220` — `DependencyGraph.from_issues()` for sprint execution
- `scripts/little_loops/cli/sprint/show.py:181` — `DependencyGraph.from_issues()` for sprint visualization
- `scripts/little_loops/cli/sprint/manage.py:99` — `DependencyGraph.from_issues()` for sprint management
- `scripts/little_loops/cli/issues/sequence.py:34` — `DependencyGraph.from_issues()` for issue sequencing
- `scripts/little_loops/cli/issues/clusters.py:202` — `DependencyGraph.from_issues()` for cluster visualization
- `scripts/tests/test_cli.py:1020` — bare `DependencyGraph()` constructor must stay backward-compatible (satisfied by `field(default_factory=dict)`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/_helpers.py` — imports `DependencyGraph` and `WaveContentionNote`, accesses `.blocked_by` attribute; no changes needed (additive field) [Agent 1 finding]

### Similar Patterns
- `dependency_graph.py:92–124` — `blocked_by`/`blocks` two-pass pattern (exact model for the third pass)

### Tests
- `scripts/tests/test_dependency_graph.py` — see Tests section for specific test cases

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_sprint_integration.py` — 3 calls to `DependencyGraph.from_issues()` at lines 249, 1260, 1308; additive-safe, no updates needed [Agent 1 finding]
- `scripts/tests/test_dependency_mapper.py` — uses `make_issue()` helper from `test_dependency_graph.py`; additive-safe since `depends_on` kwarg has a default [Agent 1 finding]
- **Caplog risk**: `test_known_id_not_in_graph_no_warning` (line 91) asserts `"unknown issue" not in caplog.text`. The new warning `"has depends_on unknown issue"` contains that substring. Safe as-is because that test's fixture has no `depends_on` entries — but confirm after extending helpers. [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `DependencyGraph` Attributes table documents `issues`, `blocked_by`, `blocks` fields; must add `depends_on_edges` row [Agent 2 finding]

### Configuration
- N/A

## Tests

1. **Extend `make_issue()` helper** (line 14): add `depends_on: list[str] | None = None` kwarg; pass `depends_on=depends_on or []` to `IssueInfo` constructor.
2. **Extend `_make_issue_with_content()` helper** (line 671): same `depends_on` kwarg pattern.
3. **`test_depends_on_edges_populated()`**: after `from_issues()`, assert `graph.depends_on_edges["A"] == {"B"}` for a simple A-depends-on-B case (mirrors `test_linear_chain()` at line 54).
4. **`test_depends_on_completed_target_skipped()`**: `depends_on` pointing at a completed ID is not added as an edge (mirrors `test_completed_blocker_not_added()` at line 118).
5. **`test_depends_on_unknown_target_warns()`**: unknown `depends_on` ID emits `logger.warning()` with substring `"depends_on unknown issue"` — caplog pattern from line 82, no `caplog.at_level()` context manager needed.

## Acceptance Criteria

- `DependencyGraph.depends_on_edges` field exists with `field(default_factory=dict)` (backward-compatible — bare `DependencyGraph()` constructor at `test_cli.py:1020` must not break)
- `from_issues()` populates `depends_on_edges` from `IssueInfo.depends_on` lists
- Completed-target and unknown-target guards work identically to `blocked_by`/`blocks` pattern
- Unknown target warning substring is distinct from existing warning substrings
- `test_depends_on_edges_populated`, `test_depends_on_completed_target_skipped`, `test_depends_on_unknown_target_warns` all pass
- All existing `test_dependency_graph.py` tests still pass

## Impact

- **Priority**: P2 — Blocks ENH-1440 (`get_execution_waves()` soft-ordering); required Step 1 of ENH-1436
- **Effort**: Small — Purely additive field plus one population pass; mirrors existing pattern exactly
- **Risk**: Low — No behavioral change to wave generation; backward-compatible (`DependencyGraph()` constructor still works at `test_cli.py:1020`)
- **Breaking Change**: No

## Labels

`enhancement`, `dependency-graph`, `data-model`

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-11T03:40:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-11T03:35:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43f2765e-b722-4c2e-95a2-8abbb8af40ec.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8188c78-a952-45d6-9ed6-345dfd9a16b2.jsonl`
- `/ll:wire-issue` - 2026-05-11T03:17:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfb07734-959c-4a53-9fae-e51a41074ba4.jsonl`
- `/ll:refine-issue` - 2026-05-11T03:10:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe60117f-d096-4a7d-b5b5-6280dd0dffb5.jsonl`
- `/ll:format-issue` - 2026-05-11T03:06:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81e98002-62c7-4b53-8124-c473cde0a16e.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
