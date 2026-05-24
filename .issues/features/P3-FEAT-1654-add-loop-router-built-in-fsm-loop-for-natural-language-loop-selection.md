---
id: FEAT-1654
type: FEAT
priority: P3
status: open
discovered_date: '2026-05-24'
discovered_by: capture-issue
captured_at: '2026-05-24T02:32:39Z'
confidence_score: 98
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1654: Add `loop-router` built-in FSM loop for natural language loop selection and sub-loop dispatch

## Summary

Add a new built-in FSM loop `loop-router` that accepts a natural language description of a task or goal, reasons over the catalog of available built-in and project-level FSM loops, selects the best fit, runs it as a sub-loop with derived parameters, then reviews the sub-loop's output and presents a synthesized result to the user. Provides a single entry point for users who know *what they want done* but not *which loop to run*.

## Current Behavior

- Users must already know the name of the loop they want and call `ll-loop run <name>` directly.
- `/ll:loop-suggester` analyzes message history to suggest *new loops to author*, not which existing loop to dispatch right now (FEAT-219, FEAT-716).
- `ll-loop next-loop` (FEAT-1546, done) picks the next loop based on execution history under `.loops/.history/`, not from a natural language goal.
- `general-task.yaml` exists as a generic task harness but does not perform loop selection — it just runs a single agent over the input.
- There is no path from "natural language goal" → "best-fit existing loop" → "executed sub-loop" → "reviewed result".

## Expected Behavior

`ll-loop run loop-router --input "<natural language goal>"` (or `/loop /loop-router <goal>`):

1. **Catalog** — collect all available loops, *split by source*: project loops under `loops/*.yaml` and built-ins under `scripts/little_loops/loops/*.yaml` (excluding `loops/lib/` fragments per [[feedback_nested_loops_runnable]]). Read each loop's name, description, and accepted inputs into two distinct buckets.
2. **First decision (3-way classify)** — an LLM classifier looks at the goal text plus a summary of both catalogs and picks exactly one of three branches:
   - **A) Project-level loops** — the goal matches a project-specific workflow (preferred when applicable; project loops are tailored to this codebase and beat built-ins).
   - **B) Built-in loops** — the goal matches a general-purpose loop in the built-in catalog.
   - **C) Propose a new loop** — no existing loop fits *and* the goal describes a re-usable pattern worth codifying as a project loop (not a one-shot). The router does not run anything; it emits a structured proposal and (optionally) dispatches `create-loop` as a sub-loop.
