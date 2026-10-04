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
relates_to:
- ENH-3723
---

# ENH-3671: Implement OpenCode stored token usage

## Summary

Deliver OpenCode token usage from a proved native source to stored, normalized observations and a freshness-qualified session reader. ENH-3660 owns the producer contract; ENH-3534 owns shared replay and refresh infrastructure. This issue owns OpenCode parsing, identity, normalization, current-session trigger, capability entries, and reader cutover. It has no dependency on another host's evidence.

## Current Behavior

Live and stored 1.1.53 step-finish parts expose tokens and matching sessionID/part.id. Cache values in the committed captures are zero, so normalized input, reasoning, and replay identity remain unproved. The installed 1.1.53 CLI stores separate session, message, and part JSON files under its data storage tree; current little-loops discovery instead looks for `~/.opencode/projects/*.jsonl` and `parse_opencode_transcript` assumes Claude-shaped lines. The shared usage Stop worker and ll-ctx-stats stored cache-rate path currently serve Claude and Codex only. Other hosts retain the direct transcript fallback where it applies.

## Expected Behavior

Discover real OpenCode sessions through their native storage tree and read their step-finish part files. Use the session record's project directory for discovery and each part's native `sessionID`, `messageID`, and `id` for attribution and identity; avoid an unnecessary full join through every message file. Use the proved part identity to avoid counting matching live/stored copies or retries twice. Derive disjoint input, cache-read, cache-creation, and output components only where ENH-3660 proves the semantics. A supported native field is not automatically a measured stored observation. Keep unproved components null/unknown; do not infer zero, request identity, or non-overlap from matching counts. Use the shared coverage selector and verified host/session identity for canonical reporting.

If ENH-3660 proves partial native support, store the proved components with null evidence-backed unsupported components as `unknown`, audit-only rows under the current row-level provenance contract; canonical totals/rates that require missing components stay unavailable. If native absence is proved for every in-scope path, this issue still owns the direct-fallback disposition and explicit unavailable diagnostic; mark it done after that work, or cancel only if no change remains. An in-scope unknown keeps this issue blocked and the epic incomplete. If no after-usage event exists, prove another current-session trigger or keep this issue open for an explicit epic scope decision.

ENH-3534 is done and supplies the baseline `UsageReplayRecord`, `HostUsageState`, `normalize_host_usage` where applicable, `refresh_raw_events`, and derive checkpoint contract. This delivery issue owns its native adapter and required integration, coordinating shared source refresh, incremental derive, freshness, and trigger changes under EPIC-3562 § Shared Delivery Ownership, with shared regression tests. Preserve the baseline replay guarantees; no other host's evidence becomes a hard blocker.

## Runtime Qualification and Cutover Gate

Qualify each observation using the runtime provider and source/CLI version from the evidence issue's verified native source. Match the captured contract exactly or apply its specifically evidenced compatibility policy. Absent/unmatched provider/version or unproved attribution/identity remains audit-only with a visible reason and unavailable dependent canonical figures. A broad typed host capability never substitutes for this check.

Persist the ingest-time contract reference, provider/version evidence and qualification disposition on `raw_events`, using existing metadata where sufficient, so incremental derive and rebuild make the same decision. A later CLI upgrade or provider configuration must not promote old unknowns; requalification requires new source evidence and an explicit tested operation.

ENH-3723 is linked through `relates_to` and is required before reader cutover/closeout. There is no whole-issue scheduling edge to it, so native capture, parser and adapter development can proceed before that shared gate lands. Before cutover, add this host's qualified/partial/mismatch rows to its shared source/snapshot/session-reader matrix. The only hard evidence blocker remains this host's matching ENH-3660–3665 issue.

## Program Design

- **Producer input**: the real session/message/part JSON storage tree, including stored step-finish parts with tokens and matching live part IDs; ENH-3660 supplies the versioned layout, field, and component contract. The reduced JSONL excerpt is contract evidence, not the ingest source.
- **Replay identity**: (sessionID, part.id) only after ENH-3660 proves uniqueness across retries and compaction. The key is scoped by verified host and session and survives full rebuild; copied or conflicting records remain unknown until resolved.
- **Mutation policy**: `_preserves_fields` currently rejects changed existing values; do not assume monotonic refresh accepts final/revised part counters. Implement evidence-backed part replacement with stable native identity, transactional derived replacement, and freshness recovery. Invalidate an observation only for a proved authoritative retraction within a present, valid native source. A missing, empty, compacted, retention-pruned or inaccessible source does not retract consumption: retain committed historical observations and their ingest-time qualification, emit a diagnostic, and leave current-source freshness stale/unknown without advancing its as-of proof. Do not convert source loss into zero usage. If ENH-3660 cannot distinguish retraction from disappearance, provide no deletion-invalidation path; no tombstone subsystem is required.
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

