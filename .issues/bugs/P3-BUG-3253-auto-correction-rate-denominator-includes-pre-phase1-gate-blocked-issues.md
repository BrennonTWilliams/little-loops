---
id: BUG-3253
type: BUG
title: Auto-correction rate denominator includes issues blocked before Phase 1 ever
  ran
priority: P3
status: open
testable: true
discovered_by: analyze_log
discovered_date: '2026-08-17'
discovered_commit: 6ba249d0
discovered_source: ll-auto run 2026-08-17T17:51-18:20 (--only ENH-3237,ENH-3240)
relates_to:
- BUG-3252
reconcile_attempted: true
confidence_score: 88
outcome_confidence: 60
score_complexity: 18
score_test_coverage: 12
score_ambiguity: 10
score_change_surface: 20
decision_needed: true
---

# BUG-3253: Auto-correction rate denominator includes issues blocked before Phase 1 ever ran

## Summary

The run summary's auto-correction rate divides the number of corrected issues by
`completed + failed`. Issues stopped by a pre-Phase-1 gate — confidence,
learning, or decision — land in `failed_issues` despite never having run
`/ll:ready-issue`, so they enter the denominator without ever having had the
opportunity to contribute to the numerator. The reported rate is mechanically
biased downward by exactly the number of gate-blocked issues.

## Steps to Reproduce

1. Run `ll-auto --only A,B` where issue A is ready and issue B is blocked by the
   pre-Phase-1 confidence gate.
2. Let A go through `/ll:ready-issue` and receive a `CORRECTED` verdict.
3. Read the PROCESSING SUMMARY block.

Observed, from the 2026-08-17 run:

```
[18:20:58] Issues processed: 1
[18:20:58] Failed issues: 1
[18:20:58]   - ENH-3240: below_readiness_threshold (0 < 85)...
[18:20:58] Auto-corrections: 1/2 (50.0%)
```

One issue ran Phase 1. It was corrected. The correct rate is 1/1 = 100%. The
reported rate is 1/2 = 50%, and the second denominator slot belongs to an issue
whose log shows `PHASE1_NOT_STARTED ENH-3240 confidence_gate`.

## Current Behavior

`scripts/little_loops/issue_manager.py:1971-1977`:

```python
if state.corrections:
    total_corrected = len(state.corrections)
    total_issues = len(state.completed_issues) + len(state.failed_issues)
    correction_rate = (total_corrected / total_issues * 100) if total_issues > 0 else 0
    self.logger.info(
        f"Auto-corrections: {total_corrected}/{total_issues} ({correction_rate:.1f}%)"
    )
```

`state.failed_issues` is populated by every non-success return from
`_process_issue`, including the three pre-Phase-1 gate branches:

- confidence gate — `issue_manager.py:813-833`, `failure_reason` prefix
  `below_readiness_threshold`
- learning gate — the `LEARNING_GATE_BLOCKED` branch referenced at
  `issue_manager.py:819-826`
- decision gate — the `decision_needed` halt

All three emit `PHASE1_NOT_STARTED`, which is precisely the discriminator this
computation needs and does not consult.

