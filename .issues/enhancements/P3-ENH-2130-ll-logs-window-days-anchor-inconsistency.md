---
id: ENH-2130
type: ENH
priority: P3
status: done
title: ll-logs --window-days anchor semantics inconsistent across subcommands
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T01:52:17Z'
completed_at: '2026-06-19T15:43:02Z'
parent: EPIC-1918
depends_on:
- ENH-2134
decision_needed: false
confidence_score: 95
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2130: ll-logs --window-days anchor semantics inconsistent across subcommands

## Summary

`--window-days` computes a cutoff date relative to a reference timestamp, but that reference differs by subcommand:

- **`sequences`, `stats`, `dead-skills`**: each project/db is filtered independently using *that project's* latest timestamp as the anchor. When used with `--all`, project A's "last 30 days" and project B's "last 30 days" may refer to entirely different calendar windows.
- **`scan-failures`**: uses `latest_ts_overall`, the single latest timestamp seen across *all* projects scanned — a global anchor.

A user running `ll-logs sequences --all --window-days 30` and `ll-logs scan-failures --all --window-days 30` in the same session gets results anchored to different dates. Neither behavior is documented.

## Current Behavior

`--window-days N` anchors to different reference points depending on the subcommand:

- `sequences`, `stats`, `dead-skills`: anchor = per-project latest event timestamp. With `--all`, each project's window is computed independently against its own data, so two projects with different activity recency yield non-overlapping calendar windows for the "same" N-day filter.
- `scan-failures`: anchor = `latest_ts_overall`, the maximum timestamp across all projects scanned in a single invocation — a single shared anchor.

## Expected Behavior

`--window-days N` should use a consistent wall-clock anchor (`datetime.now(UTC) - timedelta(days=N)`) across all subcommands, so "last 30 days" always means the last 30 calendar days regardless of which subcommand is used or how many projects are scanned.

## Motivation

Predictable UX: `--window-days N` should mean the same thing across all subcommands. A user expecting "the last 30 days" should get consistent results.

## Proposed Solution

**Option A — Global anchor (align to `scan-failures` behavior)**: Use the single latest timestamp across all inputs as the anchor for all subcommands. Most intuitive for `--all` usage; slightly less precise per-project.

**Option B — Wall-clock anchor** (recommended): Anchor all subcommands to `datetime.now(UTC)` rather than data-derived timestamps. Eliminates cross-subcommand inconsistency and aligns with user mental model ("last 30 calendar days"). Requires no cross-project timestamp scan. Reuse the existing `datetime` import in `logs.py`; pass an explicit `cutoff: datetime | None` parameter down through `_extract_ll_event_streams`, `_aggregate_skill_stats`, and `_cmd_dead_skills` rather than deriving the anchor internally.

> **Selected:** Option B (wall-clock anchor) — matches existing `history_reader.py` `_stale_cutoff()` pattern; eliminates per-project data-derived anchor and removes `latest_ts_overall` dead code from `_cmd_scan_failures`.

**Option C — Document the current behavior**: Add a note to the CLI docs and each subcommand's `--help` string explaining the per-project vs. global anchor distinction. Lowest change surface.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-19.

**Selected**: Option B — Wall-clock anchor

**Reasoning**: Option B directly matches the established codebase pattern in `history_reader.py:_stale_cutoff()` (line 162) and `history_context.py:246`, both of which use `datetime.now(UTC) - timedelta(days=N)`. It also simplifies `_cmd_scan_failures` by enabling complete removal of the `latest_ts_overall` accumulation (lines 949, 977–978). The existing test-seeding pattern from `test_history_reader.py:92` means no freezegun is needed, keeping the updated tests straightforward.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (global anchor) | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |
| Option B (wall-clock) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option C (document only) | 0/3 | 3/3 | 1/3 | 3/3 | 7/12 |

**Key evidence**:
- **Option A**: Elevates the `latest_ts_overall` anchor to all subcommands — but that anchor is itself one of the two inconsistent behaviors being fixed. No existing codebase pattern uses cross-project max-timestamp as a time window anchor.
- **Option B**: `history_reader.py:_stale_cutoff()` (line 162) and `history_context.py:246` establish wall-clock `datetime.now(UTC) - timedelta(days=N)` as the project standard. `latest_ts_overall` becomes dead code after the fix.
- **Option C**: Documents rather than fixes the inconsistency; contradicts the stated Expected Behavior.

## Implementation Steps

