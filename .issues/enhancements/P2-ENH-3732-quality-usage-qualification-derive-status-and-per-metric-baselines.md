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
size: Large
---

# ENH-3732: Quality usage qualification, session derive status, and per-metric baselines

## Summary

Make agent-quality token/cost figures obey the landed usage qualification policy, transcript acquisition scope, and complete retained-session derivation proof. Preserve nullable values, independent token/cost baselines, fractional issue attribution and the documented member-additive workspace population. Consume the shared semantic proof and progress interfaces from ENH-3744/3745 instead of implementing a second producer algorithm.

## Parent Issue

Decomposed from ENH-3723. Its recorded Decision (commit `01747bb96`) requires all-measured quality baselines/verdicts, makes phantom-zero and unknown-containing windows unavailable, and preserves `_rate_metrics`' absence-equals-zero default for non-usage metrics. ENH-3731, ENH-3748 and BUG-3736 are done; ENH-3744/3745 remain implementation prerequisites. No new readiness score is claimed.

## Current Behavior

On inspected branch `main`, `_usage_totals` in `scripts/little_loops/issue_history/agent_quality.py` filters channels after coverage acquisition, ignores qualification and coerces missing components to zero. A partial/unknown observation with numeric stored cost becomes a token/cost figure. `_rate_metrics` accepts a no-observation window as a zero baseline; the regression stage then rejects genuinely measured zero baselines. Text/markdown assert a numeric value unless sample history is insufficient. Workspace totals carry no member-local derive proof and leave local raw/observation IDs undiscriminated.

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
| Validated source-local pending work remains after preceding checks | `derive_pending`; an advanced scan high-water cannot certify it |
| In-scope observations and preceding checks pass | `complete`; apply shared qualification independently for tokens and cost |
| Fully covered recognized non-usage raw, no in-scope observations | `derived_no_usage`; contributes nothing, not an observed zero |
| Neither raw nor usage for an attributed session | `no_evidence`; unavailable |

Retained observations whose raw was legitimately pruned retain their recorded as-of qualification without requiring cursors or current source-file availability. A conservation hold alone neither rejects them nor proves completeness. Consult durable pending evidence even when no raw remains; legitimate retention cannot erase known outstanding work. Actual outstanding/unprovable in-scope work still blocks each fractionally attributed window. An entirely observation-free window is `no_observations`; retain any contributing derive failures as diagnostics rather than hiding them behind that label.

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

`QualityMetric` gains trailing defaulted usage-only qualification/provenance/reason/trend-eligibility fields. Preserve the existing seven positional fields and the seven non-usage `to_dict()` keys; usage keys are additive when set.

Proposed compatibility bucket shape (richer qualification/status metadata is carried in a parallel internal per-window map):

```python
class UsageBucket(TypedDict):
    cost: float | None
    tokens: float | None
    priced_rows: float
    total_rows: float
```

Use a typed internal window-usage result for nullable `cost`/`tokens`, fractional `priced_rows`/`total_rows` and separate per-metric qualification/derive diagnostics. Preserve the existing four numeric bucket names for direct helper callers; update their return annotation to permit `None`. Carry richer metadata alongside, without dropping rejected rows or changing attribution. Counts supplied to `UsageQualification` describe original contributors, not weighted pseudo-observations: qualify before dividing each accepted contribution by its session's attributed issue count.

### Signatures

- `select_session_derive_status(conn: sqlite3.Connection, session_ids: Iterable[str], *, schema: str = "main") -> dict[str, SessionDeriveStatus]` — new helper. Every requested session gets a key; missing schema/evidence fails closed. `schema` selects `main` or a validated generated attached-member alias, never caller SQL. Qualify raw/meta/observation-identity queries to that schema; never read first-attached `meta` implicitly.
- Existing `analyze_agent_quality(...) -> QualityAnalysis` gains keyword-only `derive_status: Mapping[str, SessionDeriveStatus] | None = None`. `None` computes locally; a supplied map is authoritative and missing keys fail closed.
- Existing `_usage_totals`, `_rate_metrics`, `_metric_eligible`, `_metric_eligible_as_baseline` and `aggregate_history_dbs` keep their existing roles. Add explicit usage metadata to the rate path; retain the generic zero default for non-usage calls.

### Call Path

Single repo: analysis read transaction → transcript selector + local session proof → usage-window metadata → rate/verdict → compositions/regressions → formatters.

