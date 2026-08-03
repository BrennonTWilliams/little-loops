---
id: BUG-3027
status: open
captured_at: "2026-08-03T17:14:59Z"
discovered_date: 2026-08-03
discovered_by: capture-issue
testable: false
---

# ll-sprint prints "depends_on unknown issue" for a dependency that exists and is done

## Summary

At the very start of `ll-sprint run epic-3008`, before wave scheduling, the
runner printed `Issue ENH-3015 has depends_on unknown issue BUG-3009` — but
BUG-3009 existed on disk and was later confirmed `done` (its completion
correctly resolved the `depends_on: [BUG-3009]` blocker for ENH-3015 during
wave 6's `ready-issue` pass). The warning is spurious: the dependency wasn't
actually unknown, just excluded from the lookup set used at scan time.

The warning is emitted by `DependencyGraph.from_issues()` in
`scripts/little_loops/dependency_graph.py` (classmethod starting line 56),
at line 145 (analogous `blocked_by`/`blocks` warnings at lines 113 and 130).

## Current Behavior

Before `from_issues()` runs, callers build the `all_known_ids` set via
`gather_all_issue_ids()` in
`scripts/little_loops/dependency_mapper/operations.py:365-394`, which scans
`issues_dir/{bugs,features,enhancements,epics}` with a **non-recursive**
`d.glob("*.md")` (line 390) and extracts IDs via
`r"(BUG|FEAT|ENH|EPIC)-(\d+)"` (line 391). The three call sites —
`issue_manager.py:1471` (IssueManager `__init__`, the sprint-run path),
`sprint.py:381` (EPIC resolution), and `issue_parser.py:2126` — each wrap
the `gather_all_issue_ids()` call in a bare `try/except Exception` that
silently falls back to `all_known_ids = active_ids_set` (i.e., only
currently-active/open issues) if the call raises for any reason.

If `gather_all_issue_ids()` raised silently and the fallback engaged,
`all_known_ids` would be `active_ids_set` only — which excludes BUG-3009 if
it was already `done` (not "active") by the time the sprint kicked off,
producing exactly the observed "unknown issue" false positive for a
dependency that is real but already resolved.

## Expected Behavior

The dependency-known-ness check used for `depends_on`/`blocked_by`/`blocks`
validation should include done/cancelled issues, not just active ones — a
`depends_on` pointing at a `done` issue is a *satisfied* dependency, not an
unknown one, and should never trigger the "unknown issue" warning. If
`gather_all_issue_ids()` throws in the normal case (not just as a defensive
fallback), that exception should surface (or at least be logged), not be
silently swallowed and replaced with a much narrower active-only set.

## Motivation

This warning is currently harmless noise (the dependency resolved correctly
moments later), but it undermines trust in the dependency-scan output at
sprint kickoff — a real "unknown issue" (e.g. a typo'd ID with no matching
file at all) would look identical to this false positive, so operators
can't currently tell them apart from the log line alone.

## Steps to Reproduce

1. Have an issue `X` with `depends_on: [Y]` where `Y` is `status: done`.
2. Run `ll-sprint run <epic>` including issue `X`.
3. Observe `Issue X has depends_on unknown issue Y` printed at kickoff, even
   though `Y` exists and is done.

## Root Cause

- **File**: `scripts/little_loops/dependency_mapper/operations.py`
- **Anchor**: `in gather_all_issue_ids()`, lines 365-394 (non-recursive glob,
  line 390)
- **Cause**: Not yet confirmed between two candidate causes — needs a repro
  with instrumentation to distinguish them:
  1. The bare `try/except Exception` at each of the three call sites
     (`issue_manager.py:1471`, `sprint.py:381`, `issue_parser.py:2126`)
     silently swallowed a real exception from `gather_all_issue_ids()` and
     fell back to `active_ids_set`, which excludes BUG-3009 once it's
     `done`.
  2. Or `gather_all_issue_ids()`'s non-recursive `d.glob("*.md")` (line 390)
     missed BUG-3009's file because it lives in a nested subdirectory of
     `bugs/` that a non-recursive glob doesn't visit.
  Given the warning specifically says "unknown" for an issue that resolved
  correctly moments later once evaluated as `done`, (1) is the more likely
  explanation — the silent except-fallback directly explains why a
  known-but-done issue would drop out of the lookup set.

## Proposed Solution

TBD - requires investigation to confirm which of the two Root Cause
candidates applies, then:
1. If (1): either don't swallow the exception silently (log it at minimum),
   or scope the fallback's `all_known_ids` to include done/cancelled issues
   too, not just `active_ids_set`.
2. If (2): make `gather_all_issue_ids()`'s glob recursive, or confirm issue
   files are guaranteed to live directly under their type directory (no
   nesting) and this candidate is ruled out.

## Impact

- **Priority**: P4 - Cosmetic/log-noise only in this occurrence; the actual
  dependency resolution worked correctly. Worth fixing so real "unknown
  issue" warnings (e.g. genuine typos) aren't drowned out by false
  positives from this same code path.
- **Effort**: Small - likely a scoping fix to `all_known_ids` construction
  or a `glob` -> `rglob` change, pending confirmation of the actual cause.
- **Risk**: Low - narrow, well-isolated code path.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-03 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-03T17:16:22 - `4ad49473-6f8b-44cc-afa6-91e971b86c04.jsonl`
