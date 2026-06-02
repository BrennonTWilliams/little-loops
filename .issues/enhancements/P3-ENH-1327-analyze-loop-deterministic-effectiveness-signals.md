---
id: ENH-1327
type: ENH
priority: P3
size: Very Large
captured_at: '2026-05-02T19:05:00Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
status: done
completed_at: 2026-05-02T00:00:00Z
---

# ENH-1327: Add Deterministic Effectiveness Signals to `/ll:analyze-loop`

## Summary

Extend `/ll:analyze-loop`'s Step 3 signal classifier with five new **rule-based** signals that catch effectiveness problems without requiring artifact inspection or LLM judgment. These complement (not replace) the LLM-heavy effectiveness audit being added as `/ll:assess-loop` (FEAT-1325) and the `from:`/fragment/sub-loop resolution work (ENH-1326).

## Current Behavior

`/ll:analyze-loop`'s Step 3 signal classifier only emits fault-oriented signals: action failure, SIGKILL, FATAL_ERROR, retry flood, slow state, and evaluate failure. Loops that execute cleanly past all fault checks can still fail to accomplish their goal — phantom convergence, degenerate routing gates, stub actions, empty captures, and plateaued numeric scores are currently invisible to the analyzer.

## Expected Behavior

Step 3 emits five additional deterministic effectiveness signals (Iteration-1 Convergence with No Apply, Degenerate Gate, Stub Action Detection, Capture Vacuum, Numeric Trajectory Stall) derived purely from resolved YAML and event history — no model calls or artifact reads required. `--json` output partitions these under `effectiveness_signals`, separate from `fault_signals`, so `/ll:assess-loop` can consume them cleanly.

## Motivation

The current signal set is purely fault-oriented: action failure, SIGKILL, FATAL_ERROR, retry flood, slow state, evaluate failure. Loops can run cleanly through every one of those checks while still failing to do their job. The five signals below are detectable purely from the resolved YAML plus event history — no model calls, no artifact reads — so they belong in the cheap rule-based skill, not the reasoning-heavy assessor.

## Proposed Signals

### 1. Iteration-1 Convergence with No Apply

- **Trigger**: loop terminated with `iteration_count == 1` AND a state matching the apply/refine pattern (`apply_*`, `refine_*`, `update_*`, `write_*`, `commit_*`) was never visited.
- **Priority**: P3
- **Title**: `"<loop_name> converged on iteration 1 without entering apply/refine state — likely phantom convergence"`
- **Catches**: `apo-textgrad` model emitting `CONVERGED` from `compute_gradient` without ever firing `apply_gradient`.

### 2. Degenerate Gate

- **Trigger**: an `evaluate` state's `route` event distribution shows >95% to a single branch across ≥10 evaluations within the same run, OR ≥20 evaluations across the most recent 5 runs.
- **Priority**: P3
- **Title**: `"<state> route fan-out is degenerate (<N>/<M> evaluations took <branch>)"`
- **Catches**: `refine-to-ready-issue.check_outcome` always routing to `breakdown_issue` when the outcome rubric is too strict.

### 3. Stub Action Detection

- **Trigger**: a state's `action` body matches one of:
  - `^echo "\d+"$` in a state whose name contains `score`, `evaluate`, `judge`, `reward`
  - `^echo "Replace.*"$` or `^echo "TODO.*"$` in any state
  - `^echo "[A-Z_]+"$` (literal verdict echo) in a state whose `evaluate.type` is `output_string`
- **Priority**: P2
- **Title**: `"<state> action is a stub (<echo body>) — loop ships unimplemented"`
- **Catches**: `rl-rlhf` template's `echo "5"` in `score` and `echo "Replace with..."` in `generate`/`refine`. This is a static check at Step 2 (config-time), not history-driven.

### 4. Capture Vacuum

- **Trigger**: a downstream state's `action` or `evaluate.source` references `${captured.X.output}` AND the producing event for capture `X` shows empty/whitespace output in >20% of occurrences within the analyzed window.
- **Priority**: P3
- **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`
- **Catches**: `examples-miner` chained captures (`harvested_examples → judge_scores → calibrated_corpus`) where any upstream silently produces nothing.

### 5. Numeric Trajectory Stall

- **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has standard deviation < 1% of mean for ≥3 iterations AND the value has not crossed its target threshold.
- **Priority**: P3
- **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`
- **Catches**: `rl-coding-agent` reward stuck at the same composite score iteration after iteration; `apo-beam` best-score plateaued below `target_score`.

