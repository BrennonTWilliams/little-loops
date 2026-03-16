---
id: FEAT-722
priority: P3
type: FEAT
status: open
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 90
outcome_confidence: 79
---

# FEAT-722: Built-in Loops for Automatic Prompt Optimization (APO) Techniques

## Summary

Add new built-in FSM loop configurations that implement Automatic Prompt Optimization (APO) techniques, enabling users to iteratively improve prompts using established optimization strategies (e.g., gradient-free optimization, feedback-driven refinement, meta-prompting) without writing custom loops from scratch.

## Current Behavior

`ll-loop` supports custom FSM loop configurations but has no built-in loops targeting prompt optimization workflows. Users who want to run APO-style iterative improvement on their prompts must design the FSM from scratch.

## Expected Behavior

A set of built-in loop configurations (ship with `ll-loop` or discoverable via `ll-loop list --builtin`) that implement common APO techniques:
- Feedback-driven prompt refinement (run → evaluate → refine → repeat)
- Contrastive prompt optimization (generate candidates → score → select best → iterate)
- Meta-prompting loops (use a prompt to improve a prompt, iterate until stable)
- Possibly: DSPy-style few-shot bootstrapping loops

## Motivation

APO is a well-established research area with practical, automatable workflows. Little-loops already has the FSM loop infrastructure — adding built-in APO loop templates lowers the barrier significantly for users who want to systematically improve their prompts. This positions little-loops as a practical tool for prompt engineering workflows, not just code automation.

## Use Case

A developer has a system prompt for a Claude-powered feature that produces inconsistent outputs. They run:

```bash
ll-loop apo-feedback-refinement --context prompt_file=system.md --context eval_dataset=examples.json
```

The loop generates improved prompt candidates, evaluates them against the dataset, selects the best-performing variant, and repeats for N iterations — surfacing the optimized prompt at the end.

## Acceptance Criteria

- [ ] At least 2 built-in APO loop configurations ship with little-loops (e.g., `apo-feedback-refinement`, `apo-contrastive`)
- [ ] Built-ins are discoverable via `ll-loop list --builtin` or equivalent
- [ ] Each built-in documents its technique, required variables, and expected outputs
- [ ] Built-ins are parameterized (users can pass in their prompt file, eval criteria, iteration count, etc.)
- [ ] `ll-loop run --builtin <name>` loads and executes the built-in without a user-managed YAML file
- [ ] Documentation explains each APO technique and when to use it

## API/Interface

```bash
# Discover available built-ins (already works — ll-loop list shows built-ins labeled [built-in])
ll-loop list

# Run a built-in with context overrides (resolve_loop_path() fallback already finds built-ins)
ll-loop apo-feedback-refinement --context iterations=5 --context prompt=my-prompt.md

# Show built-in definition (ll-loop show already works for any loop name)
ll-loop show apo-contrastive

# Optional UX improvements (require CLI changes per Proposed Solution steps 3–4):
ll-loop list --builtin          # filter to built-ins only
ll-loop run --builtin apo-feedback-refinement --context iterations=5  # explicit disambiguation
```

_Note: The correct flag for context variable overrides is `--context KEY=VALUE` (not `--var`). See `scripts/little_loops/cli/loop/__init__.py:139-145` and `run.py:53-57`._

## Proposed Solution

1. Add APO YAML files to the **existing** `loops/` directory at repo root — `get_builtin_loops_dir()` (`_helpers.py:81`) already resolves here; no new `builtins/` subdirectory needed
2. Each built-in is a YAML loop config with `context: {}` variable slots (overridable via `--context KEY=VALUE`)
3. Optionally extend `ll-loop run` with a `--builtin` flag for explicit disambiguation (not required — `resolve_loop_path()` fallback at `_helpers.py:102-105` already resolves from `loops/`)
4. Optionally extend `ll-loop list` with `--builtin` to filter to built-ins only (`cmd_list()` at `info.py:87-92` already shows built-ins in human-readable output)
5. APO loop states use `action_type: prompt` with `evaluate.type: llm_structured` — the standard pattern for Claude-driven evaluation (see `loops/fix-quality-and-tests.yaml`)

## Integration Map

