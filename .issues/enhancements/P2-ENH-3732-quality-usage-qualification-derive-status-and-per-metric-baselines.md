---
id: ENH-3732
type: ENH
title: Quality usage qualification, session derive status, and per-metric baselines
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
blocked_by:
- ENH-3731
- BUG-3736
- ENH-3744
- ENH-3745
- ENH-3748
relates_to:
- ENH-3733
- ENH-3730
- BUG-3735
- ENH-3543
- ENH-3770
size: Large
risk_factors:
- id: deep-multi-module-rewiring
  domain: outcome
  criterion: complexity
  description: Nullable usage metrics, per-metric baselines and attached-member workspace
    proof span four modules with shared state
- id: wide-consumer-surface
  domain: outcome
  criterion: change_surface
  description: QualityMetric, _usage_totals and rate path feed rework, workspace_activity,
    CLI renderers and docs
- id: workspace-transaction-ownership
  domain: outcome
  criterion: complexity
  description: Attached-schema snapshot, TEMP views and query-only ordering across
    caller/owned connections is error-prone
---

# ENH-3732: Quality usage qualification, session derive status, and per-metric baselines

## Summary

Make agent-quality token/cost figures obey the landed usage qualification policy, transcript acquisition scope, and complete retained-session derivation proof. Preserve nullable values, independent token/cost baselines, fractional issue attribution and the documented member-additive workspace population. Consume the shared semantic proof and progress interfaces from ENH-3744/3745 instead of implementing a second producer algorithm.

## Parent Issue

Decomposed from ENH-3723. Its recorded Decision (commit `01747bb96`) requires all-measured quality baselines/verdicts, makes phantom-zero and unknown-containing windows unavailable, and preserves `_rate_metrics`' absence-equals-zero default for non-usage metrics. All structured prerequisites, including ENH-3744/3745, are `done` on inspected branch `main`. Consume their landed APIs below. ENH-3770 is also `done` and supplies guarded replay plus production supplier/context witnesses. This reader consumes the landed evidence while retaining conservative proof and retained-as-of handling for legacy/untracked observations. Historical scores were cleared because their unlanded-interface/dependency premise no longer holds; re-run `/ll:confidence-check` before implementation.

## Current Behavior

On inspected branch `main`, `_usage_totals` in `scripts/little_loops/issue_history/agent_quality.py` filters channels after coverage acquisition, ignores qualification and coerces missing components to zero. A partial/unknown observation with numeric stored cost becomes a token/cost figure. `_rate_metrics` accepts a no-observation window as a zero baseline; the regression stage then rejects genuinely measured zero baselines. Text/markdown assert a numeric value unless sample history is insufficient. Workspace totals carry no member-local derive proof and leave local raw/observation IDs undiscriminated. The single-repo default opener delegates to `history_reader._base._connect_readonly`, which calls `open_history_readonly(..., ensure=True)` and can migrate a store before analysis. The regression mean `sum(values) / K` can overflow for finite usage priors: `[1e308, 1e308]` produces infinity instead of mean `1e308`, silently losing a real 50% increase to `1.5e308`.

## Expected Behavior

- Acquire `channel="transcript"` before coverage selection. Excluded live/rollout counterparts cannot change usage figures, qualification or model composition. Preserve in-scope audit contributors, the closed-issue denominator and fractional attribution.
- Inspect every attributed session and every surviving logical candidate before accepting its observations. ENH-3745's global checkpoint is a validated scan high-water mark, not a completion certificate: source-local pending work below it remains visible to proof and retry. Read only committed retained evidence; no source stat, native-file parsing, pricing, refresh or derivation.

| Retained-session evidence, evaluated in this order | Status/action |
| --- | --- |
| No in-scope observations/candidates; evidence positively proves excluded-only channels | `out_of_scope`; ignore numerator contribution, denominator unchanged |
| In-scope raw; missing/invalid checkpoint or missing/mismatched derive version | `derive_pending`; unavailable |
| In-scope session-local raw maximum above the validated member scan high-water | `derive_lagging`; unrelated later session IDs do not taint it |
| Contract/channel/key/context or retained input cannot be proved | `derive_status_unavailable`; unavailable |
| Any proved logical candidate lacks committed/native-coalesced representation | `derive_gap`; unavailable even if another observation exists |
| Validated source-local usage work remains after preceding checks | `derive_pending`; an advanced scan high-water cannot certify it; cache-only work is not a usage blocker |
| In-scope observations and preceding checks pass | `complete`; apply shared qualification independently for tokens and cost |
| Fully covered recognized non-usage raw, no in-scope observations | `derived_no_usage`; contributes nothing, not an observed zero |
| Neither raw nor usage for an attributed session | `no_evidence`; unavailable |