3. **Score** — within the chosen bucket (A or B), use an LLM evaluator (Tier 2, per FEAT-044) to rank candidates and derive sensible parameters (input string, `--context key=value`) from the goal text.
4. **Confirm (optional)** — if top-candidate confidence is below threshold or `--auto=false`, surface the top 1-3 candidates *from the chosen bucket* (plus the strongest candidate from the other bucket, if any, as a "did you mean…" fallback) for the user to pick. With `--auto=true` (default for unattended use), proceed with the top pick.
5. **Dispatch** — invoke the selected loop as a sub-loop via the existing sub-loop mechanism (set the `loop:` field on a state; see "Codebase Research Findings" below).
6. **Review** — after the sub-loop terminates, read `${captured.sub_loop_output.output}` (the child's JSONL event stream) and synthesize a concise summary of what was attempted, what was produced, and whether it succeeded.
7. **Present** — emit a structured result (human summary + machine-readable JSON with `branch`, `loop_chosen`, `confidence`, `sub_loop_run_id`, `success`, `summary`; for branch C, `proposed_loop_spec` instead of `loop_chosen`).

## Motivation

The loop catalog has grown to 30+ built-ins plus project loops. Even experienced users default to running 2-3 familiar loops because picking the right one from a long list is friction. New users have no entry point — they know they want to "research X" or "refine that issue" but don't know whether to reach for `deep-research`, `recursive-refine`, `issue-refinement`, `rn-plan`, or something else.

`loop-router` collapses that decision into a single command. It also unlocks higher-level automation: `/loop`, scheduled agents, and on-completion hooks can dispatch *intent* ("research the auth migration") instead of hard-coding loop names, so adding a new loop to the catalog automatically makes it available to those entry points.

**Why:** Catalog growth (30+ loops) is making manual loop selection a bottleneck and a barrier to onboarding.
**How to apply:** This is a routing/dispatch layer, not a replacement for individual loops — keep selection logic in `loop-router` and leave the actual work to the sub-loops it picks.

## Proposed Solution

Add `scripts/little_loops/loops/loop-router.yaml` with these states (rough sketch — refine during design):

1. `discover_loops` — shell out to list built-in + project loops, parse names/descriptions/inputs into a catalog JSON **split into two buckets**: `project[]` and `builtin[]`. Filter out `loop-router` itself and any names in `${context.exclude}`.
2. `classify_goal` — **first decision (3-way)**. Tier 2 LLM classifier: input = (user goal, project-bucket summary, builtin-bucket summary), output = `{branch: "project" | "builtin" | "propose_new", reason, hint}`. Preference order when multiple branches look viable: project > builtin > propose_new. Route via `on_yes`/`on_no`/an evaluator that maps the branch label to a target state.
3. `score_project_loops` — Tier 2 LLM evaluator scoped to the project bucket. Output = ranked candidates with confidence + derived parameters. → `select_loop`.
4. `score_builtin_loops` — same as above, scoped to the builtin bucket. → `select_loop`.
5. `select_loop` — common merge point. If top confidence ≥ `${context.confidence_threshold}` and `${context.auto}` is true → `dispatch`; else → `present_choices`.
6. `present_choices` — HITL state showing top 3 from the chosen bucket plus the strongest candidate from the other bucket as a "did you mean…" fallback; user picks one or CANCELs. (Plain `prompt` state — HITL is a convention, not a runtime primitive.)
7. `dispatch` — regular state with `loop: "${captured.chosen.output}"`, `with: {...}`, `capture: sub_loop_output` (NOT a `type: run_sub_loop` — see Codebase Research Findings).
8. `review` — read `${captured.sub_loop_output.output}`; LLM synthesizes a result summary.
9. `propose_new_loop` — terminal-adjacent branch C path. LLM drafts a structured proposal for a new project loop (name, description, initial state graph, input keys) and emits it as a recommendation. If `${context.auto_create}` is true, dispatch `create-loop` as a sub-loop (passing the drafted spec); otherwise present the proposal to the user and exit. → `present_result`.
10. `present_result` — emit final structured output (`branch`, `loop_chosen`, `confidence`, `sub_loop_run_id`, `success`, `summary` — or `proposed_loop_spec` for branch C).

Reuse existing primitives wherever possible:
- Catalog discovery: lift logic from `/ll:loop-suggester --from-commands` and `ll-loop list --json`.
- Sub-loop dispatch: `loop:` field on a state (FEAT-1311 / FEAT-837 wired the typed `with:` binding).
- HITL fallback: model on `hitl-compare.yaml` and `hitl-md.yaml`.
- Score/classify/review: reuse the Tier 2 evaluator pattern (FEAT-044 / `evaluate: type: llm_structured`).
- Propose-new path: leverage `/ll:create-loop` skill output as the schema target for `proposed_loop_spec`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on actual code inspection (`scripts/little_loops/fsm/*`, `scripts/little_loops/cli/loop/*`, existing built-in loops):_

**Sub-loop dispatch is not a state type.** There is no `type: run_sub_loop` in the FSM schema. Sub-loop dispatch is triggered by setting the `loop:` field on any `StateConfig` — `FSMExecutor._execute_state()` checks `if state.loop is not None` and branches to `_execute_sub_loop()`. The router's `dispatch` state should be a regular state with `loop: "${captured.chosen.output}"`, `with: {...}`, `capture: sub_loop_output`, and routing via `on_yes` / `on_no` / `on_error`. See `scripts/little_loops/fsm/executor.py::_execute_sub_loop` and the canonical example in `scripts/little_loops/loops/outer-loop-eval.yaml` state `run_sub_loop` (lines 55-63 for the dispatch fields themselves; lines 65-77 are the error-terminal states it routes to).

Sub-loop routing semantics: child terminates at a state named `done` → `on_yes`; any other terminal state (e.g. `failed`) → `on_no`; child `terminated_by == "error"` → `on_error` (falls back to `on_no` if undefined); `max_iterations` / timeout / external signal → `on_no`. There is no `on_partial` routing for sub-loops.

**HITL is a design convention, not a runtime primitive.** Neither `hitl-compare.yaml` nor `hitl-md.yaml` uses any special `type: hitl` — they are composed entirely of standard `action_type: prompt` and `action_type: shell` states. The "gate on a sentinel string" pattern is a `prompt` state whose output is checked by `evaluate: type: output_contains` (see `hitl-compare.yaml::score`, lines 218-272 — actual `pattern:` is `"ALL_PASS"`, NOT `CANCEL`). The router's `present_choices` state introduces a *new* sentinel (`CANCEL`) that its own prompt must instruct the user to type — it is not borrowed from existing HITL loops.

**Tier 2 is a prompt-design tier, not a YAML keyword.** The actual evaluator name is `evaluate: type: llm_structured` (with optional `source:`, `prompt:`, `schema:`, `min_confidence:` fields — see `scripts/little_loops/fsm/evaluators.py::evaluate_llm_structured`, lines 572-581, and `DEFAULT_LLM_SCHEMA` at lines 59-84). For `score_candidates`, use a custom `schema:` returning `{loop_name, confidence, reason, parameters}` instead of the default `{verdict, confidence, reason}` (which is binary yes/no and doesn't support ranked candidates).

**CRITICAL: parsed LLM schema output is NOT exposed as a capture variable.** When `evaluate: type: llm_structured` runs with an overridden `schema:`, the parsed JSON result is stored in `EvaluationResult.details["raw"]` and emitted in the `evaluate` event — it is NOT written back into `${captured.<state>.output}`. The `output` field in `self.captured[state.capture]` always holds the action's raw stdout (the LLM's text reply for an `action_type: prompt` state). Routing via `on_yes` / `on_no` is driven by the evaluator's verdict mapping (yes/no/partial/blocked), which has no clean 3-way analog. **Design implication for the classifier**: the `classify_goal` prompt must instruct the LLM to emit the branch label as a parseable token in its text reply (e.g., a final-line marker like `BRANCH:project`), and a follow-up `action_type: shell` state must read `${captured.classify_goal.output}`, parse the marker, and route via `evaluate: type: exit_code` to one of three targets. Do NOT rely on `llm_structured` to drive 3-way routing directly.

**Catalog discovery is a one-liner, but `source` must be derived.** `ll-loop list --json` (implemented in `scripts/little_loops/cli/loop/info.py::cmd_list`, lines 53-250; merge logic at lines 115-158) merges built-in and project loops, applies project-overrides-builtin precedence by relative path, and excludes `loops/lib/` fragments via `is_runnable_loop()` (`scripts/little_loops/fsm/validation.py`, lines 897-916 — fragments lack `initial:`/`states:` keys). **The JSON output does NOT carry a `source:` field**; built-in entries carry `"built_in": true` while project entries omit the key entirely. The `discover_loops` shell must derive the bucket from `built_in` presence: `project[]` = entries lacking `"built_in"`, `builtin[]` = entries with `"built_in": true`. Subdirectory loops (e.g. `loops/oracles/`) are included with prefixed `name` values like `oracles/oracle-capture-issue`. The shell filter should: (a) drop `loop-router` itself, (b) drop names in `${context.exclude}`, (c) emit two arrays.

**No built-in recursion guard.** `_execute_sub_loop()` does not prevent a loop from dispatching itself or creating cycles. The parent FSM's `_edge_revisit_counts` mechanism detects repeated `state→state` edge traversals but does not inspect sub-loop names. A state with `loop: loop-router` inside `loop-router` would be dispatched normally until `max_iterations` is exhausted. The "router must not select router" guard must live in `loop-router.yaml` — either in the `discover_loops` shell filter (preferred — keeps the LLM's candidate pool clean) or as an explicit instruction in the `score_candidates` prompt.

