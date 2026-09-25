---
id: BUG-3587
type: BUG
title: Invocation consumption is used as context occupancy
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T01:46:08Z'
parent: EPIC-3562
relates_to:
- ENH-3545
- ENH-3538
- ENH-1376
labels:
- observability
- context-monitor
---

# BUG-3587: Invocation consumption is used as context occupancy

## Summary

Invocation token consumption is written to `result_token_count` and treated as current context occupancy by the context monitor and handoff sentinel. Repeated model requests can consume more tokens than remain in the context window, so this can cause premature pressure warnings or handoffs. Correct the metric selection separately from ENH-3545's additive provenance/staleness labels.

## Current Behavior

`scripts/little_loops/issue_manager.py` writes the sum of the legacy usage callback's input and output to the result_token_count state field. `hooks/scripts/context-monitor.sh` prioritizes that value over its transcript baseline and estimator, and `hooks/scripts/context-handoff-sentinel.sh` prioritizes it over `estimated_tokens`. The field has no metric/scope/freshness qualification and can survive context changes and compaction. ENH-3538's known-component lower bounds preserve consumption reporting; they do not establish current occupancy.

## Expected Behavior

Consumption remains available for usage accounting and consumption budgets, but does not replace a current-context occupancy measurement or estimate. Occupancy guards use a valid measurement for the same session/context interval, or the existing occupancy estimator with explicit estimated provenance. Legacy unqualified `result_token_count` must not be treated as measured occupancy. Configured threshold values remain unchanged; corrected inputs may intentionally change when a warning or handoff fires.

## Motivation

Premature context-pressure handoffs interrupt useful work even when the active context fits. Correcting the metric lets occupancy protection remain useful without discarding valid consumption accounting.

## Proposed Solution

Separate consumption and occupancy at the producer/consumer boundary. Audit the context-limit guards in `issue_manager.py` and `parallel/worker_pool.py` as well as both shell consumers; preserve consumption-budget behavior, but remove invocation totals from occupancy-only decisions. Reuse ENH-3545's additive state metadata when present and remain compatible with older state files. Define invalidation on compaction and session changes so an old consumption value cannot regain priority. Do not replace the existing estimator with a new accuracy project.

## Integration Map

- Files: `scripts/little_loops/issue_manager.py`, `scripts/little_loops/parallel/worker_pool.py`, `hooks/scripts/context-monitor.sh`, `hooks/scripts/context-handoff-sentinel.sh`; context state readers as needed.
- Tests: `scripts/tests/test_hooks_integration.py`, issue-manager and worker-pool usage/guard tests, `scripts/tests/test_enh3538_token_observations.py` where prior lower-bound expectations encode occupancy behavior.
- Docs: `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/guides/SESSION_HANDOFF.md`, `docs/development/TROUBLESHOOTING.md`.

## Program Design

### Types

Reuse the existing context-state mapping and additive metric/scope/freshness metadata from ENH-3545. Keep consumption values separate from occupancy measurement/estimate values; exact additive key names and compatibility rules must be recorded before implementation. No replacement estimator is required.

### Signatures

- `_on_usage_writer(input_tokens: int, output_tokens: int) -> None` — existing nested callback in the issue manager; retain consumption reporting while removing any implicit occupancy certification.
- Shell monitor/sentinel entry points remain unchanged; their metric selection changes, not their configured thresholds.

### Call Path

- Usage callback → consumption accounting/state → consumption-budget consumers.
- Qualified occupancy measurement or existing estimator → context state → monitor/sentinel/Python occupancy guards.
- Session change or compaction → invalidate occupancy baseline evidence; an old invocation total never becomes the fallback measurement.

## Implementation Steps

1. Classify every result-count/usage-callback consumer as consumption accounting, consumption budget, or context occupancy; record the chosen occupancy source and fallback contract.
2. Separate the metrics and update occupancy consumers, preserving consumption reporting and configured threshold values.
3. Test repeated requests, absent/partial usage, old state files, compaction, and session changes, including monitor/sentinel agreement; update docs and run project checks.

## Impact

- Priority: P2 — incorrect metric selection can prematurely interrupt automated work.
- Risk: Medium — guard behavior intentionally changes, while accounting and threshold configuration must remain stable.

## Steps to Reproduce

1. Supply a completed invocation with multiple model requests whose total consumption exceeds the configured context threshold while its current context occupancy remains below it.
2. Observe the usage callback writing that consumption into the context state.
3. Run the monitor and Stop sentinel against that state and observe that the consumption total takes priority over the lower occupancy estimate.

## Root Cause

- `scripts/little_loops/issue_manager.py` — `_on_usage_writer`: invocation consumption is stored in the context-state file without metric/scope qualification.
- `hooks/scripts/context-monitor.sh` — `main`: the result-count branch assumes that consumption is an occupancy baseline.
- `hooks/scripts/context-handoff-sentinel.sh` — result-count preference repeats that assumption.

## Acceptance Criteria

- [ ] A multi-request invocation with high total consumption and low current occupancy does not trigger an occupancy handoff from consumption alone.
- [ ] Genuine high occupancy still triggers the configured guard using a valid occupancy measurement or the existing estimator.
- [ ] Invocation consumption and known-component lower bounds remain available to their accounting/budget consumers.
- [ ] Legacy `result_token_count` is never implicitly promoted to measured occupancy; session changes and compaction cannot reuse a stale value as an authoritative baseline.
- [ ] Monitor, sentinel, and Python occupancy guards agree on metric selection; threshold configuration is unchanged, with intentional trigger changes documented.
- [ ] ENH-3545 labels/staleness behavior remains additive and compatible; no dependency cycle is introduced between the two issues.

## Scope Boundaries

- In scope: correcting consumption-as-occupancy decisions and their producers, compatibility, and regression coverage.
- Out of scope: estimator accuracy improvements, threshold tuning, usage ingestion/coverage reconciliation, and ENH-3545's UI metadata implementation.
- ENH-3545 can land independently; this issue owns behavior changes to occupancy decisions.

## Related Key Documentation

- `docs/guides/SESSION_HANDOFF.md` — context state and handoff behavior.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — monitor and sentinel behavior.

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-25T01:52:41 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`
