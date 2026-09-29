---
id: ENH-3664
type: ENH
title: Capture real OMP token usage contract
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels: [observability, multi-host, producer-evidence]
relates_to: [ENH-3648, ENH-3534, ENH-3544]
---

# ENH-3664: Capture real OMP token usage contract

## Evidence gap

No OMP CLI was available during ENH-3648. The existing session fixtures are
synthetic examples derived from vendored types, not native producer evidence.
All metric/channel claims remain unknown.

## Required proof

Install or access an OMP CLI and capture sanitized, versioned live and stored
usage from a tool-using invocation and resume. Verify native fields, cache
inclusivity and writes, omissions, reasoning/output relationship, grain,
reset behavior and source-event identity. Add real fixtures and findings to
`scripts/tests/fixtures/omp/README.md`, then update the typed map for proved
entries and hand an ingestion recommendation to ENH-3534. Keep OMP incomplete
in EPIC-3562 until ingestion, trigger and reader are verified or absence is
proved.