Retained observations whose raw was legitimately pruned retain their recorded as-of qualification without requiring cursors or current source-file availability. A conservation hold alone neither rejects them nor proves completeness. Missing production observation witnesses alone do not erase this retained-as-of allowance. Consult durable pending evidence even when no raw remains; legitimate retention cannot erase known outstanding usage work. Actual outstanding/unprovable in-scope work still blocks each fractionally attributed window. An entirely observation-free window is `no_observations`; retain any contributing derive failures as diagnostics rather than hiding them behind that label.

Absent/mismatched global checkpoints or current derive versions alone do not retroactively reject otherwise legitimate retained-as-of observations with no surviving candidate or known outstanding usage work. Those checks certify current retained work/completion; relevant pending/new-candidate scope or version mismatches still block. The recorded qualification is a historical consumption fact, not ENH-3746's whole-figure source freshness/as-of certificate. Older stores missing the storage needed to rule out relevant outstanding work still fail closed; this allowance does not invent absent proof.

“Retained as-of” here names committed historical consumption with recorded qualification; it adds no source-freshness `as_of` field and never infers one from observation timestamps. Pair production prune while an unresolved candidate/usage obligation survives with fully resolved prune: the former stays unavailable, the latter retains qualified historical consumption without needing new witness facts. A conservation hold alone cannot blank the resolved case or certify the unresolved case. The cache-rate reader's observed figure may remain numeric with stale/unknown freshness where quality's complete attributed window is unavailable; document their different completeness contracts.

- Build complete window populations before applying `qualify_usage`, separately for tokens and cost (`require_cost=True`). Missing/invalid/audit-only contributors cannot produce complete-subset values. Estimated/mixed qualified values remain labeled numeric consumption, with no trend verdict; a qualified observed zero is zero.
- Keep qualification, sample insufficiency and trend eligibility separate. `insufficient_history` means only that the sample gate failed. Text/markdown show unavailable with a bounded reason, JSON/YAML use `null`; all formats preserve provenance and actual period. Cost coverage stays a diagnostic, not permission to publish a partial figure above 50%.
- Select the earliest qualified, sample-sufficient, all-measured baseline separately per usage metric for per-window verdicts. Regression detection still averages the last eligible prior K windows: measured `[10, 0, 10]` with two priors yields mean `5` and relative increase `1.0`. A zero mean keeps `skipped_zero_baseline`; correction/fix/retry behavior is unchanged. With `latest_only=True`, retain the latest eligible target rule and label an older result's actual period; never attach its verdict to an unavailable latest window.
- Workspace totals remain member-additive `UNION ALL`, including accepted shared-session counting. Derive the attributed session set from the union, then inspect every member carrying in-scope raw/usage or pending evidence for those sessions, even when that member has no local issue association. Its observations still contribute through the accepted shared-session join. A member with neither association nor contributing in-scope evidence invents no missing status. No checkpoint/raw ID is compared across members. Keep repository/issue discriminators and `_UNION_RELATIONS`.

## Proposed Solution

Add a frozen session-status result and usage-only metric metadata. Assemble scope → coverage → semantic/progress proof → complete window populations → per-metric qualification/value → trend eligibility/baselines. Factor no producer recognition into quality.

## Program Design

### Types

Proposed `SessionDeriveStatus` in `history_reader/usage.py`:

```python
@dataclass(frozen=True)
class SessionDeriveStatus:
    status: Literal["complete", "out_of_scope", "derived_no_usage", "derive_pending",
                    "derive_lagging", "derive_gap", "derive_status_unavailable", "no_evidence"]
    reason: str | None = None  # bounded session-status vocabulary
    contributing_reasons: tuple[str, ...] = ()  # stable, deduplicated workspace reasons
```

Derive `in_population` and availability from the status; do not store contradictory booleans. No raw IDs, native keys, paths or arbitrary diagnostic text in serialization. Session reasons stay separate from source freshness and snapshot accounting codes.

`QualityMetric` gains trailing defaulted fields `qualification: UsageQualification | None = None`, `usage_reason: str | None = None`, `derive_reasons: tuple[str, ...] = ()` and `trend_eligible: bool | None = None`. Preserve the existing seven positional fields and the seven non-usage `to_dict()` keys. For both usage metric names, always emit the four additive keys, including empty/unavailable/sample-insufficient windows: serialize `qualification`'s actual frozen fields (component counts as records), `derive_reasons` as a list and `trend_eligible` as a boolean. Provenance and policy version come from `qualification`; do not duplicate independently mutable labels.

`usage_reason` describes consumption qualification, independently of the sample gate: use `no_observations` for an empty attributed observation population (retaining derive failures in `derive_reasons`), otherwise the highest-priority unavailable derive status, otherwise the shared qualification reason, otherwise `None`. Its allowed codes are the session-status vocabulary above, `USAGE_QUALIFICATION_REASONS` and the quality-only `no_observations`; the shared qualification still reports `empty_selection` for its empty group. No shared reason-vocabulary change is required. Use the fixed workspace status order below for local multi-session failures too. A sample-insufficient but qualified population retains its successful qualification and `usage_reason=None`, while `value=None`, `insufficient_history=True` and `trend_eligible=False`. Render the sample result and any usage failure/provenance diagnostics without erasing either; no renderer infers eligibility from a numeric value or a non-NULL verdict.

