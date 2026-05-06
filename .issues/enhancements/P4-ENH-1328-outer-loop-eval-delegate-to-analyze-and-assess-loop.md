---
id: ENH-1328
type: ENH
priority: P4
captured_at: '2026-05-02T19:05:00Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
decision_needed: true
---

# ENH-1328: `outer-loop-eval` Should Delegate to `/ll:analyze-loop` and `/ll:assess-loop`

## Summary

`outer-loop-eval.yaml` currently has three inline prompt-based states — `analyze_definition`, `analyze_execution`, `generate_report` — that each ask the model to inspect the target loop's YAML and execution trace and produce structured analysis. With FEAT-1325 (`/ll:assess-loop`) and the existing `/ll:analyze-loop` skill, that logic is duplicated. Replace the inline prompts with skill invocations so we ship a single canonical analyzer.

## Motivation

- **Two diverging analyzers** — every improvement to `/ll:analyze-loop` (e.g., the new effectiveness signals in ENH-1327) has to be either re-implemented in `outer-loop-eval`'s prompts or remain unavailable to it. That guarantees drift.
- **Inline prompts can't access the resolved state map** — once ENH-1326 lands, `/ll:analyze-loop` will see merged `from:`/`fragment:`/sub-loop graphs. The inline prompts in `outer-loop-eval` will continue to call `ll-loop show <name>` and miss that resolution.
- **Inline prompts produce free-text** — `analyze_definition.capture: definition_analysis` is unstructured. `/ll:analyze-loop --json` and `/ll:assess-loop --json` produce structured output that `generate_report` can route on programmatically.

## Current Behavior

`scripts/little_loops/loops/outer-loop-eval.yaml` states:

- `analyze_definition` (lines 28-49) — prompt that asks the model to read `ll-loop show ${context.loop_name}` and emit a structured analysis covering state coverage, missing routes, evaluator types, context hygiene, and cycle risks.
- `analyze_execution` (lines 59-81) — prompt that parses sub-loop output for transition sequence, retry counts, verdicts, terminal state, anomalies.
- `generate_report` (lines 83-135) — prompt that combines the two analyses into a 5-section improvement report.
- `refine_analysis` (lines 137-164) — fallback when `generate_report` produced no concrete findings.

## Expected Behavior

After ENH-1326 and FEAT-1325 land:

