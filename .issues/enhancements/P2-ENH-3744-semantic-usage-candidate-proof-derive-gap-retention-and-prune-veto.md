---
id: ENH-3744
type: ENH
title: Semantic usage-candidate proof, derive-gap retention and prune veto
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:27:33Z'
parent: EPIC-3562
labels:
- observability
- history
- usage-retention
blocked_by: []
relates_to:
- BUG-3735
- ENH-3731
- ENH-3732
- ENH-3745
- ENH-3746
- ENH-3747
- ENH-3751
- ENH-3770
testable: true
risk_factors:
- id: proof-limit-retention-cost
  domain: outcome
  criterion: complexity
  description: Whole-scope proof limits conservatively retain over-limit dependency
    components; initial aggregate calibration covers Claude, not Codex neighborhoods
- id: native-correspondence-context
  domain: outcome
  criterion: complexity
  description: Producer-specific snapshot dominance and dedup context must remain
    valid across independently committed source prune transactions
- id: per-source-prune-transaction-restructure
  domain: outcome
  criterion: complexity
  description: Prune moves from one operation-wide BEGIN IMMEDIATE to per-source transactions
    with cross-source revalidation and fail-fast partial commits
- id: sanitizer-identity-registration
  domain: readiness
  criterion: specification
  description: Every native identity path read by proof needs sanitizer-registry parity;
    unregistered evidence must remain bounded-unprovable rather than disappear
- id: writer-replay-seam-factoring
  domain: outcome
  criterion: change_surface
  description: Factoring native recognition/dedup seams out of writers.py replay paths
    must leave writer mutation and replay behavior unchanged
confidence_score: 85
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3744: Semantic usage-candidate proof, derive-gap retention and prune veto

## Summary

Add shared pure native candidate-correspondence proof and a semantic veto to production prune. A checkpoint alone cannot prove that retained usage represents every surviving logical candidate. This issue lands independently before ENH-3745's checkpoint/storage/completion work and ENH-3770's guarded reconciliation. It exports committed correspondence and retention dependencies; source completion and permission to mutate or release protection are separate decisions owned by those consumers.

## Current Behavior

On inspected branch `main`, `_plan_raw_prune` in `scripts/little_loops/session_store/lifecycle.py` treats a checkpoint at/above source max raw ID as sufficient derivation proof. Its `not capable` branch deletes eligible raw when a source has no linked usage and its max ID is at/below the checkpoint, so deleting a committed observation can hide a missing candidate in either branch. The source is currently planned and deleted under one operation-wide `BEGIN IMMEDIATE`.

`writers.py` contains the native Claude omission/snapshot and Codex notification/response-copy rules inside replay paths. `_iter_usage_replay_records` silently skips malformed JSON and non-object stored payloads; packed-payload corruption can also escape as an exception. Missing model/closure makes a Codex observation audit-only, independently of whether its request was captured. Source parsers additionally skip failures before raw insertion; durable evidence for those absent rows belongs to ENH-3745.

## Expected Behavior

- Every recognized logical candidate needs a compatible committed observation, or an actual native coalesced/deduplicated representation, before its raw can be pruned. Missing representation retains raw with `usage_derive_gap`. Safely captured partial/unknown audit observations satisfy conservation independently of canonical qualification.
- Recognized producer-specific terminal omissions need no fabricated observation: current-native-contract Claude malformed/partial/all-zero snapshots with the verified message identity, and Codex rate-limit-only notifications. Unsupported native grain, contradictory identity and corrupt retained inputs fail closed. A NULL persisted ingest-time qualification marker alone is not an unsupported native grain and cannot be promoted by proof.
- Verify replay-envelope, native payload and observation host/session/channel identity plus captured value semantics. A matching key or raw pointer alone does not prove representation. Disagreement retains raw/context and protection with a bounded unprovable reason; it cannot be classified as an excluded acquisition channel.
- Return the committed observations and retained native context on which each proof depends. Missing recognition/order/dedup context remains unprovable. Missing qualification-only model/closure does not invalidate otherwise proved audit correspondence. Retain enough context or explicit observation protection to prevent later replay from downgrading or duplicating retained evidence.

