---
id: ENH-3534
type: ENH
title: Token usage ingestion for Qwen, Gemini, OMP and remaining hosts
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:40Z'
labels:
- observability
- multi-host
blocked_by:
- ENH-3532
- ENH-3528
---

# ENH-3534: Token usage ingestion for Qwen, Gemini, OMP and remaining hosts

## Summary

Add native token-usage ingestion for the remaining runtime hosts that expose it (Qwen, Gemini, OMP, and any others whose transcripts carry usage), following the normalization, provenance, and coverage contract established for Codex in ENH-3532. Deferred from ENH-3528.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl` notes that qwen/gemini/omp cache rates are unreachable because their normalizers strip `message.usage`.
- Only Claude (assistant `message.usage`) and Codex (live, plus historical via ENH-3532) usage reach `usage_events`.

## Expected Behavior

For each host whose transcripts expose usage, usage reaches `usage_events` as `measured` observations under the canonical disjoint input/cache contract; hosts without usage remain `unavailable`, never zero.

## Integration Map

- `scripts/little_loops/session_store/` per-host readers/normalizers, `writers.py`; `cli/ctx_stats.py`; `host_runner.py` runtime telemetry entries.

## Impact

- **Priority**: P3.
- **Effort**: Medium per host; can be split per host after the survey.
- **Risk**: Medium — each host has its own accounting semantics.

## Acceptance Criteria

- [ ] Per host: a fixture-backed survey records which usage fields exist, their inclusive/exclusive semantics, and request vs cumulative grain; hosts with no usage are marked unsupported in the runtime telemetry capability map (ENH-3528).
- [ ] Each supported host has a normalizer with the same fixture categories as ENH-3532 (repeats, resets, partial records, multiple sessions).
- [ ] The normalizers stop stripping `message.usage` where it is needed, without changing other normalized output.
- [ ] Ingestion and rebuild are idempotent and preserve live-only rows.

## Scope Boundaries

- **In scope**: per-host usage-field survey, normalizers for hosts that expose usage, marking the rest unsupported in the runtime telemetry map.
- **Prerequisite**: ENH-3532 (normalization/coverage contract and fixture categories).
- **Out of scope**: pricing for non-Anthropic models; context-occupancy monitors for these hosts.

## Program Design

### Types

- Reuses `UsageObservation` from ENH-3532.

### Signatures

- `normalize_host_usage(host: str, event: dict[str, Any]) -> list[UsageObservation]` — dispatches to a per-host normalizer; returns an empty list for events without usage.

### Call Path

- `_backfill_usage_events` → `normalize_host_usage` → `usage_events` insert
- `_compute_cache_rate_from_jsonl` reads the same normalized components.

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `_compute_cache_rate_from_jsonl` (`ctx_stats.py` L402) docstring confirms qwen/gemini/omp cache rates are unreachable because normalizers strip `message.usage`; `normalize_host_usage` not yet present, as proposed. Blocker ENH-3532 is open.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T01:05:30 - `af4614fc-00c0-4ee9-995a-e89a43f1523c.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:10 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