**Use `context:` defaults + `input_key:`, not `parameters:`.** Only `recursive-refine.yaml` currently uses the FEAT-1311 typed `parameters:` contract. 11 loops use `input_key:` explicitly (`deep-research`, `rn-plan`, `rn-refine`, `hitl-compare`, `hitl-md`, `html-anything`, `html-website-generator`, `svg-image-generator`, `svg-textgrad`, `sprint-build-and-validate`, `sprint-refine-and-implement`, `greenfield-builder`). Others (`outer-loop-eval`, `issue-refinement`, `fix-quality-and-tests`, `general-task`) use only `context:` with no `input_key:` and receive input via `--context` at the CLI invocation level. The router needs a positional `goal`, so follow the `input_key:` convention: `input_key: goal` plus `context: {goal: "", auto: "true", confidence_threshold: "0.7", exclude: ""}`.

**Sub-loop output capture.** When `capture: sub_loop_output` is set on a sub-loop state, `_execute_sub_loop` stores `{"output": "\n".join(json.dumps(e) for e in child_events), "exit_code": None}` into `self.captured[state.capture]`. Child runs do NOT get their own `.loops/.history/<run>/` entry (the child `FSMExecutor` is instantiated without a `PersistentExecutor`); child events stream into the parent's `events.jsonl` with `"depth": N` injected. The `review` state should read `${captured.sub_loop_output.output}` (a newline-joined JSONL string), not a history folder.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml` (new)
- `scripts/little_loops/loops/README.md` — append router to built-in loops index table
- `docs/guides/LOOPS_GUIDE.md` — note router as the natural-language entry point
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"loop-router"` to the `expected` set (lines 67-121) or the test will fail

### Dependent Files (Callers/Importers)
- None at creation time; consumers are users and `/loop`/scheduled agents that may later default to `loop-router` for natural-language dispatch.

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — generic single-agent harness (closest existing primitive but doesn't route)
- `scripts/little_loops/loops/recursive-refine.yaml` — multi-state loop with sub-loop dispatch shape
- `scripts/little_loops/loops/hitl-compare.yaml` — HITL state pattern for user confirmation
- `scripts/little_loops/loops/outer-loop-eval.yaml` — orchestrating-loop pattern (FEAT-933)

### Tests
- `scripts/tests/test_loop_router.py` (new) — schema validation, state-graph structure, behavioral (live-LLM) class guarded by `@pytest.mark.skipif(shutil.which("claude") is None)`. Note: loop tests live flat at `scripts/tests/`, not `scripts/tests/loops/`.
- `scripts/tests/test_builtin_loops.py` — extend `expected` set so the loop-count guard passes

### Documentation
- `docs/ARCHITECTURE.md` — note router as the recommended natural-language entry point
- `docs/reference/API.md` — if a public Python helper is exposed
- `docs/guides/LOOPS_GUIDE.md` — author-facing reference for the new built-in
- `scripts/little_loops/loops/README.md` — catalog table entry

### Configuration
- May want a config knob like `orchestration.router.confidence_threshold` and `orchestration.router.exclude_loops: []` in `.ll/ll-config.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current code (re-verified 2026-05-24 in second refine pass):_

