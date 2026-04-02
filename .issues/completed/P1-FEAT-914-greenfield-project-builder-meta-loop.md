---
discovered_date: "2026-04-02"
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 79
---

# FEAT-914: Greenfield Project Builder Meta-Loop

## Summary

Create two new built-in FSM loops in `scripts/little_loops/loops/`:

1. **`eval-driven-development.yaml`** — A reusable inner loop that runs an eval harness, captures issues from findings, refines them to readiness, implements fixes, and cycles until the harness passes or the iteration budget is exhausted. Usable by any project with an eval harness, not just greenfield builds.

2. **`greenfield-builder.yaml`** — The outer meta-loop that drives a full greenfield project lifecycle: spec decomposition → eval harness creation → issue creation → refinement → then delegates the improvement cycle to `eval-driven-development` as a sub-loop.

The outer loop accepts one or more project spec Markdown files as input and autonomously drives the project from zero to a working, evaluated implementation. The inner loop is extracted as a standalone primitive so it can be independently tested, tuned, and reused by other workflows (e.g., hardening an existing project, post-refactor validation).

## Current Behavior

No built-in loop exists for end-to-end greenfield project implementation. Users must manually orchestrate multiple skills and loops (`issue-refinement`, `ll-auto`, harness loops, etc.) in sequence. There is no single automation that takes a spec file and drives continuous implementation cycles.

## Expected Behavior

Running `ll-loop run greenfield-builder -- spec=path/to/spec.md` (or multiple specs via comma-separated list) should:

**Outer loop (`greenfield-builder`):**

1. Read and analyze the spec file(s)
2. Research technology decisions — produce `docs/research.md` (tech choices, library comparisons, rejected alternatives)
3. Create design artifacts — produce `docs/data-model.md`, `docs/contracts/`, `docs/quickstart.md`; commit
4. Plan and create an as-a-user eval harness (per AUTOMATIC_HARNESSING_GUIDE.md), informed by design artifacts
5. Create P1 FEAT issues for the eval harness
6. Decompose specs into FEAT and ENH issues via `/ll:capture-issue`, referencing research and design artifacts
7. Normalize and commit issues
8. Refine all issues via the `issue-refinement` sub-loop
9. Run `/ll:tradeoff-review-issues` to annotate issues with viability notes
10. Invoke `eval-driven-development` as a sub-loop → done when it terminates

**Inner loop (`eval-driven-development`):**

1. Implement viable issues via `ll-auto`
2. Run the eval harness, capture results
3. Create/update issues from eval findings via `/ll:capture-issue`, commit
4. Refine new issues via the `issue-refinement` sub-loop
5. Run `/ll:tradeoff-review-issues` on new issues
6. Route: eval passed all gates → done. Otherwise → back to step 1

## Motivation

Greenfield projects require orchestrating many little-loops capabilities in a specific order. This meta-loop is the "outer brain" that composes existing primitives into a full project build pipeline. It enables a user to hand off a spec and walk away while the system builds, evaluates, and iterates. This is the highest-leverage automation the plugin can offer — it turns little-loops from a toolkit into an autonomous project builder.

## Use Case

A developer has a project specification document (`spec.md`) describing a new CLI tool. They run `ll-loop run greenfield-builder -- spec=spec.md`. The loop reads the spec, creates an eval harness that tests the CLI from a user perspective, decomposes the spec into 12 FEAT and 5 ENH issues, refines them all to implementation-ready quality, implements them in priority order, runs the eval harness to catch gaps, and creates new issues from evaluation findings. The cycle continues until the eval harness passes or the iteration budget is exhausted.

## Acceptance Criteria

### Inner loop (`eval-driven-development.yaml`)

- [ ] `eval-driven-development.yaml` exists in `scripts/little_loops/loops/` and passes `ll-loop validate`
- [ ] Accepts `harness_name` context variable (name of harness loop to run)
- [ ] Accepts `readiness_threshold` and `outcome_threshold` context variables (with defaults from `ll-config.json` canonical values)
- [ ] Implements viable issues via `ll-auto` (`action_type: shell`)
- [ ] Runs the harness loop via `action_type: shell` with `ll-loop run ${context.harness_name}`, captures stdout (`capture: run_harness`), routes unconditionally to `capture_issues` — `loop: ${context.*}` interpolation is unsupported (`executor.py:585`); see `rl-coding-agent.yaml:37-44` for the established workaround pattern
- [ ] Creates/updates issues from eval findings via `/ll:capture-issue`
- [ ] Refines new issues via `issue-refinement` sub-loop (`loop:` field with `context_passthrough`)
- [ ] Runs `/ll:tradeoff-review-issues` on new issues
- [ ] Routes: eval gates pass → `done`; otherwise → back to implement
- [ ] Periodic commits via `/ll:commit` at natural phase boundaries
- [ ] Has own `max_iterations`, `timeout`, and `on_handoff: spawn` configured appropriately

### Outer loop (`greenfield-builder.yaml`)

