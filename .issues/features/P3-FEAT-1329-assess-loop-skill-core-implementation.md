---
id: FEAT-1329
type: FEAT
priority: P3

decision_needed: false
confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-02T20:22:36Z
parent: FEAT-1325
status: done
---

# FEAT-1329: `/ll:assess-loop` Skill — Core Implementation

## Summary

Create the `skills/assess-loop/SKILL.md` skill definition and its test suite (including FSM fixture YAMLs). This child covers all logic phases of the skill: loop resolution, contract extraction, artifact inspection, Phase 1 analyze-loop invocation, goal-vs-outcome scorecard, rubric audit, sub-loop verdict laundering check, and ranked proposals output.

## Parent Issue

Decomposed from FEAT-1325: `/ll:assess-loop` Skill for Loop Effectiveness Auditing

## Current Behavior

The `/ll:assess-loop` skill does not exist. There is no automated way to audit whether a configured loop's execution actually achieved its stated goal, whether artifacts were mutated as expected, or whether the loop contains structural defects (phantom convergence, degenerate gates, rubric drift, sub-loop verdict laundering).

## Expected Behavior

Running `/ll:assess-loop [loop-name]` produces:
- A goal-vs-outcome scorecard with one of four verdicts: `met`, `partial`, `phantom`, or `degraded`
- A rubric-vs-description audit (gated by `--no-rubric-audit`)
- A sub-loop verdict laundering check
- Ranked improvement proposals with concrete YAML diffs

## Use Case

A developer has deployed `apo-textgrad` for automated prompt optimization. Before trusting it in production, they run `/ll:assess-loop apo-textgrad` to verify the loop actually mutated `prompts/test.md` and hit the `target_pass_rate` threshold — rather than reaching `done` via model self-report with no artifact evidence (phantom success).

## API/Interface

```bash
/ll:assess-loop [loop-name] [--tail N] [--no-rubric-audit]
```

- `loop-name` — same resolution rules as `/ll:analyze-loop` (auto-select most recent if omitted).
- `--no-rubric-audit` — skip the LLM rubric-vs-description pass (cost gate).
- Phase 1 internally calls `ll-loop history <name> --json` + `ll-loop show <name> --json` (prose-read stub acceptable pending ENH-1327).

## Implementation Steps

1. **Resolve the loop** — call `ll-loop show <name> --json` to get the fully-materialized FSM via `FSMLoop.to_dict()` (entry: `scripts/little_loops/cli/loop/info.py:cmd_show()`; schema: `scripts/little_loops/fsm/schema.py`). No separate resolution needed.

2. **Extract success contract** — from `.context` flat dict, scan threshold keys: `target_pass_rate`, `pass_threshold`, `quality_threshold`, `readiness_threshold`, `outcome_threshold`, `reward_target`, `target_score`, `min_per_category`, `adversarial_cap`. Also scan each `evaluate.target` for `"${context.<key>}"` interpolation and each `action` / `evaluate.prompt` for embedded references.

3. **Inspect artifacts** — check `.loops/tmp/<loop>/<run>/` and run `git diff` against paths the loop's actions touch (`${context.prompt_file}`, `system.md`, `.issues/**`, `data/curated/`, `image.svg`, `examples.json`, `manifest.json`). For issue-based loops, read frontmatter via `ll-issues show <id> --json`. In-memory captures are in `state.json:captured` (schema: `scripts/little_loops/fsm/persistence.py:LoopState`).

4. **Phase 1** — call `ll-loop history <name> [run_id] --json --tail N` for fault signals; include verbatim in scorecard. (Prose-read stub acceptable if ENH-1327 `--json` flag is not yet available.)

5. **Goal-vs-outcome scorecard** — output structured block: Goal / Contract / Achieved / Artifacts / Verdict. Verdict rules:
   - `met` = terminal reached AND all threshold contracts verified AND all expected artifact mutations occurred
   - `phantom` = terminal reached AND (artifacts unchanged OR threshold unverified — only model self-reported)
   - `partial` = terminal reached AND some but not all contracts satisfied
   - `degraded` = loop completed but metric trended downward vs baseline

6. **Rubric-vs-description audit** (gated by `--no-rubric-audit`) — for each `evaluate.type: llm_structured`, send the loop description plus that evaluator's `prompt` text to a single judge call. Pattern from `outer-loop-eval.yaml:generate_report` state.

7. **Sub-loop verdict laundering check** — when a state has `loop: <child>`, verify `on_yes` != `on_no` (aliases resolved via `_route()` in `scripts/little_loops/fsm/executor.py`).