1. Decide on the anchor strategy (recommend Option B — wall-clock is unambiguous and deterministic).
2. Update `_extract_ll_event_streams`, `_aggregate_skill_stats`, and `_cmd_dead_skills` to accept an explicit `cutoff: datetime | None` parameter rather than deriving the anchor internally.
3. In each `_cmd_*` handler, compute `cutoff = datetime.now(UTC) - timedelta(days=args.window_days)` once and pass it down.
4. Update `_cmd_scan_failures` to use the same wall-clock cutoff (remove `latest_ts_overall` anchor).
5. Update `--window-days` help strings to say "within the last N calendar days".
6. Update tests to reflect the new semantics.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Rewrite `test_sequences_window_days_filter` (line 865) and `test_aggregate_skill_stats_window_days` (line 1694) in `test_ll_logs.py` — replace hardcoded absolute timestamps with `datetime.now(UTC) - timedelta(days=N)` relative seeds to avoid date-sensitivity under wall-clock anchor (follow `TestStaleRowFiltering._insert_old_correction` pattern in `test_history_reader.py:94`)
8. Add behavioral test for `_cmd_scan_failures` wall-clock cutoff — seed one recent and one old record, assert old record is excluded; include a cross-project variant confirming `--all --window-days` uses the same calendar cutoff for both projects (validates `latest_ts_overall` removal at lines 949, 977–978)
9. Add behavioral tests for `_cmd_dead_skills` and `_cmd_stats` wall-clock cutoff — same seed-and-assert pattern

## Scope Boundaries

- Out of scope: changing any other `ll-logs` flags or adding new ones
- Out of scope: changing behavior when `--window-days` is omitted (no cutoff filtering)
- Out of scope: modifying `ll-logs discover`, `extract`, `tail`, or `diff` subcommands (they do not use `--window-days`)
- Not a breaking change to the public Python API — `_extract_ll_event_streams` and related helpers are internal

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_extract_ll_event_streams`, `_aggregate_skill_stats`, `_cmd_sequences`, `_cmd_stats`, `_cmd_dead_skills`, `_cmd_scan_failures`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` is the sole consumer of its own internal helpers for the anchor computation
- `scripts/little_loops/cli/ctx_stats.py` — imports `_aggregate_skill_stats` directly at line 20 and calls it at line 494 in `main_ctx_stats()` with no `window_days` argument (`window_days=None` default); signature is unchanged by the fix, but this is an external consumer of a private symbol that the issue currently lists as "no external callers" [Agent 1/2 finding]

### Similar Patterns
- All `--window-days` consumers live in `logs.py`; the fix must be consistent across all six functions above

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` — tests for `sequences`, `stats`, `dead-skills`, `scan-failures` subcommands
  - `test_sequences_window_days_filter` (line 865) — **will break**: hardcoded timestamps (`"2026-06-01T10:00:00Z"`) designed for per-project anchor; rewrite with `datetime.now(UTC) - timedelta(days=N)` relative timestamps (follow `TestStaleRowFiltering._insert_old_correction` pattern in `test_history_reader.py:94`)
  - `test_aggregate_skill_stats_window_days` (line 1694) — **will break**: `"2026-06-01T00:00:00Z"` anchor row becomes stale under wall-clock; rewrite the same way
  - `test_stats_window_days` (line 1449) — parse-only, safe; no behavioral update needed
  - `test_dead_skills_window_days` (line 1740) — parse-only; add new behavioral test seeding data at `datetime.now(UTC) - timedelta(days=recent)` and `datetime.now(UTC) - timedelta(days=old)`, assert old record excluded
  - `test_scan_failures_window_days_flag` (line 2005) — parse-only; add new behavioral test; also add a cross-project test confirming `--all --window-days` uses same calendar cutoff for both projects (validates `latest_ts_overall` removal at lines 949, 977–978)
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` class (line 2921): smoke tests for `main_logs()` entry point with no `--window-days` assertions; not affected by this change

### Documentation
- `docs/reference/CLI.md` — `ll-logs` section; `--window-days` help strings in each affected `_cmd_*` handler

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Function Signatures and Cutoff Logic Locations

| Function | Signature | Cutoff Logic |
|---|---|---|
| `_extract_ll_event_streams` | `(project_folder: Path, *, window_days: int \| None = None)` at `logs.py:222` | Lines 276–278: `cutoff = _parse_iso_timestamp(latest_ts) - timedelta(days=window_days)` — per-project anchor |
| `_aggregate_skill_stats` | `(db_path: Path, *, window_days: int \| None = None)` at `logs.py:674` | Lines 701–704: `cutoff = _parse_iso_timestamp(skill_rows[-1]["ts"]) - timedelta(days=window_days)` — per-DB anchor |
| `_cmd_sequences` | `(args: Namespace, logger: Logger)` at `logs.py:477` | Delegates to `_extract_ll_event_streams`; call at line 497 |
| `_cmd_stats` | `(args: Namespace, logger: Logger)` at `logs.py:1144` | Delegates to `_aggregate_skill_stats`; call at line 1155 |
| `_cmd_dead_skills` | `(args: Namespace, logger: Logger)` at `logs.py:811` | Delegates to `_aggregate_skill_stats`; call at line 823 |
| `_cmd_scan_failures` | `(args: Namespace, logger: Logger)` at `logs.py:926` | `latest_ts_overall` init at line 949; accumulation at lines 977–978; cutoff filter at lines 1046–1050 |

