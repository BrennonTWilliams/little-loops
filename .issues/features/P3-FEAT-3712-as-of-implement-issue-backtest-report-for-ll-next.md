---
id: FEAT-3712
type: FEAT
title: As-of implement-issue backtest report for ll-next
priority: P3
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
relates_to:
- FEAT-3711
---

# FEAT-3712: As-of implement-issue backtest report for ll-next

## Summary

Original proposal: produce a reproducible historical **choice-agreement** report for ll-next's within-type implement-issue ranking: hit@3 and MRR versus the existing next-issue ranking rule and a priority-only baseline, with explicit sample coverage, temporal cutoffs, origin uncertainty and paired uncertainty estimates. A **diagnostic report**, not a metric suite assertion, pass/fail gate or proof that recommendations improve project outcomes. Interval width depends on observed choices/sample dependence; a small sample is descriptive evidence, not a fixed precision guarantee. **The pre-implementation source audit failed: no structured source supplies the required clean recorded base paired with confirmed-manual choice provenance. This implementation is cancelled; the design below is retained for a future evidence-backed proposal.**

## Current Behavior

No evidence compares the arena's ordering to existing recommendations. Arbitrary historical SHAs can precede no relevant choice, repeat the same label, or contain future/current metadata. Manage-issue telemetry may be optional/backfilled; orchestration rows identify picks before readiness gates, not necessarily work that actually started. Absence of an orchestration row is insufficient proof a pick was manual.

## Expected Behavior

A read-only report tool evaluates up to 50 eligible historical decision samples with a recorded manifest and fixed seed. It reconstructs issue/config content at a SHA, scores using FEAT-3561's immutable ProjectState with a fixed UTC as_of, and looks forward **only to obtain a label** within a declared seven-day horizon. It reports two strata: **confirmed-manual** (affirmative provenance) and **other** (orchestrated or unclassified, shown with its orchestrated/unclassified sub-counts for transparency but not as a separate primary stratum). Unknown origin stays unknown; no orchestrator match must not silently become manual.

Report matched picks and each exclusion/censoring reason, even if fewer than 50 or zero defensible samples remain. Pressure and recommendation attribution are not feature inputs. The report answers whether ranking agrees with observed choices; completion/outcome value is outside scope.

## Motivation

A convincing recommender needs inspectable empirical comparisons. Historical choice agreement is useful only with honest candidate eligibility, reproducible snapshots and a visible distinction between algorithm-driven picks, independent user choices and unavailable ground truth.

## Proposed Solution

### Decision samples and label contract

- Sample decision opportunities associated with observed explicit implementation requests/picks, rather than 50 unrelated SHAs. Import FEAT-3561's pure typed action parser/canonicalization rules: manage-issue TYPE fix/implement/improve ID, excluding plan/verify/plan-only/dry-run; orchestration picks require valid issue/start identity. Reject ambiguous skill-name/argument syntax and capture at the existing 200-character/50-token truncation boundaries, where hidden flags cannot be ruled out. Deduplicate hook/backfill copies and a skill request correlated to the same orchestration pick; do not count one choice twice.
- Prefer an orchestration row's `base_sha` with `base_dirty=false` for an exact committed base snapshot, with feature as_of immediately before the pick. Otherwise use a first-parent committed state preceding the request as a **proxy**, record that limitation, and exclude all proxy/known-dirty/unreconstructible state from the primary clean-base comparison. Anchor proxy traversal to an explicitly recorded ancestry tip/ref; never silently choose today's branch. In first-parent traversal order, choose the nearest ancestor whose committer timestamp precedes the boundary, and record that heuristic and timestamp anomalies. Commit dates alone do not prove historical availability or capture uncommitted scores/config; proxy results remain secondary even when the current worktree is clean.
- `as_of` is the feature cutoff. The label is the first eligible observed implementation request/pick **strictly after** it and within `label_horizon_days=7`; allow a named `before_event` boundary for equal-timestamp starts without admitting that event into features. Label queries may look through the separate `label_cutoff`; feature readers never may. Requests/picks are observational labels, not proof Phase 3 started.
- Deterministic simultaneous-choice ties use `(event_time, semantic_event_key)` and are flagged as ambiguous rather than silently inventing user preference. Exclude ambiguous labels from the primary comparison, retaining their counts.
- Unknown/missing target, no in-horizon pick, incomplete follow-up observation, or missing SHA/config/source yields an explicit exclusion/censoring reason. Include a label outside the candidate population in coverage reporting; never silently drop it or call it a ranking miss. Avoid overlapping windows that label the same event repeatedly; keep one sample per chosen event/base snapshot.
- Freeze `observation_end` and availability/coverage basis **per label source**. The latest observed event is not proof of complete observation through that timestamp, and absence of a pick is not proof none happened. If follow-up coverage cannot be established, report `followup_unknown`; if a known source window ends before label_cutoff, report censoring. Neither state becomes a negative ranking label.
- Freeze the eligible source window and sample manifest first; deterministically select up to 50 distinct opportunities (fixed seed if downsampling). Record the exact SHA, as_of, label cutoff, semantic label event, snapshot quality and origin evidence. Reuse this manifest when comparing weight changes.