## Implementation Steps

1. Add a `static_analysis` pass that runs on the resolved state map (depends on ENH-1326 for fragment expansion) and emits Signal 3 (Stub Action) before history is even loaded.
2. Add a `route_distribution` accumulator to the event-history walker; emit Signal 2 (Degenerate Gate) when thresholds met.
3. Add an `apply_state_visit` check to the existing terminal-event handler; emit Signal 1 (Iter-1 Convergence) when conditions met.
4. Add `capture_emptiness` tracking keyed by capture name; emit Signal 4 (Capture Vacuum) at the end of the walk.
5. Add `numeric_trajectory` tracking per `output_numeric`/`convergence` evaluator; emit Signal 5 (Numeric Stall).
6. Update Step 5 output to group these under a new "Effectiveness Signals" subsection, distinct from the existing fault signals.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/COMMANDS.md` — add 5 new signal descriptions to "Signal detection rules:" list and update "Output format:" block to show `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout; update Quick Reference table entry to reflect effectiveness coverage
8. Update `scripts/tests/test_enh1268_doc_wiring.py` — add/update `TestAnalyzeLoopCommandsWiring` tests to assert `"Fault Signals"` and `"Effectiveness Signals"` grouping strings after COMMANDS.md is updated
9. Create `scripts/tests/fixtures/fsm/analysis-stub-action.yaml` — Signal 3 positive fixture (stub action in scoring state); follow `analysis-multi-signal.yaml` convention
10. Create `scripts/tests/fixtures/fsm/analysis-capture-vacuum.yaml` — Signal 4 positive fixture (capture chain with empty-output scenario)
11. Create `scripts/tests/fixtures/fsm/analysis-numeric-stall.yaml` — Signal 5 positive fixture (`convergence` evaluator with stalled `previous` reference)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**SKILL.md section anchors** (all changes go into `skills/analyze-loop/SKILL.md`):

- **Step 1 → `## Step 2` (static pass for Signal 3)**: Insert the stub-action scan immediately after the `ll-loop show <loop_name> --resolved --json` parse block, before event history is loaded. Iterate the resolved state map; apply the three regex patterns against each state's `action` body; emit Signal 3 items into a `static_issues` list separate from the history-driven `signals` list.
- **Step 2 → `## Step 3` (accumulator for Signal 2)**: Declare a `route_distribution: {state_name: {branch: count}}` dict at the start of the event history walk. Update it on every `route` event (`route.to` keyed by the current state context). Evaluate the degenerate-gate threshold after the walk completes (or inline when per-state count ≥ 10).
- **Step 3 → Signal 5 numeric value source**: The `evaluate` event in the history only carries `verdict` and `reason` — the raw numeric value is **not** in the evaluate event. Read it from the most recent `capture` event emitted by the same state immediately before the `evaluate` event. The state's `evaluate.target` (threshold) and `evaluate.type` come from the resolved YAML state map.
- **Step 4 → `--json` flag is currently undefined**: `skills/analyze-loop/SKILL.md` has no `--json` flag or structured JSON output today. The issue states "No CLI surface change," but `--json` with `fault_signals`/`effectiveness_signals` keys would be a new flag. If this is deferred, the Step 5 section only needs the text "Effectiveness Signals" subsection grouping (no JSON branch required for the initial implementation).
- **Step 5 → `## Step 5` output format**: Replace the flat numbered signal list with two labelled groups: `Fault Signals (N):` and `Effectiveness Signals (M):`. Signal 3 results (from the Step 2 static pass) appear in the Effectiveness Signals group alongside the history-driven signals.

**assess-loop integration note**: `skills/assess-loop/SKILL.md` currently re-implements fault signal classification inline in its Step 5 and does **not** consume `effectiveness_signals` from analyze-loop output. Assess-loop would need a separate update to consume effectiveness signals (not in scope for ENH-1327 per Scope Boundaries).

## API/Interface

