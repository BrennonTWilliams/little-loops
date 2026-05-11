---
id: ENH-1439
type: ENH
priority: P2
parent: ENH-1436
depends_on:
- ENH-1430
status: open
---

# ENH-1439: Add `depends_on_edges` field to DependencyGraph and populate in `from_issues()`

## Summary

Add `depends_on_edges: dict[str, set[str]] = field(default_factory=dict)` to the `DependencyGraph` dataclass and implement the third-pass population loop in `from_issues()`. This is Step 1 of ENH-1436: purely additive — no behavioral change to wave generation. Includes test helper extensions and field-level tests.

## Parent Issue

Decomposed from ENH-1436: DependencyGraph soft-ordering via `depends_on`

## Scope

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

## Files to Modify

- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` dataclass (line 32), `from_issues()` (lines 52–124)
- `scripts/tests/test_dependency_graph.py` — helper extensions + 3 new test cases

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

## Session Log
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
