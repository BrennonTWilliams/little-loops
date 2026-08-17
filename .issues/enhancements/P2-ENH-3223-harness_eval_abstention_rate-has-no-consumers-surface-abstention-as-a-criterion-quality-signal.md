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
decision_needed: true
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Wire the new report into `ll-harness`'s own per-run summary/exit-code output (`cli/harness.py`). This is exactly what the issue's own text names as the strongest placement ("put the signal in front of the user at the moment they are looking at the criterion") — `_evaluate_and_report()` (`cli/harness.py:580`) already distinguishes abstention via `is_abstention_verdict()` and sets `overall = "ABSTAIN"`/exit code 3; it would gain one additional call to `harness_eval_abstention_rate(target, ...)` and print/attach the historical rate alongside the current run's verdict.

**Option B**: Add a new `ll-session` subcommand mirroring the wiring pattern ENH-3211 established for a structurally similar "reader has no consumers" case (`subagent_tree`/`subagent_retries`/`subagent_budget`). Weaker analogy here: ENH-3211's functions are per-session lookups, while `harness_eval_abstention_rate`/`harness_eval_pass_rate` are per-`target` rollups — `ll-session`'s existing subcommands (`path`, `related`, `recent`) are all session-scoped, not target-scoped, so this would be a new argument shape for that CLI, not a drop-in fit.

**Option C**: Add a new subcommand under `ll-logs` telemetry or `ll-history`. No precedent exists for either module: neither currently imports `history_reader.py`'s `harness_eval_pass_rate`/`harness_eval_abstention_rate` at all, and `harness_eval_pass_rate` (the older, ENH-2741 sibling) is itself unwired into any CLI today despite being documented in `docs/reference/API.md` — so there is no existing "pass rate is already reported here" location to co-locate with, contrary to the Proposed Solution's original assumption that such a location exists.

**Recommended**: Option A for v1 — it is the smallest surface, matches the issue's own stated preference for where the signal is most actionable, and requires no new CLI-location decision. The meta-loop gating consumer (`harness-optimize` and friends) is a separate, later wiring step regardless of which reporting surface ships first, since none of those loops currently reference `harness_events`/`harness_eval_abstention_rate` at all.

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
