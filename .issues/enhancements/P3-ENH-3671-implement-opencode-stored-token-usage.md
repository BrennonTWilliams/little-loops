---
id: ENH-3671
type: ENH
title: Implement OpenCode stored token usage
priority: P3
status: blocked
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:24:20Z'
parent: EPIC-3562
labels:
- observability
- multi-host
- usage-ingestion
blocked_by:
- ENH-3660
---

# ENH-3671: Implement OpenCode stored token usage

## Summary

Deliver OpenCode token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3660 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns OpenCode parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

Live and stored 1.1.53 step-finish parts expose tokens and matching sessionID/part.id. Cache values in the captures are zero, so normalized input, reasoning, and replay identity remain unproved. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Read native step-finish tokens; use the proved part identity to avoid counting matching live/stored copies or retries twice. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3660 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3660 proves partial native support, store the proved components with explicit provenance and null unsupported components; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

The shared seam is ENH-3534's existing `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. Consume it without changing its replay guarantees. If this host requires a shared seam change, implement it in coordination with ENH-3534 and extend shared tests; the other hosts do not become hard blockers.

## Program Design

- **Producer input**: stored step-finish parts with tokens and matching live part IDs; ENH-3660 supplies the versioned field and component contract.
- **Replay identity**: (sessionID, part.id) only after ENH-3660 proves uniqueness across retries and compaction. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Stored path**: adapt the native record at the session parser or replay-writer seam into `usage_events` with disjoint nullable components and durable source attribution. Reuse ENH-3534's refresh and ENH-3651's incremental derive checkpoint.
- **Current session**: prove an after-usage host lifecycle event and source path before extending `usage_stop.handle`/`backfill_worker._run_usage_trigger` or choosing a host-specific equivalent. The worker commits an as-of boundary after derive.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser entry point; preserve native usage needed by this host.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing replay writer; extend through a host-specific normalizer when the contract is proved.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Native session file → `iter_events` → `raw_events` → `_backfill_usage_events` → `usage_events` → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Native after-usage lifecycle event → adapter → `_run_usage_trigger` or proved equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session parser/normalizer and replay writer under scripts/little_loops/session_store/; coordinate shared seam changes with ENH-3534.
- OpenCode lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/opencode/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] ENH-3660 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] A parser-replayable real fixture passes through iter_events, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] A captured OpenCode lifecycle event fires after current-session usage is available and drives the real adapter → worker → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped worker cannot appear fresh.
- [ ] This issue owns the OpenCode direct-fallback disposition. `ll-ctx-stats` switches to the stored reader only after the end-to-end path passes, or emits an explicit unavailable diagnostic after proved native absence. Missing store, partial components, and unresolved overlap never produce a fabricated canonical rate; audit subtotals remain labeled.
- [ ] The typed telemetry map and epic ledger record supported, unsupported, or unknown for each metric/channel separately from ingestion status. Documentation and tests cover the host's actual native shape.

## Scope Boundaries

- **In scope**: OpenCode native usage ingestion, request identity, current-session trigger, freshness-qualified stored read, capability entries, and fixture-backed tests.
- **Out of scope**: non-Anthropic pricing, non-Claude context occupancy, and other hosts' producer contracts.

## Impact

- **Priority**: P3 — closes one of the epic's six remaining host paths.
- **Effort**: Medium — native parser, lifecycle, and reader integration.
- **Risk**: Medium — silent double counting or stale usage if identity or trigger timing is wrong.
- **Breaking Change**: No CLI option change expected; a previously unverified fallback figure may become explicitly unavailable until stored evidence is current.

## Status

**Blocked** | Created: 2026-09-30 | Priority: P3
