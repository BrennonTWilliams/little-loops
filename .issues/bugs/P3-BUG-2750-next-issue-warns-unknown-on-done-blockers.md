---
id: BUG-2750
title: next-issue/next-issues log spurious "unknown issue" warnings for done/deferred/cancelled
  blockers
type: BUG
priority: P3
status: open
captured_at: '2026-07-23T21:34:34Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
relates_to:
- BUG-2728
- BUG-2733
labels:
- issues
- dependency-graph
confidence_score: 100
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 23
---

# BUG-2750: `next-issue`/`next-issues` log spurious "unknown issue" warnings for done/deferred/cancelled blockers

## Summary

`ll-issues next-issue` and `ll-issues next-issues` print `Issue X blocked by
unknown issue Y` / `has depends_on unknown issue Y` warnings for blockers that
are perfectly valid issues sitting at `status: done` (or `deferred`/
`cancelled`). The referenced files exist on disk with matching `id:`
frontmatter — the warning is a false positive, not a sign of a dangling
reference.

## Current Behavior

`DependencyGraph.from_issues()` (`dependency_graph.py:99-108,119-124,133-140`)
only suppresses the "unknown issue" warning when the referenced blocker ID is
in the `completed_ids` or `all_known_ids` sets — both of which are optional
kwargs the caller must supply. Three call sites never supply either:

- `cli/issues/next_issue.py:57` — `DependencyGraph.from_issues(find_issues(config))`
- `cli/issues/next_issues.py:48` — same pattern
- `issue_parser.py:1276` (inside `find_issues`'s own `skip_blocked=True` branch)
  — `DependencyGraph.from_issues(all_active)`

`find_issues(config)` with no flags returns only active issues (excludes
`done`/`deferred`/`cancelled`), so any `blocked_by`/`depends_on`/`blocks`
reference to a completed issue falls outside the graph's known-issue set and
triggers the warning — even though the blocker resolved fine (unknown
blockers are simply skipped, not added as edges, so this does **not**
functionally block anything; it's log noise only).

Contrast with the correct pattern in `issue_manager.py:1194-1204`, which
builds `all_known_ids` via `dependency_mapper.gather_all_issue_ids()` over the
whole `.issues` tree and passes it into `from_issues()`, silently skipping
completed blockers.

## Expected Behavior

`next-issue`/`next-issues` (and `find_issues`'s internal `skip_blocked` graph
build) should pass `all_known_ids` (or `completed_ids`) into
`DependencyGraph.from_issues()`, matching `issue_manager.py`'s pattern, so
blockers that are `done`/`deferred`/`cancelled` resolve silently instead of
logging a warning.

## Root Cause

`cli/issues/next_issue.py:57`, `cli/issues/next_issues.py:48`, and
`issue_parser.py:1276` construct `DependencyGraph` without the
`all_known_ids`/`completed_ids` kwargs that `DependencyGraph.from_issues()`
(`dependency_graph.py:56-145`) needs to distinguish "truly missing" blockers
from "exists on disk but filtered out of the active-issue list."

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `DependencyGraph.from_issues()` (`dependency_graph.py:56-145`) signature:
  `from_issues(cls, issues: list[IssueInfo], completed_ids: set[str] | None = None, all_known_ids: set[str] | None = None) -> DependencyGraph`.
  `completed_ids` fully resolves a blocker (skipped, no edge, no warning).
  `all_known_ids` only suppresses the *warning* for a blocker that's a real
  file on disk but excluded from the `issues` list passed in — that's the
  exact "done/deferred/cancelled" case this bug is about. Both are checked
  independently in each of the three passes (`blocked_by` lines 96-111,
  one-sided `blocks:` lines 117-127, `depends_on` lines 131-143), each with
  its own warning message format (`"blocked by unknown issue"`, `"blocks
  unknown issue"`, `"has depends_on unknown issue"`). Passing `all_known_ids`
  once at construction covers all three warning sites.
- `issue_parser.py:1276`'s `skip_blocked` branch already narrows the blast
  radius vs. the other two sites: `non_terminal = _ALL_STATUSES -
  _TERMINAL_STATUSES` where `_TERMINAL_STATUSES = frozenset({"done",
  "cancelled"})` (`issue_progress.py:12,14`) — `deferred` is *not* terminal,
  so `deferred` blockers are already included in this call site's
  `all_active` list and don't warn. Only `done`/`cancelled` blockers trigger
  the warning here. The other two call sites (`next_issue.py:57`,
  `next_issues.py:48`) call bare `find_issues(config)` with
  `status_filter=None`, which excludes all three terminal-ish statuses
  (`done`, `deferred`, `cancelled`) — full blast radius.
- Correct pattern (`issue_manager.py:1193-1204`): imports
  `gather_all_issue_ids` from `little_loops.dependency_mapper`, wraps the
  call in `try/except Exception` (falls back to `all_known_ids=None` —
  `from_issues()`'s pre-existing default, still warns on truly-missing IDs —
  and logs at `debug` on failure), then passes the result as
  `all_known_ids=` into `from_issues()`.
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]`
  (`dependency_mapper/operations.py:261-293`, re-exported from
  `dependency_mapper/__init__.py:65`) does a lightweight filename-only scan
  of `bugs/`, `features/`, `enhancements/`, `epics/` (or
  `config.issue_categories`), regex-matching `(BUG|FEAT|ENH|EPIC)-(\d+)`
  against each `*.md` filename — status-agnostic by design ("Done and
  deferred issues remain in type dirs with status frontmatter, so scanning
  only type dirs finds all known IDs").
- Three other call sites already follow the correct pattern and can serve as
  direct templates: `cli/sprint/manage.py:91-99`, `cli/sprint/show.py:182-190`
  (both import `gather_all_issue_ids` directly, no try/except), and
  `sprint.py:365-367` (reuses an already-computed `active_ids_set` instead of
  re-scanning). `dependency_mapper/analysis.py:481` shows `completed_ids` and
  `all_known_ids` used together: `DependencyGraph.from_issues(issues,
  completed, all_known_ids=all_known_ids)`.
- A fourth bare call site with the same convention gap exists but is outside
  this bug's stated scope: `cli/issues/sequence.py:34` —
  `DependencyGraph.from_issues(issues)`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issue.py:57` — wire `all_known_ids`
  into the bare `DependencyGraph.from_issues(find_issues(config))` call
  inside the `include_blocked` branch.
- `scripts/little_loops/cli/issues/next_issues.py:48` — same fix, identical
  call shape.
- `scripts/little_loops/issue_parser.py:1276` — inside `find_issues()`'s
  `skip_blocked=True` branch; narrower blast radius (only `done`/`cancelled`
  blockers warn here since `deferred` is already in `non_terminal`).

### Similar Patterns (reference implementations)
- `scripts/little_loops/issue_manager.py:1193-1204` — canonical pattern:
  `gather_all_issue_ids()` wrapped in `try/except Exception` → `debug`-log
  fallback to `all_known_ids=None` on failure.
- `scripts/little_loops/cli/sprint/manage.py:91-99` and
  `scripts/little_loops/cli/sprint/show.py:182-190` — direct (no
  try/except) wiring of the same `gather_all_issue_ids()` → `all_known_ids=`
  pattern.
- `scripts/little_loops/sprint.py:365-367` — reuses an already-computed
  `active_ids_set` instead of re-scanning disk.

### Reusable Utility
- `gather_all_issue_ids(issues_dir: Path, config: BRConfig | None = None) -> set[str]`
  — `scripts/little_loops/dependency_mapper/operations.py:261-293`,
  re-exported from `scripts/little_loops/dependency_mapper/__init__.py:65`.

### Tests
- `scripts/tests/test_dependency_graph.py` (`TestDependencyGraphConstruction`)
  — existing `caplog`-based unit tests for `from_issues()`'s
  `all_known_ids` warning-suppression behavior
  (`test_known_id_not_in_graph_no_warning`, `test_truly_unknown_id_still_warns`).
- `scripts/tests/test_next_issue.py` — has `_write_config`/`_make_issue`/
  `_setup_dirs` helpers and a closely-related existing test,
  `test_done_blocker_does_not_block`, which proves the `done` blocker is
  filtered but does **not** currently assert on the absent/present warning
  text — extend with `caplog` for a BUG-2750 regression test.
- `scripts/tests/test_next_issues.py` — sibling test file for
  `next-issues`, same extension needed.
- `scripts/tests/test_dependency_mapper.py::TestGatherAllIssueIds` — existing
  coverage for `gather_all_issue_ids()` itself (no change needed there).

## Steps to Reproduce

1. In a project with issue history, have issue A `blocked_by`/`depends_on` an
   issue B that is `status: done`.
2. Run `ll-issues next-issue` or `ll-issues next-issue --include-blocked`.
3. Observe `Issue A blocked by unknown issue B` on stderr, despite B existing
   on disk with a valid `done` status.

## Impact

- **Priority**: P3 - Cosmetic stderr noise, not a functional blocker (unknown
  blockers are skipped as edges, not treated as unresolved), but it's
  confusing output that looks like data corruption and erodes trust in the
  command.
- **Effort**: Small - reuse the existing `gather_all_issue_ids()` +
  `all_known_ids` wiring already proven in `issue_manager.py`.
- **Risk**: Low - additive kwarg wiring, no behavior change to graph edges.
- **Breaking Change**: No

## Implementation Steps

1. In `cli/issues/next_issue.py:57`, import `gather_all_issue_ids` from
   `little_loops.dependency_mapper`, build `all_known_ids` from
   `config.project_root / config.issues.base_dir` (mirroring
   `issue_manager.py:1193-1204`'s `try/except Exception` fallback to `None`),
   and pass it as `DependencyGraph.from_issues(find_issues(config),
   all_known_ids=all_known_ids)`.
2. Apply the identical fix to `cli/issues/next_issues.py:48`.
3. Apply the same fix to `issue_parser.py:1276` inside `find_issues()`'s
   `skip_blocked` branch — this only needs to suppress `done`/`cancelled`
   blockers since `deferred` is already covered by `non_terminal`.
4. Extend `test_next_issue.py::test_done_blocker_does_not_block` (or add a
   sibling test) with `caplog` assertions that no `"unknown issue"` warning
   is logged for a `done`/`deferred`/`cancelled` blocker; add the analogous
   test to `test_next_issues.py`.
5. Verify: `python -m pytest scripts/tests/test_next_issue.py
   scripts/tests/test_next_issues.py scripts/tests/test_dependency_graph.py -v`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`dependency-graph`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-07-23T21:40:52 - `942918e6-b4f1-42b1-be48-5fcea493fffd.jsonl`
- `/ll:confidence-check` - 2026-07-23T22:15:00 - `f0bf3f77-75c8-42f8-9e8e-95bc79a1f6f9.jsonl`
- `/ll:capture-issue` - 2026-07-23T21:34:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b69a734-b6b5-46c0-956e-d8f616b1aa18.jsonl`

---

## Status

**Open** | Created: 2026-07-23 | Priority: P3