8. **Proposals** — emit ranked improvement suggestions (state-level, rubric-level, contract-level) with concrete YAML diffs where possible. Follow `analyze-loop/SKILL.md` deduplication pattern: `grep -rl` against `.issues/` dirs; present via `AskUserQuestion` for user to selectively run `/ll:capture-issue`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Write `scripts/tests/test_assess_loop_skill.py` — use `_load_fixture()` + `_happy_path()` instance methods on the test class (copy verbatim from `TestAnalyzeLoopSynthesis`); structural validation via `load_and_validate(FIXTURES_DIR / "assess-X.yaml")` with `validate_fsm()` + `ValidationSeverity.ERROR` filter; four discriminator tests (phantom success, degenerate gate, rubric drift, sub-loop laundering) using inline-dict + assert + `# → skill should flag as X` pattern from `TestReviewLoopQualityChecks`. Module-level `FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fsm"` — do not use `conftest.py` `fsm_fixtures` fixture.
10. Write the 4 `scripts/tests/fixtures/fsm/assess-*.yaml` fixture files — exact YAML content is specified in the "Fixture YAML Structures" section above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 7 (sub-loop laundering) correction**: The issue says "aliases resolved via `_route()`" — this is inaccurate. Sub-loop routing bypasses `_route()` entirely and is handled by `FSMExecutor._execute_sub_loop()` (`scripts/little_loops/fsm/executor.py`). The laundering check should read `on_yes` and `on_no` directly from the `ll-loop show --json` FSM JSON output (`states.<name>.on_yes` and `states.<name>.on_no`). A laundering defect is: a state where `loop:` is set AND `state.on_yes == state.on_no` (after `${context.*}` interpolation if applicable).
- **`ll-loop history --json` availability**: `cmd_history()` in `scripts/little_loops/cli/loop/info.py` already supports `--json`. ENH-1327 is about extracting deterministic effectiveness signals from history — it does not add the `--json` flag. No prose-read stub is needed.
- **`FSMLoop.to_dict()` concrete shape**: always-present keys: `name`, `initial`, `states`. Conditionally present: `description`, `context` (threshold keys live here as flat dict), `max_iterations` (only if ≠ 50), `parameters`. Each state value in `states` omits None/default fields; for sub-loop states expect: `loop`, `on_yes`, `on_no` (and optionally `on_error`). Threshold scan should cover the `context` dict (Step 2) and also scan `action` / `evaluate.prompt` strings for `${context.<key>}` interpolations.
- **Skill allowed-tools**: copy exactly from `skills/analyze-loop/SKILL.md`: `Bash(ll-loop:*, ll-issues:*, git:*)`, `Read`, `Glob`, `Grep`, `Write`, `AskUserQuestion`.

## Files to Create

- `skills/assess-loop/SKILL.md` — New skill definition; follow frontmatter conventions from `skills/analyze-loop/SKILL.md` (allowed-tools, arguments, model: sonnet)
- `scripts/tests/test_assess_loop_skill.py` — Skill existence + logic discriminator tests
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — Loop converges iter 1, prompt_file unchanged
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — evaluate.target never actually reached
- `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml` — evaluate.prompt doesn't operationalize description
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — sub-loop on_yes == on_no

### Codebase Research Findings — Fixture YAML Structures

_Added by `/ll:refine-issue` — concrete YAML for each new fixture (modeled on `scripts/tests/fixtures/fsm/analysis-dominant-cycling.yaml` and similar):_

**`assess-phantom-success.yaml`** — loop converges iter 1, `prompt_file` artifact unchanged:
```yaml
name: assess-phantom-success
description: "Optimize prompt quality until pass rate target is reached"
initial: optimize
context:
  prompt_file: "prompts/test.md"
  target_pass_rate: 90
states:
  optimize:
    action_type: prompt
    action: "Improve the prompt in ${context.prompt_file} to increase pass rate."
    evaluate:
      type: llm_structured
      prompt: "Did pass rate reach ${context.target_pass_rate}%? Answer YES or NO."
    on_yes: done
    on_no: optimize
  done:
    terminal: true
```

**`assess-degenerate-gate.yaml`** — `evaluate.target` never reached; loop exits only via `on_no`:
```yaml
name: assess-degenerate-gate
description: "Run dataset quality check until quality threshold is met"
initial: check_quality
context:
  quality_threshold: 95
states:
  check_quality:
    action_type: shell
    action: "python scripts/check_quality.py"
    evaluate:
      type: exit_code
      target: 0
    on_yes: done
    on_no: check_quality
    on_error: check_quality
  done:
    terminal: true
```

