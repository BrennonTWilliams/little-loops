---
id: ENH-1342
type: ENH
priority: P3

confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-03T05:14:52Z
parent: ENH-1336
status: done
---

# ENH-1342: Implement Signals 4-5 in `/ll:analyze-loop` SKILL.md, Fixtures, and Synthesis Tests

## Summary

Implement the two remaining deterministic effectiveness signals (Capture Vacuum and Numeric Trajectory Stall) in `skills/analyze-loop/SKILL.md` Step 3, create their positive-case fixtures, and add corresponding synthesis test methods.

## Parent Issue

Decomposed from ENH-1336: Add Effectiveness Signals 4-5, Fixtures, and Documentation Wiring to `/ll:analyze-loop`

## Current Behavior

`skills/analyze-loop/SKILL.md` Step 3 implements effectiveness Signals 1-3 (rate-limit waiting, degenerate gate route distribution, iter-1 convergence without apply) plus retry flood and slow state, but Signals 4 (Capture Vacuum) and 5 (Numeric Trajectory Stall) from the original ENH-1336 design are not implemented. No fixtures exist for these two signal types and no synthesis tests cover them.

## Expected Behavior

After this enhancement, Step 3 of SKILL.md emits Signal 4 when a downstream state consumes a `${captured.X.output}` reference whose producing state's `action_complete.output_preview` is empty in >20% of runs, and Signal 5 when an `output_numeric` or `convergence` evaluator's value stalls (stddev <1% of mean across ≥3 iterations) without crossing its target. Two new fixtures (`analysis-capture-vacuum.yaml`, `analysis-numeric-stall.yaml`) and matching synthesis test methods exist; the Step 5 effectiveness enumeration list mentions both new signals; existing guardrail tests (`test_enh1146_doc_wiring.py`) continue to pass.

## Impact

- **Priority**: P3 - Completes the Signals 4-5 portion of parent ENH-1336 decomposition; non-blocking but closes a known gap in the analyze-loop signal taxonomy.
- **Effort**: Small - Pattern is established by ENH-1335 (Signals 1-3 landed in commit a9ea71e6); insertion site, fixture style, and test pattern are fully specified in the refinement passes.
- **Risk**: Low - Additive changes only (new SKILL.md blocks, new fixtures, new tests); guardrail test enumerated in Step 6 protects against regression of existing assertions.
- **Breaking Change**: No

## Labels

`enhancement`, `analyze-loop`, `effectiveness-signals`

## Implementation Steps