`scripts/little_loops/parallel/orchestrator.py:1653` carries an identical
computation for `ll-parallel` and has the same defect.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Only the confidence gate is genuinely pre-Phase-1; the learning gate is not.** Tracing `process_issue_inplace()`'s call order: the confidence gate (`issue_manager.py:800-835`) runs before the `# Phase 1` block. The learning gate (`issue_manager.py:1141-1207`) runs *after* `issue_timing["ready"]` is recorded — i.e. after `/ll:ready-issue` (Phase 1) has already completed with `is_ready=True`. An issue blocked by the learning gate had the opportunity to be auto-corrected during Phase 1, and per the finding below, often was.
- **The decision gate never produces a `_stamped_result` failure at all.** `issue_manager.py:1111-1136`: on a non-zero `/ll:decide-issue` returncode it only logs a warning and falls through to Phase 2 — "continuing to implementation anyway." It cannot contribute a `failure_reason` to `state.failed_issues` through this path, despite being listed as one of the three gate branches that do.
- **Corrections made during Phase 1 are preserved into `state.corrections` for a subsequently gate-blocked issue in the sequential path.** `corrections` is threaded into `_stamped_result(..., corrections=corrections, ...)` on the CLOSE/BLOCKED/NOT-READY/all-three-learning-gate failure branches (e.g. `issue_manager.py:1010, 1074, 1101, 1164, 1182, 1206`) — so an issue corrected by `ready-issue` and then blocked by the learning gate contributes to `total_corrected` *and* to the `+ failed` half of the denominator. This is the concrete mechanism producing the bias this issue describes, for the learning-gate case specifically.
- **The parallel path diverges independently, in the opposite direction.** `parallel/worker_pool.py` has no confidence-gate equivalent at all — a grep for the readiness-check entry point used elsewhere in this issue turns up no hits in that file. Its BLOCKED-verdict result does set `was_blocked=True` (`worker_pool.py:508-520`), but `ParallelOrchestrator._on_worker_complete`'s dispatch (`orchestrator.py:1071-1232`) has no `elif result.was_blocked` arm before its generic `else: self.queue.mark_failed(...)` (`1229-1232`) — so BLOCKED issues count toward `queue.failed_count` there, unlike the sequential path (which excludes them via `mark_skipped`, `issue_manager.py:2109-2111`). Separately, `WorkerResult.corrections` is attached only on the single success-path return (`worker_pool.py:743-744`) — every failure return (BLOCKED, NOT_READY, proof-first-task-gate-blocked) omits it, so the parallel path's numerator can never include a gate-blocked issue's corrections even though its denominator (`queue.completed_count + queue.failed_count`, `orchestrator.py:1649`) still counts that issue.

## Expected Behavior

The denominator counts issues that actually ran `/ll:ready-issue` — the only
issues that could have produced a correction. Gate-blocked issues are excluded.

For the observed run: `Auto-corrections: 1/1 (100.0%)`.

Ideally the summary also states what was excluded, so a reader can tell 1/1 from
1/1-of-2-attempted:

```
Auto-corrections: 1/1 (100.0%)  [1 issue gated before Phase 1]
```

## Impact

- **Severity**: P3 — cosmetic in a single run, but the docstring at
  `state.py:34` presents auto-corrections as a quality-tracking signal. A metric
  that drifts with unrelated gate activity is not usable for tracking issue
  authoring quality over time, which is its stated purpose.
- **Frequency**: every run containing at least one gate-blocked issue *and* at
  least one correction. 1 of 1 such runs observed.
- **Data Risk**: None.

## Root Cause

`failed_issues` is overloaded: it means both "attempted and did not succeed" and
"never attempted". The correction-rate computation needs the first meaning and
gets the union. This is the metrics-facing symptom of the classification problem
described in BUG-3252 Part 3.

## Proposed Solution

Two routes, depending on whether BUG-3252 Part 3 lands:

**If BUG-3252 introduces a distinct skipped/gated bucket** — this becomes a
one-line fix: `total_issues = len(state.completed_issues) + len(state.failed_issues)`
already excludes the new bucket, and only the optional "[N gated]" annotation
remains.

**Standalone** — filter the denominator on `failure_reason`. The three gate
branches have stable, greppable prefixes (`below_readiness_threshold`,
and the learning/decision equivalents); a shared
`_is_pre_phase1_gate_failure(reason: str) -> bool` predicate keeps the two call
sites (`issue_manager.py:1973`, `parallel/orchestrator.py:1653`) in agreement.

Prefer the first if BUG-3252 is being worked; it removes the string-matching.

