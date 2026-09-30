---
id: ENH-3665
type: ENH
title: Prove Kimi usage component and replay identity
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels:
- observability
- multi-host
- producer-evidence
relates_to:
- ENH-3648
- ENH-3534
- ENH-3544
blocks:
- ENH-3676
---

# ENH-3665: Prove Kimi usage component and replay identity

## Summary

Prove the Kimi Code native token-usage contract needed by ENH-3676. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

ENH-3648 captured Kimi Code 0.30.0 stored `usage.record` fields, a nonzero
cache read, a resume, and matching copies in context events. The
live stream sample had no usage. `inputOther` normalization,
`inputCacheCreation` behavior beyond zero, reasoning/output inclusion,
`usageScope: turn` grain, and a durable request key for dedup/replay remain
unknown. One no-usage live sample does not prove that channel unsupported.

## Expected Behavior

Capture or establish producer-contract evidence for `inputOther` versus cached
input, nonzero cache creation if available, omission behavior, output versus
reasoning, and the mapping of `usage.record` to `llm.request.turnStep` across
resume, retries and compaction. Determine whether a stable native ID exists;
otherwise define a replay-safe source-position key. Verify whether additional
live event modes can expose usage. Update
`scripts/tests/fixtures/kimi-code/README.md` and the typed map for proved
entries, then hand the stored-record dedup rule to ENH-3676; ENH-3534 owns
only shared replay/refresh. Keep Kimi Code incomplete in EPIC-3562 until
ingestion, trigger and reader are verified.

## Acceptance Criteria

- [ ] Capture or cite version-pinned producer evidence for `inputOther`, cache creation, output/reasoning, omissions, and `usageScope: turn` grain; preserve request, usage, and copied event context across a tool call and resume.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts. Prove a native request key or specify a replay-safe source-position key that survives incremental derive and full rebuild without counting copied context events.
- [ ] Give ENH-3676 the native fixture and dedup rule. ENH-3676 owns parsing `usage.record`, stored ingestion, current-session trigger, and reader proof.
- [ ] If the live channel or nonzero cache-creation case remains unobservable, record why and keep that channel/metric `unknown`; one no-usage sample or zero-only field is not evidence of absence.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3676.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) may support an inclusivity/omission verdict only as a **distinct, lower tier**: record it as such in the fixture README and in the typed telemetry map (`TelemetryCapability`), never identically to a captured verdict. A captured nonzero-cache sample and a captured identity/replay fixture are still required before canonical totals or rates are reported as measured. Do not use source-only evidence to close this issue or release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. Add a sync test asserting that this host's fixture README verdict table and the typed telemetry map agree (see EPIC-3562 note on the missing README↔`telemetry_matrix` gate).

## Program Design

- Capture a sanitized, versioned producer sample for native usage records and their copied context records beside request steps, preserving the envelope and request order needed to test identity and replay.
- Record each metric/channel verdict in scripts/tests/fixtures/kimi-code/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3676; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3676 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3676 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3676 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3676); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured Kimi Code ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
