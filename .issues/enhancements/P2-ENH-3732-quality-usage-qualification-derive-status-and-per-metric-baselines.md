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
relates_to:
- ENH-3733
- ENH-3730
- ENH-3543
---

# ENH-3732: Quality usage qualification, session derive status, and per-metric baselines

## Summary

Make the agent-quality report obey the shared usage qualification policy. This child scopes quality acquisition to the transcript channel, adds a member-local read-only per-session derive-status helper (with workspace map injection), carries optional token/cost numerators with per-metric qualification, and replaces the zero-as-unmeasured baseline proxy in `quality_regressions` with explicit all-measured trend eligibility. Blocked by ENH-3731 (`qualify_usage` and the `channel=` selector scope).

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. Parent Decision (commit `01747bb96`) items 2, 3, 4 and 5 apply: quality baselines/verdicts require an all-`measured` composition; the 5 phantom zero baselines and 9 unknown-containing windows (all 7 non-stable verdicts) become unavailable with a reason; underived in-scope sessions make their window unavailable; do not change `_rate_metrics`' absence-equals-zero default (correction/fix/retry counts depend on it) — pass usage qualification in separately.

## Current Behavior

`agent_quality._usage_totals` reads annotated audit rows, ignores qualification and coerces missing components to zero: a partial/unknown row with stored cost $1 yields `tokens: 16`, `cost: 1`, `priced_rows: 1`, `total_rows: 1`. `_rate_metrics` makes a five-closed-issue window with no usage numerator a `0.0`, `stable` baseline that later priced windows are compared against. `_metric_eligible_as_baseline` rejects observed zeros, so `[10, 0, 10]` with two prior baselines produces no regression (complete mean would be `5`). A verified complete measured transcript row is coverage-selected only until an unrelated unidentified live row trips the store-wide ambiguity gate; quality's later channel filter cannot undo that annotation. Workspace quality exposes raw/usage union views but no member-local derive proof, so a bare `meta` read on the union resolves to an attached member.

## Expected Behavior

