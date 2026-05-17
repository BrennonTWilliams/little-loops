---
id: FEAT-1534
type: FEAT
priority: P2
status: open
discovered_date: 2026-05-16
discovered_by: capture-issue
captured_at: '2026-05-17T01:07:32Z'
confidence_score: 85
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
size: Very Large
---

# FEAT-1534: Add rn-plan built-in FSM loop for recursive task planning and execution

## Summary

Add a new built-in FSM loop `rn-plan` (Recursive-N Plan) that accepts a natural language task description, generates a plan markdown file and a scoring rubric file, then iteratively researches and refines the plan until it achieves perfect rubric scores or exhausts `max_iterations` (default 50). Intended as one of the core built-in loops in little-loops.

## Current Behavior

No built-in loop exists for structured, self-improving task planning. Users must manually create plan files, define evaluation criteria, conduct research, and refine plans with no automated feedback loop or convergence criterion. The existing `eval-driven-development.yaml` operates on code/issue quality, not free-form task planning.

## Expected Behavior

Users can run:

```bash
ll-loop run rn-plan "Build a REST API for user authentication with JWT tokens"
```

The loop:

1. **Creates output files** — derives a slug from the task description and writes:
   - `<slug>-plan.md` — the evolving task plan
   - `<slug>-plan-rubric.md` (or `.json`) — the scoring rubric

2. **Generates a rubric** — analyzes the task and builds a LOW / MEDIUM / HIGH / VERY-HIGH scale rubric evaluating:
   - **Breadth** — does the plan cover all relevant concerns?
   - **Depth** — are sub-steps sufficiently detailed?
   - **Complexity** — is the plan's complexity calibrated to the task?
   - **Granularity** — are action items actionable at the right level?
   - **Clarity** — is language unambiguous and concrete?
   - **Consistency** — are no steps contradictory or redundant?
   - **Logic & Strategy** — does the ordering and approach make sense?
   - **Outcome Confidence** — how confident is the agent that following the plan will produce the desired result?

3. **Determines research scope** — classifies what research is needed:
   - (A) File/directory research (grep, read, explore codebase)
   - (B) Web research (docs, APIs, current best practices)
   - (C) Both

4. **Executes research** — runs only the identified research steps, then synthesizes findings into plan updates.

5. **Scores the plan** — evaluates the current `<slug>-plan.md` against each rubric dimension and computes a final aggregate verdict.

6. **Loops or completes** — if all rubric dimensions are VERY-HIGH and no improvement is possible, the loop exits with `done`. Otherwise it repeats the Research → Refine → Score cycle until all scores are perfect or `max_iterations` is reached.

## Use Case

A developer starts a non-trivial implementation task and wants a battle-tested plan before writing code. They run `ll-loop run rn-plan "migrate the hooks adapter layer to support OpenCode events"` and the loop autonomously researches the codebase, refines the plan over multiple passes, and terminates with a high-confidence, fully-scoped implementation plan ready for execution.

## Acceptance Criteria

- [ ] `ll-loop run rn-plan "<task>"` accepts a positional task description and runs end-to-end without manual intervention
- [ ] Loop writes `<slug>-plan.md` and `<slug>-plan-rubric.md` to the configured output directory (default `.loops/plans/`)
- [ ] Rubric file contains all 8 dimensions (breadth, depth, complexity, granularity, clarity, consistency, logic_strategy, outcome_confidence) on a LOW/MEDIUM/HIGH/VERY-HIGH scale
- [ ] FSM states include init, generate_rubric, classify_research, research_files, research_web, synthesize, score, check_convergence, done
- [ ] Loop terminates with `done` when all rubric dimensions are VERY-HIGH or when `max_iterations` (default 50) is reached
- [ ] `--max-iterations` and `--output-dir` flags override defaults
- [ ] Research classification routes to file research, web research, or both based on task content
- [ ] Tests in `scripts/tests/loops/` cover rubric generation, research classification, score computation, and convergence detection

## Motivation

Planning quality directly determines implementation outcome confidence. Manual planning is inconsistent — developers skip research under time pressure, produce plans that are too vague, or miss cross-cutting concerns. A recursive self-scoring loop enforces a minimum quality bar before any implementation begins, reducing mid-task course corrections. As a core loop, `rn-plan` becomes a reusable front-end for any complex issue: run it, review the plan, then implement.

## Proposed Solution

