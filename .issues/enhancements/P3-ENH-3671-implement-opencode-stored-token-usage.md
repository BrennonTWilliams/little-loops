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

Live and stored 1.1.53 step-finish parts expose tokens and matching sessionID/part.id. Cache values in the committed captures are zero, so normalized input, reasoning, and replay identity remain unproved. The installed 1.1.53 CLI stores separate session, message, and part JSON files under its data storage tree; current little-loops discovery instead looks for `~/.opencode/projects/*.jsonl` and `parse_opencode_transcript` assumes Claude-shaped lines. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Discover real OpenCode sessions through their native storage tree and read their step-finish part files. Use the session record's project directory for discovery and each part's native `sessionID`, `messageID`, and `id` for attribution and identity; avoid an unnecessary full join through every message file. Use the proved part identity to avoid counting matching live/stored copies or retries twice. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3660 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3660 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns any extension needed for its native source layout, source refresh, incremental derive, freshness cursor, or runtime trigger, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Program Design

- **Producer input**: the real session/message/part JSON storage tree, including stored step-finish parts with tokens and matching live part IDs; ENH-3660 supplies the versioned layout, field, and component contract. The reduced JSONL excerpt is contract evidence, not the ingest source.
- **Replay identity**: (sessionID, part.id) only after ENH-3660 proves uniqueness across retries and compaction. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Stored path**: implement native-tree discovery and a source adapter that assigns stable `source_path`/position and verified session attribution to each part before writing `raw_events` and `usage_events`. Extend ENH-3534's refresh baseline and ENH-3651's derive checkpoint to track the native files without treating a concatenated JSONL export as the original source.
- **Current session**: use the evidence issue's event and source-write timing candidate, then prove a real trigger after usage is persisted. Extend `usage_stop.handle`/`backfill_worker._run_usage_trigger` or a host-specific equivalent. A read-time refresh is acceptable only when tested against a real post-write source and committed as-of boundary; a manually invoked worker alone does not prove current-session freshness.
- **Reader**: `ll-ctx-stats` selects the verified host/session through `select_usage_coverage`, checks `usage_source_freshness`, and exposes a canonical rate only for qualified non-overlapping components.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — current single-file entry point; adapt `SessionHandle`/discovery and parsing so a real OpenCode session tree yields its usage-bearing parts without assuming `~/.opencode/projects/*.jsonl`.
- `_backfill_usage_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int` — existing replay writer; extend through a host-specific normalizer when the contract is proved.
- `_run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int` — existing Claude/Codex worker path; reuse only after this host's event timing and source are proved.

### Call Path

- Native session/message/part storage tree → OpenCode discovery and part adapter → `raw_events` → `_backfill_usage_events` → `usage_events` → `select_usage_coverage` → `_compute_cache_rate_from_usage` → `ll-ctx-stats`.
- Proved post-write host event or read-time refresh → host adapter/worker or tested equivalent → incremental derive checkpoint → reader freshness check.

## Integration Map

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; this issue owns any required extension to `refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, and shared tests. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Coordinate `session_store/writers.py::host_layout_for`, `session_store/sessions.py` discovery, `user_messages.py` source lookup, and `test_session_reader_no_host_roots_gate.py` so they describe one real OpenCode root. Define how the current `(source_path, line_no)` raw-event dedup key and file-based freshness cursor map to individual part files or a stable session manifest.
- OpenCode lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/opencode/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] ENH-3660 records a versioned, sanitized producer contract for every implemented metric/channel: fields, inclusivity, omissions, request grain/reset behavior, reasoning/output relation, and stable source identity; unresolved items remain explicit unknowns.
- [ ] A parser-replayable fixture in the real native source layout passes through discovery/parser, raw_events, usage_events, and the shared selector. It preserves the native usage fields needed for this host and does not change unrelated normalized content; a reduced JSONL excerpt alone cannot satisfy this gate.
- [ ] Real-tree discovery selects the correct project/session; stable part identity and source position survive resume, part rewrite, repeated refresh, incremental derive, and full rebuild. A changed or missing native file makes freshness stale/unknown rather than retaining a false fresh verdict.
- [ ] Proven repeated, resumed, live/stored, and copied records are counted once per native request. Full rebuild, incremental derive, and repeated refresh of available originals agree; missing originals or unverified attribution never manufacture measured usage.
- [ ] A proved OpenCode current-session trigger runs after native usage is persisted and drives the real adapter or read-time equivalent → ingest → incremental derive → stored read path. The selected host/session has a committed as-of/freshness proof; a failed or skipped refresh cannot appear fresh.
- [ ] A row with a proved component but a null evidence-backed unsupported canonical component remains `unknown` and audit-only under the current row-level provenance contract; missing dependent totals/rates stay unavailable. Any component-level measured exception requires an explicit tested contract and epic ledger revision.
- [ ] A partial host may close when proved components are stored with replay and freshness qualification as audit-only rows, the selected reader emits an explicit unavailable diagnostic for dependent canonical figures, and the epic ledger records that terminal partial disposition; in-scope unknowns still block closure.
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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Shared usage seams (`refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, `_run_usage_trigger` dispatch, shared tests): the first delivery issue among ENH-3671/3672/3673 to land a change owns it; later hosts extend through host-keyed dispatch and rebase. Host-specific adapter work (OpenCode storage tree) stays here.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:29 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
