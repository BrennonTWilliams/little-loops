---
id: ENH-3731
type: ENH
title: Shared usage qualification core, transcript channel scope, and source readers
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
relates_to:
- ENH-3732
- ENH-3733
- BUG-3696
- ENH-3543
- ENH-3528
- ENH-3730
- ENH-3671
- ENH-3672
- ENH-3673
- ENH-3674
- ENH-3675
- ENH-3676
---

# ENH-3731: Shared usage qualification core, transcript channel scope, and source readers

## Summary

Add the shared qualification contract for canonical stored-usage figures and route the source readers through it. This child owns `qualify_usage`/`UsageQualification` with fixed row admission, the logical `channel=` acquisition scope on both coverage selectors, and the source-side consumers (`aggregate_usage`, `cost_attribution`, `waste_attribution`, `ll-ctx-stats` all-history/per-model and the stored cache-rate path). Sibling children ENH-3732 (quality) and ENH-3733 (snapshot/dashboard) consume this contract and are blocked by this issue.

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. The parent's recorded **Decision (2026-10-04, `/ll:decide-issue`, commit `01747bb96`)** is authoritative and is not reopened here:

1. Legacy NULL provenance is conservative: audit-only, exactly like explicit `unknown`; no provenance-presence column or compatibility label.
2. Complete `estimated` rows are admitted in general consumption reports with an explicit `estimated`/`mixed` label; cache rate stays measured-only; quality trends require all-measured composition.
3. Decision 4 (Option A, refined): `channel=` scope on `select_usage_coverage`/`select_usage_observations`; the store-wide ambiguity gate and ENH-3543's contract are unchanged (narrowing it belongs to ENH-3730).

## Current Behavior

`ObservationGroup.total` gates on coverage and component presence; `aggregate_usage` can return numeric components with unknown provenance. `ctx_stats._aggregate_usage_events` publishes `ObservationGroup.subtotal` as canonical `usage_by_model.totals` with cost availability `available`. `waste_attribution` has its own coverage-only numeric gate. A partial row (input 10, output 2, cache-read 4, cache-creation NULL) with unknown **or measured** provenance and stored cost $1 publishes canonical input/output/cache-read/cost from source readers. `_compute_cache_rate_from_usage` separately requires measured usage and a complete denominator.

## Expected Behavior

- Row admission precedes figure completeness: an observation missing any of the four `TOKEN_COLUMNS` is audit-only for every canonical figure, regardless of provenance or requested component. Missing `cost_usd` alone is a pricing gap, not a partial-token row. Unrecognized stored provenance fails closed like explicit unknown.
- Qualification evaluates every coverage-selected contributor in the requested aggregate; if any contributor fails the figure's contract the canonical figure is unavailable with a bounded reason code. Audit subtotals stay numeric and distinctly labeled; derived totals never turn missing components into zero. A stored numeric `cost_usd` alone cannot qualify an audit-only row.
- Figure prerequisites (after coverage reconciliation and row admission):

  | Figure | Prerequisites |
  | --- | --- |
  | Token component / four-component consumption | Every in-population row admitted; each requested component present. |
  | Cost / cost per issue | Every contributor admitted with a stored numeric cost; no read-time repricing; no priced-subset sums. Dollars are API list-price estimates. |
  | Waste tokens / percentage | Admit the full joined population; keep the existing **input + output** definition, wasted-run subset and nonzero-denominator rule. |
  | Session cache hit rate | Every contributor admitted **and measured**; input, cache-read and cache-creation form the complete denominator; zero denominator is unavailable. |

- `select_usage_coverage(..., channel: str | None = None)` and `select_usage_observations` with the same argument: resolve logical channels with `row_channel` (including legacy NULL/absent channel with a session ID) before grouping and before computing `ambiguous_cross_channel`. Default `channel=None` preserves the current store-wide gate; `since`/run filters still apply after coverage reconciliation. Selectors stay coverage-only and keep audit-only rows in `selected_usage_events`.
- **Freshness contract**: qualification of a stored observation and completeness of the current source are separate. Preserve qualified historical/as-of Claude/Codex figures with existing freshness, lag reason and as-of metadata; stale/unknown cannot read as current. A cache rate over only the complete subset of selected observations is not permitted. Characterize text and JSON behavior before extending to other hosts.
- `ll-ctx-stats` all-history/per-model JSON keys keep their existing public numeric keys, show canonical values only when qualified, expose labeled audit subtotals distinctly, and never mark metadata `available` for an unavailable canonical field. Qualified tokens with missing model pricing stay canonical while cost is unavailable.
- Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown ingest-time evidence.

## Proposed Solution

Factor a small immutable `UsageQualification` (eligibility, provenance label `measured`/`estimated`/`mixed`/`unknown`, bounded reason code, audit known/missing and rejected-contributor counts) from the `ObservationGroup`/coverage chokepoint in `token_provenance.py`:

