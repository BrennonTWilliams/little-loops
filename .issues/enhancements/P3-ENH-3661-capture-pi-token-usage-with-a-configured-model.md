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
gate:
- kind: external
  satisfied: false
  owner: user
  evidence: "Configure a model API key for Pi (>=0.84.2) and run a tool-using + resume invocation. Pi 0.84.2 installed for ENH-3648 but no API key configured."
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

## Capture Boundary

`PiRunner` in `host_runner.py` is still a stub: every `build_*` method raises `HostNotConfigured`. OMP's runner records the cancellation of vanilla Pi orchestration (ARCHITECTURE-050). This evidence issue does not reopen orchestration or require a new Pi runner. A verified operator-provided native capture can satisfy the evidence contract; any automated CLI invocation must follow the repository's `resolve_host()` abstraction and cannot bypass the stub with a new hard-coded automation path. Keep unsupported capture tooling separate from the configured-model access gate.

The existing discovery/parser assumptions are unproved: `sessions.py` searches `.pi/projects/<encoded-cwd>/*.jsonl` and `parse_pi_transcript` uses `_parse_claude_shaped`. Capture the actual native layout and header before choosing a parser. Do not infer that Pi and OMP share a source contract from their common ancestry.

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

- [ ] Source-present or affirmative no-source completion follows **Completion Rule**; no-source evidence has a scoped native proof and unavailable-reader handoff, while unavailable access remains unknown. A selected source declares its acquisition channel and retained-raw logical-candidate identity for quality derive-status integration.
- [ ] For a selected usage-bearing source: The ENH-3672 handoff identifies a captured provider/version-qualified contract and an evidenced exact-version or compatibility rule, with matching and mismatch/absent-identity fixtures. Runtime values come from a verified native source; missing evidence remains audit-only/unavailable rather than inheriting a host-wide supported verdict.
- [ ] For a selected usage-bearing source: Capture and sanitize a real versioned Pi invocation with configured model access, a tool call, resume, and matching live/stored usage records; record the model and channel without exposing credentials.
- [ ] For a selected usage-bearing source: Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, and cache read/write; record the reasoning/output relationship separately. Prove inclusivity, omission, grain/reset behavior, and source identity where measured ingestion is proposed.
- [ ] For a selected usage-bearing source: Capture the actual storage root, workspace encoding, header/session/provider/version metadata, and physical-to-normalized event position rule. Document which native context fields the current parser drops and must survive raw retention. Include resume/copy ordering and source mutation behavior needed by the selected acquisition path; unproved generation/order cannot authorize value replacement or positive freshness. Update the fixture README recommendation to name ENH-3672 as the adapter/trigger/reader owner, replacing its stale ENH-3534 implementation handoff.
- [ ] Select the canonical native source/channel or record an evidence-backed no-source verdict; classify possible duplicate copies. Record provider/CLI version, excluded channels, and the non-duplication rationale in the fixture README and EPIC-3562 ledger. Record a candidate after-usage event and source-write timing, or an explicit unknown; the delivery issue proves the working trigger. Also record the native field path(s) that carry request/replay identity, model and the usage-bearing fields, and the event type the adapter will store them under — the input to the delivery's history-sanitizer path registration (EPIC-3562 § Shared Delivery Ownership).
- [ ] For a selected usage-bearing source: Give ENH-3672 a replay-ready native fixture and explicit normalizer recommendation; its own tests prove parser → stored observation → trigger → reader.
- [ ] If model access is still unavailable, record the precise missing configuration, leave native availability `unknown`, and keep this issue open or `blocked`. An authentication failure is not an unsupported-telemetry verdict.

## Completion Rule

The runtime qualification handoff above is required before releasing the delivery issue.

**Source-present versus no-source disposition:** the usage-bearing capture, request/replay identity, nonzero supported-cache and output/reasoning criteria apply only when selecting a usage-bearing canonical path. An affirmative no-source verdict instead supplies sanitized, versioned provider/source evidence demonstrating absence for the declared path, states the limits of that verdict, and names the delivery issue's unavailable-reader/fallback work in the epic ledger. It does not require inventing a usage-bearing fixture, request key or post-usage trigger for a nonexistent source. Authentication failure, an absent CLI, empty/zero-only samples and source-only speculation still cannot satisfy this branch. Keep any unproved in-scope path open; partial support uses the source-present branch for its proved components.

Mark this evidence issue `done` only when every metric/channel and identity rule needed for the selected canonical stored path has a supported or evidence-backed unsupported verdict. An unselected auxiliary channel may stay `unknown` only when the EPIC-3562 ledger names it as outside that path and explains why it cannot duplicate or change the canonical figure. If an in-scope field, request identity, or source path remains `unknown`, keep this issue `open` or `blocked`; completing the fixture alone does not release ENH-3672. The chosen canonical source and possible duplicate channels, or the evidence-backed no-source verdict, must be recorded in the fixture README and epic ledger before this issue is done. Resolve the reasoning/output relationship for any selected output path; if it remains unknown, keep this issue open because normalized output cannot be measured.

## Evidence Tiers (added 2026-09-30 after `/ll:advise` review)

