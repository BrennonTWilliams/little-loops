---
id: ENH-3465
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

## Current Behavior

Every improvement claim the self-improvement tooling can currently make is incumbent-relative. Successive wrapper drafts are judged against the previous draft; plan-scoring rubrics score against their own dimensions. Neither holds a fixed reference the whole lineage could fail against, so a lineage where each generation genuinely beats its immediate parent can drift away from any absolute standard while every local comparison still passes.

## Expected Behavior

A candidate is measured against two opponents: the incumbent (proving the lineage is still improving) and a frozen external baseline that never changes (proving "better" is still anchored outside the lineage). Beating one but not the other is a distinct, reportable outcome — not a pass — and a candidate that beats the incumbent while losing to the baseline is the signal that the lineage has entered a self-referential local optimum.

## Scope Boundaries

- Decide what the frozen baseline is per improvement loop: a pinned wrapper version, a shipped default, or a recorded run.
- Decide how and when the baseline is allowed to be re-pinned, without re-pinning becoming a backdoor for drift.
- Decide what the loop does when the two comparisons disagree.

## Design

This is a different axis from the evaluator-hardening work (epoch-bounded objective versioning, versioned evaluator prompts over golden sets): those keep the *measuring instrument* honest; this keeps the *subject* honest by pinning a permanent second opponent. Golden sets test the evaluator; a frozen baseline tests the lineage.

Complements the unmutated baseline arm shipped as ENH-3435, and is a different thing: that baseline is a control arm measured inside a single harness run (it answers "did this change help relative to no change"); this issue's baseline is a standing external opponent for the lineage (it answers "is the lineage still ahead of a fixed reference"). A loop that has both can distinguish a change that helps from a lineage that is drifting. Also pairs naturally with two-number reporting of structure-vs-tuning decomposition, which needs exactly this kind of dual result as input.

## Program Design

### Types

- `BaselineKey`: `runner, target, input_hash, target_content_hash` (frozen) (`scripts/little_loops/history_reader/harness.py:239`)
- `BaselineConditions`: `n, conditions_fp, semantic_prompt, semantic_model, subject_model, timeout_s, host_cli` (`scripts/little_loops/history_reader/harness.py:~250`)
- `BaselineResult`: `key, conditions, tally, attempt_ids, head_sha, measured_at, subject_model, dirty_rows, source` (`scripts/little_loops/history_reader/harness.py:~260`)
- `BaselineDelta`: `candidate, baseline, delta, source, head_sha_differs` (`scripts/little_loops/cli/harness.py:1525`)
- New: a frozen-external-baseline record, distinct from `BaselineResult` — `BaselineResult` is an unmutated in-run control arm (ENH-3435), not a standing lineage opponent, per this issue's own Design distinction.

### Signatures

- `_compare_baseline_refusal(key: BaselineKey, conditions: BaselineConditions) -> str | None` — existing pre-run compare gate in `scripts/little_loops/cli/harness.py:1802`; the new frozen-baseline comparison needs an analogous refusal check against the external baseline record.
- `baseline_for(db_path: Path | str, *, runner: str, ...) -> BaselineResult | None` — existing unmutated-arm reader in `scripts/little_loops/history_reader/harness.py:315`; the new frozen-external-baseline lookup is a distinct function, not a reuse of this one.
- `_run_baseline_phase(runner_label: str, args: argparse.Namespace, n: int, ...)` (`cli/harness.py:1729`), `_run_compare_arm(runner_label: str, args: argparse.Namespace, n: int, ...)` (`cli/harness.py:1820`) — existing single-run control-arm comparison logic; the new incumbent-vs-frozen-baseline comparison is additive to this call path, not a replacement.

### Call Path

Candidate result -> existing `_run_compare_arm()` (incumbent comparison, `cli/harness.py:1820`) run alongside a new frozen-baseline comparison against a record outside `baseline_for()`'s unmutated-arm store -> combined into a `BaselineDelta`-shaped pair (beats-incumbent, beats-baseline) reported as the four-way outcome this issue's Summary specifies.

## Impact

- **Priority**: P4 — the guard is cheap and structural but addresses a slow-drift failure mode rather than an active incident; the Scope Boundaries section leaves baseline-pinning mechanics as open decisions still to be made.
- **Effort**: Medium — depends on the outstanding Scope Boundaries decisions (what the frozen baseline is per loop, how/when it's re-pinned, what happens when the two comparisons disagree) before implementation can start.
- **Risk**: Low-Medium — a poorly chosen re-pinning policy could itself become the drift backdoor this issue is designed to prevent.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-13 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