- [ ] `greenfield-builder.yaml` exists in `scripts/little_loops/loops/` and passes `ll-loop validate`
- [ ] Accepts `spec` input parameter (single path or comma-separated paths to Markdown spec files)
- [ ] Produces `docs/research.md` with technology decisions, library comparisons, and rejected alternatives before issue decomposition
- [ ] Produces `docs/data-model.md` with entity definitions traceable to spec requirements
- [ ] Produces `docs/contracts/` with interface definitions (API/CLI/service boundaries)
- [ ] Produces `docs/quickstart.md` with observable validation scenarios
- [ ] Design artifacts are committed before harness planning begins
- [ ] Plans and creates a harness loop YAML dynamically based on the spec (using patterns from AUTOMATIC_HARNESSING_GUIDE.md)
- [ ] Creates P1 FEAT issues for the eval harness itself
- [ ] Decomposes spec into FEAT and ENH issues using `/ll:capture-issue`; `spec_decomposition` prompt references `${captured.tech_research.output}` and `${captured.design_artifacts.output}`
- [ ] Invokes `issue-refinement` as a sub-loop for initial refinement pass
- [ ] Runs `/ll:tradeoff-review-issues` and updates issues with findings
- [ ] Invokes `eval-driven-development` as a sub-loop (via `loop:` field with `context_passthrough`), passing `harness_name`
- [ ] Has `max_iterations`, `timeout`, and `on_handoff: spawn` configured appropriately

## API/Interface

```yaml
# Outer loop invocation:
# ll-loop run greenfield-builder -- spec=path/to/spec.md
# ll-loop run greenfield-builder -- spec=spec1.md,spec2.md

# greenfield-builder context variables:
context:
  spec: ""           # required: path(s) to spec file(s), comma-separated
  max_issues: 30     # max issues to create per decomposition pass
  harness_name: ""   # auto-generated: name of created harness loop
```

```yaml
# Inner loop invocation (standalone):
# ll-loop run eval-driven-development -- harness_name=my-harness

# eval-driven-development context variables:
context:
  harness_name: ""            # required: name of harness loop to run
  readiness_threshold: 90     # canonical: commands.confidence_gate.readiness_threshold in ll-config.json
  outcome_threshold: 75       # canonical: commands.confidence_gate.outcome_threshold in ll-config.json
```

## Proposed Solution

### Architecture: Two-Loop Decomposition

The original 9-phase monolithic design is split into two composable loops:

```
greenfield-builder (outer)
  ├── Phase 1-6: One-time setup (spec → research → design → harness → issues)
  ├── Phase 7-9: Initial refinement + tradeoff review
  └── Phase 10:  loop: eval-driven-development  ← sub-loop
                   ├── implement (ll-auto)
                   ├── run harness
                   ├── capture issues from findings
                   ├── refine new issues (loop: issue-refinement)
                   ├── tradeoff review
                   └── route: pass → done, fail → back to implement
```

**Why two loops?**
- The eval→fix cycle is independently useful — any project with a harness can use it (hardening existing projects, post-refactor validation, regression hunting)
- Separate iteration budgets: outer loop runs ~5-10 macro cycles, inner runs ~15-20 micro cycles per invocation
- Each loop can be validated and tested independently with `ll-loop validate` and `ll-loop test`
- Follows the established composition pattern: `issue-refinement.yaml` → `refine-to-ready-issue.yaml`

### Inner Loop: `eval-driven-development.yaml`

Structural analog: `agent-eval-improve.yaml` (eval → score → analyze → refine → re-eval cycle with convergence routing). This is the issue-management equivalent of that RL pattern.

**States:**

1. **`implement`** — `action_type: shell` with `ll-auto --priority P1,P2` to implement viable issues. Follow `docs/generalized-fsm-loop.md:26-30` pattern.

2. **`commit_impl`** — `action_type: prompt` with `/ll:commit`. Commit implementation changes before evaluation.

3. **`run_harness`** — `action_type: shell` with `ll-loop run ${context.harness_name}`, `capture: run_harness`, `next: capture_issues` (unconditional — result evaluation deferred to `route_eval`). Pass context via explicit `--context` flags. **Do NOT use `loop: ${context.harness_name}`** — `_execute_sub_loop` passes `state.loop` raw to `resolve_loop_path()` at `executor.py:585` without interpolation; the literal string `"${context.harness_name}"` would cause `FileNotFoundError`. Established workaround pattern: `rl-coding-agent.yaml:37-44`.

4. **`capture_issues`** — `action_type: prompt`. Analyze harness results from `${captured.run_harness.output}`, create issues from failures/gaps via `/ll:capture-issue`, normalize with `/ll:normalize-issues`.

5. **`commit_eval`** — `action_type: prompt` with `/ll:commit`. Commit new issues and eval findings.

6. **`route_eval`** — `evaluate.type: llm_structured` on `${captured.run_harness.output}`. Did all harness gates pass? `on_yes` → `done`, `on_no` → `refine_issues`.

