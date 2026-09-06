---
id: BUG-3392
type: BUG
title: 'll-issues show: derived ''Superseded by'' row hidden when superseding issue
  is deferred/done/cancelled'
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-05'
captured_at: '2026-09-05T23:53:50Z'
completed_at: '2026-09-06T01:38:09Z'
confidence_score: 100
outcome_confidence: 96
score_complexity: 25
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 25
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

In `show.py`, load the issue list for the supersession/parent lookup with an all-statuses filter instead of the default. **Decided:** source the set from `little_loops.issue_progress._ALL_STATUSES` via a function-scoped import (inside the existing `try:` block alongside the `find_issues`/`superseded_by` import) and pass it wrapped as `set(_ALL_STATUSES)` — `find_issues()` is typed `status_filter: set[str] | None` and `_ALL_STATUSES` is a `frozenset`, so the bare form fails mypy. This matches `normalize.py:275`, `format_check.py:556`, `sprint.py:360`, and `issue_manager.py:1913`; do not retype the six-status literal inline.

Add a regression test in `scripts/tests/test_show.py`:
cancelled issue A, deferred issue B whose frontmatter forward-references A, assert `_parse_card_fields(A)["superseded_by"] == "B"`.

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/cli/issues/show.py:281` — widen the `find_issues(config)` call to pass an all-statuses `status_filter` for the supersession/parent lookup

### Dependent Files (Callers/Importers)
- `scripts/tests/test_show.py:9` — imports from `little_loops.cli.issues.show`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py:134` — `_tool_issue_get` imports and calls `_parse_card_fields()` directly (not via CLI subprocess); will surface the corrected `superseded_by` value to MCP clients once this bug is fixed
- `scripts/little_loops/mcp_server/resources.py:264` — `_read_issue_body` imports and calls `_parse_card_fields()` directly, JSON-serializing the result (including `superseded_by`) as an MCP resource body

### Conventions in Force
- Two live conventions coexist for sourcing an "all statuses" filter set: import `_ALL_STATUSES` from `little_loops.issue_progress` via a local, function-scoped import (evidence: `cli/issues/normalize.py:263`, `cli/issues/format_check.py:516`, `sprint.py:354-360`, `issue_manager.py:1910-1913`, each wrapping it as `set(_ALL_STATUSES)`) vs. retyping a fresh six-status literal inline at the call site (evidence: `cli/deps.py:280-281`, `cli/issues/list_cmd.py:65-73` and `:186-196`). **Resolved (2026-09-06 review): use the `set(_ALL_STATUSES)` import form** — see Proposed Solution. The `set()` wrap is required for mypy (`frozenset[str]` is not `set[str]`).
- `find_issues()` parses every issue file and only then applies `_matches_status` (`issue_parser.py:4056`, inner closure), so widening `status_filter` to all six statuses adds zero I/O — it changes only which parsed `IssueInfo`s are kept. No caching or perf work is warranted.
- `find_issues_for_graph()` (`scripts/little_loops/issue_parser.py:4182-4201`) is the named precedent for "load a superset instead of relying on the default filter", but its superset (`_ALL_STATUSES - _TERMINAL_STATUSES`) still excludes `done`/`cancelled` — it does not fit this bug's need, which requires all six statuses (including `done`/`cancelled`) visible to `superseded_by()`.
- Prior fixes in this family both resolved a `find_issues()` default-filter blind spot by widening the *specific call site's* `status_filter`, never by changing `find_issues()`'s own default: `.issues/bugs/P2-BUG-2897-deferred-blocker-treated-as-satisfied-in-dependency-graph.md` (done) explicitly rejected widening the default itself, because it would leak `deferred` into 10+ work-selection surfaces; `.issues/bugs/P4-BUG-2915-ll-issues-link-warns-unknown-issue-for-done-cancelled-targets.md` (done) fixed a related terminal-status blind spot the same way. This issue's proposed fix (scope the widening to the `show.py:281` call site only) matches that precedent.