**`assess-rubric-drift.yaml`** — `evaluate.prompt` checks "clean syntax" but description says "improve answer quality":
```yaml
name: assess-rubric-drift
description: "Improve answer quality in the training dataset until convergence"
initial: refine_answers
context:
  pass_threshold: 80
states:
  refine_answers:
    action_type: prompt
    action: "Review and improve the dataset answers for clarity and correctness."
    evaluate:
      type: llm_structured
      prompt: "Does the file contain clean Python syntax with no errors? Answer YES or NO."
    on_yes: done
    on_no: refine_answers
  done:
    terminal: true
```

**`assess-subloop-laundering.yaml`** — sub-loop `on_yes == on_no` (success indistinguishable from failure):
```yaml
name: assess-subloop-laundering
description: "Run child evaluation loop and act on result"
initial: run_eval
states:
  run_eval:
    loop: inner-eval
    on_yes: report_done
    on_no: report_done
  report_done:
    action_type: prompt
    action: "Write a summary of the evaluation outcome."
    next: done
  done:
    terminal: true
```

## Primary Data Sources

- `ll-loop show <name> --json` → `FSMLoop.to_dict()` (entry: `scripts/little_loops/cli/loop/info.py:cmd_show()`)
- `ll-loop history <name> [run_id] --json --tail N` → event array (entry: `scripts/little_loops/cli/loop/info.py:cmd_history()`)
- `.loops/.running/<loop_name>.state.json` or `.loops/.history/<run_id>-<loop_name>/state.json` → `LoopState.to_dict()` (schema: `scripts/little_loops/fsm/persistence.py:LoopState`)

## Loop YAML Examples (for testing)

- `scripts/little_loops/loops/apo-textgrad.yaml` — Phantom-convergence; `context.prompt_file` artifact
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `context.readiness_threshold: 90`, `context.outcome_threshold: 75`
- `scripts/little_loops/loops/rl-coding-agent.yaml` — `context.reward_target: 0.85`; `evaluate.type: convergence`
- `scripts/little_loops/loops/svg-image-generator.yaml` — `context.pass_threshold: 6`; per-run artifact dirs
- `scripts/little_loops/loops/outer-loop-eval.yaml` — `evaluate: type: llm_structured` rubric audit pattern

## Similar Test Patterns

- `scripts/tests/test_analyze_loop_synthesis.py` — Semantic fixture-based test pattern
- `scripts/tests/test_review_loop.py:TestReviewLoopQualityChecks` — Logic discriminator pattern
- `scripts/tests/test_outer_loop_eval.py` — Loop YAML structural validation using `load_and_validate()`

## Integration Map

### Files to Create
- `skills/assess-loop/SKILL.md` — New skill; follows `skills/analyze-loop/SKILL.md` frontmatter exactly (model: sonnet, Bash scoped to `ll-loop:*`, `ll-issues:*`, `git:*`)
- `scripts/tests/test_assess_loop_skill.py` — Test suite using fixture-loading + discriminator patterns
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — Phantom verdict discriminator fixture
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — Degenerate gate discriminator fixture
- `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml` — Rubric drift discriminator fixture
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — Sub-loop laundering discriminator fixture

### Dependent Files (Callers/Importers)
- `skills/analyze-loop/SKILL.md` — sibling skill; assess-loop replicates its CLI invocation approach as Phase 1
- `.claude-plugin/plugin.json` — skill registry entry (wired in FEAT-1330, not this issue)

### Primary Data Dependencies
- `scripts/little_loops/cli/loop/info.py:cmd_show()` — `ll-loop show <name> --json` → `FSMLoop.to_dict()` JSON
- `scripts/little_loops/cli/loop/info.py:cmd_history()` — `ll-loop history <name> <run_id> --json --tail N` → event array
- `scripts/little_loops/fsm/schema.py:FSMLoop.to_dict()` — JSON shape: always-present `name`, `initial`, `states`; conditionally `description`, `context` (threshold keys live here), `max_iterations`, `parameters`
- `scripts/little_loops/fsm/persistence.py:LoopState` — `state.json` schema; `captured` dict shape: `{state_name: {output, stderr, exit_code, duration_ms}}`
- `scripts/little_loops/fsm/executor.py:FSMExecutor._execute_sub_loop()` — sub-loop routing semantics for laundering check: `on_yes` = child reached `done` terminal; `on_no` = child did not
- `scripts/little_loops/fsm/validation.py:load_and_validate()` — YAML fixture validation in tests; signature: `load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]`; also import `validate_fsm`, `ValidationSeverity` for structural error checks

