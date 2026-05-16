---
id: ENH-1328
type: ENH
priority: P4
captured_at: '2026-05-02T19:05:00Z'
completed_at: '2026-05-06T19:00:54Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 81
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 18
decision_needed: false
status: done
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

- `analyze_definition` (lines 39-67) — prompt that asks the model to read `ll-loop show ${context.loop_name}` and emit a structured analysis covering state coverage, missing routes, evaluator types, context hygiene, and cycle risks.
- `analyze_execution` (lines 79-102) — prompt that parses sub-loop output for transition sequence, retry counts, verdicts, terminal state, anomalies.
- `generate_report` (lines 104-157) — prompt that combines the two analyses into a 5-section improvement report.
- `refine_analysis` (lines 159-187) — fallback when `generate_report` produced no concrete findings.

## Expected Behavior

After ENH-1326 and FEAT-1325 land:

- `analyze_definition` becomes a `slash_command` state: `"/ll:analyze-loop ${context.loop_name} --auto"` capturing the static-signal output.
- `analyze_execution` becomes a `slash_command` state: `"/ll:analyze-loop ${context.loop_name} --auto"` capturing the full fault + effectiveness signals from the just-completed sub-loop run.
- `generate_report` becomes a `slash_command` state: `"/ll:assess-loop ${context.loop_name} --auto"` using its structured scorecard + proposals as the report basis.
- `refine_analysis` stays as a `slash_command` fallback: `"/ll:assess-loop ${context.loop_name} --auto"` — research confirmed `assess-loop` has no ≥1 proposal guarantee, so the fallback route from `generate_report`'s `on_no` is necessary.

## Implementation Steps

1. ~~Wait for FEAT-1325, ENH-1326, and ENH-1327 to ship~~ — all three are now in `.issues/completed/`; no remaining dependency blockers.
2. ~~Add a headless invocation mode to `/ll:analyze-loop` and `/ll:assess-loop`~~ — completed in ENH-1373 (2026-05-06). Both skills now define `--auto` and `--skip-issue-creation` flags that suppress `AskUserQuestion` at Step 5 (analyze-loop) and Step 9 (assess-loop) and exit cleanly. Use `--auto` in all invocations below.
3. Rewrite `analyze_definition` in `scripts/little_loops/loops/outer-loop-eval.yaml`:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:analyze-loop ${context.loop_name} --auto"`
   - Keep `capture: definition_analysis` and `timeout: 600`
   - Follow pattern from `fix-quality-and-tests.yaml:analyze-type-errors`
4. Rewrite `analyze_execution` similarly:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:analyze-loop ${context.loop_name} --auto"`
   - Keep `capture: execution_analysis` and routing
5. Rewrite `generate_report`:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:assess-loop ${context.loop_name} --auto"`
   - Keep `capture: improvement_report`
   - Update the `evaluate` block's `prompt:` to check for non-empty proposals section in the assess-loop output (rather than checking for "None identified." in free-text prose)
6. Keep `refine_analysis` as a fallback `slash_command`: codebase research confirmed `/ll:assess-loop` makes no "always emit ≥1 proposal" guarantee — both skills have explicit zero-result exit paths — so the `on_no: refine_analysis` routing in `generate_report` is necessary. Rewrite `refine_analysis`:
   - Change `action_type: prompt` → `action_type: slash_command`
   - Change `action:` to `"/ll:assess-loop ${context.loop_name} --auto"`
   - Keep `capture: improvement_report` (overwrites the same key, triggering re-evaluation)
   - Keep `next: generate_report` to re-trigger the `llm_structured` evaluator