No CLI surface change. New signals appear inline in `/ll:analyze-loop` output and propagate through `--json` output under a new `effectiveness_signals` key (separate from `fault_signals`) so `/ll:assess-loop` (FEAT-1325) can consume them cleanly.

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md` — Step 3 signal classifier, Step 2 static analysis pass, Step 5 output formatting

### Dependent Files (Callers/Importers)
- `skills/assess-loop/SKILL.md` — consumes `effectiveness_signals` key from `--json` output (FEAT-1325)

### Similar Patterns
- Existing fault signal implementations in `skills/analyze-loop/SKILL.md` Step 3 (action failure, SIGKILL, FATAL_ERROR, retry flood, slow state, evaluate failure)

### Tests
- Synthetic loop run: `apo-textgrad` converging iter 1 → Signal 1
- Synthetic config: state with `echo "5"` in score action → Signal 3
- Synthetic run: 10/10 evaluate routes to one branch → Signal 2
- Healthy runs of `dataset-curation`, `sprint-build-and-validate`, `rl-coding-agent` → no false positives

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1268_doc_wiring.py` — `TestAnalyzeLoopCommandsWiring`: 6 string-presence tests assert on the COMMANDS.md `/ll:analyze-loop` section (e.g., `"Execution Summary"`, `"--resolved"`, `"Sub-loop verdict discarded"`); must be updated to also assert `"Fault Signals"` / `"Effectiveness Signals"` grouping strings after COMMANDS.md is updated [Agent 2/3 finding — tests break if COMMANDS.md changes without corresponding test update]
- `scripts/tests/test_enh1146_doc_wiring.py` — `TestAnalyzeLoopSkillWiring.test_semantic_synthesis_heading_present`: asserts `"Step 3b"` exists in SKILL.md; verify the heading is preserved when the Step 2 static analysis pass is inserted [Agent 3 finding — at risk of breakage if step heading numbering shifts]
- New fixture needed: `scripts/tests/fixtures/fsm/analysis-stub-action.yaml` — Signal 3 positive test case; no existing fixture for stub action pattern (`echo "5"` in a scoring state); follow `analysis-multi-signal.yaml` naming convention and Tier A structural assertion pattern [Agent 3 finding]
- New fixture needed: `scripts/tests/fixtures/fsm/analysis-capture-vacuum.yaml` — Signal 4 positive test case; no existing fixture for capture chain with empty output pattern; model after `examples-miner.yaml` structure [Agent 3 finding]
- New fixture needed: `scripts/tests/fixtures/fsm/analysis-numeric-stall.yaml` — Signal 5 positive test case; no existing fixture for `output_numeric`/`convergence` evaluator trajectory stall; model after `rl-coding-agent.yaml` `score` state with `previous: "${captured.prev_reward.output}"` [Agent 3 finding]
- Note: `sprint-build-and-validate` triggers the pre-existing "Sub-loop verdict discarded" fault signal (`refine_unresolved` routes all branches to `done`); false-positive effectiveness-signal tests using it must scope checks to Signals 1–5 only [Agent 3 finding]

### Documentation
- Output examples in `skills/analyze-loop/SKILL.md` Step 5

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — `/ll:analyze-loop` section: "Signal detection rules:" block must gain 5 new entries (one per signal); "Output format:" block must show `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout; Quick Reference table description becomes stale ("failure signals" only) [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Test Files
- `scripts/tests/test_analyze_loop_synthesis.py` — existing analyze-loop Step 3b tests; model new signal tests after this structure
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — existing fixture for phantom convergence; adapt for Signal 1 synthetic test (apo-textgrad converging iter 1)
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — existing fixture for degenerate self-loop gate; adapt for Signal 2 synthetic test
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — multi-fault-signal fixture; healthy-run snapshots for false-positive tests

#### Loop YAML Sources for Acceptance Criteria Test Cases
- `scripts/little_loops/loops/apo-textgrad.yaml` — `route_convergence` routes `on_yes: done` bypassing `apply_gradient`; primary Signal 1 test case (converges iter 1 without visiting `apply_gradient`)
- `scripts/little_loops/loops/rl-rlhf.yaml` — `score.action: echo "5"` and `generate.action: echo "Replace this with..."` stubs; primary Signal 3 test case
- `scripts/little_loops/loops/examples-miner.yaml` — 7-state `calibrated_corpus` capture chain (`harvest → judge → calibrate → write_examples/synthesize/...`); primary Signal 4 test case
- `scripts/little_loops/loops/rl-coding-agent.yaml` — `score` state with `convergence` evaluator, `previous: "${captured.prev_reward.output}"`; primary Signal 5 test case
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_outcome` / `check_refine_limit` routing; Signal 2 test case candidate (>95% to `breakdown_issue`)
- `scripts/little_loops/loops/dataset-curation.yaml` — healthy loop; include in false-positive test suite (no signals expected)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — healthy loop; include in false-positive test suite