Proposed compatibility bucket shape (richer qualification/status metadata is carried in a parallel internal per-window map):

```python
class UsageBucket(TypedDict):
    cost: float | None
    tokens: float | None
    priced_rows: float
    total_rows: float
```

Use a typed internal window-usage result for nullable `cost`/`tokens`, fractional `priced_rows`/`total_rows` and separate per-metric qualification/derive diagnostics. Preserve the existing four numeric bucket names for direct helper callers; update their return annotation to permit `None`. Carry richer metadata alongside, without dropping rejected rows or changing attribution. `total_rows` weights every attributed in-scope audit contributor; `priced_rows` weights only rows meeting shared token admission, recognized provenance and resolved coverage with a valid stored cost. A numeric cost on an audit-only row cannot make coverage complete; even 100% coverage cannot override a derive failure or group-level qualification. Counts supplied to `UsageQualification` describe original contributors, not weighted pseudo-observations: add each observation once per affected window, qualify that complete population, then sum its fractional issue contributions. Two issues in the same window must not duplicate one observation's qualification counts. Continue dividing by all associated issues, including those outside the closed-window population; filter output windows after determining that divisor. Distinct member observations count separately in workspace totals.

### Signatures

- `select_session_derive_status(conn: sqlite3.Connection, session_ids: Iterable[str], *, schema: str = "main") -> dict[str, SessionDeriveStatus]` — new helper. Every requested session gets a key; missing schema/evidence fails closed. `schema` selects `main` or a validated generated attached-member alias, never caller SQL. Qualify raw/meta/observation-identity queries to that schema; never read first-attached `meta` implicitly.
- Existing `analyze_agent_quality(...) -> QualityAnalysis` gains keyword-only `derive_status: Mapping[str, SessionDeriveStatus] | None = None`. `None` computes locally; a supplied map is authoritative and missing keys fail closed.
- Existing `_usage_totals`, `_rate_metrics`, `_metric_eligible`, `_metric_eligible_as_baseline` and `aggregate_history_dbs` keep their existing roles. Add explicit usage metadata to the rate path; retain the generic zero default for non-usage calls.

### Call Path

Single repo: analysis read transaction → transcript selector + local session proof → usage-window metadata → rate/verdict → compositions/regressions → formatters.

Workspace totals: `_open_union` → explicit read transaction → member-qualified session proof on each attached schema → conservative injected map + union contributors → complete analysis → end owned transaction. Per-repo analyses each use their own coherent read snapshot; totals obtain fresh proof on their attached revisions instead of reusing an unchecked earlier per-repo map.

### Decision Rules