## Impact

- **Priority**: P2 — follow-up to the landed retention safety floor.
- **Effort**: Medium — pure native proof and source-scoped semantic prune veto.
- **Risk**: High — false correspondence or omitted context can discard unrecoverable usage evidence.
- **Breaking Change**: No

## Proposed Solution

Factor native producer recognition, omission, value capture, snapshot dominance and dedup into a pure helper and a total retained-input adapter. Use the helper as a deletion veto in both branches of `_plan_raw_prune`, evaluating committed observations before deleting raw. Keep the existing checkpoint and eligibility gates as necessary conditions and apply semantic proof only as an additional veto; conservative retention is an acceptable fallback. ENH-3745 later combines these outcomes with durable source-failure/boundary storage, and ENH-3770 consumes the evidence for reconciliation.

## Program Design

### Types

Proposed frozen `UsageCandidateProof` carries logical host/session/channel/native identity where provable, bounded `correspondence` (`represented`, `missing`, `intentional_omission`, `excluded_channel`, `unprovable`) and a bounded reason. Its internal evidence includes `matched_observation_ids`, required retained raw/context references, the native position supplying the observation's values and available committed source-generation facts. These references must identify the actual supplying source, including cross-source dedup survivors; they cannot substitute a convenient current path or another copy's position. Missing durable witnesses yield conservative unprovable evidence rather than a new migration here. Native keys, paths and raw/observation references never enter quality or shareable diagnostics.

Keep observation-protection dependencies separate from `matched_observation_ids`: an incompatible same-key contender may need preservation while proving no correspondence. Existing `USAGE_NOT_HELD_SQL`/`UsageReplayHolds` protection uses the observation's stored `source_path`, or a NULL-source host/channel population; an observation ID/raw pointer is not a hold. Protect the actual supplier's source, conservatively using the existing population hold when source attribution is absent. Marking only the candidate's current source does not protect another source's dedup survivor. No row-level protection migration belongs here.

This issue publishes correspondence and evidence only. ENH-3770 owns mutation, qualification-transition and hold-release permission; no positive mutation permission is granted here. ENH-3745 owns source-local completion and any new durable generation/pending/boundary witnesses. The helper receives all evidence explicitly and cannot infer it from filesystem paths or query storage.

Proposed `UsageReplayFailure` carries verified source/envelope scope, native position where available and a bounded decode/context error when no usable `UsageReplayRecord` can be produced. The retained-input adapter preserves every raw record, including malformed JSON, non-object payloads, invalid packed bytes, invalid UTF-8 and decompression failures. Ordinary corruption produces an unprovable outcome, not an observation or unchecked crash. Recognized benign non-usage records remain distinct from decode failures and producer-specific usage omissions.

Define the adapter so ENH-3745 can later supply durable failure dispositions for source lines rejected before raw insertion without fabricated raw IDs or original malformed bytes. This issue tests retained-row failure totality; the absent-row integration belongs to ENH-3745. Retained-only proof cannot newly certify the inventory of an older already-pruned or parser-filtered source. No separate candidate ledger, registry framework or competing boundary migration is introduced.

### Signatures

- Keep `prune(db, *, config=None, dry_run=False) -> dict` unchanged.
- `inspect_usage_candidates(records: Iterable[UsageReplayRecord | UsageReplayFailure], observations: Iterable[Mapping[str, Any]], *, channel: str | None = None) -> tuple[UsageCandidateProof, ...]` — new pure helper. Inputs contain a whole deterministically ordered retained proof scope plus all required native context and actual stored observations. Prune supplies its committed snapshot; ENH-3745 may supply post-write rows on its publishing connection under its atomic publication contract. Relevant representations include affected host/session/channel evidence across sources, rather than only this source's rows. Inspect compatible source scopes independently and compose only actual native cross-source dedup rules. No file reads, SQL queries/writes, pricing or write-normalizer calls.

### Call Path

`prune` → source-scoped `_plan_raw_prune` → total retained-input adapter → `inspect_usage_candidates` → transactional raw retention/protection and eligible deletion.

