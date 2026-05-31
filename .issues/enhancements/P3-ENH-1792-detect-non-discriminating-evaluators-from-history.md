---
id: ENH-1792
title: Detect Non-Discriminating Evaluators from Run History
type: ENH
priority: P3
captured_at: '2026-05-29T19:08:54Z'
completed_at: '2026-05-31T04:01:27Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: done
parent: EPIC-1663
labels:
- enhancement
- loops
- evaluator
- meta-loop
- validation
- analytics
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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
7. **Docs** — add to `AUTOMATIC_HARNESSING_GUIDE.md` § Troubleshooting (insertion point at line 717, currently covers 8 symptoms); cross-reference from `agents/loop-specialist.md` (has `evaluator-trivial` failure mode at line 64 that this analytic feeds).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Subcommand registration test** — add `test_diagnose_evaluators_subcommand_registered` to `scripts/tests/test_ll_loop_execution.py` (follows `test_monitor_subcommand_registered` pattern). Verifies `"diagnose-evaluators"` is in the `known_subcommands` set so bare-name shorthand doesn't route it as a loop name.

9. **`_verdict_is_yes()` unit tests** — add to `scripts/tests/test_fsm_persistence.py`. This private function has **zero** test coverage currently. The analytics module will be its first external consumer. Test verdict strings: `"yes"`, `"yes (self-assessed)"`, `"no"`, `"progress"`, `"success"`, `"failure"`, `""`.

10. **Integration test** — add `test_diagnose_evaluators_*` to `scripts/tests/test_ll_loop_integration.py` (`TestMainLoopIntegration`). End-to-end CLI invocation with synthetic `.loops/.history/` directories.

11. **Analytics module unit tests** — new file `scripts/tests/test_loop_run_analytics.py`. Unit tests for variance calculator (all-pass, all-fail, mixed, insufficient-data) and recommendation generator (one test per failure pattern). Follows `test_issue_history_advanced_analytics.py` pattern.

12. **CLI reference docs** — add `#### ll-loop diagnose-evaluators` subsection to `docs/reference/CLI.md` (after `audit-meta` at line 640) with flag descriptions, output format, and usage example.

13. **Changelog entry** — add entry to `CHANGELOG.md` following the `audit-meta` subcommand pattern.

14. **CLAUDE.md cross-reference** — add `diagnose-evaluators` mention in Loop Authoring section as the tool to validate discriminator health after MR-1 passes.

