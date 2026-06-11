---
id: ENH-2080
title: Add retry-budget calibration guide tied to evaluator health
type: ENH
priority: P3
status: done
captured_at: '2026-06-10T18:12:09Z'
completed_at: '2026-06-11T03:16:45Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
depends_on: ENH-2084
confidence_score: 88
outcome_confidence: 78
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 19
score_change_surface: 22
decision_needed: false
---

# ENH-2080: Add retry-budget calibration guide tied to evaluator health

## Summary

Adds a `ll-loop calibrate-budget <loop>` subcommand that reports per-evaluator Bernoulli variance and warns authors when variance falls below 0.05, preventing wasted retry budget against toothless evaluators. Surfaces the variance score in `ll-loop run --baseline` output and documents the threshold in CLAUDE.md with a worked example linking evaluator health to retry budget ROI.

## Motivation

Loop `max_iterations` values are currently set by convention. Additional iterations amplify a sound strategy but produce near-zero returns when the underlying evaluator is unhealthy. Spending retry budget against a toothless evaluator wastes tokens without changing outcomes, which is directly indicated by the existing Bernoulli variance check in CLAUDE.md.

## Current Behavior

`max_iterations` is set by convention with no tooling feedback about evaluator health. Running `ll-loop run --baseline` produces a diff table but does not include per-evaluator variance scores. CLAUDE.md mentions the Bernoulli variance threshold (< 0.05) in the Loop Authoring section but does not link it to retry budget ROI or provide a worked example.

## Expected Behavior

- `ll-loop calibrate-budget <loop>` runs the loop's evaluator in isolation across sampled past run states and reports Bernoulli variance `p*(1-p)` per evaluator state.
- Variance < 0.05 triggers an actionable warning recommending evaluator repair before increasing `max_iterations`.
- `ll-loop run --baseline` diff table includes a variance score column.
- CLAUDE.md Loop Authoring section documents the 0.05 threshold with a concrete worked example.

## Proposed Solution

Add a `ll-loop calibrate-budget <loop>` subcommand that:
1. Runs the loop's evaluator in isolation across a sample of past run states
2. Reports the Bernoulli variance `p*(1-p)`
3. If variance is below 0.05, emits a warning that increasing `max_iterations` is unlikely to help and recommends fixing the evaluator first

Document the threshold in the Loop Authoring section of CLAUDE.md with a concrete example linking evaluator health to retry budget ROI. Surface the variance score in `ll-loop run --baseline` output.

## API/Interface

```bash
# New subcommand
ll-loop calibrate-budget <loop>

# Example output
Loop: rn-refine
Evaluator: check_quality (llm_structured)
  Variance p*(1-p): 0.02   ⚠ WARN: below 0.05 threshold — fix evaluator before increasing max_iterations
Evaluator: check_exit (exit_code)
  Variance p*(1-p): 0.23   ✓ OK
```

## Implementation Steps

1. Add `"calibrate-budget"` to `known_subcommands` set in `cli/loop/__init__.py:main_loop()` (around line 51); register argparse subparser following the `diagnose-evaluators` block (lines 650–679) with positional `loop`, `--threshold` (float, default 0.05), `--min-runs` (int, default 10), `--json` flag; add `elif args.command == "calibrate-budget": return cmd_calibrate_budget(args, loops_dir, logger)` dispatch branch
2. Add `cmd_calibrate_budget()` to `cli/loop/info.py` alongside `cmd_diagnose_evaluators()` (line 707); call `compute_evaluator_variance(loop_name, loops_dir, threshold, min_runs)` from `analytics.variance` — the full p*(1-p) logic already exists there; do not re-implement; format output per the API/Interface spec above
3. Update `_print_ab_summary()` in `cli/loop/_helpers.py` to call `compute_evaluator_variance()` after reading `ab.json` from the run dir; append per-evaluator variance rows using the existing fixed-width column format; coordinate placement with ENH-2084's Wilson CI column so both land adjacent in the same table pass
4. Add `cmd_calibrate_budget` to the `info` module handler_specs in `test_cli_loop_dispatch.py:_mock_handlers()`; add `test_calibrate_budget_routes_to_handler()` routing test following the `test_diagnose_evaluators_routes_to_handler()` pattern
5. Add `TestCmdCalibrateBudget` class to `test_ll_loop_commands.py` following `TestCmdDiagnoseEvaluators` pattern: use `_make_events_jsonl()` helper and `_base_args()` constructor; test that variance is reported correctly, warning is emitted when variance < 0.05, and `--json` flag produces parseable JSON
6. Update `.claude/CLAUDE.md` Loop Authoring section (after the existing `ll-loop diagnose-evaluators` mention at lines 166–167) with a worked example: show `p*(1-p) = 0.02` for an always-yes evaluator vs `p*(1-p) = 0.23` for a healthy one, and explain that increasing `max_iterations` against a toothless evaluator wastes tokens without changing outcomes

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Audit `_print_ab_summary()` call site in `scripts/little_loops/cli/loop/_helpers.py:run_foreground()` (line 1328) — current call is `_print_ab_summary(ab_path)` with one arg; if variance column requires `loop_name`/`loops_dir`, add keyword args with defaults or thread them through from the run context; `fsm.name` is already in scope at the call site
8. Update `scripts/tests/test_ll_loop_display.py:TestABSummaryDisplay` — verify `test_ab_summary_with_no_file_is_noop` (`captured.out == ""`) passes after variance column addition; ensure the no-file early-return guard in `_print_ab_summary` fires before any variance lookup; update the 3 format-asserting tests to accommodate variance column output if needed
9. Add `#### \`ll-loop calibrate-budget\`` section to `docs/reference/CLI.md` after the `diagnose-evaluators` section, documenting `--threshold`, `--min-runs`, `--json` flags
10. Add `ll-loop calibrate-budget` mention to `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` `## Validating and Measuring` bullet list alongside `diagnose-evaluators`

