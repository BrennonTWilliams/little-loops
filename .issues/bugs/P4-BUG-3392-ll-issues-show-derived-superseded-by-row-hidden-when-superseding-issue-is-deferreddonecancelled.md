---
id: BUG-3392
type: BUG
title: 'll-issues show: derived ''Superseded by'' row hidden when superseding issue
  is deferred/done/cancelled'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-05'
captured_at: '2026-09-05T23:53:50Z'
---

# BUG-3392: ll-issues show: derived 'Superseded by' row hidden when superseding issue is deferred/done/cancelled

## Summary

`ll-issues show` computes the derived `Superseded by` row from an issue list that already excludes `deferred`/`done`/`cancelled` issues, so a superseding issue in any of those statuses is invisible to the lookup and the row never renders.

## Current Behavior

`ll-issues show <cancelled-issue>` omits the derived `Superseded by` row when the superseding issue is `deferred` (or `done`/`cancelled`). `scripts/little_loops/cli/issues/show.py` (~line 281) calls `find_issues(config)` with the default status filter, which hides done/cancelled/deferred issues, so `superseded_by(issue_id, _all)` never sees the superseding issue's `supersedes` list.

Repro: FEAT-3388 (`status: deferred`, `supersedes: [FEAT-3385]`) → `ll-issues show FEAT-3385` shows `Cancellation reason: superseded` but no `Superseded by: FEAT-3388` row.

## Steps to Reproduce

1. Create issue A with `status: cancelled`.
2. Create issue B with `status: deferred` (or `done`/`cancelled`) and `supersedes: [A]` in its frontmatter.
3. Run `ll-issues show A`.
4. Observe: output shows `Cancellation reason: superseded` but no `Superseded by: B` row, even though B's `supersedes` list names A.

## Expected Behavior

The reverse `Superseded by` edge renders regardless of the superseding issue's status. Supersession is a permanent record; the replacement being deferred or already done should not hide it.

## Proposed Solution

