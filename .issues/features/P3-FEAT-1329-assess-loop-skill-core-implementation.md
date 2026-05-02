---
id: FEAT-1329
type: FEAT
priority: P3
parent_issue: FEAT-1325
---

# FEAT-1329: `/ll:assess-loop` Skill — Core Implementation

## Summary

Create the `skills/assess-loop/SKILL.md` skill definition and its test suite (including FSM fixture YAMLs). This child covers all logic phases of the skill: loop resolution, contract extraction, artifact inspection, Phase 1 analyze-loop invocation, goal-vs-outcome scorecard, rubric audit, sub-loop verdict laundering check, and ranked proposals output.

## Parent Issue

Decomposed from FEAT-1325: `/ll:assess-loop` Skill for Loop Effectiveness Auditing

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

## Files to Create

- `skills/assess-loop/SKILL.md` — New skill definition; follow frontmatter conventions from `skills/analyze-loop/SKILL.md` (allowed-tools, arguments, model: sonnet)
- `scripts/tests/test_assess_loop_skill.py` — Skill existence + logic discriminator tests
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — Loop converges iter 1, prompt_file unchanged
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — evaluate.target never actually reached
- `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml` — evaluate.prompt doesn't operationalize description
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — sub-loop on_yes == on_no

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

## Acceptance Criteria

- [ ] `skills/assess-loop/SKILL.md` exists with documented arguments (`loop-name`, `--tail`, `--no-rubric-audit`) and triggers.
- [ ] Scorecard verdict is one of: `met`, `partial`, `phantom`, `degraded`.
- [ ] `--no-rubric-audit` flag skips all LLM judge calls.
- [ ] Tests cover: phantom success, degenerate gate, rubric drift, sub-loop verdict laundering.
- [ ] Open decision resolved: Phase 1 uses `ll-loop history --json` + `ll-loop show --json` directly (not `analyze-loop --json`); acceptance criteria updated accordingly.

## Session Log
- `/ll:issue-size-review` - 2026-05-02T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
