---
id: BUG-3029
priority: P3
type: BUG
parent: BUG-3027
status: open
discovered_date: 2026-08-03
discovered_by: issue-size-review
---

# Audit and fix unguarded `gather_all_issue_ids()` call sites that crash CLI commands on exception

## Summary

Decomposed from BUG-3027: the `/ll:wire-issue` pass on BUG-3027 found that 5
call sites build `all_known_ids` via `gather_all_issue_ids()` with **no
try/except at all** around the call, unlike the other three call sites
BUG-3027 discusses. An exception there is unhandled and crashes the CLI
command outright — a strictly worse failure mode than the "spurious
warning" symptom BUG-3027 was originally filed for, and severe enough to
warrant its own fix and priority rather than folding into that P4 cosmetic
issue.

## Parent Issue

Decomposed from BUG-3027: ll-sprint prints "depends_on unknown issue" for a
dependency that exists and is done.

## Current Behavior

Confirmed by direct read (not just grep) in BUG-3027's wiring pass — each of
the following calls `gather_all_issue_ids()` with no surrounding
try/except, so any exception it raises propagates unhandled and crashes the
command:

- `scripts/little_loops/cli/sprint/run.py:499-502`
- `scripts/little_loops/cli/sprint/show.py:183-187`
- `scripts/little_loops/cli/sprint/manage.py:92-96`
- `scripts/little_loops/cli/sprint/edit.py:105-114`
- `scripts/little_loops/cli/deps.py:385` (the nearby `try/except` at
  lines 379-384 guards only the `BRConfig` construction, not the
  `gather_all_issue_ids()` call itself)

By contrast, `cli/issues/link.py:223-228`, `cli/issues/sequence.py:74-81`,
`cli/issues/next_issue.py:67-74`, and `cli/issues/next_issues.py:57-64`
already wrap the call in `try/except Exception: pass`/`all_known_ids =
None` and are correctly unaffected by this crash risk.

## Expected Behavior

`ll-sprint run/show/manage/edit --revalidate` and the `cli/deps.py` command
should degrade gracefully (matching the fallback shape used elsewhere in
this call-site family — see BUG-3028) rather than crashing outright if
`gather_all_issue_ids()` raises.

## Steps to Reproduce

1. Patch/mock `little_loops.dependency_mapper.gather_all_issue_ids` to raise
   an exception.
2. Run any of `ll-sprint run`, `ll-sprint show`, `ll-sprint manage`,
   `ll-sprint edit --revalidate`, or the relevant `ll-deps` command.
3. Observe the command crashes with an unhandled traceback instead of
   degrading gracefully.

## Proposed Solution

1. Wrap each of the 5 unguarded `gather_all_issue_ids()` calls
   (`cli/sprint/run.py:499-502`, `cli/sprint/show.py:183-187`,
   `cli/sprint/manage.py:92-96`, `cli/sprint/edit.py:105-114`,
   `cli/deps.py:385`) in a `try/except Exception` matching the fallback
   convention chosen for BUG-3028 (or the existing `sprint.py:378`
   `active_ids_set` pattern, whichever is decided as the shared
   convention), so an exception here degrades instead of crashing.
2. Add a test per call site (or a parametrized test covering all 5) that
   forces `gather_all_issue_ids` to raise and asserts the CLI command no
   longer crashes.

## Files to Modify

- `scripts/little_loops/cli/sprint/run.py:499-502`
- `scripts/little_loops/cli/sprint/show.py:183-187`
- `scripts/little_loops/cli/sprint/manage.py:92-96`
- `scripts/little_loops/cli/sprint/edit.py:105-114`
- `scripts/little_loops/cli/deps.py:385`
- Corresponding test files (e.g. `scripts/tests/test_cli_sprint.py`,
  `scripts/tests/test_cli_deps.py` or equivalent)

## Impact

- **Priority**: P3 - An unhandled exception here crashes CLI commands
  outright, a more severe failure mode than BUG-3027's original log-noise
  symptom.
- **Effort**: Small-Medium - 5 symmetric try/except additions plus tests;
  mechanical once the shared fallback convention is decided (see BUG-3028).
- **Risk**: Low - additive defensive handling, no behavior change on the
  non-exception path.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-03 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-03T18:23:42 - `13ce9106-a2bc-4289-afb9-7b03c8d5dfa8.jsonl`