## Scope Boundaries

- Does **not** automate evaluator repair or suggest specific fixes beyond "fix the evaluator"
- Does **not** change the 0.05 variance threshold (fixed per SHOR Table 1 / CLAUDE.md)
- Does **not** modify existing `ll-loop run` behavior beyond adding the variance column to `--baseline` output
- Does **not** introduce per-loop thresholds; the 0.05 threshold is universal

## Acceptance Criteria

- [x] `ll-loop calibrate-budget <loop>` runs and reports per-evaluator Bernoulli variance
- [x] Variance < 0.05 triggers a warning recommending evaluator repair before increasing iterations
- [ ] `ll-loop run --baseline` output includes variance score *(deferred: depends on ENH-2084 for `_print_ab_summary` column coordination)*
- [x] CLAUDE.md Loop Authoring section documents the threshold with a worked example

## Resolution

Implemented `ll-loop calibrate-budget` subcommand as a retry-budget-framed variant of
`diagnose-evaluators`, reusing `compute_evaluator_variance()` from `analytics.variance`.

**Changes:**
- `scripts/little_loops/cli/loop/info.py` — added `cmd_calibrate_budget()` handler
- `scripts/little_loops/cli/loop/__init__.py` — registered `calibrate-budget` in
  `known_subcommands`, argparse subparsers, and dispatch chain
- `.claude/CLAUDE.md` — added worked example linking evaluator variance to retry-budget ROI
- `docs/reference/CLI.md` — added `#### \`ll-loop calibrate-budget\`` section
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — added calibrate-budget bullet to
  Validating and Measuring section
- `scripts/tests/test_ll_loop_commands.py` — added `TestCmdCalibrateBudget` (6 tests)
- `scripts/tests/test_cli_loop_dispatch.py` — added routing test + handler mock

**Deferred (pending ENH-2084):** `_print_ab_summary` variance column in `ll-loop run --baseline`
output — step 3/7/8 skipped to avoid table rework when ENH-2084's Wilson CI column lands.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `"calibrate-budget"` to `known_subcommands` set (around line 51); register argparse subparser following the `diagnose-evaluators` block (lines 650–679); add dispatch branch to `main_loop()`
- `scripts/little_loops/cli/loop/info.py` — add `cmd_calibrate_budget()` handler alongside `cmd_diagnose_evaluators()` (line 707); calls `compute_evaluator_variance()` from `analytics.variance`
- `scripts/little_loops/cli/loop/_helpers.py` — update `_print_ab_summary()` to append evaluator variance rows to the `--baseline` diff table; extend fixed-width column format
- `.claude/CLAUDE.md` — Loop Authoring section: add 0.05 threshold documentation with worked example linking evaluator health to `max_iterations` ROI

