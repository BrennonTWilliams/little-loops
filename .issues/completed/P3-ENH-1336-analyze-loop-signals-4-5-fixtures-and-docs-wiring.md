---
id: ENH-1336
type: ENH
priority: P3

confidence_score: 88
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
size: Very Large
parent: ENH-1327
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

1. **Signal 4 — Capture Vacuum** (Step 3): Add `capture_emptiness` tracking keyed by capture name; emit Signal 4 at end of event-history walk. ⚠️ See "Refined Codebase Research Findings → CORRECTION 1" below: there is no `capture` event in the JSONL stream. Read emptiness from `action_complete.output_preview` for the state whose resolved YAML has `capture: X` (matched against the consumer's `${captured.X.output}` reference).

2. **Signal 5 — Numeric Trajectory Stall** (Step 3): Add `numeric_trajectory` tracking per `output_numeric`/`convergence` evaluator. ⚠️ See "Refined Codebase Research Findings → CORRECTION 2" below: the numeric value **is** in the `evaluate` event (`evaluate.value` for `output_numeric`, `evaluate.current` for `convergence`) — no preceding capture lookup needed. The state's `evaluate.target` is also on the event payload; `evaluate.type` is on the event and on the resolved YAML state map.

3. **Fixture: `analysis-capture-vacuum.yaml`** — Signal 4 positive test case (capture chain with empty-output scenario); model after `examples-miner.yaml` structure (7-state `calibrated_corpus` capture chain).

4. **Fixture: `analysis-numeric-stall.yaml`** — Signal 5 positive test case (`convergence` evaluator with stalled `previous` reference); model after `rl-coding-agent.yaml` `score` state with `previous: "${captured.prev_reward.output}"`.

5. **COMMANDS.md update** (`docs/reference/COMMANDS.md`): Add 5 new signal descriptions to the "Signal detection rules:" list; update "Output format:" block to show `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout; update Quick Reference table entry to reflect effectiveness coverage (not "failure signals" only).

6. **Test wiring: `test_enh1268_doc_wiring.py`** (`scripts/tests/test_enh1268_doc_wiring.py`): Update `TestAnalyzeLoopCommandsWiring` tests to assert `"Fault Signals"` and `"Effectiveness Signals"` grouping strings in COMMANDS.md after the Step 5 update; the existing 6 string-presence tests must remain passing.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add new test methods to `scripts/tests/test_analyze_loop_synthesis.py` — for Signal 4: load `analysis-capture-vacuum.yaml` via `TestAnalyzeLoopSynthesis._load_fixture`, assert at least one state has a `capture:` key and at least one consumer state references `${captured.*.output}` in its action; for Signal 5: load `analysis-numeric-stall.yaml`, assert a state has `evaluate.type: convergence` with a `previous:` field; follow Style A fixture-backed pattern from `test_3b2_happy_path_reconstruction_multi_signal`
8. Run `scripts/tests/test_enh1146_doc_wiring.py` after SKILL.md and COMMANDS.md edits to confirm `TestAnalyzeLoopSkillWiring.test_rate_limit_waiting_present`, `test_semantic_synthesis_heading_present`, and `TestCommandsWiring.test_rate_limit_waiting_present` all pass — these are guardrail tests that must not break
9. Update `README.md` line 227 (`analyze-loop`^ row "from failures") to match the updated Quick Reference language in COMMANDS.md

## Codebase Research Findings (from ENH-1327)

**Key files**:
- `skills/analyze-loop/SKILL.md` — add Signal 4 and 5 to Step 3
- `scripts/little_loops/events.py` — `LLEvent` dataclass; `capture` events carry `{name: str, output: str}` — Signal 4 reads `capture.output`
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.type` enum (`output_numeric`, `convergence`); `evaluate.target` threshold
- `docs/reference/COMMANDS.md` — add 5 signal entries + update output format block
- `scripts/tests/test_enh1268_doc_wiring.py` — `TestAnalyzeLoopCommandsWiring` 6 existing string-presence tests

### Refined Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-05-02 — based on direct reading of `executor.py`, `evaluators.py`, `events.py`, and `schema.py`. **Corrects factual errors in the Implementation Steps and parent-issue findings above.**_

**CORRECTION 1 — There is no `capture` event in the JSONL stream.**
- `scripts/little_loops/fsm/executor.py:_run_action` lines 676-683 — captures are stored in the in-memory dict `self.captured[state.capture] = {"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ...}` immediately after `_emit("action_complete", ...)`. There is **no** corresponding `_emit("capture", ...)` call anywhere in the executor.
- The full vocabulary of emitted event types is: `loop_start`, `state_enter`, `action_start`, `action_output`, `action_complete`, `action_error`, `evaluate`, `route`, `retry_exhausted`, `rate_limit_waiting`, `rate_limit_exhausted`, `api_error_exhausted`, `loop_complete`. No `capture` type exists.
- **Implication for Signal 4**: emptiness must be read from `action_complete.output_preview` (executor.py:664-674 — last 2000 chars of `result.output`, included in every `action_complete` payload). The state being checked is identified by matching the resolved YAML `state.capture: X` field against the consumer state's `${captured.X.output}` reference in its `action:` text.
- **Alternative**: stream `action_output` events (which carry per-line stdout) and aggregate per state-iteration. `output_preview` is simpler and sufficient for >20% emptiness threshold detection.

**CORRECTION 2 — The numeric value IS in the `evaluate` event payload (Signal 5).**
- `scripts/little_loops/fsm/executor.py:_evaluate` lines 844-851 — emits `{"type": <type>, "verdict": <verdict>, **result.details}`. The `**result.details` splat exposes the evaluator's full detail dict directly on the event.
- `scripts/little_loops/fsm/evaluators.py:evaluate_output_numeric` returns `details = {"value": <float>, "target": <float>, "operator": <str>}`.
- `scripts/little_loops/fsm/evaluators.py:evaluate_convergence` returns `details = {"current": <float>, "previous": <float|None>, "target": <float>, "delta": <float|None>, "direction": <str>}`.
- **Implication for Signal 5**: read the numeric value directly from the `evaluate` event — `evaluate.value` for `output_numeric` or `evaluate.current` for `convergence`. **Do not** look for a preceding `capture` event (none exists). The `previous` value is also already on the `convergence` evaluate event for free.

**CORRECTION 3 — `EvaluateConfig.previous` is a top-level field on the resolved YAML state, not an event field.**
- `scripts/little_loops/fsm/schema.py:EvaluateConfig` — `previous: str | None = None` is a top-level field. In YAML it appears as a template string like `previous: "${captured.prev_reward.output}"` and is interpolated at evaluation time (`evaluators.py:801-809`).
- The interpolated float result is what ends up on the `evaluate` event's `previous` detail. Signal 5's stall detection should track the per-iteration `current` values (already present in the event); the YAML `previous:` configuration is only relevant for confirming a state uses `convergence`-style stall semantics.

**CORRECTION 4 — `EvaluateConfig.target` is a top-level optional field, may be a template string.**
- `scripts/little_loops/fsm/schema.py:EvaluateConfig` — `target: int | float | str | None = None`. Interpolated at runtime (e.g., `target: "${context.reward_target}"` in `rl-coding-agent.yaml`).
- For Signal 5's "has not crossed its target threshold" check, prefer reading the resolved `target` from the `evaluate` event payload (always present for `output_numeric` and `convergence`) rather than re-resolving from the YAML state map.

**CONFIRMED — `examples-miner.yaml` capture chain (Signal 4 fixture model)**:
- `harvest` (line 30, `action_type: shell`, `capture: harvested_examples`) → consumed by `judge` via `${captured.harvested_examples.output}` (line 42).
- `judge` (`action_type: prompt`, `capture: judge_scores`) → consumed by `calibrate` via `${captured.judge_scores.output}` (line 101).
- `calibrate` produces `calibrated_corpus`, fanned out to 6 downstream consumers.
- `harvest` is the canonical empty-output testable case: the `ll-messages ... --since` shell command emits no output when no new sessions exist, producing an empty `harvested_examples` capture.

**CONFIRMED — `rl-coding-agent.yaml` `score` state (Signal 5 fixture model)**:
- `score` state lines 95-110: `evaluate.type: convergence`, `target: "${context.reward_target}"` (resolves to `0.85`), `tolerance: 0.05`, `previous: "${captured.prev_reward.output}"`, `direction: maximize`.
- Stall scenario: `score` produces the same numeric value (e.g., 0.6) for ≥3 consecutive iterations; `convergence` evaluator returns verdict `"continue"` (within tolerance, below target) → routes via `stall: act` → re-runs without progress. Signal 5 detects this by computing stddev of the `current` values from successive `evaluate` events with `type: convergence` for the same state.

**CONFIRMED — Fixture format and naming**:
- Existing fixtures in `scripts/tests/fixtures/fsm/analysis-*.yaml` are loop YAMLs (not synthetic event streams). Tests in `scripts/tests/test_analyze_loop_synthesis.py` load them with `yaml.safe_load()` and walk the state graph structurally — they do not run the loop or replay events.
- New fixtures `analysis-capture-vacuum.yaml` and `analysis-numeric-stall.yaml` should follow this minimal structural pattern (see `analysis-multi-signal.yaml`, 21 lines): just enough state graph to exhibit the structural property under test.
- **Implication**: Signal 4 and 5 detection logic in SKILL.md operates on actual event-history JSONL (not these fixtures). The fixtures are graph-validation inputs for synthesis tests, not signal-detection inputs. If signal-detection unit tests need event streams, those would be inline JSONL strings in the test file (no precedent yet for this kind of fixture).

**CONFIRMED — `TestAnalyzeLoopCommandsWiring` slicing helper**:
- `scripts/tests/test_enh1268_doc_wiring.py:_analyze_loop_section` — slices COMMANDS.md from `"### \`/ll:analyze-loop\`"` to the next `"\n### \`"` heading. New `"Fault Signals"` / `"Effectiveness Signals"` strings must appear within that range. The 6 existing assertions are all simple `assert "<string>" in section`.

**Updated Integration Map**:

| Concern | File | Anchor |
|---|---|---|
| Signal 4 detection — Step 3 | `skills/analyze-loop/SKILL.md` | Step 3 ("Classify Issue Signals") |
| Signal 4 emptiness source | `scripts/little_loops/fsm/executor.py` | `_run_action` lines 664-674 (`output_preview`) |
| Signal 5 detection — Step 3 | `skills/analyze-loop/SKILL.md` | Step 3 |
| Signal 5 numeric value source | `scripts/little_loops/fsm/executor.py` | `_evaluate` lines 844-851 (event `**details` splat) |
| Numeric value details schema | `scripts/little_loops/fsm/evaluators.py` | `evaluate_output_numeric`, `evaluate_convergence` returns |
| Resolved YAML state map | `skills/analyze-loop/SKILL.md` | Step 2 (`ll-loop show <loop> --resolved --json`) |
| Signal 4 fixture pattern | `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` | full file (21 lines) |
| Signal 5 fixture pattern | `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` | full file (21 lines) |
| Doc wiring test class | `scripts/tests/test_enh1268_doc_wiring.py` | `TestAnalyzeLoopCommandsWiring._analyze_loop_section` |
| COMMANDS.md target section | `docs/reference/COMMANDS.md` | `### \`/ll:analyze-loop\`` (lines 529-578) |
| Quick Reference table entry | `docs/reference/COMMANDS.md` | line 746 (current text: "failure signals") |

**Loop YAML sources**:
- `scripts/little_loops/loops/examples-miner.yaml` — primary Signal 4 test case (harvest → judge → calibrate chain)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — primary Signal 5 test case (`score` state with `convergence` evaluator, `previous: "${captured.prev_reward.output}"`)
- `scripts/little_loops/loops/apo-beam.yaml` — Signal 5 test case (best-score plateaued below `target_score`)
- `scripts/little_loops/loops/dataset-curation.yaml` — include in false-positive test suite (no signals expected)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — include in false-positive suite; note: triggers pre-existing "Sub-loop verdict discarded" fault signal (`refine_unresolved` routes all branches to `done`) — scope false-positive checks to Signals 1-5 only

**Test files**:
- `scripts/tests/test_analyze_loop_synthesis.py` — model new signal tests after this structure
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — multi-fault-signal fixture; naming convention reference

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1146_doc_wiring.py` — guardrail: `TestAnalyzeLoopSkillWiring.test_rate_limit_waiting_present` and `test_semantic_synthesis_heading_present` assert `"rate_limit_waiting"` and `"Step 3b"` survive in SKILL.md; `TestCommandsWiring.test_rate_limit_waiting_present` asserts `"rate_limit_waiting"` survives in COMMANDS.md — run after all edits to verify no regressions [Agent 2 / Agent 3 finding]
- `scripts/tests/test_analyze_loop_synthesis.py` — new test methods needed: for Signal 4, load `analysis-capture-vacuum.yaml` via `_load_fixture` and assert at least one state has a `capture:` key whose consumer references `${captured.X.output}`; for Signal 5, load `analysis-numeric-stall.yaml` and assert a state has `evaluate.type: convergence` with `previous:` field; follow `TestAnalyzeLoopSynthesis` Style A fixture-backed pattern (not inline dict) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — line 227, commands table: `analyze-loop`^ row contains "from failures" — parallels the stale Quick Reference "failure signals" language; update to match whatever language replaces "failure signals" in COMMANDS.md Quick Reference table [Agent 2 finding]

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- **ENH-1335 COMMANDS.md not yet applied**: ENH-1335's SKILL.md changes (Signals 1-3, output grouping) are in place, but its COMMANDS.md step is unfinished. Steps 5-6 of this issue (COMMANDS.md signal descriptions + test_enh1268_doc_wiring.py assertions) must wait for ENH-1335 to land its COMMANDS.md changes first. Steps 1-4 (SKILL.md + fixtures) can proceed immediately.

### Outcome Risk Factors
- **SKILL.md signal detection is untestable programmatically**: Signals 4-5 live in AI-interpreted markdown instructions. End-to-end signal firing can only be confirmed manually or via a live loop run — plan to hand-test with examples-miner and rl-coding-agent before marking complete.
- **Step ordering constraint**: implement steps 1-4 (SKILL.md + fixtures) first; gate steps 5-6 on ENH-1335's COMMANDS.md landing.

## Session Log
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:wire-issue` - 2026-05-03T04:51:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ffb837c-fbed-4b17-979a-21f952936d58.jsonl`
- `/ll:refine-issue` - 2026-05-03T04:46:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f1a3aae-d4f5-418e-925c-2341954b5c96.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17077eeb-0a80-4927-8736-7cffe26a726a.jsonl`
- `/ll:issue-size-review` - 2026-05-03T04:56:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8af1a3a1-23af-4c82-98e3-c5e3dde0272f.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-03
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1342: Implement Signals 4-5 in `/ll:analyze-loop` SKILL.md, Fixtures, and Synthesis Tests
- ENH-1343: Documentation Wiring for All 5 Signals in `/ll:analyze-loop` (COMMANDS.md, Tests, README)
