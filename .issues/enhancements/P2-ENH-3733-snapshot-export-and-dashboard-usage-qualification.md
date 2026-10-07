---
id: ENH-3733
type: ENH
title: Snapshot export and dashboard usage qualification
priority: P2
status: done
discovered_by: issue-size-review
discovered_date: '2026-10-05'
completed_at: '2026-10-07T17:17:39Z'
parent: ENH-3723
decision_needed: false
testable: true
blocked_by:
- ENH-3731
relates_to:
- ENH-3732
- ENH-3543
- ENH-3730
- BUG-3735
- ENH-3748
size: Large
risk_factors:
- id: export-only-overflow-exception
  domain: readiness
  criterion: architecture_compliance
  description: snapshot_integer_overflow is a consumer-only deviation from source/snapshot
    numeric parity.
- id: int64-bigint-split-undecided
  domain: outcome
  criterion: ambiguity
  description: Int64 subtotal guard and BigInt read may be split into P4 bugs if size
    review gates it; not yet decided.
- id: qualification-shared-state-depth
  domain: outcome
  criterion: complexity
  description: Model-wide qualification, per-channel contributions and one read snapshot
    interact across functions.
- id: snapshot-export-caller-surface
  domain: outcome
  criterion: change_surface
  description: build_snapshot_db has several callers (dashboard, serve, loop run)
    that must stay compatible.
- id: snapshot-selector-extension
  domain: readiness
  criterion: duplicate_implementations
  description: Snapshot selector and _SnapshotTotals already exist; work extends them
    rather than starting clean.
- id: wide-test-doc-site-count
  domain: outcome
  criterion: complexity
  description: About nine change sites span queries, template, five test files and
    two reference docs.
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3733: Snapshot export and dashboard usage qualification

## Summary

Route shareable snapshot accounting through the landed `qualify_usage`, export bounded qualification/provenance/reason/policy metadata and make the built-in dashboard distinguish unavailable figures from measured zero. Preserve audit evidence and the recorded model-wide qualification scope. This work can proceed independently of quality and retention followups; it adds neither derive-status nor cache-rate figures.

## Parent Issue

Decomposed from ENH-3723. Recorded Decision (commit `01747bb96`) makes legacy NULL/unknown observations audit-only, complete estimated consumption labeled numeric, and rates measured-only. ENH-3731 is done; this issue consumes its actual API.

## Current Behavior

On inspected branch `main`, `_snapshot_usage_selection` in `scripts/little_loops/session_store/queries.py` qualifies only model coverage and per-column missingness. A partial/unknown row with numeric stored cost can supply canonical token/cost components. `_SnapshotTotals` accepts invalid/non-finite costs; the predefined dashboard query omits qualification reasons and NULL renders as an empty cell. A temporary-store probe with two valid `2**62` token contributors qualifies in the source reader but crashes snapshot export because the resulting Python integer exceeds SQLite's signed integer range. Separately, the dashboard's default `stmt.getAsObject()` read rounds an exactly stored `9007199254740993` to `9007199254740992`; the bundled sql.js supports exact BigInt reads. Source schema is currently 61 (2026-10-07; v60/v61 are unrelated loop/skill columns); computed snapshot tables are not source migrations.

## Expected Behavior