Add a new built-in FSM loop YAML at `scripts/little_loops/loops/rn-plan.yaml` modeled on the existing `svg-image-generator.yaml` shape (closest analogue — free-form input, capture-based output paths, iterative generate→score→loop pattern) but tailored to free-form planning. The loop's prompt-mode states are dispatched through `DefaultActionRunner.run()` in `scripts/little_loops/fsm/runners.py`, which calls `run_claude_command()` and ultimately `resolve_host()` to invoke the host CLI. The score state uses `evaluate: type: llm_structured` (via `evaluate_llm_structured()` in `scripts/little_loops/fsm/evaluators.py`) for rubric scoring; shell states use the default `exit_code` evaluator.

Approach sketch:

```yaml
# scripts/little_loops/loops/rn-plan.yaml
name: rn-plan
description: Recursive planning loop with self-scoring rubric
category: planning
input_key: task                   # positional CLI arg -> context.task
initial: init
max_iterations: 50
context:
  task: ""
  output_dir: ".loops/plans"
states:
  init:                           # action_type: shell — derive slug, mkdir, echo absolute path
    capture: run_dir              # captured.run_dir.output used by downstream states
  generate_rubric:                # action_type: prompt — populate 8-dimension rubric file
  classify_research:              # action_type: prompt — emit one of FILES / WEB / BOTH
  research_files:                 # action_type: prompt — instruct LLM to use Read/Grep/Glob
  research_web:                   # action_type: prompt — instruct LLM to use WebSearch/WebFetch
  synthesize:                     # action_type: prompt — merge findings into plan file
  score:                          # action_type: prompt + evaluate: llm_structured
                                  #   on_yes: done   (all VERY-HIGH)
                                  #   on_no: classify_research
  done: { terminal: true }
```

Rubric scoring uses an integer-backed scale (LOW=1, MEDIUM=2, HIGH=3, VERY-HIGH=4) so the aggregate verdict is a simple mean. Convergence is `all dimensions == 4`, expressed via `evaluate: type: llm_structured` with a yes/no schema; `max_iterations` is enforced automatically by `FSMExecutor.run()` (no manual counter needed in YAML).

CLI wiring is automatic — `ll-loop run rn-plan "task description"` resolves the YAML by file glob in `cli/loop/_helpers.py:resolve_loop_path()` (no registration code to modify). The positional arg flows to `context.task` via `cmd_run()` in `cli/loop/run.py`. `--max-iterations` is already supported by the existing run subparser. No `--output-dir` flag exists today; users override via `--context output_dir=...` (recommended) or we extend `run_parser` to add the flag if desired.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Closest analogue**: `scripts/little_loops/loops/svg-image-generator.yaml` (NOT `eval-driven-development.yaml` as originally stated). It already demonstrates the exact patterns needed: `input_key: description`, shell-init state with `capture: run_dir`, prompt states writing to `${captured.run_dir.output}/filename.md`, iterative generate→score→loop with `output_contains` on a sentinel token.
- **No registration step required**: Built-in loops are discovered by file glob in `get_builtin_loops_dir()` at `scripts/little_loops/cli/loop/_helpers.py:122`. There is no `loop_runner.py` registry; dropping `rn-plan.yaml` into `scripts/little_loops/loops/` is sufficient.
- **Existing slug utility**: `slugify()` at `scripts/little_loops/issue_parser.py:99` already converts free-form strings to filename-safe slugs. The `init` shell state can shell out to a small Python one-liner or just use `sed`/`tr` inline — but the canonical helper exists for reuse from any Python code.
- **LLM-scored convergence**: `evaluate: type: llm_structured` (see `evaluate_llm_structured()` at `scripts/little_loops/fsm/evaluators.py:609`) builds a host invocation via `resolve_host().build_blocking_json(...)` and passes a JSON schema. This is the right evaluator for the score state (returns yes/no verdict directly).
- **No web-search FSM primitive**: A grep across all 43 built-in loop YAMLs found zero direct WebSearch/WebFetch state invocations. `rn-plan`'s `research_web` state must be `action_type: prompt` with explicit instructions telling the LLM to use its WebSearch/WebFetch tools (Claude/Codex provide these as built-in tools in their tool catalogs).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-plan.yaml` — NEW FSM definition (only required production file)
- `scripts/tests/test_builtin_loops.py` — update the `expected` set inside `TestBuiltinLoopFiles.test_expected_loops_exist` to include `"rn-plan"` (otherwise this test fails)