ENH-3745 consumes the exported proof for source completion; ENH-3732 consumes it through query-only retained-input reads. ENH-3770 later applies separate reconciliation decisions. None of those implementations is part of this issue.

### Decision Rules

| Correspondence outcome | Prune | Retained-reader handoff |
| --- | --- | --- |
| Represented | Raw eligible only with required context retained or equivalent observation protection | Conservation passes; qualification remains separate |
| Recognized intentional omission | No usage fabricated; retain context another candidate needs | Cannot count as observed zero or hide another gap |
| Missing | Keep raw/context | `derive_gap` |
| Unprovable identity/grain/context or corrupt input | Keep raw/context and protected observations | `derive_status_unavailable` |
| Proved excluded channel | No deletion permission from a filtered proof; prune inspects all channels | `out_of_scope` only if all session evidence is positively excluded |

- Proof is total over retained inputs and respects native grain. Several compatible Claude snapshots with the same qualified host/session/message identity coalesce; two distinct candidates with one observation remain a gap. Missing ingest-time markers never acquire qualification from retained replay. Terminal omissions require the actual verified host/version/native-ID rule, not a generic malformed/zero heuristic.
- A valid current-version checkpoint covering the source remains necessary for usage-bearing deletion, alongside the existing age/compaction/whole-source gates. Semantic proof only vetoes existing eligibility; it cannot bypass an invalid or lagging checkpoint or newly certify a complete source inventory. Checkpoint validation changes belong to ENH-3745.
- Evaluate candidates against committed observations **before** any prune deletion. A prospective insert or replacement is not committed representation. Prune consumes proof and preserves protection; it never derives usage, prices it, promotes qualification or releases existing holds.
- A native key proves request identity, not capture of every later candidate. `represented` requires compatible captured values from a proved dominating applied snapshot or actual producer coalescing/dedup. An older observation cannot certify a newer unresolved candidate solely because the key matches. Verify producer-normalized value semantics without requiring pricing or canonical qualification.
- An unkeyed audit row may correspond through its exact surviving raw link when envelope identity and captured value semantics match. With a correct pointer/session but contradictory tokens or model, retain the raw as missing/unprovable. Without a surviving link or native correspondence evidence, an existing audit row remains protected but cannot prove a candidate represented. Token/cost/timestamp equality alone never establishes correspondence.
- On Claude, compare payload `sessionId` with the verified replay envelope and retained observation identity; on Codex, also compare header/thread/native request context. Contradictions remain unprovable. Do not infer Claude resume/fork aliases without native fixture proof or silently reinterpret already-stored audit identities.
- Distinguish context needed to recognize request grain, native order or dedup from context needed only for measured qualification. An exactly linked compatible Codex audit row with missing model or `task_complete` may represent its captured candidate; it cannot promote itself or cover another missing candidate. A valid native Claude snapshot whose persisted qualification marker is NULL can likewise remain represented audit without acquiring a contract.
- Codex response-copy dedup follows the writer: key by proved host/response identity, then compare thread, turn and full native usage. Identical proved copies may share a committed representation; conflicting copies remain separate audit/unprovable candidates. Unkeyed notifications cannot borrow another source's representation. If the winner's original raw was pruned and remaining evidence cannot prove actual native-copy compatibility, retain the affected context/source.
- Codex `token_count` dedup compares both `total_token_usage` and `last_token_usage`, resets at `task_started`, and must not collapse changed last usage merely because the total did not advance. Native-record/notification pairing requires the writer's adjacent ordinal (`+1`), falling back to physical line (`+1`); equal token components alone are insufficient. Retain the context these decisions require.
- Deterministic SQL sorting is not native ordering proof. Keep paginated/reset/duplicate/contradictory positions source-scoped; when producer order needed for snapshot dominance or pairing cannot be established, retain the affected scope. Never turn the final raw-ID sorting tie-break into native order or merge ordinal resets across source pages.
- Plan, protection and deletion commit atomically **per source** under `BEGIN IMMEDIATE`. Re-read/revalidate all cross-source witnesses used by that source after earlier source commits; do not reuse stale proof from a precomputed operation-wide plan. Retention dependencies must remain valid regardless of source iteration order. A source whose proof would remove context needed elsewhere is conservatively retained unless equivalent committed protection/evidence is proved.
- First delivery collects a whole proof scope, with private limits of **10,000 combined raw/context/observation input items**, **64 MiB total stored/serialized input bytes** and **64 MiB total decoded payload text**. Include related-source context and observations selected by relevant native identities/exact raw links; never load a host-wide observation population. The collecting/decoding adapter enforces limits before materializing packed expansions, including a single oversized row, and treats decode/decompression/UTF-8/JSON recursion failures as bounded unprovable evidence. The pure correspondence helper receives explicit bounded inputs and knows no storage budget. Crossing a limit returns source-scoped `usage_proof_limit` with no partial candidate success, retains the affected dependency component/context/holds and vetoes deletion; discovery that cannot safely bound the component cannot grant deletion permission. No streaming windows, carry-forward state, new config or schema are required. Production and read-only consumers use the same adapter/fallback. Source scoping does not promise a short transaction for an arbitrarily large source.
- Initial budget calibration (2026-10-07, aggregate-only read): the 32 largest encoded Claude sources in the local store had at most 2,959 records, 8,273,996 decoded bytes per source and 3,653,779 decoded bytes per row. The 64 MiB/10,000-item bounds leave room for relevant context/observations; this sample does not establish Codex/cross-source coverage or remove the conservative retention cost. Tests shrink the private limits to exercise every threshold. Count over-limit sources and retained bytes internally; public prune keeps its existing result keys with bounded reasons/counts and never exposes native identities. Over-limit storage may remain retained indefinitely; a retry cannot promise resolution.
- Per-source failure is fail-fast: roll back the failing source, preserve earlier committed sources and stop further deletion. Keep the existing exception behavior, with a bounded failure message explaining that earlier sources may have committed and that retry is safe; do not expose source/native identities or claim whole-operation rollback. Re-running proof and prune is idempotent. Dry-run uses one read snapshot and writes nothing, including no temporary/rolled-back SQL writes. Carry an in-memory overlay of earlier planned deletions, raw-link changes and protection through the same deterministic per-source order/planner so later sources see equivalent evidence. Counts/reasons match actual prune absent concurrent changes.