Keep a frozen **sample/input digest** separate from a per-run **evaluation digest** (code version, baseline strategies, effective weights/gates/config). Reusing samples with changed weights creates a new evaluation record without rewriting the frozen observations. Pure weight comparisons hold candidate eligibility fixed. If gates or reconstruction policy change, report population/coverage changes separately and compute paired ranking deltas only on the explicitly common scorable sample set. This is reproducibility bookkeeping, not a parameter-tuning workflow.

### Snapshot reconstruction and ranking comparability

- Reconstruct from git tree/blob objects (one `git cat-file --batch` process, not one checkout per sample), without checking out files, changing the worktree/index, or reading today's issue files. Include all configured issue categories/statuses needed by the full dependency graph, terminal resolution, frontmatter scores, raw capture metadata and Session Logs. Detect missing/deleted references and cycles with the core's gate policy.
- Use config committed at the sample SHA plus defaults from the **recorded evaluated implementation version**; explicitly omit today's gitignored ll.local.md and environment overrides. Snapshot any tracked goals/other file actually consumed by core features. Record baseline strategy/effective next weights/gates/config digest per sample; skip unsupported historical config rather than silently substituting today's project settings.
- For staleness/momentum, use timestamps present in that historical content and git history reachable from the SHA only. Normalize UTC; no checkout mtime or later commit on another branch. Capture all derived values from the same as_of.
- FEAT-3561 implementation scoring uses files/git, so no history reader is necessary for ranking features. History is a bounded read-only **label/provenance input** here; use existing backend read-only seams independently of FEAT-3711. Mutable final orchestration status/head/ended fields and later skill completion fields cannot leak into features. Future-label origin joins are allowed only in the label stage, with that purpose explicit.
- Rank the same common candidate population for all three rankers: leaf `open` issues passing the core's dependency/status/readiness policy at the snapshot. Reuse the next-issue `build_sort_key` rule on that injected population, including its historical configured strategy; do not invoke the live CLI or add future scores. Its sort key has no final ID component: first reproduce find_issues' `(priority_int, issue_id)` ordering, then apply the stable baseline sort. Do not let arbitrary git enumeration order break equal configured keys. Priority baseline orders by `(priority_int, issue_id)`; arena uses its real deterministic tie-breaks. This compares **ranking rules on a common eligible set**, not each CLI's full end-to-end selection policy.
- Separately report candidate coverage: observed labels not found/not open/blocked/not ready, missing sources and how many choices the common population can score. A label outside this population is unscorable for this comparison, not evidence the arena should bypass its gates.

### Origin and metrics