### Files NOT to Modify (research confirmed)
- ~~`scripts/little_loops/loop_runner.py`~~ — does not exist; built-in loops are file-glob discovered. **No registration code path exists.**
- ~~`ll-loop` CLI entry point~~ — discovery is automatic via `get_builtin_loops_dir()` + `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py:122,127`. The existing `run_parser` already supports the positional input arg and `--max-iterations`.

### Dependent Files (Discovery Path — for reference only)
- `scripts/little_loops/cli/loop/_helpers.py:122` — `get_builtin_loops_dir()` returns the built-in loops directory; new YAML is picked up automatically
- `scripts/little_loops/cli/loop/_helpers.py:127` — `resolve_loop_path()` falls through to built-in directory if not found locally
- `scripts/little_loops/cli/loop/run.py:126` — `cmd_run()` lines 126-139 inject `args.input` into `fsm.context[fsm.input_key]`
- `scripts/little_loops/cli/loop/__init__.py:96` — `run_parser` argparse block (already supports positional `input` + `--max-iterations`; would need extending only if adding a dedicated `--output-dir` flag)

### Similar Patterns (to model after)
- `scripts/little_loops/loops/svg-image-generator.yaml` — **closest analogue**: free-form `input_key`, shell-init with `capture: run_dir`, prompt states writing to `${captured.run_dir.output}/`, iterative generate→score→loop with sentinel `output_contains` evaluator, terminal `done` state
- `scripts/little_loops/loops/eval-driven-development.yaml:69-79` — example of `evaluate: type: llm_structured` block for yes/no LLM-scored verdicts
- `scripts/little_loops/loops/general-task.yaml:12-17` — example of `action_type: prompt` writing to `${env.PWD}/.loops/tmp/<name>.md` (alternative to capture pattern)
- `scripts/little_loops/loops/greenfield-builder.yaml:47-50` — example of an `action_type: prompt` research state (web-research analogue)

### Reusable Utilities
- `slugify()` at `scripts/little_loops/issue_parser.py:99` — filename-safe slug from free-form text
- `evaluate_llm_structured()` at `scripts/little_loops/fsm/evaluators.py:609` — LLM-scored verdict evaluator with JSON schema
- `evaluate_output_contains()` and `evaluate_exit_code()` at `scripts/little_loops/fsm/evaluators.py` — simpler verdict evaluators for sentinel-token states

