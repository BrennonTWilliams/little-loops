---
id: ENH-3676
type: ENH
title: Implement Kimi Code stored token usage
priority: P3
status: blocked
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:24:22Z'
parent: EPIC-3562
labels:
- observability
- multi-host
- usage-ingestion
blocked_by:
- ENH-3665
---

# ENH-3676: Implement Kimi Code stored token usage

## Summary

Deliver Kimi Code token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3665 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns Kimi Code parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

Real 0.30.0 stored usage.record entries coexist with matching context.append_loop_event copies. Input components and a durable request key remain unproved; the sampled live stream had no usage. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Read native usage.record, exclude duplicate context.append_loop_event copies, and use a proved native or replay-safe source-position key. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3665 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3665 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns any extension needed for its native source layout, source refresh, incremental derive, freshness cursor, or runtime trigger, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Program Design

- **Producer input**: stored usage.record rather than its context.append_loop_event copy; ENH-3665 supplies the versioned field and component contract.
- **Replay identity**: the ENH-3665 proved native or replay-safe source-position key. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Stored path**: adapt the native record at the session parser or replay-writer seam into `usage_events` with disjoint nullable components and durable source attribution. Reuse ENH-3534's refresh and ENH-3651's incremental derive checkpoint.
- **Current session**: use the evidence issue's event and source-write timing candidate, then prove a real trigger after usage is persisted. Extend `usage_stop.handle`/`backfill_worker._run_usage_trigger` or a host-specific equivalent. A read-time refresh is acceptable only when tested against a real post-write source and committed as-of boundary; a manually invoked worker alone does not prove current-session freshness.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser entry point; preserve native usage needed by this host.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing replay writer; extend through a host-specific normalizer when the contract is proved.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Verified native source layout → host discovery/parser adapter (`iter_events` where applicable) → `raw_events` → `_backfill_usage_events` → `usage_events` → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Proved post-write host event or read-time refresh → host adapter/worker or tested equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; this issue owns any required extension to `refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, and shared tests. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Kimi Code lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/kimi-code/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] ENH-3665 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] A parser-replayable fixture in the real native source layout passes through discovery/parser, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content; a reduced JSONL excerpt alone cannot satisfy this gate.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] A proved Kimi Code current-session trigger runs after native usage is persisted and drives the real adapter or read-time equivalent → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped refresh cannot appear fresh.
- [ ] A row with a proved component but a null evidence-backed unsupported canonical component remains `unknown` and audit-only under the current row-level provenance contract; missing dependent totals/rates stay unavailable. Any component-level measured exception requires an explicit tested contract and epic ledger revision.
- [ ] A partial host may close when proved components are stored with replay and freshness qualification as audit-only rows, the selected reader emits an explicit unavailable diagnostic for dependent canonical figures, and the epic ledger records that terminal partial disposition; in-scope unknowns still block closure.
- [ ] This issue owns the Kimi Code direct-fallback disposition. `ll-ctx-stats` switches to the stored reader only after the end-to-end path passes, or emits an explicit unavailable diagnostic after proved native absence. Missing store, partial components, and unresolved overlap never produce a fabricated canonical rate; audit subtotals remain labeled.
- [ ] The typed telemetry map and epic ledger record supported, unsupported, or unknown for each metric/channel separately from ingestion status. Documentation and tests cover the host's actual native shape.

## Scope Boundaries

- **In scope**: Kimi Code native usage ingestion, request identity, current-session trigger, freshness-qualified stored read, capability entries, and fixture-backed tests.
- **Out of scope**: non-Anthropic pricing, non-Claude context occupancy, and other hosts' producer contracts.

## Impact

- **Priority**: P3 — closes one of the epic's six remaining host paths.
- **Effort**: Medium — native parser, lifecycle, and reader integration.
- **Risk**: Medium — silent double counting or stale usage if identity or trigger timing is wrong.
- **Breaking Change**: No CLI option change expected; a previously unverified fallback figure may become explicitly unavailable until stored evidence is current.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Shared usage seams (`refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, `usage_stop.handle`/`_run_usage_trigger` dispatch, shared tests): the first delivery issue among ENH-3671..ENH-3676 to land a change owns it; later hosts extend through host-keyed dispatch and rebase. The "this issue owns any required extension" line applies only to the first lander. Host-specific adapter work stays in this issue.

## Status

**Blocked** | Created: 2026-09-30 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:03 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
