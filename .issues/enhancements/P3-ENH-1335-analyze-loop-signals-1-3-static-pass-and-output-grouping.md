---
id: ENH-1335
type: ENH
priority: P3
parent_issue: ENH-1327
---

# ENH-1335: Add Effectiveness Signals 1-3 + Static Pass + Output Grouping to `/ll:analyze-loop`

## Summary

Implement three of the five new deterministic effectiveness signals in `/ll:analyze-loop` Step 3, plus the static analysis pass (Signal 3 at config-load time), and the Step 5 output grouping that separates `Fault Signals` from `Effectiveness Signals`.

## Parent Issue

Decomposed from ENH-1327: Add Deterministic Effectiveness Signals to `/ll:analyze-loop`

## Proposed Signals to Implement

### Signal 3: Stub Action Detection (static pass — Step 2)

- **Trigger**: a state's `action` body matches one of:
  - `^echo "\d+"$` in a state whose name contains `score`, `evaluate`, `judge`, `reward`
  - `^echo "Replace.*"$` or `^echo "TODO.*"$` in any state
  - `^echo "[A-Z_]+"$` (literal verdict echo) in a state whose `evaluate.type` is `output_string`
- **Priority**: P2
- **Title**: `"<state> action is a stub (<echo body>) — loop ships unimplemented"`
- **Implementation**: static check at Step 2 (config-time), results emitted into a `static_issues` list separate from the history-driven `signals` list

### Signal 2: Degenerate Gate (event-history walker)

- **Trigger**: an `evaluate` state's `route` event distribution shows >95% to a single branch across ≥10 evaluations within the same run, OR ≥20 evaluations across the most recent 5 runs.
- **Priority**: P3
- **Title**: `"<state> route fan-out is degenerate (<N>/<M> evaluations took <branch>)"`

### Signal 1: Iteration-1 Convergence with No Apply (terminal-event handler)

- **Trigger**: loop terminated with `iteration_count == 1` AND a state matching the apply/refine pattern (`apply_*`, `refine_*`, `update_*`, `write_*`, `commit_*`) was never visited.
- **Priority**: P3
- **Title**: `"<loop_name> converged on iteration 1 without entering apply/refine state — likely phantom convergence"`

## Implementation Steps

1. **Signal 3 static pass** (Step 2): Insert stub-action scan immediately after `ll-loop show <loop_name> --resolved --json` parse block, before event history is loaded. Iterate the resolved state map; apply the three regex patterns against each state's `action` body; emit Signal 3 items into a `static_issues` list separate from the history-driven `signals` list.

2. **Signal 2 accumulator** (Step 3): Declare a `route_distribution: {state_name: {branch: count}}` dict at the start of the event history walk. Update it on every `route` event. Evaluate the degenerate-gate threshold after the walk completes (or inline when per-state count ≥ 10).

3. **Signal 1 check** (terminal-event handler): Add `apply_state_visit` tracking; emit Signal 1 when `iteration_count == 1` and no apply/refine/update/write/commit state was visited.

4. **Step 5 output grouping**: Replace the flat numbered signal list with two labelled groups: `Fault Signals (N):` and `Effectiveness Signals (M):`. Signal 3 results (from the Step 2 static pass) appear in the Effectiveness Signals group alongside the history-driven signals.

5. **Fixture**: Create `scripts/tests/fixtures/fsm/analysis-stub-action.yaml` — Signal 3 positive test case (stub action in a scoring state, e.g. `echo "5"` in a state named `score`); follow `analysis-multi-signal.yaml` naming/structure convention.

6. **Verify** `scripts/tests/test_enh1146_doc_wiring.py` — `TestAnalyzeLoopSkillWiring.test_semantic_synthesis_heading_present` asserts `"Step 3b"` exists in SKILL.md; confirm this heading is preserved when the Step 2 static analysis pass is inserted (step numbering must not shift it away).

## Codebase Research Findings (from ENH-1327)

**SKILL.md section anchors**:
- Insert static pass immediately after the `ll-loop show <loop_name> --resolved --json` parse block in `## Step 2`
- Declare `route_distribution` dict at start of event history walk in `## Step 3`
- Read numeric values from `capture` event emitted immediately before `evaluate` event for the same state

**Key files**:
- `skills/analyze-loop/SKILL.md` — primary modification target (Steps 2, 3, 5)
- `scripts/little_loops/events.py` — `LLEvent` dataclass reference
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` dataclass with `type` enum; `StateConfig.action` field for regex matching
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` produces resolved state map
- `scripts/little_loops/loops/apo-textgrad.yaml` — `route_convergence` routes `on_yes: done` bypassing `apply_gradient`; primary Signal 1 test case
- `scripts/little_loops/loops/rl-rlhf.yaml` — `score.action: echo "5"` and `generate.action: echo "Replace this with..."` stubs; primary Signal 3 test case
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_outcome` routing; Signal 2 test case candidate

**Test files**:
- `scripts/tests/test_analyze_loop_synthesis.py` — model new signal tests after this structure
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — adapt for Signal 1 synthetic test
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — adapt for Signal 2 synthetic test
- `scripts/tests/fixtures/fsm/analysis-multi-signal.yaml` — follow naming convention for new fixture

## Acceptance Criteria

- [ ] Signal 3 (Stub Action) implemented as static pass at Step 2; `rl-rlhf` loop's `echo "5"` triggers it at config-load time.
- [ ] Signal 2 (Degenerate Gate) implemented in event-history walker; 10/10 evaluate routes to one branch emits the signal.
- [ ] Signal 1 (Iter-1 Convergence) implemented in terminal-event handler; `apo-textgrad` run converging iter 1 emits the signal.
- [ ] Step 5 output uses `Fault Signals (N):` / `Effectiveness Signals (M):` two-group layout.
- [ ] `analysis-stub-action.yaml` fixture created and passing.
- [ ] `test_enh1146_doc_wiring.py` still passes (`Step 3b` heading preserved).
- [ ] No false positives on healthy runs of `dataset-curation` and `sprint-build-and-validate`.

## Depends On

- ENH-1326 — fragment/inheritance resolution needed for reliable stub-action and signal detection on YAML with fragments.

## Scope Boundaries

- **In scope**: Signals 1, 2, 3 in `skills/analyze-loop/SKILL.md`; Step 5 output grouping; `analysis-stub-action.yaml` fixture; SKILL.md test verification.
- **Out of scope**: Signals 4, 5 (Capture Vacuum, Numeric Stall — see ENH-1336); COMMANDS.md update (ENH-1336); `--json` flag with structured output (deferred per confidence check notes in parent).

## Session Log
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17077eeb-0a80-4927-8736-7cffe26a726a.jsonl`