### Tests
- `scripts/tests/test_show.py:521` `test_superseded_by_derived_from_reverse_edge` and `:535` `test_superseded_by_absent_when_nobody_references` — existing coverage of the derived `superseded_by` field, both asserting on `_parse_card_fields()` directly rather than `cmd_show()` end-to-end. Neither currently exercises a terminal-status (`done`/`cancelled`/`deferred`) superseding issue.
- `scripts/tests/test_issue_parser.py:2453` `test_superseding_issue_done_still_found_when_scan_unfiltered` — existing test whose docstring already names "caller's responsibility to pass an unfiltered scan" as the exact risk this bug reports.
- `scripts/tests/test_issue_parser.py:1273` `test_find_issues_status_filter_none_preserves_default` — documents the default-exclusion behavior (`status_filter=None` drops `done`/`cancelled`/`deferred`) that this bug's fix must widen past, for this call site only.
- `scripts/tests/test_issue_parser.py` (class spanning ~1512-1661) `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes` maintains a `callsite_shapes` registry enumerating every known `find_issues()` caller's exact kwarg shape (e.g. `cli/deps:269`, `epic_progress:53`, `list_cmd:166`) — `show.py:281` is not yet an entry in that registry.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` (`callsite_shapes` list, ~line 1622) — add a `("show:281", {"status_filter": _ALL_STATUSES})` entry once `show.py:281` passes an explicit `status_filter` kwarg, matching the shape of the existing `epic_progress:53`/`cli/deps:269` entries
- `scripts/tests/test_show.py` — no existing test covers `parent_display` in either direction (searched repo-wide, zero hits); widening the same `_all` lookup that fixes `superseded_by` also resolves titles for closed/deferred/done `parent` EPICs (previously ID-only fallback) — add a regression test for this side effect, following the `test_superseded_by_derived_from_reverse_edge` pattern. **Test-fixture caveat:** the `_write_issue` helper (`test_show.py:296`) builds its config with only the `enhancements` category, so a `done` parent written under `.issues/epics/` would never be scanned and the test would fail for the wrong reason. Either write the parent as an `ENH-` file in `enhancements/` (simplest; `parent:` is an ID lookup, not a type check) or extend the helper's `categories` dict with an `epics` entry.

