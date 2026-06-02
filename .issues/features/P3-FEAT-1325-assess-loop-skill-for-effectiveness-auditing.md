---
id: FEAT-1325
type: FEAT
priority: P3
captured_at: '2026-05-02T19:05:00Z'
discovered_date: '2026-05-02'
discovered_by: capture-issue
decision_needed: false
confidence_score: 90
outcome_confidence: 61
score_complexity: 0
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
size: Very Large
status: done
completed_at: 2026-05-02T00:00:00Z
---

# FEAT-1325: `/ll:assess-loop` Skill for Loop Effectiveness Auditing

## Summary

Add a sibling skill to `/ll:analyze-loop` that judges whether a loop is **accomplishing the purpose stated in its description**, not just whether it crashed. `/ll:analyze-loop` stays lean and rule-based (runtime fault detection). `/ll:assess-loop` adds reasoning-heavy effectiveness analysis: it consumes `analyze-loop`'s findings as Phase 1, then layers on a goal-vs-outcome scorecard, success-contract extraction, artifact inspection, and an LLM-graded rubric-vs-description audit.

## Motivation

Survey of the 30+ built-in loops in `scripts/little_loops/loops/` showed that "did the loop do its job" is almost never visible from event history alone. Success is defined by **artifact state changes external to the FSM**: file mtime/diffs (`apo-textgrad`'s `prompt_file`, `svg-image-generator`'s `image.svg`), frontmatter score thresholds (`refine-to-ready-issue`'s `confidence` ≥ 90 / `outcome` ≥ 75), captured numeric trajectories (`rl-coding-agent`'s composite reward ≥ `reward_target`), and rubric semantics (the eval-harness mistake captured in `feedback_eval_harness_purpose.md` — running `/ll:manage-issue` from an `execute` state is a phantom success the current skill can't detect).

The existing `analyze-loop` Step 3b "Goal alignment" only compares state names against the `description` string — that's far too thin to catch phantom convergence, degenerate gates, or rubrics that don't operationalize the stated goal.

## Use Case

A user runs `apo-textgrad` to optimize a prompt. The loop terminates cleanly on iteration 1 because the model emitted `CONVERGED` from `compute_gradient` without ever entering `apply_gradient` — the prompt file is byte-identical to what it was at the start. `/ll:analyze-loop` reports no faults. `/ll:assess-loop` reports:

```
Goal:        Test prompt against examples; refine until pass-rate ≥ 90
Contract:    target_pass_rate=90, prompt_file mutation expected
Achieved:    iteration 1; pass_rate=100 (unverified); apply_gradient never visited
Artifacts:   git diff ${context.prompt_file} → empty
Verdict:     PHANTOM — terminal reached, contract unmet
Proposals:   1) tighten convergence rubric to require evidence;
             2) add invariant: apply_gradient must run ≥ 1× before terminal
```

## API/Interface

```bash
/ll:assess-loop [loop-name] [--tail N] [--no-rubric-audit]
```

- `loop-name` — same resolution rules as `/ll:analyze-loop` (auto-select most recent if omitted).
- `--no-rubric-audit` — skip the LLM rubric-vs-description pass (cost gate).
- Phase 1 internally calls `/ll:analyze-loop --json` and includes its findings.
- Output is the goal-vs-outcome scorecard followed by ranked improvement proposals (NOT auto-created issues — the user runs `/ll:capture-issue` selectively).

## Implementation Steps

1. **Resolve the loop fully** — merge `from:` parents, expand `fragment:` against `lib/*.yaml`, recursively parse one level of `loop:` sub-loop refs. (See ENH companion for stand-alone version of this step that also benefits `/ll:analyze-loop`.)
2. **Extract success contract** — parse `context.*` thresholds (`target_pass_rate`, `pass_threshold`, `quality_threshold`, `readiness_threshold`, `outcome_threshold`, `reward_target`, `target_score`, `min_per_category`, `adversarial_cap`); tag each `evaluate` state with the threshold it gates.
3. **Inspect artifacts** — read files under `.loops/tmp/<loop>/<run>/` and run `git diff` against any path the loop's actions touch (`${context.prompt_file}`, `system.md`, `.issues/**`, `data/curated/`, `image.svg`, `examples.json`, `manifest.json`).
4. **Phase 1 — invoke `/ll:analyze-loop`** and parse its JSON output for fault signals; include verbatim in the scorecard.
5. **Goal-vs-outcome scorecard** — output the structured block: Goal / Contract / Achieved / Artifacts / Verdict (met | partial | phantom | degraded).
6. **Rubric-vs-description audit** (gated by `--no-rubric-audit`) — for each `evaluate.type: llm_structured`, send the loop description plus that evaluator's `prompt` text to a single judge call: "Does this rubric operationalize the loop's stated purpose?" Catches the harness-running-`/ll:manage-issue` mistake and rubric drift.
7. **Sub-loop verdict laundering check** — when a state has `loop: <child>`, verify `on_success` and `on_failure` route to different downstream states.
8. **Proposals** — emit ranked improvement suggestions (state-level, rubric-level, contract-level) with concrete YAML diffs where possible.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — Loop resolution:** `ll-loop show <name> --json` (entry: `scripts/little_loops/cli/loop/info.py:cmd_show()`) already outputs the fully-materialized FSM via `FSMLoop.to_dict()` (schema in `scripts/little_loops/fsm/schema.py`). Resolution is done by `load_and_validate()` in `scripts/little_loops/fsm/validation.py`, which calls `resolve_inheritance()` then `resolve_fragments()` before constructing `FSMLoop`. No separate resolution step is needed — `ll-loop show --json` is the one call that provides the complete state map including `context.*`, all `evaluate` blocks, `description`, and `states` with their `loop:` fields.

**Step 2 — Contract extraction:** From `ll-loop show <name> --json`, `.context` is a flat dict. Threshold keys to scan: `target_pass_rate`, `pass_threshold`, `quality_threshold`, `readiness_threshold`, `outcome_threshold`, `reward_target`, `target_score`, `min_per_category`, `adversarial_cap`, `quality_threshold`. Also scan each state's `evaluate.target` for `"${context.<key>}"` interpolation patterns, and each state's `action` / `evaluate.prompt` for embedded `${context.<key>}` references (apo-textgrad embeds the threshold in the prompt string rather than using a numeric evaluator — see `scripts/little_loops/loops/apo-textgrad.yaml`).

**Step 3 — Artifact paths:** Flat `.loops/tmp/` files (most loops) vs per-run subfolder `${context.output_dir}/<TS>/` (svg-image-generator). For issue-based loops, artifacts are frontmatter fields read via `ll-issues show <id> --json`. In-memory captured values are in `state.json:captured` dict (loaded from `.loops/.running/<loop_name>.state.json` or `.loops/.history/<run_id>-<loop_name>/state.json`). Persistence schema defined in `scripts/little_loops/fsm/persistence.py:LoopState.to_dict()`.

**Step 4 — Critical prerequisite:** `analyze-loop` has **no `--json` flag today** (`skills/analyze-loop/SKILL.md` arguments: `loop_name`, `tail` only). ENH-1327 ("deterministic effectiveness signals") is the companion that would add structured output. Until ENH-1327 ships, `assess-loop` must either (a) treat Phase 1 as calling `ll-loop history <name> [run_id] --json` + `ll-loop show <name> --json` directly, or (b) block on ENH-1327. The issue's acceptance criteria don't require `--json` to be wired yet — a read-the-prose Phase 1 is acceptable for the initial skill.

**Step 5 — Verdict rules:** `met` = terminal reached AND all threshold contracts verified AND all expected artifact mutations occurred. `phantom` = terminal reached AND (artifacts unchanged OR threshold unverified by code — only model self-reported). `partial` = terminal reached AND some but not all contracts satisfied. `degraded` = loop completed but metric trended downward vs baseline.

**Step 6 — Rubric audit pattern:** `outer-loop-eval.yaml:generate_report` state uses exactly this `llm_structured` judge pattern (see `scripts/little_loops/loops/outer-loop-eval.yaml`). For each state where `evaluate.type == "llm_structured"`, the state's `evaluate.prompt` and the loop's top-level `description` are the two inputs to the judge call.

**Step 7 — Sub-loop check:** In `FSMLoop.to_dict()`, states with sub-loops have a `"loop"` key. The routing shorthands are `on_yes`/`on_no` (aliases for `on_success`/`on_failure` in practice, resolved via `_route()` in `scripts/little_loops/fsm/executor.py`). The check: `state["on_yes"] != state["on_no"]` (or equivalently `route["yes"] != route["no"]`).

**Step 8 — Proposals deduplication:** Follow `analyze-loop/SKILL.md` Steps 4–5: `grep -rl` against `.issues/bugs/`, `.issues/enhancements/`, `.issues/features/`; then present ranked proposals via `AskUserQuestion` for user to selectively run `/ll:capture-issue`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `README.md` — increment skill count 27→28; add `/ll:assess-loop` to Automation & Loops table and Skills table
10. Update `CONTRIBUTING.md` — increment skill count 27→28; add `assess-loop/` to the skills directory listing
11. Update `docs/ARCHITECTURE.md` — increment skill count 27→28; insert `assess-loop/` tree entry after `analyze-loop/`
12. Update `.claude/CLAUDE.md` — add `assess-loop`^ to the "Automation & Loops" bullet; update 27→28 in Key Directories line
13. Update `docs/reference/COMMANDS.md` — add `### /ll:assess-loop` full section; add `assess-loop` to the `**See also:**` line under `### /ll:analyze-loop`; add row to Quick Reference table
14. Update `scripts/tests/test_enh1268_doc_wiring.py` — add `TestAssessLoopCommandsWiring` class parallel to `TestAnalyzeLoopCommandsWiring`

## Integration Map

### Files to Create
- `skills/assess-loop/SKILL.md` — New skill definition; follow frontmatter conventions from `skills/analyze-loop/SKILL.md` (allowed-tools, arguments, model: sonnet)
- `scripts/tests/test_assess_loop_skill.py` — Skill existence + logic discriminator tests
- `scripts/tests/fixtures/fsm/assess-phantom-success.yaml` — Fixture: loop converges iter 1, prompt_file unchanged
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — Fixture: evaluate.target never actually reached
- `scripts/tests/fixtures/fsm/assess-rubric-drift.yaml` — Fixture: evaluate.prompt doesn't operationalize description
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — Fixture: sub-loop on_yes == on_no

### Primary Data Sources
- `ll-loop show <name> --json` → `FSMLoop.to_dict()` — one call provides the complete resolved loop (entry: `scripts/little_loops/cli/loop/info.py:cmd_show()`; schema: `scripts/little_loops/fsm/schema.py:FSMLoop`)
- `ll-loop history <name> [run_id] --json --tail N` → event array — for fault signal pass (entry: `scripts/little_loops/cli/loop/info.py:cmd_history()`)
- `.loops/.running/<loop_name>.state.json` or `.loops/.history/<run_id>-<loop_name>/state.json` → `LoopState.to_dict()` — contains `captured` dict with in-memory action outputs (schema: `scripts/little_loops/fsm/persistence.py:LoopState`)

### Loop YAML Examples (for testing and pattern reference)
- `scripts/little_loops/loops/apo-textgrad.yaml` — Phantom-convergence test case; `context.target_pass_rate: 90` embedded in prompt (not numeric evaluator); `context.prompt_file` artifact
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `context.readiness_threshold: 90`, `context.outcome_threshold: 75`; thresholds enforced via shell Python subprocess reading issue frontmatter
- `scripts/little_loops/loops/rl-coding-agent.yaml` — `context.reward_target: 0.85`; uses `evaluate.type: convergence` with `target: "${context.reward_target}"`
- `scripts/little_loops/loops/svg-image-generator.yaml` — `context.pass_threshold: 6`, `context.output_dir`; artifacts at `${context.output_dir}/<TS>/image.svg`
- `scripts/little_loops/loops/outer-loop-eval.yaml` — `generate_report` state has `evaluate: type: llm_structured, min_confidence: 0.7`; its `analyze_definition` and `analyze_execution` states are the ones ENH-1328 replaces with calls to this skill

### Similar Patterns
- `scripts/tests/test_analyze_loop_synthesis.py` — Semantic fixture-based test pattern for loop analysis; load YAML fixture → assert structural properties Claude would need to detect
- `scripts/tests/test_review_loop.py:TestReviewLoopQualityChecks` — Logic discriminator pattern: encode each quality check as an independent Python assertion with a comment documenting the expected skill behavior
- `scripts/tests/test_outer_loop_eval.py` — Loop YAML structural validation pattern using `load_and_validate()` + `validate_fsm()`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — Add `/ll:assess-loop` entry alongside `/ll:analyze-loop`; also add `assess-loop` to the `**See also:**` line in the existing `### /ll:analyze-loop` section [Agent 2 finding]
- `README.md` — Update `**27 skills**` → `**28 skills**` (line ~89); add `/ll:assess-loop` row to the `### Automation & Loops` command table (~line 166) and the full Skills table (~line 221) [Agent 2 finding]
- `CONTRIBUTING.md` — Update `27 skill definitions` → `28 skill definitions` (~line 125); add `assess-loop/` entry to the `skills/` directory listing (~lines 125–150) [Agent 2 finding]
- `docs/ARCHITECTURE.md` — Update `# 27 skill definitions` → `# 28 skill definitions` (~line 100); add `assess-loop/` tree entry between `analyze-loop/` and `audit-claude-config/` (~line 103) [Agent 2 finding]
- `.claude/CLAUDE.md` — Add `assess-loop`^ to the "Automation & Loops" bullet in `## Commands & Skills`; update `skills/ # Skill definitions (27 skills)` → `(28 skills)` in `## Key Directories` [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1268_doc_wiring.py` — Add a `TestAssessLoopCommandsWiring` class parallel to the existing `TestAnalyzeLoopCommandsWiring`; assert that `docs/reference/COMMANDS.md` contains the `### /ll:assess-loop` section with the verdict values (`met`, `partial`, `phantom`, `degraded`) and the `--no-rubric-audit` flag [Agent 2 finding: `TestAnalyzeLoopCommandsWiring._analyze_loop_section()`]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/doc_counts.py` — No code change needed; `verify_documentation()` uses `rglob("SKILL.md")` so it auto-detects the new count once the three documentation files above are updated to 28 [Agent 2 finding: `COUNT_TARGETS`, `verify_documentation()`]

## Coordination With `outer-loop-eval`

`outer-loop-eval` already has prompt-based `analyze_definition` / `analyze_execution` / `generate_report` states. See the companion ENH to swap those inline prompts for `/ll:analyze-loop` + `/ll:assess-loop` calls so we don't ship two diverging analyzers.

## Acceptance Criteria

- [ ] `/ll:assess-loop` skill exists at `skills/assess-loop/SKILL.md` with documented arguments and triggers.
- [ ] Phase 1 invokes `/ll:analyze-loop --json` and threads its output into the scorecard.
- [ ] Scorecard verdict is one of: `met`, `partial`, `phantom`, `degraded`.
- [ ] Detects the phantom-success case on a synthetic `apo-textgrad` run that converges on iter 1 without diff.
- [ ] Detects the harness-running-wrong-skill case (rubric audit flags an `execute` action that doesn't match the harness subject).
- [ ] `--no-rubric-audit` flag skips all LLM judge calls.
- [ ] Tests cover at least: phantom success, degenerate gate, rubric drift, sub-loop verdict laundering.

## Labels

`feature`, `loops`, `analysis`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-02_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors

- **Complexity score is artificially low** — 12-file count triggers the worst bracket, but 6 are tiny YAML fixtures and 5 are single-paragraph doc updates. True implementation effort is concentrated in `skills/assess-loop/SKILL.md` + `test_assess_loop_skill.py`. Expect faster than the score implies.
- **Open decision on Phase 1 path** — acceptance criteria says "Phase 1 invokes `/ll:analyze-loop --json`" but that flag does not exist (ENH-1327 pending). Resolve this open decision before implementing: choose approach (a) — call `ll-loop history <name> --json` + `ll-loop show <name> --json` directly (confirmed viable) — and update acceptance criteria to match, or explicitly mark Phase 1 as a prose-read stub pending ENH-1327.

> **Selected:** Option A (direct `ll-loop history/show --json`) — confirmed viable, reuses the identical two-call pattern already used by `analyze-loop`; no ENH-1327 dependency required.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-02.

**Selected**: Option A — Call `ll-loop history <name> --json` + `ll-loop show <name> --json` directly

**Reasoning**: Both CLI commands already ship `--json` output; `analyze-loop` uses this exact two-call pattern today (`skills/analyze-loop/SKILL.md:78–97`); `FSMLoop.to_dict()` and `LoopState.captured` are fully serializable with no gaps. The child issue FEAT-1329 has already adopted this approach in its acceptance criteria, superseding Option B (block on ENH-1327) entirely.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (direct `ll-loop history/show --json`) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (block on ENH-1327 / prose stub) | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- Option A: `cmd_show()` JSON path at `scripts/little_loops/cli/loop/info.py:643`; `analyze-loop` uses identical pattern at `skills/analyze-loop/SKILL.md:78–97`; 10+ passing tests (`test_ll_loop_commands.py:840–910, 2424–2508`)
- Option B: No existing skill parses prose output from another skill; ENH-1327 chains through ENH-1326 (two open issues deep); FEAT-1329 acceptance criteria already supersedes this approach

## Status

**Open** | Created: 2026-05-02 | Priority: P3


---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-02
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1329: `/ll:assess-loop` Skill — Core Implementation (Steps 1–8, skill file + tests + fixtures)
- FEAT-1330: `/ll:assess-loop` Skill — Documentation & Wiring (Steps 9–14, doc updates + wiring test)

## Session Log
- `/ll:decide-issue` - 2026-05-02T19:40:34 - `086a8ee8-3a17-4e59-8e8e-6617217c02f8.jsonl`
- `/ll:confidence-check` - 2026-05-02T20:15:00Z - `8577a3e4-2b35-418b-bd1f-2875a7606043.jsonl`
- `/ll:wire-issue` - 2026-05-02T19:31:01 - `f518bac9-1a11-45b6-9edd-4639111fecb7.jsonl`
- `/ll:refine-issue` - 2026-05-02T19:26:48 - `cd19a52d-95ef-4129-baf3-ab21f5925877.jsonl`
- `/ll:issue-size-review` - 2026-05-02T20:30:00Z - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