- **Circularity caveat:** orchestrated runs (ll-auto/ll-parallel/ll-sprint) chose issues with the priority/next-issue rule, so agreement with those labels largely measures a baseline against itself; only confirmed-manual choices carry independent signal. Orchestrated = affirmative exact issue/run/time provenance (per-issue skill events nested in those runs belong here). Confirmed manual requires affirmative provenance (or an explicit reviewed annotation in the saved manifest); unmatched/missing provenance is `other`/unclassified, never manual. Two strata: manual vs other. Report proxy snapshots separately from clean recorded bases.
- Measure ll-auto/next-issue top-1 agreement on the common population and report the denominator/unknowns. This is a contamination sanity check, not a rule that can relabel an origin. Do not choose strata after seeing the agreement result.
- `hit@3 = 1` when the chosen issue is among the first `min(3, len(ranking))` results, else 0. Reciprocal rank is `1/rank` for the chosen issue, else 0; use deterministic actual tie-breaks. Empty rank results are explicit and covered in denominators. Average metrics use exactly the same scorable samples for all three rankers.
- Show per-stratum counts, ranker hit@3/MRR, paired deltas versus both baselines, and paired bootstrap 95% intervals (stdlib implementation, recorded seed/resample count). No runtime tuning/metric pass threshold. State when evidence is insufficient (especially zero confirmed-manual samples or intervals including zero); `other` choices are exploratory, never presented as an uncontaminated manual primary result. History-derived axes (e.g. momentum Session Log timestamps) must be filtered to the as-of time so no future data leaks into features.
- Label sample-level bootstrap intervals as descriptive under dependent historical picks; several issues from the same orchestration run are not independent choices. Report distinct run/session counts where known. A cluster-bootstrap/statistical-inference framework is outside this small report; do not present these intervals as a calibrated causal significance test.
- Header: choice agreement is not proof of value, causation, successful implementation or superiority. Record sampling dates/manifest, code/ll version, git HEAD, dirty-code/config warning, baseline strategies, effective parameters, store/source identity without credentials, and timestamp/provenance limitations. A fixed SHA list alone is insufficient reproducibility when history backfill changes: save the extracted label/provenance inputs with a digest in the manifest.

## Integration Map

### Files to Modify

- New report module/script under `scripts/little_loops/`, using stdlib/existing dependencies; specify and document one entry point (prefer `python -m little_loops.next_backtest` to avoid an unnecessary new registered CLI).
- FEAT-3561 ProjectState/axis/gate adapters and existing next-issue sort helper through pure imports; existing resolved backend read-only helper for bounded label extraction.
- Hermetic synthetic-git/history fixtures and report metric/manifest tests; a docs note under `docs/guides/` explaining execution, reconstruction limits and reading the report.
- Private actual run artifacts belong in source-repo `postmortems/`, not the repo root or consuming-project templates; source-controlled docs contain only synthetic/public examples.

## Program Design

### Types

- `BacktestSample(sha, ancestry_anchor, as_of, label_cutoff, chosen_issue, label_key, origin, origin_evidence, snapshot_quality, exclusion_reason)`; origin `manual_confirmed` or `other` (with `origin_evidence` recording orchestrated vs unclassified).
- `BacktestManifest` freezes sample/label inputs, per-source observation bounds and their digest; a separate evaluation record pins evaluated code/config/baseline versions and parameters. `BacktestReport` includes both identities, metrics, paired intervals, sample coverage and exclusions.

### Signatures

- `reconstruct_state(repo: Path, sha: str, *, as_of: datetime, committed_config: Mapping) -> ProjectState` — pure reconstruction into core state from tree/blob objects.
- `build_sample_manifest(repo, history, *, seed: int, limit: int, horizon: timedelta) -> BacktestManifest` — separates feature and label cutoffs/provenance.
- `score_backtest(manifest: BacktestManifest, rankers: Mapping[str, Ranker]) -> BacktestReport` — common candidate set and paired metrics, no pressure.

### Call Path

New report entry point → existing backend `connect_readonly` for bounded label extraction → `build_sample_manifest` (new) → `reconstruct_state` (new) → core eligibility and existing `build_sort_key` baseline rule → `score_backtest` (new) → human and machine-readable report. Existing anchors live in `session_store/backend.py` and `cli/issues/search.py`; no invocation of the live recommendation CLI.

## Implementation Steps

