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

If ENH-3660 proves native absence for an in-scope metric/channel, record that verdict in the typed map and epic ledger, then cancel this implementation issue if no supported ingestion path remains. If access or semantics stay unknown, keep this issue blocked and the epic incomplete; do not relabel unknown as unsupported.

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
- [ ] ll-ctx-stats uses the stored reader for OpenCode only after that end-to-end path passes. The direct fallback retires only with a proven replacement or evidence-backed unavailable verdict; missing store, partial components, and unresolved overlap produce explicit unavailable diagnostics and audit subtotals rather than a canonical rate.
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
