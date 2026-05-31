---
id: ENH-1792
title: Detect Non-Discriminating Evaluators from Run History
type: ENH
priority: P3
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: open
parent: EPIC-1663
labels: [enhancement, loops, evaluator, meta-loop, validation, analytics]
---

# ENH-1792: Detect Non-Discriminating Evaluators from Run History

## Summary

Add a "non-discriminating evaluator" diagnostic that scans `.loops/runs/*/` history and surfaces evaluator states whose verdict has near-zero variance — i.e., always `yes` or always `no` — across many runs. A state that never distinguishes good from bad isn't a quality gate; it's noise (or self-bias). Surfaces via `ll-loop analyze <loop>` (or new `ll-loop diagnose-evaluators`) and integrates with `loop-specialist`'s self-evaluation-bias diagnosis.

## Current Behavior

MR-1 validation in `ll-loop validate` detects evaluator states that are missing non-LLM evidence — but there is no mechanism to detect evaluator states that are present yet non-discriminating. An evaluator that always returns the same verdict (100% pass or 100% fail) across many runs produces no signal. These toothless evaluators survive validation because the gate only checks for their existence, not their effectiveness. Common causes:

- `check_semantic` states with overly vague judge prompts where the LLM returns `yes` almost universally
- `output_numeric` states with targets far from actual run values (e.g., `target: 50` on a skill that produces diffs of 12 lines)
- `exit_code` states gating on commands that never fail (e.g., `echo done`)

## Expected Behavior

`ll-loop diagnose-evaluators <loop>` surfaces evaluators with near-zero verdict variance from run history, with per-state pass rate, Bernoulli variance `p*(1-p)`, and pattern-matched recommendations for improving discriminating power. The `loop-specialist` agent automatically includes variance findings in diagnosis artifacts when run history meets the minimum-run threshold.

## Motivation

`revfactory/harness`'s testing methodology (`references/skill-testing-guide.md` §4-3) explicitly identifies "non-discriminating assertions" — checks that pass for *both* with-skill and without-skill runs — as having no signal value. The reframing: an evaluator whose verdict has near-zero variance across runs isn't measuring anything useful.