### Documentation
- `.claude/CLAUDE.md:189` (§ Issue File Format → Supersession) already documents the standing contract this bug violates: "`ll-issues show` derives the reverse `Superseded by` row... Never hand-write `superseded_by`."
- `.issues/enhancements/P3-ENH-2829-derive-superseded-by-reverse-edge-from-supersedes.md:118-147` — the origin issue that introduced this feature; its own "Open design questions / Silent degradation" section explicitly predicted this exact bug (superseding issue later closed → row silently vanishes) and left it as an accepted limitation at the time.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md:291` — documents `Superseded by` as derived ("the reverse of another issue's `supersedes:`, never hand-written frontmatter"); describes the same contract this bug violates
- `skills/audit-issue-conflicts/SKILL.md:366` — states that recording `supersedes:` on the kept issue "is what makes `ll-issues show [CLOSED-ID]` derive the reverse `Superseded by` row"; same contract

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a `("show:281", {"status_filter": _ALL_STATUSES})` entry to the `callsite_shapes` registry in `scripts/tests/test_issue_parser.py` (~line 1622) once `show.py:281` passes an explicit `status_filter` kwarg
- Add a regression test in `scripts/tests/test_show.py` asserting `parent_display` resolves the parent's title (not just its ID) when the parent is `done`/`cancelled`/`deferred` — a side effect of the same `_all` widening that fixes `superseded_by`. Write the parent as an ENH file under `enhancements/` (or extend `_write_issue`'s categories) — see the fixture caveat under Tests.

## Program Design

### Signatures

- `find_issues(config: BRConfig, category: str | None = None, skip_ids: set[str] | None = None, only_ids: list[str] | set[str] | None = None, type_prefixes: set[str] | None = None, status_filter: set[str] | None = None, *, skip_blocked: bool = False) -> list[IssueInfo]` (`scripts/little_loops/issue_parser.py:4056`) — already supports an explicit `status_filter`; the bug is the call site never passes one.
- `superseded_by(issue_id: str, all_issues: Iterable[IssueInfo]) -> list[str]` (`scripts/little_loops/issue_parser.py:4204`) — unchanged; only needs an `all_issues` argument that isn't pre-filtered.

### Call Path

`show.py` (`~line 281`, inside the parent/supersession resolution block) -> `find_issues(config, status_filter=set(_ALL_STATUSES))` -> `superseded_by(issue_id, _all)`

## Impact

- **Priority**: P4 - Cosmetic display gap; the underlying supersession data is intact and derivable via `ll-issues show` on the superseding issue itself, so this only affects a single CLI convenience row.
- **Effort**: Small - One-line change to the `find_issues(config)` call's `status_filter` argument, plus one regression test.
- **Risk**: Low - Widening the status filter for this specific lookup only affects the parent-title and superseded-by resolution block; it does not change which issues `ll-issues show` lists or operates on elsewhere. No performance cost: `find_issues()` already parses every file and filters afterward, so the widened filter only retains more already-parsed entries.
- **Breaking Change**: No

## Acceptance Criteria

- [x] `ll-issues show` renders `Superseded by` when the superseding issue is deferred, done, or cancelled (manual check: `ll-issues show FEAT-3385` shows `Superseded by: FEAT-3388`)
- [x] Regression test covering the deferred-superseder case, asserting on `_parse_card_fields()["superseded_by"]` (unit level, matching the existing `test_superseded_by_*` tests — no `cmd_show` end-to-end test required)
- [x] Regression test for `parent_display` resolving a `done`/`cancelled`/`deferred` parent's title
- [x] `("show:281", {"status_filter": _ALL_STATUSES})` entry added to the `callsite_shapes` registry in `test_issue_parser.py`
- [x] `python -m pytest scripts/tests/` passes; `python -m mypy scripts/little_loops/` clean on `show.py`

## Resolution

Widened the supersession/parent lookup in `show.py:281` (`find_issues(config)` →
`find_issues(config, status_filter=set(_ALL_STATUSES))`, importing `_ALL_STATUSES`
from `little_loops.issue_progress`), matching the established
`set(_ALL_STATUSES)` convention used at `normalize.py:275`, `cli/deps.py:269`,
`epic_progress.py:53`, and `list_cmd.py:166`.

Added regression coverage in `test_show.py` (deferred-superseder `superseded_by`
case; `done`-parent `parent_display` title-resolution case) and registered the
new call shape (`("show:281", {"status_filter": _ALL_STATUSES})`) in the
`callsite_shapes` registry in `test_issue_parser.py`. Full suite
(`python -m pytest scripts/tests/`) passes (23189 passed, 43 skipped); `mypy`
and `ruff` clean on all touched files.

## Status

**Open** | Created: 2026-09-05 | Priority: P4


## Session Log
- `/ll:manage-issue` - 2026-09-06T01:37:05 - `cc6fb6c6-194a-445b-a5ab-2f780c8abc03.jsonl`
- `/ll:ready-issue` - 2026-09-06T01:30:00 - `b2298fce-801f-4892-994c-561496dc1163.jsonl`
- `/ll:confidence-check` - 2026-09-06T01:26:41 - `366fbab1-2425-4032-9107-25922a0dc3e9.jsonl`
- `/ll:confidence-check` - 2026-09-06T00:54:09 - `f8c6a35f-53bd-4185-b107-75ddceecc2f6.jsonl`
- `/ll:wire-issue` - 2026-09-06T00:51:45 - `2a52dfcf-16c7-48fe-83e3-d9895c70f5c1.jsonl`
- `/ll:refine-issue` - 2026-09-06T00:38:20 - `d41a820b-4488-495c-b1ba-f59ae30351ff.jsonl`
- `/ll:format-issue` - 2026-09-06T00:18:01 - `1e264319-0c50-4b45-8bb6-a6a83e8511b2.jsonl`
