---
id: ENH-3435
title: Measure and cache an unmutated baseline arm before the first change, and make the cache bidirectional
type: ENH
priority: P2
status: open
discovered_date: '2026-09-10'
labels: []
---

## Summary

An `ll-harness` verdict of the form "this change improved things" is a claim against a before-number, and today that number is remembered rather than measured. The delta must come from an unmutated arm run on the same task, at the same n, under the same conditions as the candidate, or the claimed delta describes two different systems. Make the baseline an explicit phase of the run: before the first proposal, execute n unmutated runs and record the result. That also calibrates magnitude, which is what makes any subsequent proposal meaningful — "make this better" is not actionable when the baseline is already at zero, exactly as "make this harder" is not.

Make the cache bidirectional, which is the part that pays for itself. The loop and any post-hoc analysis write and read the same result shape, so a rollout paid for once is reusable in either direction instead of being re-paid per analysis. In a system where every measurement is an API call, this is a direct cost argument sitting inside a verdict-integrity mechanism.

Cache resilience is part of the contract: a corrupt or partial cache entry must degrade to re-measuring, never to a silently wrong baseline.

## Current Behavior

`ll-harness` comparisons are incumbent-relative: a candidate is graded against whatever the incumbent lineage last produced, and any "before" number cited in a verdict is remembered from an earlier run rather than measured as part of this one. The existing cache is one-directional — a result paid for on one path is not reusable by the other. The two sibling guards are now in place: n-run redundancy (ENH-3415) supplies a sound n, and the frozen external reference (ENH-3421) supplies an external anchor. Both assume a baseline exists; neither makes producing the unmutated incumbent-arm baseline a phase of the run itself. This issue is that remaining piece.

## Design

Mechanics borrowed from evolutionary-search harness design, where the baseline arm is treated as mandatory loop structure rather than optional rigor:

- **Baseline phase before the first proposal.** Per task, before the agent's first proposal or mutation is evaluated, execute n unmutated runs — same task, same effective n as the candidate arm, same conditions (model, host, timeout, criteria) — and record the result. The n is whatever the candidate arm will use, so the two arms are directly comparable; nothing about the sample machinery is redefined here.
- **Disk-cached, bidirectional.** The baseline result persists to a disk cache with a defined result shape. The loop writes it; any post-hoc analysis reads it — and writes the same shape back, so a checkpoint evaluation performed after the fact feeds the next run's baseline lookup. Either direction can consume the other's already-paid rollouts. This is the difference between paying for a baseline once and paying for it per analysis.
- **Degrade, never lie.** A corrupt or partial cache entry is discarded and re-measured. The failure mode being guarded against is a silently wrong baseline — a plausible-looking cached number that no longer describes the system it claims to. Cache resilience is explicitly unit-testable and must be tested.
- **Provenance on the delta.** A verdict that reports a delta names its baseline: task set, n, conditions, and whether the baseline was freshly measured or reused from cache.

On the run model (ENH-3397): baseline runs are ordinary repetitions recorded against their own named cells (`task × repetition × subject`), with the unmutated incumbent as the subject. Nothing about attempt classification changes; the baseline arm simply is another subject the existing machinery scores.

## Scope Boundaries

- **In scope**: the baseline phase in the `ll-harness` run path (execute-before-first-change, at the candidate's effective n), the disk cache and its result shape, the bidirectional read/write contract between loop-time and post-hoc analysis, corrupt/partial-entry degradation, and delta provenance reporting.
- **Out of scope**: n-run redundancy and its `--samples` semantics (ENH-3415, done); the frozen external reference guard (ENH-3421, done); the repetition/infra-retry/continuation attempt model (ENH-3397, done); widening the evidence surface beyond the current channels; scoring runs on an efficiency vector. Those are separate concerns that compose with this one.

## Acceptance Criteria

1. Before the first proposal in a harness run that will report a delta, n unmutated runs execute on the same task set, at the same effective n, under the same conditions as the candidate arm.
2. A run that would report a delta without a measured baseline either refuses or reports an explicit "no measured baseline" state — it never falls back to comparing against a remembered number.
3. Baseline results persist to a disk cache under a defined result shape, keyed so subsequent invocations on the same task and conditions reuse them.
4. The cache is bidirectional: one test shows a loop-produced baseline consumed by post-hoc analysis without re-running the subject, and one shows a post-hoc-produced result consumed as a run's baseline.
5. A corrupt or partial cache entry causes re-measurement and re-write, not use; a test writes a deliberately corrupted entry and asserts the baseline is re-measured.
6. A reported delta names its baseline's provenance: fresh or reused, the n, and the conditions.
7. Existing single-shot and n-sample verdict behavior is unchanged when no baseline is requested; the test suite passes.

## Impact

- **Priority**: P2 — the remaining leg of verdict integrity after ENH-3415 and ENH-3421; without it, "this change helped" remains a claim against a remembered number.
- **Effort**: Medium — a new baseline phase in the harness run path, a disk cache with a defined shape and degradation rule, and tests for both directions of the cache contract.
- **Risk**: Low-medium — additive path; the existing verdict surface is unchanged when no baseline is requested.
- **Breaking Change**: No.