- **Catalog enumeration**: `scripts/little_loops/cli/loop/info.py::cmd_list` (lines 53-250; merge logic at lines 115-158) — already merges built-in + project, excludes `loops/lib/` via `is_runnable_loop()`, applies project-overrides-builtin precedence. Use `ll-loop list --json` directly from `discover_loops`.
- **Catalog filter gate**: `scripts/little_loops/fsm/validation.py::is_runnable_loop` (lines 897-916) — the sole `loops/lib/` exclusion mechanism (no path-based blacklist).
- **`source` derivation**: JSON output does NOT carry a `source:` key — built-in entries carry `"built_in": true`, project entries omit it. The `discover_loops` filter splits via `built_in` presence (NOT a missing `source` field).
- **Sub-loop dispatch**: `scripts/little_loops/fsm/executor.py::_execute_sub_loop` — branched into when `state.loop is not None`. No `type: run_sub_loop` exists.
- **FEAT-1311 `with:` binding**: `scripts/little_loops/fsm/schema.py::ParameterSpec` (lines 181-200+), validated at load time by `scripts/little_loops/fsm/validation.py::_validate_with_bindings`.
- **Tier 2 evaluator**: `scripts/little_loops/fsm/evaluators.py::evaluate_llm_structured` (signature at lines 572-581), with `DEFAULT_LLM_SCHEMA` at lines 59-84 and `DEFAULT_LLM_PROMPT` at line 86. Default verdict enum: `["yes", "no", "blocked", "partial"]` — override `schema:` for ranked candidate output.
- **Parsed LLM output is NOT a capture variable.** When `schema:` is overridden, `${captured.<name>.output}` still contains the action's raw stdout (the LLM's text reply). The parsed schema dict lives in the `evaluate` event's `details["raw"]` and is not surfaced as a context variable. Routing on a 3-way classifier therefore requires the LLM prompt to embed a parseable branch marker in its text reply (e.g., a sentinel like `BRANCH:project` on the final line), then a follow-up `action_type: shell` state reads `${captured.classify_goal.output}`, parses the marker, and exits with a code that drives `evaluate: type: exit_code` routing to the three target states.
- **Canonical `run_sub_loop` reference**: `scripts/little_loops/loops/outer-loop-eval.yaml::run_sub_loop` (lines 55-63 for the dispatch fields; lines 65-77 are the error-terminal states it routes to) — copy this shape directly.
- **Canonical `llm_structured` with `min_confidence`**: `scripts/little_loops/loops/outer-loop-eval.yaml::generate_report` (state body lines 90-111; evaluate block lines 99-111) and `scripts/little_loops/loops/loop-specialist-eval.yaml::check_skill` (state body lines 32-53; evaluate block lines 37-51).
- **Reusable fragments**: `scripts/little_loops/loops/lib/common.yaml` provides `with_rate_limit_handling` (used by `recursive-refine.yaml::run_refine`) — apply this to the `dispatch` state to inherit 429 resilience.
- **Persistence**: `scripts/little_loops/fsm/persistence.py` — child sub-loops do NOT write their own `.loops/.history/` entry (no `PersistentExecutor` is wired in for children); their events stream into the parent's `events.jsonl` with `"depth": N` injected by `_execute_sub_loop`. The `review` state reads `${captured.sub_loop_output.output}` (a JSONL string), not a history folder.
- **Test templates**: `scripts/tests/test_outer_loop_eval.py` (primary — file/state structural tests with `load_and_validate`), `scripts/tests/test_feat1544_loop_specialist_eval.py` (secondary — adds `@pytest.mark.slow` live-LLM class).
- **Built-in loop guard set**: `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` is at lines 65-121 (slight drift from earlier claim of 67-121). Current `expected` set has 51 entries; adding `"loop-router"` requires extending the literal set or `assert expected == actual` will fail. The test uses `glob("*.yaml")` (not `rglob`), so subdirectory loops (e.g. `loops/oracles/`) are NOT in this set — placing `loop-router.yaml` at the flat root is required for it to be tracked here.

### Pattern Precedents (Refinement Pass 2 — pattern-finder agent)

