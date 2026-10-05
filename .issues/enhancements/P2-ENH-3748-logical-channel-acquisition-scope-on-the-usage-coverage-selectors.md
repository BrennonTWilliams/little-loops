---
id: ENH-3748
type: ENH
title: Logical channel acquisition scope on the usage coverage selectors
priority: P2
status: done
discovered_by: issue-size-review
discovered_date: '2026-10-05'
completed_at: '2026-10-05T21:38:18Z'
parent: EPIC-3562
labels:
- observability
- usage-coverage
testable: true
size: Small
blocked_by:
- BUG-3735
blocks:
- ENH-3732
relates_to:
- ENH-3731
- ENH-3730
- ENH-3733
- ENH-3723
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3748: Logical channel acquisition scope on the usage coverage selectors

## Summary

Add a logical `channel=` acquisition scope to `select_usage_coverage` and `select_usage_observations`. Split from ENH-3731 (2026-10-05 pre-implementation review): the scope shares no code with usage qualification, has no caller inside ENH-3731, and its only planned consumer is ENH-3732's transcript-scoped quality report. It edits the same acquisition/output ordering as BUG-3735, so it lands **after** BUG-3735 on the repaired selector.

## Parent Issue

Implements Decision 4 (Option A, refined) of ENH-3723's recorded decision (2026-10-04, `/ll:decide-issue`, commit `01747bb96`): `channel=` scope on `select_usage_coverage`/`select_usage_observations`; the store-wide ambiguity gate and ENH-3543's contract are unchanged (narrowing it belongs to ENH-3730). Tracked under EPIC-3562.

## Current Behavior

Neither selector accepts a channel argument. `issue_history/agent_quality.py:_usage_totals` narrows to transcript rows **after** selection with the raw-column predicate `session_id is not None and channel in (None, "transcript")`, so live/rollout counterparts have already influenced coverage classification and `ambiguous_cross_channel` before they are discarded.

## Expected Behavior

- `select_usage_coverage(..., channel: str | None = None)` and `select_usage_observations(..., channel: str | None = None)`. Accepted non-NULL values are exactly `live`, `transcript`, `rollout`.
- Logical channels are resolved with `row_channel` (legacy NULL/absent channel with a session ID is `transcript`; without one is `live`) before grouping and before `ambiguous_cross_channel` is computed.
- Rows outside the requested channel are excluded from `audit_rows`, `selected_rows` and group subtotals entirely; excluded counterparts cannot change values, coverage or qualification.
- An unsupported argument always raises `ValueError`, validated before schema/query early returns — including on an empty or legacy store (when iterating the `select_usage_observations` generator).
- Default `channel=None` preserves the post-BUG-3735 coverage policy and acquisition population byte-for-byte, and does not silently drop unrecognized stored channel values.
- `since`/`require_run_id` filters and BUG-3735's host/session output narrowing still apply after coverage reconciliation; they cannot certify coverage. Selectors stay coverage-only and keep numerically/provenance-audit-only rows in coverage-selected rows.

## Proposed Solution

Thread `channel` through both selectors in `history_reader/usage.py`. Filter Python-side, immediately after the cursor→dict conversion and before `grouped` is built, so both `row_channel` consumers (per-group channel set in `_classify_coverage`, store-wide `channels` feeding `ambiguous_cross_channel`) see only the declared population. `row_channel` has no SQL equivalent for legacy NULL rows, so no SQL `channel =` predicate is added.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — `select_usage_coverage`, `select_usage_observations`: add and validate `channel`; apply the Python-side filter before `_classify_coverage`. Do not add a string constant naming token/cost columns beside `FROM usage_events` (chokepoint gate).
- `scripts/little_loops/history_reader/__init__.py` — module docstring signature lines for both selectors gain `channel`.

### Dependent Files (unchanged; regression-guarded with `channel=None`)

- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals` calls `select_usage_observations(conn)`; ENH-3732 migrates it to `channel="transcript"`.
- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection` calls `select_usage_coverage(conn, since=since)` store-wide (ENH-3733).
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_compute_cache_rate_from_usage`; `history_reader/usage.py` — `_read_groups`, `waste_attribution`.
- `scripts/little_loops/issue_history/quality_regressions.py` — hand-written `AND (channel = 'transcript' OR channel IS NULL)` query; **do not migrate** — `test_usage_selection_chokepoint_gate.py:test_quality_regressions_query_is_not_flagged` pins that literal (ENH-3732 territory).

### Tests

- New selector-level tests (no in-scope caller passes `channel=`): all three accepted channels; legacy NULL-channel rows with a session ID resolve to `transcript`; a live counterpart for the same and for an unrelated session cannot change transcript-scoped values or coverage; default unscoped coverage still blocks the same population; out-of-channel rows absent from `audit_rows`/`selected_rows`/subtotals; `since`/run filters cannot certify coverage; invalid arguments raise `ValueError` on populated, empty and legacy stores (both selectors, generator iterated).
- Reuse `_live`, `_stored_rollout`, `_handle` and the `fixtures/codex/rollout-*-v0.158.0*.jsonl` fixtures from `scripts/tests/test_enh3543_usage_coverage.py`; explicit-NULL inserts follow the raw `INSERT INTO usage_events(...)` pattern there.
- Controls that must pass unchanged: `test_enh3543_usage_coverage.py`, `test_enh3549_codex_stored_ctx_stats.py`, `test_enh3543_snapshot_usage.py`, `test_feat3304_artifact_dashboard.py`, `test_issue_history_agent_quality.py`, `test_usage_selection_chokepoint_gate.py` (allowlists by enclosing function name: `select_usage_observations`, `recent_usage_events`).

### Documentation

- `docs/reference/API.md` — `### select_usage_coverage / select_usage_observations`: add `channel: str | None = None` to the signature block and a `channel=` paragraph; check the mirror note ("mirror `select_usage_observations`' `channel`/`host`/`host_basis`").
- `docs/ARCHITECTURE.md` — `v53 | usage_events.channel` row: logical channel scope semantics.

