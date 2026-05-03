---
id: ENH-1335
type: ENH
priority: P3
parent_issue: ENH-1327
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-05-03T04:57:18Z
---

# ENH-1335: Add Effectiveness Signals 1-3 + Static Pass + Output Grouping to `/ll:analyze-loop`

## Summary

Implement three of the five new deterministic effectiveness signals in `/ll:analyze-loop` Step 3, plus the static analysis pass (Signal 3 at config-load time), and the Step 5 output grouping that separates `Fault Signals` from `Effectiveness Signals`.

## Parent Issue

Decomposed from ENH-1327: Add Deterministic Effectiveness Signals to `/ll:analyze-loop`

## Current Behavior

`/ll:analyze-loop` Step 3 emits only fault signals (BUG-class anomalies). It does not detect three known effectiveness pathologies that show up in current loop YAMLs and runs:

- Stub `action` bodies (e.g., `score.action: echo "5"` in `rl-rlhf.yaml`) ship as if implemented but are inert.
- Iteration-1 termination that bypasses the apply/refine state (e.g., `apo-textgrad`'s `route_convergence` taking `on_yes: done`) — phantom convergence.
- Degenerate route fan-out where an `evaluate` state always takes the same branch (e.g., `refine-to-ready-issue.yaml`'s `check_outcome`) — gate adds no signal.

Step 5 also presents all signals as a single flat numbered list with no separation between fault and effectiveness classes.

## Expected Behavior

- Signal 3 (Stub Action) emits at config-load time via a Step 2 static pass over the resolved state map, populating a separate `static_issues` list.
- Signal 2 (Degenerate Gate) emits from a Step 3 event-history walker maintaining a `{from_state: {to_state: count}}` route distribution.
- Signal 1 (Iter-1 Convergence) emits from the terminal-event handler when `iterations == 1` and no apply/refine/update/write/commit state was visited.
- Step 5 renders two markdown-heading groups: `### Fault Signals (N)` and `### Effectiveness Signals (M)`, omitting either when count is zero.
- Existing doc-wiring tests (`Step 3b` heading, `rate_limit_waiting` row) continue to pass.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Create `scripts/tests/fixtures/fsm/analysis-iter1-no-apply.yaml` — Signal 1 positive-case fixture; structure: evaluate state whose `on_yes: done` and no `apply_*`/`refine_*`/`update_*`/`write_*`/`commit_*` state in the state map; follow `analysis-multi-signal.yaml` shape (no `context:` block, explicit `on_yes`/`on_no`/`on_error`)
8. Create `scripts/tests/fixtures/fsm/analysis-degenerate-gate.yaml` — Signal 2 structural fixture; evaluate state with `on_no: <same_state>` (self-loop showing >95% route fan-out to one branch); follow `analysis-multi-signal.yaml` shape
9. Add test blocks in `scripts/tests/test_analyze_loop_synthesis.py` for Signals 1 and 2 structural assertions (happy-path and field-value checks following `test_3b2_happy_path_reconstruction_multi_signal` and `test_3b4_fixture_has_prompt_then_shell_adjacency` patterns); add `APPLY_STATE_PREFIXES = ("apply_", "refine_", "update_", "write_", "commit_")` constant at module level parallel to existing `DECISION_PREFIXES`
10. Add `test_fault_signals_heading_present` and `test_effectiveness_signals_heading_present` to `TestAnalyzeLoopSkillWiring` in `scripts/tests/test_enh1146_doc_wiring.py` asserting these new Step 5 heading strings appear in `skills/analyze-loop/SKILL.md` after the output grouping change
11. Update `skills/assess-loop/SKILL.md` `## Step 5: Phase 1 — Fault Signals` cross-reference (currently "same classification as `/ll:analyze-loop` Step 3`"): clarify that assess-loop inherits only the *fault-signal subset* of analyze-loop Step 3; after ENH-1335 Step 3 also contains effectiveness signals (Signals 1–2) which are out of scope for assess-loop Phase 1

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

## Codebase Research Findings (refine-issue verification pass — 2026-05-02)

_Added by `/ll:refine-issue` — verified against current SKILL.md and surrounding files; corrects/extends parent ENH-1327 findings._

### Splice Points in `skills/analyze-loop/SKILL.md`

| Target | Anchor | Notes |
|---|---|---|
| Signal 3 static pass | End of `## Step 2: Load Event History and Loop Config` (~line 99), **after** the paragraph "Sub-loop states do not contribute to parent loop event counts." and **before** the `**Parse the events**` table (~line 101) | Insert here so `static_issues` are populated before history walking begins |
| Signal 1 (iter-1 convergence) | New `####` block inside `### Signal Rules` in `## Step 3`, immediately after `#### BUG — FATAL_ERROR termination` | Co-locates with the other terminal/`loop_complete`-driven rules |
| Signal 2 (degenerate gate) | New `####` block inside `### Signal Rules` (history-driven, alongside `#### BUG — Evaluate failure`) | Walks `route` events; uses the same "most recent `state_enter.state`" grouping convention already documented in the Step 3 preamble |
| Step 5 output grouping | Replaces the flat numbered list at `## Step 5: Present Proposals and Confirm` (~lines 314–325; preamble `Found <M> issue signal(s):`) | See "Output convention" below |

### Field-Name Corrections

- **`iterations`, not `iteration_count`** — the `loop_complete` event payload exposes `iterations` (int), per the event-payload table in Step 2 of `skills/analyze-loop/SKILL.md` and `LLEvent` in `scripts/little_loops/events.py`. Treat the issue's `iteration_count == 1` trigger phrasing as shorthand for `iterations == 1`.
- **`route.to` is the branch field** — `route` events carry `from` (origin state) and `to` (destination), per `_format_history_event()` in `scripts/little_loops/cli/loop/info.py:~319`. Signal 2's "branch distribution" should be a `{from_state: {to_state: count}}` dict.

### State-Prefix Convention (Apply/Refine States)

There is **no existing apply-state prefix list** in the codebase. The closest precedents:

- `DECISION_PREFIXES = ("check_", "verify_", "evaluate_", "wait_")` — `scripts/tests/test_analyze_loop_synthesis.py:16` (used by 3b-5 dominant-state detection)
- `GATE_STATE_PREFIXES = ("check_", "verify_", "validate_")` — `scripts/tests/test_review_loop.py:756`

For Signal 1, define a parallel `APPLY_STATE_PREFIXES = ("apply_", "refine_", "update_", "write_", "commit_")` symmetric tuple (in the SKILL.md prose, since matching is performed by the LLM in-context, not by Python code). Document it adjacent to the existing prefix lists' style.

### Static-Pass Precedent

The only existing config-based signal in `analyze-loop` is `#### BUG — Sub-loop verdict discarded` (~SKILL.md lines 182–186), which inspects `state.on_yes == state.on_no` against the resolved state map. Today it lives in the same `### Signal Rules` bucket as history-driven rules. **Decision needed at implementation time** (low-stakes; not blocking refinement): does Signal 3 introduction motivate moving the sub-loop verdict signal into the new `static_issues` bucket too, or leave it where it is for backward compatibility? Default: leave it; let `static_issues` be the new bucket and document that pre-existing config-signal stays inline. Either way, Step 5's "Effectiveness Signals" group should include both static and history-driven effectiveness signals.

The closest existing example of regex applied against `state.action` bodies is `_collect_action_text()` + `re.search()` in `scripts/tests/test_builtin_loops.py:~303–326`. Same shape: iterate `data["states"].values()`, read each `state["action"]` string, regex-match. Reference this when writing the SKILL.md prose for the static pass.

### Output Convention (Step 5 grouping)

Project convention for labelled output groups uses **markdown headings**, not bare-colon lines:

- `skills/review-loop/reference.md:505–535` → `### Errors (N)` / `### Warnings (N)` / `### Suggestions (N)` (omit a section if N == 0)
- `skills/audit-docs/templates.md:170–179` → `### Critical (Must Fix)` / `### Warnings (Should Fix)` / `### Suggestions`

Recommend rendering as:

```
### Fault Signals (N)
  [1] BUG P2 — <title>
  ...

### Effectiveness Signals (M)
  [1] ENH P3 — <title>
  ...
```

(omit either section when its count is 0). The issue's `Fault Signals (N):` colon-form is acceptable but inconsistent with the project's other multi-bucket renderings.

### Doc-Wiring Test Caveat

`scripts/tests/test_enh1146_doc_wiring.py::TestAnalyzeLoopSkillWiring` asserts **two** literal substrings against `skills/analyze-loop/SKILL.md`:

1. `"rate_limit_waiting"` (`test_rate_limit_waiting_present`) — must be preserved in the Step 2 event-payload table.
2. `"Step 3b"` (`test_semantic_synthesis_heading_present`) — must remain present.

The issue's Acceptance Criteria mentions only `Step 3b`. Add `rate_limit_waiting` to the verification — the Step 2 static-pass insertion is adjacent to that table and an accidental edit could remove the row.

### Implementation Locus Clarification

All three signals are implemented as **prose directives in `skills/analyze-loop/SKILL.md`** for an LLM to execute at runtime — no new Python code is added under `scripts/little_loops/`. Existing `analyze-loop` signals follow this same in-context pattern (the Step 3 preamble even explicitly instructs "Group events by `state` (use the most recent `state_enter.state`...)" as natural-language guidance). The fixture in `scripts/tests/fixtures/fsm/analysis-stub-action.yaml` and any new test methods in `scripts/tests/test_analyze_loop_synthesis.py` are pure structural YAML assertions (no LLM/subprocess invocation) — see `test_3b4_fixture_has_prompt_then_shell_adjacency` for the canonical shape.

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

## Integration Map

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `skills/assess-loop/SKILL.md` — `## Step 5: Phase 1 — Fault Signals` cross-reference to "same classification as `/ll:analyze-loop` Step 3`" becomes incomplete after ENH-1335 adds effectiveness signals to Step 3; scope must be narrowed to fault-signal subset [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/fsm/analysis-iter1-no-apply.yaml` — **new** Signal 1 positive-case fixture (no apply/refine state in state map, evaluate exits `on_yes: done` on first iteration) [Agent 3 finding]
- `scripts/tests/fixtures/fsm/analysis-degenerate-gate.yaml` — **new** Signal 2 structural fixture (`on_no: <self>` evaluate state showing degenerate single-branch route fan-out) [Agent 3 finding]
- `scripts/tests/test_analyze_loop_synthesis.py` — add Signal 1 and Signal 2 test blocks + `APPLY_STATE_PREFIXES` module-level constant; follow `test_3b2_*` and `test_3b4_*` patterns [Agent 3 finding]
- `scripts/tests/test_enh1146_doc_wiring.py::TestAnalyzeLoopSkillWiring` — existing, **update**: add `test_fault_signals_heading_present` and `test_effectiveness_signals_heading_present` for new Step 5 heading strings; **re-verify** `test_rate_limit_waiting_present` (Step 2 table adjacent to static-pass insertion) and `test_semantic_synthesis_heading_present` (`"Step 3b"` must not be renumbered) still pass after SKILL.md edits [Agents 2 & 3 finding]

## Impact

- **Priority**: P3 — quality improvement to existing `/ll:analyze-loop` skill; not blocking other work but unlocks better diagnosis of loops that "complete" without doing useful work.
- **Effort**: Medium — three signals across two SKILL.md sections plus Step 5 grouping, three fixture YAMLs, and test updates in two files; all signals follow existing prose-directive pattern (no new Python).
- **Risk**: Low/Medium — splice points sit adjacent to assertions in `test_enh1146_doc_wiring.py` (`Step 3b`, `rate_limit_waiting`); careful editing required but no API surface changes.
- **Breaking Change**: No — additive signal emission and output grouping only.

## Labels

`enhancement`, `analyze-loop`, `effectiveness-signals`, `decomposed-from-ENH-1327`, `wired`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Splice-point discipline required**: The Signal 3 static-pass insertion in Step 2 sits adjacent to the `rate_limit_waiting` event-payload table row and the `Step 3b` heading — both are asserted by `test_enh1146_doc_wiring.py`. Edit carefully at lines ~99–101 to avoid displacing either.
- **One low-stakes design call remains open**: whether to migrate the existing sub-loop verdict signal into the new `static_issues` bucket alongside Signal 3. Stated default is to leave it in place; resolve this at the Step 2 insertion point without further research.
- **7-file spread increases coordination cost**: SKILL.md edits drive two separate test files and three fixture YAMLs; work the acceptance criteria checklist in order (Signal 3 static pass first, then Signals 1 and 2, then Step 5 grouping) to keep changes coherent.

## Resolution

Implemented Signals 1, 2, 3 as prose directives in `skills/analyze-loop/SKILL.md` and added Step 5 Fault/Effectiveness output grouping. Signal 3 (Stub Action) is a static pass at Step 2 that scans the resolved state map for stub-action regex patterns; results land in a `static_issues` list that is merged with history-driven signals under the Effectiveness heading in Step 5. Signal 1 (Iter-1 Convergence) fires from the terminal handler when `iterations == 1` and no `apply_/refine_/update_/write_/commit_` state was visited. Signal 2 (Degenerate Gate) walks `route` events accumulating a `{from_state: {to_state: count}}` distribution and flags evaluate states whose dominant branch exceeds 95% over ≥10 evaluations. `skills/assess-loop/SKILL.md` Step 5 cross-reference was clarified to point only at the fault-signal subset of analyze-loop Step 3. Three new YAML fixtures were created (`analysis-stub-action.yaml`, `analysis-iter1-no-apply.yaml`, `analysis-degenerate-gate.yaml`) and 16 structural tests were added in `test_analyze_loop_synthesis.py` plus 2 doc-wiring tests in `test_enh1146_doc_wiring.py` for the new Step 5 headings. The `Step 3b` and `rate_limit_waiting` doc-wiring guards continue to pass.

## Status

**Completed** | Created: 2026-05-02 | Completed: 2026-05-03 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-05-03T04:57:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8af1a3a1-23af-4c82-98e3-c5e3dde0272f.jsonl`
- `/ll:ready-issue` - 2026-05-03T04:44:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4217de01-e6a0-4956-b983-ddbac6e33cd5.jsonl`
- `/ll:wire-issue` - 2026-05-03T04:36:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae2d04cb-8b7e-427b-8b4d-eb46dd7e7963.jsonl`
- `/ll:refine-issue` - 2026-05-03T04:30:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72d1a6da-5f0e-44c1-99c9-d038fb2c92e5.jsonl`
- `/ll:issue-size-review` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17077eeb-0a80-4927-8736-7cffe26a726a.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae2d04cb-8b7e-427b-8b4d-eb46dd7e7963.jsonl`