- **NO YAML precedent for custom `schema:` in `llm_structured`.** Every existing usage relies on `DEFAULT_LLM_SCHEMA` (verdict enum `yes`/`no`/`blocked`/`partial`). The dataclass `EvaluateConfig.schema: dict[str, Any] | None` (`fsm/schema.py:74`) accepts it and `evaluate_llm_structured()` honors it (`fsm/evaluators.py:572-575`), but `loop-router.yaml` would be the FIRST loop to exercise this code path. Implementer must (a) verify YAML→dict round-trip preserves the nested schema, (b) verify `evaluate` event details carry the parsed result for debugging.
- **`fragment: shell_exit`** (defined in `lib/common.yaml`) wraps `action_type: shell` + `evaluate: type: exit_code` — use this for `route_branch` instead of declaring both inline. Reference: `recursive-refine.yaml::check_attempt_budget` (lines 108-146).
- **`on_success` / `on_failure` are aliases** for `on_yes` / `on_no` — both forms exist in built-ins and are interchangeable (`scan-and-implement.yaml::implement`, `auto-refine-and-implement.yaml::refine_issue`).
- **Alternative 3-way routing**: `DEFAULT_LLM_SCHEMA` supports up to 5 branches via `on_yes` / `on_no` / `on_partial` / `on_blocked` / `on_error` (see `harness-single-shot.yaml::check_semantic` lines 113-131 for `on_partial`, `issue-staleness-review.yaml::triage` lines 37-50 for `on_blocked`). The router could theoretically map `yes`→project, `no`→builtin, `partial`→propose_new, but the verdict semantics get confusing — the two-state (classify + `route_branch` shell parser) approach in step 3 is cleaner and self-documenting.
- **NO YAML precedent for `ll-loop list --json` inside a state.** Closest analog is `ll-issues list --json | python3 -c "..."` in `recursive-refine.yaml::capture_baseline` (lines 156-163) and `scan-and-implement.yaml::snapshot_pre` (lines 18-28) — copy the shell-+-Python-heredoc shape for `discover_loops`.
- **NO YAML precedent for structured-JSON terminal emission.** All existing `terminal: true` states emit human-readable text (`recursive-refine.yaml::done` lines 668-816 via shell `printf`; `hitl-compare.yaml::done` lines 274-297 via prompt) or nothing (`general-task.yaml::done` line 151; `outer-loop-eval.yaml::done` lines 124-125). The router's `present_result` state must invent the JSON emission pattern — use `action_type: shell` with a Python heredoc printing `json.dumps(...)` to stdout, modeled on the recursive-refine summary shape.
- **HITL sentinel is `ALL_PASS` / `ITERATE`** in both `hitl-compare.yaml` and `hitl-md.yaml`. `CANCEL` is router-specific — the router's `present_choices` prompt must instruct the user to type it; copy the prompt-construction shape from `hitl-compare.yaml::score` lines 223-270.
- **Test gating decorators**: exact `@pytest.mark.skipif(shutil.which("claude") is None, reason="live LLM required; skip in CI unless claude CLI is available")` + `@pytest.mark.slow` sequence is at `test_feat1544_loop_specialist_eval.py:163-167` — copy verbatim.

## Implementation Steps

