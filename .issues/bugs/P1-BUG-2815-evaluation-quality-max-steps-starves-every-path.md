---
id: BUG-2815
type: BUG
priority: P1
status: done
captured_at: '2026-07-25T22:08:07Z'
completed_at: '2026-07-26T05:34:33Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- loops
- max-steps
blocked_by:
- ENH-2814
confidence_score: 100
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 25
---

# BUG-2815: `evaluation-quality` can never reach `done` — its only exit-0 path is an evaluator error

## Summary

`evaluation-quality.yaml:10` sets `max_steps: 5`, which starves every path
through a fully acyclic 12-state graph. A healthy run always dies at the step cap
with exit 1; the loop's **only** exit-0 path is an evaluator *error*. Success
semantics are fully inverted. Audit §1.3 /
`thoughts/builtin-loops-audit-2026-07-24.md`.

## Current Behavior

Shortest path is `sample → evaluate_code → score → route_action →
prepare_report → report → done` — 7 state entries, of which **6 count against
the budget** (the executor checks the cap at the top of each pass,
`executor.py:460`, increments once per non-terminal state, `:632`, and terminal
entry is free, `:569`).

Trace: after `prepare_report` the counter is 5; the next pass hits `5 >= 5` →
`_finish("max_steps")` → **exit 1** (`EXIT_CODES["max_steps"] = 1`). `report`
never executes. There is no `on_max_steps` handler. Only 5 of the loop's 12
states can run in any single run (6 distinct states across all paths); the
remediation branches (`route_code`, all three `remediate_*`) are unreachable.

Meanwhile `route_action` / `route_issues` / `route_code` carry `on_error: done`
(`:103`, `:112`, `:121`), and terminal entry is free — so an evaluation failure
at step 4 reaches `done` within budget and exits **0**.

Net: healthy run → exit 1; broken evaluator → exit 0.

Context: BUG-2735 (done 2026-07-22) fixed this loop's `sample` state reading JSON
fields `ll-issues list --json` never returns — so the loop is under active
repair, but the budget starvation survived that fix. It also explains the loop's
zero run history.

## Expected Behavior

- A healthy run reaches `report` → `done` and exits 0.
- The remediation branches are reachable.
- An evaluator error routes to a failure terminal, not the success terminal.
- Hitting the step cap produces a summary rather than a bare exit 1.

## Root Cause

`max_steps: 5` is below the loop's minimum viable step count (6 counted steps on
the shortest path), almost certainly copy-pasted rather than calibrated. The
`on_error: done` edges compound it by making the error path the only one that
fits the budget.

## Proposed Solution

1. Raise `max_steps` to ~15–20 (accommodates the remediation branches).
2. Add an `on_max_steps:` summary state.
3. Re-point or remove the three `on_error: done` edges (`:103`, `:112`, `:121`) —
   they belong on a failure terminal (see audit §2.2 / rec #8, and ENH-2814 for
   making such terminals observable).
4. Verify with `ll-loop calibrate-budget evaluation-quality`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Counted-step accounting confirmed**: shortest path `sample → evaluate_code
  → score → route_action → prepare_report → report → done` is 6 counted
  non-terminal states (`sample`, `evaluate_code`, `score`, `route_action`,
  `prepare_report`, `report`); `done` entry is free. The longest remediation
  path adds one more hop (e.g. `route_action → route_issues → remediate_issues
  → prepare_report → report → done`), so **8 counted states** covers every
  branch including `route_code`/`remediate_code`/`remediate_backlog`. A
  `max_steps` of 15 leaves comfortable headroom for the `on_max_steps` summary
  state itself plus any retry slack.
- **`on_max_steps:` is a real, already-supported FSM field** — declared at
  `schema.py:1457`, consumed in `executor.py:461-502` (dispatches to the named
  state once, guarded by `_summary_state_executed`, then finishes with
  `terminated_by="max_steps"` after that state runs). Six other built-in loops
  already use it: `general-task.yaml:9` (`on_max_steps: summarize_partial`),
  `cua-agent-desktop.yaml:17`, `vega-viz.yaml:37`,
  `oracles/generator-evaluator.yaml:20`, `oracles/generator-evaluator-flux.yaml:8`,
  `canvas-sketch-generator.yaml:32`.
