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
testable: true
---

# ENH-3223: harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal

## Summary

> **Not implementation-ready.** This issue still carries `decision_needed: true`, has no `confidence_score`, no Program Design section, and an entirely `TBD` Integration Map — a different maturity tier from its EPIC siblings ENH-3224 (decided, wired, scored 95/79) and ENH-3222. Route it through `/ll:refine-issue` and `/ll:wire-issue` before implementation. The findings below narrow the decision but do not close it.

ENH-3185 shipped `harness_eval_abstention_rate()` in `scripts/little_loops/history_reader.py` (schema v41) so that "a criterion that is abstained on repeatedly becomes visible as a badly written criterion rather than disappearing into a pass/fail number". Nothing reads it. The function has no callers outside its own definition and its tests — no loop, no CLI report, no skill.

**The same is true of its older sibling.** `harness_eval_pass_rate()` (ENH-2741) is *also* unwired into any CLI, despite being documented in `docs/reference/API.md`. This reframes the issue: the Proposed Solution below assumes a place where "pass rate is already reported" that this surface can join, and **no such place exists**. Whatever surface ships here has to introduce both rates, not append abstention to an existing report. That materially enlarges the smallest viable v1.

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

- ~~Which CLI does this belong to — pick by where pass rate is already reported, so the two appear together.~~ **This question rests on a false premise**: `harness_eval_pass_rate()` is not reported anywhere either (see Summary). There is no existing co-location to pick. Choose the surface on its own merits and expect to introduce both rates there.
- What threshold makes a criterion a rewrite candidate? This should be measured against real data rather than guessed; the first version may report without gating.
- `ll-harness` already distinguishes abstention in its summary and exit code (ABSTAIN = 3). Check whether that summary should also report the historical rate for the target, which would put the signal in front of the user at the moment they are looking at the criterion.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Wire the new report into `ll-harness`'s own per-run summary/exit-code output (`cli/harness.py`). This is exactly what the issue's own text names as the strongest placement ("put the signal in front of the user at the moment they are looking at the criterion") — `_evaluate_and_report()` (`cli/harness.py:580`) already distinguishes abstention via `is_abstention_verdict()` and sets `overall = "ABSTAIN"`/exit code 3; it would gain one additional call to `harness_eval_abstention_rate(target, ...)` and print/attach the historical rate alongside the current run's verdict.

**Option B**: Add a new `ll-session` subcommand mirroring the wiring pattern ENH-3211 established for a structurally similar "reader has no consumers" case (`subagent_tree`/`subagent_retries`/`subagent_budget`). Weaker analogy here: ENH-3211's functions are per-session lookups, while `harness_eval_abstention_rate`/`harness_eval_pass_rate` are per-`target` rollups — `ll-session`'s existing subcommands (`path`, `related`, `recent`) are all session-scoped, not target-scoped, so this would be a new argument shape for that CLI, not a drop-in fit.

**Option C**: Add a new subcommand under `ll-logs` telemetry or `ll-history`. No precedent exists for either module: neither currently imports `history_reader.py`'s `harness_eval_pass_rate`/`harness_eval_abstention_rate` at all, and `harness_eval_pass_rate` (the older, ENH-2741 sibling) is itself unwired into any CLI today despite being documented in `docs/reference/API.md` — so there is no existing "pass rate is already reported here" location to co-locate with, contrary to the Proposed Solution's original assumption that such a location exists.

**Recommended**: Option A for v1 — it is the smallest surface, matches the issue's own stated preference for where the signal is most actionable, and requires no new CLI-location decision. The meta-loop gating consumer (`harness-optimize` and friends) is a separate, later wiring step regardless of which reporting surface ships first, since none of those loops currently reference `harness_events`/`harness_eval_abstention_rate` at all.

#### Two blockers on Option A, found 2026-08-17

Both must be resolved during refinement; neither is fatal to Option A but both change its acceptance criteria.

**1. `target` is not written consistently, so a lookup keyed on `args.target` under-reports.** `harness_eval_abstention_rate(target, ...)` filters `harness_events WHERE target = ?` (`history_reader.py:3092-3096`), but the CLI writes three different things into that column:

- single-task paths: `target=args.target` (`cli/harness.py:738, 753, 783, 826, 867`)
- multi-task DSL paths: `target=str(path)` (`cli/harness.py:917`) and `target=task_file.name` (`cli/harness.py:940`)

So a rate computed from `args.target` inside `_evaluate_and_report()` silently excludes every DSL-path row for the same logical target. Decide during refinement whether to (a) normalize `target` at write time, (b) accept the single-task-only scope and say so in the output, or (c) key the lookup on something stabler such as `target_content_hash`/`target_path` (the ENH-141 content-pin columns, already populated).

**2. Read-before-write ordering must be pinned as an AC, not left incidental.** `_evaluate_and_report()` (`cli/harness.py:580`) runs *before* `_record_harness_event()` (`cli/harness.py:751`), so a rate read inside it naturally excludes the current run. That is the desired behavior — "abstention rate before this run" is the meaningful number — but it is currently an accident of call ordering that a future refactor could invert silently, flipping the reported figure with no test catching it. Add an explicit acceptance criterion and a regression test asserting the current run is excluded.

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

_Placeholder — this issue has not been through `/ll:refine-issue` or `/ll:wire-issue`. Do not implement from this section. Prerequisites before it can be filled in:_

1. Close the `decision_needed` flag on the reporting surface (Option A/B/C), factoring in that both rates are unwired, not just abstention.
2. Resolve blocker 1 (`target` write inconsistency across single-task vs DSL paths).
3. Pin blocker 2 (read-before-write ordering) as an explicit AC with a regression test.
4. Run `/ll:refine-issue` then `/ll:wire-issue` to produce a real Program Design, Integration Map, and Implementation Steps, then `/ll:confidence-check`.

## Scope Boundaries

**In scope**
- One reporting surface that exposes abstention rate (and, per the Summary finding, pass rate — since it has no existing home either)
- Resolving the `target` write inconsistency enough that the reported figure is correct or its limits are stated

**Out of scope**
- **Meta-loop gating.** Wiring `harness-optimize` / `evaluation-quality` / `rubric-refine` to consume the signal is a separate, later step — none of those loops reference `harness_events` at all today, and the threshold that makes a criterion a rewrite candidate should be measured against real data rather than guessed. v1 reports; it does not gate.
- Choosing that threshold
- Any change to the persistence half (`semantic_passed = NULL` on abstention, the pass-rate denominator) — it is already correct
- Backfilling or migrating existing `harness_events` rows

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