1. **Draft the YAML skeleton** — create `scripts/little_loops/loops/loop-router.yaml` modeled on `outer-loop-eval.yaml` (closest existing orchestrator). Use `input_key: goal` and `context: {goal, auto, auto_create, confidence_threshold, exclude}`. Validate with `ll-loop validate scripts/little_loops/loops/loop-router.yaml`.
2. **Catalog discovery state (`discover_loops`)** — `action_type: shell` that runs `ll-loop list --json` (already excludes `loops/lib/`) and pipes through a Python filter to (a) drop `loop-router` itself, (b) drop any names in `${context.exclude}`, (c) **split into two arrays**: `project[]` and `builtin[]`. Write `{project: [...], builtin: [...]}` to `.loops/tmp/loop-router-catalog.json` and `capture: catalog`.
3. **Classifier state (`classify_goal`) + router (`route_branch`)** — **3-way first decision**. Because `${captured.<name>.output}` holds the action's raw stdout (not the parsed `llm_structured` JSON — see Codebase Research Findings), the prompt must instruct the LLM to emit a parseable branch marker on its final line (e.g., `BRANCH:project`, `BRANCH:builtin`, `BRANCH:propose_new`). `classify_goal` uses `action_type: prompt` with `evaluate: type: llm_structured`, `source: "${captured.catalog.output}"`, and `schema:` returning `{branch: enum["project", "builtin", "propose_new"], confidence: number, reason: string}` (the structured evaluation enforces JSON discipline even though it doesn't drive routing). Prompt instructs: prefer `project` when any project loop plausibly fits; fall back to `builtin`; pick `propose_new` only when nothing fits AND the goal describes a re-usable workflow (not a one-shot). Capture as `classification`. Add a follow-up `route_branch` state with `action_type: shell` that greps `${captured.classification.output}` for the marker and exits 0/1/2 (or three chained `output_contains` checks), driving routing to `score_project_loops` / `score_builtin_loops` / `propose_new_loop`.
4. **Bucketed scoring states (`score_project_loops`, `score_builtin_loops`)** — two near-identical `action_type: prompt` states differing only in which bucket they pass into the prompt. Each uses `evaluate: type: llm_structured` with `source` filtered to the relevant bucket and a custom `schema:` returning `{loop_name, confidence, reason, parameters, top_candidates: [...]}`. Set `min_confidence: 0.7`. Both → `select_loop`. Model on `outer-loop-eval.yaml::generate_report` (lines 99-111).
5. **Selection gate (`select_loop`)** — common merge point. `action_type: shell` comparing `${context.confidence_threshold}` against the captured score and checking `${context.auto}`. Use `evaluate: type: exit_code` with `on_yes: dispatch`, `on_no: present_choices`. Reference `auto-refine-and-implement.yaml::get_next_issue` (lines 26-34) for shell-driven routing.
6. **HITL fallback (`present_choices`)** — `action_type: prompt` printing top 3 candidates from the chosen bucket plus the best candidate from the other bucket as a "did you mean…" fallback. `capture: user_choice`, `evaluate: type: output_contains` with `pattern: "CANCEL"` → `on_yes: done`, `on_no: dispatch`. Model the *shape* on `hitl-compare.yaml::score` (lines 218-272), which uses the same `output_contains` pattern but with sentinel `"ALL_PASS"`. `CANCEL` is a router-specific sentinel — the prompt itself must instruct the user to type `CANCEL` to abort.
7. **Dispatch state** — regular state with `loop: "${captured.chosen.output}"`, `with: {input: "${captured.derived_params.output}"}`, `capture: sub_loop_output`, `on_yes: review`, `on_no: review`, `on_error: review`. Apply `fragment: with_rate_limit_handling` from `lib/common.yaml` for 429 resilience. Copy the YAML shape verbatim from `outer-loop-eval.yaml::run_sub_loop` (lines 55-63 for the dispatch fields).
8. **Review state** — `action_type: prompt` that reads `${captured.sub_loop_output.output}` (JSONL string of child events) and synthesizes a summary. Use `evaluate: type: llm_structured` with a `{success: bool, summary: string}` schema. The child does NOT write its own `.loops/.history/` entry — child events live in the parent's `events.jsonl` with `"depth": N`.
9. **Propose-new branch (`propose_new_loop`)** — `action_type: prompt`, `evaluate: type: llm_structured` with `schema:` returning `{name, description, input_key, initial, states_summary, rationale}` (mirrors the input format of `/ll:create-loop`). If `${context.auto_create}` is `"true"`, transition to a sub-loop dispatch state that runs `create-loop` (when a YAML wrapper exists) or shells out to the skill; otherwise → `present_result`. The proposal is emitted in the structured result as `proposed_loop_spec`.
10. **Present result (terminal)** — `action_type: shell` that emits the structured JSON output (`branch`, `loop_chosen` or `proposed_loop_spec`, `confidence`, `parameters`, `sub_loop_run_id`, `success`, `summary`) before `terminal: true`. Model on `recursive-refine.yaml::done` for the non-empty terminal pattern.
11. **Tests** — create `scripts/tests/test_loop_router.py` (flat, not under `tests/loops/`) mirroring `scripts/tests/test_outer_loop_eval.py`: file/state structural tests using `load_and_validate`, then `test_run_sub_loop_dispatch` asserting `state.loop is not None` for the dispatch state. Add structural tests asserting all three branch targets (`score_project_loops`, `score_builtin_loops`, `propose_new_loop`) are reachable from `classify_goal`. Add an optional `@pytest.mark.slow` live-LLM behavioral class guarded by `@pytest.mark.skipif(shutil.which("claude") is None)` covering all three branches.
12. **Update the builtin loop guard** — add `"loop-router"` to the `expected` set in `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` (lines 65-121; current `expected` has 51 entries). The test enforces an exact set match via `assert expected == actual` and will fail otherwise. The glob is non-recursive (`glob("*.yaml")`), so `loop-router.yaml` must live at the flat `scripts/little_loops/loops/` root, not in a subdirectory.
13. **Docs** — append to `scripts/little_loops/loops/README.md` (built-in loops table) and `docs/guides/LOOPS_GUIDE.md`. Note router as the recommended natural-language entry point and document the 3-way branch behavior.
14. **Verification** — run against representative goals for each branch:
    - **A (project)**: `"refine FEAT-1654"` → project `issue-refinement` (if present) or `rn-refine`.
    - **B (built-in)**: `"research auth middleware patterns"` → `deep-research`; `"build a static landing page"` → `html-website-generator`.
    - **C (propose_new)**: `"every Friday, summarize merged PRs and post to Slack"` → branch C with a drafted loop spec.
    - Confirm: 3-way classification correctness, no-match-within-bucket → HITL with cross-bucket fallback, recursion guard rejects `"run loop-router"`, branch C without `auto_create` does not run anything.

## Use Case

> "I want to dig into how our auth middleware handles refresh tokens — research the patterns and current pitfalls."

