---
id: BUG-3724
type: BUG
title: Mixed-model action usage is priced at the last model
priority: P2
status: open
discovered_by: capture-issue
discovered_date: '2026-10-03'
captured_at: '2026-10-04T01:44:03Z'
parent: EPIC-3562
testable: true
relates_to:
- ENH-3719
- BUG-3696
- ENH-3538
---

# BUG-3724: Mixed-model action usage is priced at the last model

## Summary

An FSM action can report usage from several models or batch modes, but its persisted aggregate is priced at the last usage event's model and batch flag. Preserve the attribution needed to price each contribution. A staged mitigation may first make heterogeneous costs unavailable, but this issue remains `in_progress` until per-contribution accounting is delivered. Keep ENH-3719's footer work separate.

## Current Behavior

`FSMExecutor._run_action` sums all token components in `result.usage_events`, then copies the last event's model and `is_batch` onto one `action_complete` payload. `PersistentExecutor._handle_event` writes that aggregate to `usage.jsonl`. `CostReport.from_usage_jsonl` prices the aggregate at the one model/flag, and `_check_cost_ceiling` relies on that report.

An actual executor-path test with synthetic complete events — 1,000,000 input tokens from `claude-haiku-4-5`, followed by 1,000,000 from `claude-sonnet-5`, with output/cache components zero — produces a Sonnet action row with 2,000,000 input tokens. With the current rates, the report is $4 while the sum of separately priced events is $3. Reversing event order changes the wrong answer. This is a reproduced code-path defect, not evidence that this exact mixture occurred in a native session.

## Expected Behavior

State/run cost is the sum of individually qualified model/batch contributions. Model switches and batch/live mixtures cannot silently price earlier usage at the last model's rate. Missing components or unpriced contributions keep affected costs unavailable and preserve known token audit subtotals. Cost ceilings never enforce an invented aggregate cost.

If preserving exact attribution requires a separate compatibility step, first mark heterogeneous action cost unavailable with a specific reason. Do not synthesize a concrete model ID such as a mixed-model sentinel for ENH-3719's missing-price footer.

## Motivation

Silent model/batch misattribution distorts state/run estimates and can incorrectly permit or abort work under a cost ceiling. The producer already has each event's attribution; preserve it through the durable report boundary.

## Proposed Solution

Retain per-event contributions or aggregate buckets keyed by concrete model and batch mode in the action payload and durable usage artifact. Choose and document the artifact compatibility strategy before adding keys; `CostReport`'s existing stable JSON contract must be respected. One action remains one iteration even if it contains several pricing contributions. New-format contributions are the pricing source; the parent aggregate is an audit/compatibility summary and is never added a second time. Preserve nullable components and missing counts at the bucket boundary, including NULL when every contribution lacks a component. Reuse the collected live events rather than changing their observation grain. Legacy rows with only one aggregate identity retain their documented historical interpretation; do not reconstruct missing earlier identities. Distinguish legacy rows without an attribution field from new rows with empty/invalid attribution; the latter remain unavailable with a diagnostic instead of silently using the last-model aggregate. Preserve the existing timestamp/`as_of` pricing behavior for historical and homogeneous rows.

