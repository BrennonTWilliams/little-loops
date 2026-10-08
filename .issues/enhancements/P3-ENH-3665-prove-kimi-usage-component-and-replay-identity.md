---
id: ENH-3665
type: ENH
title: Prove Kimi usage component and replay identity
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
- ENH-3676
---

# ENH-3665: Prove Kimi usage component and replay identity

## Summary

Prove the Kimi Code native token-usage contract needed by ENH-3676. This issue records producer evidence and typed metric/channel availability; the delivery issue implements stored ingestion, current-session triggering, and the reader.

## Current Behavior

ENH-3648 captured Kimi Code 0.30.0 stored `usage.record` fields, a nonzero
cache read, a resume, and matching copies in context events. The
live stream sample had no usage. `inputOther` normalization,
`inputCacheCreation` behavior beyond zero, reasoning/output inclusion,
`usageScope: turn` grain, and a durable request key for dedup/replay remain
unknown. One no-usage live sample does not prove that channel unsupported.

## Expected Behavior

Capture or establish producer-contract evidence for `inputOther` versus cached
input, nonzero cache creation if available, omission behavior, output versus
reasoning, and the mapping of `usage.record` to `llm.request.turnStep` across
resume, retries and compaction. Determine whether a stable native ID exists;
otherwise define a replay-safe source-position key. Verify whether additional
live event modes can expose usage. Update
`scripts/tests/fixtures/kimi-code/README.md` and the typed map for proved
entries, then hand the stored-record dedup rule to ENH-3676; ENH-3534 owns
only shared replay/refresh. Keep Kimi Code incomplete in EPIC-3562 until
ingestion, trigger and reader are verified.

## Acceptance Criteria

- [ ] Source-present or affirmative no-source completion follows **Completion Rule**; no-source evidence has a scoped native proof and unavailable-reader handoff, while unavailable access remains unknown. A selected source declares its acquisition channel and retained-raw logical-candidate identity for quality derive-status integration.
- [ ] For a selected usage-bearing source: The ENH-3676 handoff identifies a captured provider/version-qualified contract and an evidenced exact-version or compatibility rule, with matching, mismatch/absent-identity and missing/conflicting-context fixtures. Retain the native records or verified acquisition metadata supplying provider/version, channel/scope and request identity, including their relationship to each usage record. Missing evidence remains audit-only/unavailable rather than inheriting a host-wide supported verdict.
- [ ] For a selected usage-bearing source: Capture or cite version-pinned producer evidence for `inputOther`, cache creation, output/reasoning, omissions, and `usageScope: turn` grain; preserve request, usage, and copied event context across a tool call and resume.
- [ ] For a selected usage-bearing source: Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts. Prove a native request key or a replay-safe source-position key without counting copied context events. A position key requires a full-enough sanitized wire fixture and native session/index/header or verified acquisition context, with an explicit host/session/source-generation namespace and append/reopen/incremental/full-rebuild stability. Classify rewrite/rotation/compaction continuity as proved or unknown; reduced excerpts cannot prove original physical positions.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger. Declare the stored adapter event shape and string replay-identity, model and qualification-context paths for the delivery's existing `usage_proof.PROOF_IDENTITY_PATHS`/sanitizer-parity extension. Record numeric usage-field paths separately for exact preservation and malformed-value validation; they are not replay identity (EPIC-3562 § Shared Delivery Ownership).
- [ ] For a selected usage-bearing source: Give ENH-3676 the native fixture and dedup rule. ENH-3676 owns parsing `usage.record`, stored ingestion, current-session trigger, and reader proof.
- [ ] If this is the first of ENH-3660/3665 to land, add the common README verdict table and parameterized typed-map evidence test; otherwise add Kimi rows to that test. Define how source-cited provisional evidence remains `unknown` in the map.
- [ ] If the live channel or nonzero cache-creation case remains unobservable, record why and keep that channel/metric `unknown`; one no-usage sample or zero-only field is not evidence of absence.

## Completion Rule

The runtime qualification handoff above is required before releasing the delivery issue.

**Source-present versus no-source disposition:** the usage-bearing capture, request/replay identity, nonzero supported-cache and output/reasoning criteria apply only when selecting a usage-bearing canonical path. An affirmative no-source verdict instead supplies sanitized, versioned provider/source evidence demonstrating absence for the declared path, states the limits of that verdict, and names the delivery issue's unavailable-reader/fallback work in the epic ledger. It does not require inventing a usage-bearing fixture, request key or post-usage trigger for a nonexistent source. Authentication failure, an absent CLI, empty/zero-only samples and source-only speculation still cannot satisfy this branch. Keep any unproved in-scope path open; partial support uses the source-present branch for its proved components.

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3676. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required for a selected usage-bearing source before this issue closes; affirmative no-source evidence follows Completion Rule instead. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, this issue owns it. If this issue goes first, its initial case covers Kimi; otherwise it adds Kimi rows to the existing test. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Runtime Qualification Handoff

The usage-bearing contract and fixture requirements below apply to a selected usage-bearing path. An affirmative no-source handoff instead supplies the scoped native absence proof and unavailable-reader disposition defined in Completion Rule.