Apply the same fix to `parallel/orchestrator.py:1653` regardless — the two
summary blocks are near-duplicates and should not diverge.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **The existing "no-silent-caps" annotation convention uses round-parenthesis inline suffixes, not square brackets.** Evidence: `_sample()` (`work_verification.py:48-58`, `"(first {limit} of {len(paths)})"`), `worker_pool.py:1365` (`"(+{N} more)"`), `issue_history/formatting.py:216,735` (`"(+{N} more)"`), `cli/issues/sequence.py:204` (`"… +{N} more"`). This issue's own suggested `[N gated]` bracket suffix (Expected Behavior) does not match this format; no prior example in the codebase uses square-bracket annotation.

## Program Design

### Types
N/A under the standalone route — the fix is a filtered count over data
`AutoManagerState` already holds. Under the BUG-3252-Part-3 route, the new type
is whatever skipped/gated bucket that issue introduces on `AutoManagerState`;
this issue then consumes it rather than defining it.

### Signatures
- `_is_pre_phase1_gate_failure(reason: str) -> bool` — new module-level helper, shared by both summary call sites — returns True when a `failure_reason` came from a gate that halted before `/ll:ready-issue` ran. Standalone route only; unnecessary if BUG-3252 Part 3 lands first.
- `AutoManager._log_timing_summary(self, run_start_time: float) -> None` — `scripts/little_loops/issue_manager.py:1949` — owns the `Auto-corrections:` line at `:1971-1977`. The single-line denominator change lands here.
- `_stamped_result(**kwargs: Any) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:768` — produces the `failure_reason` strings the standalone route would match on; the confidence-gate branch's is built at `issue_manager.py:827-830`.

### Call Path
`ll-auto` run completes -> `AutoManager._log_timing_summary()` (`scripts/little_loops/issue_manager.py:1949`) -> reads `state.completed_issues` and `state.failed_issues` -> `total_issues = len(completed) + len(failed)` at `:1973` -> `Auto-corrections: N/total` at `:1976`.

`state.failed_issues` is fed by every non-success `_stamped_result` return, including the three pre-Phase-1 gate branches — the confidence gate at `issue_manager.py:813-833`, plus the learning and decision gates referenced from the same comment block.

The parallel mirror: `ll-parallel` run completes -> `parallel/orchestrator.py:1653` -> the same computation over its own state.

### Decision Rules
- **Prefer consuming BUG-3252's bucket over string-matching.** If a distinct skipped/gated collection exists, `len(completed) + len(failed)` already excludes it and this issue reduces to the optional "[N gated]" annotation. Matching on `failure_reason` prefixes is the fallback, not the design.
- **One predicate, two call sites.** `issue_manager.py:1973` and `parallel/orchestrator.py:1653` are near-duplicate blocks. Whichever route is taken, both must change together or they will report different rates for the same class of run.
- **Do not silently drop the excluded count.** A bare `1/1 (100.0%)` is indistinguishable from a run where nothing was gated. Annotating the excluded count preserves the operator's ability to tell those apart, consistent with this repo's no-silent-caps posture.
- **Guard the empty denominator.** The existing `if total_issues > 0 else 0` must survive: a run where every issue was gate-blocked now has a denominator of zero where it previously had a nonzero one.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **`processed_count` and `state.timing` (sequential path) already exclude every non-success outcome — confirms the Open Questions speculation.** `AutoManager.run()` increments `self.processed_count` only `if success:` (`issue_manager.py:1911-1914`), and `state.timing` is populated only from `mark_completed(issue_id, timing)`'s `timing` argument, which only the `elif result.success:` branch supplies (`issue_manager.py:2113`). "Issues processed:" and "Average per issue:" already report success-only figures — no change needed there.
- **The parallel path's timing is NOT success-only, unlike the sequential path.** `self.state.timing[result.issue_id]` is set unconditionally for every `WorkerResult` in `orchestrator.py` (~1243-1246), outside the success/failure branching. No orchestrator "Average per issue:"-style line currently exists, but this is relevant if a fix is extended there.
- **No `_is_pre_phase1_gate_failure`-style predicate, nor any `failure_reason`-string classifier, exists anywhere in the codebase today.** A search for `_is_.*failure`/`_is_.*_reason` under `scripts/little_loops/` returns zero matches. Gate classification today happens exclusively via stdout markers (`CONFIDENCE_GATE_BLOCKED`, `LEARNING_GATE_BLOCKED`, `PHASE1_NOT_STARTED ... <gate>`), never `failure_reason` prefix matching. The standalone route's proposed predicate would be a new pattern, not an extension of an existing family.
- **The zero-denominator guard (`if total > 0 else 0`) is a uniform, codebase-wide convention** — evidence: `issue_manager.py:1974`, `orchestrator.py:1650`, `issue_progress.py:161-162`, `hotspots.py:70,96`, `dependency_mapper/analysis.py:227,317,389`, `verify_triggers.py:365-366`. No divergent example found.
- **`issue_manager.py` and `parallel/orchestrator.py` are maintained as intentionally separate, lockstep-edited duplicate blocks, not a shared module.** No `metrics.py`/`summary.py`-style shared helper exists for this computation; the orchestrator's block is already a superset (it adds `by_category` grouping, `orchestrator.py:1662-1669`) despite sharing the identical core rate computation — the two blocks already drift in scope even under the "edit together" convention.
- **No existing test exercises `_log_timing_summary`'s or the orchestrator's `Auto-corrections:`/correction-rate output.** A grep for `_log_timing_summary`, `Auto-corrections`, and `PROCESSING SUMMARY` across `scripts/tests/` returns no hits — whichever route this issue takes, its test will be new, not an extension.