### Delivery Plan (revised 2026-10-07)

The earlier mixed-owner MP1/MP2 plan is superseded by independently landable **whole issues**. `ll-auto`/`ll-parallel`/`ll-sprint` land one issue per branch, so no partial-issue or atomic multi-issue landing is required. Do not depend on epic-branch auto-merge for verification.

| Order | Whole issue | Deliverable and prerequisite |
| --- | --- | --- |
| 1 | **ENH-3744** (this issue) | Pure retained correspondence/evidence + semantic prune veto + sanitizer parity. Standalone; no ENH-3745 storage or checkpoint change required. |
| 2 | **ENH-3745** | Checkpoint safety (S0), pending/failure/derived-boundary storage and first positive completion consuming this issue's proof. `blocked_by: ENH-3744`. |
| 3 | **ENH-3770** (MP3) | Guarded reconciliation, held-source retry/addition, writer identity enforcement and hold release. Depends on ENH-3744, ENH-3745 and independent ENH-3747 search-survival work. |

ENH-3747 can land independently at any point before ENH-3770; it is not a prerequisite of this issue's pure proof or prune veto. ENH-3732 and ENH-3746 can consume proof/completion after ENH-3745 without waiting for MP3.

Each merge is independently fail-closed: this issue can veto existing deletions but cannot add trust to unproved evidence or mutate protected observations. It does not change cursor freshness, publish positive source completion, bump `_USAGE_DERIVE_VERSION`, alter `rebuild()` or its non-usage fingerprint, or replay already-linked raw rows. Legacy cursor/checkpoint behavior is unchanged by this issue. ENH-3745 owns malformed/contradictory checkpoint handling and pre-raw source failures; ENH-3770 owns destructive-path replacement. Deferred digest continuity, held/beyond-gap context-only promotion and figure-boundary witnesses remain with their owning issues, outside this issue's implementation and gate.

### Sanitizer Interaction