## Program Design

### Types

- `CoverageGroup` / `CoverageSelection` (`history_reader/usage.py`, both `frozen=True`) — the scope changes which rows reach them, not their fields.

### Signatures

- `select_usage_coverage(conn, *, since=None, require_run_id=False, host=None, session_id=None, channel: str | None = None) -> CoverageSelection` — new `channel` argument.
- `select_usage_observations(conn, *, since=None, require_run_id=False, host=None, session_id=None, channel: str | None = None) -> Iterator[Mapping[str, Any]]` — same argument; yields the scoped `audit_rows`.
- `row_channel(row) -> str` — existing logical-channel resolver in `little_loops.token_provenance`.

### Call Path

`select_usage_observations` -> `select_usage_coverage` -> channel filter (`row_channel`) -> `_classify_coverage` -> `CoverageSelection`.

### Decision Rules

- Validate `channel` first; anything other than `None`/`live`/`transcript`/`rollout` raises `ValueError`.
- Filter by `row_channel(row) == channel` before grouping and before `ambiguous_cross_channel`; `None` filters nothing.
- Acquisition scope precedes BUG-3735's coverage-before-output-narrowing order; it does not certify a host/session by removing possible cross-channel counterparts from an unscoped request.

## Implementation Steps

1. Confirm BUG-3735 is committed; re-anchor on the repaired `select_usage_coverage`.
2. Write the failing selector-level tests above (TDD).
3. Add and validate `channel`, filter Python-side, update docstrings.
4. Run `python -m pytest scripts/tests/test_usage_selection_chokepoint_gate.py scripts/tests/test_enh3543_usage_coverage.py scripts/tests/test_enh3549_codex_stored_ctx_stats.py`, then the full suite.
5. Update API.md and ARCHITECTURE.md.

## Acceptance Criteria

- [ ] `channel="transcript"` on both selectors reconciles transcript and legacy NULL/absent-channel rows with a session ID before coverage analysis; excluded live/rollout counterparts cannot change values or coverage and are absent from `audit_rows`/`selected_rows`/subtotals.
- [ ] An unrecognized channel raises `ValueError` on populated, empty and legacy stores.
- [ ] Default `channel=None` output is identical to the post-BUG-3735 baseline for every existing caller; unscoped coverage still blocks unresolved counterparts; `since`/run filters cannot certify coverage.
- [ ] No new SQL constant trips the chokepoint gate; API.md and ARCHITECTURE.md describe the argument.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — prerequisite for ENH-3732's transcript-scoped quality report.
- **Effort**: Small — one argument, one Python-side filter, selector-level tests.
- **Risk**: Low — default path unchanged.

## Scope Boundaries

- **Out of scope:** usage qualification (ENH-3731), migrating any caller to `channel=` (ENH-3732), ENH-3730's store-wide ambiguity redesign, BUG-3735's acquisition/output repair, the stored-cache `channels` metadata normalization (BUG-3735).

## Resolution

Implemented 2026-10-05. `select_usage_coverage`/`select_usage_observations` accept `channel` (`live`/`transcript`/`rollout`), validated first (`ValueError` before any schema early return); rows are filtered Python-side by `row_channel` before grouping and `ambiguous_cross_channel`. `channel=None` is unchanged. Tests: `scripts/tests/test_enh3748_usage_channel_scope.py`; docs: API.md, ARCHITECTURE.md, `history_reader/__init__.py` docstring. Full suite: only unrelated failures (issue-corpus evidence/prose-dep gates on other issues' files, live libsql endpoint).

## Session Log


- `/ll:manage-issue` - 2026-10-05T21:38:18 - `00c36ff6-10c3-4ba5-9b72-45eaac795f67.jsonl`
- `/ll:ready-issue` - 2026-10-05T21:27:11 - `747c79bd-5eb2-4930-a17d-72ecde1f4d4f.jsonl`
- `/ll:confidence-check` - 2026-10-05T20:41:25 - `db871f03-686f-4948-9fc4-2cabe2027d34.jsonl`
- Split from ENH-3731 - 2026-10-05 - Pre-implementation review (`/ll:advise` with `claude-fable-5-1`, confidence 0.85) moved the `channel=` selector scope out of ENH-3731 and ordered it after BUG-3735, which rewrites the same acquisition/output ordering.

## Status

**Open** | Created: 2026-10-05 | Priority: P2
