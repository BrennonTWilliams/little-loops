---
id: ENH-3534
type: ENH
title: Shared infrastructure for remaining-host token usage ingestion
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:40Z'
labels:
- observability
- multi-host
relates_to:
- ENH-3528
- ENH-3543
- ENH-3546
- ENH-3549
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
---

# ENH-3534: Shared infrastructure for remaining-host token usage ingestion

## Summary

Maintain the shared replay dispatch and safe source refresh needed to ingest native usage from the six remaining production hosts. ENH-3648 owns the completed survey, ENH-3660–3665 own host evidence, and ENH-3671–3676 own host-specific normalization, runtime triggers, and stored readers. This issue can finish independently of any one host's credentials or producer contract. It does not certify eight-host coverage by itself.

## Current Behavior

- `usage_refresh.py` can safely replace verified stored source rows from available originals, and `_backfill_usage_events` dispatches assistant-message usage through `normalize_host_usage`.
- The shared dispatch qualifies Claude observations only. Codex uses its completed native path; Kimi native `usage.record` and the other hosts' differing usage shapes have no measured implementation yet.
- The current-session usage Stop hook and stored `ll-ctx-stats` cache-rate reader serve Claude and Codex only. ENH-3671–3676 own the corresponding host-specific paths.

## Expected Behavior

Provide a replay seam that lets each host-specific issue normalize its verified native records into `usage_events` without duplicating source refresh, attribution, derivation, or coverage policy. Host adapters may handle assistant `message.usage`, OpenCode `step-finish` tokens, Qwen `usageMetadata`, Gemini `tokens`, OMP `message.usage`, or Kimi `usage.record`; this issue does not assume one shape fits all.

The current shared contract consists of `UsageReplayRecord`, source/host/session-scoped `HostUsageState`, `normalize_host_usage` for assistant-message records, `refresh_raw_events`, and ENH-3651's derive checkpoint. ENH-3671–3676 consume those guarantees and may add separate native adapters. A host requiring a shared change updates this issue's contract and shared tests in coordination with its delivery issue; no other host's evidence becomes a hard dependency.

Only producer-verified observations with valid, complete canonical components can be `measured`. Partial, malformed, legacy, or unverified observations remain `unknown`; missing values are unavailable, never zero. A host's native metric/channel capability remains distinct from implemented ingestion.

### Upgrade and replay contract

Existing `raw_events` store normalized payloads, so previously stripped usage cannot be recovered by replay alone. The implemented refresh operation re-parses available verified originals; keep its attribution, position, idempotency, and source-cursor guarantees as host adapters arrive. When originals are gone, retain missing/unknown coverage and report the limitation; never synthesize tokens or certify legacy host attribution.

Use the completed ENH-3543 shared observation selector for reporting. No host-specific direct-sum bypass or inferred reconciliation is permitted.

## Integration Map

- `scripts/little_loops/session_store/writers.py`, `lifecycle.py`, and `usage_refresh.py`; `scripts/little_loops/cli/session.py` owns the shared refresh CLI. ENH-3671–3676 own host parsers, triggers, telemetry entries, and `ll-ctx-stats` integration.
- Tests: shared replay/refresh and backfill CLI tests, including an upgrade fixture whose persisted normalized payload lacks usage while its original still has it. Host-specific end-to-end fixtures belong to ENH-3671–3676.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium for shared replay/refresh hardening; host work is split.
- **Risk**: Medium — replacing stored source rows must preserve attribution and replay safety.

## Acceptance Criteria

- [ ] Shared replay dispatch accepts verified host/source/session state and labels surviving unproved assistant usage as unknown audit data; it never promotes a host merely because a payload resembles Claude usage. Host-native shapes are owned by ENH-3671–3676.
- [ ] An upgrade test starts with normalized raw rows missing usage, refreshes available originals, and rebuilds twice with stable totals and attribution. Missing originals remain unavailable with a diagnostic.
- [ ] Refresh and rebuild preserve live-only rows, source positions, verified host attribution, derive freshness, and idempotency; an interrupted refresh/rebuild leaves readers explicitly stale or unavailable until repaired.
- [ ] Shared reporting uses `select_usage_coverage`/`select_usage_observations`; unresolved overlap stays audit-only, and identical counts never establish request identity.
- [ ] ENH-3671–3676 carry host-specific parser, normalization, capability, trigger, reader, and end-to-end fixture gates; ENH-3534 can close while their evidence or implementation remains open.