0. **Pre-implementation source audit (go/no-go; does not require FEAT-3561).** First identify a source for affirmative manual origin and a source for the **same choice's** recorded `base_sha`/`base_dirty=false`; absence of an orchestration match proves neither. Inspect schema/producer contracts, then count exact parsed implementation requests and independently report proven clean/manual pairs. No source is distinct from a source with zero qualifying choices. Reviewed manifest annotations may establish origin only with explicit evidence, and cannot invent a clean base. Proceed only with **at least 30** defensible pairs under the clean-base primary policy; proxy-only/orchestrated evidence does not pass. On no-go, record evidence and mark `cancelled`, resolving the epic child without building reconstruction machinery. Do not use nonterminal `deferred` or create a provenance/collection subsystem in this issue. Audit result is recorded in Resolution below.
1. Implement after FEAT-3561 (and a passing probe); pin snapshot/label/origin/candidate-population contracts and the manifest format with synthetic data first.
2. Implement batch git reconstruction and pure ranker adapters; prove feature and label cutoff separation with a later score/config/status mutation fixture.
3. Implement deterministic sample selection, frozen label inputs, coverage/censoring tables, metrics and paired intervals.
4. Run the actual report if defensible samples exist, including auto/baseline agreement; document how to rerun the same manifest and all evidence limitations. A small/empty sample is a valid honest report.

## Scope Boundaries

- **In scope:** reproducible report tool/manifest, reconstruction, origin-aware choice agreement, candidate coverage/paired uncertainty, hermetic tests.
- **Out of scope:** other verbs, pressure, recommendation acceptance attribution, weight fitting, outcome-value claims, live learned policy or a suite assertion on metric quality.

## Impact

- **Priority:** P3
- **Effort:** Medium–Large — reliable reconstruction/label provenance is the main cost.
- **Risk:** Medium — future/dirty state, self-agreement and unclassified origin can make apparent gains misleading.
- **Breaking Change:** No.

## Use Case

A maintainer reruns the same saved manifest after an implement-issue weight change and sees paired rank changes against both baselines, together with sample coverage and uncertainty. They can distinguish algorithm-driven picks and unknown-origin proxy snapshots from independent user-choice evidence.

## Acceptance Criteria

- [ ] Feasibility probe run and recorded before reconstruction work; proceed only with ~30+ clean-base confirmed-manual samples, otherwise defer/close with the count.
- [ ] Reproducible saved manifest freezes samples, label/provenance inputs/digests, feature/label cutoffs, seed and evaluated code/config/baseline versions; supports fewer than 50 or zero eligible samples honestly.
- [ ] Proxy ancestry is explicitly anchored and always secondary; nonmonotonic commit dates, switched live branches and unknown source observation ends cannot invent an exact snapshot or a negative label. Frozen sample and evaluation digests permit weight-only reruns without changing observations.
- [ ] Synthetic git/history tests prove no future score/config/Session Log/status/mtime/branch leakage, no live worktree changes, known dirty/unavailable source handling and strict feature-versus-label stage separation.
- [ ] Exact implementation-request/pick parsing excludes planning/dry-runs and deduplicates correlated telemetry; horizon, ties, repeated labels, censoring and unscorable labels have explicit reasons/counts.
- [ ] Rankers use the same historical eligible population/config and actual deterministic tie-breaks; candidate/readiness coverage is reported separately and no baseline silently reads current project state.
- [ ] Equal next-issue sort keys preserve the existing `(priority_int, issue_id)` loader order; shared parser fixtures reject truncation/hidden flags, and eligibility changes between evaluation records are separated from weight-only ranking comparisons.
- [ ] Origins require affirmative provenance; manual-confirmed vs other (orchestrated/unclassified sub-counts) and clean/proxy snapshots are reported distinctly. Auto/next-issue agreement includes denominators and remains a sanity check.
- [ ] Hit@3/MRR, paired deltas and bootstrap intervals use matching samples with fixed seeds; report states choice-agreement limits and insufficient evidence. No assertion requires one ranker to win.
- [ ] Read-only backend extraction and report execution are documented; actual source-repo run evidence stays under postmortems/; `python -m pytest scripts/tests/` passes.

## Related Key Documentation

- `docs/reference/API.md` — issue parser, dependency graph and read-only history backend.
- `docs/reference/CLI.md` — next-issue baseline strategy and ll-next eligibility.