- `analyze_definition` becomes a `shell` action: `/ll:analyze-loop ${context.loop_name} --static-only --json` (or equivalent) capturing the resolved-graph + static-signal output.
- `analyze_execution` becomes a `shell` action: `/ll:analyze-loop ${context.loop_name} --json` capturing the full fault + effectiveness signals from the just-completed sub-loop run.
- `generate_report` calls `/ll:assess-loop ${context.loop_name} --json` and uses its structured scorecard + proposals as the report basis.
- `refine_analysis` either disappears (the assessor's "always emit ≥1 proposal" guarantee replaces it) or is repurposed as a higher-temperature fallback that runs only when `assess-loop` returns zero proposals.

## Implementation Steps

1. ~~Wait for FEAT-1325, ENH-1326, and ENH-1327 to ship~~ — all three are now in `.issues/completed/`; no remaining dependency blockers.
2. Add a headless invocation mode to `/ll:analyze-loop` (`skills/analyze-loop/SKILL.md`) and `/ll:assess-loop` (`skills/assess-loop/SKILL.md`) — at minimum a flag (e.g., `--no-create-issues` or `--auto`) that skips the `AskUserQuestion` issue-creation prompt (analyze-loop Step 5, assess-loop Step 9) and exits cleanly without side effects. Without this, invoking either skill from a loop state will block waiting for user input.
3. Rewrite `analyze_definition` in `scripts/little_loops/loops/outer-loop-eval.yaml`:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:analyze-loop ${context.loop_name} --no-create-issues"` (or the flag name from step 2)
   - Keep `capture: definition_analysis` and `timeout: 600`
   - Follow pattern from `fix-quality-and-tests.yaml:analyze-type-errors`
4. Rewrite `analyze_execution` similarly:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:analyze-loop ${context.loop_name} --no-create-issues"`
   - Keep `capture: execution_analysis` and routing
5. Rewrite `generate_report`:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:assess-loop ${context.loop_name} --no-create-issues"`
   - Keep `capture: improvement_report`
   - Update the `evaluate` block's `prompt:` to check for non-empty proposals section in the assess-loop output (rather than checking for "None identified." in free-text prose)
6. Decide fate of `refine_analysis`: either remove it (if `/ll:assess-loop` guarantees ≥1 proposal), or repurpose it as a higher-temperature fallback `slash_command` that re-invokes `assess-loop` only when the proposals section is empty.
7. Update `scripts/tests/test_outer_loop_eval.py`:
   - `test_analyze_definition_is_prompt` (line 93): change `assert state.get("action_type") == "prompt"` → `== "slash_command"`; update action content assertion
   - `test_analyze_execution_is_prompt` (line 113): same action_type change
   - `test_generate_report_has_llm_structured_evaluator` (line 120): change `action_type` assertion; update evaluate prompt assertion to match new output format check
   - `test_refine_analysis_loops_to_generate_report` (line 142): update action_type assertion if refine_analysis is kept

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — rewrite `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` states to `action_type: shell` skill invocations

### Dependent Files (Callers/Importers)
- `scripts/tests/test_outer_loop_eval.py` — structural tests for outer-loop-eval.yaml; assertions for `action_type: "prompt"` on `analyze_definition` (line 94), `analyze_execution` (line 113), `generate_report` (line 122), and `refine_analysis` (line 143) will need updating to match the new action types
- `scripts/tests/test_builtin_loops.py:102` — parametrized FSM validation; includes `"outer-loop-eval"` in the expected set; no content changes needed, only the YAML structure must remain valid
- `docs/guides/LOOPS_GUIDE.md:1718` — extensive section describing outer-loop-eval's inline prompt analysis states; will need updating to reflect delegation to skills
- `scripts/little_loops/loops/README.md:52` — one-line description in the built-in loops catalog

### Similar Patterns
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:analyze-type-errors` — canonical pattern to follow: `action_type: slash_command`, `action: "/ll:check-code types"`, `capture: type_analysis`; downstream `fix-type-errors` state consumes `${captured.type_analysis.output}` in its prompt
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:refine_issue` — `action_type: slash_command`, `action: "/ll:refine-issue ${captured.issue_id.output} --auto"`, no capture but chained via `next:`
- `scripts/little_loops/loops/harness-multi-item.yaml:check_skill` — `action_type: slash_command` with both a `capture:` and an inline `evaluate: llm_structured` block; demonstrates how to evaluate skill output without a separate state

### Tests
- `scripts/tests/test_outer_loop_eval.py` — existing test file; `TestOuterLoopEvalStates` class has per-state assertions for `action_type`, `capture`, `evaluate.type`, and routing targets; these will need updating for all four refactored states

### Documentation
- `docs/guides/LOOPS_GUIDE.md:1718–1761` — `outer-loop-eval` section describes inline analysis states in detail; will need updating post-implementation
- `docs/guides/LOOPS_GUIDE.md:637` — one-line entry in the built-in loops table
- `docs/guides/LOOPS_GUIDE.md:253` — usage example referencing `outer-loop-eval`

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Action type correction**: The issue's Expected Behavior says "becomes a `shell` action" but the correct `action_type` for invoking `/ll:` skills from loop states is `slash_command` (not `shell`). In the FSM executor (`executor.py:963-964`), `_action_mode()` maps both `"prompt"` and `"slash_command"` to the same `"prompt"` execution path — both run via `run_claude_command()` which launches `claude -p <action>`. A plain `action_type: shell` with `/ll:analyze-loop` as the action would invoke it as a bash command and fail.

**Skill flag gap**: Neither `/ll:analyze-loop` nor `/ll:assess-loop` currently has `--json` or `--static-only` flags defined in their frontmatter arguments. Both produce human-readable markdown output. More critically, both use `AskUserQuestion` (analyze-loop Step 5, assess-loop Step 9) to ask whether to create issues — this interactive step will block when invoked headlessly from a loop state. Step 2 of Implementation Steps below must address this before the YAML rewrite can work.

**Dependency status**: FEAT-1325, ENH-1326, and ENH-1327 are all in `.issues/completed/` — all declared blockers have shipped.

## API/Interface

No new CLI surface — this is a pure refactor of one loop YAML to consume existing skills.

## Scope Boundaries

- **In scope**: Rewriting the four analysis states in `outer-loop-eval.yaml` to `action_type: shell` skill invocations; updating associated tests to mock skill output instead of inline prompts.
- **Out of scope**: Changes to `/ll:analyze-loop` or `/ll:assess-loop` skill implementations; new CLI flags or public interface changes; altering `outer-loop-eval`'s invocation contract with callers.

## Acceptance Criteria

- [ ] `outer-loop-eval.yaml` no longer contains inline analysis prompts; states delegate to `/ll:analyze-loop` and `/ll:assess-loop`.
- [ ] `outer-loop-eval` produces an improvement report identical in structure (or richer) to the prior version.
- [ ] When the underlying skills change (e.g., new signal added), `outer-loop-eval` benefits without YAML edits.
- [ ] Existing tests for `outer-loop-eval` updated and passing.

## Depends On

- FEAT-1325 — `/ll:assess-loop` must exist.
- ENH-1326 — resolved-graph view should be available.
- ENH-1327 — effectiveness signals enrich the assessor's input (nice-to-have, not strict blocker).

## Impact

- **Priority**: P4 — blocked by FEAT-1325 and ENH-1326; low urgency until dependencies land
- **Effort**: Medium — rewriting 3-4 YAML states + test mock updates; no new logic required
- **Risk**: Low — pure refactor with identical external behavior; existing tests provide regression coverage
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `refactor`, `captured`

## Status

**Open** | Created: 2026-05-02 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-06_

**Readiness Score**: 93/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- **Complexity spike from skill prerequisite**: Step 2 (adding `--no-create-issues` headless mode to `/ll:analyze-loop` and `/ll:assess-loop`) is a prerequisite that expands scope to 6 files across loops, skills, and docs subsystems — the inline YAML rewrite cannot work headlessly until both skills are updated first.
- **Scope Boundaries contradiction**: The Scope Boundaries section says "Out of scope: Changes to `/ll:analyze-loop` or `/ll:assess-loop`" and uses "action_type: shell" — both contradict Implementation Steps 2–5 (which require skill changes and `slash_command`). Risk of implementer confusion; fix the Scope Boundaries section at the start of the session.
- **Unresolved decision — `refine_analysis` fate**: Step 6 presents two options (remove it if assess-loop guarantees ≥1 proposal, or repurpose as fallback) without selecting one. This unresolved decision requires verifying `/ll:assess-loop`'s actual output guarantees before the implementation state can be finalized.

## Session Log
- `/ll:confidence-check` - 2026-05-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/484c72e4-5eaa-4465-a207-cc2a1d3e75ea.jsonl`
- `/ll:refine-issue` - 2026-05-06T17:42:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae942d93-13fc-4689-a86a-676d13c32c1e.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T13:08:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66b7ef9c-3106-4ab5-9130-c852d0e94984.jsonl`
