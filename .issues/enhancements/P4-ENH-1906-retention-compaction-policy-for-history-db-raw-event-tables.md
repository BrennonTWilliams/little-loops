---
id: ENH-1906
title: Retention/compaction policy for history.db raw event tables
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T19:50:05Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, FEAT-1712, ENH-1830]
blocked_by: []
labels:
  - captured
  - history-db
---

# ENH-1906: Retention/compaction policy for history.db raw event tables

## Summary

`.ll/history.db` is ~221 MB and grows unbounded. The `issue_sessions` view spans
178k rows; `tool_events` holds 80k, `cli_events` 34k. There is no eviction or
roll-up of raw event rows. FEAT-1712 (hierarchical summary DAG) addresses
*summarization* of session history but not *pruning* of the raw event tables,
so the DB will keep growing and backfill/FTS scans will keep slowing.

## Current Behavior

- All raw events (`tool_events`, `cli_events`, `file_events`, `message_events`)
  accumulate indefinitely; nothing is ever evicted or rolled up.
- DB size and FTS5 index grow linearly with usage; backfill scans walk an
  ever-larger corpus.

## Expected Behavior

- A configurable retention policy prunes or rolls up high-volume raw events
  (tool/cli/file/message) older than N days, while retaining lower-volume,
  higher-value events (`issue_events`, `user_corrections`) longer.
- Policy is config-gated under `analytics` and off (or generous) by default so
  fresh projects are unaffected.
- A `VACUUM`/compaction step reclaims space after pruning.

## Motivation

Unbounded growth turns the context DB from an asset into a maintenance/perf
liability. A retention story keeps reads fast and the file size bounded,
complementing FEAT-1712's summary layer (summarize-then-prune).

## Proposed Solution

1. Add an `analytics.retention` config block (per-table max-age / max-rows).
2. Add a prune routine in `session_store.py` (e.g. `prune(config)`), invoked
   opportunistically (after backfill) or via `ll-session prune`.
3. Optionally roll raw rows into FEAT-1712 summaries before deletion.
4. Run `VACUUM` after prune to reclaim disk.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — prune/compaction routine.
- `config-schema.json` — `analytics.retention` settings.
- Optionally `scripts/little_loops/cli/` — `ll-session prune` subcommand.

### Tests
- `scripts/tests/test_session_store.py` — prune respects per-table age limits;
  high-value tables retained; gate off by default; idempotent.

## Implementation Steps

0. **Coordinate with ENH-1911 data dependencies.** The recurrence-feedback detector in
   ENH-1911 relies on FTS5 searches over `message_events` and `user_corrections` rows that
   pruning would remove. Before enabling retention on these tables, verify that
   ENH-1911's detectors have run, or support a `recurrence_exempt_tables` override so
   correction-shaped rows survive until recurrence analysis has processed them.

1. Define retention config schema + defaults.
2. Implement prune routine with per-table rules.
3. Wire optional roll-up into FEAT-1712 summaries (if landed).
4. Add VACUUM + tests.

## Impact

- **Priority**: P4 — not urgent at current size, but compounding; cheap to add
  before the DB grows much larger.
- **Effort**: Medium.
- **Risk**: Medium — deleting raw events is irreversible; default-off and
  conservative ages mitigate. Coordinate with FEAT-1712 so summaries exist
  before raw rows are pruned.
- **Breaking Change**: No (default-off / generous defaults).

## Labels

`captured`, `history-db`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-04_

**Verdict: VALID (with size update)** — DB size updated from ~112 MB → ~221 MB (actual: 231,915,520 bytes as of 2026-06-04). Blocker FEAT-1712 is done; core retention/pruning feature (`ll-session prune`, `analytics.retention` config key) is not yet implemented. Issue is unblocked and ready to implement. Previous verification (2026-06-03) noted FEAT-1712 completion and `session_store.py` compaction infrastructure.

## Session Log
- `/ll:verify-issues` - 2026-06-04T18:41:57 - `18003f27-33de-416c-b594-e351d9d60c9d.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T04:34:25 - `e1e6b264-2dd0-4d92-92be-102681aa7fbc.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:21:13 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T21:54:23 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:50:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13a13638-9030-4da6-94ba-939418824572.jsonl`

---

**Open** | Created: 2026-06-03 | Priority: P4
