---
id: FEAT-3712
type: FEAT
title: As-of implement-issue backtest report for ll-next
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:45:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
---

# FEAT-3712: As-of implement-issue backtest report for ll-next

## Summary

Produce a reproducible as-of backtest report for `ll-next`'s `implement-issue` ranking: top-3 hit rate and MRR versus `ll-issues next-issue`, with a ground truth that controls for ll-auto contamination. A report, not a suite assertion.

## Current Behavior

No evidence exists that `ll-next`'s within-type `implement-issue` ordering beats or differs from `next-issue`. Replaying "what would have been recommended" on historical state needs all signal sources reconstructed as of a past point.

## Expected Behavior

A script/CLI emits a report over ~50 sampled historical commit SHAs. For each SHA it reconstructs issue files via `git ls-tree`/`cat-file`, history events with `ts <= as_of`, and staleness from capture/commit time rather than checkout mtime. Ground truth is the issue actually started after `as_of` (`skill_events` `manage-issue` ID match). The report is **stratified** into manual-session picks (primary) and ll-auto/ll-parallel picks (`orchestration_runs`), because ll-auto's ordering may track `next-issue` and bias the comparison toward the baseline. It includes a priority-only baseline and reports unresolvable samples explicitly. No pressure is involved (within-type only).

## Motivation

The scorer is only trustworthy if it is compared against the existing recommender on an uncontaminated ground truth; without this the arena's ranking claims are unfalsifiable.

## Proposed Solution

1. First, directly measure how often ll-auto's pick equals `next-issue`'s top-1 on the same state; document the result in the report header and decide stratification from it.
2. Implement as-of reconstruction helpers (pure; take `as_of`), sampled deterministically (fixed seed, fixed SHA list in the report).
3. Run `ll-next`'s `implement-issue` generator + scorer, `next-issue`, and a priority-only baseline on each reconstructed state; compute top-3 hit and MRR per stratum with sample counts.

## Integration Map

### Files to Modify

- New report module/script under `scripts/little_loops/` (no new third-party dependencies), tests for reconstruction helpers against a synthetic git repo, `docs/` note on how to run it.

## Implementation Steps

1. Measure ll-auto vs `next-issue` top-1 agreement on a sample and record it for the report header.
2. Implement pure as-of reconstruction helpers and the deterministic SHA sampler; test against a synthetic git repo for leakage.
3. Run `ll-next`'s `implement-issue` scorer, `next-issue` and the priority-only baseline per state; compute top-3 hit and MRR per stratum.
4. Document how to run the report.

## Use Case

A maintainer changes the `implement-issue` default weights and reruns the report to see whether top-3 hit rate on manual-session picks moved relative to `next-issue`, without being fooled by ll-auto's own ordering.

## Program Design

### Types

- `BacktestSample(sha, as_of, started_issue, origin)` is a typed record; `origin` is `manual` or `orchestrated`.

### Signatures

- `reconstruct_state(repo: Path, sha: str, *, as_of: datetime) -> ProjectState` — rebuilds issue files from git at `sha` and keeps only history events with `ts <= as_of`.
- `score_backtest(samples: list[BacktestSample], rankers: dict[str, Ranker]) -> BacktestReport` — returns top-3 hit rate and MRR per ranker and per origin stratum with sample counts.

### Call Path

Report entry point → deterministic SHA sampler → `reconstruct_state` → `generate_candidates` / `find_issues` rankers → `score_backtest` → rendered report.

## Impact

- **Priority:** P3
- **Effort:** Medium
- **Risk:** Low–Medium — leakage of future state is the failure mode; helpers are tested against a synthetic repo.
- **Breaking Change:** No.

## Scope Boundaries

- **In scope:** the report tool, reconstruction helpers, stratified metrics, a small hermetic fixture test of the helpers.
- **Out of scope:** other verbs, pressure, live acceptance reporting, a CI-gated assertion on the metrics.

## Acceptance Criteria

- [ ] Report is reproducible (fixed seed, recorded SHA list) and states the measured ll-auto/`next-issue` agreement rate.
- [ ] No future leakage: issue files from `git` at the SHA, events `ts <= as_of`, staleness from capture/commit time; synthetic-repo test proves it.
- [ ] Metrics are reported per stratum (manual vs ll-auto) with sample sizes, plus the priority-only baseline.
- [ ] `python -m pytest scripts/tests/` passes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P3