### Similar Patterns
- `skills/analyze-loop/SKILL.md` — exact frontmatter template to copy; Phase 1 CLI invocation pattern; dedup/capture-issue flow (`grep -rl` + `AskUserQuestion`)
- `scripts/little_loops/loops/outer-loop-eval.yaml:generate_report` — `evaluate.type: llm_structured` with `source: "${captured.<key>.output}"`, `min_confidence: 0.7`, YES/NO judge prompt
- `scripts/tests/test_analyze_loop_synthesis.py:TestAnalyzeLoopSynthesis` — `_load_fixture()` + `_happy_path()` helpers + inline threshold constants pattern
- `scripts/tests/test_review_loop.py:TestReviewLoopQualityChecks` — logic discriminator test pattern: inline dict, assert condition, `# → skill should flag as X`

### Tests (to model after)
- `scripts/tests/test_analyze_loop_synthesis.py` — semantic fixture-based test structure
- `scripts/tests/test_review_loop.py` — logic discriminator test pattern
- `scripts/tests/test_outer_loop_eval.py` — loop YAML structural validation via `load_and_validate()`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — Automation & Loops list needs `assess-loop`^ + skill count `27 → 28` **(FEAT-1330)**
- `README.md` — skill count `27 skills → 28 skills` (line 89) **(FEAT-1330)**
- `docs/ARCHITECTURE.md` — two skill count occurrences `27 → 28` + `assess-loop/` entry in directory listing (alphabetical, between `analyze-loop/` and `audit-claude-config/`) **(FEAT-1330)**
- `docs/reference/COMMANDS.md` — full `### /ll:assess-loop` subsection + quick reference table row; also add to `/ll:analyze-loop` and `/ll:cleanup-loops` "See also" lines **(FEAT-1330)**
- `docs/guides/LOOPS_GUIDE.md` — Further Reading section entry alongside `/ll:review-loop` **(FEAT-1330)**

## Acceptance Criteria

- [ ] `skills/assess-loop/SKILL.md` exists with documented arguments (`loop-name`, `--tail`, `--no-rubric-audit`) and triggers.
- [ ] Scorecard verdict is one of: `met`, `partial`, `phantom`, `degraded`.
- [ ] `--no-rubric-audit` flag skips all LLM judge calls.
- [ ] Tests cover: phantom success, degenerate gate, rubric drift, sub-loop verdict laundering.
- [ ] Open decision resolved: Phase 1 uses `ll-loop history --json` + `ll-loop show --json` directly (not `analyze-loop --json`); acceptance criteria updated accordingly.

## Impact

- **Priority**: P3 — Child issue of FEAT-1325; non-critical but foundational for loop quality auditing
- **Effort**: Medium — New skill definition + 4 FSM fixture YAMLs + test suite; well-specified with clear patterns to follow from `analyze-loop` and `review-loop`
- **Risk**: Low — New file creation only; no changes to existing production code
- **Breaking Change**: No

## Labels

`skill`, `automation`, `loops`, `assess-loop`, `captured`

## Resolution

**Status**: Completed 2026-05-02

### Changes Made

- Created `skills/assess-loop/SKILL.md` — skill definition with 8 implementation steps: loop resolution, FSM load, contract extraction, artifact inspection, Phase 1 fault signals, goal-vs-outcome scorecard (4 verdicts), rubric-vs-description audit (gated by `--no-rubric-audit`), sub-loop verdict laundering check, and ranked proposals with YAML diffs.
- Created `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — loop converges iter 1 via `llm_structured` self-report; `prompt_file` artifact may be unchanged.
- Created `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — `exit_code` evaluator with `on_no` and `on_error` both looping to self; gate cannot be exited on failure.
- Created `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml` — description says "improve answer quality"; evaluator checks Python syntax — no semantic overlap.
- Created `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — sub-loop state has `on_yes == on_no`; child verdict silently discarded.
- Created `scripts/tests/test_assess_loop_skill.py` — 26 tests covering skill existence, 4 fixture structural validations via `load_and_validate` + `validate_fsm`, and 4 logic discriminator groups (phantom success, degenerate gate, rubric drift, sub-loop laundering).

All 26 tests pass.

## Status

**Completed** | Created: 2026-05-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-02T20:16:00 - `84942db7-8cc7-4831-b8e7-956bded3b552.jsonl`
- `/ll:wire-issue` - 2026-05-02T20:11:17 - `3d728104-c3d3-4d54-90ed-bb75fe7962bc.jsonl`
- `/ll:refine-issue` - 2026-05-02T20:07:35 - `0a3d6f5c-dcaa-40b6-ad56-66d5c8ad85af.jsonl`
- `/ll:issue-size-review` - 2026-05-02T20:30:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:confidence-check` - 2026-05-02T21:00:00Z - `90b32456-5506-47a2-abed-b98982ed82c8.jsonl`
- `/ll:manage-issue` - 2026-05-02T20:22:36Z - `current.jsonl`