- Session discovery/parser/normalizer and replay writer under scripts/little_loops/session_store/; coordinate extensions to `refresh_usage_source`, `_derive_usage_incremental_conn`, `usage_source_freshness`, and shared tests under EPIC-3562 § Shared Delivery Ownership; ENH-3723 owns shared canonical eligibility. Verify append, overwrite, rotation, or file-tree mutation behavior against the real native source before reusing a cursor.
- Coordinate `session_store/writers.py::host_layout_for`, `session_store/sessions.py` discovery, `user_messages.py` source lookup, and `test_session_reader_no_host_roots_gate.py` so they describe one real OpenCode root. Define how the current `(source_path, line_no)` raw-event dedup key and file-based freshness cursor map to individual part files or a stable session manifest.
- OpenCode lifecycle adapter and scripts/little_loops/hooks/usage_stop.py or another proved after-usage trigger; scripts/little_loops/cli/backfill_worker.py and incremental derivation.
- scripts/little_loops/cli/ctx_stats.py and scripts/little_loops/history_reader/usage.py shared selection; scripts/little_loops/host_runner.py typed telemetry entries.
- Real versioned fixtures and contract notes under scripts/tests/fixtures/opencode/; parser, replay, hook-worker, reader, and capability tests; update the CLI/host compatibility documentation.

## Acceptance Criteria

- [ ] An ordered native-tree test writes a partial usage part, finalizes/revises its counters, adds another part, and replaces a part, refreshing multiple times at each stage. Proved replacement is counted once at its latest valid value. Full rebuild, incremental derive and repeated refresh agree on counts and identity. If ENH-3660 proves an authoritative retraction signal, its fixture invalidates only that observation transactionally; otherwise retain recorded usage after deletion/disappearance and mark current-source freshness stale/unknown.
- [ ] Missing, empty, unreadable, retention-pruned and compacted source cases preserve committed historical usage and its qualification, expose a diagnostic, and do not advance the as-of proof. Current-source freshness/rates become stale or unavailable, never a fresh zero. Rebuild from retained raw evidence and repeated refresh do not erase real consumption merely because its original source vanished.
- [ ] A malformed/in-progress part write or failed derive makes freshness stale/unknown without exposing a false canonical value. After a valid write and successful refresh, qualification/freshness recover and the selected reader shows the corrected counts; `_preserves_fields` cannot leave a legitimate revised part permanently unknown.
- [ ] Runtime matching, unmatched provider, absent provider/version, unproved version, and unproved identity fixtures enforce the evidence-backed qualification policy. Unsupported versions/providers cannot inherit a measured host-level verdict; diagnostics explain audit-only/unavailable results.
- [ ] Ingest-time qualification evidence survives on `raw_events`; incremental derive, full rebuild, and later CLI/provider changes produce the same qualified or unknown disposition without promoting old rows.
- [ ] Before reader cutover/closeout, ENH-3723's selected eligibility policy and this host's source/snapshot/session-reader parity cases pass, including partial/mismatch rows and any documented stricter measured-only rate rule.
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

## Implementation Steps

1. Consume ENH-3660's provider/version-qualified native contract, real layout, identity and source-write timing evidence.
2. Implement the native adapter and durable ingest-time qualification; coordinate shared seams under the epic ownership rule.
3. Prove replay/update behavior, incremental/full parity, a real current-session trigger and freshness recovery.
4. Add this host's ENH-3723 qualification matrix cases; cut over the reader only after its gate passes, or record the evidence-backed unavailable/partial disposition.

## Impact

- **Priority**: P3 — closes one of the epic's six remaining host paths.
- **Effort**: Medium — native parser, lifecycle, and reader integration.
- **Risk**: Medium — silent double counting or stale usage if identity or trigger timing is wrong.
- **Breaking Change**: No CLI option change expected; a previously unverified fallback figure may become explicitly unavailable until stored evidence is current.

## Status

**Blocked** | Created: 2026-09-30 | Priority: P3

---

## Scope Boundary

**Coordination rule (2026-10-03):** EPIC-3562 § Shared Delivery Ownership governs all six delivery issues (ENH-3671–3676). The first lander owns the shared refresh/derive/freshness/trigger extension; later hosts extend the host-keyed dispatch and rebase. ENH-3723 owns shared canonical eligibility. Host-specific adapter work stays here.


## Session Log

- Pre-implementation epic review - 2026-10-04 - Replaced ambiguous delete-equals-invalidate wording with evidence-backed replacement/retraction and conservative source-loss handling, preserving the completed refresh baseline. Added source-loss/rebuild/freshness controls; no retraction machinery is required without native evidence.

- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:29 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