ENH-3751 canonicalizes newly stored history payloads, while legacy retained rows may be plaintext or rewritten later by `ll-session redact`. Every identity path this proof actually reads must be protected in `pii._protocol_rules` for its host/event type. Add a parity test against the finite registry and read only identity paths supported by the proved native shape. An unregistered path yields bounded unprovable retention, never an absent candidate or an assumption that redaction preserved its identity. Keep ENH-3751's canonical-payload and qualification-marker behavior unchanged; parser-refresh changes belong to ENH-3770.

The initial finite payload-path contract already present in `pii.py` is:

| Supported payload shape | Identity/context paths consumed by proof |
| --- | --- |
| Claude-shaped assistant | `type`, `sessionId`, `version`, `message.id`, captured `message.model` |
| Codex `session_meta` inner payload | `id`, `timestamp` |
| Codex `turn_context` inner payload | `turn_id`, `model` |
| Codex `event_msg` inner payload | `type`, `turn_id` |
| Codex `token_usage_record` inner payload | `thread_id`, `turn_id`, `response_id` |

Host/session/position envelope columns are separate from payload paths; numeric usage components are captured values, not identity exemptions. Test event-specific registry shapes and sanitizer preservation/refusal, and keep future unsupported native paths unprovable until fixture and registry parity establish them.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/writers.py` — factor existing native recognition/value-capture/coalescing/dedup and retained-input decoding into reusable pure seams without changing writer mutation or replay behavior.
- `scripts/little_loops/session_store/claude_usage.py` — reuse actual producer/omission rules without promoting missing ingest-time contracts.
- `scripts/little_loops/session_store/lifecycle.py` — per-source semantic `_plan_raw_prune` veto, cross-source witness revalidation, context/protection retention and fail-fast partial-commit handling. Leave checkpoint, catch-up and rebuild behavior to ENH-3745/3770.
- `scripts/little_loops/pii.py` — register a missing proof identity path only if the supported native shape requires it; enforce registry parity in tests.
- A small pure helper module under `session_store/` is permitted to avoid circular imports; no third-party dependency or persisted subsystem.

### Dependent Files

- `scripts/little_loops/history_reader/usage.py` — ENH-3732 consumes the pure retained-input proof; provide a tested importable interface without implementing quality here.
- ENH-3745 consumes bounded outcomes and owns source failures, checkpoint safety, completion and durable generation/pending facts.
- ENH-3770 consumes correspondence/evidence and owns safe mutation/reconciliation/hold release. ENH-3747 owns search survival; ENH-3746 owns retained-session admission and figure-boundary checks.

### Tests

Extend `scripts/tests/test_bug3736_usage_replay_holds.py` and add pure-proof/native-parity tests. Drive real Claude/Codex fixtures through ingest/derive and production prune; remove a committed observation to exercise both checkpoint-covered prune branches. Assert missing candidates retain raw, while genuine coalescing and compatible linked audit evidence do not invent gaps. Include a same-key newer candidate not captured by the older observation, a correct pointer with wrong captured values, and envelope/payload/observation identity disagreements.

Reuse controls from `test_session_store_incremental_usage.py`, `test_claude_usage_producer.py` and `test_enh3532_codex_rollout_usage.py`: Claude last-valid snapshots and terminal omissions; NULL qualification marker without promotion; Codex identical/conflicting response copies, unkeyed notifications, unchanged total with changed last usage, turn-reset notification dedup and ordinal/physical-line adjacency. Separate absent qualification-only model/closure from missing recognition/dedup context. Retained decode tests cover invalid JSON, non-object payloads, invalid packed bytes, invalid UTF-8 and decompression errors; absent-row source-failure storage integration belongs to ENH-3745.

Assert pure proof cannot read source files, query/write SQL, call pricing or invoke write normalizers. Test sanitizer identity-path parity. In actual prune, delete/protect one source before inspecting a source with cross-source dependencies, permute source order and ensure revalidation cannot discard required context. Force a second-source transaction failure: its rows/guards roll back, prior committed work remains, later sources are untouched and retry is safe. Dry-run writes nothing and matches actual count/reason/context plans on an unchanged database. Keep existing rebuild/refresh behavior as non-regression controls, not new reconciliation obligations.

Patch the whole-scope limits small and cover primary rows, related-source observations/context, single oversized plaintext/packed rows, compressed expansion and deeply nested JSON. No partial represented result can survive the limit; test that the entire affected component retains protection. A host-wide unrelated observation population must not trip a candidate-scoped budget. Test dry-run overlay against real multi-source commits, including raw-link disappearance and actual supplier holds/source-less population protection. Reuse the Codex paginated same-thread/reset-ordinal fixture as an order-proof control; raw-ID sorting cannot manufacture adjacency/dominance.

### Documentation

Update pure usage-proof and prune contracts in `docs/reference/API.md`, bounded retention/partial-failure diagnostics in `docs/reference/CLI.md` and semantic-veto limitations in `docs/guides/HISTORY_SESSION_GUIDE.md`. Explain conservative context retention, independent audit correspondence/qualification and safe retry after partial source commits. Identify source-completion and reconciliation as ENH-3745/3770 follow-ups. Keep internal native keys, paths and witnesses out of end-user diagnostics.

## Acceptance Criteria

- [ ] A current checkpoint cannot hide a missing logical candidate in either prune branch; its raw remains retained with `usage_derive_gap`. Genuine coalesced/deduplicated snapshots and compatible represented audit rows do not create false gaps.
- [ ] Envelope/native/observation host-session-channel contradictions and incompatible captured values remain bounded-unprovable with retained raw/context. An older matching native key or a raw pointer alone cannot certify a newer or differently captured candidate.
- [ ] Actual Claude terminal omissions and Codex rate-limit-only notifications fabricate no usage. Unsupported native grain, unregistered identity paths and corrupt retained inputs remain protected; absent qualification-only context or a NULL qualification marker does not invalidate proved audit correspondence or promote qualification.
- [ ] Internal proof exports matched committed observation references and all required native context/raw dependencies. Native dedup, conflicts, unkeyed notifications, nonadvancing totals and adjacency match concrete producer parity tests; insufficient surviving evidence takes a conservative retention fallback.
- [ ] Every native identity path read by proof is protected in `pii._protocol_rules` for its supported host/event type; a parity test fails loudly and unsupported paths yield a bounded retention reason.
- [ ] Prune plans/protects/deletes per source atomically, revalidates cross-source witnesses after earlier commits and preserves required context regardless of source order. A source failure rolls back only that source, stops further deletion and reports that prior commits may have occurred; retry is idempotent.
- [ ] Retained decode failures never disappear from proof. Recognized benign non-usage remains harmless. Whole-scope item/byte budgets and bounded packed expansion yield `usage_proof_limit`/unprovable with no partial success and conservative component/context retention; no streaming carry-forward implementation is required.
- [ ] Dry-run uses one read snapshot plus virtual prior-source effects, writes nothing and matches actual multi-source semantic plans/counts/reasons absent concurrent changes. Observation protection follows actual supplier source/population predicates, never an observation ID/raw pointer or candidate-source substitute. Prune and pure proof never derive, price, promote or release holds.
- [ ] The importable pure interface works with read-only consumer inputs and exposes no native keys/paths in shareable statuses. Retained-only proof does not certify absent historical source inventories; ENH-3745 can later supply its durable pre-raw failure evidence.
- [ ] The whole issue lands independently without ENH-3745/3747 changes, cursor/checkpoint semantics changes, storage migration, derive-version bump, `rebuild()` fingerprint change or replay of an already-linked raw row. `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

