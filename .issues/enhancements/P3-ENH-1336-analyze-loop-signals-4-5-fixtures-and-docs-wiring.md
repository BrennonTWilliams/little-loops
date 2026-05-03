---
id: ENH-1336
type: ENH
priority: P3
parent_issue: ENH-1327
---

# ENH-1336: Add Effectiveness Signals 4-5, Fixtures, and Documentation Wiring to `/ll:analyze-loop`

## Summary

Implement the two remaining deterministic effectiveness signals (Capture Vacuum and Numeric Trajectory Stall) in `/ll:analyze-loop` Step 3, create their positive-case fixtures, and update documentation/test wiring to reflect all five effectiveness signals introduced by ENH-1327.

## Parent Issue

Decomposed from ENH-1327: Add Deterministic Effectiveness Signals to `/ll:analyze-loop`

## Proposed Signals to Implement

### Signal 4: Capture Vacuum

- **Trigger**: a downstream state's `action` or `evaluate.source` references `${captured.X.output}` AND the producing event for capture `X` shows empty/whitespace output in >20% of occurrences within the analyzed window.
- **Priority**: P3
- **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`

### Signal 5: Numeric Trajectory Stall

- **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has standard deviation < 1% of mean for ≥3 iterations AND the value has not crossed its target threshold.
- **Priority**: P3
- **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`

## Implementation Steps

1. **Signal 4 — Capture Vacuum** (Step 3): Add `capture_emptiness` tracking keyed by capture name; emit Signal 4 at end of event-history walk. Read `capture.output` from `LLEvent` for emptiness check.

2. **Signal 5 — Numeric Trajectory Stall** (Step 3): Add `numeric_trajectory` tracking per `output_numeric`/`convergence` evaluator. The raw numeric value is **not** in the `evaluate` event — read it from the most recent `capture` event emitted by the same state immediately before the `evaluate` event. The state's `evaluate.target` (threshold) and `evaluate.type` come from the resolved YAML state map.

3. **Fixture: `analysis-capture-vacuum.yaml`** — Signal 4 positive test case (capture chain with empty-output scenario); model after `examples-miner.yaml` structure (7-state `calibrated_corpus` capture chain).

4. **Fixture: `analysis-numeric-stall.yaml`** — Signal 5 positive test case (`convergence` evaluator with stalled `previous` reference); model after `rl-coding-agent.yaml` `score` state with `previous: "${captured.prev_reward.output}"`.

5. **COMMANDS.md update** (`docs/reference/COMMANDS.md`): Add 5 new signal descriptions to the "Signal detection rules:" list; update "Output format:" block to show `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout; update Quick Reference table entry to reflect effectiveness coverage (not "failure signals" only).

6. **Test wiring: `test_enh1268_doc_wiring.py`** (`scripts/tests/test_enh1268_doc_wiring.py`): Update `TestAnalyzeLoopCommandsWiring` tests to assert `"Fault Signals"` and `"Effectiveness Signals"` grouping strings in COMMANDS.md after the Step 5 update; the existing 6 string-presence tests must remain passing.

## Codebase Research Findings (from ENH-1327)

**Key files**:
- `skills/analyze-loop/SKILL.md` — add Signal 4 and 5 to Step 3
- `scripts/little_loops/events.py` — `LLEvent` dataclass; `capture` events carry `{name: str, output: str}` — Signal 4 reads `capture.output`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.type` enum (`output_numeric`, `convergence`); `evaluate.target` threshold
- `docs/reference/COMMANDS.md` — add 5 signal entries + update output format block
- `scripts/tests/test_enh1268_doc_wiring.py` — `TestAnalyzeLoopCommandsWiring` 6 existing string-presence tests

**Loop YAML sources**:
- `scripts/little_loops/loops/examples-miner.yaml` — primary Signal 4 test case (harvest → judge → calibrate chain)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — primary Signal 5 test case (`score` state with `convergence` evaluator, `previous: "${captured.prev_reward.output}"`)
- `scripts/little_loops/loops/apo-beam.yaml` — Signal 5 test case (best-score plateaued below `target_score`)
- `scripts/little_loops/loops/dataset-curation.yaml` — include in false-positive test suite (no signals expected)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — include in false-positive suite; note: triggers pre-existing "Sub-loop verdict discarded" fault signal (`refine_unresolved` routes all branches to `done`) — scope false-positive checks to Signals 1-5 only

**Test files**:
- `scripts/tests/test_analyze_loop_synthesis.py` — model new signal tests after this structure
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — multi-fault-signal fixture; naming convention reference

## Pre-requisites

This issue should follow ENH-1335 (Signals 1-3 + output grouping) since:
- COMMANDS.md update in Step 5 documents all 5 signals and references the `Fault Signals / Effectiveness Signals` grouping format established in ENH-1335's Step 5 SKILL.md changes.
- Signals 4-5 can be added to SKILL.md independently, but COMMANDS.md update requires the full output format to be settled.

## Acceptance Criteria

- [ ] Signal 4 (Capture Vacuum) implemented; `examples-miner` chain with empty upstream capture emits the signal.
- [ ] Signal 5 (Numeric Stall) implemented; `rl-coding-agent` reward stuck at same value for ≥3 iterations emits the signal.
- [ ] `analysis-capture-vacuum.yaml` fixture created and passing.
- [ ] `analysis-numeric-stall.yaml` fixture created and passing.
- [ ] `docs/reference/COMMANDS.md` updated with all 5 signal descriptions and two-group output format.
- [ ] `test_enh1268_doc_wiring.py` passes with new `"Fault Signals"` / `"Effectiveness Signals"` assertions.
- [ ] No false positives on healthy runs of `dataset-curation` and `rl-coding-agent` (when properly populated).

## Depends On

- ENH-1326 — fragment/inheritance resolution needed for reliable signal detection.
- ENH-1335 — establishes Step 5 output grouping in SKILL.md; COMMANDS.md update should follow.

## Scope Boundaries

- **In scope**: Signals 4, 5 in `skills/analyze-loop/SKILL.md`; `analysis-capture-vacuum.yaml` and `analysis-numeric-stall.yaml` fixtures; `docs/reference/COMMANDS.md` update; `test_enh1268_doc_wiring.py` update.
- **Out of scope**: Signals 1, 2, 3 (ENH-1335); `--json` flag with structured output (deferred per confidence check notes in parent ENH-1327); assess-loop integration (FEAT-1325 separate).

## Session Log
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17077eeb-0a80-4927-8736-7cffe26a726a.jsonl`
