---
id: ENH-3651
type: ENH
title: Hook-driven incremental ingest of the current session transcript into usage_events
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T02:51:25Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3532
blocks:
- ENH-3549
- ENH-3656
---

# ENH-3651: Hook-driven incremental ingest of the current session transcript into usage_events

## Summary

Make the still-running session's token usage visible to stored-usage readers without waiting for the next SessionStart or a manual rebuild, by ingesting **and deriving** it incrementally from a lifecycle hook (Stop, PreCompact, or throttled PostToolUse). Split out of ENH-3549's freshness gate (option A). Review of the code (2026-09-29) showed the problem is larger than "the current session is not yet ingested": stored transcript usage is stale until a rebuild, so ENH-3549 depends on this issue's incremental derive (see Current Behavior). The hook trigger is the smaller half; the incremental derive is the substance.

## Current Behavior

- The SessionStart hook (`little_loops.hooks.session_start`) spawns a **detached** `little_loops.cli.backfill_worker` subprocess (`start_new_session=True`; a daemon thread was killed when the short-lived hook exited, BUG-1882). It passes the payload's `transcript_path` when present, otherwise the host's project folder, and is skipped when `LL_NON_INTERACTIVE` is set.
- The worker runs `backfill_incremental`, which is **ingest-only**: it writes `raw_events` for sources modified after the global `last_raw_event_ts` watermark and derives nothing.
- Transcript `usage_events` rows are derived only by `rebuild()` (`_backfill_usage_events` is called from `lifecycle.py` in that one place). `rebuild()` is a full `DELETE`-then-replay of every derived table (`usage_events` scoped by `channel IS NOT 'live'`), and the worker runs it only with `--rebuild`, which SessionStart passes only when `SCHEMA_VERSION` has advanced past `last_rebuild_version`.
- Net effect: transcript `usage_events` are stale until a schema bump or a manual `ll-session` rebuild, not merely until the next SessionStart. The current session is never present.
- Existing hook entries in `hooks/hooks.json`: `Stop` has four (sentinel 10s, cleanup 15s, telemetry 5s, the advisor `stop.sh` at 190s); `PreCompact` has two (5s each); `PostToolUse` has several at 5s.

## Expected Behavior

A non-blocking hook step brings the current session's transcript usage into `usage_events` shortly after each turn (or compaction), so `ll-ctx-stats` and every other stored-usage reader see a fresh figure. Reads stay pure. The write path:

- ingests only the appended lines of the current transcript (no whole-file rescan per turn once that is measured to matter),
- derives `usage_events` for newly ingested `raw_events` after a one-time catch-up of previously ingested rows, without a full `rebuild()` on each turn,
- is idempotent with the SessionStart path and with a later full `rebuild()` (same rows, same identity, no double counting), and
- never delays the turn: detached like the SessionStart worker, with a throttle so it does not run on every tool call.

## Motivation

ENH-3549 turns `ll-ctx-stats`'s cache rate into a read-only consumer of stored observations. `ll-ctx-stats` usually reports on the latest session, which is usually the one still running, so without this step the figure is unavailable for the current session (and, per Current Behavior, for older sessions too until a rebuild). Every other stored-usage reader (cost, waste, dashboard) has the same blind spot.

## Proposed Solution

Investigate first; the design is open. Candidate shape:

1. Choose the trigger. `Stop` fires after every assistant turn (as the advisor gate notes), `PreCompact` is rare but pre-compaction is when occupancy matters, `PostToolUse` is frequent and needs a throttle. Prefer `Stop` plus a throttle, reusing the detached-worker pattern rather than running in the hook process.
2. Add an incremental derive: `_backfill_usage_events` over eligible `raw_events` rows newer than a committed derived-row checkpoint, writing through the same normalizer and identity contract as `rebuild()` (ENH-3532 key rules, ENH-3546 eligibility discriminator). A source-specific ingest cursor is separate from this derive checkpoint; the global `last_raw_event_ts` cannot decide whether the active file has unread appended lines.
3. Make the incremental write and `rebuild()` provably equivalent (a test that ingests a transcript incrementally in N slices and compares against one full rebuild).

### Catch-up, atomicity and host coverage

On first enablement, already-ingested `raw_events` may have no corresponding `usage_events`, while others may already have derived rows from an earlier rebuild. Establish a one-time catch-up that safely replaces or deduplicates replayable usage rows, preserves live rows, and records the derived checkpoint in the **same transaction**; a full `rebuild()` must also advance or reset that checkpoint atomically with its replacement rows. Subsequent workers acquire a write transaction before reading the checkpoint, then commit derived rows and checkpoint together. A crash before commit retries the same rows; a crash after commit skips them. Define a stable source-row link or equivalent uniqueness rule for transcript rows so a retry cannot insert a second copy. Replay state that spans slices (including a Codex turn that opens before the slice boundary) must be persisted or reconstructed from its prefix, never inferred from a suffix alone.