7. **`refine_issues`** — `loop: issue-refinement`, `context_passthrough: true`. Refine newly captured issues to implementation readiness.

8. **`tradeoff_review`** — `action_type: prompt` with `/ll:tradeoff-review-issues`. Annotate issues with viability notes, commit. `next: implement`.

9. **`done`** — `terminal: true`.

**Configuration:** `max_iterations: 20`, `timeout: 14400` (4 hours), `on_handoff: spawn`.

### Outer Loop: `greenfield-builder.yaml`

Follows the phased pipeline pattern from `sprint-build-and-validate.yaml` with sub-loop invocations.

**Phase 1 — Initialization**: `action_type: shell` to validate spec file(s) exist, read contents. `capture: spec_content`.

**Phase 2 — Technology Research**: `action_type: prompt` to analyze the spec and research technology decisions. Writes `docs/research.md` with: Technology Decisions table, Library Comparisons, Rejected Alternatives, Security & Platform Notes. `capture: tech_research`. `next: design_artifacts`.

**Phase 3 — Design Artifacts**: `action_type: prompt` referencing `${captured.spec_content.output}` and `${captured.tech_research.output}`. Produces:
- `docs/data-model.md` — key entities with fields, types, relationships, constraints (spec-traceable only)
- `docs/contracts/` — one file per major interface boundary (operation name, inputs, outputs, error cases)
- `docs/quickstart.md` — 3-5 observable validation scenarios in prose

`capture: design_artifacts`. `next: commit_design`.

**Phase 4 — Commit Design**: `action_type: prompt` with `/ll:commit`. Commits research and design artifacts before any issue work begins. `next: harness_planning`.

**Phase 5 — Eval Harness Planning**: `action_type: prompt` to analyze the spec and design artifacts and plan an as-a-user eval harness following patterns in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`. References `${captured.design_artifacts.output}` so the harness targets concrete API contracts and data-model entities. Output a harness YAML to `.loops/`. `capture: harness_plan`.

**Phase 6 — Harness Issue Creation**: `action_type: prompt` to create P1 FEAT issues for the eval harness using `/ll:capture-issue`.

**Phase 7 — Spec Decomposition**: `action_type: prompt` to analyze spec file(s) and create FEAT/ENH issues via `/ll:capture-issue`, then normalize with `/ll:normalize-issues` and commit. References `${captured.tech_research.output}` and `${captured.design_artifacts.output}` so issues name specific entities, contracts, and chosen technologies rather than abstract spec language.

**Phase 8 — Issue Refinement**: `loop: issue-refinement`, `context_passthrough: true`. Initial refinement pass on all decomposed issues.

**Phase 9 — Tradeoff Review**: `action_type: prompt` with `/ll:tradeoff-review-issues` and `/ll:commit`.

**Phase 10 — Eval-Driven Improvement**: `loop: eval-driven-development`, `context_passthrough: true`. The outer loop's `harness_name` context variable flows through to the inner loop. Inner loop handles the implement→eval→fix cycle autonomously.

**Done** — `terminal: true`.

**Configuration:** `max_iterations: 20`, `timeout: 28800` (8 hours), `on_handoff: spawn`.

### Key Design Decisions

- Inner loop is a standalone reusable primitive — invocable directly via `ll-loop run eval-driven-development -- harness_name=...` or as a sub-loop
- Use `action_type: prompt` for phases requiring LLM reasoning (spec analysis, issue decomposition, eval planning)
- Use `loop:` sub-loop states for `issue-refinement`, `eval-driven-development`, and the harness evaluation
- Use `action_type: shell` for `ll-auto` invocation and deterministic checks
- Use `context_passthrough: true` on all sub-loop states to share captured data and flow `harness_name`
- Commit at natural phase boundaries (after decomposition, after implementation, after evaluation)
- `on_handoff: spawn` on both loops to support session continuity across long runs

### Reference Patterns

- Sub-loop invocation: `issue-refinement.yaml:29-33` (`loop: refine-to-ready-issue`, `context_passthrough: true`)
- Eval→refine cycle analog: `agent-eval-improve.yaml:1-91` (eval → score → analyze → refine → re-eval with convergence routing)
- Phased prompt pipeline: `sprint-build-and-validate.yaml:12-116` (assess → create → validate → fix → review with `capture` chaining)
- Periodic commits: `backlog-flow-optimizer.yaml:125-130` (commit state between phases)
- Counter-gated commits: `issue-refinement.yaml:34-52` (shell counter file + `output_contains` to commit every N cycles)
- Context variables: `general-task.yaml:9` (`${context.input}`) and `refine-to-ready-issue.yaml:5-7` (child receiving parent context)
- Harness patterns: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Variant A (single-shot) and Variant B (multi-item)
- Shell CLI invocation: `docs/generalized-fsm-loop.md:26-30` (`ll-auto --max-issues 5` with `action_type: shell`)
- Sub-loop with diverging outcomes: `prompt-regression-test.yaml:88-93` (`on_success`/`on_failure` routing)
- Child capture dereference: `examples-miner.yaml:148` (`captured.<state>.<child-capture>.output`)
- LLM evaluation routing: `sprint-build-and-validate.yaml:57-69` (`llm_structured` with captured output source)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/eval-driven-development.yaml` (new file)
- `scripts/little_loops/loops/greenfield-builder.yaml` (new file)