Source-cited producer evidence (upstream source at a pinned version/commit, keyed by provider) is a **provisional lower tier** in the fixture README. `TelemetryCapability` has no tier or reasoning field: a source-only metric/channel stays `unknown` with a note naming that source; captured native evidence is required before marking it `supported`, and an `unsupported` verdict needs affirmative evidence. Record the reasoning/output relationship in the README and the `output_tokens` note, not as a separate telemetry metric. A captured identity/replay fixture is required for a selected usage-bearing source before this issue closes; affirmative no-source evidence follows Completion Rule instead. Capture a nonzero cache case when claiming a supported cache component's measured semantics that affect canonical figures or rates; an evidence-backed unsupported cache component does not require a nonzero sample. Source-only evidence does not release the delivery issue.

Fixture sanitization: strip credentials, tokens, absolute home paths and prompt content before commit; the pre-commit `ll-verify-private-refs` hook must pass. The first of ENH-3660/3665 to prepare a closing change owns the common verdict-table format and one parameterized README-to-`telemetry_matrix` evidence test; if both proceed together, ENH-3665 owns it. This issue adds its host's rows. The test covers only the six remaining hosts with a structured table; Claude/Codex and not-yet-captured hosts keep their existing verification. The test checks that each typed `supported` claim has captured native support for its metric/channel and a provider/version-scoped note, that `unsupported` has affirmative evidence for its stated scope, and that source-only evidence is never the sole support for a typed claim.

## Runtime Qualification Handoff

The usage-bearing contract and fixture requirements below apply to a selected usage-bearing path. An affirmative no-source handoff instead supplies the scoped native absence proof and unavailable-reader disposition defined in Completion Rule.

Give ENH-3672 the observed provider and CLI/source version, the native envelope or verified source of those values, and a stable fixture contract reference. Record whether qualification requires the exact captured version or permits a specific compatibility range backed by evidence. A current local CLI version alone cannot qualify a historical record. A host-level capability note does not qualify every provider/version.

Include a matching fixture and unmatched-provider, unsupported/unproved-version, absent provider/version, and unproved identity cases. Specify the audit-only/unavailable reason for each mismatch. The delivery issue persists the ingest-time contract/evidence on `raw_events` (using existing metadata where sufficient) and reuses it on rebuild; it must not substitute later machine configuration or promote an old unknown. No all-provider capture matrix or mandatory new column is implied. ENH-3731/3732/3733 implement ENH-3723's recorded shared eligibility policy, separately from this native evidence contract. The handoff also declares the normalized acquisition channel and a pure logical-candidate/key rule usable by ENH-3732's derive-status reader on retained raw evidence. This prevents a newly supported transcript source from being treated as excluded/non-usage while its observations are pending; a host name alone is not a channel rule. The matching delivery implements and tests that extension before production publication. Its retained-evidence rule must fit ENH-3744's shared pure recognition/key/coalescing/correspondence interface: distinguish a represented candidate, intentional no-observation and unprovable/missing native context. This issue supplies the evidence, not a second production proof engine; the delivery also tests pruning/held-source recovery and ENH-3745's source-local completion handoff. Supply the retained native identity/context and ordering evidence that ENH-3770's landed guarded planner needs for no-op, conflict and newer-snapshot decisions; raw ID or normalized enumeration alone is not native order. Unknown ordering permits conservative preservation, not a guessed replacement. Identify the exact value supplier and every separately retained provider/version/model/session/request context record actually consumed by qualification; header metadata lost during normalization is not durable evidence. The current shared `QualificationDependency`/schema role set is only `model` and `closure`: the delivery narrowly extends shared roles/position mapping if the selected source needs other context, or keeps affected positive proof unavailable. Do not mislabel a provider/header record as model/closure or invent a physical line for a normalized index.

## Program Design

- Use one stable row ID per native metric/channel/provider/version verdict, with evidence tier, inclusivity/omission semantics, native source, and duplicate-channel disposition. A table-backed `TelemetryCapability.note` cites `README:<row-id>` for each supporting verdict; the shared test joins those IDs without treating a host-level entry as proof for every provider. Document in `host_runner.py` that `token_reporting_summary: full` describes native field availability, not stored measurement.
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

## Session Log

- Pre-implementation epic review - 2026-10-08 - Separated Pi telemetry evidence from the cancelled orchestration lane and documented the frozen runner/discovery/parser assumptions. Added real native layout/context/position and guarded-replay evidence handoff, plus correction of the fixture README's stale delivery owner. Model-access gate and status remain unchanged; no native capture or readiness claim.

- Pre-implementation epic review - 2026-10-07 - Added the native identity-path recording requirement: ENH-3751 now sanitizes every raw_events insert and `pii._protocol_rules` is the only protection for replay-identity fields, so the matching delivery needs these paths from this evidence. No captured proof or readiness claim.

- Pre-implementation epic review - 2026-10-05 - Connected the existing acquisition-channel/logical-candidate evidence to ENH-3744's shared pure proof and ENH-3745's source-local progress contract. Native evidence/access/partial-support closeout rules remain unchanged; no captured proof or readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Made usage-bearing proof conditional on a selected source and specified affirmative no-source closeout. Added acquisition-channel/logical-candidate handoff to the delivery and quality derive-status reader; existing access gates and evidence standards remain in force.
