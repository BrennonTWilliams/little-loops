---
id: BUG-2915
type: BUG
priority: P4
status: done
captured_at: '2026-07-29T15:59:35Z'
completed_at: '2026-07-29T15:59:35Z'
discovered_date: 2026-07-29
discovered_by: user-report
labels:
- issues
- dependency-graph
- cli
---

# BUG-2915: `ll-issues link` warns "unknown issue" for edges pointing at done/cancelled issues

## Summary

Running `ll-issues link` in a project with a mature issue graph (many
`done`/`cancelled` issues) prints a wall of `WARNING ... blocked by unknown
issue <ID>` / `has depends_on unknown issue <ID>` lines for every edge that
targets a completed or cancelled issue. The targets are real, existing
issues — just excluded from the non-terminal issue set the cycle-check
builds its graph from — so the warning is indistinguishable from a genuine
typo'd/nonexistent ID. Reported from a consuming project
(`sketch-storyboards`, local-editable against this checkout), but the defect
is in `little-loops` itself.

## Steps to Reproduce

1. In a project with issues in `done`/`cancelled` status that are targets of
   `blocked_by`/`depends_on`/`blocks` edges on other issues.
2. Run any `ll-issues link` invocation that triggers `_check_cycle`
   (e.g. `ll-issues link FEAT-X --depends-on FEAT-Y`).
3. Observe `little_loops.dependency_graph` warnings naming the done/cancelled
   IDs as "unknown", even though they exist on disk.

## Current Behavior

`_check_cycle()` in `scripts/little_loops/cli/issues/link.py` builds its
graph from `find_issues_for_graph()`, which excludes `done`/`cancelled`
issues by design, then calls `DependencyGraph.from_issues(issues)` with no
`all_known_ids`. Any edge whose target is absent from that non-terminal set
— including a target that is done/cancelled rather than nonexistent — logs
`Issue X blocked by unknown issue Y` (or the `blocks`/`depends_on`
equivalents) via `logger.warning`, indistinguishable from a genuinely
nonexistent/typo'd ID.

## Expected Behavior

An edge pointing at an issue that exists on disk under any status should
never warn as "unknown" — only edges pointing at IDs absent from the whole
issue set (a real typo or deleted issue) should warn. This is exactly what
`DependencyGraph.from_issues()`'s existing `all_known_ids` parameter
provides; `_check_cycle` just needs to supply it.

## Root Cause

`DependencyGraph.from_issues()` (`scripts/little_loops/dependency_graph.py`)
already supports an `all_known_ids` parameter — added for BUG-2897 — that
suppresses the "unknown issue" warning when the missing ID exists on disk
under any status. Every other caller in the codebase
(`issue_manager.py`, `next_issue.py`, `next_issues.py`, `sequence.py`,
`issue_parser.py`) passes it via the existing `gather_all_issue_ids()`
helper. `_check_cycle()` in
`scripts/little_loops/cli/issues/link.py` was the one caller that built its
graph from `find_issues_for_graph()` (which deliberately excludes terminal
statuses, BUG-2897) and then called `DependencyGraph.from_issues(issues)`
without `all_known_ids`, so every terminal-status target it encountered
logged a false-positive "unknown" warning.

## Resolution

`scripts/little_loops/cli/issues/link.py:211-227` (`_check_cycle`) now
computes `all_known_ids` via `gather_all_issue_ids(issues_dir, config=config)`
(status-agnostic, filename-based scan across all category dirs) and passes
it into `DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)`,
matching the pattern used everywhere else. Added a regression test,
`test_link_no_unknown_warning_for_done_blocker` in
`scripts/tests/test_link_cli.py`, which links two open issues while a third
`blocked_by` target is `status: done`, and asserts no "unknown issue"
warning is logged for it. Verified the test fails against the pre-fix code
(reproduces the exact warning text) and passes with the fix. Full suite
(`python -m pytest scripts/tests/`) passes.

## Impact

- **Correctness/UX**: eliminates false-positive warning noise on every
  `ll-issues link` call in any project with a non-trivial completed/cancelled
  issue history — the exact symptom reported from `sketch-storyboards`.
- **No behavior change** for genuinely unknown/typo'd IDs — those still warn
  as before, since `all_known_ids` only suppresses the case where the target
  exists on disk.
- **Scope**: single call site, no schema/format changes.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-29T16:00:07 - `a1ff567a-de88-4c40-8772-ef2fa14ed5a1.jsonl`

Investigated via a research agent tracing the warning to
`dependency_graph.py`'s `from_issues()` and confirming `link.py`'s
`_check_cycle` was the only caller missing `all_known_ids`; fix applied
directly plus a regression test, verified against pre-fix code.

---

## Status

`done`