7. Update `scripts/tests/test_outer_loop_eval.py`:
   - `test_analyze_definition_is_prompt` (line 93): change `assert state.get("action_type") == "prompt"` → `== "slash_command"`; update action content assertion
   - `test_analyze_execution_is_prompt` (line 113): same action_type change
   - `test_generate_report_has_llm_structured_evaluator` (line 120): change `action_type` assertion; update evaluate prompt assertion to match new output format check
   - `test_refine_analysis_loops_to_generate_report` (line 142): change `action_type` assertion to `"slash_command"`; update `action` assertion to match `/ll:assess-loop` invocation string
   - `test_generate_report_sections_in_prompt` (line 129): remove or replace — this test asserts five section headings in the inline prompt text, which will no longer exist after the rewrite to `slash_command`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/outer-loop-eval.yaml` — rewrite `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` states to `action_type: slash_command` skill invocations

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

_Updated by `/ll:refine-issue` (second pass) — 2026-05-06:_

**ENH-1373 completed**: The headless flag prerequisite (Step 2) is done. Both `skills/analyze-loop/SKILL.md` and `skills/assess-loop/SKILL.md` now declare `--auto` and `--skip-issue-creation` as frontmatter arguments. `--auto` suppresses `AskUserQuestion` at Step 5 (analyze-loop) / Step 9 (assess-loop) and prints `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` before stopping. Use `--auto` in all `slash_command` invocations in Steps 3–6.

**`refine_analysis` decision resolved (keep as fallback)**: Neither `assess-loop` nor `analyze-loop` guarantees ≥1 proposal/signal in its output — both have explicit zero-result exit paths. The `generate_report` evaluate block's `on_no: refine_analysis` route must be preserved. `refine_analysis` should be rewritten from `action_type: prompt` to `action_type: slash_command` with `action: "/ll:assess-loop ${context.loop_name} --auto"`, keeping `capture: improvement_report` (overwrites the key, re-triggering the evaluator on `next: generate_report`).

**`generate_report` evaluate routing**: The existing `llm_structured` evaluator at lines 145–157 checks `"${captured.improvement_report.output}"` for "at least one concrete finding" vs "every section contains only 'None identified.'". After the rewrite, this evaluate block should continue to work as-is, since `assess-loop` output will still contain section text — update only if the output format changes materially.

**Test updates needed** (`scripts/tests/test_outer_loop_eval.py`): Four `action_type == "prompt"` assertions (lines 95, 114, 121, 142) change to `"slash_command"`. The `action` string assertions for `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` must be updated to match the new `/ll:*` action strings. The `test_generate_report_sections_in_prompt` test (lines 129–140) — which asserts five section headings in the `action` prompt text — will need to be removed or replaced since the new `action` is a short skill invocation string, not a multi-section prompt.

## API/Interface

No new CLI surface — this is a pure refactor of one loop YAML to consume existing skills.

## Scope Boundaries

- **In scope**: Rewriting the four analysis states in `outer-loop-eval.yaml` to `action_type: slash_command` skill invocations; updating associated tests to match new `action_type` and `action` string values.
- **Out of scope**: New CLI flags or public interface changes to `/ll:analyze-loop` or `/ll:assess-loop` (headless flags `--auto`/`--skip-issue-creation` already landed in ENH-1373; no further skill changes needed); altering `outer-loop-eval`'s invocation contract with callers.

## Acceptance Criteria

- [x] `outer-loop-eval.yaml` no longer contains inline analysis prompts; states delegate to `/ll:analyze-loop` and `/ll:assess-loop`.
- [x] `outer-loop-eval` produces an improvement report identical in structure (or richer) to the prior version.
- [x] When the underlying skills change (e.g., new signal added), `outer-loop-eval` benefits without YAML edits.
- [x] Existing tests for `outer-loop-eval` updated and passing.

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

## Resolution

Rewrote all four inline `action_type: prompt` analysis states in `outer-loop-eval.yaml` to `action_type: slash_command` delegating to `/ll:analyze-loop` and `/ll:assess-loop` with `--auto`. Updated tests (`test_analyze_definition_is_slash_command`, `test_analyze_execution_is_slash_command`, updated `test_generate_report_has_llm_structured_evaluator`, updated `test_refine_analysis_loops_to_generate_report`; removed `test_generate_report_sections_in_prompt`). Updated `docs/guides/LOOPS_GUIDE.md` and `scripts/little_loops/loops/README.md`. All 314 tests pass, lint clean.

## Session Log
- `/ll:manage-issue` - 2026-05-06T19:00:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-06T18:55:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/863f77a8-f087-48b6-abf9-96e4b84b6af7.jsonl`
- `/ll:confidence-check` - 2026-05-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7b2c6f8-e164-450a-8eee-06915b99a26a.jsonl`
- `/ll:refine-issue` - 2026-05-06T18:19:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b83f09f-29bf-4f72-b768-87d537225716.jsonl`
- `/ll:confidence-check` - 2026-05-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/484c72e4-5eaa-4465-a207-cc2a1d3e75ea.jsonl`
- `/ll:refine-issue` - 2026-05-06T17:42:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae942d93-13fc-4689-a86a-676d13c32c1e.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T13:08:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66b7ef9c-3106-4ab5-9130-c852d0e94984.jsonl`