### Tests
- `scripts/tests/loops/test_rn_plan.py` — NEW test module covering rubric generation, research classification, score computation, convergence detection. Model after:
  - `scripts/tests/test_loops_recursive_refine.py:TestDepthMapInit` — shell-state unit pattern using `_bash(script, tmp_path)` helper
  - `scripts/tests/test_ll_loop_execution.py:TestEndToEndExecution` — end-to-end pattern with `_make_mock_popen_factory()` + `monkeypatch.chdir(tmp_path)` + `patch.object(sys, "argv", [...])` + `main_loop()`
  - `scripts/tests/test_fsm_executor.py:MockActionRunner` (lines 31-88) — for unit-testing FSMExecutor without subprocess
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles` — parameterized validation (YAML parses, FSM valid, description present, name in expected set)

_Wiring pass added by `/ll:wire-issue`:_
- **Test file location**: `scripts/tests/loops/` subdirectory does NOT exist today; existing per-loop files (`test_harness_optimize.py`, `test_outer_loop_eval.py`) live at `scripts/tests/test_<name>.py` — place new file at `scripts/tests/test_rn_plan.py` OR create `scripts/tests/loops/__init__.py` first if subdirectory is intentional [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:TestSvgImageGeneratorLoop` (line 2488) — closest structural analog for per-state assertion pattern; use as template [Agent 3 finding]
- Auto-coverage (no changes needed): `test_fsm_flow.py:TestBuiltinLoopRegression.test_all_builtin_loops_still_load`, `test_review_loop.py:TestLoopValidation.test_builtin_loops_are_valid`, `test_fsm_fragments.py:TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` exercise all builtin YAML files dynamically and will cover `rn-plan.yaml` automatically [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add `rn-plan` entry to the built-in loops listing section
- `docs/reference/loops.md` — add a state graph / reference section for `rn-plan` (matches the format of existing entries)
- `scripts/little_loops/loops/README.md` — mention `rn-plan` if it lists built-ins

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — line 167 hardcodes `**47 FSM loops**`; update to `48` after adding `rn-plan.yaml` [Agent 2 finding]
- `CONTRIBUTING.md` — line 121 hardcodes `Built-in FSM loop definitions (43 YAML files)`; update to current count (already stale before this change) [Agent 2 finding]
- `CHANGELOG.md` — add `rn-plan` entry under the next concrete version `### Added` section (do NOT use `[Unreleased]`) [Agent 2 finding]

### Configuration
- Output directory default `.loops/plans/` is set via the `context.output_dir` default in the YAML (no `.ll/ll-config.json` entry required)
- Runtime override: `ll-loop run rn-plan "task" --context output_dir=custom/path` (uses existing `--context KEY=VALUE` flag — no new CLI infrastructure needed)
- Optional enhancement: extend `run_parser` in `cli/loop/__init__.py` to add a dedicated `--output-dir` flag (not strictly required; `--context` already covers the use case)

## Implementation Steps

1. **Create `scripts/little_loops/loops/rn-plan.yaml`** modeled on `svg-image-generator.yaml`. Top-level keys (per `FSMLoop.from_dict()` in `scripts/little_loops/fsm/schema.py`):
   - `name: rn-plan`
   - `description: Recursive planning loop with self-scoring rubric`
   - `category: planning` (optional, for `ll-loop list --category`)
   - `input_key: task` — routes the positional CLI arg into `context.task` (per `cmd_run()` at `scripts/little_loops/cli/loop/run.py:126`)
   - `initial: init`
   - `max_iterations: 50` — enforced automatically by `FSMExecutor.run()` (overridable with `--max-iterations`)
   - `context: { task: "", output_dir: ".loops/plans" }`

2. **Define states** (all transitions use `on_yes`/`on_no` shorthand or `next` for unconditional):
   - `init` — `action_type: shell`, action computes `SLUG=$(...)`, mkdir `${context.output_dir}/$SLUG`, writes blank plan+rubric files, echoes absolute run dir. `capture: run_dir`. `next: generate_rubric`.
     - Use Python-via-`python -c` to call `from little_loops.issue_parser import slugify; print(slugify("${context.task}"))` OR inline `tr`/`sed` (slugify is canonical).
   - `generate_rubric` — `action_type: prompt`, instructs the LLM to populate `${captured.run_dir.output}/<slug>-plan-rubric.md` with 8 dimensions on LOW/MEDIUM/HIGH/VERY-HIGH scale. `next: classify_research`.
   - `classify_research` — `action_type: prompt`, instructs the LLM to emit exactly one of `FILES`, `WEB`, or `BOTH`. `evaluate: type: output_contains` to detect token; route to `research_files`, `research_web`, or a `research_both` orchestration state.
   - `research_files` — `action_type: prompt`, tells LLM to use Read/Grep/Glob to research codebase; write findings into `${captured.run_dir.output}/<slug>-research.md`. `next: synthesize`.
   - `research_web` — `action_type: prompt`, tells LLM to use WebSearch/WebFetch (host tools); write findings into the same research file. `next: synthesize`.
   - `synthesize` — `action_type: prompt`, merges research into `${captured.run_dir.output}/<slug>-plan.md`. `next: score`.
   - `score` — `action_type: prompt` that reads the plan + rubric, scores each dimension, and writes scores back to the rubric file. Use `evaluate: type: llm_structured` (see `evaluators.py:609`) with a yes/no schema: "yes" if all 8 dimensions == VERY-HIGH, else "no". `on_yes: done`, `on_no: classify_research`, `on_error: failed`.
   - `done` — `action_type: prompt` that prints the final paths and summary. `terminal: true`.
   - `failed` — `terminal: true` (catches scoring errors).

3. **Rubric schema** (8 dimensions): `breadth`, `depth`, `complexity`, `granularity`, `clarity`, `consistency`, `logic_strategy`, `outcome_confidence`. Each scored LOW=1 / MEDIUM=2 / HIGH=3 / VERY-HIGH=4. Aggregate = mean. Convergence = all == 4 (expressed via the `llm_structured` yes/no schema in the score state — no separate `check_convergence` state needed).

4. **Update `scripts/tests/test_builtin_loops.py`**: add `"rn-plan"` to the `expected` set inside `TestBuiltinLoopFiles.test_expected_loops_exist`. Without this, `test_expected_loops_exist` will fail on first CI run.

5. **Create `scripts/tests/loops/test_rn_plan.py`** with three test classes:
   - `TestRnPlanYaml` — use `load_and_validate("scripts/little_loops/loops/rn-plan.yaml")` + `validate_fsm(fsm)`; assert no ERROR-severity results and that `fsm.description` is truthy. (Mirror `test_builtin_loops.py:TestBuiltinLoopFiles`.)
   - `TestRnPlanShellStates` — exercise the `init` shell action using `_bash(script, tmp_path)` helper (mirror `test_loops_recursive_refine.py:TestDepthMapInit`); assert run-dir creation and slug derivation.
   - `TestRnPlanExecution` — end-to-end test using `_make_mock_popen_factory()` + `monkeypatch.chdir(tmp_path)` + `patch.object(sys, "argv", ["ll-loop", "run", "rn-plan", "test task"])` + `main_loop()`. Verify the loop reaches `done` when the score state returns "yes". (Mirror `test_ll_loop_execution.py:TestEndToEndExecution`.)

6. **Documentation**: append a `rn-plan` entry to `docs/guides/LOOPS_GUIDE.md` (built-in loops listing) and `docs/reference/loops.md` (state graph + context variables section). Match the format used for `harness-optimize` or `eval-driven-development`.

7. **Verification**: run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/loops/test_rn_plan.py -v` and `python -m mypy scripts/little_loops/` to confirm all green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `README.md` line 167 — change `**47 FSM loops**` to `**48 FSM loops**`
9. Update `CONTRIBUTING.md` line 121 — change `Built-in FSM loop definitions (N YAML files)` count to reflect the new actual count after adding `rn-plan.yaml` (count is already stale before this change; verify with `ls scripts/little_loops/loops/*.yaml | wc -l`)
10. Add `CHANGELOG.md` entry under the next concrete version `### Added` section: `Added \`rn-plan\` built-in FSM loop for recursive, self-scoring task planning`
11. **Test file placement**: place new test at `scripts/tests/test_rn_plan.py` (following `test_harness_optimize.py` / `test_outer_loop_eval.py` convention) — the `loops/` subdirectory does not exist; create `scripts/tests/loops/__init__.py` first if the subdirectory location is intentional

## API/Interface

```bash
# Positional input
ll-loop run rn-plan "natural language task description"

# Override iterations
ll-loop run rn-plan "task" --max-iterations 20

# Custom output directory
ll-loop run rn-plan "task" --output-dir plans/
```

Output files (under `.loops/plans/` by default):
- `<slug>-plan.md`
- `<slug>-plan-rubric.md`

## Impact

- **Priority**: P2 - Core built-in loop that becomes the front-end for any complex implementation task; high reuse value but no existing user blocked
- **Effort**: Large - New FSM definition with 9 states, rubric schema, research classification logic, scoring, and test coverage
- **Risk**: Medium - Self-contained as a new built-in loop; main risk is iteration cost and rubric calibration, not regression in existing loops
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `captured`, `loops`, `built-in`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- **AC/implementation contradictions**: AC lists `check_convergence` as a required FSM state; implementation steps resolve to embedding convergence in `score` — reconcile before writing the YAML. AC also specifies `scripts/tests/loops/` (directory doesn't exist); implementation step 11 correctly resolves to `scripts/tests/test_rn_plan.py`
- **`research_both` routing undefined**: Three-way `classify_research → research_files | research_web | research_both` is referenced throughout but `research_both` is never defined; no existing built-in loop uses three-way `output_contains` routing — requires a concrete design decision before the YAML is stable

### Outcome Risk Factors
- Three design choices are simultaneously open (research_both routing, check_convergence vs embedded convergence, --output-dir flag vs --context override); their combined presence makes the first-pass YAML likely to need at least one revision cycle
- Breadth increased since previous check (wire-issue added README/CONTRIBUTING/CHANGELOG sites); Complexity score dropped 18→14, reflecting wider doc surface

## Session Log
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98cb73b6-2acb-4c4d-8e34-69fd0182f1e1.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:wire-issue` - 2026-05-17T01:26:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7b4be4f-93c3-4066-a776-3422cb63071d.jsonl`
- `/ll:refine-issue` - 2026-05-17T01:19:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76bec7dc-bf41-4c71-a95b-5d226691fa23.jsonl`
- `/ll:format-issue` - 2026-05-17T01:11:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c1c0949-0900-40f0-8cd1-9755750db2fa.jsonl`
- `/ll:capture-issue` - 2026-05-17T01:07:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9f536c9-fcc5-4138-bf10-9ec509b5e3a6.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P2