Workspace totals: `_open_union` → explicit read transaction → member-qualified session proof on each attached schema → conservative injected map + union contributors → complete analysis → end owned transaction. Per-repo analyses each use their own coherent read snapshot; totals obtain fresh proof on their attached revisions instead of reusing an unchecked earlier per-repo map.

### Decision Rules

- Reuse ENH-3744's pure native recognition/coalescing/correspondence and ENH-3745's validated retained-state completion. Observations satisfy conservation separately from qualification. Exact surviving raw linkage may prove an unkeyed audit representation; values/timestamps cannot. Decode failures and unregistered contracts are unavailable, never affirmative non-usage.
- A matching native key alone does not prove that a retained observation represents a later snapshot. Consume the proof's compatible generation/order and applied-value position; an unresolved newer snapshot remains unavailable even when an older observation with that key survives. Envelope/payload/observation identity disagreements are unprovable, never attributed to a different session to make its window complete.
- The helper reuses a caller-owned transaction; when none exists it owns only its read transaction. The full analysis must pin proof, attribution, usage and compositions together. Never commit or close a caller's transaction/connection. Helpers run on query-only connections; no migration, refresh or writes.
- Choose the attached-transaction solution for totals, replacing the old close-before-attach map handoff. Pin each member before its proof/contributors are read. This ensures consistency within each member, without promising a simultaneous global epoch across independent databases. Do not add a `data_version` polling/retry design.
- Keep coverage/raw-link identities member-qualified in scratch views/mappings, with collision-free member tags rather than arbitrary raw-ID strides. Preserve shared-session attribution and additive observation counts; do not deduplicate shared native observation keys across members.
- Do not reuse only the sessions requested by per-repo analyses for totals proof. Include the union-attributed sessions with evidence in otherwise unassociated members; exclude truly absent member/session pairs before merging statuses.
- Merge unavailable member statuses in fixed order `derive_status_unavailable` > `no_evidence` > `derive_pending` > `derive_lagging` > `derive_gap`, retaining bounded contributing reasons in stable order. Every unavailable status blocks; precedence is diagnostic only.
- Read the deriver's `_USAGE_DERIVE_VERSION` from the `lifecycle` module at call time; no copied literal or import-time binding. Consume the actual frozen `UsageQualification` fields and `counts(column)`.
- Model composition remains transcript/legacy scoped. Keep and label `load_window_compositions`' broader all-raw host diagnostic; it cannot certify usage qualification or trend eligibility.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` — new session helper/result and identity/proof queries at the existing SQL chokepoint; `history_reader/__init__.py` — re-export, docstring and `__all__`.
- `scripts/little_loops/issue_history/agent_quality.py` — nullable window usage/metric metadata, `_usage_totals`, `_rate_metrics`, `QualityMetric.to_dict`, `_format_metric_line` and markdown cells; `_STANDARD_NOTES`, `_REGRESSION_NOTES`, `_definitions` and module docstring.
- `scripts/little_loops/issue_history/quality_regressions.py` — explicit all-measured target/baseline eligibility, measured-zero inclusion and diagnostic wording; preserve zero-mean and retry branches.
- `scripts/little_loops/issue_history/workspace_quality.py` — attached-schema proof, transaction/connection ownership, conservative injection and member-qualified local identities. Create TEMP views before enabling query-only; keep the attach-limit/totals-skipped behavior and close owned resources on every exit.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py`, `claude_usage.py`, `usage_refresh.py` — consume shared proof/progress and refresh invalidation; ENH-3744/3745 own writer/storage changes.
- `scripts/little_loops/cli/history.py` — single-repo caller uses default local proof; workspace proof remains inside aggregation.
- `scripts/little_loops/issue_history/rework.py` and `_utils.py` — shared definitions/window/verdict helpers; preserve rework output, four definitions and the correlational note. `workspace_activity.py` uses workspace helpers; avoid unrelated signature changes.

### Tests

- `scripts/tests/test_issue_history_agent_quality.py` — add explicit measured provenance fixtures while retaining unknown controls; nullable rendering, independent baseline stages, estimated/mixed targets, zero/zero-mean and older-period output, authoritative injected map/missing key, fractional attribution, four definitions and seven-key non-usage serialization. Retain the direct `_usage_totals` bucket contract in `test_enh3532_codex_rollout_usage.py` while allowing unavailable values.
- `scripts/tests/test_enh3732_session_derive_status.py` (new) — real Claude ingestion/derive/prune with coalesced snapshots, two candidates/one observation, audit correspondence through raw links, corrupt/mismatched contracts, omitted/no-usage/excluded-only evidence, session-local lag, complete requested-session coverage, source loss and retained as-of behavior. Assert frozen result, package exports, query-only execution, byte-identical source files and forbidden source/derive/pricing calls.
- `scripts/tests/test_feat3410_workspace_quality.py` and `test_feat3418_workspace_quality.py` — member-local checkpoints, colliding IDs with unrelated audit groups, shared sessions, member-order permutations, absent/out-of-scope members and a WAL commit during analysis. Add the asymmetric case: A associates session S with an issue; B has S usage plus an unresolved candidate but no S issue association; B must still taint totals. A third member with no S evidence must not. Assert proof and usage use the same attached-member snapshot, no first-member certification, one-member totals parity, exact union relations, attach-limit handling and owned-resource cleanup.
- `scripts/tests/test_cli_history.py` — actual usage-bearing text/markdown/JSON/YAML output. Preserve `test_usage_selection_chokepoint_gate.py` and `test_history_store_chokepoint_gate.py`; no new raw SQLite history openers or token/cost SQL outside the existing seam.

### Documentation

Update `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, reader/issue-history package docstrings and `scripts/little_loops/pricing.py` docstring. Remove “always computable”, 50%-coverage permission and zero-as-unmeasured claims. State transcript scope, unchanged denominator, member-additive population, broad host diagnostic and labeled historical periods. Follow end-user audience rules; retain pinned reference headings and run audience/count gates.

