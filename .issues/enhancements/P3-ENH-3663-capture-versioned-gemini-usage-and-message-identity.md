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
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, and cache read/write; record the thoughts/output relationship separately. Establish inclusivity, omissions, request grain/reset behavior, and whether repeated IDs replace one observation or identify independent requests.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger.
- [ ] Give ENH-3674 a replay-ready fixture and identity rule. ENH-3674 owns preserving native `tokens` through the file-level parser and proving stored ingestion, trigger, and reader behavior.
- [ ] If Vertex/model access remains unavailable, record the exact configuration blocker, leave current-version availability `unknown`, and keep this issue open or `blocked`; the unversioned historical pair alone cannot certify the current contract.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3674. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required before this issue closes. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, ENH-3665 owns it. This issue adds its host's rows. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Program Design

- Use one stable row ID per native metric/channel/provider/version verdict, with evidence tier, inclusivity/omission semantics, native source, and duplicate-channel disposition. A table-backed `TelemetryCapability.note` cites `README:<row-id>` for each supporting verdict; the shared test joins those IDs without treating a host-level entry as proof for every provider. Document in `host_runner.py` that `token_reporting_summary: full` describes native field availability, not stored measurement.
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