### Dependent Files (Callers/Importers)
- N/A (new loop, no existing callers)

### FSM Engine Files (Reference Only — Not Modified)
- `scripts/little_loops/fsm/executor.py:571-625` — `_execute_sub_loop`: resolves child YAML, merges context if `context_passthrough: true`, runs child executor synchronously, merges child `captured` back into parent
- `scripts/little_loops/fsm/executor.py:975-986` — `_action_mode`: `prompt` and `slash_command` both route to Claude CLI; `shell` routes to `bash -c`
- `scripts/little_loops/fsm/executor.py:689-761` — `_run_action`: constructs CLI invocations, handles handoff signals
- `scripts/little_loops/fsm/schema.py:455-488` — `FSMLoop` dataclass: defaults `max_iterations=50`, `on_handoff="pause"`, `input_key="input"`
- `scripts/little_loops/fsm/schema.py:179-309` — `StateConfig`: `loop` and `action` are mutually exclusive; supported action_types: `prompt`, `slash_command`, `shell`, `mcp_tool`
- `scripts/little_loops/fsm/validation.py:432-495` — `load_and_validate`: required top-level keys are `name`, `initial`, `states`
- `scripts/little_loops/fsm/interpolation.py:65-100` — `InterpolationContext.resolve`: supports `${context.*}`, `${captured.*}`, `${prev.*}`, `${result.*}`, `${state.*}`, `${loop.*}`, `${env.*}`
- `scripts/little_loops/fsm/handoff_handler.py:94-122` — `_spawn_continuation`: spawns `claude -p "... ll-loop resume {name}"` with `start_new_session=True`
- `scripts/little_loops/cli/loop/run.py:85-102` — pre-flight context variable check: scans for `${context.KEY}` patterns and errors if missing