The derive mechanism covers every replayable usage channel produced by `_backfill_usage_events`, including `rollout` once ENH-3532 adds it; ENH-3532 owns Codex normalization and native deduplication, not a second derive engine. If a new normalizer lands **after** the checkpoint already passed its historical raw rows, its schema/derivation version must trigger a one-time replay of those rows and atomically establish the new checkpoint; merely deriving rows with larger IDs would lose the older observations. Test the generic normalizer-version catch-up here, and verify both concrete ENH-3532/ENH-3651 landing orders under ENH-3549 after the Codex normalizer exists. Prove the combined Codex ingest → incremental derive → selected read before ENH-3549 retires `_codex_cache_usage`. The hook trigger is initially Claude Code unless a verified adapter provides the same lifecycle event and transcript path for another host. Record the supported trigger hosts and make an unsupported host's current-session result explicitly unavailable until an ingest/derive trigger exists; do not claim an eight-host freshness guarantee from a Claude-only hook.

**Freshness boundary for readers (2026-09-29 review):** commit enough source-specific ingest progress and derive-completion metadata for a read-only consumer to state how far the selected session was materialized. `usage_events.observed_at` is the observation time, not proof that the detached worker processed the current source tail. A global derive checkpoint is sufficient only if every eligible raw row through it is committed and a selected session's source cursor can be compared with its current source tail; skipped rows, late appends, rotation and partial writes must not make the global checkpoint falsely certify that session. Otherwise persist a per-session completion boundary. ENH-3656 reads this proof and reports as-of plus stale/unknown lag; it never treats an earlier stored value as fresh after a newer append and failed worker.

**Trigger ownership:** this issue implements the shared ingest/derive worker and a verified Claude Code lifecycle trigger so ENH-3656 can ship first. It leaves a reusable host-adapter entry point and records Codex trigger requirements, but ENH-3549 owns wiring and proving the Codex runtime trigger during its later cutover. A manually invoked Codex rollout derive test proves the shared mechanism, not current-session Codex freshness. ENH-3651 can close before ENH-3532; ENH-3549 owns the combined Codex producer, trigger, derive and read test after both land.

## Program Design

### Types

- No new token-accounting type; the incremental path emits the same `TokenUsage`/`usage_events` rows as `rebuild()`. Keep source-specific ingest progress separate from the last committed derived `raw_events.id` (or an equivalent replay checkpoint). Choose the source-row uniqueness link, checkpoint schema, reader-visible as-of boundary and first-enable catch-up before writing the migration; document how `rebuild()` updates them.

### Signatures

- `backfill_usage_incremental(db: Path | str, *, since_raw_event_id: int | None = None) -> int` — proposed: derive replayable `usage_events` for `raw_events` rows newer than the committed checkpoint and return the row count; delegates to `_backfill_usage_events`.
- `backfill_incremental(db, *, jsonl_files=None, handles=None, since_ts=None, config=None, also_rebuild=False, host=None) -> dict[str, int]` — existing (`session_store/lifecycle.py`); ingest-only, unchanged.

### Call Path

- Stop/PreCompact hook → detached `backfill_worker` → `backfill_incremental` (`raw_events`) → `backfill_usage_incremental` (`usage_events`)
- full `rebuild()` → `_backfill_usage_events` plus an atomic checkpoint update (must yield the same rows)

## Integration Map

### Files to Modify
- `hooks/hooks.json` — a Stop/PreCompact (or throttled PostToolUse) entry with a short timeout that only spawns the detached worker.
- `scripts/little_loops/hooks/` — a handler beside `session_start.py` / `pre_compact.py`; `scripts/little_loops/hooks/__init__.py` `_USAGE` banner if a new intent is added.
- `scripts/little_loops/cli/backfill_worker.py` — an incremental-derive mode (it currently has no derive step and no argparse by design).
- `scripts/little_loops/session_store/lifecycle.py`, `session_store/writers.py` — incremental derive entry point beside `backfill_incremental` and `_backfill_usage_events`.
- `scripts/little_loops/session_store/schema.py`, `session_store/schema_manifest.json` — append-only checkpoint/source-row identity migration if the chosen design requires one; coordinate with EPIC-3562's landing-order rule.

### Dependent Files (Callers/Importers)
- `ll-ctx-stats` and the usage/cost/waste readers via `select_usage_observations` (freshness only; no contract change).
- The host adapters under `hooks/adapters/` (Claude Code trigger here; Codex trigger added under ENH-3549; Codex/OpenCode reach `transcript_path` differently, see the SessionStart handler).

### Similar Patterns
- SessionStart detached worker launch in `session_start.py` (ENH-1830 / BUG-1882 / ENH-1945).
- `pre_done` Stop handler: per-turn firing, diff-hash dedup, non-blocking (FEAT-3118).

### Tests
- `test_session_store_lifecycle.py` (first-enable catch-up, incremental-vs-rebuild equivalence, cross-slice state, interrupted/concurrent workers, source-tail/as-of proof and Codex rollout compatibility after ENH-3532), `test_hooks_integration.py`, hook-intent tests, a backfill-worker test. ENH-3549 owns the later real Codex hook-to-reader test.

### Documentation
- `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/reference/CLI.md` (freshness of stored usage), `docs/ARCHITECTURE.md` if the ingest/derive split is described there.

