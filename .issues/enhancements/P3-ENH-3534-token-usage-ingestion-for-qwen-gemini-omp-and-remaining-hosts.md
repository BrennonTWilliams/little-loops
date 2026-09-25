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
relates_to:
- ENH-3528
- ENH-3543
- ENH-3546
- ENH-3549
---

# ENH-3534: Token usage ingestion for Qwen, Gemini, OMP and remaining hosts

## Summary

Add native token-usage ingestion for the remaining runtime hosts that expose it (Qwen, Gemini, OMP, and any others whose transcripts carry usage), following ENH-3532's observation/replay contract, ENH-3528's provenance reporting, and ENH-3543's shared coverage policy. ENH-3544 owns the capability vocabulary. Deferred from ENH-3528.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl` notes that qwen/gemini/omp cache rates are unreachable because their normalizers strip `message.usage`.
- The backfill recognizes assistant `message.usage`; Codex live usage is captured separately. Codex historical ingestion is pending in ENH-3532. Other-host usage must be qualified by its own producer contract, not by a Claude-shaped payload.

## Expected Behavior

Usage reaches `usage_events` under the canonical disjoint input/cache contract. Only producer-verified observations with valid, complete components become `measured`; partial, malformed, legacy or unverified observations remain `unknown`. Missing observations are unavailable, never zero or implicitly estimated.

Survey every production runtime host: `claude-code`, `codex`, `opencode`, `pi`, `qwen`, `gemini`, `omp`, `kimi-code`. Claude and Codex reference their dedicated issues; this issue owns the other six. Record host/version/channel evidence, fields, grain, identity, and cache semantics. In ENH-3544's map, `unsupported` requires evidence that the metric/channel is unavailable; an uninvestigated path is `unknown`. Native capability does not imply implemented ingestion. Survey first and split per-host implementation only where the findings justify it.

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

- [ ] The survey covers all eight production hosts with explicit owners and producer/version/channel evidence; only verified complete observations are measured.
- [ ] An upgrade test starts with already-normalized raw rows missing usage, refreshes from available originals, then rebuilds twice with stable totals and attribution. Missing originals remain unavailable with a diagnostic.
- [ ] Reporting uses the shared selector and remains explicitly unresolved until verified overlap reconciliation exists; identical counts never establish identity.

- [ ] Per host: a fixture-backed survey records which usage fields exist, their inclusive/exclusive semantics, and request vs cumulative grain; ENH-3544 capability entries distinguish proven unsupported paths from unknown/uninvestigated ones, separately from ingestion implementation.
- [ ] Each supported host has a normalizer with the same fixture categories as ENH-3532 (repeats, resets, partial records, multiple sessions).
- [ ] The normalizers stop stripping `message.usage` where it is needed, without changing other normalized output.
- [ ] Ingestion and rebuild are idempotent and preserve live-only rows.

## Scope Boundaries

- **In scope**: per-host usage-field survey, normalizers for hosts that expose usage, recording supported/unsupported/unknown capability evidence in the runtime map.
- **Prerequisites**: ENH-3532 (normalization/replay contract and fixture categories), ENH-3544 (capability vocabulary). ENH-3543 owns coverage selection but is not required to ingest conservatively qualified rows; the survey can start before prerequisites finish.
- **Out of scope**: pricing for non-Anthropic models; context-occupancy monitors for these hosts.

## Program Design

### Types

- Reuses `UsageObservation` from ENH-3532.

### Signatures

- `normalize_host_usage(host: str, event: dict[str, Any]) -> list[UsageObservation]` — dispatches to a per-host normalizer; returns an empty list for events without usage.

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