- **Transcript scope:** quality requests `channel="transcript"` from the selectors (added in ENH-3731). Excluded live/rollout counterparts cannot change values, qualification or model-composition inputs. Within scope, unknown/partial/unresolved contributors stay as completeness contributors and the same coverage/qualification rules apply. Text/JSON and metric definitions state the transcript-only numerator, that Codex rollout/live work is excluded, and that the closed-issue denominator is unchanged.
- **Derive completeness:** `select_session_derive_status(conn, session_ids) -> dict[str, SessionDeriveStatus]` in `history_reader/usage.py`, read-only over committed `raw_events` and the member's `meta.usage_derive_version`/`usage_derive_raw_id`. It never stats source files, calls `usage_source_freshness`, requires source cursors or re-derives; it reuses the deriver's version constant. Every requested session gets a status (missing proof cannot omit a key). Dispositions:

  | Attributed-session evidence | Disposition |
  | --- | --- |
  | In-scope raw evidence, missing/invalid checkpoint or absent/mismatched derive version | Unavailable: `derive_pending` |
  | In-scope raw evidence with session-local max raw ID above the member checkpoint | Unavailable: `derive_lagging` (unrelated sessions' later IDs do not taint it) |
  | In-scope usage observations, no pending/lagging raw evidence | Apply shared row qualification and coverage (legacy/as-of usage stays qualified even without retained raw/cursors) |
  | No in-scope observations, evidence proves only excluded channels | `out_of_scope`; ignored for this numerator, denominator unchanged |
  | Fully checkpoint-covered raw, no usage observations | `derived_no_usage` (contributes nothing, not a zero); a retained ingest-time `usage_contract` recognized by the existing transcript producer proving a usage candidate with no derived observation is unavailable `derive_gap` |
  | Neither raw nor usage evidence, or unreadable/inadequate evidence for an in-population session | Unavailable: `no_evidence` / `derive_status_unavailable` |

  Any unavailable session blocks the usage-derived figures of every window it is fractionally attributed to. A window with zero in-scope observations stays `no_observations`. Keep these codes namespaced apart from the source-freshness `derive_pending` in `session_store/lifecycle.py`.
- **Per-metric qualification:** propagate `None` through optional numerators; a qualified observed zero is zero; no observations or unmet prerequisites are unavailable. Cost cannot qualify on a partial priced subset, even above the legacy 50% verdict threshold. Preserve `sample_size`, fractional attribution and coverage diagnostics. Qualification, sample insufficiency and trend eligibility are separate metadata; `insufficient_history` keeps meaning only the sample gate failed. Estimated/mixed numeric values carry labels and a reason explaining why they have no verdict. `_format_metric_line` must render sample-sufficient unavailable metrics without asserting a number.
- **Baselines/verdicts:** select the earliest qualified, sample-sufficient, all-measured baseline independently for tokens and cost (not the earliest closed-issue window). Replace `_ZERO_INELIGIBLE_BASELINE_METRICS` for usage metrics with explicit eligibility; a measured `[10, 0, 10]` series with two prior baselines includes the zero (mean `5`, relative increase `1.0`) while the zero-**mean** division guard stays. Keep `_rate_metrics`/`classify_verdict` zero-baseline behavior and regression-window/model-composition rules otherwise. Label the period of any older eligible result; never present it as a verdict for an unavailable latest window.
- **Workspace:** compute derive status per member on the already-open read-only connections, merge conservatively across members in which a session participates (retain any unavailable member's reason; excluded-channel-only members contribute nothing; a member with no association does not invent a missing status), and inject the map via `analyze_agent_quality(..., derive_status: Mapping[str, SessionDeriveStatus] | None = None)`. `None` computes locally; a supplied map is authoritative, missing keys fail closed, and there is no fallback to unqualified `meta` on the union. Never compare raw IDs/checkpoints across members. Keep repository/issue discriminators, TEMP union views and `_UNION_RELATIONS`.

## Proposed Solution

Introduce immutable `SessionDeriveStatus` (bounded status/reason, in-population disposition; no raw IDs or paths in serialization), extend `QualityMetric` with defaulted qualification/provenance/reason/trend-eligibility fields preserving existing keys and non-usage callers, and assemble quality windows in order: declared scope → coverage → session derive status → complete per-window population → per-metric qualification/value → baseline/verdict.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader/usage.py` and `history_reader/__init__.py` — `select_session_derive_status`, `SessionDeriveStatus` (re-export).
- `scripts/little_loops/issue_history/agent_quality.py` — `_usage_totals`, `_rate_metrics`, `QualityMetric`, callers, metric definitions, text/JSON diagnostics, `_format_metric_line`, `derive_status` parameter.
- `scripts/little_loops/issue_history/quality_regressions.py` — all-measured target/baseline eligibility, replace the usage zero-as-missing exclusion, keep the zero-mean guard and model-composition inputs on the transcript/legacy population.
- `scripts/little_loops/issue_history/workspace_quality.py` — member-local status and merged map injection.

### Dependent Files

- `scripts/little_loops/session_store/lifecycle.py`, `writers.py`, `claude_usage.py` — read the derive-version/checkpoint and producer-contract definitions; factor/re-export a constant only if needed. No derive-algorithm, source-freshness, producer-contract or migration change.

### Tests

- `scripts/tests/test_issue_history_agent_quality.py` (also holds quality-regression tests), `test_feat3410_workspace_quality.py`, `test_feat3418_workspace_quality.py`. Query-only status cases: missing/version-mismatched checkpoint, session-local lag, recognized positive contract without derived usage, fully derived non-usage raw, no evidence, source loss. Workspace tests use overlapping raw IDs and different member checkpoints, proving neither an eligible member nor the first attached `meta` can certify an underived member. Drive actual consumers, not just helpers.

### Documentation

- `docs/reference/API.md`, `docs/reference/CLI.md` — update metric definitions that currently say tokens are always computable or price coverage withholds only the verdict.

## Acceptance Criteria

- [ ] Quality cost/token numerators obey shared qualification, including the partial/unknown row with numeric stored cost; ineligible contributors stay in completeness accounting and cannot become zero tokens, 100% priced coverage or a numeric verdict; channel pins and qualified-history controls preserved.
- [ ] Windows with no usage or any audit-only contributor have unavailable usage-derived values with reasons and cannot become zero baselines; the next qualified, sample-sufficient window supplies the baseline; qualified zeros remain zero; correction/fix/retry metrics, fractional multi-issue attribution and workspace-union populations keep their definitions; an older regression result names its actual period.
- [ ] Transcript-scoped quality: adding excluded live/rollout counterparts (same and unrelated session) cannot change values, qualification or model composition; in-scope unknown/partial/unresolved rows remain completeness contributors; text/JSON state the transcript-only numerator and unchanged denominator.
- [ ] Baselines/verdicts require qualified sample-sufficient all-measured values independently for tokens and cost; estimated/mixed windows show labels/reasons but cannot be targets or baselines; measured `[10, 0, 10]` with two prior baselines yields mean `5` and relative increase `1.0`; no-observation windows stay unavailable; an all-zero mean keeps the division guard; text/JSON render sample-sufficient unavailable metrics without exceptions or false insufficiency labels.
- [ ] Attributed sessions with in-scope raw evidence and absent/invalid/version-mismatched proof or session-local lag make each touched window unavailable with bounded reasons; recognized positive contract without a derived observation is `derive_gap`; fully derived non-usage raw needs no usage row; no evidence or zero in-scope observations never becomes zero; proved rollout/live-only sessions stay excluded; source deletion and unrelated later raw appends cannot invalidate qualified stored sessions; helpers run on `query_only` connections with no writes, re-derivation or source reads.
- [ ] Workspace analysis uses member-local proof and a conservatively merged injected map; colliding raw IDs with different checkpoints on a shared window cannot publish a complete subset total; bare first-attached `meta` cannot certify another member; shared-session merging and absent/out-of-scope members tested; attribution/discriminators and union relations preserved.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope:** qualification core and selectors (ENH-3731), snapshot/dashboard (ENH-3733), source-to-raw freshness, derive-algorithm changes, re-deriving unknown transcript rows (promotion is forbidden), ENH-3730's gate redesign.

## Session Log

- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2