- Coverage reconciliation precedes report-window filtering; qualification uses all in-filter annotated audit contributors. An out-of-window audit-only row alone does not taint another window, but an overlapping counterpart outside the window still prevents coverage certification.
- Build one `ObservationGroup` per logical model from every in-filter audit contributor, including unresolved and audit-only rows. Qualify tokens together and cost separately. The entire model's eligibility controls each channel's canonical contribution: a channel subset cannot recertify an incomplete model. Model-wide reason/provenance labels accompany per-channel values and are described as such.
- Audit/coverage-selected observations and counts stay intact. No observations is empty/unavailable; qualified zero is zero. Missing/invalid/audit-only rows make dependent canonical values NULL with reasons, without claiming the remaining subset is complete. Valid tokens can remain numeric when cost alone is unavailable.
- Normalize computed buckets with `row_channel` and `UNKNOWN_MODEL_BUCKET`; preserve original raw model/channel/provenance in observation exports. A source reader whose public grouping key remains NULL is compared through an explicit NULL-to-bucket mapping. Derived `mixed` is allowed in computed aggregate metadata, without storing it as producer provenance.
- Generated raw/known audit subtotals apply the same valid-value and finite-sum rules as source `ObservationGroup` subtotals. Unknown-but-valid values remain labeled audit sums. Invalid values are not silently admitted or allowed to create non-finite SQL values; missing/invalid count meanings are documented and do not claim qualified completeness.
- Check generated integer subtotals against SQLite's signed 64-bit range before binding. An unrepresentable raw/known token subtotal becomes NULL without losing observation rows/counts; if any canonical channel token subtotal overflows, all canonical token components for that model become unavailable with `snapshot_integer_overflow`. Cost remains independently qualified. This export representability failure does not make valid producer observations invalid or change shared qualification. Never round/clamp to fit, switch exact integers to REAL, or let the whole export crash.
- Read representable SQLite INTEGER values exactly through the dashboard's shared query path, including custom SQL. Preserve exact decimal display above JavaScript's safe-integer range, numeric zero and REAL cost values; exact snapshot storage alone is insufficient. This is a row-read/display change using the existing runtime, with no SQL rewrite, vendor upgrade or extra snapshot exception.
- New reason/version/label fields contain only approved bounded codes/literals. A lexical snake_case/length check alone is insufficient: an identifier-shaped source secret must become `unclassified`. Preserve existing approved observation columns (including already-allowlisted `session_id`/`invocation_id`); add no native request/turn IDs, raw links, paths, credentials or source-derived prose. The metadata change does not expand identity export permissions.
- Keep existing public numeric fields. The snapshot has no rate column and gains none; cache-rate measured-only/zero-denominator criteria are source-reader parity controls. Custom SQL stays unchanged and is described as an audit tool: `SUM` over selected rows or NULLs does not certify a complete population.

## Proposed Solution

Apply model-scoped token/cost qualification to generated canonical columns, add aggregate metadata to `usage_coverage_audit`, and expose explicit availability/reasons in the predefined query. Keep the existing five-key `HistoryPayload`, table set and export return contract.

### Recorded Policy-Version Decision

`/ll:decide-issue` selected Option C: `qualification_policy_version` on each generated `usage_coverage_audit` row. It travels with a retained standalone snapshot and needs only the existing allowlist/DDL/insert edits. Keep that decision; no new table, page stamp, template-manifest key or payload field.

Empty generated usage tables have no audit rows/figures and consequently no policy-version row; test and document this. A new export from a pre-v55 source store still generates the current audit schema and policy metadata, with absent provenance remaining unknown/audit-only. Retained old snapshot databases and standalone HTML files lacking these columns/view remain historical audit artifacts, not certified under the current policy; regenerate the dashboard to obtain the new view. There is no snapshot import or old-page retrofit in this work. Exports without `usage_event`, and live payloads for a missing source store, need not contain usage tables; those differ from an empty generated audit table. The qualification-policy version differs from export-allowlist/source-schema/coverage-policy versions and comes from the shared result, never a copied literal.

## Program Design

### Types

Consume implemented frozen `UsageQualification` fields `eligible`, `provenance`, `reason`, `contributors`, `rejected_contributors`, `component_counts`, `policy_version` and `counts(column)`.

Add exactly these aggregate metadata columns to `usage_coverage_audit`: `provenance`, `qualification_reason`, `cost_qualification_reason`, `qualification_policy_version`. Their scope is the whole in-filter logical model, repeated on each channel row. Keep `coverage_reason` distinct from accounting reasons. `selected_usage_events.provenance` remains the raw stored value; no row-level qualification columns are needed.

Reuse `_SnapshotTotals` for per-channel raw/coverage-selected contributions, with shared validity/finite-sum behavior. Track NULL versus present-invalid internally. Fix the export schema to exactly the four new metadata columns above; add no diagnostic-count columns. Existing `raw_missing_cost_count` and `known_missing_cost_count` count SQL NULL only, matching shared `missing_count`; invalid inputs are excluded from valid-value subtotals and reported through the existing bounded qualification reasons. This corrects the current conflation of invalid and missing, so document the changed count semantics under the new allowlist version. Aggregate overflow increments neither missing nor invalid contributor counts. Never change the shared `ObservationGroup.channel_subtotals()` shape to add cost.

Use an explicit snapshot-export reason allowlist combining `USAGE_QUALIFICATION_REASONS`, the consumer-only `snapshot_integer_overflow` literal and the enumerated shared coverage reason codes. Unknown code → `unclassified`; stable sorted joins for coverage reasons. No arbitrary source text is admitted merely because it passes the old sanitizer. Shared qualification failures keep their existing precedence; use the export overflow reason only when shared token qualification otherwise succeeds.