### Similar Patterns
- `scripts/little_loops/loops/issue-refinement.yaml:29-33` — canonical sub-loop invocation: `loop: refine-to-ready-issue`, `context_passthrough: true`, binary `on_yes`/`on_no` routing
- `scripts/little_loops/loops/agent-eval-improve.yaml:1-91` — structural analog for the inner loop: eval → score → analyze → refine → re-eval with convergence routing
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:12-116` — multi-phase prompt pipeline: assess → create → validate → fix → review with `capture` chaining via `${captured.<name>.output}`
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml:62-69` — cascading `output_contains` routing: `route_bloat → route_size → route_priority → done`
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml:125-130` — periodic commit via `action_type: prompt` with `/ll:commit` and `next:` back to loop top
- `scripts/little_loops/loops/issue-refinement.yaml:34-52` — counter-gated commit every N cycles using shell counter file + `output_contains`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1-7` — sub-loop child receiving `context.input` from parent via passthrough
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:64-78` — `python3 -c` inline config reading pattern for `ll-config.json` test_cmd
- `scripts/little_loops/loops/examples-miner.yaml:135-139` — sub-loop with `on_success`/`on_failure` routing (aliases for `on_yes`/`on_no`)
- `scripts/little_loops/loops/prompt-regression-test.yaml:88-93` — sub-loop with diverging outcome routing (`on_success` → `update_baseline`, `on_failure` → `report`)

### Tests
- `ll-loop validate greenfield-builder` — structural validation via `validation.py:load_and_validate`
- `ll-loop test greenfield-builder` — interactive dry-run walkthrough via `cli/loop/testing.py:12-169`
- `scripts/tests/test_builtin_loops.py` — validates ALL built-in YAML loops (context_passthrough, harness references); new loop will be auto-included
- `scripts/tests/test_fsm_executor.py` — FSM execution tests (sub-loop, capture, routing)
- `scripts/tests/test_fsm_schema.py` — schema validation tests

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — reference for eval harness creation; documents two variants: single-shot (execute → check chain) and multi-item (discover → execute → check → advance cycle)
- `docs/guides/LOOPS_GUIDE.md` — primary loops guide
- `docs/generalized-fsm-loop.md` — FSM loop design spec (includes `ll-auto` shell invocation pattern)
- `scripts/little_loops/loops/README.md` — add entry for new loop
- `skills/create-loop/reference.md` — canonical field reference for all loop/state fields, sub-loop spec, routing table syntax

### Configuration
- N/A — no config changes required; reads existing `ll-config.json`

## Implementation Steps

1. **Design the inner loop FSM state graph**: Map `eval-driven-development` states and transitions. Use `agent-eval-improve.yaml` as the structural analog. Key decisions: harness invocation as sub-loop vs shell, commit placement, routing logic.

2. **Write `scripts/little_loops/loops/eval-driven-development.yaml`**:
   - Top-level: `name`, `description`, `initial: implement`, `context` (with `harness_name: ""` required, thresholds with defaults), `max_iterations: 20`, `timeout: 14400`, `on_handoff: spawn`
   - `implement`: `action_type: shell` with `ll-auto --priority P1,P2`
   - `commit_impl`: `action_type: prompt` with `/ll:commit`
   - `run_harness`: `action_type: shell`, `action: "ll-loop run ${context.harness_name}"`, `capture: run_harness`, `next: capture_issues` — pass context explicitly via `--context KEY=VALUE` flags (pattern: `rl-coding-agent.yaml:37-44`)
   - `capture_issues`: `action_type: prompt` analyzing `${captured.run_harness.output}`, invoking `/ll:capture-issue` + `/ll:normalize-issues`
   - `commit_eval`: `action_type: prompt` with `/ll:commit`
   - `route_eval`: `evaluate.type: llm_structured` — pass → `done`, fail → `refine_issues`
   - `refine_issues`: `loop: issue-refinement`, `context_passthrough: true`
   - `tradeoff_review`: `action_type: prompt` with `/ll:tradeoff-review-issues`, `next: implement`
   - `done`: `terminal: true`

3. **Validate inner loop**: Run `ll-loop validate eval-driven-development`.

4. **Design the outer loop FSM state graph**: Map `greenfield-builder` phases 1-10 referencing `eval-driven-development` as a sub-loop in phase 10. Use `sprint-build-and-validate.yaml:12-116` as the structural template.

5. **Write `scripts/little_loops/loops/greenfield-builder.yaml`**:
   - Top-level: `name`, `description`, `initial`, `context` (with `spec: ""` required), `max_iterations: 20`, `timeout: 28800`, `on_handoff: spawn`
   - Phase 1 (init): `action_type: shell` to validate spec files exist, `capture: spec_content`
   - Phase 2 (tech research): `action_type: prompt` referencing `${captured.spec_content.output}`, writes `docs/research.md`, `capture: tech_research`, `next: design_artifacts`
   - Phase 3 (design artifacts): `action_type: prompt` referencing `${captured.spec_content.output}` + `${captured.tech_research.output}`, writes `docs/data-model.md` + `docs/contracts/` + `docs/quickstart.md`, `capture: design_artifacts`, `next: commit_design`
   - Phase 4 (commit design): `action_type: prompt` with `/ll:commit`, `next: harness_planning`
   - Phase 5 (harness planning): `action_type: prompt` referencing `AUTOMATIC_HARNESSING_GUIDE.md` + `${captured.design_artifacts.output}`, `capture: harness_plan`
   - Phase 6 (harness issues): `action_type: prompt` invoking `/ll:capture-issue`
   - Phase 7 (spec decomposition): `action_type: prompt` invoking `/ll:capture-issue` + `/ll:normalize-issues`, referencing `${captured.tech_research.output}` + `${captured.design_artifacts.output}`, then `/ll:commit`
   - Phase 8 (refinement): `loop: issue-refinement`, `context_passthrough: true`
   - Phase 9 (tradeoff review): `action_type: prompt` with `/ll:tradeoff-review-issues` + `/ll:commit`
   - Phase 10 (eval-driven improvement): `loop: eval-driven-development`, `context_passthrough: true`
   - `done`: `terminal: true`

6. **Validate and test both loops**:
   - Run `ll-loop validate eval-driven-development` and `ll-loop validate greenfield-builder`
   - Run `ll-loop test` for both loops
   - **Update `scripts/tests/test_builtin_loops.py:48-75`**: `test_expected_loops_exist` uses strict `==` comparison (`assert expected == actual`) against the glob result. **The test is already failing before this issue is implemented** — the expected set has 26 entries but 31 loop files exist on disk (5 undocumented: `agent-eval-improve`, `dataset-curation`, `incremental-refactor`, `prompt-regression-test`, `test-coverage-improvement`). Add all **7** missing stems to the set: the 5 pre-existing ones plus `"eval-driven-development"` and `"greenfield-builder"`. Adding only 2 will leave the test still failing.

7. **Update `scripts/little_loops/loops/README.md`** with entries for both loops

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Schema constraints** (from `fsm/validation.py:76-94` and `fsm/schema.py:179-309`):
- Required top-level fields: `name`, `initial`, `states` only — all others optional
- `loop` and `action` are **mutually exclusive** on a state (`validation.py:201-209`)
- `max_retries` and `on_retry_exhausted` must be set together (`validation.py:261-282`)
- States with `next:` (unconditional) skip evaluation entirely (`executor.py:648-663`)
- Default evaluator for `shell` = `exit_code`; for `prompt`/`slash_command` = `llm_structured`

**Sub-loop context merge behavior** (from `executor.py:589-596`):
- Parent `context` + flattened `captured` values (extracts `.output` from capture dicts) + child's own `context` defaults are merged
- After child completes: child `captured` stored in `parent.captured[<state_name>]`
- Child termination routing: `"terminal"` → `on_yes`/`on_success`; anything else → `on_no`/`on_failure`

**Harness creation patterns** (from `AUTOMATIC_HARNESSING_GUIDE.md`):
- Two built-in templates: `harness-single-shot.yaml` and `harness-multi-item.yaml`
- `check_concrete` uses `action_type: shell` with test_cmd from config
- `check_semantic` uses `evaluate.source: "${captured.execute_result.output}"` (not `${prev.output}`)
- `check_invariants` uses `output_numeric` with `operator: lt`, `target: 50` for diff size gates

**`ll-auto` invocation** (from `cli/auto.py` and `docs/generalized-fsm-loop.md`):
- Entry point: `little_loops.cli.auto:main_auto`
- Useful flags: `--max-issues N`, `--priority P1,P2`, `--type BUG,FEAT,ENH`, `--skip ID1,ID2`, `--quiet`
- No existing built-in loop directly invokes `ll-auto`; the documented pattern is `action_type: shell` with `ll-auto --max-issues 5`

**Existing loop count**: Built-in loops in `scripts/little_loops/loops/`. `test_builtin_loops.py` has two test categories: (a) structural YAML validation — auto-discovers all files; (b) `test_expected_loops_exist` (lines 46-77) — uses a **hardcoded `expected` set** with strict `==` comparison against the glob result. Adding new loops will pass structural validation automatically but WILL FAIL the expected-set test until the set is manually updated.

### Codebase Research Findings (Round 2)

_Added by `/ll:refine-issue` — resolving Confidence Check concerns:_

**`loop: ${context.*}` interpolation is unsupported — confirmed** (`executor.py:571-625`):
- `_execute_sub_loop` passes `state.loop` raw to `resolve_loop_path()` at `executor.py:585` — the `ctx` object is built at line 637 and used for routing (`on_yes`/`on_no`) but never applied to `state.loop`
- `resolve_loop_path()` (`cli/loop/_helpers.py:90-111`) treats the input as a literal filename stem; `"${context.harness_name}"` causes `FileNotFoundError` at line 111
- By contrast, `action:` strings ARE interpolated: `interpolate(action_template, ctx)` at `executor.py:705` resolves all `${context.*}` tokens before shell execution
- **Resolution**: Use `action_type: shell` with `action: "ll-loop run ${context.harness_name}"` — the FSM executor interpolates the action string, the shell receives the resolved loop name

**Established workaround pattern** (`rl-coding-agent.yaml:37-44`):
```yaml
refine:
  action: |
    ll-loop run rl-rlhf \
      --context quality_dimension="correctness and test coverage" \
      --max-iterations 10
  action_type: shell
  capture: refine_result
  next: observe
