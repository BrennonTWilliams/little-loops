---
id: 3415
title: Require n-run redundancy before an ll-harness verdict on a stochastic subject counts
type: ENH
priority: P2
status: open
discovered_date: '2026-09-08'
labels:
- harness
- evaluation
- statistics
---

## Summary

`ll-harness` evaluates a runner one-shot: a single pass against exit-code and semantic criteria produces a pass/fail verdict. But the subject under test is an LLM-driven runner whose behavior varies run to run, so a one-shot verdict certifies only "this runner passed once" — a lucky sample is indistinguishable from a real capability, and any promotion decision resting on it is unsound.

Require redundancy as structure, not as optional rigor: a verdict on a stochastic subject does not count until the criterion has been evaluated over n samples, and the harness reports pass-rate-over-n rather than a bare pass/fail. The threshold and the reporting change travel together — reporting a rate without requiring a minimum n just relabels the same weak evidence, and requiring n without surfacing the rate throws away the variance information the extra runs bought.

Scope: identify which runner types have stochastic subjects (a deterministic `cmd` runner should not pay for n samples it does not need), define the default n and how it is overridden per criterion, and decide what the verdict surface looks like when the rate lands between clear pass and clear fail.

## Why redundancy has to be structural

The argument comes from evolutionary-search harnesses that select a candidate on a measured fitness signal. Two guards recur in those systems, and both are treated as *mandatory structure of the loop* rather than as extra rigor a careful operator adds:

- **N-sample redundancy.** High-variance evaluation environments produce flukes. Mandating multiple evaluations per unique match-up is what stops a single lucky win from promoting a candidate — the thing that separates principled selection from prompt-and-hope.
- **A frozen external reference.** A candidate is tested against both the incumbent and an unchanged baseline, so a lineage cannot drift into a self-referential local optimum where every generation only beats its immediate parent.

Neither is novel as statistics. What is worth copying is the posture: the loop is not considered runnable without them. The second guard is out of scope here and belongs in its own issue; this issue supplies the first.

## Dependencies and tensions to resolve explicitly

This sits directly on top of the harness run model that defines how an attempt is recorded against a named cell — as a repetition, an infrastructure retry, or a continuation, with only repetitions incrementing n. That model deliberately leaves the threshold open. This issue supplies the missing half: how large n must be before the harness will certify anything.

It also resolves a standing tension with the capability-preflight work, whose stop-on-first-confirmation is a budget policy pulling in the opposite direction. The two need an explicit boundary — **preflight capability probes may stop early; verdicts that gate promotion may not** — because leaving it implicit means whichever code path runs last silently wins.

The existing score-reproducible-not-byte-reproducible stance on judging stochastic agent runs is the auditing posture this makes mechanical: that stance says what a verdict on a stochastic subject may claim, and this issue supplies the mechanism that makes the claim true.

## Acceptance Criteria

- Runner types are classified as stochastic or deterministic, and only stochastic subjects incur n samples; a deterministic `cmd` runner's cost is unchanged.
- A default n is defined, and a per-criterion override mechanism exists.
- The harness verdict surface reports pass-rate-over-n. A bare pass/fail is no longer emitted for a stochastic subject.
- The behavior for a rate landing between clear pass and clear fail is specified rather than left to the caller.
- The preflight-vs-promotion boundary is stated in code and enforced: early stop on first confirmation is permitted for capability probes and refused for verdicts that gate promotion.