**ENH-3719 handoff:** once contributions exist, its footer inspects every contribution's concrete pricing ID and missing-ID sentinel. Whichever issue lands second owns adapting the shared reader and a regression with an earlier unpriced contribution followed by a known last model. Keep the `relates_to` coordination link; add no mutual blocking edge.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — aggregation and ceiling diagnostics.
- `scripts/little_loops/fsm/persistence.py` — durable contribution attribution.
- `scripts/little_loops/fsm/cost_graph.py` — per-contribution pricing and compatibility.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/summary.py` reporter, history consumers of usage artifacts, and the live usage writer at executor finish.

### Similar Patterns

- `TokenUsage` completeness/provenance fields and ENH-3538's NULL propagation; existing live per-event storage.

### Tests

- `scripts/tests/test_fsm_executor.py`, `test_fsm_cost_graph.py`, `test_cost_ceiling_enforcement.py`, `test_usage_reporter.py`, and persistence usage-artifact tests.

### Documentation

- `docs/reference/CLI.md` and `docs/reference/API.md` — durable artifact contract, model attribution, historical limitations.

### Configuration

- No new pricing option or vendor dependency.

## Program Design

### Types

- Existing `TokenUsage` preserves concrete model, `is_batch`, and nullable components.
- Proposed `UsageCostContribution` or equivalent durable bucket: model, batch flag, four nullable token components and completeness counts; use original event identities where needed, without inventing request identities.

### Signatures

- Existing `FSMExecutor._run_action` → `PersistentExecutor._handle_event` retains contributions.
- `CostReport.from_usage_jsonl(path: Path) -> CostReport` — existing prices contributions without counting one action as multiple iterations.
- `FSMExecutor._check_cost_ceiling(state: StateConfig) -> bool` — existing uses the corrected report or explicit unavailable reason.

### Call Path

Runner `TokenUsage` events → action payload → durable `usage.jsonl` contributions → `CostReport` → table/JSON/reporter and cost ceiling. Preserve the separate `_finish` live `usage_events` writer.

## Implementation Steps

1. Add an executor → persistence → report regression for mixed models, reversed order, and mixed batch flags.
2. Choose the durable compatibility strategy; preserve attributed contributions or land an explicit fail-closed mitigation first.
3. Update report pricing, reporter/JSON behavior, and cost-ceiling diagnostics without changing iteration counts or the live observation grain.
4. Test homogeneous/legacy parity (including timestamp-based pricing), nullable/missing contributions, single counting, malformed new attribution, and footer handoff; document historical limitations. A fail-closed mitigation alone does not satisfy this issue's closeout contract.

## Impact

- **Priority:** P2 — silently wrong run costs can influence enforced ceilings.
- **Effort:** Medium — crosses producer, durable artifact, and report contracts.
- **Risk:** Medium — preserve action counts, legacy artifacts and stable report JSON.
- **Breaking Change:** Any artifact extension must be additive or explicitly versioned; no CLI option change intended.

## Steps to Reproduce

1. Drive `FSMExecutor._run_action` with an `ActionResult` containing the two complete `TokenUsage` events above through a mocked runner, retaining the normal executor event emission.
2. Persist its `action_complete` event through `PersistentExecutor._handle_event` into a temporary run's `usage.jsonl`.
3. Read it with `CostReport.from_usage_jsonl` and compare with `estimate_cost_usd` summed per original event. Assert the current $4 versus $3 mismatch and repeat with reversed event order and a same-model mixed-batch case.

## Actual Behavior

The action's aggregate tokens carry the last event's model/batch identity; cost and cost-ceiling decisions can be wrong even when every underlying event is complete and individually priced.

## Root Cause

- **File:** `scripts/little_loops/fsm/executor.py`.
- **Anchor:** `FSMExecutor._run_action`, the `result.usage_events` payload aggregation.
- **Cause:** token totals aggregate a heterogeneous set while the pricing identity comes from only its last member; persistence discards the earlier model/batch identities.

## Acceptance Criteria

- [ ] At closeout, the reproduced mixed-model action is correctly $3 at current fixture rates, independent of event order, using durable per-contribution attribution. An earlier fail-closed mitigation may land but leaves this issue `in_progress`; it is never priced at the last model alone.
- [ ] Same-model batch/live mixtures retain each contribution's rate; mixed known/unknown models and incomplete components make affected costs unavailable with a specific reason.
- [ ] Executor, persistence, report, reporter, and ceiling tests cover the real call path. Known token subtotals survive. Unavailable cost emits `cost_ceiling_unknown` once per state and skips numeric ceiling comparison under the existing continue-with-diagnostic policy; it is never classified as zero or under budget. No automatic abort-on-unknown policy is introduced.
- [ ] Contributions and the parent aggregate are never both summed: one action retains one iteration and one wallclock contribution. A component missing from all events/buckets stays NULL with missing counts; partially known bucket sums retain positive missing counts and cannot be priced. Empty/invalid new-format attribution cannot silently fall back to a legacy last-model price.
- [ ] Homogeneous complete actions and historical timestamp/`as_of` pricing retain numeric parity, iteration/event counts remain correct, and the separate live `usage_events` writer retains per-event attribution.
- [ ] Stable report JSON and legacy artifact compatibility are explicitly tested; no historical identity is fabricated and no stored history costs are backfilled by this change.
- [ ] ENH-3719's missing-price footer remains scoped to concrete missing pricing IDs; this issue owns heterogeneous attribution and its diagnostic. Once both land, an earlier unpriced contribution followed by a known last model appears in the footer, including incomplete-token contributors. Whichever lands second adapts the shared reader/tests; coordinate docs for the landed behavior without a mutual dependency.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope:** FSM action model/batch attribution, durable pricing, ceilings, compatibility, diagnostics and regression tests.
- **Out of scope:** unpriced-model footer implementation, family pricing fallback, host-native evidence, historical backfill, and unrelated estimator accuracy.

## Related Key Documentation

- `docs/reference/CLI.md` — usage reports and cost ceilings.
- `docs/reference/API.md` — FSM event and cost-report contracts.

## Status

**Open** | Created: 2026-10-03 | Priority: P2


## Session Log

- Pre-implementation epic review - 2026-10-04 - Opus critique supported explicit final-attribution closeout, NULL/missing-count preservation, no double counting and contribution-aware footer coordination. Verified the existing ceiling policy continues with a once-per-state unknown-cost diagnostic; retained it explicitly. Added a new-format-versus-legacy discriminator so invalid attribution cannot restore the last-model bug. Fail-closed mitigation is a stage, not a done verdict.

- `/ll:capture-issue` - 2026-10-04T01:51:01 - `7ac1ad38-c74f-402b-a14d-5845cde7ff55.jsonl`
