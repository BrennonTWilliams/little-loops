---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# FEAT-933: Add outer-loop-eval Built-in Loop for Loop Observation and Improvement

## Summary

A new built-in loop `outer-loop-eval` that accepts a target loop name (built-in or
project-level) and optional input value, executes the target loop as a sub-loop, then
performs structured analysis of the execution to identify structural problems, logic
gaps, flow inefficiencies, and component improvement opportunities in the observed loop.

## Current Behavior

There is no built-in mechanism to evaluate the quality or correctness of a loop
definition. Developers must manually inspect YAML files and trace execution logs to
find problems. The `agent-eval-improve` loop provides a pattern for self-improvement
of agents, but no equivalent exists for loops themselves.

## Expected Behavior

Running `ll-loop run outer-loop-eval <loop-name> [input]` will:
1. Load and structurally analyze the target loop's YAML definition (state coverage,
   missing routes, evaluator types, context hygiene)
2. Execute the target loop as a sub-loop with the optional input passed through
3. Analyze the execution trace (state transitions, retry counts, evaluator verdicts,
   terminal state, timing)
4. Produce a structured improvement report covering: structural issues, logic issues,
   flow issues, and specific component recommendations with suggested YAML changes

## Motivation

Loop definitions are complex FSMs with many failure modes: orphaned states, missing
error routes, incorrect evaluator types, retry logic gaps, and redundant hops.
Currently these are caught only at runtime after failures. `outer-loop-eval` enables
proactive quality checking during loop development and provides a reusable evaluation
harness for loop CI / automated loop improvement workflows.

## Proposed Solution

New file: `scripts/little_loops/loops/outer-loop-eval.yaml`

FSM design (6 states):
1. **`analyze_definition`** (prompt): Read loop YAML via `ll-loop show ${context.loop_name}`,
   produce structured analysis of state coverage, missing routes, evaluator types,
   context variable hygiene, cycle risks
2. **`run_sub_loop`** (shell): `ll-loop run ${context.loop_name} ${context.input}`,
   capture full output including state transitions and verdicts
3. **`analyze_execution`** (prompt): Parse sub-loop output — state sequence, retry counts,
   verdicts, terminal state reached, unexpected paths, anomalies
4. **`generate_report`** (prompt + `llm_structured` evaluate): Combine definition and
   execution analysis into a structured improvement report with sections for
   Structural Issues / Logic Issues / Flow Issues / Component Improvements /
   Suggested YAML Changes. Route `yes` → done if report has ≥1 concrete finding.
5. **`refine_analysis`** (prompt, max_retries: 2): Re-examine data if report lacks
   concrete recommendations, loop back to `generate_report`
6. **`done`** (terminal)

Reuse patterns from:
- `agent-eval-improve.yaml` — eval/refine pattern with `llm_structured` evaluator
- `harness-single-shot.yaml` — capture + analyze structure
- `evaluation-quality.yaml` — multi-dimensional scoring with routed remediation

Context variables:
```yaml
context:
  loop_name: ""   # Required: target loop name
  input: ""       # Optional: input value passed to sub-loop
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — new loop definition (create)
- `scripts/little_loops/loops/README.md` — add to catalog under "Meta/Analysis" section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — `ll-loop list` will auto-discover new file
- `scripts/little_loops/cli/loop/run.py` — executes via `FSMExecutor`, no changes needed

### Similar Patterns
- `scripts/little_loops/loops/agent-eval-improve.yaml` — closest structural analog
- `scripts/little_loops/loops/evaluation-quality.yaml` — multi-dimensional eval pattern
- `scripts/little_loops/loops/harness-single-shot.yaml` — capture + gate structure

### Tests
- `scripts/tests/test_fsm_interpolation.py` — verify `${context.loop_name}` resolves in shell actions
- New: `scripts/tests/loops/test_outer_loop_eval.py` — validate schema, simulate dry-run

### Documentation
- `scripts/little_loops/loops/README.md` — catalog entry

### Configuration
- N/A — no config schema changes needed; loop is auto-discovered

## Implementation Steps

1. Study `agent-eval-improve.yaml` and `evaluation-quality.yaml` for structural patterns to reuse
2. Create `scripts/little_loops/loops/outer-loop-eval.yaml` with the 6-state FSM design above
3. Validate schema: `ll-loop validate outer-loop-eval`
4. Dry-run against a simple loop: `ll-loop simulate outer-loop-eval issue-refinement`
5. Add catalog entry to `scripts/little_loops/loops/README.md`
6. Run existing FSM tests to confirm no regressions

## Use Case

A developer has written a new `data-pipeline-monitor` loop and wants to verify its
quality before deploying it. They run `ll-loop run outer-loop-eval data-pipeline-monitor`
— the outer-loop-eval executes the pipeline loop once, then returns a report identifying
that two states lack `on_error` routes and one `llm_structured` evaluator is missing a
`confidence_threshold`. The developer applies the suggested YAML changes and re-runs
to confirm clean execution.

## Acceptance Criteria

- [ ] `ll-loop validate outer-loop-eval` passes with no schema errors
- [ ] `ll-loop simulate outer-loop-eval <any-built-in-loop>` completes the dry-run without crashing
- [ ] Output report includes at least: Structural Issues, Logic Issues, Flow Issues, Component Improvements sections
- [ ] `input` context variable is correctly passed to the sub-loop when provided
- [ ] Loop handles the case where `loop_name` does not exist (error route to done with clear message)
- [ ] Loop handles sub-loop timeout/crash gracefully (on_error route to analyze_execution)
- [ ] `outer-loop-eval` appears in `ll-loop list` output
- [ ] README catalog entry added

## Impact

- **Priority**: P3 — Useful developer tool; not blocking anything
- **Effort**: Small — one new YAML file + README update; reuses existing FSM infrastructure entirely
- **Risk**: Low — no core code changes; new YAML file is isolated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `built-in-loop`, `loop-eval`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c25f637-5481-4d98-bba6-846f5500e0e9.jsonl`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3