0. Re-run `/ll:confidence-check` after these contract refinements before implementation; the recorded standalone 85/71 scores below have not been recalculated for this review.
1. Factor and test pure native recognition/capture/coalescing/dedup with explicit committed-observation and retained-context evidence. Add total retained-input failure adaptation and sanitizer identity-path parity.
2. Wire semantic proof into both `_plan_raw_prune` branches; retain missing/unprovable candidates and dependencies, preserving existing whole-source gates/protection. Export bounded outcomes for later ENH-3745 and read-only ENH-3732 consumers without implementing their storage/completion work.
3. Refactor prune to per-source transactions with cross-source revalidation, calibrated whole-scope fallback, actual supplier/population protection, fail-fast partial commits and idempotent retry. Keep dry-run in one read snapshot with virtual earlier-source effects through the same planning logic.
4. Run real prune/native-parity/rollback controls, update the scoped contracts and run `python -m pytest scripts/tests/`.

## Scope Boundaries

No writer mutation, held-source derivation/retry, reconciliation, parser refresh, hold release, checkpoint/cursor semantics, independent freshness/completion storage, search restoration, reader admission, legacy promotion or repricing. Those belong to ENH-3745, ENH-3770 and their reader/search follow-ups. Conservative unprovable evidence may retain storage indefinitely; surface a bounded reason rather than silently discard it. No new whole-source completeness claim can come from a retained-only candidate window.

