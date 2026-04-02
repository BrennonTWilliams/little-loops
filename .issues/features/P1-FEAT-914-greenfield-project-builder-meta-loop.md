---
discovered_date: "2026-04-02"
discovered_by: capture-issue
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
2. Plan and create an as-a-user eval harness (per AUTOMATIC_HARNESSING_GUIDE.md)
3. Create P1 FEAT issues for the eval harness
4. Decompose specs into FEAT and ENH issues via `/ll:capture-issue`
5. Normalize and commit issues
6. Refine all issues via the `issue-refinement` sub-loop
7. Run `/ll:tradeoff-review-issues` to annotate issues with viability notes
8. Invoke `eval-driven-development` as a sub-loop → done when it terminates

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
- [ ] Runs the harness loop as a sub-loop and captures results
- [ ] Creates/updates issues from eval findings via `/ll:capture-issue`
- [ ] Refines new issues via `issue-refinement` sub-loop (`loop:` field with `context_passthrough`)
- [ ] Runs `/ll:tradeoff-review-issues` on new issues
- [ ] Routes: eval gates pass → `done`; otherwise → back to implement
- [ ] Periodic commits via `/ll:commit` at natural phase boundaries
- [ ] Has own `max_iterations`, `timeout`, and `on_handoff: spawn` configured appropriately

### Outer loop (`greenfield-builder.yaml`)

- [ ] `greenfield-builder.yaml` exists in `scripts/little_loops/loops/` and passes `ll-loop validate`
- [ ] Accepts `spec` input parameter (single path or comma-separated paths to Markdown spec files)
- [ ] Plans and creates a harness loop YAML dynamically based on the spec (using patterns from AUTOMATIC_HARNESSING_GUIDE.md)
- [ ] Creates P1 FEAT issues for the eval harness itself
- [ ] Decomposes spec into FEAT and ENH issues using `/ll:capture-issue`
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
  ├── Phase 1-4: One-time setup (spec → harness → issues)
  ├── Phase 5-6: Initial refinement + tradeoff review
  └── Phase 7:   loop: eval-driven-development  ← sub-loop
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

3. **`run_harness`** — `loop: ${context.harness_name}`, `context_passthrough: true`. Runs the eval harness as a sub-loop, captures results. Child termination → `on_yes`/`on_no` routing.

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

**Phase 2 — Eval Harness Planning**: `action_type: prompt` to analyze the spec and plan an as-a-user eval harness following patterns in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`. Output a harness YAML to `.loops/`. `capture: harness_plan`.

**Phase 3 — Harness Issue Creation**: `action_type: prompt` to create P1 FEAT issues for the eval harness using `/ll:capture-issue`.

**Phase 4 — Spec Decomposition**: `action_type: prompt` to analyze spec file(s) and create FEAT/ENH issues via `/ll:capture-issue`, then normalize with `/ll:normalize-issues` and commit.

**Phase 5 — Issue Refinement**: `loop: issue-refinement`, `context_passthrough: true`. Initial refinement pass on all decomposed issues.

**Phase 6 — Tradeoff Review**: `action_type: prompt` with `/ll:tradeoff-review-issues` and `/ll:commit`.

**Phase 7 — Eval-Driven Improvement**: `loop: eval-driven-development`, `context_passthrough: true`. The outer loop's `harness_name` context variable flows through to the inner loop. Inner loop handles the implement→eval→fix cycle autonomously.

**Done** — `terminal: true`.

**Configuration:** `max_iterations: 15`, `timeout: 28800` (8 hours), `on_handoff: spawn`.

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
   - `run_harness`: `loop: ${context.harness_name}`, `context_passthrough: true`
   - `capture_issues`: `action_type: prompt` analyzing `${captured.run_harness.output}`, invoking `/ll:capture-issue` + `/ll:normalize-issues`
   - `commit_eval`: `action_type: prompt` with `/ll:commit`
   - `route_eval`: `evaluate.type: llm_structured` — pass → `done`, fail → `refine_issues`
   - `refine_issues`: `loop: issue-refinement`, `context_passthrough: true`
   - `tradeoff_review`: `action_type: prompt` with `/ll:tradeoff-review-issues`, `next: implement`
   - `done`: `terminal: true`

3. **Validate inner loop**: Run `ll-loop validate eval-driven-development`.

4. **Design the outer loop FSM state graph**: Map `greenfield-builder` phases 1-7 referencing `eval-driven-development` as a sub-loop in phase 7. Use `sprint-build-and-validate.yaml:12-116` as the structural template.

5. **Write `scripts/little_loops/loops/greenfield-builder.yaml`**:
   - Top-level: `name`, `description`, `initial`, `context` (with `spec: ""` required), `max_iterations: 15`, `timeout: 28800`, `on_handoff: spawn`
   - Phase 1 (init): `action_type: shell` to validate spec files exist, `capture: spec_content`
   - Phase 2 (harness planning): `action_type: prompt` referencing `AUTOMATIC_HARNESSING_GUIDE.md`, `capture: harness_plan`
   - Phase 3 (harness issues): `action_type: prompt` invoking `/ll:capture-issue`
   - Phase 4 (spec decomposition): `action_type: prompt` invoking `/ll:capture-issue` + `/ll:normalize-issues`, then `/ll:commit`
   - Phase 5 (refinement): `loop: issue-refinement`, `context_passthrough: true`
   - Phase 6 (tradeoff review): `action_type: prompt` with `/ll:tradeoff-review-issues` + `/ll:commit`
   - Phase 7 (eval-driven improvement): `loop: eval-driven-development`, `context_passthrough: true`
   - `done`: `terminal: true`

6. **Validate and test both loops**:
   - Run `ll-loop validate eval-driven-development` and `ll-loop validate greenfield-builder`
   - Run `ll-loop test` for both loops
   - Verify `test_builtin_loops.py` passes with both new loops auto-included

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

**Existing loop count**: 32 built-in loops in `scripts/little_loops/loops/`; `test_builtin_loops.py` auto-validates all YAMLs in that directory — the new loop will be automatically tested.

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

## Session Log
- `/ll:refine-issue` - 2026-04-02T05:14:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42dd0907-a734-4d2d-9267-44252d3837e7.jsonl`
- `/ll:format-issue` - 2026-04-02T05:05:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42f55760-d9eb-4053-a9a0-e47fdee21521.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/691b200f-7de4-4ff4-bdb4-e101673139e8.jsonl`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P1
