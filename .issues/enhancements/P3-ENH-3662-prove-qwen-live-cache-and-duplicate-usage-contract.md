---
id: ENH-3662
type: ENH
title: Prove Qwen live cache and duplicate usage contract
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
gate:
- kind: external
  satisfied: false
  owner: user
  evidence: "Working Qwen Code auth (OAuth free tier discontinued): supply an API key or alternate provider. ENH-3648: OAuth free tier discontinued; live probe failed."
blocks:
- ENH-3673
---

# ENH-3662: Prove Qwen live cache and duplicate usage contract

## Summary

Prove the Qwen native token-usage contract needed by ENH-3673. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

ENH-3648 captured a real Qwen Code 0.24.6 on-disk UI/assistant usage pair.
The live probe failed after the configured OAuth free tier was discontinued.
The pair reports zero cached content and no cache-write field; input
inclusivity, thought-token inclusion, response identity across the two
representations, and resume/compaction behavior remain unknown.

## Expected Behavior

With working authentication, capture a sanitized versioned live invocation
and matching transcript with tool use, cache hit/write if available, and
resume. Establish whether `promptTokenCount` includes cached input, whether
`thoughtsTokenCount` is included in `candidatesTokenCount`, what missing fields
mean, and how `response_id`/`prompt_id` joins the assistant `uuid` without
double-counting. Update `scripts/tests/fixtures/qwen/README.md` and the typed
map for proved entries, then hand a replay contract to ENH-3673; ENH-3534
owns only shared replay/refresh. Keep Qwen incomplete in EPIC-3562 until
stored ingestion, trigger and reader are proven.

## Acceptance Criteria

- [ ] Capture a sanitized, versioned Qwen live/transcript pair with tool use and resume under working authentication. Preserve enough of the native assistant record, including `message.parts`, to make the transcript usable in `iter_events` parser tests; the current reduced usage pair yields no event.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, and cache read/write; record the thought/output relationship separately. Prove or leave explicit the inclusivity, omission, grain/reset, and UI/assistant request-join semantics.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger.
- [ ] Give ENH-3673 the complete-enough native fixture and duplicate-pair rule. ENH-3673 proves that the parser preserves `usageMetadata` and that one response produces one stored observation and a fresh selected read.
- [ ] If authentication or nonzero cache behavior remains unavailable, record the exact blocker and keep those semantics `unknown`; keep this evidence issue open or `blocked` rather than claiming unsupported telemetry.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3673. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required before this issue closes. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, ENH-3665 owns it. This issue adds its host's rows. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Program Design

- Use one stable row ID per native metric/channel/provider/version verdict, with evidence tier, inclusivity/omission semantics, native source, and duplicate-channel disposition. A table-backed `TelemetryCapability.note` cites `README:<row-id>` for each supporting verdict; the shared test joins those IDs without treating a host-level entry as proof for every provider. Document in `host_runner.py` that `token_reporting_summary: full` describes native field availability, not stored measurement.
- Capture a sanitized, versioned producer sample for assistant usageMetadata and systemPayload.uiEvent copies with their native IDs, preserving the envelope and request order needed to test identity and replay.
- Record each metric/channel verdict in scripts/tests/fixtures/qwen/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3673; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3673 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3673 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3673 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3673); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured Qwen ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