`loop-router` ingests this, scores candidates, picks `deep-research` (FEAT-1540), derives `--input "auth middleware refresh token handling: patterns and pitfalls"`, dispatches it as a sub-loop, then summarizes the produced research report and points the user to the artifact path.

> "Refine FEAT-1654 so it's ready to implement."

Router picks `issue-refinement` (or `rn-refine` per [[project_recursive_refine_standalone]]) and dispatches it with the issue ID parsed from the goal.

## API/Interface

```yaml
# scripts/little_loops/loops/loop-router.yaml (sketch — corrected against actual schema)
name: loop-router
description: Route a natural language goal to the best-fit FSM loop (project or built-in) — or propose a new loop.
category: routing
input_key: goal              # CLI positional arg → context.goal
initial: discover_loops
max_iterations: 20
timeout: 7200
on_handoff: spawn
context:
  goal: ""                   # populated via input_key
  auto: "true"               # dispatch top candidate without confirmation
  auto_create: "false"       # if propose_new branch chosen, actually invoke create-loop
  confidence_threshold: "0.7"
  exclude: ""                # comma-separated loop names
states:
  discover_loops: { action_type: shell, ... }     # `ll-loop list --json` → {project: [...], builtin: [...]} (filtered)

  # FIRST DECISION — 3-way classifier (two-state pattern: classify + parse)
  classify_goal:
    action_type: prompt          # prompt must instruct LLM to emit `BRANCH:<label>` on final line
    evaluate:
      type: llm_structured
      schema: { branch: { enum: [project, builtin, propose_new] }, confidence, reason }
    capture: classification
    on_yes: route_branch         # llm_structured can't do 3-way routing; parse marker in a follow-up
  route_branch:
    action_type: shell           # greps ${captured.classification.output} for BRANCH:<label>, exits 0/1/2
    evaluate: { type: exit_code }
    on_yes: score_project_loops  # exit 0 → project
    on_no: score_builtin_loops   # exit 1 → builtin
    on_error: propose_new_loop   # exit 2 → propose_new

  # BRANCH A
  score_project_loops:
    action_type: prompt
    evaluate: { type: llm_structured, schema: {...}, min_confidence: 0.7 }
    on_yes: select_loop
  # BRANCH B
  score_builtin_loops:
    action_type: prompt
    evaluate: { type: llm_structured, schema: {...}, min_confidence: 0.7 }
    on_yes: select_loop

  # Common dispatch path for branches A and B
  select_loop:    { action_type: shell, evaluate: { type: exit_code }, on_yes: dispatch, on_no: present_choices }
  present_choices: { action_type: prompt, evaluate: { type: output_contains, pattern: "CANCEL" } }
  dispatch:                                       # NOT a `type: run_sub_loop` — `loop:` field triggers dispatch
    loop: "${captured.chosen.output}"
    with: { input: "${captured.derived_params.output}" }
    capture: sub_loop_output
    on_yes: review
    on_no: review                                 # still synthesize on failure
    on_error: review
  review: { action_type: prompt, ... }            # reads ${captured.sub_loop_output.output}

  # BRANCH C
  propose_new_loop:
    action_type: prompt
    evaluate:
      type: llm_structured
      schema: { name, description, input_key, initial, states_summary, rationale }
    # if context.auto_create == "true", dispatch create-loop as a sub-loop; else → present_result

  present_result: { terminal: true, ... }
  failed: { terminal: true }
```

Output schema (structured) — branches A/B:

```json
{
  "branch": "builtin",
  "loop_chosen": "deep-research",
  "confidence": 0.86,
  "parameters": { "input": "..." },
  "sub_loop_run_id": ".loops/.history/2026-05-24T...-deep-research/",
  "success": true,
  "summary": "Produced a research report at .../report.md covering ..."
}
```

Output schema — branch C (propose_new):

```json
{
  "branch": "propose_new",
  "confidence": 0.74,
  "proposed_loop_spec": {
    "name": "weekly-pr-digest",
    "description": "Summarize merged PRs from the last week and post to Slack.",
    "input_key": "channel",
    "initial": "collect_prs",
    "states_summary": ["collect_prs", "summarize", "post_to_slack"],
    "rationale": "Recurring weekly pattern; no built-in or project loop covers PR digest + Slack post."
  },
  "success": false,
  "summary": "No existing loop fit. Drafted a re-usable project loop. Run `/ll:create-loop` (or rerun with --context auto_create=true) to author it."
}
```

## Edge Cases