## Acceptance Criteria

- [ ] Partial/unknown numeric-cost observations and invalid components cannot produce complete token/cost figures, priced-complete coverage or verdicts; qualified tokens remain available when only cost is unpriced.
- [ ] Excluded live/rollout rows cannot change transcript values/qualification/model composition; denominator, fractional attribution and correction/fix/retry definitions are preserved.
- [ ] Every session disposition above is exercised through real quality consumers. Coalescing does not create a gap; missing candidates, corrupt/unproved context and underived held work cannot disappear behind other observations or an advanced checkpoint.
- [ ] Safely retained qualified observations survive raw/source loss and conservation holds without requiring cursors; observation-free windows stay unavailable, not zero. No stat, source parse, re-derive, pricing or writes occur in the proof.
- [ ] Sample-sufficient unavailable values render with reasons in every output format; estimated/mixed figures have labels without trend verdicts. Usage-only metadata preserves non-usage serialization.
- [ ] Independent all-measured baseline/target eligibility, measured `[10, 0, 10]`, zero-mean guard and older eligible period labeling pass at both baseline stages.
- [ ] Workspace totals pin member proof and all contributor queries to the same attached revisions; collisions, shared sessions, concurrent commit and permutation controls preserve accepted member-additive populations and bounded diagnostics.
- [ ] Source-local pending evidence survives an advanced global scan high-water; older same-key observations and envelope/session mismatches cannot certify unresolved snapshots. Asymmetric shared-session members contribute proof whenever their evidence contributes to totals, independently of local issue associations.
- [ ] `python -m pytest scripts/tests/` exits 0, including chokepoint and documentation gates.

## Impact

- **Priority**: P2 — prevents audit-only/underived observations from becoming quality baselines.
- **Effort**: Large — session proof, nullable metrics and coherent member-local workspace integration.
- **Risk**: Medium — incomplete published trends become unavailable; preserve established non-usage behavior.

## Scope Boundaries

No producer algorithm, prune/replay storage, source-file freshness, snapshot/dashboard, repricing, legacy promotion or ENH-3730 availability redesign. The shared ENH-3744/3745 handoff is required before this issue closes.

## Implementation Steps

1. After ENH-3744/3745 land together, implement and test the query-only session-status helper against their actual interfaces.
2. Build transcript-scoped complete window populations, nullable usage numerators and defaulted per-metric metadata; preserve attribution and generic rate defaults.
3. Apply independent all-measured baseline/target eligibility and update every renderer, definition and note.
4. Obtain totals proof on attached-member snapshots, inject the deterministic conservative map and keep local identities member-qualified.
5. Exercise real writer-to-quality and CLI/workspace consumers, update docs and run the local suite.

## Confidence Check Notes

Historical checks in the session log predate the landed qualification/channel/safety core. On `main` those APIs exist; the session helper and shared ENH-3744/3745 handoffs remain proposed. Re-run verification/confidence after the prerequisites land; this review is not an implementation or readiness pass.

## Session Log

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