## Review Notes

- 2026-10-03: Pre-implementation/Opus review added decision-aligned samples, fixed label horizons, exact/proxy snapshot distinctions, unknown origin, common-population comparisons, frozen history inputs, exclusion coverage and paired uncertainty. Kept the backtest pressure-free and independent of FEAT-3711.
- 2026-10-03: Follow-up review pinned shared pure argument parsing, baseline stable-tie order after find_issues' priority/ID presort, explicit proxy ancestry/secondary-only comparisons, per-source follow-up uncertainty and separate frozen-sample/evaluation identities. Kept sample-bootstrap intervals descriptive without adding a tuning or statistical framework.
- 2026-10-04: Opus epic review (0.78): added the feasibility go/no-go probe (≥~30 clean-base confirmed-manual samples), the orchestrated-label circularity caveat, two origin strata instead of three, diagnostic framing (bootstrap width at n≤50), `git cat-file --batch` reconstruction and an explicit as-of filter on history-derived axes.
- 2026-10-04: Follow-up code/schema audit and Opus critique (0.78) found the probe's required provenance/base pair unavailable in the current producers. Ran the source audit before core implementation, made the threshold exact and the no-go status terminal, and retained the report design without implementing a proxy-only substitute.

## Resolution

**Cancelled — insufficient source evidence, 2026-10-04.** This is a source-contract no-go, not a claim that no manual implementation choices occurred. No report tool or reconstruction machinery was implemented.

Read-only audit of the source checkout's existing local history store (schema 58):

| Source | Observed evidence | Missing requirement |
|---|---|---|
| `skill_events` | 143 canonical manage-issue request rows; 52 have exactly the three implementation-shaped arguments under the existing bug/fix, feature/implement, enhancement/improve grammar; 91 are other/ambiguous requests. No rows reached the 200-character capture boundary in this count. | No choice-level `base_sha`/`base_dirty` or affirmative manual-origin field. The 52 are an upper bound on possible labels, not confirmed-manual samples; dedup/origin checks could reduce them. |
| `sessions` | Columns are session_id, jsonl_path, started_at, project_path. | No entrypoint/query_source/manual discriminator or clean-base stamp. Session membership/path alone cannot distinguish interactive from orchestrated choices. |
| `orchestration_runs` | At the audit query: 745 ll-auto rows (370 clean recorded bases), 20 ll-sprint rows (8 clean recorded bases). | These are affirmative orchestrated picks; their clean bases cannot be attached to unrelated skill requests to manufacture manual samples. |
| `hook_events` / generic transcript rows | Hook events carry head/branch; raw/message event tables carry session/source/content. No reviewed sample manifest was supplied. | Head/branch/content alone is not a choice-bound clean-base stamp. No raw transcript mining or retrospective annotation was used to substitute for the specified structured evidence. |

The schema/producer audit establishes **0 provable clean-base confirmed-manual pairs from the currently supported structured sources**, against the required 30. Origin and base quality of the 52 implementation-shaped requests remain unknown; this is not an observed count of zero manual choices. Store counts can change as concurrent tooling runs, while the missing source fields remain the blocking fact.

Reproduction: inspect `PRAGMA table_info(skill_events)`, `sessions`, `orchestration_runs` and `hook_events`; count canonical manage-issue rows and strictly parse only complete three-token implementation requests; group orchestration rows by driver and count non-null base_sha with base_dirty=0. `session_store/schema.py` documents the dequeue-time base stamp specifically on orchestration_runs. All access used `backend.connect_readonly(..., timeout=0.25)` with no backfill/migration or live worktree reconstruction.

Revisit only when a declared source supplies at least 30 confirmed-manual, choice-bound clean recorded bases, or a separately reviewed proposal changes the primary evidence policy. Proxy-only retrospective choices and recommendation acknowledgements do not satisfy this issue's retained contract. The epic may close with this recorded no-go instead of a diagnostic report.

## Status

**Cancelled** | Created: 2026-10-03 | Priority: P3 | Source-audit no-go: 2026-10-04