In our codebase this manifests as:
- `check_semantic` states whose `llm_structured` prompt is so vague the judge returns `yes` almost universally (`feedback_eval_harness_purpose.md` captures a related case — `execute` running `/ll:manage-issue` instead of exercising the feature created phantom passes the judge couldn't see through)
- `check_concrete` states gating on commands that exit 0 regardless of intent (e.g. `echo done`)
- `check_invariants` with `target: 50` on a skill that never produces large diffs anyway

EPIC-1663's MR-1 rule catches *missing* non-LLM evidence; this issue catches *present-but-toothless* evidence. The two together harden the evaluator chain from both directions.

This depends on having paired with/without data ideally (best signal from FEAT-1790's A/B mode), but also works on plain run history (variance across natural-cause runs is informative even without explicit baselines).

## Use Case

A user has been running `harness-refine-issue` for weeks. They notice it always passes `check_semantic` and wonder if the gate is actually doing anything. They run:

```bash
ll-loop diagnose-evaluators harness-refine-issue
```

Output:

```
Evaluator Variance Report (n=47 runs)
  check_concrete   pass_rate=0.89   variance=0.10   ✓ discriminating
  check_semantic   pass_rate=0.98   variance=0.02   ⚠ low variance
                   ↳ 46/47 runs returned YES on first attempt
                   ↳ judge prompt: "Did the issue file get updated...?"
                   ↳ Likely too broad — most updates pass trivially.
                     Recommendation: tighten to require specific
                     evidence (e.g. confidence_score increase, new
                     codebase references added).
  check_invariants pass_rate=1.00   variance=0.00   ⚠ never fails
                   ↳ target=50 but median diff size=12 — gate is loose
```

## API/Interface

Two surfaces:

1. **New subcommand**: `ll-loop diagnose-evaluators <loop> [--threshold 0.05] [--min-runs 10]`
   - `--threshold`: variance floor below which a state is flagged (default 0.05)
   - `--min-runs`: minimum runs required to compute meaningful variance (default 10)
   - Output: per-state pass rate, variance, recommendation. JSON via `--json`.

2. **`ll-loop analyze` extension**: add a "Non-discriminating evaluators" section to the existing analysis output when run history meets `--min-runs`.

3. **`loop-specialist` integration**: when diagnosing a meta-loop, automatically call this analysis and include findings in the diagnosis artifact under `.loops/diagnostics/<loop>-<ts>.md`.

## Implementation Steps

1. **Run-history reader** — module in `scripts/little_loops/analytics/` that walks `.loops/runs/<loop>/*.jsonl`, extracts per-state verdict tuples (`state`, `verdict`, `iteration`, `run_id`).
2. **Variance calculator** — Bernoulli variance `p*(1-p)` over verdict series, grouped by state name. Filter to states with `evaluate:` blocks (skip pure shell actions).
3. **Recommendation generator** — pattern-match common failure modes:
   - High pass-rate + `llm_structured` → "broaden judge criteria"
   - 100% pass + `output_numeric` → "target may be too loose for actual diff sizes"
   - 100% pass + `exit_code` → "command may not exercise the feature"
4. **CLI wiring** — new `ll-loop diagnose-evaluators` subcommand in `scripts/little_loops/cli/loop.py` (or wherever subcommands live).
5. **Integration with `analyze-loop`** — when `--min-runs` is satisfied, include the variance report in the existing analysis output.
6. **Tests** — synthetic `.loops/runs/` fixtures with known verdict distributions; assert correct flagging at various thresholds; assert recommendations are stable for known patterns.
7. **Docs** — add to `AUTOMATIC_HARNESSING_GUIDE.md` § Troubleshooting; cross-reference from `agents/loop-specialist.md`.

## Acceptance Criteria

- [ ] `ll-loop diagnose-evaluators <loop>` outputs per-state variance with recommendations
- [ ] Threshold and min-runs configurable via flags with sensible defaults
- [ ] Output available as JSON for downstream consumption
- [ ] `loop-specialist` includes variance findings when relevant
- [ ] Tests with synthetic verdict fixtures cover all-pass, all-fail, mixed, insufficient-data cases
- [ ] Docs link from `AUTOMATIC_HARNESSING_GUIDE.md` and `agents/loop-specialist.md`

## Success Metrics

- `ll-loop diagnose-evaluators` correctly flags states with variance < 0.05 across ≥10 runs
- All three failure patterns detected: high-pass+`llm_structured`, 100%+`output_numeric`, 100%+`exit_code`
- JSON output validates against expected schema
- Tests cover all-pass, all-fail, mixed, and insufficient-data scenarios

## Scope Boundaries

- **In scope**: Per-loop run-history-based variance analysis, per-state pass rates and Bernoulli variance, pattern-matched recommendations, JSON output for downstream consumption, `loop-specialist` integration in diagnosis artifacts
- **Out of scope**: Automatic prompt tuning to improve discriminating power (could be a future meta-loop on top of this signal), cross-loop comparisons (per-loop only; cross-loop benchmarks are a separate feature), real-time evaluation during a run (retrospective only)

## Integration Map

### Files to Modify
- `scripts/little_loops/analytics/` — new run-history reader + variance calculator module
- `scripts/little_loops/cli/loop.py` — new `diagnose-evaluators` subcommand + `analyze` extension

### Dependent Files (Callers/Importers)
- `agents/loop-specialist.md` — consumer of variance findings in diagnosis artifacts

### Tests
- `scripts/tests/` — synthetic `.loops/runs/` fixtures with known verdict distributions

### Documentation
- `AUTOMATIC_HARNESSING_GUIDE.md` — troubleshooting section
- `agents/loop-specialist.md` — cross-reference

### Configuration
- N/A — no new config keys; threshold and min-runs are CLI flags

## Impact

- **Priority**: P3 — addresses self-evaluation bias detection (known paper-level reliability issue), but MR-1 already provides partial coverage
- **Effort**: Medium — 7 implementation steps across analytics module, CLI wiring, and integration
- **Risk**: Low — purely additive analytics reading run history; no changes to loop execution
- **Breaking Change**: No

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `.claude/CLAUDE.md` § Loop Authoring (MR-1) | Sibling rule — this checks for toothless evaluators, MR-1 checks for missing ones |
| `agents/loop-specialist.md` | Self-eval-bias diagnosis that this analytic feeds |
| `.issues/features/P3-FEAT-1325-assess-loop-skill-for-effectiveness-auditing.md` | Completed; different signal (artifact deltas vs verdict variance) |
| `.issues/features/P2-FEAT-1790-ab-baseline-mode-for-ll-loop-run.md` | Stronger signal source — paired with/without runs amplify the variance read |

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T19:36:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22fa3793-04ed-422e-a858-92ebec183578.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open
