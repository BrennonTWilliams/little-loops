---
id: ENH-3661
type: ENH
title: Capture Pi token usage with a configured model
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
- ENH-3672
---

# ENH-3661: Capture Pi token usage with a configured model

## Summary

Prove the Pi native token-usage contract needed by ENH-3672. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

Pi 0.84.2 was installed for ENH-3648, but no API key was configured. No
versioned live or on-disk usage-bearing record was captured. Every native
metric/channel entry remains unknown; authentication failure does not prove
absence of telemetry.

## Expected Behavior

With a configured model, capture sanitized live and stored records from a
tool-using invocation and a resume. Record field names, input/cache
inclusivity, cache-write and omitted-field behavior, output/reasoning
relationship, request grain, reset behavior and stable source-event identity.
Add versioned fixtures and a contract to `scripts/tests/fixtures/pi/README.md`,
then update the typed map for proved entries. Hand an ingestion recommendation
to ENH-3672; ENH-3534 owns only shared replay/refresh. Keep Pi incomplete in
EPIC-3562 until ingestion, trigger and reader are verified or native absence
is proved.

## Acceptance Criteria

- [ ] Capture and sanitize a real versioned Pi invocation with configured model access, a tool call, resume, and matching live/stored usage records; record the model and channel without exposing credentials.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, cache read/write, and reasoning. Prove inclusivity, omission, grain/reset behavior, and source identity where measured ingestion is proposed.
- [ ] Give ENH-3672 a replay-ready native fixture and explicit normalizer recommendation; its own tests prove parser → stored observation → trigger → reader.
- [ ] If model access is still unavailable, record the precise missing configuration, leave native availability `unknown`, and keep this issue open or `blocked`. An authentication failure is not an unsupported-telemetry verdict.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3672.

## Program Design

- Capture a sanitized, versioned producer sample for a configured Pi invocation's actual live and on-disk usage records, preserving the envelope and request order needed to test identity and replay.
- Record each metric/channel verdict in scripts/tests/fixtures/pi/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3672; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3672 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3672 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3672 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3672); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured Pi ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