```
The file even includes a comment (line 8) noting this as a workaround pending FEAT-659 (native hierarchical FSM loop support). This is the exact pattern for `run_harness`.

**Context passthrough for shell-invoked harness**: Use `--context KEY=VALUE` flags (CLI defined at `cli/loop/__init__.py:141-147`). Any FSM context variables needed by the harness must be passed explicitly — `context_passthrough: true` only works on native `loop:` states, not shell actions.

**`capture:` on `loop:` states — no explicit field needed**: Child captures are automatically stored in `parent.captured[<state_name>]` when `context_passthrough: true`. Reference syntax: `${captured.<state_name>.<child_capture_name>.output}` (pattern: `examples-miner.yaml:135-148`, reference doc: `skills/create-loop/reference.md:570-616`). For `run_harness` as a shell action, use `capture: run_harness`; reference via `${captured.run_harness.output}` in `route_eval`.

**`test_expected_loops_exist` is a strict-equality test** (`test_builtin_loops.py:46-77`):
- Uses `assert expected == actual` where `expected` is a hardcoded inline `set` literal and `actual` = `{f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}`
- Fails in both directions: new file added but not in set, OR set has a name whose file was deleted
- Add exactly `"eval-driven-development"` and `"greenfield-builder"` to the `expected` set at lines 48-75

### Codebase Research Findings (Round 3)

_Added by `/ll:refine-issue` — verifying implementation details:_

**`test_expected_loops_exist` actual expected set — 26 entries, not 31** (`test_builtin_loops.py:48-75`):

The issue previously said "31 loop names" — actual count is **26**. Adding the two new loops brings it to 28. Exact current set to which the implementer must append:

```python
expected = {
    "dead-code-cleanup",
    "docs-sync",
    "evaluation-quality",
    "fix-quality-and-tests",
    "issue-discovery-triage",
    "issue-refinement",
    "issue-size-split",
    "issue-staleness-review",
    "backlog-flow-optimizer",
    "sprint-build-and-validate",
    "worktree-health",
    "rl-bandit",
    "rl-rlhf",
    "rl-policy",
    "rl-coding-agent",
    "apo-feedback-refinement",
    "apo-contrastive",
    "apo-opro",
    "apo-beam",
    "apo-textgrad",
    "examples-miner",
    "context-health-monitor",
    "harness-single-shot",
    "harness-multi-item",
    "general-task",
    "refine-to-ready-issue",
    # ADD THESE:
    "eval-driven-development",
    "greenfield-builder",
}
```

**Harness template selection logic for Phase 5** (`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:439-495`):

Template selection is purely structural — determined at wizard Step H2 (Work Item Discovery Mode):
- **Variant A (`harness-single-shot`)**: Single-shot verification (one execution → check chain). Use when the spec defines a single validation scenario.
- **Variant B (`harness-multi-item`)**: Iterates over a list of work items (`discover → execute → check → advance`). Use when the spec implies multiple test cases, files, or items.

For Phase 5 in the prompt, instruct the LLM to:
1. Choose Variant A or B based on whether the spec has a single observable scenario vs. a list of items
2. Copy the chosen template: `ll-loop install harness-single-shot` or `ll-loop install harness-multi-item` (installs to `.loops/`)
3. Customize the key fields: `name`, `execute.action`, `check_concrete.action`, `check_semantic.evaluate.prompt`, `check_invariants.evaluate.target` (and `discover.action` for Variant B)
4. Reference `AUTOMATIC_HARNESSING_GUIDE.md` lines 600–620 for the exact fields to modify

**3-level nesting (`greenfield-builder → eval-driven-development → issue-refinement`) — mechanically sound** (`executor.py:571-625`):

- No depth limit exists in `_execute_sub_loop`; `_depth` is only used for event tagging
- Grandparent context reaches grandchild IF the intermediate `loop:` state also sets `context_passthrough: true`
- **`harness_name` flow is safe**: `greenfield-builder` → `eval-driven-development` (1 level, needs `harness_name`) is the critical pass; `eval-driven-development` → `issue-refinement` (2 levels) does NOT need `harness_name` — `issue-refinement` only uses `context.input`
- Untested gap: grandparent-to-grandchild context passthrough chain is exercised by `test_fsm_executor.py:3494` for depth/events but NOT for context values. Not a blocker — the `harness_name` variable only needs to propagate 1 level deep

**`rl-coding-agent.yaml` workaround note** (`rl-coding-agent.yaml:7-8`):

The hardcoded loop name in the existing example (`rl-rlhf`) is intentional — `rl-coding-agent` always calls the same fixed child. For `run_harness` in `eval-driven-development`, the name is dynamic (`${context.harness_name}`). This is supported because `action:` strings are interpolated at `executor.py:705` before shell execution. The pattern extends naturally: action strings support `${context.*}` interpolation; only `loop:` fields do not. No FEAT-659 blocker applies to this usage.

### Codebase Research Findings (Round 4)

_Added by `/ll:refine-issue` — correcting Round 3 and filling remaining gaps:_

**CORRECTION to Round 3 — `test_expected_loops_exist` requires adding 7 entries, not 2**:

Round 3 shows the 26-entry `expected` set and says "add just `eval-driven-development` and `greenfield-builder`". This is incorrect. The test is ALREADY failing: 31 YAML files exist at the top level of `scripts/little_loops/loops/` (the `oracles/` subdirectory is excluded by the non-recursive `glob("*.yaml")`) but only 26 are in `expected`. Five files are on disk but absent from the set:

```
agent-eval-improve, dataset-curation, incremental-refactor,
prompt-regression-test, test-coverage-improvement
```

Implementation step 6 is correct: add all **7** missing stems (5 pre-existing + 2 new). The final `expected` set must have 33 entries. Round 3's "add just 2" would leave the test still failing with `len(actual)=33 != len(expected)=28`.

**`route_eval` evaluate block exact syntax** (from `sprint-build-and-validate.yaml:57-69`):

`route_eval` is a pure routing state with NO `action` field — it evaluates `${captured.run_harness.output}` from the prior shell state using `llm_structured` + `source:`:

```yaml
route_eval:
  evaluate:
    type: llm_structured
    source: "${captured.run_harness.output}"
    prompt: |
      Did all eval harness gates pass?
      Return "yes" if all gates passed.
      Return "no" if any gates failed or produced errors.
  on_yes: done
  on_no: refine_issues
  on_error: refine_issues
  on_blocked: refine_issues