### Configuration
- A throttle/enable key under the existing hooks or history config (decide during implementation).

## Implementation Steps

1. Measure: cost of `backfill_incremental` on a large growing transcript (does it rescan the whole file?) and the watermark interaction (`last_raw_event_ts` is global, so a hook-driven run must not skip or double-advance other sources). Define rotation/truncation behavior for the source-specific cursor.
2. Choose and record the source-row uniqueness link, initial/version-change catch-up, transaction/checkpoint, reader-visible as-of boundary and cross-slice replay-state design. Prove equivalence with `rebuild()` on sliced ingestion, including a generic new-normalizer-after-checkpoint case, a live-only-row-preserving check, interrupted/concurrent workers and a selected source that advances after a failed worker. ENH-3549 tests the concrete Codex landing orders once ENH-3532 exists.
3. Add the Claude hook entry and detached launch with a throttle; confirm it never blocks a turn (timeout, `LL_NON_INTERACTIVE`). Record which host adapters actually trigger it and the entry point ENH-3549 will use for Codex.
4. Update docs; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P2 — ENH-3549 replaces the transcript parser with a stored-usage read, and stored transcript usage is only current after a full rebuild; without an incremental derive that switch turns today's working `ll-ctx-stats` figure into "unavailable" for the current session and for every session since the last rebuild. Every other stored-usage reader benefits too.
- **Effort**: Medium — the incremental derive is new (only full `rebuild()` exists today).
- **Risk**: Medium — a second writer path for derived rows must stay equivalent to `rebuild()`, and hook latency must stay off the turn's critical path.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P2

## Success Metrics

- After a turn on a supported hook-trigger host, `ll-ctx-stats` can read that session's usage and committed as-of boundary from `usage_events`/store metadata within one throttle interval, with no read-time parsing or backfill.
- No measurable added turn latency (the hook returns after spawning the detached worker).

## Acceptance Criteria

- [ ] On each supported hook-trigger host, the current session's transcript usage reaches `usage_events` without a SessionStart, schema bump or manual rebuild; a stored-usage read sees it.
- [ ] Slice-by-slice incremental ingest+derive of a transcript produces exactly the rows one full `rebuild()` produces (same counts, identity and provenance); running both, in either order, never double-counts.
- [ ] First enablement catches up already-ingested but underived raw rows. The derive checkpoint and rows commit together; crash-before-commit, crash-after-commit, concurrent-worker and later-rebuild tests prove no loss or duplicate rows.
- [ ] A newly added usage normalizer replays historical eligible raw rows that predate the checkpoint (generic fixture here); ENH-3549 later verifies that ENH-3532 before ENH-3651 and ENH-3651 before ENH-3532 produce the same Codex rollout observations.
- [ ] Source ingest progress does not depend on the global `last_raw_event_ts` alone; append, rotation/truncation and a turn span crossing slice boundaries have fixture-backed behavior.
- [ ] The shared derive accepts Codex rollout observations once ENH-3532 lands, without a per-turn full rebuild. This compatibility is tested after ENH-3532 under ENH-3549 if ENH-3651 lands first; ENH-3549 also owns the real Codex hook-to-reader test.
- [ ] Live-channel rows are untouched; the SessionStart worker and the hook path can run concurrently without corrupting the `last_raw_event_ts` watermark.
- [ ] The hook never blocks the turn: it only spawns the detached worker, honors `LL_NON_INTERACTIVE`, and is throttled.
- [ ] Supported hook-trigger hosts are listed and tested; hosts without a proven trigger report unavailable current-session usage rather than silently claiming freshness.
- [ ] A selected session's committed as-of boundary can be compared with its current source tail without parsing usage at read time. A newer append followed by a failed/skipped worker is stale or has explicit unknown lag, never fresh; checkpoint advancement cannot hide skipped sessions, late appends, rotation or partial tails.
- [ ] Legacy transcript rows keep their existing provenance (ENH-3546); new rows follow whatever eligibility discriminator that issue defines.

## Scope Boundaries

- **In scope**: the Claude Code hook trigger, reusable host-adapter worker entry point, initial catch-up, incremental derive for replayable `usage_events` channels, atomic checkpoint/as-of coordination with `rebuild()`, throttle and docs.
- **Out of scope**: the stored-usage cache-rate consumer and its diagnostics (ENH-3656/ENH-3549); Codex runtime trigger and cutover (ENH-3549); rollout/other-host normalization (ENH-3532/ENH-3534); producer eligibility (ENH-3546).

## Backwards Compatibility

No new user-facing CLI command is required. A checkpoint or source-row identity migration may be needed; coordinate its append-only version with the epic's schema plan. A full `rebuild()` must keep producing the same rows as the incremental path.

## API/Interface

```python
# Sketch only; exact names decided at implementation.
def backfill_usage_incremental(db: Path | str, *, since_raw_event_id: int | None = None) -> int:
    """Derive transcript usage_events for raw_events newer than the high-water mark."""
```


## Session Log
- `/ll:capture-issue` - 2026-09-29T02:53:24 - `efa5da7e-d183-4626-be25-08b53ab75362.jsonl`