## Scope Boundaries

- **In scope**: shared per-host dispatch, replay contracts, safe refresh/re-ingestion, and common coverage/attribution guarantees.
- **Prerequisites already done**: ENH-3648 (survey), ENH-3532 (`UsageReplayRecord`), ENH-3544 (capability vocabulary), and ENH-3543 (coverage selector).
- **Host delivery**: ENH-3671 (OpenCode), ENH-3672 (Pi), ENH-3673 (Qwen), ENH-3674 (Gemini), ENH-3675 (OMP), ENH-3676 (Kimi Code).
- **Out of scope**: pricing for non-Anthropic models; context-occupancy monitors for these hosts.

## Program Design

### Types

- Reuses `UsageReplayRecord` from ENH-3532. The shipped ENH-3532 Codex path is candidate-based rather than the proposed `UsageObservation`/`normalize_codex_usage` API; the current assistant-message path already defines `UsageObservation` in `writers.py`.
- `HostUsageState` binds a source, host and session for the assistant-message adapter. It holds no cumulative state until a host's grain and reset behavior are verified.

### Signatures

- `normalize_host_usage(record: UsageReplayRecord, *, state: HostUsageState) -> list[UsageObservation]` — current assistant-message dispatch uses the host on the replay record, never a caller-supplied host. It returns no observation for records without usage or for separate Codex/Kimi native paths. Only persisted Claude 2.1.284 contract evidence currently qualifies it as measured. ENH-3671–3676 may add host-specific adapters rather than forcing native records into this signature.

### Call Path

- `_backfill_usage_events` → `normalize_host_usage` → `usage_events` insert
- Host delivery issues connect stored normalized observations to the shared selector and reader; they do not introduce another direct transcript token parser.

## Verification Notes

Historical verdict before the host-delivery split: **VALID** for the former scope. Evidence-quote check was clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` was available. This verdict does not certify the revised shared-infrastructure scope.

Historical check, 2026-09-24: `_compute_cache_rate_from_jsonl` documented missing qwen/gemini/omp cache rates; `normalize_host_usage` and Codex rollout ingestion were then pending. The 2026-09-29 checkpoint below supersedes that implementation state.

## Implementation checkpoint (2026-09-29)

`session_store/usage_refresh.py` now has an explicit source-refresh entry point. It
re-parses supplied `SessionHandle` originals and replaces one source's normalized
`raw_events` inside a transaction only when the stored rows have verified
handle-based host attribution and have not been compacted. It skips missing,
unparseable, changing, mismatched, or field-dropping sources with a structured diagnostic; it
does not relabel legacy rows. The result states when callers must run `rebuild`
to re-derive usage and other cache rows. The focused upgrade test starts with a
stored normalized payload whose usage was removed, refreshes the available
source, rebuilds twice, and checks stable counts, attribution, and live-only
row preservation. The missing-original test keeps stored rows and yields no
invented usage.

After ENH-3651's v58 migration, replacement also deletes the selected
source's cursor, source-linked non-live usage rows, and its old usage search
entries in the same transaction. It clears the derive checkpoint so the next
incremental derive must replay from raw events. A reader sees the missing
source cursor as `unknown` until a writer re-establishes its tail proof.
Legacy usage rows without source links require a full `rebuild` before use.

The ENH-3648 survey leaves each of the six hosts with an incomplete producer
contract. ENH-3660 through ENH-3665 own those evidence gaps; ENH-3671 through
ENH-3676 own the host-specific implementation. No remaining-host normalizer is
qualified as measured in this checkpoint. The
`ll-session refresh --host ... --session-id ...|--all [--rebuild]` command now
selects only verified stored originals and reports a skip for each unavailable
or unsafe source. A refresh commits raw replacement before the
separate rebuild call, so a failed or interrupted rebuild must be retried.

The shared assistant-message dispatch is now wired into `_backfill_usage_events`
with a source/host/session-scoped `HostUsageState`. It preserves Claude's
ingest-time measured contract and duplicate handling. A surviving usage block
from a different host is retained only as an unknown audit row. Codex still
uses its closed-span candidate path, and Kimi's native records do not pass
through this adapter. No six-host parser or metric normalization was added:
the survey did not prove the input/cache semantics needed to derive disjoint
components. ENH-3660–ENH-3665 remain the owners of those contracts, and the
matching host delivery issues remain blocked on their respective producer contracts.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:30 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:10 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
