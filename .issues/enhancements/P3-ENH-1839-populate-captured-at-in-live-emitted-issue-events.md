---
id: ENH-1839
title: Populate captured_at in live-emitted issue events
type: ENH
priority: P3
status: done
captured_at: '2026-06-01T03:52:30Z'
completed_at: '2026-06-01T11:52:36Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- ENH-1711
parent: EPIC-1707
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1839: Populate captured_at in live-emitted issue events

## Summary

Fix `issue_lifecycle.py` event payloads and `SQLiteTransport.send()` to populate `captured_at` in live-emitted `issue_events` rows, which are currently always NULL. This eliminates ENH-1711's backfill dependency: the `issue_sessions` VIEW will work immediately after an issue is created, without requiring a manual `backfill` pass first.

## Current Behavior

Live-emitted `issue_events` rows always have `captured_at = NULL`. `issue_lifecycle.py`'s six emit sites (`create_issue_from_failure`, `close_issue`, `complete_issue_lifecycle`, `defer_issue`, `undefer_issue`, `skip_issue`) do not include `captured_at` in the event dict passed to `emit_issue_event()`. `SQLiteTransport.send()` also discards the field even if present. As a result, the `issue_sessions` VIEW filters `WHERE ie.captured_at IS NOT NULL` and silently excludes all live-emitted rows, giving users zero results in `ll-history sessions <ID>` until they run `ll-session backfill`.

## Expected Behavior

After live issue transitions, `captured_at` is populated immediately in `issue_events` from the issue's frontmatter value — no manual `ll-session backfill` pass required. `ll-history sessions <ID>` returns session rows immediately after working on an issue in a live session.

## Motivation

ENH-1711 (Option A) creates an `issue_sessions` VIEW that joins `issue_events` to `message_events` via overlapping timestamps. The VIEW filters `WHERE ie.captured_at IS NOT NULL`, meaning it only returns results for issues whose `captured_at` was set by `_backfill_issues()`. Live-emitted rows (from `create_issue_from_failure`, `close_issue`, etc.) never include `captured_at` in their event payloads, so they are silently excluded. Users who work on an issue in a session immediately see zero rows in `ll-history sessions <ID>` until they run backfill.

The fix is narrow: `issue_lifecycle.py` already reads `captured_at` from issue frontmatter in several places; it just doesn't include it in the event dict it emits.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — add `"captured_at"` key to the event dict at all 6 emit sites
- `scripts/little_loops/history_reader.py` — update stale `sessions_for_issue()` docstring that says "live-emitted rows have `captured_at=NULL` and are excluded"; no longer accurate after this fix [Agent 2 wiring finding]
- `scripts/little_loops/session_store.py` *(comment only)* — update stale inline comment at lines 182–184: "excluded until a backfill pass runs" is no longer accurate for issues processed after this fix; `SQLiteTransport.send()` INSERT logic requires no code change [Agent 2 wiring finding]

### Files Already Wired (No Changes Needed)
- `scripts/little_loops/session_store.py` — `SQLiteTransport.send()` already reads `event.get("captured_at")` and includes it at position 7 of the `INSERT OR IGNORE INTO issue_events` tuple (~line 543); no transport changes required

### Reference Implementation (Backfill Path)
- `scripts/little_loops/session_store.py:_backfill_issues()` (~line 624) — reads `captured_at = fm.get("captured_at")` and writes `str(captured_at) if captured_at else None` into the INSERT; this is the authoritative pattern to follow

### Similar Patterns
- `scripts/little_loops/issue_lifecycle.py:verify_issue_completed()` (~line 384) — shows the established local-import pattern: `from little_loops.frontmatter import parse_frontmatter` inside the function, then `fm = parse_frontmatter(path.read_text(encoding="utf-8"))`, then `fm.get("captured_at")`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — calls `create_issue_from_failure()` (~line 877), `close_issue()` (~line 701), `complete_issue_lifecycle()` (~lines 935, 945); no code changes required, these sites pass `event_bus` through to the lifecycle functions
- `scripts/little_loops/parallel/orchestrator.py` — calls `close_issue()` (~lines 921, 1034) and wraps `complete_issue_lifecycle()` internally via `_complete_issue_lifecycle_if_needed()`; no code changes required
- `scripts/little_loops/cli/issues/skip.py` — calls `skip_issue()` (~line 60) without `event_bus`; no code changes required
- `scripts/little_loops/__init__.py` — exports `close_issue`, `complete_issue_lifecycle`, `create_issue_from_failure`, `verify_issue_completed`; no changes required

