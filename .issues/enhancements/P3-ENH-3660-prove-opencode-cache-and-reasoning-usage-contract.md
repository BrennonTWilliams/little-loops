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

- [ ] Source-present or affirmative no-source completion follows **Completion Rule**; no-source evidence has a scoped native proof and unavailable-reader handoff, while unavailable access remains unknown. A selected source declares its acquisition channel and retained-raw logical-candidate identity for quality derive-status integration.
- [ ] For a selected usage-bearing source: Capture the native lifecycle of a usage-bearing part from partial write to final/revised values, including observed add/delete or rewrite behavior where supported. Give ENH-3671 the evidence-backed replacement/identity rule and the real storage layout; do not assume a JSONL append-only contract. Classify whether the native store distinguishes authoritative retraction from retention, compaction or source disappearance. If that distinction is unproved, record it as unknown and specify that ENH-3671 must retain recorded usage and mark current-source freshness stale/unknown; proof of a retraction signal is not a new closeout prerequisite.
- [ ] For a selected usage-bearing source: The ENH-3671 handoff identifies a captured provider/version-qualified contract and an evidenced exact-version or compatibility rule, with matching and mismatch/absent-identity fixtures. Runtime values come from a verified native source; missing evidence remains audit-only/unavailable rather than inheriting a host-wide supported verdict.
- [ ] For a selected usage-bearing source: Save a sanitized, versioned native capture with a tool call, resume, and matching live/stored parts; document which cache-hit/write and retry/compaction cases were actually observed.
- [ ] For a selected usage-bearing source: Preserve a sanitized, parser-ready fixture in the native session/message/part storage-tree layout, with the project-directory mapping and storage-root rule. A test extracts its step-finish token fields and checks parity with the existing reduced JSONL excerpt; only the tree fixture is eligible for production-discovery tests.
- [ ] For a selected usage-bearing source: Record native-field availability for input, output, cache-read, and cache-creation on each relevant channel, and record the reasoning/output relationship separately: `supported`, `unsupported` with affirmative producer evidence, or `unknown` with the missing proof. State inclusivity, omitted-field behavior, grain/reset rules, and the namespace and stability of `(sessionID, part.id)`.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger. Also record the native field path(s) that carry request/replay identity, model and the usage-bearing fields, and the event type the adapter will store them under — the input to the delivery's history-sanitizer path registration (EPIC-3562 § Shared Delivery Ownership).
- [ ] For a selected usage-bearing source: Give ENH-3671 a replay-ready source fixture and dedup contract. The delivery issue proves parser → stored observation → trigger → reader; this evidence issue does not count as ingestion completion.
- [ ] If this is the first of ENH-3660/3665 to land, add the common README verdict table and parameterized typed-map evidence test; otherwise add OpenCode rows to that test.
- [ ] If a nonzero cache or identity case cannot be exercised, record the access/model blocker and leave the affected semantics `unknown`. Keep this issue open or mark it `blocked`; do not infer `unsupported` from zero-only samples.

## Completion Rule

The runtime qualification handoff above is required before releasing the delivery issue.

**Source-present versus no-source disposition:** the usage-bearing capture, request/replay identity, nonzero supported-cache and output/reasoning criteria apply only when selecting a usage-bearing canonical path. An affirmative no-source verdict instead supplies sanitized, versioned provider/source evidence demonstrating absence for the declared path, states the limits of that verdict, and names the delivery issue's unavailable-reader/fallback work in the epic ledger. It does not require inventing a usage-bearing fixture, request key or post-usage trigger for a nonexistent source. Authentication failure, an absent CLI, empty/zero-only samples and source-only speculation still cannot satisfy this branch. Keep any unproved in-scope path open; partial support uses the source-present branch for its proved components.

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3671. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required for a selected usage-bearing source before this issue closes; affirmative no-source evidence follows Completion Rule instead. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, ENH-3665 owns it. This issue adds its host's rows. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Runtime Qualification Handoff

The usage-bearing contract and fixture requirements below apply to a selected usage-bearing path. An affirmative no-source handoff instead supplies the scoped native absence proof and unavailable-reader disposition defined in Completion Rule.

Give ENH-3671 the observed provider and CLI/source version, the native envelope or verified source of those values, and a stable fixture contract reference. Record whether qualification requires the exact captured version or permits a specific compatibility range backed by evidence. A current local CLI version alone cannot qualify a historical record. A host-level capability note does not qualify every provider/version.

Include a matching fixture and unmatched-provider, unsupported/unproved-version, absent provider/version, and unproved identity cases. Specify the audit-only/unavailable reason for each mismatch. The delivery issue persists the ingest-time contract/evidence on `raw_events` (using existing metadata where sufficient) and reuses it on rebuild; it must not substitute later machine configuration or promote an old unknown. No all-provider capture matrix or mandatory new column is implied. ENH-3731/3732/3733 implement ENH-3723's recorded shared eligibility policy, separately from this native evidence contract. The handoff also declares the normalized acquisition channel and a pure logical-candidate/key rule usable by ENH-3732's derive-status reader on retained raw evidence. This prevents a newly supported transcript source from being treated as excluded/non-usage while its observations are pending; a host name alone is not a channel rule. The matching delivery implements and tests that extension before production publication. Its retained-evidence rule must fit ENH-3744's shared pure recognition/key/coalescing/correspondence interface: distinguish a represented candidate, intentional no-observation and unprovable/missing native context. This issue supplies the evidence, not a second production proof engine; the delivery also tests pruning/held-source recovery and ENH-3745's source-local completion handoff.

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

## Session Log

- Pre-implementation epic review - 2026-10-07 - Added the native identity-path recording requirement: ENH-3751 now sanitizes every raw_events insert and `pii._protocol_rules` is the only protection for replay-identity fields, so the matching delivery needs these paths from this evidence. No captured proof or readiness claim.

- Pre-implementation epic review - 2026-10-05 - Connected the existing acquisition-channel/logical-candidate evidence to ENH-3744's shared pure proof and ENH-3745's source-local progress contract. Native evidence/access/partial-support closeout rules remain unchanged; no captured proof or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Made usage-bearing proof conditional on a selected source and specified affirmative no-source closeout. Added acquisition-channel/logical-candidate handoff to the delivery and quality derive-status reader; existing access gates and evidence standards remain in force.

- Pre-implementation epic review - 2026-10-04 - Clarified the mutable-source handoff after the Opus critique: classify authoritative retraction separately from source loss; absent retraction evidence defaults to retaining recorded usage with stale/unknown freshness. This optional retraction classification does not expand the evidence closeout gate.