- `qualify_usage(group: ObservationGroup, required_components: tuple[str, ...]) -> UsageQualification` — always enforces fixed row admission first; `required_components` adds figure requirements and cannot relax the four-component or provenance gate. Cache-rate measured-only qualification can only tighten the result. No caller-supplied admission policy. `mixed` is an aggregate label only; never store it.
- Treat `ObservationGroup.subtotal` as an explicitly labeled audit operation, including when used to sort reports.
- Add `channel` to both selectors in `history_reader/usage.py` and thread it through the coverage/ambiguity computation.
- Apply qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`, `ctx_stats._aggregate_usage_events` and `_compute_cache_rate_from_usage`.
- Keep snapshot (`queries.py`) and quality (`agent_quality.py`) untouched here; they are ENH-3733 and ENH-3732.

## Integration Map

### Files to Modify

- `scripts/little_loops/token_provenance.py` — `ObservationGroup` qualification, `entry`/rendering metadata, numeric-vs-audit distinction.
- `scripts/little_loops/history_reader/usage.py` — `channel=` scope on both selectors; qualification in `aggregate_usage`, `cost_attribution`, `waste_attribution`.
- `scripts/little_loops/history_reader/__init__.py` — re-export/doc updated selector signatures and `qualify_usage`.
- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_usage_events`, `_compute_cache_rate_from_usage`, as-of/freshness text/JSON parity.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py` — read-only; incremental/rebuild/refresh policy tests only.

### Tests

- `scripts/tests/test_enh3528_token_provenance.py`, `test_enh3543_usage_coverage.py`, `test_enh3656_stored_cache_rate.py`, `test_usage_selection_chokepoint_gate.py`; parameterized matrix of measured/estimated/explicit unknown/legacy NULL, mixed measured+estimated, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage; measured Claude/Codex controls; representative remaining-host partial row; measured-partial numeric-cost probe; aggregates mixing eligible and audit-only contributors; transcript-scope controls (live counterpart for same and unrelated session cannot change values; unscoped coverage still blocks).

### Documentation

- `docs/reference/API.md` (selector signatures, `qualify_usage`), `docs/reference/CLI.md` (consumption figures, unavailable-rate semantics, dollars as estimates).

## Acceptance Criteria

- [ ] Implementation/tests/docs match the recorded policy: legacy absent/NULL audit-only, complete estimates labeled numeric consumption, cache rates measured-only; compatibility consequences documented.
- [ ] Matrix covers measured/estimated/explicit unknown/legacy NULL, mixed aggregates, unrecognized provenance, each missing token component, complete tokens × non-overlapping/unknown/unresolved coverage, measured Claude/Codex controls, the representative remaining-host partial row, the measured-partial numeric-cost probe and eligible+audit-only mixes.
- [ ] Every selected contributor satisfies each figure's prerequisites or the full canonical figure is unavailable with a bounded reason; silently dropping an in-filter ineligible row cannot make a total or rate appear qualified; numeric stored cost cannot bypass token/provenance prerequisites; empty selection is unavailable while a qualified observed zero is zero.
- [ ] A complete measured observation plus a coverage-selected observation missing input, cache-read or cache-creation makes the session cache rate unavailable, with audit subtotals, missing counts and reason preserved.
- [ ] `channel="transcript"` on both selectors reconciles transcript and legacy NULL/absent-channel rows with a session ID before coverage analysis; excluded live/rollout counterparts cannot change values or qualification; default unscoped coverage still blocks unresolved counterparts; `since`/run filters cannot certify coverage; selected populations/counts (including audit-only rows) stay intact.
- [ ] `ll-ctx-stats` all-history/per-model JSON and text show canonical values only when qualified, with distinct labeled audit subtotals and valid provenance pointers; metadata never says `available` for an unavailable field; qualified tokens with missing pricing stay canonical while cost is unavailable; dollars are visibly estimates.
- [ ] Existing Claude/Codex text and JSON retain qualified as-of values and freshness diagnostics after append/source loss; stale/unknown never described as current; failed derive is unavailable/unknown, not a fresh zero.
- [ ] Incremental derive, full rebuild and repeated refresh preserve the policy and cannot promote unknown evidence.
- [ ] Publication gate recorded: ENH-3671–3676 cite this shared contract and pass qualification tests before enabling production derivation of newly recognized usage rows; because source, snapshot and quality readers all discover `usage_events`, that gate requires **ENH-3731, ENH-3732 and ENH-3733 together**. Capture/adapter/raw-retention work can proceed independently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope:** snapshot export/dashboard (ENH-3733), quality derive status/baselines/workspace (ENH-3732), ENH-3730's store-wide ambiguity redesign, provider capture and adapters, derive-algorithm or source-freshness changes, component-level measured exceptions, pricing fallback.

## Session Log

- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2
