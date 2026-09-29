---
id: ENH-3534
type: ENH
title: Token usage ingestion for Qwen, Gemini, OMP and remaining hosts
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
blocked_by:
- ENH-3532
- ENH-3544
- ENH-3648
relates_to:
- ENH-3528
- ENH-3543
- ENH-3546
- ENH-3549
---

# ENH-3534: Token usage ingestion for Qwen, Gemini, OMP and remaining hosts

## Summary

Add native token-usage ingestion for the remaining runtime hosts that expose it (Qwen, Gemini, OMP, and any others whose transcripts carry usage), following ENH-3532's observation/replay contract, ENH-3528's provenance reporting, and ENH-3543's shared coverage policy. ENH-3544 owns the capability vocabulary. Deferred from ENH-3528.

**Split 2026-09-28:** the six-host producer survey moved to ENH-3648 (unblocked) so evidence capture is not held behind this issue's `blocked_by` edges. This issue keeps the shared per-host dispatch, the refresh/re-ingestion operation, and normalizers for the hosts ENH-3648 recommends. Hosts whose semantics ENH-3648 finds distinct enough get their own issue; this issue then owns only the shared infrastructure plus the remaining hosts.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl` notes that qwen/gemini/omp cache rates are unreachable because their normalizers strip `message.usage`.
- The backfill recognizes assistant `message.usage`; Codex live usage is captured separately. Codex historical ingestion is pending in ENH-3532. Other-host usage must be qualified by its own producer contract, not by a Claude-shaped payload.

## Expected Behavior

Usage reaches `usage_events` under the canonical disjoint input/cache contract. Only producer-verified observations with valid, complete components become `measured`; partial, malformed, legacy or unverified observations remain `unknown`. Missing observations are unavailable, never zero or implicitly estimated.

Implement against ENH-3648's per-host findings (fields, grain, identity, cache semantics, version/channel evidence). Claude and Codex have dedicated issues (ENH-3546, ENH-3532). In ENH-3544's map, `unsupported` requires evidence that the metric/channel is unavailable; an uninvestigated path is `unknown`. Native capability does not imply implemented ingestion.

### Upgrade and replay contract

Existing `raw_events` store normalized payloads, so previously stripped usage cannot be recovered by replay alone. `_backfill_raw_events` uses `INSERT OR IGNORE` for existing path/line keys. Before implementation, define an explicit, idempotent refresh/re-ingestion operation for available original sources, including attribution/position preservation and safe replacement. When originals are gone, retain missing/unknown coverage and report the limitation; never synthesize tokens. Refresh must not blanket-certify legacy host attribution.

Use the existing shared observation selector for reporting; ENH-3543 owns reconciliation. This issue can ingest/report conservative unresolved observations before that selector enhancement lands. No host-specific direct-sum bypass or inferred reconciliation is permitted.

## Integration Map

- `scripts/little_loops/session_store/` per-host readers/normalizers, `writers.py`, `lifecycle.py` and refresh CLI wiring; `host_runner.py` runtime telemetry entries; `cli/ctx_stats.py` consumes stored observations via ENH-3549.
- Tests: per-host normalizer fixtures, `test_session_store_writers.py`, `test_session_store_lifecycle.py`, relevant backfill CLI tests, `test_cli_ctx_stats.py`, and capability-map tests. Include an upgrade fixture whose persisted normalized payload lacks usage while the source still has it.

## Impact

- **Priority**: P3.
- **Effort**: Medium per host; can be split per host after the survey.
- **Risk**: Medium — each host has its own accounting semantics.

## Acceptance Criteria

- [ ] Every host ENH-3648 recommends for ingestion has a normalizer or a linked per-host issue; only verified complete observations are measured.
- [ ] An upgrade test starts with already-normalized raw rows missing usage, refreshes from available originals, then rebuilds twice with stable totals and attribution. Missing originals remain unavailable with a diagnostic.
- [ ] Reporting uses the shared selector and remains explicitly unresolved until verified overlap reconciliation exists; identical counts never establish identity.

- [ ] ENH-3544 capability entries for implemented hosts reflect ENH-3648's evidence, distinguishing proven unsupported paths from unknown ones, separately from ingestion implementation.
- [ ] Each supported host has a normalizer with the same fixture categories as ENH-3532 (repeats, resets, partial records, multiple sessions).
- [ ] The normalizers stop stripping `message.usage` where it is needed, without changing other normalized output.
- [ ] Ingestion and rebuild are idempotent and preserve live-only rows.

## Scope Boundaries

- **In scope**: shared per-host dispatch, the refresh/re-ingestion operation, normalizers for hosts that expose usage, updating capability entries for implemented hosts.
- **Prerequisites**: ENH-3648 (survey), ENH-3532 (normalization/replay contract, `UsageReplayRecord`, fixture categories), ENH-3544 (capability vocabulary). ENH-3543 owns coverage selection but is not required to ingest conservatively qualified rows.
- **Out of scope**: pricing for non-Anthropic models; context-occupancy monitors for these hosts.

## Program Design

### Types

- Reuses `UsageObservation` and `UsageReplayRecord` from ENH-3532.
- `HostUsageState` — per-host, per-session bookkeeping (the generalization of ENH-3532's `CodexUsageState`); holds cumulative state only for hosts ENH-3648 finds cumulative.

### Signatures

- `normalize_host_usage(record: UsageReplayRecord, *, state: HostUsageState) -> list[UsageObservation]` — dispatches on `record`'s verified host to a per-host normalizer; returns an empty list for records without usage. Same shape as ENH-3532's `normalize_codex_usage(record, *, state)` so direct-file and database replay share one adapter; per-host state carries only key/span bookkeeping unless the host's grain is cumulative (ENH-3648 finding). Takes the verified host from the record, never a caller-supplied string.

### Call Path

- `_backfill_usage_events` → `normalize_host_usage` → `usage_events` insert
- ENH-3549 cache-rate reporting reads stored normalized observations through `select_usage_observations`; it does not introduce another token parser.

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_compute_cache_rate_from_jsonl` (`ctx_stats.py` L402) docstring confirms qwen/gemini/omp cache rates are unreachable because normalizers strip `message.usage`; `normalize_host_usage` not yet present, as proposed. Blocker ENH-3532 is open.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:30 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:10 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