- Reuse ENH-3744's pure native recognition/coalescing/correspondence and ENH-3745's validated retained-state completion. Observations satisfy conservation separately from qualification. Exact surviving raw linkage may prove an unkeyed audit representation; values/timestamps cannot. Decode failures and unregistered contracts are unavailable, never affirmative non-usage.
- Use `usage_proof_scope.inspect_retained_source(conn, source, channel="transcript", schema=schema)` for retained correspondence and `usage_source_state.read_source_derive_completion`, `pending_obligations`, `read_source_head` and `read_observation_witness` for committed state. Reuse `lifecycle._read_usage_checkpoint` with member-qualified reads (extend its schema seam if needed), including both `meta` and its `_raw_event_sequence` helper's `sqlite_sequence` query; do not copy checkpoint validation or borrow another member's allocation hint. The proof adapter owns decoding, related-source collection and whole-scope item/byte limits. Map `UsageProofLimit` / `UsageProofUnavailable` to bounded `derive_status_unavailable` for affected in-scope/uncertain sessions; never certify a partially collected scope or fall back to `main`.
- ENH-3770's shared adapter also collects matching peer usage and its header/model/closure context; unreadable peers taint keyed correspondence. Preserve those facts and cross-source conflict controls when adding transcript acquisition scoping. A matching peer with a contradictory payload session cannot be hidden by envelope/session filtering. The adapter's current `channel` argument filters correspondence after collection, so it does not yet enforce acquisition-before-budget scope. Omit positively proved excluded-only sources before proof; where mixed sources need channel-aware collection, extend the shared `usage_proof_scope` seam to omit positively irrelevant inputs before budget/materialization while preserving all required native context and ambiguous inputs. Do not introduce another decoder/recognizer in `history_reader`. Excluded observations cannot enter qualification/counts; genuinely unprovable or over-limit relevant context still fails closed.
- Distinguish `SourceDeriveCompletion.outstanding` and each `SourcePending.usage_pending`: `raw_cache` alone does not make usage unavailable, while `usage`, `both` and unprovable relevant usage state do. The completion reader may report semantic usage completion with cache work still outstanding. Absence of a source head cannot erase existing usage obligations, including older generations.
- Discover member-local source/session associations from retained raw, observations, applied suppliers/qualification dependencies and positively verified pending-only scope. A source head's session is not an exhaustive inventory: a transcript may contain multiple sessions, and `pending_obligations` reconstructs scopes without host/session. Whole-source or unlocatable/pruned usage obligations taint every associated in-scope session unless shared committed evidence positively excludes the entire obligation. Ignore a bounded obligation only when its complete range/affected observations prove unrelated sessions or excluded channels; a different head session or vanished raw is not negative proof. Do not taint unrelated sources or invent evidence for absent member/session pairs.
- A matching native key alone does not prove that a retained observation represents a later snapshot. `UsageCandidateProof` carries supplier positions and correspondence, but no generation certificate; combine it with sufficient compatible committed generation/order and applied-value evidence where representation relies on a newer/coalesced supplier. A witness's `known` label cannot replace complete compatible supplier scope/position (physical line at least 1) or required consumed-context dependencies; nullable fields or an empty required frontier remain unprovable. Neither `represented` nor a larger supplying raw ID alone proves that order. An unresolved newer snapshot remains unavailable even when an older observation with that key survives. Envelope/payload/observation identity disagreements are unprovable, never attributed to a different session to make its window complete. This ordering check does not impose a witness requirement on otherwise legitimately pruned retained-as-of observations with no known outstanding work.
- The helper reuses a caller-owned committed read snapshot with `PRAGMA query_only=1`; on an idle query-only caller connection it begins/ends only its owned read transaction. A writable caller cannot certify usage: report bounded `derive_status_unavailable` without toggling its PRAGMAs, reopening the database or committing/rolling back caller work. The full analysis must pin proof, attribution, usage and compositions together. Never commit or close a caller's transaction/connection. Helpers perform no migration, refresh or writes. When analysis owns its connection, use the existing backend `open_history_readonly(..., ensure=False)` seam and handle `HistoryError` with the existing empty/unavailable behavior. Do not use the migrating `_connect_readonly` wrapper or change its other callers. An older schema can expose audit observations but cannot supply absent proof; fail closed without upgrading it or creating a missing store.
- Usage trend eligibility is explicit: sample-sufficient, qualified, all-measured, no blocking derive status and a known calendar period. Consumption may remain numeric in the `unknown` period, but that period is never a usage target or baseline at either stage. Estimated/mixed windows keep numeric consumption with `trend_eligible=False`; absence of usage metadata fails closed for usage metrics. Preserve non-usage eligibility and the existing zero-baseline classifier separately from the regression zero-mean guard.
- Compute usage regression means without overflowing a representable result: for nonnegative eligible values, use a stable sum of values divided by their count, rather than `sum(values) / count`. Two valid `1e308` priors must yield `1e308`, not infinity. This changes usage baseline arithmetic only; it does not reclassify valid stored costs or change correction/fix/retry behavior.
- Choose the attached-transaction solution for totals, replacing the old close-before-attach map handoff. Pin each member before its proof/contributors are read. This ensures consistency within each member, without promising a simultaneous global epoch across independent databases. Do not add a `data_version` polling/retry design.
- Keep coverage/raw-link identities member-qualified in scratch views/mappings, with collision-free member tags rather than arbitrary raw-ID strides. Preserve shared-session attribution and additive observation counts; do not deduplicate shared native observation keys across members.
- Do not reuse only the sessions requested by per-repo analyses for totals proof. Include the union-attributed sessions with evidence in otherwise unassociated members; exclude truly absent member/session pairs before merging statuses.
- Merge unavailable member statuses in fixed order `derive_status_unavailable` > `no_evidence` > `derive_pending` > `derive_lagging` > `derive_gap`, retaining bounded contributing reasons in stable order. Every unavailable status blocks; precedence is diagnostic only.
- Read the deriver's `_USAGE_DERIVE_VERSION` from the `lifecycle` module at call time; no copied literal or import-time binding. Consume the actual frozen `UsageQualification` fields and `counts(column)`.
- Model composition remains transcript/legacy scoped. Keep and label `load_window_compositions`' broader all-raw host diagnostic; it cannot certify usage qualification or trend eligibility.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — new session helper/result and identity/proof queries at the existing SQL chokepoint; `history_reader/__init__.py` — re-export, docstring and `__all__`.
- `scripts/little_loops/session_store/usage_proof_scope.py` — shared channel-aware bounded collection if required; preserve prune's existing unfiltered proof. `session_store/lifecycle.py` — member-qualified `_read_usage_checkpoint`/`_raw_event_sequence` seams if required, with unchanged local validation.
- `scripts/little_loops/issue_history/agent_quality.py` — strict owned-connection open, nullable window usage/metric metadata, `_usage_totals`, `_rate_metrics`, `QualityMetric.to_dict`, `_format_metric_line` and markdown cells; `_STANDARD_NOTES`, `_definitions` and module docstring.
- `scripts/little_loops/issue_history/quality_regressions.py` — explicit all-measured target/baseline eligibility, measured-zero inclusion, `_REGRESSION_NOTES` and diagnostic wording; preserve zero-mean and retry branches.
- `scripts/little_loops/issue_history/workspace_quality.py` — attached-schema proof, transaction/connection ownership, conservative injection and member-qualified local identities. Create TEMP views before enabling query-only; keep the attach-limit/totals-skipped behavior and close owned resources on every exit.

