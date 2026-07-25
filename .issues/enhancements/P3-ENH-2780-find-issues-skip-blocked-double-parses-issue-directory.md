---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T06:58:31Z'
relates_to:
- ENH-2781
parent: EPIC-2792
confidence_score: 100
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
status: done
---

# ENH-2780: `find_issues(skip_blocked=True)` re-parses the entire issue directory to build the dependency graph

## Summary

Every `find_issues(..., skip_blocked=True)` call parses all matching issue
files once, then — inside the `skip_blocked` branch — calls
`find_issues(config, status_filter=set(non_terminal))` again, a second
complete `IssueParser.parse_file()` pass (frontmatter, session-log, and
regex section extraction per file) over essentially all non-terminal issues,
solely to build the `DependencyGraph`.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 1259-1304 (`find_issues()` def at 1216; first pass loop 1259-1283; `skip_blocked` branch 1285-1304, second-pass call at 1292-1293) — line numbers drift from scan commit fb567390 but the shape is unchanged.
- **Anchor**: `in function find_issues(), skip_blocked branch`
- **Code**:
```python
for cat in categories:
    issue_dir = config.get_issue_dir(cat)
    ...
    for issue_file in issue_dir.glob("*.md"):
        info = parser.parse_file(issue_file)   # 1st full parse pass
        ...
if skip_blocked:
    ...
    all_active = find_issues(config, status_filter=set(non_terminal))  # 2nd full parse pass
```

## Current Behavior

Two full parse passes over the issue tree per call. With ~2,600 issue files
in this repo, every readiness-filtered listing pays the directory walk and
markdown parse twice.

## Expected Behavior

One parse pass: the dependency graph and readiness filter are computed from
a single shared parsed issue set.

## Proposed Solution

