---
id: 3465
title: Benchmark every self-improvement candidate against a frozen external baseline, not only the incumbent
type: ENH
priority: P4
status: open
discovered_date: '2026-09-13'
labels:
- evaluation
- apo
- regression
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

Every improvement claim the self-improvement tooling can currently make is incumbent-relative. Successive wrapper drafts are judged against the previous draft; plan-scoring rubrics score against their own dimensions. Neither holds a fixed reference the whole lineage could fail against. That admits a specific failure mode: a lineage where each generation genuinely beats its immediate parent while the lineage as a whole drifts away from any absolute standard — every local comparison passes and the global regression is invisible.

The guard is cheap and structural: a candidate must be measured against two opponents — the incumbent (proving the lineage is still improving) and a frozen external baseline that never changes (proving "better" is still anchored outside the lineage). Beating one but not the other is a distinct, reportable outcome — not a pass — and a candidate that beats the incumbent while losing to the baseline is the signal that the lineage has entered a self-referential local optimum.

## Scope

- Decide what the frozen baseline is per improvement loop: a pinned wrapper version, a shipped default, or a recorded run.
- Decide how and when the baseline is allowed to be re-pinned, without re-pinning becoming a backdoor for drift.
- Decide what the loop does when the two comparisons disagree.

## Design

This is a different axis from the evaluator-hardening work (epoch-bounded objective versioning, versioned evaluator prompts over golden sets): those keep the *measuring instrument* honest; this keeps the *subject* honest by pinning a permanent second opponent. Golden sets test the evaluator; a frozen baseline tests the lineage.

Complements the unmutated baseline arm shipped as ENH-3435, and is a different thing: that baseline is a control arm measured inside a single harness run (it answers "did this change help relative to no change"); this issue's baseline is a standing external opponent for the lineage (it answers "is the lineage still ahead of a fixed reference"). A loop that has both can distinguish a change that helps from a lineage that is drifting. Also pairs naturally with two-number reporting of structure-vs-tuning decomposition, which needs exactly this kind of dual result as input.