### Files to Modify
- `loops/` (repo root) — **primary deliverable**: add new APO YAML files here (e.g., `apo-feedback-refinement.yaml`, `apo-contrastive.yaml`). No Python changes required for basic `ll-loop run apo-*` functionality.
- `scripts/little_loops/cli/loop/__init__.py:149-155` — optionally add `--builtin` filter flag to `list` subparser
- `scripts/little_loops/cli/loop/info.py:79-92` — optionally modify `cmd_list()` to filter output to built-ins only when `--builtin` is passed
- `scripts/little_loops/cli/loop/__init__.py:92-139` — optionally add `--builtin` flag to `run` subparser for explicit disambiguation (not required — fallback already exists)

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/_helpers.py:81-83` — `get_builtin_loops_dir()` returns `<repo-root>/loops/`; **no changes needed**, already handles resolution
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` already falls back to `get_builtin_loops_dir()` as step 4 of its lookup chain; `ll-loop run apo-feedback-refinement` works once YAML exists
- `scripts/little_loops/cli/loop/info.py:87-92` — `cmd_list()` already discovers and displays built-ins labeled `[built-in]`; `--builtin` filter is a UX improvement, not a blocker
- `scripts/little_loops/cli/loop/config_cmds.py:37-66` — `cmd_install()` already copies built-in loops to project `.loops/`; APO loops get `ll-loop install apo-*` for free

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `loops/fix-quality-and-tests.yaml` — gold standard model for `action_type: prompt` + `evaluate.type: llm_structured` pattern; use for APO evaluate states
- `loops/issue-refinement.yaml` — model for `context: {}` variable slots, `capture:` for storing intermediate outputs, and `${captured.*.output}` interpolation in subsequent states
- `loops/issue-discovery-triage.yaml:52-70` — `output_numeric` with `target: ${captured.baseline.output}` (cross-state numeric comparison for convergence; note: `loops/pr-review-cycle.yaml` does not exist — prior reference was stale)
- `scripts/little_loops/fsm/evaluators.py:308-370` — `convergence` evaluator (verdicts: `target`, `progress`, `stall`; fields: `target`, `tolerance`, `direction: minimize|maximize`, `previous: "${captured.prev_score.output}"`). Better semantic fit for APO score tracking than `output_numeric` — unused in current loops but fully implemented
- `scripts/little_loops/fsm/interpolation.py:65` — `InterpolationContext.resolve()`: supported namespaces are `context`, `captured`, `prev`, `result`, `state`, `loop`, `env`; APO loops should use `${context.prompt_file}` and `${captured.eval_result.output}` patterns

### Tests
- `scripts/tests/test_builtin_loops.py` — **auto-covers new YAML files**: `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` iterate all files in `BUILTIN_LOOPS_DIR`; new APO files are tested for free
- `scripts/tests/test_ll_loop_commands.py` — add tests for new `--builtin` CLI flags if added
- `scripts/tests/test_ll_loop_parsing.py:26-37` — `_create_run_parser()` helper pattern to follow for testing new flag definitions

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — primary user-facing doc; add APO technique descriptions and when-to-use guidance
- `docs/reference/CLI.md` — update `ll-loop list` and `ll-loop run` flag documentation
- `docs/reference/API.md` — may need `--builtin` flag documentation if added

### Configuration
- N/A (built-ins live in repo-root `loops/`; no user config changes needed)

## Implementation Steps

_Enriched by `/ll:refine-issue` — infrastructure already exists; core work is YAML authoring:_

1. **Author `loops/apo-feedback-refinement.yaml`** — FSM: `generate_candidate → evaluate_candidate → route_convergence → refine → [loop|done]`. Model after `loops/fix-quality-and-tests.yaml` using `action_type: prompt` + `evaluate.type: llm_structured`. Required `context` slots with defaults (follow `sprint-build-and-validate.yaml:7-10` pattern):
   ```yaml
   name: apo-feedback-refinement
   description: Iteratively refines a prompt using LLM feedback evaluation
   initial: generate_candidate
   max_iterations: 20
   context:
     prompt_file: system.md
     eval_criteria: ""
     iterations: 5
   states:
     generate_candidate:
       action_type: prompt
       action: |
         Read the prompt from ${context.prompt_file}. Generate an improved variant
         that addresses the evaluation criteria: ${context.eval_criteria}
         Output the full improved prompt text.
       capture: candidate
       next: evaluate_candidate
     evaluate_candidate:
       action_type: prompt
       action: |
         Evaluate this prompt candidate against the criteria: ${context.eval_criteria}
         Candidate: ${captured.candidate.output}
         Output a score 0-100 and analysis. End with CONVERGED or NEEDS_REFINE on its own line.
       capture: eval_result
       next: route_convergence
     route_convergence:
       evaluate:
         type: output_contains
         source: "${captured.eval_result.output}"
         pattern: "CONVERGED"
       on_yes: done
       on_no: refine
     refine:
       action_type: prompt
       action: |
         Based on this evaluation: ${captured.eval_result.output}
         Update the prompt in ${context.prompt_file} to address the feedback.
       next: generate_candidate
     done:
       terminal: true
   ```
   **LLM output tag convention**: each evaluation state emits exactly one uppercase token on its own line (e.g., `CONVERGED`, `NEEDS_REFINE`) to enable `output_contains` routing — see `backlog-flow-optimizer.yaml:35-58` for the canonical pattern.