In `show.py`, load the issue list for the supersession/parent lookup with an all-statuses filter (e.g. `find_issues(config, status_filter={"open","in_progress","blocked","deferred","done","cancelled"})`) instead of the default. Add a test in the `ll-issues show` test module: cancelled issue A, deferred issue B with `supersedes: [A]`, assert `Superseded by: B` appears in `show A` output.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-06 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/issues/show.py:281` — widen the `find_issues(config)` call to pass an all-statuses `status_filter` for the supersession/parent lookup

### Dependent Files (Callers/Importers)
- `scripts/tests/test_show.py:9` — imports from `little_loops.cli.issues.show`

### Conventions in Force
- Two live conventions coexist for sourcing an "all statuses" filter set: import `_ALL_STATUSES` from `little_loops.issue_progress` via a local, function-scoped import (evidence: `cli/issues/normalize.py:263`, `cli/issues/format_check.py:516`, `sprint.py:354-360`, `issue_manager.py:1910-1913`, each wrapping it as `set(_ALL_STATUSES)`) vs. retyping a fresh six-status literal inline at the call site (evidence: `cli/deps.py:280-281`, `cli/issues/list_cmd.py:65-73` and `:186-196`). Both are established elsewhere in the codebase — this is a genuine open choice for the implementer, not a coin-flip.
- `find_issues_for_graph()` (`scripts/little_loops/issue_parser.py:4182-4201`) is the named precedent for "load a superset instead of relying on the default filter", but its superset (`_ALL_STATUSES - _TERMINAL_STATUSES`) still excludes `done`/`cancelled` — it does not fit this bug's need, which requires all six statuses (including `done`/`cancelled`) visible to `superseded_by()`.
- Prior fixes in this family both resolved a `find_issues()` default-filter blind spot by widening the *specific call site's* `status_filter`, never by changing `find_issues()`'s own default: `.issues/bugs/P2-BUG-2897-deferred-blocker-treated-as-satisfied-in-dependency-graph.md` (done) explicitly rejected widening the default itself, because it would leak `deferred` into 10+ work-selection surfaces; `.issues/bugs/P4-BUG-2915-ll-issues-link-warns-unknown-issue-for-done-cancelled-targets.md` (done) fixed a related terminal-status blind spot the same way. This issue's proposed fix (scope the widening to the `show.py:281` call site only) matches that precedent.

### Tests
- `scripts/tests/test_show.py:521` `test_superseded_by_derived_from_reverse_edge` and `:535` `test_superseded_by_absent_when_nobody_references` — existing coverage of the derived `superseded_by` field, both asserting on `_parse_card_fields()` directly rather than `cmd_show()` end-to-end. Neither currently exercises a terminal-status (`done`/`cancelled`/`deferred`) superseding issue.
- `scripts/tests/test_issue_parser.py:2453` `test_superseding_issue_done_still_found_when_scan_unfiltered` — existing test whose docstring already names "caller's responsibility to pass an unfiltered scan" as the exact risk this bug reports.
- `scripts/tests/test_issue_parser.py:1273` `test_find_issues_status_filter_none_preserves_default` — documents the default-exclusion behavior (`status_filter=None` drops `done`/`cancelled`/`deferred`) that this bug's fix must widen past, for this call site only.
- `scripts/tests/test_issue_parser.py` (class spanning ~1512-1661) `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes` maintains a `callsite_shapes` registry enumerating every known `find_issues()` caller's exact kwarg shape (e.g. `cli/deps:269`, `epic_progress:53`, `list_cmd:166`) — `show.py:281` is not yet an entry in that registry.

### Documentation
- `.claude/CLAUDE.md:189` (§ Issue File Format → Supersession) already documents the standing contract this bug violates: "`ll-issues show` derives the reverse `Superseded by` row... Never hand-write `superseded_by`."
- `.issues/enhancements/P3-ENH-2829-derive-superseded-by-reverse-edge-from-supersedes.md:118-147` — the origin issue that introduced this feature; its own "Open design questions / Silent degradation" section explicitly predicted this exact bug (superseding issue later closed → row silently vanishes) and left it as an accepted limitation at the time.

## Program Design

### Signatures

- `find_issues(config: BRConfig, category: str | None = None, skip_ids: set[str] | None = None, only_ids: list[str] | set[str] | None = None, type_prefixes: set[str] | None = None, status_filter: set[str] | None = None, *, skip_blocked: bool = False) -> list[IssueInfo]` (`scripts/little_loops/issue_parser.py:4056`) — already supports an explicit `status_filter`; the bug is the call site never passes one.
- `superseded_by(issue_id: str, all_issues: Iterable[IssueInfo]) -> list[str]` (`scripts/little_loops/issue_parser.py:4204`) — unchanged; only needs an `all_issues` argument that isn't pre-filtered.

### Call Path

`show.py` (`~line 281`, inside the parent/supersession resolution block) -> `find_issues(config, status_filter={"open", "in_progress", "blocked", "deferred", "done", "cancelled"})` -> `superseded_by(issue_id, _all)`

## Impact

- **Priority**: P4 - Cosmetic display gap; the underlying supersession data is intact and derivable via `ll-issues show` on the superseding issue itself, so this only affects a single CLI convenience row.
- **Effort**: Small - One-line change to the `find_issues(config)` call's `status_filter` argument, plus one regression test.
- **Risk**: Low - Widening the status filter for this specific lookup only affects the parent-title and superseded-by resolution block; it does not change which issues `ll-issues show` lists or operates on elsewhere.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `ll-issues show` renders `Superseded by` when the superseding issue is deferred, done, or cancelled
- [ ] Regression test covering the deferred-superseder case
- [ ] `python -m pytest scripts/tests/` passes

## Status

**Open** | Created: 2026-09-05 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-09-06T00:38:20 - `d41a820b-4488-495c-b1ba-f59ae30351ff.jsonl`
- `/ll:format-issue` - 2026-09-06T00:18:01 - `1e264319-0c50-4b45-8bb6-a6a83e8511b2.jsonl`