### Tests
- `scripts/tests/test_issue_lifecycle.py:TestEventBusEmission` (~line 1172) — existing test class with fixture and pattern for asserting event dict fields; add `assert event["captured_at"] == expected` for each of the 6 sites
- `scripts/tests/test_session_store.py:TestSQLiteTransportIssueEvents` (~line 590) — existing round-trip test pattern; add a test that passes `"captured_at"` in the send dict and asserts the column is non-NULL in the DB
- `scripts/tests/test_session_store.py:TestBackfillIssuesV2Columns` (~line 531) — existing backfill tests; must pass unchanged per scope boundary

_Wiring pass added by `/ll:wire-issue`:_
- **Fixture gap**: `sample_issue_info` fixture used by all 6 `TestEventBusEmission` tests writes frontmatter without `captured_at` — update fixture (or individual test setups) to include `captured_at: '2026-05-20T10:00:00Z'` so `assert event["captured_at"] == expected` checks a specific value rather than `None` [Agent 3 wiring finding]
- `scripts/tests/test_session_store.py:TestIssueSessionsView.test_issue_sessions_excludes_null_captured_at` (~line 862) — docstring premise changes (live-emitted rows now have non-NULL `captured_at`); add companion positive test asserting a live-emitted row with `captured_at` set appears in the VIEW; existing negative test code (NULL rows excluded) passes unchanged [Agent 3 wiring finding]