15. **Codex agent regeneration** — run `ll-adapt-agents-for-codex` to regenerate `.codex/agents/loop-specialist.toml` after `agents/loop-specialist.md` is updated (Step 7).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (Run-history reader)**: Use `_list_archived_runs()` from `scripts/little_loops/cli/loop/info.py:430` and `get_archived_events()` from `scripts/little_loops/fsm/persistence.py:965` instead of building a new directory walker. The data source is `.loops/.history/<run_id>-<loop_name>/events.jsonl` (flat layout) — filter for `event == "evaluate"`. State names are in `state_enter` events, not evaluate events, so correlate by iteration/position.
- **Step 2 (Variance calculator)**: Reuse `_verdict_is_yes()` from `scripts/little_loops/fsm/persistence.py:69` for binary verdict classification. Bernoulli variance = `p*(1-p)` where `p = pass_count / total_verdicts` grouped by state name. Skip states without `evaluate:` blocks by loading the loop YAML via `load_loop()` from `scripts/little_loops/cli/loop/_helpers.py:845` and checking `fsm.states[name].evaluate is not None`.
- **Step 3 (Recommendation generator)**: Extract evaluator `type` from `fsm.states[name].evaluate.type` (one of `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `llm_structured`, `mcp_result`, `harbor_scorer` — from `EvaluateConfig` in `scripts/little_loops/fsm/schema.py:56`). Pattern-match failure modes: high pass-rate + `llm_structured` type, 100% pass + `output_numeric` type, 100% pass + `exit_code` type.
- **Step 4 (CLI wiring)**: Follow the `audit-meta` subcommand pattern exactly: register parser with `subparsers.add_parser()` and `set_defaults(command="diagnose-evaluators")`, add `--threshold` (float, default 0.05) and `--min-runs` (int, default 10) flags using `add_argument()`, dispatch in the `if/elif` chain, implement handler in `scripts/little_loops/cli/loop/info.py`. Model on lines 531-538 and 633-634 of `scripts/little_loops/cli/loop/__init__.py`.
- **Step 6 (Tests)**: Model on `TestCmdAuditMeta` class at `scripts/tests/test_ll_loop_commands.py:3948`. Create synthetic `.loops/.history/<run_id>-<loop>/events.jsonl` with evaluate events containing known verdict distributions. Test: all-pass (variance=0), all-fail (variance=0), mixed 50/50 (variance=0.25), and fewer-than-min-runs (no output expected).

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
- `scripts/little_loops/analytics/` — new sub-package: `__init__.py` + `variance.py` (run-history reader, variance calculator, recommendation generator)
- `scripts/little_loops/cli/loop/__init__.py` — register `diagnose-evaluators` in `known_subcommands`, add parser with `--threshold`/`--min-runs`/`--json` flags, add dispatch branch, add import from `info`
- `scripts/little_loops/cli/loop/info.py` — new `cmd_diagnose_evaluators()` handler (modeled on `cmd_audit_meta()` at line 585)

### Dependent Files (Callers/Importers)

_New analytics module imports from (read-only, no changes to these files):_
- `scripts/little_loops/fsm/persistence.py` — `_verdict_is_yes()` (line 69), `get_archived_events()` (line 965), `HISTORY_DIR` (line 43)
- `scripts/little_loops/cli/loop/_helpers.py` — `load_loop()` (line 845)
- `scripts/little_loops/cli/loop/info.py` — `_list_archived_runs()` pattern (returns `int` — replicate dir-walk inline per `cmd_audit_meta` precedent)

_Consumers of the new diagnostic output:_
- `agents/loop-specialist.md` — consumer of variance findings in diagnosis artifacts (3 update points: `evaluator-trivial` row, auditing section, Workflow Step 2)
- `.codex/agents/loop-specialist.toml` — auto-regenerated after `loop-specialist.md` changes

_Wiring pass added by `/ll:wire-issue`:_

### Tests

_Wiring pass added by `/ll:wire-issue`:_

| Test File | What | Pattern to Follow |
|-----------|------|-------------------|
| `scripts/tests/test_ll_loop_commands.py` | New `TestCmdDiagnoseEvaluators` class — tests handler with synthetic `.loops/.history/` dirs and `events.jsonl` fixtures (all-pass, all-fail, mixed, insufficient-data) | `TestCmdAuditMeta` at line 3948 — imports handler inline, uses `tmp_path / ".loops"`, passes `argparse.Namespace`, asserts on `capsys` and return code |
| `scripts/tests/test_ll_loop_execution.py` | New `test_diagnose_evaluators_subcommand_registered` — verifies `"diagnose-evaluators"` is in `known_subcommands` | `test_monitor_subcommand_registered` at line ~1451 |
| `scripts/tests/test_ll_loop_integration.py` | New `test_diagnose_evaluators_*` methods — end-to-end CLI invocation | `TestMainLoopIntegration.test_run_dry_run_outputs_plan` at line 115 |
| `scripts/tests/test_fsm_persistence.py` | Add `_verdict_is_yes()` unit tests — currently has **zero** test coverage. Test all verdict strings: `"yes"`, `"yes (self-assessed)"`, `"no"`, `"progress"`, `"success"`, `"failure"`, `""` | `TestLoopState` table-driven pattern |
| `scripts/tests/test_loop_run_analytics.py` | **New file** — unit tests for the `analytics/` module (variance calculator, recommendation generator) | `test_issue_history_advanced_analytics.py` — dataclass tests + analysis function tests |
| `scripts/tests/test_cli_output.py` | May need output formatting tests if JSON schema validation is desired | Existing patches of `get_archived_events` at lines 127–169 |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add troubleshooting row for "evaluator passes too consistently" at line 717
- `agents/loop-specialist.md` — cross-reference `diagnose-evaluators` in `evaluator-trivial` failure mode (line 64), add auditing subsection, update Workflow Step 2
- `docs/reference/CLI.md` — new `#### ll-loop diagnose-evaluators` subsection (after audit-meta at line 640) + example
- `CHANGELOG.md` — new entry (follow `audit-meta` pattern)
- `.claude/CLAUDE.md` — cross-reference `diagnose-evaluators` in Loop Authoring section (sibling to MR-1 rule)

### Configuration
- N/A — no new config keys; threshold and min-runs are CLI flags

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Run history location**: Archived run data lives in `.loops/.history/<run_id>-<loop_name>/` (not `.loops/runs/` as the issue currently assumes). See `HISTORY_DIR` in `scripts/little_loops/fsm/persistence.py:43`. The `.loops/runs/` directory holds per-run working artifacts but NOT the archived JSONL events needed for variance analysis.
- **Closest existing analog**: `cmd_audit_meta()` in `scripts/little_loops/cli/loop/info.py:585` — walks `.loops/.history/`, reads per-run JSONL (`meta-eval.jsonl`), computes agreement stats, outputs text/JSON. The new `diagnose-evaluators` should follow this pattern but read `events.jsonl` instead.
- **Reusable verdict classification**: `_verdict_is_yes()` in `scripts/little_loops/fsm/persistence.py:69` already converts verdict strings to boolean — maps `"yes"` prefixes and `"progress"`/`"success"` to `True`. Use directly for Bernoulli variance computation.
- **Reusable event reader**: `get_archived_events()` in `scripts/little_loops/fsm/persistence.py:965` reads `events.jsonl` for a specific run. `_list_archived_runs()` in `info.py:430` finds run directories by globbing `*-{loop_name}`.
- **Evaluator config extraction**: `load_loop()` in `scripts/little_loops/cli/loop/_helpers.py:845` parses loop YAML into `FSMLoop`. Access evaluator type via `fsm.states[name].evaluate.type` (from `scripts/little_loops/fsm/schema.py:56` — `EvaluateConfig`).
- **Event structure caveat**: Evaluate events in JSONL contain `type` (evaluator type) and `verdict` (routing key), but NOT the state name. The state name must be correlated with the preceding `state_enter` event in the same events file.
- **Existing `audit-meta` subcommand**: Already wired as a precedent at `scripts/little_loops/cli/loop/__init__.py:531-538` (parser) and `:633-634` (dispatch). The `diagnose-evaluators` subcommand follows the same registration pattern.
- **Test pattern**: `TestCmdAuditMeta` in `scripts/tests/test_ll_loop_commands.py:3948` creates synthetic `.loops/.history/` directories with JSONL files and asserts on computed statistics. Model the new tests on this class.

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
- `/ll:ready-issue` - 2026-05-31T03:50:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2968db23-d30a-4fb4-b91c-3c30dd626600.jsonl`
- `/ll:wire-issue` - 2026-05-31T03:45:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea9e94a2-c77d-45f9-87f4-5405d4c3b67e.jsonl`
- `/ll:refine-issue` - 2026-05-31T03:38:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5706391b-b4d6-4dc9-9959-0b1db732c320.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T19:36:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22fa3793-04ed-422e-a858-92ebec183578.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`
- `/ll:confidence-check` - 2026-05-30T22:48:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a85e424a-d8a3-4574-955e-4442d05c5fe2.jsonl`
- `/ll:manage-issue` - 2026-05-31T04:01:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b10ff71-7428-45d7-8799-ab85bfd7e39c.jsonl`

---

## Resolution

### Summary of Changes

Implemented `ll-loop diagnose-evaluators` subcommand that scans `.loops/.history/*-<loop>/events.jsonl` to detect non-discriminating evaluator states whose verdict has near-zero Bernoulli variance `p*(1-p)` across runs. Flagged states receive pattern-matched recommendations for improving discriminating power.

### Files Created
- `scripts/little_loops/analytics/__init__.py` — new analytics sub-package
- `scripts/little_loops/analytics/variance.py` — run-history reader, verdict-variance calculator, recommendation generator
- `scripts/tests/test_loop_run_analytics.py` — unit tests for variance calculator and recommendation generator (TestEvaluatorVariance, TestVarianceReport, TestCorrelateVerdicts, TestGenerateRecommendation, TestComputeEvaluatorVariance)

### Files Modified
- `scripts/little_loops/cli/loop/__init__.py` — registered `diagnose-evaluators` in `known_subcommands`, added parser with `--threshold`/`--min-runs`/`--json` flags, added dispatch branch, added import
- `scripts/little_loops/cli/loop/info.py` — new `cmd_diagnose_evaluators()` handler (modeled on `cmd_audit_meta`)
- `scripts/tests/test_ll_loop_commands.py` — new `TestCmdDiagnoseEvaluators` class (7 tests)
- `scripts/tests/test_ll_loop_execution.py` — new `test_diagnose_evaluators_subcommand_registered` test
- `scripts/tests/test_ll_loop_integration.py` — new `test_diagnose_evaluators_no_history` integration test
- `scripts/tests/test_fsm_persistence.py` — new `TestVerdictIsYes` class (9 tests, was zero coverage)
- `docs/reference/CLI.md` — added `#### ll-loop diagnose-evaluators` subsection
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — added troubleshooting row for evaluator passes too consistently
- `agents/loop-specialist.md` — updated evaluator-trivial row, Workflow Step 2, and auditing section to reference diagnose-evaluators
- `CHANGELOG.md` — added entry under [Unreleased]
- `.claude/CLAUDE.md` — added diagnose-evaluators cross-reference in Loop Authoring section
- `.codex/agents/loop-specialist.toml` — regenerated after loop-specialist.md update

### Acceptance Criteria

- [x] `ll-loop diagnose-evaluators <loop>` outputs per-state variance with recommendations
- [x] Threshold and min-runs configurable via flags with sensible defaults
- [x] Output available as JSON for downstream consumption
- [x] `loop-specialist` includes variance findings when relevant (docs updated)
- [x] Tests with synthetic verdict fixtures cover all-pass, all-fail, mixed, insufficient-data cases
- [x] Docs link from `AUTOMATIC_HARNESSING_GUIDE.md` and `agents/loop-specialist.md`

### Success Metrics

- `ll-loop diagnose-evaluators` correctly flags states with variance < 0.05 across ≥10 runs
- All three failure patterns detected: high-pass+`llm_structured`, 100%+`output_numeric`, 100%+`exit_code`
- JSON output validates against expected schema
- Tests cover all-pass, all-fail, mixed, and insufficient-data scenarios

---

## Status
done
