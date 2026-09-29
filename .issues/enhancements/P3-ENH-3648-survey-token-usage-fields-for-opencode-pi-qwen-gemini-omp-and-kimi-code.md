---
id: ENH-3648
type: ENH
title: Survey token usage fields for OpenCode, Pi, Qwen, Gemini, OMP and Kimi Code
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
completed_at: '2026-09-29T08:22:45Z'
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

Hosts whose CLI is not installed or cannot be driven get `unknown` with the reason; the survey itself does not block on them. An `unknown` host is not an eight-host completion verdict: create a per-host follow-up with `parent: EPIC-3562` so the epic remains open until the evidence is obtained or its scope is explicitly revised.

## Scope Boundaries

- **In scope**: evidence capture, fixtures, per-host findings, and a recommendation per host (ingest / defer / unsupported).
- **Out of scope**: normalizers, ingestion, refresh/re-ingestion and reporting (ENH-3534); the capability vocabulary itself (ENH-3544); Claude (ENH-3546); Codex (ENH-3532).

## Program Design

Evidence capture and the corresponding six-host entries in ENH-3544's typed
runtime map. No normalizer or ingestion code ships here.

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

1. For each host, capture one live invocation and one on-disk session containing at least one tool call and, where possible, a resume; record an explicit `unknown` reason when capture cannot be performed.
2. Sanitize and commit fixtures with version metadata; record findings in a per-host table here.
3. Recommend per host: implement in ENH-3534, split to its own issue (if the host's semantics are distinct enough), or record as evidence-backed unsupported. For unresolved `unknown` results, file a child follow-up under EPIC-3562. Update the epic's eight-host completion ledger with the evidence and owners.

## Survey findings (2026-09-29)

The real captures are sanitized excerpts, not complete unredacted sessions.
Their per-host READMEs record exactly what was retained and the limits of each
claim. `supported` below means a versioned real producer record exposes the
named native field on that channel; it does not qualify a stored observation
as measured or prove that little-loops already ingests it. No survey host has
an evidence-backed `unsupported` metric: failed probes, absent credentials,
zero-only samples and missing fixtures remain `unknown`.

| Host/version | Channel and fields | Input/cache-write semantics | Grain and native identity | Reasoning in output | Evidence class and recommendation |
| --- | --- | --- | --- | --- | --- |
| OpenCode 1.1.53 | `live`: `step_finish.part.tokens.{input,output,reasoning,cache.read,cache.write}` | Input inclusivity unknown; write field present but zero-only; omission unknown. | Two distinct `part.id` values in initial invocation, third after resume; same `sessionID` and matching stored IDs. Per-step in this sample. | Unknown. | Output/cache field availability supported, normalized input unknown. Candidate for ENH-3534 after ENH-3660. |
| OpenCode 1.1.53 | `transcript`: matching stored `step-finish` part fields | Same uncertainties; all observed cache values zero. | `(sessionID, part.id)` candidate source key; live/stored copies must deduplicate. | Unknown. | Output/cache field availability supported; normalized input unknown. |
| Pi 0.84.2 | `live`/`transcript`: no usage capture; model request required an absent API key. | Unknown. | Unknown. | Unknown. | All unknown; defer to ENH-3661, then ENH-3534. |
| Qwen 0.24.6 | `transcript`: assistant `usageMetadata.{promptTokenCount,candidatesTokenCount,thoughtsTokenCount,totalTokenCount,cachedContentTokenCount}` and preceding UI snake-case fields. | Prompt inclusivity unknown; cached field zero-only; cache-write field not present in this pair, with availability unknown. | Same numbers in two records with distinct `uuid`; UI `response_id`/`prompt_id` are candidate join keys. Request/turn grain and resume reset unknown. | Unknown despite `thoughtsTokenCount`: total equals prompt plus candidates in this sample. | Output/cache-read field availability supported; normalized input/cache creation unknown. Defer dedup/normalization to ENH-3662 and ENH-3534. |
| Qwen 0.24.6 | `live`: OAuth free-tier probe failed before a usable response. | Unknown. | Unknown. | Unknown. | All unknown; ENH-3662 owns a working-auth capture. |
| Gemini installed 0.46.0 | `live`: no usage capture; Vertex configuration absent. | Unknown. | Unknown. | Unknown. | All unknown; ENH-3663. |
| Gemini historical version unknown | `transcript`: `tokens.{input,output,cached,thoughts,tool,total}` on repeated `id`. | Unknown, including cache-write availability. | Same ID/timestamp/token values while `toolCallCount` changes; request identity and grain unproved. | Unknown. | All normalized availability unknown without version evidence; ENH-3663. |
| OMP CLI unavailable | `live`/`transcript`: only older synthetic `message.usage` fixtures exist. | Unknown. | Unknown. | Unknown. | All unknown; obtain real capture in ENH-3664. |
| Kimi Code 0.30.0 | `transcript`: `usage.record.usage.{inputOther,output,inputCacheRead,inputCacheCreation}`; same block in `context.append_loop_event`. | `inputOther` normalization unknown; nonzero cache read captured, creation zero-only; omission unknown. | Three `usage.record` blocks beside `llm.request` steps `0.1`, `0.2`, resumed `1.1`; `usageScope: turn`, but no request ID on usage records. Not a monotone session total. | Unknown. | Output/cache field availability supported; normalized input unknown. Candidate for ENH-3534 after ENH-3665. |
| Kimi Code 0.30.0 | `live`: sampled initial/resumed stream has no usage object. | Unknown. | Unknown. | Unknown. | All unknown; one absent sample is not proof of unsupported live telemetry. ENH-3665. |

`rollout` and `context_hook` availability remains unknown for these six hosts;
`context_hook` is occupancy-only and does not produce `usage_events` rows.
The typed map now reports `partial` native token availability for OpenCode,
Qwen and Kimi Code, and `unknown` for Pi, Gemini and OMP. ENH-3660 through
ENH-3665 are per-host evidence follow-ups with `parent: EPIC-3562`; each host
remains incomplete in the epic ledger while its follow-up or ingestion path
is open. ENH-3534 owns normalizers/re-ingestion only after these producer
contracts are sufficient.

Read-path check with `iter_events()` on the committed-shape excerpts:
OpenCode's stored parts yield two raw `step-finish` events with `tokens`;
Kimi's stored excerpt yields eleven raw events, including three
`usage.record` payloads. The trimmed Qwen usage pair yields no events because
its assistant excerpt lacks `message.parts`; Gemini's header-less excerpt
yields one normalized event with `tokens` dropped; OMP's synthetic session
yields five normalized events with `message.usage` dropped. These counts
describe current parser behavior on the excerpts, not producer absence or a
complete-session ingestion verdict.

## Impact

- **Priority**: P3.
- **Effort**: Small to medium (mostly capture; depends on host CLI availability).
- **Risk**: Low — no production code.
- **Breaking Change**: No.

## Acceptance Criteria

- [x] All six hosts have a findings row with CLI version, channel, fields, cache semantics, grain and identity — or an explicit `unknown` with the reason.
- [x] Every `supported` claim is backed by a committed fixture; every `unsupported` claim cites evidence of absence. (The sanitized fixtures are ready; the parent integration pass owns the commit.)
- [x] Each host has an ingestion recommendation. Host-specific implementation issues and unresolved-`unknown` evidence follow-ups use `parent: EPIC-3562` and relate to ENH-3534 where relevant; merely linking them does not count as epic completion.

## Status

**Done** | Created: 2026-09-29 | Priority: P3


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Six host surveys and sanitized evidence are recorded; incomplete native contracts have dedicated EPIC-3562 children ENH-3660–3665.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.


## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:44 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