```

The `source:` field feeds the captured harness stdout into the LLM evaluator. This pattern is identical to `route_validation` in `sprint-build-and-validate.yaml:57-69`.

**`ll-loop install` is a real, valid command** (`cli/loop/__init__.py:307-311`, `config_cmds.py:37-66`):
- Usage: `ll-loop install harness-single-shot` or `ll-loop install harness-multi-item`
- Copies the built-in template to `<project>/.loops/<loop_name>.yaml`; errors if destination already exists
- Phase 5 prompt should instruct the LLM to run `ll-loop install <variant>` to obtain the template before customizing it

## Impact

- **Priority**: P1 - This is the highest-leverage automation in the plugin; it composes all existing primitives into the ultimate workflow
- **Effort**: Large - Two FSM loops with nested sub-loop composition (3 levels deep: greenfield-builder → eval-driven-development → issue-refinement), prompt engineering for spec decomposition and harness planning, integration with many existing skills
- **Risk**: Medium - Relies on correct interaction of many subsystems (sub-loops, skills, ll-auto, harness execution); each phase is individually proven but the composition is novel
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [AUTOMATIC_HARNESSING_GUIDE.md](../../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md) | Core reference for eval harness creation (Phase 2) |
| [ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | System design context for FSM execution |
| [API.md](../../docs/reference/API.md) | Python module reference for ll-auto, ll-loop |

## Labels

`feature`, `automation`, `fsm-loop`, `meta-loop`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-02_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- **`loop: ${context.harness_name}` is not supported by the executor** (`executor.py:585`). `state.loop` is passed directly to `resolve_loop_path()` without interpolation — the literal string `"${context.harness_name}"` would be used as a file path and fail. The issue lists executor.py as "Reference Only — Not Modified", creating a contradiction. Resolution required before implementation: either (a) enhance `executor.py` to interpolate `state.loop` before resolution, or (b) use `action_type: shell` with `ll-loop run ${context.harness_name}` and `exit_code` routing instead of a sub-loop state.
- **`test_expected_loops_exist` will fail** (`test_builtin_loops.py:46-77`). This test has a hardcoded `expected` set of 26 loop names, but 31 YAML files exist on disk. Adding two new loops will widen this gap further. The issue notes new loops will be "auto-included" but this only applies to structural validation tests — the expected-set test must be manually updated (add all 7 missing stems: 5 pre-existing + 2 new).

### Outcome Risk Factors
- The outer loop's Phase 2 (creating harness YAML from spec) relies heavily on LLM judgment with no concrete template selection logic. Choosing and parameterizing the right harness variant for an arbitrary spec is a significant inference task that may produce inconsistent results.
- 3-level sub-loop nesting (greenfield-builder → eval-driven-development → issue-refinement) is novel — only 1-level nesting is established in existing loops. Debugging failures in deeply nested sub-loops has no established pattern.

## Session Log
- `/ll:ready-issue` - 2026-04-02T16:39:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/559d7ee1-0b28-4714-bc85-f7f06316dc14.jsonl`
- `/ll:refine-issue` - 2026-04-02T16:23:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d41e142-95a4-4d7a-a114-f07f2bbc44bd.jsonl`
- `/ll:refine-issue` - 2026-04-02T16:23:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d41e142-95a4-4d7a-a114-f07f2bbc44bd.jsonl`
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3dfd289-19b3-42ae-91c4-9110cbc966f7.jsonl`
- `/ll:refine-issue` - 2026-04-02T14:46:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b7533a7-29d7-44d6-8489-bc5e06ed005f.jsonl`
- `/ll:refine-issue` - 2026-04-02T06:15:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3d667a6c-0a49-4284-a4ce-4b5ecbbfe4a3.jsonl`
- `/ll:confidence-check` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79abedd4-e354-40a5-a5ad-3c6d38b65535.jsonl`
- `/ll:refine-issue` - 2026-04-02T05:14:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42dd0907-a734-4d2d-9267-44252d3837e7.jsonl`
- `/ll:format-issue` - 2026-04-02T05:05:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42f55760-d9eb-4053-a9a0-e47fdee21521.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/691b200f-7de4-4ff4-bdb4-e101673139e8.jsonl`