## Status

**Open** | Created: 2026-10-05 | Priority: P2

## Historical Confidence Check Notes (superseded)

The 2026-10-07 pre-split check recorded readiness **75/100** and outcome confidence **50/100**, with dimension scores complexity 5, test coverage 25, ambiguity 10 and change surface 10. It assessed combined proof/storage/reconciliation work and its mixed-owner delivery plan. Those fields were cleared by the scope-splitting review and replaced by the standalone checks below. The pre-split scores and paired-landing/destructive-path risk findings remain historical. This review does not recalculate the standalone result.

## Confidence Check Notes

The standalone checks recorded at 18:56:20 and 19:18:28 on 2026-10-07 both reported readiness **85/100** (PROCEED WITH CAUTION) and outcome confidence **71/100** (MODERATE). These are recorded assessments before this review's contract amendments, not recalculated scores.

### Review Resolution

- BUG-3736 is done and absent from `blocked_by`; the second check already removed its stale dependency risk.
- Whole-scope item/encoded/decoded limits now replace the unspecified memory/window rule, with aggregate Claude calibration and explicit `usage_proof_limit` fallback. Codex/cross-source retention cost remains an outcome risk.
- Supported event-specific Claude/Codex payload paths are now enumerated for `pii._protocol_rules` parity. Implementation must still prove that parity.

### Outcome Risk Factors

- Per-source prune transactions need cross-source witness revalidation and fail-fast partial commits.
- Factoring native recognition/dedup out of replay must preserve writer behavior under the existing producer/incremental/Codex regression suites.
- Snapshot-dominance/dedup context and actual supplier protection must survive independently committed source prunes regardless of source order.
- Over-limit scopes conservatively retain storage, and the initial size calibration does not establish Codex/cross-source liveness.

Re-run `/ll:confidence-check` for the amended contract before implementation; this review changes neither the recorded dimension scores nor the formal readiness result.

## Session Log

- Pre-implementation review #5 - 2026-10-07 - Pinned actual supplier/population hold predicates, separate protection versus correspondence references, dry-run virtual source effects, finite sanitizer paths and paginated/reset native-order controls. Replaced unspecified windows with whole-scope item/encoded/decoded caps and conservative component fallback; aggregate-only calibration of the 32 largest encoded Claude sources supports the initial constants but does not claim Codex coverage. Removed stale confidence ambiguity without rescoring. `/ll:advise` with Opus (confidence 0.70) supported applied-row transactional proof, scoped whole-input limits, component-specific refresh obligations and standalone rebuild invalidation in ENH-3745; its size-calibration uncertainty prompted the read-only aggregate probe. Existing producer/hold/incremental/refresh baseline: 121 passed. No implementation or new readiness score claimed.