- **No good match within the chosen bucket** — scoring stage clears nothing above floor: surface HITL with top-3 weak candidates *plus the strongest candidate from the other bucket* as a "did you mean…" fallback. User can CANCEL to fall through to `propose_new_loop`.
- **Classifier picks `project` but project bucket is empty** — short-circuit to `score_builtin_loops` (don't waste an LLM call scoring an empty bucket).
- **Classifier picks `builtin` but a perfect project match exists** — the classifier prompt must explicitly prefer project loops when applicable; if this misfires often, add a deterministic pre-pass that promotes obvious project matches before classification.
- **Classifier picks `propose_new` but a re-usable pattern isn't obvious** — degrade to general-task fallback or surface "no fit + not clearly re-usable, here's what I considered" rather than force a proposal.
- **Ambiguous goal within a bucket** — two or more candidates score within a small delta: always go to HITL regardless of `auto`.
- **Branch C without `auto_create`** — emit `proposed_loop_spec` and exit; do NOT dispatch anything. The user explicitly opts in to creation via `--context auto_create=true` or by manually running `/ll:create-loop`.
- **Sub-loop fails** — review state must surface the failure (not retry by default) and include the sub-loop's error in the summary.
- **Project loop with same name as built-in** — prefer project loop (matches existing precedence in `ll-loop list`).
- **Goal includes a loop name** — short-circuit ("just run `autodev`"): skip classification + scoring, dispatch directly.
- **Recursion guard** — `loop-router` must not select `loop-router` as the sub-loop (catalog filter in `discover_loops`). Likewise, `create-loop` dispatched via branch C must not be allowed to dispatch `loop-router` (handled by `create-loop` itself, not enforced here).

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/loop-router.yaml` exists and passes `ll-loop validate`.
- [ ] `ll-loop run loop-router --input "..."` produces a structured result; for branches A/B, also a sub-loop run captured in the parent's `events.jsonl` with `"depth": N`.
- [ ] Catalog discovery splits results into `project[]` and `builtin[]`, excludes `loops/lib/` fragments, `loop-router` itself, and `${context.exclude}`.
- [ ] **First decision is 3-way**: `classify_goal` reaches one of `score_project_loops`, `score_builtin_loops`, or `propose_new_loop` on each run. All three branches are exercised by tests.
- [ ] Branch A (project) runs the chosen project loop; branch B (built-in) runs the chosen built-in; branch C (propose_new) emits a `proposed_loop_spec` and does NOT dispatch unless `${context.auto_create}` is true.
- [ ] When confidence < threshold within a bucket, HITL surfaces top 3 candidates from that bucket plus the strongest candidate from the other bucket as a "did you mean…" fallback.
- [ ] Final output includes `branch`, `confidence`, `success`, `summary`; A/B add `loop_chosen` + `sub_loop_run_id`; C adds `proposed_loop_spec`.
- [ ] Test coverage for: 3-way classification correctness (one representative goal per branch), no-match-within-bucket path, HITL path, sub-loop failure path, branch C without `auto_create` (proposal-only).
- [ ] `scripts/tests/test_loop_router.py` exists (flat path, mirroring `test_outer_loop_eval.py`) and asserts all three branch targets are reachable from `classify_goal`.
- [ ] `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` includes `"loop-router"` in the `expected` set.
- [ ] Docs reference `loop-router` as the recommended natural-language entry point and document the 3-way branch behavior (`scripts/little_loops/loops/README.md` table entry + `docs/guides/LOOPS_GUIDE.md` mention).

## Impact

- **Priority**: P3 — meaningful UX improvement and unlocks downstream automation, but not blocking. Several similar built-in loops (`deep-research`, `rn-plan`) shipped at P3.
- **Effort**: Medium — composes existing primitives (catalog discovery, Tier 2 evaluator, `run_sub_loop`, HITL fragments). Most work is in the routing prompt and the review/synthesis state.
- **Risk**: Low-medium — the failure mode is "picks the wrong loop", which is recoverable (user re-runs with explicit loop name). Watch for recursion (router → router) and prompt-injection in the goal text.

## Related Key Documentation

| Document | Why Relevant |
|----------|-------------|
| `docs/ARCHITECTURE.md` | Where router fits in the FSM/loop architecture |
| `docs/reference/API.md` | Sub-loop dispatch and state-type APIs |
| `.claude/CLAUDE.md` | Built-in loop conventions and CLI tooling overview |

## Labels

built-in-loop, fsm, routing, dispatch, sub-loop

## Session Log
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/97139a79-dcef-4b4c-81a6-1f92ca838d7f.jsonl`
- `/ll:refine-issue` - 2026-05-24T05:59:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3ba6256-c98b-41f3-aa42-08b4d281735f.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c95a88a-c371-475b-bf49-5d58dbcf7c25.jsonl`
- `/ll:refine-issue` - 2026-05-24T05:31:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b12732b3-3fbc-45ff-97ff-40b2acebd193.jsonl`
- `/ll:format-issue` - 2026-05-24T02:35:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9eaefb33-d00d-4955-9bd3-f90c748f44ef.jsonl`
- `/ll:capture-issue` - 2026-05-24T02:32:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ba66e45-43d3-4537-a63b-088dff9cbb2f.jsonl`
- `/ll:refine-issue` - 2026-05-24T08:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73db8a10-ad41-49e8-a62e-6cbe1b3b0ebf.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P3