2. **Author `loops/apo-contrastive.yaml`** — FSM: `generate_variants → score_variants → select_best → route_convergence → [loop|done]`. Use `capture: scored_variants` to store scoring output. **Note**: multi-candidate generation is new territory — no existing loop does this. Recommend generating N variants in a single prompt state as a numbered list, then scoring all in the next state, then selecting/committing the winner. Example convergence check: use `output_contains` on `CONVERGED` tag emitted by `select_best` when selected score exceeds threshold; or use the `convergence` evaluator at `evaluators.py:308-370` (verdicts: `target`, `progress`, `stall`) for numeric score-based tracking.

3. **Add `--builtin` filter to `ll-loop list`** (optional, UX improvement) — add `store_true` arg at `cli/loop/__init__.py:149-155`; modify `cmd_list()` at `info.py:101-136` to skip project loops section when `--builtin` is set.
4. **Add `--builtin` flag to `ll-loop run`** (optional) — add `store_true` arg at `cli/loop/__init__.py:92-139`; modify `cmd_run()` at `run.py:32` to call `get_builtin_loops_dir() / f"{loop_name}.yaml"` directly when flag is set, bypassing `resolve_loop_path()`.
5. **Tests** — new APO YAML files are auto-validated by `scripts/tests/test_builtin_loops.py:28-43`; add `--builtin` flag tests to `scripts/tests/test_ll_loop_commands.py` if flags are added.
6. **Document APO techniques** in `docs/guides/LOOPS_GUIDE.md` — add technique descriptions, required variables, and `ll-loop run` invocation examples.

### Codebase Research Findings (YAML Authoring Reference)

_Added by `/ll:refine-issue` — full schema and patterns:_

**Complete `StateConfig` fields** (`schema.py:179-227`): `action`, `action_type` (`prompt`|`shell`|`slash_command`|`mcp_tool`), `params`, `evaluate`, `route`, `on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, `next`, `terminal`, `capture`, `timeout`, `max_retries`, `on_retry_exhausted`, `on_maintain`

**Top-level loop fields**: `name`, `description`, `initial`, `states`, `context`, `max_iterations` (default 50), `backoff`, `timeout`, `maintain`, `scope`, `llm`, `on_handoff`, `input_key`

**Route-only state pattern** (zero-cost dispatcher, no action): set `evaluate.source: "${captured.state_name.output}"` with no `action` field — evaluator reads prior capture directly. Used in `backlog-flow-optimizer.yaml:61-84` and `issue-refinement.yaml:54-69`.

**`convergence` evaluator** (best fit for APO numeric score tracking):
```yaml
evaluate:
  type: convergence
  target: 95          # score threshold (0-100)
  tolerance: 2.0
  direction: maximize
  previous: "${captured.prev_score.output}"
on_target: done
on_progress: refine
on_stall: done        # exit if no improvement
```
Not used in any current loop yet — fully implemented at `evaluators.py:308-370`.

**Interpolation namespaces in any string field**: `${context.*}`, `${captured.<state>.output}`, `${prev.output}`, `${state.iteration}`, `${loop.elapsed}`, `${env.*}`

## Impact

- **Priority**: P3 - High value for prompt engineering workflows; not blocking but expands use cases significantly
- **Effort**: Large - Requires APO technique research, FSM design, CLI extension, and documentation
- **Risk**: Medium - New subsystem (builtins directory + CLI flags); core loop engine unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Loop system architecture |
| `docs/reference/API.md` | CLI reference for `ll-loop` |

## Labels

`feature`, `loops`, `apo`, `prompt-engineering`, `captured`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- No APO loop YAML files exist in `loops/` (confirmed by filename search). No `builtins/` directory exists under `scripts/little_loops/`. `ll-loop list` and `ll-loop run` have no `--builtin` flag. Feature not yet implemented.

## Session Log
- `/ll:refine-issue` - 2026-03-16T00:58:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88954013-7439-4bde-96ee-7533696b0537.jsonl`
- `/ll:refine-issue` - 2026-03-16T00:52:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42bbd8c6-c965-46f9-b9f1-23535801a250.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75ab9873-e77b-46a5-b50b-85782d3bc37c.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2503a31-5075-415e-95d5-959cac6eec58.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