- `/ll:confidence-check` - 2026-10-07T19:18:28 - `b97d96d3-c931-4dc1-998b-71841952c10d.jsonl`
- `/ll:confidence-check` - 2026-10-07T18:56:20 - `000f8816-1881-424d-9310-315d32e525a7.jsonl`
- Pre-implementation review #4 - 2026-10-07 - Replaced mixed-owner partial merge points with whole-issue order ENH-3744 → ENH-3745 → ENH-3770 (ENH-3747 independent before ENH-3770). Removed active reconciliation, checkpoint/storage, hold-release and deferred-promotion obligations from this issue and cleared obsolete pre-split scores. Pinned matched observation/context evidence, captured-value compatibility, audit correspondence separate from missing qualification-only context, native Codex parity, cross-source prune revalidation and fail-fast partial-commit/retry semantics. Opus second opinion (confidence 0.73) supported the whole-issue order, an additional veto over existing eligibility and the acquisition-accounting handoff; the parent review ran existing baseline controls (131 passed). Preserved earlier logs below as historical decisions; no implementation or new readiness score claimed.

_Earlier entries describe superseded combined scope and partial merge points; the current Delivery Plan and scope above control implementation._

- Pre-implementation review #3 - 2026-10-07 - Re-verified the Current Behavior claims against `lifecycle.py` (unguarded `int()` of the checkpoint, `max_id < checkpoint` destructive reset, `max_id == checkpoint` early return, checkpoint-only prune proof, `raw_events` AUTOINCREMENT, unique `source_raw_event_id` index, `test_enh3678` rebuild-fingerprint gate). `/ll:advise` with `claude-opus-5-5` (confidence 0.74) resolved the pending slicing decision: ordered fail-closed merge points MP0-MP3 instead of one atomic landing, Phase 2 deferrals, no version bump before MP3, per-source prune veto, sanitizer-identity parity gate, and "never route invalid checkpoint to the reset branch". Opus dissent noted: if MP3's version bump has a normalizer-output justification, dropping it would leave stale-meaning rows. Added 3 ACs, rewrote steps and the Delivery Contract. No implementation or new score claimed.
- `/ll:confidence-check` - 2026-10-07T16:32:13 - `2231707d-b3c0-49ab-b995-a5f45163a660.jsonl`
- Pre-implementation epic review - 2026-10-07 - Added landing mechanics (tooling lands one issue per branch; epic-branch mode auto-merges unverified), the ENH-3751 refresh-seam interaction and the sanitizer identity precondition for the pure proof, and the ENH-3747 search-loss coupling (verified: reset/rebuild wipe all usage search rows; preserving unchanged rows widens the loss from held/live to every preserved observation). Recorded Opus's slicing proposal as a pending decision with one verified premise correction (raw of usage-bearing sources is pruned today). No implementation or readiness claim.

- Pre-implementation review - 2026-10-06 - Reproduced complete/fresh publication after source decode skips, unchanged rebuild row/cost replacement, and Codex audit-to-measured qualification from later closure with unchanged numeric usage. Required pre-deletion reconciliation, pure prune/dry-run parity, protected two-phase refresh recovery and qualification-context witnesses. Opus consults (confidence 0.76 and 0.80) supported the changes; did not adopt harmless row-ID churn or weaker inode/tail generation proof. Existing targeted producer/retention/incremental/refresh suites: 111 passed; both revised issues passed structural checks. No implementation or readiness score claimed.

- Pre-implementation handoff review - 2026-10-06 - Reproduced a verified current-contract Claude payload becoming measured despite disagreement with the replay envelope's session. Added fail-closed identity controls, snapshot-dominance requirements and applied-value witness publication/rollback, including the older-request/later-update counterexample. Wired retry iteration to ENH-3745's source-local pending bound. Opus confidence 0.74 supported these handoffs; speculative Claude fork-copy reclassification was not adopted without fixture evidence. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Added the shared pure semantic-proof handoff, concrete lifecycle/refresh ownership, atomic hold-release and below-checkpoint recovery controls. A temporary-store probe with one deleted committed observation reproduced checkpoint-only pruning of all four raw rows; the missing candidate must remain protected. No implementation or new readiness score is claimed.

- Pre-implementation review - 2026-10-06 - Separated correspondence, mutation and completion; required safe additive held-source appends, total corrupt-input proof, actual cross-source Codex dedup and unchanged-cost no-ops. Assigned all shared generation/progress storage to ENH-3745 and required paired writer delivery. Opus confidence 0.72; rejected its raw-ID-only replacement rule because larger ingestion IDs can carry older source snapshots. Existing related suites: 188 passed; no implementation/readiness claim.