## Open Questions

- Are the learning-gate and decision-gate `failure_reason` strings as stable as
  `below_readiness_threshold`? If not, the standalone route needs them
  normalized first.
- Should `Issues processed:` (which already correctly reported `1`) and
  `Average per issue:` be audited for the same overload? They read from
  `processed_count` and `state.timing` respectively, both of which appear to
  exclude gate-blocked issues already — worth confirming rather than assuming.

## Related Issues

- BUG-3252 — the confidence gate's failure-vs-skip classification, of which this
  is the downstream metrics consequence.

## Related Key Documentation

- `scripts/little_loops/state.py:32-34` — states that failed issues and
  auto-corrections are tracked for quality purposes.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-18_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 60/100 → LOW

### Concerns
- The Proposed Solution has two unresolved routes (standalone `_is_pre_phase1_gate_failure` predicate vs. consuming BUG-3252 Part 3's skip bucket) — the winning route depends on whether BUG-3252 lands first, which is not yet decided.
- Open Questions ask whether the learning-gate and decision-gate `failure_reason` strings are stable enough to string-match under the standalone route; unconfirmed.

### Gaps to Address
_(none — no format-check, program-design, or dependency gate gaps found)_

### Outcome Risk Factors
- No existing test exercises `_log_timing_summary`'s or the orchestrator's `Auto-corrections:`/correction-rate output (confirmed via grep) — any fix requires new test infrastructure, not an extension of existing coverage.
- Two-route ambiguity (standalone vs. BUG-3252-dependent) means the implementer must make a sequencing/design call mid-implementation rather than following a single specified path.

## Status

**Open** | Created: 2026-08-17 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-08-18T01:57:01 - `22c6cfbd-e81b-49b4-b781-b4588a9711ab.jsonl`
- `/ll:reconcile-issue` - 2026-08-18T01:53:03 - `06441b6f-0a06-4067-9c07-e33e815934ec.jsonl`
- `/ll:refine-issue` - 2026-08-18T01:45:34 - `45517e10-4dcf-4cdb-ac90-c8175e3464a2.jsonl`
- `/ll:format-issue` - 2026-08-18T01:35:12 - `f0f6a7d7-4813-4604-95ee-0469a847224f.jsonl`
- `/analyze_log` - 2026-08-17 - ll-auto run audit (ENH-3237, ENH-3240)
