---
id: BUG-3028
priority: P4
type: BUG
parent: BUG-3027
status: open
discovered_date: 2026-08-03
discovered_by: issue-size-review
---

# Harden `all_known_ids` exception-fallback branches in `AutoManager.__init__` and `find_issues(skip_blocked=True)`

## Summary

Decomposed from BUG-3027: the originally-reported spurious "unknown issue"
warning was already fixed on the `sprint.py` path by commit `15152136`
(closing BUG-3024). The remaining, still-open scope from BUG-3027 is
hardening the two other `all_known_ids` construction sites that share the
same `gather_all_issue_ids()` try/except shape but currently degrade to
`all_known_ids = None` on exception (a stricter, untested failure mode)
instead of a `gather_all_issue_ids`-derived fallback like `sprint.py` now
uses.

## Parent Issue

Decomposed from BUG-3027: ll-sprint prints "depends_on unknown issue" for a
dependency that exists and is done.

## Current Behavior

- `scripts/little_loops/issue_manager.py:1509-1521` (`AutoManager.__init__`):
  `except Exception: self.logger.debug(...)` leaves `all_known_ids = None`.
- `scripts/little_loops/issue_parser.py:2118-2126` (`find_issues()`'s
  `skip_blocked` branch): `except Exception: pass` leaves
  `all_known_ids = None`, with no logging at all.
- Per `dependency_graph.py`'s guard (`if all_known_ids is None or <id> not in
  all_known_ids: warn`), `None` triggers warnings on *every* referenced ID
  outside the graph — reachable only if `gather_all_issue_ids()` itself
  raises, not on the normal path. Neither branch is exercised by any
  existing test.
- Three coexisting conventions for the fallback body already disagree:
  `sprint.py:378` (`all_known_ids = active_ids_set`, marked
  `# pragma: no cover - defensive, mirrors issue_parser`),
  `issue_manager.py:1520-1521` (`None` + `logger.debug`), `issue_parser.py`
  (`None` + bare `pass`). No existing precedent picks one over the others
  for this exception specifically.

## Expected Behavior

Both remaining sites degrade consistently with the already-fixed
`sprint.py` site: on `gather_all_issue_ids()` exception, fall back to a
`gather_all_issue_ids`-derived set (or, if that's not feasible, at minimum
log the swallowed exception rather than silently leaving `all_known_ids =
None`) — and cover the exception path with a regression test at each site,
since none currently exists anywhere in this call-site family.

## Proposed Solution

1. `issue_manager.py:1509-1521` (`AutoManager.__init__`): change the
   except-branch's fallback shape to match `sprint.py`'s post-fix pattern
   (derive `all_known_ids` from the already-active-ids set, or another
   `gather_all_issue_ids`-shaped fallback), keeping the existing
   `logger.debug` call or upgrading it per whatever convention is chosen.
2. `issue_parser.py:2118-2126` (`find_issues()`'s `skip_blocked` branch):
   same fallback-shape fix; add at least a `logger.debug` call since none
   exists today.
3. Add a test forcing the exception path for `AutoManager.__init__`,
   modeled on `test_dependency_graph_built_on_init`
   (`scripts/tests/test_issue_manager.py:613-626`) and its fixture
   `temp_project_with_deps` (`:568-611`); patch
   `little_loops.dependency_mapper.gather_all_issue_ids` to raise, construct
   `AutoManager`, and assert it doesn't crash and produces the expected
   `all_known_ids`/warning behavior.
4. Add a test forcing the exception path for `find_issues(skip_blocked=True)`,
   modeled on `test_find_issues_skip_blocked_terminal_blocker_unblocks` /
   `test_find_issues_skip_blocked_deferred_blocker_still_blocks`
   (`scripts/tests/test_issue_parser.py:1352-1394`), same patch approach.

## Files to Modify

- `scripts/little_loops/issue_manager.py:1509-1521`
- `scripts/little_loops/issue_parser.py:2118-2126`
- `scripts/tests/test_issue_manager.py` (new exception-path test)
- `scripts/tests/test_issue_parser.py` (new exception-path test)

## Impact

- **Priority**: P4 - Consistency/hardening fix; no user-visible crash today,
  only a stricter (but unexercised) warning-suppression degrade path.
- **Effort**: Small - two symmetric fallback-shape edits plus two new
  mock-based exception-path tests, modeled directly on existing test
  patterns.
- **Risk**: Low - narrow, well-isolated code paths with clear precedent to
  follow from the already-fixed `sprint.py` site.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Session Log
- `/ll:issue-size-review` - 2026-08-03T18:23:42 - `13ce9106-a2bc-4289-afb9-7b03c8d5dfa8.jsonl`
