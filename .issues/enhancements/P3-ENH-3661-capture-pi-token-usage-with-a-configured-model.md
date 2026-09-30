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

## Evidence gap

Pi 0.84.2 was installed for ENH-3648, but no API key was configured. No
versioned live or on-disk usage-bearing record was captured. Every native
metric/channel entry remains unknown; authentication failure does not prove
absence of telemetry.

## Required proof

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