- **Convention to copy for the summary state** (`general-task.yaml:658-722`,
  `summarize_partial`): a plain non-terminal `action_type: shell` (or
  `prompt`) state whose `next`/`on_error` both route into a dedicated
  terminal. Key gotcha from that state's own comment: the executor stops
  immediately after the `on_max_steps` target state finishes
  (`terminated_by: max_steps`) — any `next` chain past it never runs on that
  path, so the summary state's own action must do all the needed
  summarization work itself rather than deferring it downstream.
- **Convention to copy for the failure terminal** (`general-task.yaml:731-748`,
  `rn-implement.yaml:1662-1676`): add a second `terminal: true` state (e.g.
  `failed`) distinct from `done`, and route the three `on_error:` edges
  (`route_action:103`, `route_issues:112`, `route_code:121`) there instead of
  to `done`. `failed` is already in `fsm/validation.py`'s
  `FAILURE_TERMINAL_NAMES` name-convention set, so this alone flips the
  CLI-observed exit code today (`cli/loop/_helpers.py`'s legacy name check)
  even before ENH-2814's `failure:` schema flag lands — ENH-2814 makes the
  *persisted* `final_status`/history-DB view consistent, but the exit-code
  behavior for a bare `failed` terminal is already partially wired via the
  name-convention path per `EXIT_CODES`/`_helpers.py`.
- **No loop YAML references ENH-2814 directly** — that issue's changes are
  confined to `.py` engine files (`fsm/executor.py`, `fsm/persistence.py`,
  `fsm/schema.py`, `fsm/validation.py`, etc.), not loop authoring. This
  confirms the `blocked_by: [ENH-2814]` relationship is about *making the
  failure terminal observable end-to-end* (exit code + persistence +
  history), not a prerequisite for adding the `failed` terminal state itself
  — the YAML-side fix here (adding `failed`, re-pointing `on_error` edges) can
  proceed independently; only the downstream `final_status: "failed"`
  persistence guarantee waits on ENH-2814.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction re: exit-code wiring status**: `/ll:wire-issue`'s side-effect
  agent confirmed the CLI exit-code path is already fully live today, not
  merely "partially wired via the name-convention path" as stated above.
  `_finish()` (`executor.py:2833-2839`) computes `failure_terminal` from
  `StateConfig.failure`, which (`schema.py:806-824`) already defaults `True`
  from `FAILURE_TERMINAL_NAMES` (`schema.py:32-34`) for a terminal literally
  named `failed` — no `failure: true` flag needed. `cli/loop/__init__.py`
  (`:1907-1909`) reads `result.failure_terminal` directly and returns
  `FAILURE_TERMINAL_EXIT_CODE = 2` (`fsm/types.py:25`). So naming the new
  terminal `failed` gets correct exit-code behavior immediately; ENH-2814's
  remaining scope is narrower than this issue implies — persisted
  `final_status`/history-DB consistency only, not exit codes [Agent 2 finding].

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/evaluation-quality.yaml`

### Dependent Files (Callers/Importers)
- None — loop has no callers and zero run history

### Similar Patterns
- Other copy-pasted budgets flagged in audit §2.1 (separate issue)

### Tests
- `scripts/tests/test_builtin_loops.py` — structural coverage for this loop
- Consider a general assertion: `max_steps` ≥ counted states on the shortest terminal path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestEvaluationQualityLoop` (`:706-848`) — existing class; none of its assertions hardcode `max_steps: 5`, exact state count, or `on_error: done`, so the fix won't break it, but two existing tests should be tightened and four new ones added:
  - `test_route_states_have_on_error` (`:752-757`) — update: currently only checks the key exists on `route_action`/`route_issues`/`route_code`; tighten to assert the target is the new failure terminal (`on_error == "failed"`), matching the assertion style of `test_audit_conflicts_on_no_routes_to_retry` (`:6420-6424`) [Agent 3 finding]
  - `test_required_states_exist` (`:722-740`) — update: add `failed` to the `required` set once the terminal exists [Agent 3 finding]
  - New: a budget-vs-graph-depth test modeled on `test_max_steps_covers_intended_cycle_count` (`:9346-9355`, BUG-2824) asserting `max_steps >= <chosen value>` with a comment naming the longest remediation path [Agent 3 finding]
  - New: an `on_max_steps` handler test modeled on `test_has_on_max_steps_summary_handler` (`:9357-9368`, BUG-2824) — asserts the handler exists, resolves to a real state, and is `terminal: true` (BUG-158 terminal-doubling shape) [Agent 3 finding]
  - New: a `failed` terminal existence/shape test modeled on `test_done_state_is_terminal` (`:742-745`) — `assert data["states"]["failed"].get("terminal") is True` [Agent 3 finding]
- After the edit, run `ll-loop validate scripts/little_loops/loops/evaluation-quality.yaml` — `fsm/validation.py`'s `_validate_failure_terminal_action` (`:1100-1150`, WARNING) requires the failure terminal to have at least one predecessor with a diagnostic `action`/`loop`/`learning` primitive; `route_action`/`route_issues`/`route_code` are pure evaluator states with no such field, so routing `on_error` straight to `failed` from them may trip this WARNING — confirm and address if it fires [Agent 2 + Agent 3 finding]

### Documentation
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Adjacent finding, out of scope for this fix but worth flagging**:
  `prepare_report` (`evaluation-quality.yaml:159-165`) writes to a bare
  `.loops/quality-report-$(date +%Y-%m-%d).md` path rather than
  `${context.run_dir}/`, matching the MR-3 pattern (`.claude/CLAUDE.md` loop
  authoring rules) — this is a pre-existing issue independent of the
  `max_steps` fix and shouldn't be conflated with it here.

### Configuration
- N/A

## Implementation Steps

1. Re-derive the counted-step budget for the longest remediation path.
2. Set `max_steps` accordingly; add `on_max_steps`.
3. Re-point the `on_error: done` edges.
4. Run the loop once end-to-end and confirm exit 0 on the healthy path.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Run `ll-loop validate scripts/little_loops/loops/evaluation-quality.yaml` after the edit — check for a `_validate_failure_terminal_action` WARNING, since `route_action`/`route_issues`/`route_code` are pure evaluator states with no diagnostic `action`/`loop`/`learning` field of their own.
6. Update `test_route_states_have_on_error` and `test_required_states_exist` in `scripts/tests/test_builtin_loops.py::TestEvaluationQualityLoop` and add the four new tests (budget-vs-depth, `on_max_steps` handler shape, `failed` terminal shape) described in the Tests subsection above.

## Impact

- **Severity**: High for this loop — it cannot succeed as shipped, and its exit
  code lies in both directions.
- Isolated blast radius (1 file, no callers), so a fast, safe fix.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.3, §2.1, rec #4 | Source finding, step accounting |
| BUG-2735 (done 2026-07-22) | Sibling fix in the same loop — fold into the same repair arc |

## Steps to Reproduce

1. `ll-loop run evaluation-quality` with a healthy evaluator.
2. Observe the run terminates `max_steps` with exit 1 after `prepare_report`;
   `report` and `done` are never reached.
3. Force an evaluator error at `route_action` → the `on_error: done` edge is
   taken within budget and the run exits **0**.
4. Confirm statically: shortest terminal path is 7 state entries / 6 counted
   steps against `max_steps: 5` (`evaluation-quality.yaml:10`).

## Session Log
- `/ll:manage-issue` - 2026-07-26T05:34:03Z - `78cc9973-eca2-441b-85fc-238ef9fa89b5.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `0954064b-c66c-4a8e-9b2d-389d7a4157ad.jsonl`
- `/ll:wire-issue` - 2026-07-26T05:26:29 - `37228d12-afda-42a7-b0a4-a5c0a15c3979.jsonl`
- `/ll:refine-issue` - 2026-07-26T05:21:07 - `1383d2b3-9b44-437b-a036-7050826a0535.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:34 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