Give ENH-3676 the observed provider and CLI/source version, the native envelope or verified source of those values, and a stable fixture contract reference. Preserve the request/session context or verified acquisition metadata needed to qualify and key each usage record on retained-raw replay, and declare those dependencies. Record whether qualification requires the exact captured version or permits a specific compatibility range backed by evidence. A capture fixture's filename or current local CLI/provider configuration cannot qualify a historical record. A host-level capability note does not qualify every provider/version.

Include a matching fixture and unmatched-provider, unsupported/unproved-version, absent provider/version, and unproved identity cases. Specify the audit-only/unavailable reason for each mismatch. The delivery issue persists the ingest-time contract/evidence on `raw_events` (using existing metadata where sufficient) and reuses it on rebuild; it must not substitute later machine configuration or promote an old unknown. No all-provider capture matrix or mandatory new column is implied. ENH-3731/3732/3733 implement ENH-3723's recorded shared eligibility policy, separately from this native evidence contract. The handoff also declares the normalized acquisition channel and a pure logical-candidate/key rule usable by ENH-3732's derive-status reader on retained raw evidence. This prevents a newly supported transcript source from being treated as excluded/non-usage while its observations are pending; a host name alone is not a channel rule. The matching delivery implements and tests that extension before production publication. Its retained-evidence rule must fit ENH-3744's shared pure recognition/key/coalescing/correspondence interface: distinguish a represented candidate, intentional no-observation and unprovable/missing native context. This issue supplies the evidence, not a second production proof engine; the delivery also tests pruning/held-source recovery and ENH-3745's source-local completion handoff.

## Program Design

- Use one stable row ID per native metric/channel/provider/version verdict, with evidence tier, inclusivity/omission semantics, native source, and duplicate-channel disposition. A table-backed `TelemetryCapability.note` cites `README:<row-id>` for each supporting verdict; the shared test joins those IDs without treating a host-level entry as proof for every provider. Document in `host_runner.py` that `token_reporting_summary: full` describes native field availability, not stored measurement.
- Capture a sanitized, versioned producer sample for native usage records and their copied context records beside request steps, preserving the envelope and request order needed to test identity and replay.
- If using source positions, capture a parser-ready source with session context and record how sanitization preserves the native position rule. Use the declared generation/continuity rule on replay; unproved rewrite/rotation/compaction retains historical usage with stale/unknown freshness rather than reusing positions. The existing reduced excerpt remains field/order evidence only.
- Hand the stored shape and string identity/qualification paths to ENH-3676 for extension of `usage_proof.PROOF_IDENTITY_PATHS` and `TestSanitizerParity` in `scripts/tests/test_enh3744_usage_candidate_proof.py`. Reuse the shared declaration; the delivery adds secret-shaped identity refusals and source-to-sanitized-raw replay equivalence. Numeric usage fields need value preservation/validation, not identity exemptions.
- Record each metric/channel verdict in scripts/tests/fixtures/kimi-code/README.md with its source version, observed values, inclusive/exclusive meaning, omission behavior, grain, resume behavior, and evidence limits.
- Update only proved entries in the typed telemetry map. Hand the exact fixture and identity rule to ENH-3676; no production normalizer is implemented in this evidence issue.

### Signatures

- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing parser inspection point; record which native fields survive today. ENH-3676 owns any parser change.

### Call Path

- Native CLI/session file → sanitized versioned fixture → `iter_events` inspection → fixture README contract → typed telemetry map → ENH-3676 handoff.

## Scope Boundaries

- **In scope**: native capture, fixture sanitization, component and request-identity proof, typed metric/channel verdicts, and a concrete ENH-3676 handoff.
- **Out of scope**: stored normalizer, lifecycle trigger, and reader cutover (ENH-3676); shared replay/refresh infrastructure (ENH-3534).

## Impact

- **Priority**: P3 — evidence is required before measured Kimi Code ingestion.
- **Effort**: Small to medium, depending on CLI/model access and cache behavior.
- **Risk**: Low to the current runtime; an unproved contract would create silent accounting errors downstream.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-29 | Priority: P3

## Session Log

- Pre-implementation epic review - 2026-10-07 - Tightened retained runtime/context evidence, required native position and generation proof for a source-position key, and reused the landed proof-path/sanitizer parity seam with numeric-field validation separate from string identity protection. Reduced captures remain field/order evidence; no native capture, status or readiness claim.

- Pre-implementation epic review - 2026-10-07 - Added the native identity-path recording requirement: ENH-3751 now sanitizes every raw_events insert and `pii._protocol_rules` is the only protection for replay-identity fields, so the matching delivery needs these paths from this evidence. No captured proof or readiness claim.

- Pre-implementation epic review - 2026-10-05 - Connected the existing acquisition-channel/logical-candidate evidence to ENH-3744's shared pure proof and ENH-3745's source-local progress contract. Native evidence/access/partial-support closeout rules remain unchanged; no captured proof or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Made usage-bearing proof conditional on a selected source and specified affirmative no-source closeout. Added acquisition-channel/logical-candidate handoff to the delivery and quality derive-status reader; existing access gates and evidence standards remain in force.
