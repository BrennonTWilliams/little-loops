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
gate:
- kind: external
  satisfied: false
  owner: user
  evidence: "Install an OMP CLI and configure a model. ENH-3648: no OMP CLI available; fixtures are synthetic."
blocks:
- ENH-3675
---

# ENH-3664: Capture real OMP token usage contract

## Summary

Prove the OMP native token-usage contract needed by ENH-3675. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

No OMP CLI was available during ENH-3648. The existing session fixtures are
synthetic examples derived from vendored types, not native producer evidence.
All metric/channel claims remain unknown.

## Expected Behavior

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

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3675.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) may support an inclusivity/omission verdict only as a **distinct, lower tier**: record it as such in the fixture README and in the typed telemetry map (`TelemetryCapability`), never identically to a captured verdict. A captured nonzero-cache sample and a captured identity/replay fixture are still required before canonical totals or rates are reported as measured. Do not use source-only evidence to close this issue or release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. Add a sync test asserting that this host's fixture README verdict table and the typed telemetry map agree (see EPIC-3562 note on the missing README↔`telemetry_matrix` gate).

## Program Design

- Capture a sanitized, versioned producer sample for real assistant message.usage and the session/message envelope, preserving the envelope and request order needed to test identity and replay.
- Record each metric/channel verdict in scripts/tests/fixtures/omp/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3675; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3675 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3675 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3675 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3675); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured OMP ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