1. **Signal 4 — Capture Vacuum** (Step 3 of SKILL.md): Add `capture_emptiness` tracking keyed by capture name; emit Signal 4 at end of event-history walk. There is no `capture` event in the JSONL stream — read emptiness from `action_complete.output_preview` for the state whose resolved YAML has `capture: X` (matched against the consumer's `${captured.X.output}` reference).
   - **Trigger**: downstream state's `action` or `evaluate.source` references `${captured.X.output}` AND the producing event for capture `X` shows empty/whitespace output in >20% of occurrences within the analyzed window.
   - **Priority**: P3
   - **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`

2. **Signal 5 — Numeric Trajectory Stall** (Step 3 of SKILL.md): Add `numeric_trajectory` tracking per `output_numeric`/`convergence` evaluator. Read the numeric value directly from the `evaluate` event — `evaluate.value` for `output_numeric` or `evaluate.current` for `convergence` (emitted via `**result.details` splat in `executor.py:_evaluate`).
   - **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has standard deviation < 1% of mean for ≥3 iterations AND the value has not crossed its target threshold (read from `evaluate.target` on the event payload).
   - **Priority**: P3
   - **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`

3. **Fixture: `analysis-capture-vacuum.yaml`** — Signal 4 positive test case. Model after `examples-miner.yaml` structure: a capture chain where upstream state (`harvest`-like) feeds downstream consumer via `${captured.X.output}`. Minimal structural pattern (see `analysis-multi-signal.yaml`, 21 lines): just enough state graph to exhibit the structural property (at least one state with `capture: X`, at least one consumer referencing `${captured.X.output}`).

4. **Fixture: `analysis-numeric-stall.yaml`** — Signal 5 positive test case. Model after `rl-coding-agent.yaml` `score` state: `evaluate.type: convergence`, `previous: "${captured.prev_reward.output}"`. Minimal structural pattern: a state with `evaluate.type: convergence` and a `previous:` field.

5. **Test wiring: `test_analyze_loop_synthesis.py`** — Add new test methods to `TestAnalyzeLoopSynthesis`:
   - Signal 4 test: load `analysis-capture-vacuum.yaml` via `_load_fixture`, assert at least one state has a `capture:` key and at least one consumer state references `${captured.*.output}` in its action.
   - Signal 5 test: load `analysis-numeric-stall.yaml`, assert a state has `evaluate.type: convergence` with a `previous:` field.
   - Follow Style A fixture-backed pattern from `test_3b2_happy_path_reconstruction_multi_signal`.

6. **Guardrail verification**: After all SKILL.md edits, run `scripts/tests/test_enh1146_doc_wiring.py` to confirm `TestAnalyzeLoopSkillWiring.test_rate_limit_waiting_present` and `test_semantic_synthesis_heading_present` still pass (assert `"rate_limit_waiting"` and `"Step 3b"` survive in SKILL.md).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness()` in `scripts/tests/test_analyze_loop_synthesis.py` — extend the `effectiveness_signals` set with `"capture_vacuum"` and `"numeric_stall"` so the taxonomy enumeration stays complete after Signals 4-5 land

## Codebase Research Findings

**Key files**:
- `skills/analyze-loop/SKILL.md` — add Signal 4 and 5 to Step 3
- `scripts/little_loops/fsm/executor.py` — `_run_action` lines 664-683 (`output_preview` in `action_complete`); `_evaluate` lines 844-851 (`**result.details` splat)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_numeric` returns `{"value", "target", "operator"}`; `evaluate_convergence` returns `{"current", "previous", "target", "delta", "direction"}`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.type` enum, `EvaluateConfig.previous`, `EvaluateConfig.target`
- `scripts/tests/test_analyze_loop_synthesis.py` — model new signal tests here
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — fixture format reference (21 lines)
- `scripts/tests/fixtures/fsm/analysis-capture-vacuum.yaml` — create this
- `scripts/tests/fixtures/fsm/analysis-numeric-stall.yaml` — create this

**Fixture models**:
- `scripts/little_loops/loops/examples-miner.yaml` — Signal 4: `harvest` (capture: `harvested_examples`) → `judge` consumer (`${captured.harvested_examples.output}`)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — Signal 5: `score` state (`evaluate.type: convergence`, `previous: "${captured.prev_reward.output}"`, `target: "${context.reward_target}"`)

**Signal 4 empty-output detection**: Read from `action_complete.output_preview` (executor.py:664-674 — last 2000 chars of `result.output`, included in every `action_complete` payload). There is no `capture` event type in the JSONL stream.

**Signal 5 numeric value**: Read directly from `evaluate` event — `evaluate.value` (`output_numeric`) or `evaluate.current` (`convergence`). Do NOT look for a preceding `capture` event (none exists). `evaluate.target` is always present for these evaluator types.

### Refinement Pass 2 — Insertion Site & Cross-Section Wiring

_Added by `/ll:refine-issue` on 2026-05-03 — based on direct reading of `skills/analyze-loop/SKILL.md` after sibling ENH-1335 landed (commit a9ea71e6 added Signals 1-3 plus Fault/Effectiveness grouping)._

**SKILL.md insertion location for Signals 4 and 5**: insert both new `#### ENH —` blocks in `skills/analyze-loop/SKILL.md` between the existing `#### ENH — Degenerate Gate Route Distribution (Signal 2)` block (ends at line 192) and the `#### ENH — Retry flood (true retries only)` block (starts at line 194). This keeps the numbered effectiveness signals (1, 2, 4, 5) contiguous within the `### Signal Rules` bucket while preserving Signal 3's separate "Static Pass" placement at lines 101-119 (Signal 3 is the only static-pass signal — no relocation needed).

**Required `**Class**:` label** — match Signal 2's pattern verbatim:
- Signal 4: `**Class**: Effectiveness signal (history walker).`
- Signal 5: `**Class**: Effectiveness signal (history walker).`

Both are history walkers because they require iterating `action_complete` / `evaluate` events across the run window (not single-event terminal handlers like Signal 1).

**Step 5 enumeration update (additional integration touchpoint, not in original issue)**: `skills/analyze-loop/SKILL.md:360` enumerates the effectiveness bucket inline as: `"stub action..., retry flood, slow state, iter-1 convergence without apply, degenerate gate"`. After adding Signals 4-5, append `, capture vacuum, numeric trajectory stall` to that list so the prose introduction stays in sync with the actual signal set. This is an in-file edit only (no separate test); the guardrail tests in `test_enh1146_doc_wiring.py` do not assert on this prose, but `/ll:audit-docs` and `/ll:ready-issue` will flag the drift if missed.

**Tracking-dict naming convention**: follow Signal 2's `route_distribution: {from_state: {to_state: count}}` style for the prose description of Signals 4 and 5. Suggested wording (mirrors line 188's tracking-dict sentence):
- Signal 4: `"Maintain a capture_emptiness: {capture_name: {empty_count: int, total_count: int}} dict, updated on every action_complete event whose state has capture: X set in the resolved YAML."`
- Signal 5: `"Maintain a numeric_trajectory: {state: [value, value, ...]} dict, appending evaluate.value (output_numeric) or evaluate.current (convergence) on each evaluate event for that state. After the walk, for each state with ≥3 samples, compute stddev/mean and compare against evaluate.target."`