### Signatures

- `_snapshot_usage_selection(conn: sqlite3.Connection, since: str | None) -> None` — keeps store-wide `select_usage_coverage(conn, since=since)` acquisition (`channel=None`).
- Existing `build_snapshot_db(db, dest, *, tables, since=None, local_mode=False) -> str | None` keeps its source-schema-version return contract.
- Existing `qualify_usage(group, *, require_cost=False, measured_only=False) -> UsageQualification` is called separately for tokens and cost; no qualification-core changes.

### Call Path

`build_snapshot_db` → one source read transaction → coverage selector → model groups over audit contributors → shared qualification → per-channel canonical contributions and aggregate metadata → generated tables.

`build_history_payload` → embedded snapshot → dashboard `PREDEFINED` query → visible availability/reasons. Metadata remains in the snapshot on live refresh; no new page/payload stamp.

### Decision Rules

- Model-wide qualification cannot be derived from `selected_rows` alone, a channel subtotal or raw numeric stored cost. Shared qualification reason precedence is consumed unchanged.
- Every canonical token component is NULL together when token qualification fails; cost uses its own result. Selected/audit counts and raw evidence remain diagnostic.
- Qualification and export representability both precede canonical token publication. The bounded overflow exception is the only source/snapshot numeric-parity exception introduced here; the shared result and policy version are unchanged. Audit subtotal NULL may mean no valid values or an unrepresentable sum, not an invented missing/invalid contributor.
- Check token representability on channel subtotals actually bound to generated INTEGER columns. An unbound model total exceeding int64 does not by itself suppress individually representable channel values. Cost eligibility still checks the whole model's finite sum: finite channel costs cannot recertify a model whose shared cost sum overflows.
- Create audit channel rows only for actual in-filter observations. A nonempty qualified channel whose observed components are all zero has numeric zero; an empty channel/model/window gains neither a row nor a fabricated zero. Dashboard availability requires a non-NULL canonical value as well as applicable model-scoped metadata.
- Rename the predefined view to `Usage by model and channel`; select all four existing canonical token components directly alongside canonical cost, audit subtotals/counts and the four model-scoped metadata fields. Add query-result `token_availability` and `cost_availability` fields with `available`/`unavailable` literals, without adding snapshot columns. Token availability requires all four canonical token values and no token qualification reason. Cost availability independently requires canonical cost and no cost qualification reason; token export overflow must not hide eligible cost. NULL canonical values are unavailable even when the model reason is NULL; a channel with zero selected contributions has no canonical figure, rather than a model qualification failure. Preserve the model reason fields unchanged and explain this channel case alongside the selected count. Never re-sum observation rows, perform token arithmetic (including `+`, `SUM` or `TOTAL`), add a derived total-token column or coalesce canonical NULL to zero. Preserve four-decimal USD presentation, but compute availability from the unrounded stored cost: positive `0.00001` remains available even when displayed as zero. Custom SQL continues to expose the original REAL value.
- In `runQuery`, acquire rows with `stmt.getAsObject(undefined, {useBigInt: true})` for both predefined and custom queries. Keep `String(value)`/`textContent` rendering, the row cap, submitted SQL and REAL reads. Do not convert BigInt back to Number or serialize query rows with JSON; existing interaction payloads carry no query-row values. Zero displays as `0`, never `0n`. The existing bundled sql.js/WASM needs no edit.
- Acquire source version and exported source rows from the same read snapshot; move `read_schema_version` inside the existing export transaction if needed. Generated raw/selected/audit tables must never describe different source commits.
- Keep the recorded Option C and legacy/empty behavior. Unknown historical provenance, unresolved coverage and unpriced cost can legitimately leave an unscoped dashboard unavailable after implementation.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection`, `_SnapshotTotals`, `_SHAREABLE_COLUMNS`, generated `CREATE TABLE` DDL, insert tuple/column order and export-reason admission; coherent source-version read in `build_snapshot_db`.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — predefined usage query with four canonical token fields, independent token/cost `CASE` availability, exact INTEGER retrieval in the shared `runQuery` loop and visible model-scope/availability/reason/custom-SQL guidance. The shared renderer already handles BigInt through `String`. Keep numeric zero numeric and unavailable NULL; USD rounding is presentation only.

### Dependent Files

- `scripts/little_loops/token_provenance.py` and `history_reader/usage.py` — consume existing qualification/coverage APIs unchanged.
- `scripts/little_loops/cli/artifact/dashboard.py`, `serve.py` and `cli/loop/run.py` — existing snapshot callers and five-key payload remain compatible; no manifest/page-stamp edits required.
- `scripts/little_loops/session_store/schema.py` and `schema_manifest.json` — no source-history migration. Read current source schema dynamically, not a pinned issue-era number.

### Tests

- `scripts/tests/test_enh3543_snapshot_usage.py` — extend real `_source_db` fixtures for partial/unknown/mixed/unpriced/invalid rows, NULL model/channel, coexisting channel contributions, `since` and out-of-window overlap. Compare source `aggregate_usage`/`cost_attribution` token/cost qualification and audit subtotals on the same store; selected/raw rows and counts remain intact.
- Assert all four token canonical fields change together, token/cost independence, unavailable vs zero, all-invalid audit values and finite-sum overflow; prove a complete channel cannot recertify an incomplete model. Compare qualification at the model scope, not a separately qualified channel.
- Add a measured model with one NULL cost and one stored infinite cost: raw/selected missing-cost counts are exactly 1, cost reason is `invalid_cost`, valid tokens remain available and no invalid-cost subtotal is published. Check invalid token/cost inputs separately from missing and aggregate-overflow cases; no extra diagnostic columns appear.
- Add two measured `2**62` contributors in one channel, a second complete channel of that model and an unaffected model: export succeeds, oversized raw/known subtotals are NULL, model-wide canonical tokens are NULL with the bounded overflow reason, and independently qualified costs remain numeric. Check the exact signed-64-bit boundary and insertion permutations without changing approved raw observations. Query generated fields rather than re-summing raw integers in predefined SQL.
- Add two demonstrably disjoint verified channels each contributing `2**62`: assert `coverage='non_overlapping'` and both canonical channel contributions stay exact and available, even though the unbound model token sum is `2**63`. Compare source channel contributions rather than requiring a snapshot model-total column. Contrast finite `1e308` cost in each channel: shared model cost qualification fails `invalid_cost` while tokens remain independent. Check both insertion orders; the export range guard must not become a new model-wide token policy.
- Add a deterministic WAL concurrency test: wrap the module's `read_schema_version` so a raw SQLite writer with `timeout=0` commits a version change and a usage row immediately after the version read, before returning to `build_snapshot_db`. The returned version, raw/selected observations and audit rows must all describe the same earlier committed revision; the source writer's later revision remains intact. This fails against version acquisition outside the read transaction. Also inject a write at the coverage-selector seam after raw copying to guard against ending/reopening the transaction between raw and generated tables. Set the fixture to WAL explicitly; do not use the migrating store opener or rely on sleeps, a `BEGIN` substring assertion or rollback-journal writer blocking.
- Leak tests scan snapshot bytes for source/native-ID sentinels and inject both prose and a syntactically valid identifier-shaped sentinel into reason inputs; new code fields must become `unclassified`. Preserve existing approved identity columns rather than asserting that all session IDs vanished.
- `scripts/tests/test_feat3304_artifact_dashboard.py` — allowlist hash/version lockstep, `PRAGMA table_info` order, policy version, empty/legacy/pre-v55 behavior, deterministic gzip bytes and actual predefined SQL execution on a real generated snapshot through stdlib SQLite. Update `TestSnapshotRoundTrip.test_predefined_usage_view_uses_qualified_audit` for the renamed/widened view; extend `test_pre_v55_db_exports_without_error` for current metadata and canonical NULL/reasons. Require numeric zero, NULL cost plus visible unavailable reason, unknown-model bucket and model-wide taint cases; a substring assertion alone is insufficient. The view returns zero rows for empty generated usage tables. Retained old HTML/database files are not retroactively upgraded. Include a token-overflow model with eligible cost and an audit-only channel with no selected contribution to prove independent value-based availability. Use separate complete measured models for costs `0`, `0.00001` and NULL so an unpriced contributor cannot taint the other two controls; presentation rounding must not drive availability.
- `scripts/tests/js/feat3304/feat3304_dashboard_runtime.test.mjs` — execute the generated page's own `runQuery`/`renderTable` with a small DOM stub against embedded snapshot bytes, without a new dependency. The existing test repeats engine calls and does not yet execute that page loop; an engine-only probe or template substring check cannot close the rendering criterion. Exercise the actual predefined usage query and a custom query of generated token fields: `2**53-1`, `2**53`, `2**53+1` and `2**63-1` render as exact decimal strings, zero as `0`, NULL with the applicable independent availability/reason fields. Use fully qualified boundary rows in separate models so their sums do not trigger the export guard and erase the intended precision controls. Check predefined costs against their four-decimal presentation and custom SQL against original REAL values, including a small positive cost rounded to display zero. Require the SQL text and row cap to remain intact, with no BigInt query-row JSON serialization. Existing pytest Node gate runs wherever Node is available and skips gracefully when absent; `LL_REQUIRE_NODE=1` makes missing Node a failure. Do not misdescribe it as opt-in-only or add a CI workflow.
- Preserve `scripts/tests/test_feat3323_sse_bridge.py`, `test_remote_operation_matrix.py` and `test_usage_selection_chokepoint_gate.py` for payload, export signature/return and selector seams.

### Documentation

Update snapshot/table/qualification scope, policy-version, old/empty snapshot, NULL-only missing-cost count semantics and custom-SQL guidance in `docs/reference/API.md` and `docs/reference/CLI.md`; correct stale allowlist documentation. Distinguish regenerated pre-v55-source dashboards from retained old artifacts, and explain independent availability plus presentation-only USD rounding. State that the page preserves exact SQLite integers; do not imply SQL arithmetic beyond SQLite's range is supported. `docs/reference/CONFIGURATION.md` changes only if mentioning policy metadata. Use end-user wording; run audience gates. No release/changelog edit here.

### Configuration

Bump `_SHAREABLE_ALLOWLIST_VERSION` with every allowlist edit and update `TestAllowlistVersionLockstep.PINNED_VERSION`/`PINNED_HASH` in the same commit. Keep generated schema column order synchronized across allowlist, DDL and insert tuple. Source `SCHEMA_VERSION` and dashboard manifest/payload stay unchanged.

## Acceptance Criteria

- [x] Source/snapshot token and cost qualification agree for measured/estimated/mixed, partial/unknown, invalid and unpriced contributor populations; rejected rows cannot create a canonical subset. Valid sums outside SQLite's integer range follow the documented consumer-only unavailable exception without crashing or rounding.
- [x] Full-identity coverage precedes filtering; window/channel/model controls preserve completeness, approved raw/selected evidence and observation counts. Logical NULL buckets and whole-model metadata are documented.
- [x] Canonical unavailable fields are NULL with bounded reasons; observed zero remains numeric zero. Empty channels/models create no figures or artificial zeros. Generated audit subtotals obey shared validity/finite-sum/range rules without failing on invalid or unrepresentable values; missing-cost counts mean NULL only, and invalid/overflow values do not inflate them. Exactly four new metadata columns are added.
- [x] New metadata is strictly allowlisted and leak-tested against both prose and identifier-shaped sentinels; approved existing observation identities remain unchanged.
- [x] Aggregate label, separate token/cost reasons and shared policy version travel on audit rows. Old snapshots are audit-only; empty new snapshots have neither figures nor a version row. No rate/page-stamp/payload/table additions.
- [x] Predefined SQL is executed in ordinary pytest against real generated snapshots and displays unavailable vs zero correctly. The generated page's own query/render path passes Node controls for exact integers through `2**63-1`, REAL costs, zero, NULL and row caps wherever supported. Custom SQL is unmodified and receives truthful completeness guidance; no BigInt query-row JSON serialization or vendor edit is needed.
- [x] The predefined usage view includes all four canonical token components and independent token/cost availability. Token export overflow can coexist with available cost; positive cost below display precision remains available. Unrounded custom-SQL REAL values, zero-row empty generated tables and current metadata on newly exported pre-v55 source stores pass the real SQL/page controls.
- [x] Two disjoint channels with representable `2**62` token subtotals remain available despite an unbound model sum above int64; finite per-channel costs whose shared model sum overflows stay unavailable with `invalid_cost`. A WAL writer committing between version acquisition and export reads cannot produce mixed-revision source metadata/raw/selected/audit tables.
- [x] Generated tables and source-version metadata use one source read snapshot; concurrent writes cannot create internally inconsistent export. Schema/allowlist/hash lockstep, reproducibility and five-key live payload controls pass.
- [ ] `python -m pytest scripts/tests/` exits 0. (1 failure + 8 errors reproduce on clean `main`: `test_next_loop_golden`, live `test_libsql_integration`.)

## Impact

- **Priority**: P2 — audit-only observations currently reach shareable accounting.
- **Effort**: Large — coordinated generated-table, dashboard, privacy and parity test changes; landed qualification removes the earlier core dependency work.
- **Risk**: Medium — canonical availability/bucket labels and allowlist version change; raw evidence stays accessible.

## Scope Boundaries

No qualification-core change, new source-history migration, quality/derive-status/source-freshness implementation, snapshot rates, custom query engine or ENH-3730 gate redesign.

## Implementation Steps

**Sequencing (2026-10-07):** this issue's only blocker (ENH-3731) is done and it has no dependency on the retention/progress followups, so it is the cheapest unblocked win in the epic. Do the core model-wide qualification, metadata columns and predefined-SQL work first. The SQLite signed-int64 subtotal guard and the dashboard exact-integer (`useBigInt`) read are real, reproduced robustness controls but need token sums above `2**53`/`2**62` to matter in practice; keep them in this issue unless size review gates it, in which case split them into standalone P4 bugs — they must not delay the qualification work.

1. Build per-model audit groups and independent token/cost qualification using the landed API; align logical buckets and audit validity.
2. Add the four bounded metadata columns, synchronize allowlist/DDL/tuple and bump allowlist/hash pins. Preserve Option C, old/empty behavior and a coherent export snapshot.
3. Update predefined SQL/guidance and exact shared row reads; execute the SQL through normal pytest and the generated page's query/render loop through the Node gate.
4. Extend source-parity, privacy and deterministic-export controls, update docs and run the local suite.

## Confidence Check Notes

Historical missing-core checks in the log are superseded: ENH-3731/3748 exist on `main`. Export/template/privacy integration remains unimplemented. The 2026-10-07 confidence pass restored 90 readiness / 71 outcome scores after the earlier clearing. This review clarifies the actual predefined query, legacy artifact behavior and discriminating range/concurrency controls; those scores were cleared with `ll-issues set-scores --clear` because they predate these revisions. Re-run confidence for the revised contract before implementation. No new score is claimed.

## Verification Notes

Pre-implementation review (2026-10-07, initial HEAD `a9c31cc39`): clarified the predefined token/cost projection and independent value-based availability, preserved display-only USD rounding, distinguished regenerated legacy-source exports from retained old artifacts, and added discriminating channel-range/WAL controls. Parent/epic handoffs now use the landed API and annotated-audit population. This is an issue revision, not implementation or a fresh readiness score.

- `/ll:advise` with Opus (`--model opus`, confidence 0.80) supported these corrections. Adopted direct token-field projection without arithmetic, explicit version-read/selector injection seams, non-vacuous coverage assertions and existing-test update sites. Preserved the recorded Decision and dated probes while correcting current parent directives. A local SQLite 3.49.2 probe accepted `ATTACH` inside `BEGIN`, so the consult's contrary restriction was not added.
- Existing qualification/provenance/snapshot/dashboard/selector suites: **198 passed**. Issue dependency/evidence corpus gates: **4 passed**. These controls verify the existing baseline; the new implementation tests specified above remain to be written. Changed-file evidence, structural/design and acceptance-automation checks are clean.
- Cleared the restored 90/71 scores through the supported CLI; ENH-3731 remains a satisfied dependency and quality/retention followups remain independent.

Verdict at time of check: **VALID** (2026-10-06; corrected contract on inspected `main` at `ec36b137d`, not an implementation or refreshed confidence pass).

- Current-behavior claims hold on `main`: the snapshot selector builds per-channel totals from selected rows without calling `qualify_usage`, the totals class accepts any numeric cost (no finite check), `read_schema_version` runs before the export transaction begins, and the source schema version was 60 at that check (61 on 2026-10-07; the export must keep reading it dynamically).
- Referenced API exists: `UsageQualification` (with `counts`, `policy_version`, `rejected_contributors`, `component_counts`), `qualify_usage`, `USAGE_QUALIFICATION_REASONS`, `UNKNOWN_MODEL_BUCKET` and `row_channel` in the token-provenance module.
- Allowlist pins hold: allowlist version 3 with a lockstep test class pinning version and hash; the dashboard template's predefined query already reads the audit table; the Node gate honors `LL_REQUIRE_NODE`.
- Actual vendored sql.js/WASM probe: default row retrieval returned `9007199254740992` for SQL integer `9007199254740993`; BigInt retrieval preserved the exact decimal. Added shared page-loop precision controls through the signed-64-bit boundary, including custom SQL, without a vendor change.
- Resolved diagnostic-column ambiguity: exactly four new metadata columns; existing missing-cost counts mean NULL only, with invalid inputs tracked internally and exposed by bounded qualification reasons. The already-required allowlist bump documents the semantic change too.
- Dependencies: ENH-3731, ENH-3748, BUG-3735, ENH-3543 and parent ENH-3723 are done; ENH-3732 and ENH-3730 (relates_to only) are open. The single `blocked_by` edge is satisfied.
- Evidence-quote check clean; format-check reported no gaps; no required decision rules exist.
- Proposal-vs-code check: no refuted mechanism found; every Integration Map entry maps to a criterion or step.
- Opus consult (`claude-opus-5-5`, confidence 0.78) supported the exact reads and fixed column scope. Kept a real page-loop test despite its cheaper static/engine-only alternative, since those do not exercise the failing read/render seam. Existing related suites: **233 passed**; proposed implementation tests remain to be written.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Risk Factor Delta
- Added: `int64-bigint-split-undecided`
- No longer reported: none
- Retained: `export-only-overflow-exception`, `qualification-shared-state-depth`, `snapshot-export-caller-surface`, `snapshot-selector-extension`, `wide-test-doc-site-count`
- Changed fields: none

## Session Log

- `/ll:manage-issue` - 2026-10-07T17:17:39 - `bc545c3f-f96c-4059-84c3-601caf2c25c7.jsonl`
- `/ll:ready-issue` - 2026-10-07T16:56:21 - `c3217ded-bd6e-47d6-8550-bc50b893cca6.jsonl`
- `/ll:confidence-check` - 2026-10-07T16:51:58 - `8d2a4672-0c21-4e88-b585-9393828cb9fc.jsonl`
- Pre-implementation review - 2026-10-07 - Specified token-bearing predefined SQL, independent unrounded-value availability, isolated zero/small-positive/unpriced fixtures, regenerated-vs-retained legacy artifacts and discriminating WAL/channel-boundary tests. Corrected parent/epic API and population handoffs; Opus supported the changes (confidence 0.80). Existing baseline: 198 passed; issue corpus gates: 4 passed. Cleared prior confidence scores; no implementation or refreshed readiness score claimed.

- `/ll:confidence-check` - 2026-10-07T16:31:43 - `0ab981ae-1c6f-4236-9e99-a0583a392d97.jsonl`
- Pre-implementation epic review - 2026-10-07 - Refreshed the schema note (v61), added sequencing: first unblocked implementation in the epic; core qualification before the int64 guard/BigInt read, which are low-likelihood robustness controls and may be split as P4 bugs if size review requires. Opus consult (confidence 0.72) recommended running this first and splitting those two controls; split not applied because the 2026-10-06 review deliberately kept them after reproducing both. No implementation or readiness claim; confidence needs a rerun for the revised contract.
- `/ll:confidence-check` - 2026-10-07T00:41:41 - `179a571f-b346-4676-99c5-427e664b8107.jsonl`
- `/ll:ready-issue` - 2026-10-06T23:34:46 - `rollout-2026-10-06T17-27-26-01a1138b-1e26-7522-81f8-fe08a1540f42.jsonl`
- Pre-implementation consumer review - 2026-10-06 - Reproduced sql.js rounding of an exact stored integer and required BigInt retrieval in the actual page query/render loop. Fixed the four-column schema and NULL-only missing-cost count semantics; invalid/overflow inputs remain separate. Opus confidence 0.78; existing related suites: 233 passed. Invalidated prior confidence scores with the CLI; no implementation or fresh score claimed.

- `/ll:confidence-check` - 2026-10-06T23:26:26 - `7b2080b7-52de-4a81-b19c-3b298dbc8c46.jsonl`
- `/ll:verify-issues` - 2026-10-06T23:03:22 - `2c57054f-2b3f-496f-821f-b71d405d9036.jsonl`
- Pre-implementation handoff review - 2026-10-06 - Reproduced a valid `2**63` source subtotal crashing SQLite snapshot binding. Added a bounded export-only representability guard, model-wide token taint with independent cost, range/permutation tests and exact unavailable-versus-empty semantics. Opus confidence 0.74 supported the overflow guard; its empty-channel zero proposal was rejected because no observation cannot certify zero. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation review - 2026-10-06 - Rechecked `main`, consolidated obsolete option/research/wiring questions, corrected schema drift and the actual Node gate behavior, pinned four model-scoped metadata columns, strengthened reason allowlisting and added real predefined-SQL/read-snapshot tests. Retained Option C and approved existing identity columns; no rates or payload changes. Opus consult confidence 0.72; existing related suites: 188 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reconciled the implemented core/result/channel API and cleared historical scores; snapshot work can proceed without quality or retention-followup scheduling edges. Added valid-value raw/known audit sum parity, while preserving recorded Option C, model-wide qualification and the existing payload. Opus confidence 0.70; no new readiness or implementation pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Removed active page-stamp/manifest directives that contradicted recorded Option C, aligned tests/docs with the audit-table policy version, and marked the already resolved vocabulary/rate/bucket concerns as resolved. Source numeric audit safety remains ENH-3731's handoff; no new readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Resolved model-wide audit contributor scope, logical bucketing, derived labels, independent token/cost reasons, numeric validity and shared policy version. Kept Option C and scoped rate criteria to session-reader parity, without new snapshot rates or payload fields. Opus confidence 0.74; its empty-snapshot stamping dissent was not adopted because the recorded decision needs no new table/payload and an empty snapshot carries no figures. Added Impact; fresh confidence required after ENH-3731.

- `/ll:confidence-check` - 2026-10-05T04:41:52 - `a3a2850e-1859-4131-baf9-41bae51155b8.jsonl`
- `/ll:verify-issues` - 2026-10-05T04:40:12 - `faddfe34-ee99-446f-9e12-f81bfea56f96.jsonl`
- `/ll:decide-issue` - 2026-10-05T04:38:16 - `727b64ff-a77b-4d8b-9c8c-afabeceeda4b.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T04:33:31 - `6d396473-5fc6-4381-8b30-58b5f06aa040.jsonl`
- `/ll:confidence-check` - 2026-10-05T04:27:46 - `a146c9c4-1b4b-4d4f-9052-ad3e3745a066.jsonl`
- `/ll:wire-issue` - 2026-10-05T04:23:20 - `1b404432-b825-49eb-bd3d-99651e25e458.jsonl`
- `/ll:refine-issue` - 2026-10-05T04:16:01 - `688a8bf8-c000-4ab4-a82d-b83b98aa3a6a.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Resolution

- **Action**: improve
- **Completed**: 2026-10-07T17:17:39Z
- **Status**: Completed

### Changes Made
- `session_store/queries.py`: `_snapshot_usage_selection` now builds one `ObservationGroup` per logical model (NULL model → `UNKNOWN_MODEL_BUCKET`, `row_channel` buckets) and qualifies tokens and cost separately through `qualify_usage`; each channel row carries its own contribution plus four model-scoped metadata columns (`provenance`, `qualification_reason`, `cost_qualification_reason`, `qualification_policy_version`). `_SnapshotTotals` reuses the shared validators and finite `fsum`, tracks NULL vs invalid separately (missing-cost counts are NULL-only), and an export-only int64 representability guard yields `snapshot_integer_overflow` for canonical tokens. Reasons pass a bounded allowlist (`unclassified` otherwise). `read_schema_version` moved inside the export transaction. Allowlist version 3 → 4.
- `templates/dashboard.llat/template.html.j2`: predefined view renamed `Usage by model and channel` with four canonical token fields, independent `token_availability`/`cost_availability` (value-based, unrounded cost), reasons and model scope; `runQuery` reads rows with `getAsObject(undefined, {useBigInt: true})` for exact integers; guidance text for custom SQL.
- Tests: `test_enh3543_snapshot_usage.py` (parity, overflow permutations, disjoint channels, window, leak/reason bounding, WAL version and selector-seam snapshot tests), `test_feat3304_artifact_dashboard.py` (predefined SQL executed on real snapshots, pins bumped to v4), `feat3304_dashboard_runtime.test.mjs` (page's own query/render loop with a DOM stub).
- Docs: `docs/reference/API.md`, `docs/reference/CLI.md`.

### Verification
- Full suite: 29448 passed; 1 failure (`test_next_loop_golden` float repr) and 8 errors (`test_libsql_integration` live endpoint) reproduce identically on clean `main`. `ruff check` findings are in unrelated spike files; mypy clean.
- Mutation checks: moving the version read outside the transaction fails the WAL test; reverting `useBigInt` fails the Node page-loop test.

## Status

**Open** | Created: 2026-10-05 | Priority: P2