### Documentation
- `docs/ARCHITECTURE.md` — documents history.db producer/consumer flow; may need a note clarifying live-emit path now also populates `captured_at`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-history sessions <ISSUE_ID>` section (~line 1272) and `recent --issue` flag description (~line 1535) contain "Requires a prior `ll-session backfill` pass" caveat — update to reflect live-emitted rows now populate `captured_at` immediately [Agent 2 wiring finding]
- `docs/reference/EVENT-SCHEMA.md` — all 6 issue lifecycle event property tables (~lines 707–839) do not list `captured_at` as a property; add field entry to each table (`additionalProperties: true` means no validation failure, but docs are incomplete) [Agent 2 wiring finding]

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> **Correction to original step 2**: `SQLiteTransport.send()` in `session_store.py` already reads `event.get("captured_at")` and writes it to the `issue_events` INSERT (~line 543). No changes to `session_store.py` are required — the only file to modify is `issue_lifecycle.py`.
>
> **Key constraint**: `IssueInfo` does NOT have a `captured_at` attribute. All 6 emit sites must read it via `parse_frontmatter()`. The local-import pattern (`from little_loops.frontmatter import parse_frontmatter` inside the function) is already established at line 384.

1. In `scripts/little_loops/issue_lifecycle.py`, update each of the 6 emit sites to include `"captured_at"` in the event dict. Since `IssueInfo` has no `captured_at` attribute, each site reads it via `parse_frontmatter()` on the available file path:

   - **`create_issue_from_failure()` (~line 408)**: The `captured_at` value is `_completed_at_now()` written into the frontmatter content string at line ~452. Extract it as a local variable before the content string (`captured_at_val = _completed_at_now()`), substitute `{captured_at_val}` in the f-string, and add `"captured_at": captured_at_val` to the event dict.

   - **`close_issue()` (~line 517)**: `original_path = info.path` is available. Parse frontmatter early in the `try` block using `parse_frontmatter(original_path.read_text(...))` to get `captured_at`, then add `"captured_at": captured_at` to the event dict at line ~603.

   - **`complete_issue_lifecycle()` (~line 611)**: `original_path = info.path` and `content` (the file text) are available. Parse `captured_at = parse_frontmatter(content).get("captured_at")` after the initial content read at line ~631, then add `"captured_at": captured_at` to the event dict at line ~668.

   - **`defer_issue()` (~line 706)**: `content = original_path.read_text(encoding="utf-8")` is already called at line ~737. Parse `captured_at = parse_frontmatter(content).get("captured_at")` immediately after, then add `"captured_at": captured_at` to the event dict at line ~759.

   - **`skip_issue()` (~line 785)**: Unlike the others, this function reads the file only to concatenate a skip section — it does not parse frontmatter. Split the read: `raw_content = original_path.read_text(encoding="utf-8")`, then `captured_at = parse_frontmatter(raw_content).get("captured_at")`, then set `content = raw_content + _build_skip_section(reason)` as before. Add `"captured_at": captured_at` to the event dict at line ~847.

   - **`undefer_issue()` (~line 851)**: `content = deferred_issue_path.read_text(encoding="utf-8")` is already called. Parse `captured_at = parse_frontmatter(content).get("captured_at")` immediately after, then add `"captured_at": captured_at` to the event dict at line ~904.

2. **No changes needed** to `scripts/little_loops/session_store.py` — `SQLiteTransport.send()` already handles `captured_at` at the INSERT level.

3. Verify `_backfill_issues()` is unaffected — it writes `captured_at` directly from the parsed frontmatter dict (`fm.get("captured_at")`, line ~647) and does not go through `emit_issue_event()`.

4. Add tests to `test_issue_lifecycle.py` following the `TestEventBusEmission` pattern (~line 1172): assert `event["captured_at"]` equals the expected ISO timestamp value for each of the 6 emit functions.

5. Add one test to `test_session_store.py` following `TestSQLiteTransportIssueEvents` (~line 590): pass `"captured_at": "2026-05-20T10:00:00Z"` in the event dict to `send()`, then query the DB and assert `rows[0]["captured_at"] == "2026-05-20T10:00:00Z"`.

6. Run: `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_issue_lifecycle.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/history_reader.py:sessions_for_issue()` docstring — remove "live-emitted rows have `captured_at=NULL` and are excluded" claim; replace with accurate description
8. Update stale inline comment in `scripts/little_loops/session_store.py` (lines 182–184) — "excluded until a backfill pass runs" is no longer accurate after this fix
9. Update `docs/reference/CLI.md` — remove/qualify "Requires a prior `ll-session backfill` pass" caveat in `ll-history sessions` section (~line 1272) and `recent --issue` flag (~line 1535)
10. Update `sample_issue_info` fixture in `test_issue_lifecycle.py:TestEventBusEmission` to include `captured_at` in frontmatter YAML (e.g. `captured_at: '2026-05-20T10:00:00Z'`) so assertions on `event["captured_at"]` verify a specific value
11. Add companion positive test in `test_session_store.py:TestIssueSessionsView` asserting that a row inserted via `SQLiteTransport.send()` with `captured_at` set appears in the VIEW

## API / Interface Changes

No public API changes. `captured_at` is an existing column in `issue_events`; this change starts populating it from live events in addition to backfill.

## Acceptance Criteria

- After creating or transitioning an issue in a live session, `SELECT captured_at FROM issue_events WHERE issue_id = '<ID>'` returns a non-NULL value without running `ll-session backfill`.
- `ll-history sessions <ID>` (from ENH-1711) returns session rows immediately after working on the issue, without a prior backfill pass.
- Existing backfill tests in `scripts/tests/test_session_store.py` continue to pass unchanged.

## Scope Boundaries

- No schema changes — `captured_at` column already exists in `issue_events` (added in schema v2)
- `_backfill_issues()` is unchanged; it writes `captured_at` directly from the frontmatter dict and does not go through `emit_issue_event()`
- No changes to the `issue_sessions` VIEW definition or ENH-1711's query logic
- Does not address other potentially NULL fields in `issue_events`
- Does not change the public Python API for `emit_issue_event()` or `SQLiteTransport.send()`

## Impact

- **Priority**: P3 — Quality-of-life fix; new users see confusing empty `ll-history sessions` output until they discover the backfill command
- **Effort**: Small — Two targeted changes in two files (6 emit sites in `issue_lifecycle.py` + one INSERT tuple in `session_store.py`); no new patterns required
- **Risk**: Low — Populates an existing NULL column; no schema migration; backfill path is unaffected; well-tested insertion path
- **Breaking Change**: No

## Labels

`session-store`, `issue-lifecycle`, `history-db`, `enhancement`

## Session Log
- `/ll:ready-issue` - 2026-06-01T11:41:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a286eea1-c41c-4201-bcb4-91cea0e98d65.jsonl`
- `/ll:confidence-check` - 2026-06-01T12:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c45015c-035b-44de-baea-dddaf95c3385.jsonl`
- `/ll:wire-issue` - 2026-06-01T11:35:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13aa779a-fb54-4ecb-a824-b2c6b963f726.jsonl`
- `/ll:refine-issue` - 2026-06-01T11:28:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7066e3cc-b95f-4bd0-8d3f-82278ee2d580.jsonl`
- `/ll:format-issue` - 2026-06-01T03:54:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2276f3e0-d626-41d7-ba0a-b79943225ed9.jsonl`
- `/ll:capture-issue` - 2026-06-01T03:52:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43c6ff18-cbc3-4adc-b83d-de514a9863c0.jsonl`

## Status

**Open** | Created: 2026-06-01 | Priority: P3