#### Python Modules (for event field and schema reference)
- `scripts/little_loops/events.py` — `LLEvent` dataclass; `capture` events carry `{name: str, output: str}` — Signal 4 reads `capture.output` for emptiness
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` dataclass with `type` enum (`output_numeric`, `convergence`, `output_string`, etc.); `StateConfig.action` string field for stub-action regex matching
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` produces the resolved state map that `ll-loop show --resolved --json` exposes

## Scope Boundaries

- **In scope**: Five new rule-based signals in Step 3 of `analyze-loop`; `effectiveness_signals` key in `--json` output; "Effectiveness Signals" subsection grouping in text output; static analysis pass (Signal 3) at config-load time in Step 2
- **Out of scope**: LLM-based effectiveness reasoning (handled by `/ll:assess-loop` FEAT-1325); changes to existing fault signals or their thresholds; new CLI arguments; cross-run trending or aggregation beyond the per-run checks defined here

## Acceptance Criteria

- [ ] All five signals implemented in `skills/analyze-loop/SKILL.md` Step 3 with deterministic thresholds.
- [ ] Synthetic test: `apo-textgrad` run that converges iter 1 → emits Signal 1.
- [ ] Synthetic test: state with `echo "5"` in score action → emits Signal 3 at config-load time.
- [ ] Synthetic test: 10 evaluate routes 10/10 to one branch → emits Signal 2.
- [ ] `--json` output partitions `fault_signals` and `effectiveness_signals` keys.
- [ ] No false positives on healthy runs of `dataset-curation`, `sprint-build-and-validate`, `rl-coding-agent` (when properly populated).

## Depends On

- ENH-1326 — fragment/inheritance resolution is needed before stub-action and numeric-trajectory checks can be reliably applied.

## Impact

- **Priority**: P3 - Improves signal coverage for effectiveness analysis; complements `/ll:assess-loop` but not blocking
- **Effort**: Medium - Five new signal checkers plus output formatting; depends on ENH-1326 for fragment resolution
- **Risk**: Low - Purely additive; no changes to existing fault signal logic or CLI surface
- **Breaking Change**: No — `effectiveness_signals` is a new `--json` key; existing `fault_signals` key unchanged

## Labels

`enhancement`, `loops`, `analysis`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- `--json` scope is an unresolved decision: the issue states "No CLI surface change" but acceptance criterion 4 requires implementing `--json` output with `fault_signals`/`effectiveness_signals` keys — a new CLI flag. Resolve this decision point before implementing: either add the `--json` flag (scope expansion) or drop acceptance criterion 4 and deliver text-only grouping.
- 3 new YAML fixtures (analysis-stub-action, analysis-capture-vacuum, analysis-numeric-stall) must be authored from scratch; fixture correctness depends on the exact `ll-loop show --resolved --json` event schema — verify field names against live loop output before writing.

## Session Log
- `/ll:decide-issue` - 2026-05-02T23:28:02 - `5b2bfd06-4435-45ee-9d21-b45dce5c461e.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `240b4286-7960-49d3-9941-39b44686e459.jsonl`
- `/ll:wire-issue` - 2026-05-02T23:19:41 - `240b4286-7960-49d3-9941-39b44686e459.jsonl`
- `/ll:refine-issue` - 2026-05-02T23:13:08 - `4fa73db3-6104-4572-aa2c-13851f10c219.jsonl`
- `/ll:format-issue` - 2026-05-02T23:03:39 - `4e772f68-1c09-44f2-844d-e56af787e2e1.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `17077eeb-0a80-4927-8736-7cffe26a726a.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-02
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1335: Add Effectiveness Signals 1-3 + Static Pass + Output Grouping to `/ll:analyze-loop`
- ENH-1336: Add Effectiveness Signals 4-5, Fixtures, and Documentation Wiring to `/ll:analyze-loop`
