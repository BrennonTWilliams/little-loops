---
id: ENH-3661
type: ENH
title: Capture Pi token usage with a configured model
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels: [observability, multi-host, producer-evidence]
relates_to: [ENH-3648, ENH-3534, ENH-3544]
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
to ENH-3534. Keep Pi incomplete in EPIC-3562 until ingestion, trigger and
reader are verified or native absence is proved.