### Dependent Files (Callers/Importers)
- `scripts/little_loops/analytics/variance.py` — `compute_evaluator_variance()`, `EvaluatorVariance`, `VarianceReport` — **already implements p*(1-p)**; `calibrate-budget` calls this directly rather than re-implementing variance logic; `_correlate_verdicts()` walks `.loops/.history/*-{loop_name}/events.jsonl`
- `scripts/little_loops/fsm/persistence.py` — `HISTORY_DIR` constant; defines run history directory structure (`.loops/.history/`); `get_archived_events()` for reading event files; referenced by `compute_evaluator_variance()` internally
- `scripts/little_loops/ab_writer.py` — `ABResults` dataclass, `calculate_ab_summary()`, `read_ab_json()` — `_print_ab_summary()` reads `ab.json` via these; may need to expose per-state data so variance can be looked up by state name in the extended table

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (line 1106) calls `_print_ab_summary(ab_path)` at line 1328 with a single argument [Agent 1 finding, file path corrected by `/ll:ready-issue`]; if the variance column requires additional args (e.g., `loop_name`, `loops_dir`) the call site must supply them — `fsm.name` is already in scope but `loops_dir` must be threaded through or defaulted

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:cmd_diagnose_evaluators()` (line 707) — closest analog; `calibrate-budget` is a calibration-framed variant calling the same `compute_evaluator_variance()`; follow identical arg parsing and output formatting
- `scripts/little_loops/cli/loop/_helpers.py:_print_ab_summary()` — `--baseline` diff table to extend; uses `printf`-style fixed-width columns (`f"{'state':<24} {'invoc':>5}"`) — match this format for the variance column
- `scripts/little_loops/analytics/variance.py:compute_evaluator_variance()` — returns `VarianceReport(loop, total_runs, states: list[EvaluatorVariance])`; states sorted ascending by variance (lowest = most suspicious first)

### Tests
- `scripts/tests/test_ll_loop_commands.py:TestCmdDiagnoseEvaluators` — model class for behavior tests; use `_make_events_jsonl()` and `_base_args()` patterns for new `TestCmdCalibrateBudget` class
- `scripts/tests/test_cli_loop_dispatch.py:_mock_handlers()` — add `cmd_calibrate_budget` to the `info` module `handler_specs` list; add routing test
- `scripts/tests/test_loop_run_analytics.py:TestComputeEvaluatorVariance` — existing analytics unit tests; reference for fixture patterns and fixture structure (10 run dirs under `.history/20260101T0000{i:02d}-<loop>`)
- New `TestCmdCalibrateBudget` in `test_ll_loop_commands.py` — verify variance reported, warning emitted when variance < 0.05, `--json` flag output is parseable

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py:TestABSummaryDisplay` — **update: at risk of breaking** [Agent 3 finding]; 4 methods assert on `_print_ab_summary` output strings; `test_ab_summary_with_no_file_is_noop` uses exact equality (`captured.out == ""`), will break if any variance-path output runs before the no-file early-return guard; the early-return guard in `_print_ab_summary` must fire before any variance lookup is triggered

### Documentation
- `.claude/CLAUDE.md` (Loop Authoring section) — add threshold documentation with worked example

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — every `ll-loop` subcommand has a dedicated `####`-level heading; add `#### \`ll-loop calibrate-budget\`` section immediately after `#### \`ll-loop diagnose-evaluators\`` documenting `--threshold`, `--min-runs`, `--json` flags [Agent 2 finding]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — `## Validating and Measuring` section bullet list references `ll-loop diagnose-evaluators`; add `ll-loop calibrate-budget` as a peer bullet (same conceptual layer: evaluator health → retry budget) [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 — Improves developer experience for loop authors; not blocking but addresses a real pain point (wasted tokens against toothless evaluators)
- **Effort**: Medium — New CLI subcommand requires evaluator isolation runner and history DB integration; `diagnose-evaluators` pattern can be reused
- **Risk**: Low — Additive feature; no changes to existing evaluator behavior or loop execution paths
- **Breaking Change**: No

## Labels

`cli`, `loops`, `dx`, `documentation`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-10 (re-scored 2026-06-10 post wiring/refinement)_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION _(was 80 before wiring/refine passes)_
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **ENH-2084 still open**: Step 3 (`_print_ab_summary` variance column) must coordinate column placement with ENH-2084's Wilson CI column. Suggested staging: implement all other steps first (1–2, 4–6, 7–10), defer step 3 until ENH-2084 merges to avoid table rework.

_Previous concerns resolved: Integration Map file path error (`loop_cli.py`) fixed by `/ll:refine-issue`; all integration touchpoints now documented with line numbers via `/ll:wire-issue`._

## Session Log
- `/ll:ready-issue` - 2026-06-11T03:07:39 - `ad30eba9-0026-4c19-80eb-47f6d08beed3.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `ca414300-0c23-44ad-9e43-2c615cdcd4cf.jsonl`
- `/ll:wire-issue` - 2026-06-11T02:59:37 - `6f86a4a3-6421-45ac-8ae7-307de5439ff7.jsonl`
- `/ll:confidence-check` - 2026-06-10T18:30:00Z - `31388a78-9fa1-4fef-883a-0f0a6e1193d4.jsonl`
- `/ll:refine-issue` - 2026-06-11T02:47:20 - `aaca4fc0-a8a7-445b-b6b1-53e846ec60e3.jsonl`
- `/ll:confidence-check` - 2026-06-10T23:45:00Z - `48aecd8b-fc0b-4050-b978-3b6fd561e85b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-10T23:30:28 - `59a16773-20bc-402b-b0cb-97d45d141b4c.jsonl`
- `/ll:format-issue` - 2026-06-10T23:22:11 - `c93434ab-0ed3-45d3-9d83-508ca4bc0147.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers the `calibrate-budget` subcommand and the variance score column in `ll-loop run --baseline`. Related issue ENH-2084 adds Wilson CI bounds to the same baseline diff table and the same `ll-loop diagnose-evaluators` surface. Both issues compute statistics over past evaluator run states from the history DB using the same inputs (p, n). To avoid duplicate sampling/computation code, variance `p*(1-p)` and Wilson CI should be implemented in a shared `scripts/little_loops/stats.py` module rather than independently. This issue should land after ENH-2084 so the variance column can be placed adjacent to ENH-2084's Wilson CI column in a coordinated table format.
