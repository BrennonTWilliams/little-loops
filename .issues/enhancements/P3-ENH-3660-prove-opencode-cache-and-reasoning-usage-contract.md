---
id: ENH-3660
type: ENH
title: Prove OpenCode cache and reasoning usage contract
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
- ENH-3671
---

# ENH-3660: Prove OpenCode cache and reasoning usage contract

## Summary

Prove the OpenCode native token-usage contract needed by ENH-3671. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

ENH-3648 captured OpenCode 1.1.53 live `step_finish` and matching stored
`step-finish` parts, including a resume. The observed cache read/write fields
are all zero. `tokens.input` inclusivity, `tokens.reasoning` inclusion in
`tokens.output`, omitted-field semantics, and part identity across retries or
compaction remain unknown. The typed map marks observed output/cache fields
available while normalized disjoint input stays unknown. The reduced stored
fixture is JSONL, but the installed 1.1.53 CLI keeps separate session,
message, and part JSON files under its data storage tree. Existing little-loops
session discovery expects `~/.opencode/projects/*.jsonl`, which is absent on
this installation. A reduced JSONL fixture cannot prove production discovery.

## Expected Behavior

Capture a sanitized, versioned cache-hit and cache-write-capable run with
matching live and stored parts, a tool call, resume, and any retry/compaction
behavior that occurs. Establish whether input includes cache reads/writes,
whether reasoning is included in output, what absent fields mean, and whether
`(sessionID, part.id)` is stable and unique across live/stored/replay. Update
`scripts/tests/fixtures/opencode/README.md` and the six-host telemetry map
only for proved metric/channel semantics. Hand the contract to ENH-3671;
ENH-3534 owns only the completed shared replay/refresh baseline. Keep the
epic's OpenCode ledger incomplete until stored ingestion, trigger and reader
are verified. Capture the actual storage-tree layout and session/project mapping,
the part's native `sessionID`/`messageID`/`id`, CLI version, and storage-root rule;
ENH-3671 owns adapting discovery, replay and freshness to that layout.

### Access prerequisite (2026-09-30)

Cache-hit/write semantics need a caching-capable provider. A local storage-tree probe found a nonzero cache-read part that has not yet been sanitized into a committed fixture; no nonzero cache-write part was found. Use that read case as a capture candidate without treating it as completed proof. OpenCode's inclusivity semantics may be provider-dependent, so every verdict must be keyed by provider and version. This issue is not gated as `external` because real 1.1.53 captures and identity/resume evidence can proceed now; record any remaining cache-write/model access blocker precisely. Sequenced first alongside ENH-3665 (Kimi) per the 2026-09-30 review.

## Acceptance Criteria

- [ ] Save a sanitized, versioned native capture with a tool call, resume, and matching live/stored parts; document which cache-hit/write and retry/compaction cases were actually observed.
- [ ] Preserve a sanitized, parser-ready fixture in the native session/message/part storage-tree layout, with the project-directory mapping and storage-root rule. A test extracts its step-finish token fields and checks parity with the existing reduced JSONL excerpt; only the tree fixture is eligible for production-discovery tests.
- [ ] Record native-field availability for input, output, cache-read, and cache-creation on each relevant channel, and record the reasoning/output relationship separately: `supported`, `unsupported` with affirmative producer evidence, or `unknown` with the missing proof. State inclusivity, omitted-field behavior, grain/reset rules, and the namespace and stability of `(sessionID, part.id)`.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger.
- [ ] Give ENH-3671 a replay-ready source fixture and dedup contract. The delivery issue proves parser → stored observation → trigger → reader; this evidence issue does not count as ingestion completion.
- [ ] If this is the first of ENH-3660/3665 to land, add the common README verdict table and parameterized typed-map evidence test; otherwise add OpenCode rows to that test.
- [ ] If a nonzero cache or identity case cannot be exercised, record the access/model blocker and leave the affected semantics `unknown`. Keep this issue open or mark it `blocked`; do not infer `unsupported` from zero-only samples.

## Completion Rule

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3671. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required before this issue closes. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, ENH-3665 owns it. This issue adds its host's rows. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Program Design

- Use one stable row ID per native metric/channel/provider/version verdict, with evidence tier, inclusivity/omission semantics, native source, and duplicate-channel disposition. A table-backed `TelemetryCapability.note` cites `README:<row-id>` for each supporting verdict; the shared test joins those IDs without treating a host-level entry as proof for every provider. Document in `host_runner.py` that `token_reporting_summary: full` describes native field availability, not stored measurement.
- Capture a sanitized, versioned producer sample for step_finish.part.tokens and the sessionID/part.id pair, preserving the envelope and request order needed to test identity and replay.
- Capture native session, message, and part file relationships and their mutation behavior. Record the real storage root, version, project mapping, and stable per-part source identity without relying on a synthetic concatenated JSONL stream.
- Record each metric/channel verdict in scripts/tests/fixtures/opencode/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3671; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — current parser inspection point for the legacy JSONL assumption; record its discovery failure against the captured native tree. ENH-3671 owns the source adapter and parser change.

### Call Path

- Native session/message/part storage tree → sanitized versioned tree fixture → `detect_sessions`/`iter_events` discovery and parser gap inspection → fixture README contract → `telemetry_matrix` native availability → ENH-3671 source-adapter handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3671 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3671); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured OpenCode ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3
