---
id: ENH-1436
type: ENH
priority: P2
parent: ENH-1432
depends_on:
- ENH-1430
status: done
size: Very Large
decision_needed: false
confidence_score: 95
outcome_confidence: 66
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
---

# ENH-1436: DependencyGraph soft-ordering via `depends_on`

## Summary

Add a third pass to `DependencyGraph.from_issues()` that builds `depends_on_edges` for soft-ordering, then update `get_execution_waves()` to place `depends_on` targets in earlier waves without hard-blocking the dependent. Depends on ENH-1430 (`IssueInfo.depends_on` field must exist).

## Parent Issue

Decomposed from ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Scope

Covers implementation steps 1 and 2 from the parent, plus the `test_dependency_graph.py` test helper extension and `test_depends_on_soft_ordering()` test.

## Proposed Solution

### Step 1 — Add `depends_on_edges` to `DependencyGraph` (`dependency_graph.py:32`)

Add `depends_on_edges: dict[str, set[str]]` field alongside `blocked_by` and `blocks`. Populate in `from_issues()` as a third pass at lines 93–124 following the exact same pattern:
- Skip completed issues
- Skip unknown issue IDs with `logger.warning()`
- Build edges (directional: `A depends_on B` → A's soft prereq is B)

Do NOT make `depends_on` bidirectional in the same way as `blocked_by/blocks` — `depends_on` is one-directional (dependent → target).

### Step 2 — Update `get_execution_waves()` (`dependency_graph.py:154`)

After each wave is collected, check whether any `depends_on` targets of remaining issues are not yet in `processed`. If so, reorder those targets to the earliest possible wave without introducing hard blocks.

The BFS loop at lines 154–201 is the insertion point. Key constraint: `depends_on` never prevents an issue from entering a wave; it only nudges targets forward.

### Similar Patterns

- `dependency_graph.py:93–124` — blocked_by/blocks two-pass pattern: exact model for the `depends_on` third pass

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` dataclass (line 32), `from_issues()` (lines 52–124), `get_execution_waves()` (lines 154–201)

### Dependent Files (Callers — verify no regressions, no changes needed)
- `scripts/little_loops/issue_manager.py:1003` — calls `DependencyGraph.from_issues()` during initialization
- `scripts/little_loops/sprint.py` — consumes execution waves for sprint ordering
- `scripts/little_loops/cli/sprint/run.py` — executes sprints using `get_execution_waves()`
- `scripts/little_loops/cli/sprint/show.py` — displays wave plan; `_render_dependency_graph()` reads `dep_graph.blocks` and `dep_graph.blocked_by` by name — safe with new field added via `field(default_factory=dict)`
- `scripts/little_loops/cli/sprint/manage.py` — imports and uses `DependencyGraph`
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan()` reads `dep_graph.blocked_by.get(...)` at two points; safe with new field, but wave display will not annotate `depends_on`-nudged placement
- `scripts/little_loops/cli/issues/sequence.py` — sequences issues by dependency order
- `scripts/little_loops/cli/issues/clusters.py` — visualizes dependency clusters
- `scripts/little_loops/dependency_mapper/analysis.py` — `validate_dependencies()` calls `DependencyGraph.from_issues()` for cycle detection only; no field access beyond `from_issues()` return value

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/manage.py` — confirmed importer of `DependencyGraph` [Agent 1 finding]
- `scripts/little_loops/cli/sprint/_helpers.py` — accesses `.blocked_by` and `.blocks` fields by name; adding `depends_on_edges` with `field(default_factory=dict)` is backward-compatible [Agent 1 + 2 finding]
- `scripts/little_loops/dependency_mapper/analysis.py` — imports `DependencyGraph` (line 13) for cycle detection; no field access risks [Agent 1 finding]

### Similar Patterns
- `dependency_graph.py:92–124` — blocked_by/blocks two-pass pattern: exact model for the `depends_on` third pass (same 4-guard structure: completed skip → all_issue_ids check → all_known_ids suppression → logger.warning())

### Tests
- `scripts/tests/test_dependency_graph.py` — primary test file (see Tests section)
- `scripts/tests/test_sprint_integration.py` — integration tests that exercise wave generation
- `scripts/tests/test_cli.py` — bare `DependencyGraph()` constructor at line 1020 in `TestRenderExecutionPlan.test_render_execution_plan_empty_waves()`; safe only if `depends_on_edges` uses `field(default_factory=dict)` — verify no breakage [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `DependencyGraph` attributes table lists only `issues`, `blocked_by`, `blocks`; needs `depends_on_edges` added; `get_execution_waves()` description says waves derive from blocker resolution only [Agent 2 finding]
- `docs/ARCHITECTURE.md` — wave table example and prose in "Dependency Graph" section describe only `blocked_by`-driven ordering [Agent 2 finding]
- `docs/guides/SPRINT_GUIDE.md` line 45 — "you configure dependencies via the `blocked_by` field" is now incomplete [Agent 2 finding]
- Note: doc updates are out of scope for ENH-1436 (see Scope Boundaries) — flag for a follow-up doc pass after implementation

### Warning String Coupling

_Wiring pass added by `/ll:wire-issue`:_
- `test_dependency_graph.py` lines 82–116 assert on `"blocked by unknown issue"` and `"blocks unknown issue"` substrings via `caplog.text`. The new `depends_on` third-pass warning must use a different substring (e.g., `"depends_on unknown issue"`) to avoid false matches [Agent 2 finding]

### Dependency Status
- ENH-1430 **confirmed complete**: `IssueInfo.depends_on: list[str] = field(default_factory=list)` is at `scripts/little_loops/issue_parser.py:251`; parsed from frontmatter at lines 494–547

## Tests

- `scripts/tests/test_dependency_graph.py:14` — extend `make_issue()` helper: add `depends_on: list[str] | None = None` kwarg, pass `depends_on=depends_on or []` to `IssueInfo` constructor
- `scripts/tests/test_dependency_graph.py:671` — also extend `_make_issue_with_content()` helper with `depends_on` kwarg (same pattern)
- Add `test_depends_on_soft_ordering()`: assert that an issue whose `depends_on` target is in wave 2 causes the target to move to wave 1 without hard-blocking the dependent
  - Use set-membership assertions: `assert "TARGET" in {i.issue_id for i in waves[0]}` (model: lines 596–603)
- `scripts/tests/test_dependency_graph.py:82` — caplog pattern for warning assertions: `assert "text" in caplog.text` (no `caplog.at_level()` context manager needed — WARNING is captured by default)

_Wiring pass added by `/ll:wire-issue` — additional test cases mirroring blocked_by pattern:_
- Add `test_depends_on_edges_populated()`: after `from_issues()`, assert `graph.depends_on_edges["A"] == {"B"}` for a simple A-depends-on-B case (mirrors `test_linear_chain()` at line 54)
- Add `test_depends_on_completed_target_skipped()`: `depends_on` pointing at a completed ID is not added as an edge (mirrors `test_completed_blocker_not_added()` at line 118)
- Add `test_depends_on_does_not_hard_block()`: confirm the dependent issue still enters a wave even when its `depends_on` target is absent or in the same wave (soft-ordering only, not blocking)
- Add `test_depends_on_unknown_target_warns()`: unknown `depends_on` ID emits `logger.warning()` with a substring distinct from `"blocked by unknown issue"` (e.g., `"depends_on unknown issue"`) — caplog pattern from line 82 [Agent 2 + 3 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Verify `scripts/little_loops/cli/sprint/_helpers.py` — confirm `_render_execution_plan()` reads `.blocked_by` by name and that adding `depends_on_edges: dict[str, set[str]] = field(default_factory=dict)` to `DependencyGraph` does not break the dataclass constructor call at `test_cli.py:1020`
4. Choose warning string for unknown `depends_on` target — use `f"Issue {issue.issue_id} has depends_on unknown issue {target_id}"` (must not contain `"blocked by unknown issue"` or `"blocks unknown issue"` to avoid false caplog matches in existing tests)
5. Extend `make_issue()` helper (line 14) and `_make_issue_with_content()` helper (line 671) with `depends_on` kwarg before writing new tests
6. Write all 4 new test cases: `test_depends_on_edges_populated`, `test_depends_on_completed_target_skipped`, `test_depends_on_does_not_hard_block`, `test_depends_on_unknown_target_warns`

## Acceptance Criteria

- `DependencyGraph.from_issues()` builds soft-ordering edges from `depends_on` without treating them as hard blocks
- `get_execution_waves()` respects `depends_on` for soft ordering (target in earlier wave, not required)
- Unknown `depends_on` targets emit `logger.warning()` (caplog-testable)
- `test_depends_on_soft_ordering()` passes
- All existing dependency graph tests still pass

## Scope Boundaries

- **In scope**: `dependency_graph.py` and `test_dependency_graph.py` only
- **Out of scope**: Validation, formatting, sync, CLI display (separate children)
- **Depends on**: ENH-1430 — `IssueInfo.depends_on` field must exist

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 66/100 → MODERATE

### Concerns
- Step 2 algorithm underspecified: "reorder to earliest possible wave" admits at least three incompatible mechanisms (post-processing pass, BFS modification, two-phase compute); implementer must invent and defend the approach.
- ENH-1430 not formally closed in the issue tracker; code dependency is confirmed present but the issue remains open.

### Outcome Risk Factors
- Ambiguity in soft-ordering algorithm: the acceptance criteria test observable output only, leaving edge cases (multi-hop depends_on chains, mixed hard/soft deps) unguarded against algorithm-specific bugs.
- Broad wave-consumer surface: 9 callers of `get_execution_waves()` will be affected by behavioral ordering changes; `test_sprint_integration.py` may surface regressions.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1439: Add `depends_on_edges` field to DependencyGraph and populate in `from_issues()`
- ENH-1440: Update `get_execution_waves()` for soft ordering via `depends_on_edges`

---

## Session Log
- `/ll:refine-issue` - 2026-05-11T01:02:11 - `0d6c6f30-c80d-4059-8f6a-f4842dd99486.jsonl`
- `/ll:issue-size-review` - 2026-05-10T23:55:00Z - `49b56280-19ff-42e9-bb93-088d6e560fa2.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00 - `current.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `3fced62d-7d83-4549-8102-e5e13cee49ad.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `23183115-4e9d-49d8-a987-c848c2818729.jsonl`
