---
id: ENH-3648
type: ENH
title: Survey token usage fields for OpenCode, Pi, Qwen, Gemini, OMP and Kimi Code
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T01:55:16Z'
parent: EPIC-3562
epic: EPIC-3562
labels:
- observability
- multi-host
relates_to:
- ENH-3534
- ENH-3544
- ENH-3546
- ENH-3532
blocks:
- ENH-3534
---

# ENH-3648: Survey token usage fields for OpenCode, Pi, Qwen, Gemini, OMP and Kimi Code

## Summary

Produce fixture-backed producer evidence for token usage on the six non-Claude, non-Codex production hosts, so ENH-3534 can implement ingestion against recorded contracts and ENH-3544's capability matrix can move entries off `unknown`. Split out of ENH-3534 (2026-09-28) so the survey is not held behind ENH-3534's `blocked_by` edges — the survey needs no code from ENH-3532 or ENH-3544. Claude Code is covered by ENH-3546 and Codex by BUG-3531/ENH-3532.

## Current Behavior

- `ctx_stats._compute_cache_rate_from_jsonl` documents that qwen/gemini/omp cache rates are unreachable because their normalizers strip `message.usage`.
- Payload shape differs by host (`session_store/sessions.py` "Payload rule (ENH-3420)"): `kimi-code` yields host-native records; `qwen`, `gemini`, `omp` yield Claude-shaped normalizer output with usage stripped; `opencode`, `pi` share the Claude loop.
- Fixtures exist under `scripts/tests/fixtures/{qwen,gemini,omp}/`; none exist for `opencode`, `pi` or `kimi-code`.
- No per-host record states field names, inclusive/exclusive cache semantics, request vs cumulative grain, or native identity.

## Expected Behavior

For each of `opencode`, `pi`, `qwen`, `gemini`, `omp`, `kimi-code`, record — with host CLI version and acquisition channel (live invocation output, on-disk transcript/session file):

1. Which usage fields exist and their names.
2. Input semantics: inclusive or exclusive of cached tokens; whether cache-write is reported; what an omitted field means.
3. Grain: per request, per turn, per invocation, or cumulative; reset behavior on resume/compaction.
4. Native identity usable as a source-event/request key (session ID, message/request ID, ordinal) and its namespace.
5. Whether reasoning tokens are folded into output.
6. Evidence class per metric/channel: `supported` (captured), `unsupported` (evidence of absence), or `unknown` (not investigated / could not capture). Absence of a sample is `unknown`, never `unsupported`.

Evidence lands as sanitized, versioned fixtures under `scripts/tests/fixtures/<host>/` plus a per-host README section, following the `fixtures/codex/README.md` pattern. If ENH-3544 has landed, the survey also updates that host's typed telemetry entries; otherwise the per-host findings table is the hand-off to ENH-3544/ENH-3534.

Hosts whose CLI is not installed or cannot be driven get `unknown` with the reason; the survey does not block on them.

## Scope Boundaries

- **In scope**: evidence capture, fixtures, per-host findings, and a recommendation per host (ingest / defer / unsupported).
- **Out of scope**: normalizers, ingestion, refresh/re-ingestion and reporting (ENH-3534); the capability vocabulary itself (ENH-3544); Claude (ENH-3546); Codex (ENH-3532).

## Program Design

Evidence-only; no production code ships here.

### Types

- Per-host findings row: `host`, `cli_version`, `channel` (`live` | `transcript`), `fields`, `input_semantics` (inclusive | exclusive | unknown), `cache_write` (reported | omitted | unknown), `grain` (request | turn | invocation | cumulative | unknown), `identity`, `reasoning_in_output`, `evidence_class` (`supported` | `unsupported` | `unknown`), `recommendation`.

### Signatures

- `normalize_host_usage(record: UsageReplayRecord, *, state: HostUsageState) -> list[UsageObservation]` — ENH-3534's consumer of these findings (not implemented here).
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing; the survey reads captured on-disk sessions through it to confirm what each host's parser currently strips.

### Call Path

- captured fixture → `iter_events` → payload inspection → findings table → ENH-3544 entries / ENH-3534 `normalize_host_usage`

## Integration Map

- `scripts/tests/fixtures/{opencode,pi,qwen,gemini,omp,kimi-code}/` — new or extended captures + README.
- `scripts/little_loops/host_runner.py` telemetry entries — only if ENH-3544 has landed.
- Findings recorded in this issue and linked from ENH-3534.

## Implementation Steps

1. For each host, capture one live invocation and one on-disk session containing at least one tool call and, where possible, a resume.
2. Sanitize and commit fixtures with version metadata; record findings in a per-host table here.
3. Recommend per host: implement in ENH-3534, split to its own issue (if the host's semantics are distinct enough), or record as unsupported/unknown.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium (mostly capture; depends on host CLI availability).
- **Risk**: Low — no production code.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] All six hosts have a findings row with CLI version, channel, fields, cache semantics, grain and identity — or an explicit `unknown` with the reason.
- [ ] Every `supported` claim is backed by a committed fixture; every `unsupported` claim cites evidence of absence.
- [ ] Each host has an ingestion recommendation, and any host needing its own implementation issue is filed and linked to ENH-3534.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