### Dependent Files

- `scripts/little_loops/session_store/usage_proof.py`, `usage_source_state.py`, `lifecycle.py`, `writers.py`, `claude_usage.py`, `usage_refresh.py` — consume landed proof/progress and refresh invalidation. ENH-3770 owns guarded mutation and production supplier/context witnesses; this issue adds neither writer mutation nor storage migration.
- `scripts/little_loops/cli/history.py` — single-repo caller uses default local proof; workspace proof remains inside aggregation.
- `scripts/little_loops/session_store/backend.py` and `history_reader/_base.py` — reuse the existing strict opener/error types; the migrating compatibility wrapper and its unrelated callers remain unchanged.
- `scripts/little_loops/issue_history/rework.py` and `_utils.py` — shared definitions/window/verdict helpers; preserve rework output, four definitions and the correlational note. `workspace_activity.py` uses workspace helpers; avoid unrelated signature changes.

### Tests

- `scripts/tests/test_issue_history_agent_quality.py` — add explicit measured provenance fixtures while retaining unknown controls; nullable rendering, independent baseline stages, estimated/mixed targets, zero/zero-mean and older-period output, authoritative injected map/missing key, four definitions and seven-key non-usage serialization. Assert exact additive usage metadata and sample/derive/qualification reason precedence, including simultaneous failures. Test one session touching two issues in the same window and one outside it: qualification counts reflect original rows once per window, while weighted numerators retain the all-associated-issues divisor. Test numeric `unknown`-period consumption with no usage baseline/verdict at either stage. With measured cost windows `[1e308, 1e308, 1.5e308]`, K=2 and valid per-window proof, assert a finite mean `1e308`, magnitude 0.5 and a regression event. Retain the direct `_usage_totals` bucket contract in `test_enh3532_codex_rollout_usage.py` while allowing unavailable values.
- `scripts/tests/test_enh3732_session_derive_status.py` (new) — real Claude ingestion/derive/prune with coalesced snapshots, two candidates/one observation, audit correspondence through raw links, corrupt/mismatched contracts, omitted/no-usage/excluded-only evidence, session-local lag, complete requested-session coverage, source loss and retained as-of behavior. Assert frozen result, package exports, query-only execution, byte-identical source files and forbidden source/derive/pricing calls. Exercise the full default analysis on current/older/missing stores with schema ensuring forbidden; assert no upgrade/create and unavailable absent proof. Exercise active/idle query-only callers: reuse/end only owned read transactions and keep caller connections open on success and failure. Active/idle writable callers, including provisional uncommitted usage, fail usage proof closed without changing PRAGMAs or caller work.
- Use landed storage helpers to test `raw_cache`-only versus `usage`/`both` pending, older-generation obligations after raw prune and a multi-session transcript with a head naming only its last session. Test complete-range unrelated/excluded pending controls, missing/mismatched supplier generations despite affirmative correspondence, `known` witnesses with incomplete supplier fields/line zero or empty required context, missing witnesses with legitimate retained-as-of evidence, excluded-heavy acquisition scopes and bounded mixed/uncertain proof-limit/unavailable failures. Reader proof must not call producer reconciliation to make an analysis pass. Numeric writer-to-quality positives must use already-committed Claude transcript acquisition/guarded replay and its actual production supplier witnesses, including first-copy survival; keep separate retained-as-of fixtures without witnesses. ENH-3770's Codex context-only requalification is an excluded-rollout/non-taint control for transcript-only quality, never permission to add rollout usage to its numeric population. Cross-source contradictory/unreadable peer evidence and invalidated consumed frontiers must block relevant current work without erasing unrelated retained facts.
- `scripts/tests/test_feat3410_workspace_quality.py` and `test_feat3418_workspace_quality.py` — member-local checkpoints and differing `sqlite_sequence` allocation hints, colliding IDs with unrelated audit groups, shared sessions, member-order permutations, absent/out-of-scope members and a WAL commit during analysis. Add the asymmetric case: A associates session S with an issue; B has S usage plus an unresolved candidate but no S issue association; B must still taint totals. A third member with no S evidence must not. Assert proof and usage use the same attached-member snapshot, no first-member certification, one-member totals parity, exact union relations, attach-limit handling and owned-resource cleanup.
- `scripts/tests/test_cli_history.py` — actual usage-bearing text/markdown/JSON/YAML output. Preserve `test_usage_selection_chokepoint_gate.py` and `test_history_store_chokepoint_gate.py`; no new raw SQLite history openers or token/cost SQL outside the existing seam.