Have the `skip_blocked` branch build `all_active` by filtering the
already-parsed `issues` list, plus one targeted parse only for
categories/files not already covered; or extract a lower-level
`_find_issues_raw()` helper both steps share.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Why the first-pass `issues` list can't be reused as-is**: the second-pass
  call `find_issues(config, status_filter=set(non_terminal))` (line
  1292-1293) forwards none of the outer call's `category`, `skip_ids`,
  `only_ids`, or `type_prefixes` args, so it always walks *all*
  `config.issue_categories` (line 1257's `else` branch) — even when the
  outer call narrowed to one `category`. The existing comment above it
  explains this is deliberate: a blocker outside the requested slice must
  still resolve correctly. So the first-pass `issues` list is a strict
  subset of what the graph needs whenever `category`/`type_prefixes`/
  `skip_ids`/`only_ids` narrowed it, and can't be substituted directly.
- **What `DependencyGraph.from_issues()` actually needs**: only
  `issue.issue_id`, `issue.blocked_by`, `issue.blocks`, `issue.depends_on`
  (`dependency_graph.py:from_issues`, lines ~97/118/132) and
  `issue.priority_int` for the final sort in `get_ready_issues()` (line
  180). It does not touch title, content, frontmatter, product_impact, or
  any other `IssueInfo` field — so nothing about the graph-building step
  requires a *second, independently filtered* `parse_file()` pass; it just
  requires a **full unfiltered non-terminal parse**, once.
- **Concrete fix**: when `skip_blocked=True`, invert the order — do the full
  unfiltered non-terminal `parse_file()` pass *first* (this is the superset
  the graph needs regardless of the outer call's filters), then derive the
  outer call's `issues` result by applying `category`/`type_prefixes`/
  `skip_ids`/`only_ids`/status filters to that same superset in memory,
  instead of re-walking the directory a second time with a fresh `parser`.
  This collapses two `IssueParser.parse_file()` passes into one for every
  `skip_blocked=True` call, and is functionally equivalent to extracting
  `_find_issues_raw(config, status_filter) -> list[IssueInfo]` (unfiltered
  parse only) and having both the outer filtering and the `all_active`
  graph input call it exactly once.
- **`gather_all_issue_ids()` is a separate, cheap concern**: it's a
  filename-only regex scan (`dependency_mapper/operations.py:261`, no
  `parse_file()` call), already wrapped in `try/except Exception: pass`
  (lines 1295-1301) — it adds a third directory `glob()` walk but not a
  third `parse_file()` pass, and is out of scope for this fix.
- **Established single-parse-then-graph shape to follow**: this codebase
  already has the correct pattern in several other call sites that build a
  `DependencyGraph` from an already-parsed list rather than re-calling
  `find_issues()` — `issue_manager.py:1210-1219` (`AutoManager.__init__`),
  `sprint.py:367`, `cli/sprint/run.py:490`, `cli/sprint/manage.py:99`,
  `cli/sprint/show.py:190`, `cli/issues/sequence.py:34`, and
  `dependency_mapper/analysis.py:481`. The fix here brings `find_issues()`'s
  own internals in line with that convention.
- **Sibling redundancy at the caller level (ENH-2781)**: `cli/issues/next_issue.py`
  (`cmd_next_issue()`, lines 47-65) and `cli/issues/next_issues.py`
  (`cmd_next_issues()`) each call `find_issues(config)` a *second* time
  after already calling it once, purely to rebuild a `DependencyGraph` —
  the exact shape this issue fixes internally. ENH-2781 is `blocked_by:
  [ENH-2780]` and fixes this caller-level duplication once this lands.
- **No existing cache/memoization** exists for `parse_file()` or
  `find_issues()` results in `issue_parser.py` — the fix here is a
  single-call-shape change, not a caching layer.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `find_issues()` (def at line
  1216; first-pass loop 1259-1283; `skip_blocked` branch 1285-1304) — the
  actual fix.

### Dependent Files (Callers of `find_issues(..., skip_blocked=True)`)
- `scripts/little_loops/cli/issues/next_issue.py:82` — `cmd_next_issue()`
  passes `skip_blocked=True`.
- `scripts/little_loops/cli/issues/next_issues.py:74` — `cmd_next_issues()`
  passes `skip_blocked=True`.
- Broader `find_issues()` caller surface (unaffected by signature, but
  exercised by the byte-identical regression test below):
  `issue_manager.py:1210`, `sprint.py`, `cli/sprint/run.py`,
  `cli/sprint/manage.py`, `cli/sprint/show.py`, `cli/deps.py`,
  `parallel/priority_queue.py:244`, `parallel/orchestrator.py:473,1357`.

### Similar Patterns
- `scripts/little_loops/issue_manager.py:1210-1219`
  (`AutoManager.__init__`) — parses once via `find_issues()`, builds
  `DependencyGraph.from_issues()` from that same list. Model for the fix.

### Tests
- `scripts/tests/test_issue_parser.py:1267-1358` — existing `skip_blocked`
  behavior tests (`test_find_issues_skip_blocked_default_is_byte_identical`,
  `test_find_issues_skip_blocked_true_excludes_blocked`,
  `test_find_issues_skip_blocked_terminal_blocker_unblocks`,
  `test_find_issues_skip_blocked_deferred_blocker_still_blocks`) — must
  keep passing unchanged (behavior must stay byte-identical, only the parse
  count changes).
- `scripts/tests/test_issue_parser.py:1359-1487` —
  `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes`
  — enumerates 13 real external callsite `kwargs` shapes; template for a
  new regression test proving the single-pass refactor is output-identical.
- `scripts/tests/test_issue_parser.py:1227-1265` —
  `test_find_issues_skip_check_no_dir_globs` — uses
  `patch.object(Path, "glob", autospec=True, side_effect=...)` to count
  directory walks; the same technique
  (`patch.object(IssueParser, "parse_file", autospec=True, side_effect=...)`)
  is the template for a new test asserting exactly one `parse_file()` call
  per file when `skip_blocked=True`. **No `parse_file`-call-count-assertion
  test exists anywhere in the suite today** — this must be authored fresh
  following the `Path.glob`-patching shape above, applied to
  `IssueParser.parse_file` instead.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_next_issue.py:592,928` — `skip_blocked=True`
  readiness-ordering and all-blocked-returns-`[]` behavioral assertions
  (via the `next_issue` module); must keep passing unchanged post-refactor
  [Agent 3 finding].
- `scripts/tests/test_next_issues.py:640` — parallel
  all-blocked-returns-`[]` assertion for the plural variant; must keep
  passing unchanged [Agent 3 finding].
- `scripts/tests/test_issue_workflow_integration.py:139,158` — end-to-end
  `find_issues(config)` / `find_issues(config, category="bugs")` calls
  against a real fixture project dir; correctness (not parse-count)
  regression coverage, must keep passing unchanged [Agent 3 finding].
- `scripts/tests/test_dependency_graph.py` (`TestDependencyGraphConstruction`,
  line 42+) — confirmed **not at risk**: exercises `DependencyGraph.from_issues()`
  directly via hand-built `IssueInfo` fixtures, never calls `find_issues()`
  [Agent 3 finding, informational only].

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add a dated version-section entry for this fix per repo
  convention (no `[Unreleased]` section) [Agent 2 finding].

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Author a new `parse_file`-call-count assertion test in
   `scripts/tests/test_issue_parser.py`, following the `Path.glob`-patching
   shape of `test_find_issues_skip_check_no_dir_globs` (lines 1227-1265) but
   patching `IssueParser.parse_file` with `autospec=True` — assert exactly
   one call per file when `skip_blocked=True`.
2. Re-run `scripts/tests/test_next_issue.py`, `test_next_issues.py`, and
   `test_issue_workflow_integration.py` to confirm the refactor is
   byte-identical for their `skip_blocked=True` / `find_issues()` assertions
   (no edits expected, verification only).
3. Add a `CHANGELOG.md` entry under a concrete dated version section
   describing the parse-count fix.

## Impact

- **Effort**: Medium
- Halves issue-directory I/O and parsing for every `skip_blocked` caller
  (`ll-issues next-issue(s)`, autodev dequeue paths, sprint planning).

## Resolution

Collapsed `find_issues(skip_blocked=True)` from two `IssueParser.parse_file()`
passes to one. The `skip_blocked` branch now does a single unfiltered
non-terminal parse pass across every category (the superset
`DependencyGraph.from_issues()` needs), then derives both the outer call's
filtered `issues` result and the graph's `all_active` input from that same
in-memory superset — instead of the outer loop parsing once and the
`skip_blocked` branch recursively calling `find_issues()` a second time to
rebuild the same information. `skip_blocked=False` (the default, unaffected
path) keeps its original single-pass loop unchanged.

Added a `parse_file`-call-count regression test
(`test_find_issues_skip_blocked_single_parse_pass`) asserting exactly one
`parse_file()` call per file when `skip_blocked=True`, following the
`Path.glob`-patching shape of `test_find_issues_skip_check_no_dir_globs`.
All existing `skip_blocked` behavior tests, `test_next_issue.py`,
`test_next_issues.py`, `test_issue_workflow_integration.py`, and
`test_dependency_graph.py` pass unchanged.

## Status

`done`

## Session Log
- `/ll:manage-issue` - 2026-07-25T06:57:48 - `ac54797e-e274-4db7-8df2-bea0f5112d6d.jsonl`
- `/ll:ready-issue` - 2026-07-25T06:52:57 - `005040e9-0f3c-4da7-a486-8bc53cb1412f.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `e4c43467-940d-4528-8291-802d09e9c7be.jsonl`
- `/ll:wire-issue` - 2026-07-25T06:50:47 - `773d1f11-a9b8-4d48-81ea-4a8211d3495d.jsonl`
- `/ll:refine-issue` - 2026-07-25T06:43:50 - `b9c68175-9b18-4b38-b165-578351487931.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
