---
id: ENH-3664
type: ENH
title: Capture real OMP token usage contract
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
- ENH-3675
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
entries and hand an ingestion recommendation to ENH-3675; ENH-3534 owns only
shared replay/refresh. Keep OMP incomplete in EPIC-3562 until ingestion,
trigger and reader are verified or absence is proved.

## Acceptance Criteria

- [ ] Obtain an OMP CLI and capture a sanitized, versioned real live and full-enough stored session with a tool call and resume; retain header/message structure needed for file-level parser tests.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, cache read/write, and reasoning. Establish inclusivity, omissions, request grain/reset behavior, and source-event identity.
- [ ] Give ENH-3675 a replay-ready native fixture and normalization contract. ENH-3675 owns preserving `message.usage` and proving stored ingestion, trigger, and reader behavior.
- [ ] If the CLI remains unavailable, record the access blocker, leave native availability `unknown`, and keep this issue open or `blocked`; synthetic fixtures do not prove producer support or absence.
