---
id: ENH-3663
type: ENH
title: Capture versioned Gemini usage and message identity
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
  evidence: "Working Vertex/model configuration for Gemini CLI >=0.46.0. ENH-3648: 0.46.0 live probe lacked Vertex configuration."
blocks:
- ENH-3674
---

# ENH-3663: Capture versioned Gemini usage and message identity

## Summary

Prove the Gemini native token-usage contract needed by ENH-3674. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

ENH-3648 found a historical real Gemini `tokens` pair with repeated message
`id` and changed `toolCallCount`, but the producing CLI version is unknown.
The installed Gemini 0.46.0 live probe lacked Vertex configuration. The
historical pair cannot certify current-version metric availability or the
identity of independent usage observations.

## Expected Behavior

With working Vertex/model configuration, capture sanitized live and on-disk
0.46.0-or-newer records with tool use and resume. Verify whether repeated
message IDs rewrite one usage record or represent distinct requests; record
cache inclusivity/write semantics, omissions, reasoning/output inclusion,
grain and resets. Add versioned fixtures and findings to
`scripts/tests/fixtures/gemini/README.md`; update the typed map only for
proved entries and hand the contract to ENH-3674; ENH-3534 owns only shared
replay/refresh. Keep Gemini incomplete in EPIC-3562 until ingestion, trigger
and reader are verified.

## Acceptance Criteria

- [ ] Capture sanitized, versioned Gemini live and full-enough stored sessions with tool use and resume under working Vertex/model configuration; retain the session header and repeated-ID records needed for parser and identity tests.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, cache read/write, and thoughts. Establish inclusivity, omissions, request grain/reset behavior, and whether repeated IDs replace one observation or identify independent requests.
- [ ] Give ENH-3674 a replay-ready fixture and identity rule. ENH-3674 owns preserving native `tokens` through the file-level parser and proving stored ingestion, trigger, and reader behavior.
- [ ] If Vertex/model access remains unavailable, record the exact configuration blocker, leave current-version availability `unknown`, and keep this issue open or `blocked`; the unversioned historical pair alone cannot certify the current contract.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3674.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) may support an inclusivity/omission verdict only as a **distinct, lower tier**: record it as such in the fixture README and in the typed telemetry map (`TelemetryCapability`), never identically to a captured verdict. A captured nonzero-cache sample and a captured identity/replay fixture are still required before canonical totals or rates are reported as measured. Do not use source-only evidence to close this issue or release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. Add a sync test asserting that this host's fixture README verdict table and the typed telemetry map agree (see EPIC-3562 note on the missing README↔`telemetry_matrix` gate).

## Program Design

- Capture a sanitized, versioned producer sample for versioned message tokens and repeated message IDs, preserving the envelope and request order needed to test identity and replay.
- Record each metric/channel verdict in scripts/tests/fixtures/gemini/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3674; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3674 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3674 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3674 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3674); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured Gemini ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