**Sibling-issue boundary**: ENH-1343 owns the `docs/reference/COMMANDS.md` + `README.md:227` updates and `test_enh1268_doc_wiring.py` assertions for the new signal names. This issue (ENH-1342) does **not** touch those files — the Step 6 guardrail check is limited to `test_enh1146_doc_wiring.py` (SKILL.md-only assertions: `rate_limit_waiting` and `Step 3b` heading). Do not run or modify `test_enh1268_doc_wiring.py` from within this issue.

## Tests

- `scripts/tests/test_analyze_loop_synthesis.py` — new Signal 4 and Signal 5 test methods (Style A fixture-backed pattern)
- `scripts/tests/test_enh1146_doc_wiring.py` — guardrail: run after SKILL.md edits; `TestAnalyzeLoopSkillWiring.test_rate_limit_waiting_present` and `test_semantic_synthesis_heading_present` must pass

### Tests (update existing)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_analyze_loop_synthesis.py` — `TestAnalyzeLoopSynthesis.test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness()`: the inline `effectiveness_signals` set currently enumerates Signals 1-3 plus `retry_flood` and `slow_state`; add `"capture_vacuum"` and `"numeric_stall"` to keep the taxonomy complete after Signals 4-5 land [Agent 2 finding]

## Acceptance Criteria

- [x] Signal 4 (Capture Vacuum) implemented in SKILL.md Step 3.
- [x] Signal 5 (Numeric Trajectory Stall) implemented in SKILL.md Step 3.
- [x] `analysis-capture-vacuum.yaml` fixture created (structural property: state with `capture: X`, consumer referencing `${captured.X.output}`).
- [x] `analysis-numeric-stall.yaml` fixture created (structural property: state with `evaluate.type: convergence` and `previous:` field).
- [x] New synthesis test methods pass for both fixtures.
- [x] Guardrail tests (`test_enh1146_doc_wiring.py`) pass after SKILL.md edits.

## Depends On

- ENH-1326 — fragment/inheritance resolution for reliable signal detection.

## Scope Boundaries

- **In scope**: Signals 4-5 in SKILL.md; two fixtures; synthesis test methods; guardrail verification.
- **Out of scope**: COMMANDS.md documentation update (ENH-1343); Signals 1-3 (ENH-1335); `--json` flag; assess-loop integration (FEAT-1325).

## Status

**Completed** | Created: 2026-05-03 | Completed: 2026-05-03 | Priority: P3

## Resolution

Implemented Signals 4 (Capture Vacuum) and 5 (Numeric Trajectory Stall) in `skills/analyze-loop/SKILL.md` Step 3, inserted between Signal 2 and Retry flood blocks. Both follow Signal 2's `**Class**: Effectiveness signal (history walker).` pattern. Updated Step 5's effectiveness enumeration prose to mention `capture vacuum, numeric trajectory stall`.

Created two minimal positive-case fixtures:
- `scripts/tests/fixtures/fsm/analysis-capture-vacuum.yaml` — `harvest` (capture: harvested_examples) → `judge` (consumes `${captured.harvested_examples.output}`)
- `scripts/tests/fixtures/fsm/analysis-numeric-stall.yaml` — `score` state with `evaluate.type: convergence`, `previous: "${captured.prev_reward.output}"`, target 0.85

Added 8 new test methods to `TestAnalyzeLoopSynthesis`: 3 fixture-backed for Signal 4 (producer/consumer/reference-match) and 5 for Signal 5 (convergence evaluator/previous/target plus 3 inline trigger arithmetic checks). Extended `test_step5_fault_effectiveness_grouping_assigns_signal3_to_effectiveness` to include `capture_vacuum` and `numeric_stall` in the effectiveness taxonomy.

All 56 tests pass (44 synthesis + 12 doc-wiring guardrail). Lint clean. Two unrelated pre-existing failures in `test_update_skill.py::TestMarketplaceVersionSync` (marketplace.json 1.92.1 vs plugin.json 1.93.0 — owned by `/ll:publish`).

## Session Log
- `/ll:ready-issue` - 2026-05-03T05:09:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8926186-cf89-43f9-8317-8ce90b252bfa.jsonl`
- `/ll:confidence-check` - 2026-05-03T05:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6517b85c-1988-43ec-a3a4-9ee94e4df566.jsonl`
- `/ll:wire-issue` - 2026-05-03T05:06:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9eec30ec-fd21-4b25-85fb-9c7ce42f32aa.jsonl`
- `/ll:refine-issue` - 2026-05-03T05:00:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e6daf8-43ea-4030-aade-5ecde0a9db23.jsonl`
- `/ll:issue-size-review` - 2026-05-03T04:56:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8af1a3a1-23af-4c82-98e3-c5e3dde0272f.jsonl`
- `/ll:manage-issue` - 2026-05-03T05:14:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2eab1476-28be-4970-aae9-e6a5a6e625d7.jsonl`
