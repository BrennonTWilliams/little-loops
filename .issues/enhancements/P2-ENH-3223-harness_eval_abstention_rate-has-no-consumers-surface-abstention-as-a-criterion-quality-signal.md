---
id: ENH-3223
type: ENH
title: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality
  signal
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:29:07Z'
parent: EPIC-3217
---

# ENH-3223: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal

## Summary

ENH-3185 shipped `harness_eval_abstention_rate()` in `scripts/little_loops/history_reader.py` (schema v41) so that "a criterion that is abstained on repeatedly becomes visible as a badly written criterion rather than disappearing into a pass/fail number". Nothing reads it. The function has no callers outside its own definition and its tests — no loop, no CLI report, no skill.

The persistence half is done and correct (`semantic_passed = NULL` on abstention, excluded from the pass-rate denominator). The signal is recorded and unqueried.

## Current Behavior

`harness_eval_abstention_rate(target, since, ...)` returns `{scored, abstentions, abstention_rate}` or `None` when there are no scored rows. A user learns their abstention rate only by calling the Python API directly.

Meanwhile the loops that exist to diagnose harness quality — `harness-optimize`, `evaluation-quality`, `rubric-refine` — have no access to it, so a criterion the judge cannot evaluate looks the same to them as a criterion that is merely hard to satisfy.

## Expected Behavior

Abstention rate is available as a first-class signal in the two places it can act:

1. **Reporting.** An `ll-history`/`ll-logs` surface reports abstention rate alongside pass rate for a target, so a high-abstention criterion is visible without writing Python.
2. **Meta-loop diagnosis.** `harness-optimize` (and the other harness-quality loops) can gate on it — a criterion above some abstention threshold is a rewrite candidate, distinct from a criterion that fails.

The meta-loop use fits the project's own loop-authoring rules unusually well: abstention rate is a *non-LLM external evaluator* for an LLM-judged gate, which is exactly what the meta-loop design rules require every `check_semantic`/`llm_structured` state to pair with.

## Motivation

The diagnostic value claimed in ENH-3185's rationale is not yet delivered. Abstention data is accumulating in `.ll/history.db` with no path to a user or an automated consumer, so badly-written criteria stay invisible in practice even though the mechanism to see them exists.

## Proposed Solution

Start with the reporting surface, since it is a thin wrapper over an existing query and validates the data shape before anything automated depends on it. Then wire the meta-loop consumer.

Open questions for the implementer:

- Which CLI does this belong to — `ll-logs telemetry`, an `ll-history` subcommand, or the harness's own reporting? Pick by where pass rate is already reported, so the two appear together.
- What threshold makes a criterion a rewrite candidate? This should be measured against real data rather than guessed; the first version may report without gating.
- `ll-harness` already distinguishes abstention in its summary and exit code (ABSTAIN = 3). Check whether that summary should also report the historical rate for the target, which would put the signal in front of the user at the moment they are looking at the criterion.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

Turns recorded-but-unread abstention data into an actionable signal for criterion quality. Additive; no change to existing pass-rate reporting, whose denominator already excludes abstentions.

## Related Key Documentation

- `docs/ARCHITECTURE.md` `## Directory Structure` history-schema table (v31
  `harness_events`, v33 `verdict_events`) — sibling live-write telemetry tables
  with the same recorded-but-unconsumed shape
- `docs/reference/API.md` `little_loops.fsm.executor` section — where
  `harness_eval_abstention_rate()`'s source data (`semantic_passed = NULL`
  on abstention) is produced

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-16T23:29:37 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`