---

## Resolution

**Resolved** — 2026-04-02

### Changes Made
- Created `scripts/little_loops/loops/eval-driven-development.yaml` — inner loop with 9 states: implement → commit → run_harness → capture_issues → commit → route_eval → refine → tradeoff → done
- Created `scripts/little_loops/loops/greenfield-builder.yaml` — outer loop with 12 states: init → tech_research → design → commit → harness_planning → harness_issues → spec_decomposition → commit → refinement → tradeoff → eval_driven_improvement → done
- Updated `scripts/tests/test_builtin_loops.py` — added 7 missing loop stems to expected set (5 pre-existing + 2 new, 33 total)
- Updated `scripts/little_loops/loops/README.md` — added "Greenfield & Eval-Driven" section

### Key Design Decisions
- `run_harness` uses `action_type: shell` with `ll-loop run ${context.harness_name}` (not `loop:` field) because `executor.py:585` doesn't interpolate `state.loop` — follows `rl-coding-agent.yaml:37-44` workaround pattern
- `eval-driven-development` is standalone-reusable: any project with an eval harness can invoke it directly
- 3-level nesting supported: greenfield-builder → eval-driven-development → issue-refinement
- `context_passthrough: true` on all sub-loop states to flow `harness_name` through

### Verification
- `ll-loop validate` passes for both loops
- All 52 tests in `test_builtin_loops.py` pass
- `ruff check` passes
- `mypy` passes (pre-existing unrelated `wcwidth` warning only)

## Status

**Completed** | Created: 2026-04-02 | Completed: 2026-04-02 | Priority: P1