#### `--window-days` Argparse Help Text (4 locations to update)

All four declared identically (`type=int, default=None, metavar="D"`) in `_build_parser()`:
- `logs.py:1769–1774` — `sequences` subparser
- `logs.py:1793–1799` — `stats` subparser
- `logs.py:1824–1830` — `scan-failures` subparser
- `logs.py:1859–1865` — `dead-skills` subparser

Current help: `"Only consider records within D days of latest record"`. New help (Option B): `"within the last N calendar days"`.

#### Import: No New Imports Needed

`from datetime import UTC, datetime, timedelta` already at `logs.py:14`. `datetime.now(UTC)` is not called anywhere today — this is the new call to add.

#### Wall-Clock Cutoff Pattern to Follow

Existing codebase pattern:
- `history_reader.py:_stale_cutoff()` at line 162: `return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")`
- `history_context.py:246` uses same inline pattern

#### Test Coverage Gaps

| Test | Location | Current Type | Action Required |
|---|---|---|---|
| `test_sequences_window_days_filter` | `test_ll_logs.py:865` | Behavioral | **Update**: currently validates per-project anchor; must validate wall-clock anchor |
| `test_aggregate_skill_stats_window_days` | `test_ll_logs.py:1694` | Behavioral (unit) | **Update**: directly tests `_aggregate_skill_stats` with per-DB anchor |
| `test_scan_failures_window_days_flag` | `test_ll_logs.py:2005` | Parse-only | **Add behavioral test**: no filtering behavior is tested today |
| `test_dead_skills_window_days` | `test_ll_logs.py:1740` | Parse-only | **Add behavioral test**: no filtering behavior is tested today |

Test seeding pattern for wall-clock cutoff (from `test_history_reader.py:92`): compute `ts = datetime.now(UTC) - timedelta(days=days_old)` at insertion time — no freezegun needed.

#### `latest_ts_overall` Cleanup Opportunity

After switching to wall-clock anchor, lines 949 (init) and 977–978 (accumulation loop) in `_cmd_scan_failures` can be removed entirely — `latest_ts_overall` is used only by the cutoff filter.

## Impact

- **Priority**: P3 — Behavioral inconsistency; primarily affects multi-project `--all` usage where different projects have different last-active timestamps. Not blocking.
- **Effort**: Small — Refactor of anchor derivation in ~5 functions within a single file; no new infrastructure required.
- **Risk**: Low — Semantic change to `--window-days` (wall-clock vs. data-derived); help text update documents the new behavior. No external API contracts affected.
- **Breaking Change**: Yes (semantic) — Users relying on the per-project or global-max anchor behavior will see different filter boundaries after this change.

## Labels

`cli`, `ll-logs`, `ux-consistency`

## Verification Notes

2026-06-18 (ACCURATE): Confirmed in `cli/logs.py`. `_extract_ll_event_streams` (line 276-278) and `_aggregate_skill_stats` (lines 701-704) both use per-project latest event timestamp as the `--window-days` anchor. `_cmd_scan_failures` (lines 1046-1049) uses `latest_ts_overall` — the global max across all projects scanned. Option B (wall-clock anchor) not yet implemented.

## Status

**Open** | Created: 2026-06-14 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-19T15:28:14 - `ee552026-6004-44a7-80cf-471e10c26dce.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `f18b6716-bf60-4b47-a07f-4901094b9863.jsonl`
- `/ll:wire-issue` - 2026-06-19T15:01:18 - `9b2903ff-f6c7-4d40-b9e4-d543ef646a60.jsonl`
- `/ll:decide-issue` - 2026-06-19T14:50:46 - `ec443386-b697-4ea3-bf7c-48919232b7ca.jsonl`
- `/ll:refine-issue` - 2026-06-19T14:47:55 - `8d7dd3ba-73a4-4db9-bceb-61f0596cf5e8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-14T02:30:10 - `1f6a8dcb-a399-44be-a092-c05f684e7ce2.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:32 - `2a5cb136-c2a6-4327-b4ad-e6deaff58e4f.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