### Documentation

Update `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, reader/issue-history package docstrings and `scripts/little_loops/pricing.py` docstring. Remove “always computable”, 50%-coverage permission and zero-as-unmeasured claims. State transcript scope, unchanged denominator, member-additive population, broad host diagnostic and labeled historical periods. Follow end-user audience rules; retain pinned reference headings and run audience/count gates.

## Acceptance Criteria

- [ ] Partial/unknown numeric-cost observations and invalid components cannot produce complete token/cost figures, priced-complete coverage or verdicts; qualified tokens remain available when only cost is unpriced.
- [ ] Excluded live/rollout rows cannot change transcript values/qualification/model composition; denominator, fractional attribution and correction/fix/retry definitions are preserved.
- [ ] Every session disposition above is exercised through real quality consumers. Coalescing does not create a gap; missing candidates, corrupt/unproved context and underived held work cannot disappear behind other observations or an advanced checkpoint.
- [ ] Safely retained qualified observations survive raw/source loss and conservation holds without requiring cursors; observation-free windows stay unavailable, not zero. No stat, source parse, re-derive, pricing or writes occur in the proof.
- [ ] Production prune/guarded replay cannot erase relevant unresolved candidate or durable usage-pending evidence to make retained proof vacuously complete. Paired resolved/unresolved prune controls preserve numeric historical facts only when relevant outstanding work is ruled out; mixed/uncertain-channel proof-limit cases stay unavailable rather than dropping obligations.
- [ ] Unavailable values render with bounded reasons in every output format; sample insufficiency and underlying usage diagnostics remain separately visible. Estimated/mixed figures have labels without trend verdicts. The four additive usage metadata keys and original-contributor counts are deterministic; non-usage serialization and all-associated-issues fractional attribution are preserved.
- [ ] Independent all-measured baseline/target eligibility, measured `[10, 0, 10]`, zero-mean guard and older eligible period labeling pass at both baseline stages.
- [ ] With ordered windows `[10, unavailable, 0, 10]` and regression K=2, the unavailable gap is skipped and the two eligible priors `[10, 0]` yield mean 5 and relative increase 1.0. Per-window verdicts still use the earliest eligible measured baseline 10; neither stage requires a verdict from the other to establish eligibility.
- [ ] Valid finite usage priors with a finite representable mean cannot lose a regression to intermediate sum overflow; measured `[1e308, 1e308, 1.5e308]` yields mean `1e308` and magnitude 0.5 for K=2.
- [ ] Workspace totals pin member proof and all contributor queries to the same attached revisions; collisions, shared sessions, concurrent commit and permutation controls preserve accepted member-additive populations and bounded diagnostics.
- [ ] Source-local pending evidence survives an advanced global scan high-water; older same-key observations and envelope/session mismatches cannot certify unresolved snapshots. Asymmetric shared-session members contribute proof whenever their evidence contributes to totals, independently of local issue associations.
- [ ] Cache-only pending does not blank proved usage; usage/both/unknown relevant work still blocks. Multi-session sources and pruned/older-generation obligations cannot disappear behind the source head's last session. Shared adapter bounds and missing-member failures produce bounded unavailable diagnostics without partial proof or cross-member fallback; excluded-only/heavy controls preserve transcript acquisition scope.
- [ ] Full default analysis never creates/migrates a history store; older stores fail closed for absent proof. Caller query-only admission and transaction/connection ownership hold on success and failure; writable/provisional caller state cannot certify usage. Member checkpoints and allocation hints remain member-local. Numeric `unknown`-period usage cannot become a baseline or trend target at either stage.
- [ ] `python -m pytest scripts/tests/` exits 0, including chokepoint and documentation gates.

## Impact

- **Priority**: P2 — prevents audit-only/underived observations from becoming quality baselines.
- **Effort**: Large — session proof, nullable metrics and coherent member-local workspace integration.
- **Risk**: Medium — incomplete published trends become unavailable; preserve established non-usage behavior.

## Scope Boundaries

No producer algorithm, prune/replay storage migration, source-file freshness, snapshot/dashboard, repricing, legacy promotion or ENH-3730 availability redesign. Consume the landed shared proof/completion handoff. No scheduling edge to ENH-3746 or ENH-3770 is required; insufficient relevant proof stays unavailable and legitimate retained-as-of observations follow the allowance above.

## Implementation Steps

**Sequencing (2026-10-07):** the stable usage-mean arithmetic (priors near `1e308`) is a robustness control with no realistic USD-cost trigger; implement it after the status helper and nullable-metric work, and split it into a standalone P4 bug if size review gates this issue. The proof/completion APIs have landed. Reconciliation/hold release has landed in ENH-3770; consume its evidence without mutation or another scheduling edge.

1. Re-run `/ll:confidence-check`, then implement/test the query-only session helper using the landed bounded proof, member-qualified checkpoint and component-aware source-state APIs; resolve acquisition scoping in the shared adapter.
2. Use strict owned-connection reads; build transcript-scoped complete window populations, nullable usage numerators and the fixed additive per-metric metadata; preserve original contributor counts, attribution and generic rate defaults.
3. Apply independent all-measured baseline/target eligibility and update every renderer, definition and note.
4. Obtain totals proof on attached-member snapshots, inject the deterministic conservative map and keep local identities member-qualified.
5. Exercise real writer-to-quality and CLI/workspace consumers, update docs and run the local suite.

## Confidence Check Notes

**Historical assessment, superseded for dependency readiness by this review:** ENH-3744/3745 are now `done`, their APIs resolve on `main`, and the old top-level scores/resolved interface risks were cleared. Re-run `/ll:confidence-check` against the revised scope; this review claims no new score.

_Added by `/ll:confidence-check` on 2026-10-07, before those prerequisites landed_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- Spec is strong (no Program Design, parity, claim, structure or decision gaps; learning tests not required; no unproven-mechanism flag), but the session-status helper is written against ENH-3744/3745 interfaces that do not exist in the tree yet.
- Complexity 10/25: nullable metrics, per-metric baselines and attached-member workspace proof span four modules with shared transaction state.

### Gaps to Address
- Resolved on 2026-10-07: all structured prerequisites are `done`; the earlier interface/dependency STOP no longer applies. The remaining implementation complexity and the revised proof/scoping cases need a fresh check.

### Risk Factor Delta
- Baseline: none recorded

## Verification Notes

Pre-implementation review on `main` at `55f52f0ad` (2026-10-07): all structured prerequisites are now `done`; the earlier dependency STOP and its top-level scores are superseded. No refreshed implementation-confidence score is claimed.

- Named the landed bounded retained-proof, checkpoint and source-state APIs; separated cache-only work, multi-session/older-generation pending attribution and correspondence from sufficient supplier-generation/order proof. Required acquisition scoping and bounds to remain in the shared adapter.
- Preserved legitimate raw-pruned historical qualification despite absent current checkpoint/version or production observation witnesses, while known/unprovable relevant usage work and missing required proof storage still fail closed. This historical qualification does not certify source freshness.
- `/ll:advise` with Opus (`--signal user_requested`, confidence 0.78) supported independent conservative readers and component-aware pending. Retained the existing bounded reason vocabulary and member-additive population rather than adding advisor-proposed payload/reason fields or changing workspace semantics. The advisor's cache-rate `raw_cache` concern does not apply to parser-derived message/tool cache obligations.
- All three reviewed issues pass format/dependency and program-design checks; learning-test assessment is `not_required`. Existing proof/state/checkpoint/refresh/qualification/cache-rate/quality/workspace/chokepoint suites and the repository-wide prose-dependency gate: **330 passed**. These are current-behavior controls, not tests of the future implementation.

Pre-implementation review on `main` at `ec36b137d` (2026-10-06): contract corrected; readiness remains **BLOCKED** by ENH-3744/3745.

- A call probe confirmed the default analysis requests `ensure=True`; the strict backend opener already supports `ensure=False`. Added full-call no-migration and transaction-ownership controls without changing unrelated history readers.
- Pinned usage serialization, quality-only empty-window vocabulary, sample/usage diagnostic separation and original-contributor counts before weighting. Corrected `_REGRESSION_NOTES`' owning module in the Integration Map.
- Shared qualification has no period check, so all-measured alone cannot exclude an `unknown` period. Added explicit usage trend eligibility and unavailable-gap/zero controls; preserved the recorded `no_observations` primary label with contributing derive failures.
- A direct regression-consumer probe returned no event for `[1e308, 1e308, 1.5e308]` because its prior mean overflowed to infinity. Added stable usage-only mean arithmetic and a concrete finite-mean regression control; this finding is independent of the Opus consult.
- Opus consult (`claude-opus-5-5`, confidence 0.78) supported fixed metadata/counts and the gap test. Its proposed derive-first empty-window reason order and assumption that qualification excludes unknown periods were not adopted because they conflict with the recorded contract/current API.
- Existing policy/channel/quality/workspace/snapshot/dashboard/chokepoint suites: **233 passed**. These are existing behavior controls, not tests of the proposed implementation. Structural/design/proof/decision gates are recorded by the current review; no new readiness score is claimed.

## Session Log

- Pre-implementation epic review - 2026-10-08 - Reconciled completed ENH-3770 production evidence and required committed writer-to-quality positives beside witnessless retained-as-of controls. Channel-aware proof collection must retain the landed peer header/model/closure, contradictory-session and unreadable-peer protections; analysis never reconciles or writes. No implementation or readiness score.

- Pre-implementation consumer review - 2026-10-07 - Rechecked the landed proof/progress and quality/workspace seams at `659639f17`. Clarified active/idle query-only caller ownership and fail-closed writable callers, preserving bounded reasons and caller state. Named both member-qualified checkpoint reads (`meta` and `_raw_event_sequence`'s `sqlite_sequence`) and added differing-allocation-hint controls. Required complete supplier/consumed-context facts when a witness is needed, rather than trusting its `known` label. All structured prerequisites remain done; no dependency, policy, implementation or numerical readiness change.

- Pre-implementation landed-handoff review - 2026-10-07 - Updated resolved dependencies and actual shared APIs, cleared historical readiness scores, added component-aware/multi-session pending and bounded acquisition controls, and preserved raw-pruned historical qualification without claiming applied-value freshness. Opus confidence 0.78 supported independent reader delivery; relevant existing suites and prose gate: 330 passed. No implementation or fresh numerical readiness score.
- `/ll:ready-issue` - 2026-10-07T23:18:25 - `d4950fb6-e6e8-449c-ae1d-00ebb49011d8.jsonl`
- `/ll:confidence-check` - 2026-10-07T16:36:38 - `2df55fef-6809-48a2-9c94-dc2d5f791646.jsonl`
- Pre-implementation epic review - 2026-10-07 - Added sequencing (status helper first; overflow-mean robustness last/splittable) and recorded which ENH-3744/3745 pieces this issue actually consumes (pure proof + source completion read) for the pending slicing decision. No scope change; no implementation or readiness claim.
- `/ll:ready-issue` - 2026-10-06T23:34:46 - `rollout-2026-10-06T17-27-26-01a1138b-1e26-7522-81f8-fe08a1540f42.jsonl`
- Pre-implementation consumer review - 2026-10-06 - Added strict non-migrating quality reads, fixed additive usage metadata/reason semantics, original-contributor qualification counts and independent known-period/gap/zero trend controls. Reproduced intermediate baseline-sum overflow and required a stable finite usage mean. Opus confidence 0.78; existing related suites: 233 passed. ENH-3744/3745 still block implementation closeout; no implementation or fresh confidence score claimed.

- Pre-implementation handoff review - 2026-10-06 - Distinguished scan progress from source completion and required durable pending checks, dominance of the applied snapshot and identity consistency. Closed the asymmetric workspace hole where a member contributes shared-session usage without a local issue association. Opus confidence 0.74 supported bounded source/figure proof; its global completion-floor proposal was not adopted because an unrelated pending source must not taint complete sources. Targeted existing policy/lifecycle/reader/quality/workspace/dashboard/chokepoint suites: 293 passed. No implementation or readiness score claimed.

- Pre-implementation review - 2026-10-06 - Rechecked `main`, consolidated superseded research/wiring directives and specified bounded status/nullable metadata, qualify-before-weighting, attached-schema snapshot proof and period semantics. Opus consult confidence 0.72 supported separation of representation, mutation and source completion; allocation/raw-ID shortcuts were rejected because they cannot prove native order or processing. Existing shared-policy/retention/quality/workspace/chokepoint tests: 188 passed. No implementation or readiness score claimed.

- Pre-implementation epic review - 2026-10-05 - Reconciled landed core/channel/Stage 1 dependencies and cleared historical scores. Assigned pure candidate proof to ENH-3744, processing validation to ENH-3745, and made the workspace connection/revision contract actionable. Opus confidence 0.70; blanket rejection of legacy conservation holds was not adopted because it changes the recorded retained-as-of policy. Actual pending/unprovable candidates still block. No implementation or fresh readiness pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Opus critique (confidence 0.72) confirmed gap-before-usage ordering and unregistered-contract failure. Added coherent read-snapshot, stable workspace-reason and member-qualified local-identity controls, while retaining the accepted member-additive population. BUG-3736 owns the independently reproduced pruning/usage-loss repair and is a hard integration prerequisite. Reconciled superseded wiring concerns; no new confidence pass is claimed.

- Pre-implementation epic review - 2026-10-05 - Resolved logical-observation derive gaps, raw-host diagnostic scope and workspace coverage/proof controls. Kept the explicitly documented member-additive totals instead of adopting Opus’s proposed cross-member quarantine (confidence 0.74); that would change the existing accepted population. Added Impact and required regression cases; no new score or implementation pass is claimed.

- `/ll:confidence-check` - 2026-10-05T04:09:15 - `ddd0ba49-7247-411f-a7ef-57bd1c042115.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T04:06:20 - `097f9bb1-c676-46ac-b043-c8b9570fd790.jsonl`
- `/ll:confidence-check` - 2026-10-05T03:58:51 - `34b28804-d521-4695-861e-b3e56e525c2d.jsonl`
- `/ll:verify-issues` - 2026-10-05T03:57:29 - `e36568ce-5b7b-43e2-a419-0854752c451b.jsonl`
- `/ll:wire-issue` - 2026-10-05T03:55:31 - `442ab9b5-db9b-449c-b459-e80826708c51.jsonl`
- `/ll:refine-issue` - 2026-10-05T03:44:38 - `18d2ef05-82f6-4fff-9353-148e58d582a1.jsonl`
- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2
