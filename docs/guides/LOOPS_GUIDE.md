# Loops Guide

## What Is a Loop?

A loop is a YAML-defined automation workflow that runs commands, evaluates results, and decides what to do next — without you prompting each step. Under the hood, each loop is a **Finite State Machine (FSM)**: a set of states connected by transitions, with a clear start and end.

Why does this matter? LLMs are stateless — they don't remember what happened two prompts ago. The FSM gives them persistent memory of what was tried, what worked, and when to stop.

```
You write:    FSM YAML (or use /ll:create-loop)
You run:      ll-loop run <name>
```

## How Loops Work

Loops live in `.loops/` as YAML files. Each loop has:

- **States** — units of work (run a check, apply a fix, etc.)
- **Transitions** — edges between states (on success go here, on failure go there)

When a loop runs, the engine:

1. Enters the **initial state** and runs its action
2. Evaluates the result (exit code, output pattern, metric, etc.)
3. Follows the matching **transition** to the next state
4. Repeats until reaching a **terminal state** or hitting `max_iterations`

Use `/ll:create-loop` for an interactive wizard that guides you through creating loops, or write FSM YAML directly (see the [FSM Loop System Design](../generalized-fsm-loop.md) for the schema).

## Common Loop Patterns

```
What are you trying to do?
│
├─ Fix a specific problem ──────────▶ Fix until clean
│   "Run check, if fails run fix, repeat"
│
├─ Maintain multiple standards ─────▶ Maintain constraints
│   "Check A, fix A, check B, fix B, ..."
│
├─ Reduce/increase a metric ────────▶ Drive a metric
│   "Measure, if not at target, fix, measure again"
│
├─ Run ordered steps ───────────────▶ Run a sequence
│   "Do step 1, do step 2, check if done, repeat"
│
└─ Apply a skill to many items ─────▶ Harness a skill
    "Discover items, run skill, pass evaluation pipeline, advance"
```

| Loop type | States | Branching | Best for |
|-----------|--------|-----------|----------|
| Fix until clean | evaluate, fix, done | Binary (pass/fail) | Single check + fix |
| Drive a metric | measure, apply, done | Three-way (target/progress/stall) | Metric optimization |
| Maintain constraints | 2 per constraint + 1 | Binary per constraint | Multi-gate quality |
| Run a sequence | 1 per step + 2 | Binary exit check | Ordered workflows |
| Harness a skill | discover, execute, check_*, advance, done | Multi-phase evaluation (exit code → MCP → skill → LLM → diff) | Batch processing with layered quality gates |

Use `/ll:create-loop` to build any of these interactively. The wizard generates FSM YAML ready to run.

## Walkthrough: Creating and Running a Loop

Here's a complete example: a loop that fixes test failures until all tests pass.

### 1. Create

Run `/ll:create-loop` to use the interactive wizard. Or write the FSM YAML directly:

```yaml
name: fix-tests
initial: evaluate
max_iterations: 10
states:
  evaluate:
    action: "pytest tests/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "Fix failing tests based on the pytest output"
    action_type: prompt
    next: evaluate
  done:
    terminal: true
```

Save this to `.loops/fix-tests.yaml`.

### 2. Validate

```bash
ll-loop validate fix-tests
```

The validator checks your YAML for schema errors, unreachable states, and missing transitions.

### 3. Inspect

```bash
ll-loop show fix-tests
```

Output:

```
Loop: fix-tests
Description: All tests pass
Max iterations: 10
Source: .loops/fix-tests.yaml

States:
  [evaluate] [INITIAL]
    action: pytest tests/
    on_yes ──→ done
    on_no ──→ fix
    on_error ──→ fix
  [fix]
    action: Fix failing tests based on the pytest output
    type: prompt
    next ──→ evaluate
  [done] [TERMINAL]

Diagram:
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──▶│ done │
  └──────────┘             └──────┘
       │ ▲
  fail │ │ next
       ▼ │
     ┌─────┐
     │ fix │
     └─────┘

Run command:
  ll-loop run fix-tests
```

### 4. Run

```bash
ll-loop run fix-tests
```

The engine enters `evaluate`, runs `pytest tests/`, checks the exit code, and follows the transition. If tests fail, it enters `fix`, sends the fix prompt to Claude, then returns to `evaluate`. This continues until tests pass or `max_iterations` is reached.

### 5. Monitor

```bash
ll-loop status fix-tests     # Current state and iteration count
ll-loop history fix-tests    # Full execution history
```

## Built-in Loops

These loops ship with little-loops and cover common workflows. Install one to `.loops/` to customize it:

```bash
ll-loop install <name>       # Copies to .loops/ for editing
```

| Loop | Description |
|------|-------------|
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass |
| `docs-sync` | Verify documentation matches the codebase and check for broken links |
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `issue-discovery-triage` | Automated issue discovery and triage cycle |
| `issue-refinement` | Progressively refine all active issues through format → score → refine pipeline |
| `issue-size-split` | Review issues for sizing and split oversized ones |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `sprint-build-and-validate` | Create a sprint from the backlog and validate all included issues |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches |
| `rl-bandit` | Epsilon-greedy bandit loop — explore vs exploit rounds routing on reward convergence |
| `rl-rlhf` | RLHF-style loop — generate candidate output, score quality, refine until target met |
| `rl-policy` | Policy iteration loop — act, observe reward, improve policy toward a target |
| `apo-feedback-refinement` | Feedback-driven APO — generate → evaluate → refine until convergence |
| `apo-contrastive` | Contrastive APO — generate N variants → score comparatively → select best → repeat |
| `apo-opro` | OPRO-style prompt optimization — history-guided proposal until convergence |
| `apo-beam` | Beam search prompt optimization — generate N variants, score all, advance the winner |
| `apo-textgrad` | TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement |

## Beyond the Basics

The sections below cover features you'll encounter as you move past simple loops. For full technical details — schema definitions, compiler internals, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md).

### Evaluators

Evaluators interpret action output and produce a **verdict** string used for routing. Every state gets a default evaluator based on its action type.

| Evaluator | Verdicts | Default for | When to use |
|-----------|----------|-------------|-------------|
| `exit_code` | `yes` / `no` / `error` | shell commands | CLI tools that report pass/fail via exit code |
| `output_numeric` | `yes` / `no` / `error` | — | Compare parsed numeric output to a target |
| `output_json` | `yes` / `no` / `error` | — | Extract a JSON path value and compare |
| `output_contains` | `yes` / `no` | — | Regex or substring match on stdout |
| `convergence` | `target` / `progress` / `stall` | metric-tracking states | Track a metric toward a goal value |
| `diff_stall` | `stall` / `progress` | — | Detect when consecutive iterations produce no git diff changes |
| `llm_structured` | `yes` / `no` / `blocked` / `partial` | slash commands | Natural-language judgment via LLM |

Override the default by adding an `evaluate:` block to a state:

```yaml
evaluate:
  type: output_contains
  pattern: "All checks passed"
```

### Variable Interpolation

Use `${namespace.path}` in action strings, evaluator configs, and routing targets. Variables are resolved at runtime.

| Namespace | Description | Example |
|-----------|-------------|---------|
| `context` | User-defined variables from the `context:` block | `${context.src_dir}` |
| `captured` | Values stored by `capture:` in earlier states | `${captured.lint.output}` |
| `prev` | Previous state's result (output, exit_code) | `${prev.output}` |
| `result` | Current evaluation result | `${result.verdict}` |
| `state` | Current state metadata | `${state.name}`, `${state.iteration}` |
| `loop` | Loop-level metadata | `${loop.name}`, `${loop.elapsed}` |
| `env` | Environment variables | `${env.HOME}` |

Escape literal `${` with `$${`.

### Capture

Store a state's action output for use in later states:

```yaml
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    capture: lint_count
    next: apply
```

The captured value is accessible as `${captured.lint_count.output}`, `${captured.lint_count.stderr}`, `${captured.lint_count.exit_code}`, and `${captured.lint_count.duration_ms}`.

### Routing

States use **shorthand** (`on_yes`, `on_no`, `on_partial`, `on_blocked`) or a **route table** for verdict-to-state mapping:

```yaml
route:
  success: done
  failure: fix
  _: retry        # default for unmatched verdicts
  _error: error   # fallback for evaluation errors
```

Use `$current` as a target to retry the current state. Use `_` for a default route when no other verdict matches.

An additional shorthand, `on_blocked`, routes when the evaluator returns a `blocked` verdict (i.e., the action cannot proceed without external intervention):

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    on_yes: "verify"
    on_no: "fix"
    on_blocked: "escalate"
```

`on_blocked` is resolved alongside `on_yes`/`on_no`/`on_error` in the shorthand lookup. It is equivalent to adding `blocked: "escalate"` to a full `route` table. If a `blocked` verdict is returned and no `on_blocked` target is defined, the loop terminates with a fatal routing error — define `on_blocked` on any state whose action can return a `blocked` verdict.

### Action Types

Each state's action is executed in one of four modes:

| Type | Syntax hint | Default evaluator | Behavior |
|------|-------------|-------------------|----------|
| `shell` | No `/` prefix | `exit_code` | Run as shell command, capture stdout/stderr/exit code |
| `slash_command` | Starts with `/` | `llm_structured` | Execute a Claude Code slash command |
| `prompt` | Natural language | `llm_structured` | Send text to Claude as a prompt |
| `mcp_tool` | Must be set explicitly | `mcp_result` | Call an MCP server tool with structured params |

The engine auto-detects type: `/` prefix → `slash_command`, otherwise → `shell`. Set `action_type: prompt` explicitly for natural-language fix instructions.

#### Skills as Actions

Skills (invoked via `/ll:`) are auto-detected as `slash_command` actions. Their default evaluator is `llm_structured`, which uses an LLM to judge whether the skill's output meets the expected quality criteria.

For deterministic routing — when the skill supports `--check` — override the evaluator to `exit_code` so the FSM routes on pass/fail without an LLM call:

```yaml
check-format:
  action: "/ll:format-issue --all --check"
  action_type: slash_command
  evaluate:
    type: exit_code
  on_yes: next-step
  on_no: fix-format
```

To compose multiple skill calls in a single state (e.g., run format then verify in sequence), use `action_type: prompt`:

```yaml
refine-and-score:
  action: "Run /ll:refine-issue on ${captured.current_item.output}, then run /ll:format-issue --check on the same file."
  action_type: prompt
  next: advance
```

See [Pattern: Using `--check` with Exit Code Evaluators](#pattern-using---check-with-exit-code-evaluators) for a worked multi-skill loop example.

#### MCP Tool Actions

MCP tool actions call a registered MCP server tool directly from a loop state. Unlike shell and slash commands, the type is **not** auto-detected — you must set `action_type: mcp_tool` explicitly.

```yaml
get-issue-details:
  action: "github/get_issue"
  action_type: mcp_tool
  params:
    owner: "${context.repo_owner}"
    repo: "${context.repo_name}"
    issue_number: "${captured.current_item.output}"
  capture: issue_data
  next: process-issue
```

Key fields:
- `action`: `"server_name/tool_name"` — must match a tool registered in `.mcp.json`
- `params`: JSON object passed to the tool; supports `${variable}` interpolation
- `capture`: optional — stores the tool's response for use in later states

The default evaluator for `mcp_tool` states is `mcp_result` (no need to specify it). Verdict table:

| Verdict | Meaning | Exit code analogue |
|---------|---------|-------------------|
| `success` | Tool returned a result | 0 |
| `tool_error` | Tool ran but returned an error response | 1 |
| `not_found` | Server or tool not registered in `.mcp.json` | 127 |
| `timeout` | Transport-level timeout (default 30 s) | 124 |

Route on these verdicts using a route table:

```yaml
get-issue-details:
  action: "github/get_issue"
  action_type: mcp_tool
  params:
    owner: "${context.repo_owner}"
    repo: "${context.repo_name}"
    issue_number: "${captured.current_item.output}"
  capture: issue_data
  route:
    success: process-issue
    tool_error: log-error
    not_found: abort
    timeout: retry-fetch
```

MCP tools also appear as `check_mcp` evaluation gates in harness loops — a deterministic external-state check that runs before the more expensive LLM phases. See [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) for details.

### Handoff Behavior

When a loop detects that Claude's context window is approaching its limit, it triggers a **handoff**:

| Mode | `on_handoff:` value | Behavior |
|------|---------------------|----------|
| Pause | `pause` (default) | Save state to disk, resume later with `ll-loop resume` |
| Spawn | `spawn` | Save state and launch a fresh Claude session to continue |
| Terminate | `terminate` | Stop the loop immediately (state is not saved) |

Set `on_handoff` at the **loop level** (not per state):

```yaml
name: issue-refinement
on_handoff: spawn        # loop-level field
max_iterations: 20
states:
  discover:
    action: "ll-issues list --status active"
    capture: active_issues
    next: refine
  refine:
    action: "/ll:refine-issue ${captured.active_issues.output}"
    action_type: slash_command
    next: discover
  done:
    terminal: true
```

**Choosing a mode:**

- **`spawn`** — best for long-running automated loops that should continue without human intervention: issue processing pipelines, APO loops, sprint workflows. A fresh session picks up exactly where the previous one left off.
- **`pause`** (default) — best for metric-tracking or monitoring loops where reviewing state between sessions is desirable: RL loops, worktree health checks. Requires manual `ll-loop resume <name>` to continue.
- **`terminate`** — use when partial execution is worse than none. For example, if the loop rewrites a file atomically and a partial run would leave it in a corrupt intermediate state.

**What is preserved** across a pause or spawn handoff:

- Current state name and iteration count
- All `captured` variable values from completed states
- Loop-level `context` variables

On resume (manual or automatic), the engine re-enters the state where the handoff occurred and re-runs its action with full variable context restored.

For interactive session handoff details see [Session Handoff](SESSION_HANDOFF.md).

### Scope-Based Concurrency

The `scope:` field declares which paths a loop operates on. The engine uses file-based locking to prevent two loops from modifying the same files simultaneously.

```yaml
scope:
  - "src/"
  - "tests/"
```

If a conflicting loop is already running, `ll-loop run` will error. Use `--queue` to wait for the conflict to resolve instead.

## Prompt Optimization Loops (APO)

Automatic Prompt Optimization (APO) loops apply iterative improvement techniques to refine prompts using LLM-driven evaluation. They are a practical alternative to manual prompt engineering: instead of tweaking prompts by hand, you describe your criteria and let the loop drive convergence.

Five built-in APO loops ship with little-loops:

### `apo-feedback-refinement` — Feedback-Driven Refinement

**Technique**: Generate one improved candidate → evaluate against criteria → apply feedback → repeat until convergence.

**When to use**: You have a single target prompt and a clear quality rubric. Good for system prompts that produce inconsistent outputs — the evaluator diagnoses what's wrong and the refinement step fixes it.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria the evaluator uses to score candidates |
| `quality_threshold` | `85` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults (improves system.md in the current directory)
ll-loop apo-feedback-refinement

# Override context variables
ll-loop apo-feedback-refinement \
  --context prompt_file=prompts/classifier.md \
  --context eval_criteria="accuracy and conciseness" \
  --context quality_threshold=90

# Load explicitly from built-ins (bypasses project .loops/)
ll-loop run --builtin apo-feedback-refinement --context prompt_file=system.md
```

**FSM flow**:
```
generate_candidate → evaluate_candidate → route_convergence
                                          ├─ CONVERGED → apply_candidate → done
                                          └─ NEEDS_REFINE → refine → generate_candidate
```

---

### `apo-contrastive` — Contrastive Optimization

**Technique**: Generate N diverse variants → score comparatively → select the best → update the file → repeat until convergence.

**When to use**: You want broader exploration of the prompt space per iteration. Each round explores N distinct directions and keeps the winner, so the loop avoids local optima that single-candidate refinement can get stuck in.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria used to score each variant |
| `num_variants` | `3` | Number of distinct variants to generate per iteration |
| `quality_threshold` | `90` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults
ll-loop apo-contrastive

# Tune for deeper search
ll-loop apo-contrastive \
  --context prompt_file=prompts/system.md \
  --context num_variants=5 \
  --context quality_threshold=95
```

**FSM flow**:
```
generate_variants → score_and_select → route_convergence
                                       ├─ CONVERGED → done
                                       └─ CONTINUE → generate_variants
```

---

### `apo-opro` — OPRO-Style History-Guided Optimization

**Technique**: Maintain a running history of scored candidates → propose a new candidate informed by past successes and failures → evaluate and score it → append to history → repeat until convergence. Inspired by the OPRO (Optimization by PROmpting) approach: the accumulated score history acts as in-context gradient information, steering each new proposal away from previously observed weaknesses.

**When to use**: You want the optimizer to learn from its own history across iterations. Each proposal is explicitly conditioned on what was tried before and how it scored, so the loop avoids re-proposing variants with known weaknesses. This makes it better than `apo-feedback-refinement` (single candidate, no memory) for runs where early proposals reveal recurring failure patterns that need to be systematically avoided.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria the evaluator uses to score candidates |
| `target_score` | `90` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults (improves system.md in the current directory)
ll-loop apo-opro

# Customize prompt file and criteria
ll-loop apo-opro \
  --context prompt_file=prompts/classifier.md \
  --context eval_criteria="accuracy and conciseness" \
  --context target_score=85

# Install to project for customization
ll-loop install apo-opro
```

**FSM flow**:
```
init_history → propose_candidate → evaluate_candidate → update_history → route_convergence
                    ↑                                                              │
                    └──────────────────── CONTINUE ─────────────────────────────────┘
                                                                                   │
                                                                  CONVERGED → done
```

---

### `apo-beam` — Beam Search Optimization

**Technique**: Generate N variants in parallel → score all → advance the highest-scoring winner → repeat until convergence.

**When to use**: You have already tried linear refinement (`apo-feedback-refinement` or `apo-contrastive`) and hit a plateau. Beam search explores `beam_width` directions simultaneously each iteration rather than following a single candidate forward. This makes it less likely to stay trapped in a local optimum and more likely to find a qualitatively different high-scoring prompt region.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `""` | Criteria used to score each variant |
| `beam_width` | `4` | Number of distinct variants generated per iteration |
| `target_score` | `90` | Score (0–100) at which the loop emits `CONVERGED` and terminates |

**Invocation**:

```bash
# Run with defaults (beam_width=4)
ll-loop apo-beam

# Wider beam for higher-stakes optimization
ll-loop apo-beam \
  --context prompt_file=prompts/triage.md \
  --context eval_criteria="correctly triage support tickets by severity" \
  --context beam_width=6 \
  --context target_score=88

# Install to project for customization
ll-loop install apo-beam
```

**FSM flow**:
```
generate_variants → score_variants → select_best → route_convergence
                                                    ├─ CONVERGED → done
                                                    └─ CONTINUE → generate_variants
```

---

### `apo-textgrad` — TextGrad (Example-Driven Gradient Descent)

**Technique**: Test the current prompt against a batch of input/output example pairs → compute a structured "text gradient" (failure pattern, root cause, and fix instruction) → apply the gradient to the prompt → repeat until the pass rate reaches the target.

**When to use**: You have a prompt and a concrete set of input/output examples where the prompt fails on a predictable subset. This is the most targeted APO strategy: failures on specific examples produce specific signals, driving faster convergence than holistic feedback for prompts with clear success criteria (classification, extraction, structured generation).

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `examples_file` | `examples.json` | Path to a JSON array of `{"input": ..., "expected": ...}` pairs |
| `target_pass_rate` | `90` | Pass rate (0–100) at which the loop considers the prompt converged |

**`examples_file` format**:

```json
[
  { "input": "Support ticket text...", "expected": "HIGH" },
  { "input": "Another ticket...", "expected": "LOW" }
]
```

Each object must have an `input` field (the text to pass to the prompt) and an `expected` field (the correct output). Arrays of 10–20 examples are typical; larger sets increase signal quality at the cost of more LLM calls per iteration.

**Invocation**:

```bash
# Run with defaults (system.md + examples.json in current directory)
ll-loop apo-textgrad

# Point at specific prompt and examples files
ll-loop apo-textgrad \
  --context prompt_file=prompts/extractor.md \
  --context examples_file=tests/extraction-examples.json \
  --context target_pass_rate=95

# Install to project for customization
ll-loop install apo-textgrad
```

**FSM flow**:
```
test_on_examples → compute_gradient → route_convergence
                                      ├─ CONVERGED → done
                                      └─ CONTINUE → apply_gradient → test_on_examples
```

---

### Choosing Between APO Loops

| | `apo-feedback-refinement` | `apo-contrastive` | `apo-opro` | `apo-beam` | `apo-textgrad` |
|---|---|---|---|---|---|
| Exploration per iteration | Low (single candidate) | Medium (N candidates, comparative) | Low (history-guided single candidate) | High (N parallel candidates, independent) | Low (single targeted refinement) |
| Convergence speed | Fastest when feedback is precise | Moderate | Moderate | Slowest (most LLM calls) | Fast when examples have clear correct answers |
| Local optima risk | High | Moderate | Moderate | Low | Low (example failures provide precise signal) |
| Best for | Targeted improvement with clear criteria | Broad style exploration | Long runs where history improves proposals | Escaping plateaus, high-variance search spaces | Prompts with measurable pass/fail examples (classification, extraction) |

### Tips for APO Loops

- **Start with a concrete `eval_criteria`**: vague criteria produce vague scores. Instead of `"good"`, try `"responds only with valid JSON, handles edge cases, and explains its reasoning"`.
- **Set `quality_threshold` conservatively**: start at 80 and raise once the loop reaches it. Overly strict thresholds burn iterations without improvement.
- **Check the prompt file after each run**: the loop writes back to the file in-place. Use `git diff` to review the evolution across iterations.
- **Install to customize**: run `ll-loop install apo-feedback-refinement` to copy the YAML to `.loops/` and edit state actions or add custom evaluation logic.

## Harness Loops

A **harness loop** is a pre-structured FSM pattern that wraps a skill or prompt in a layered quality evaluation pipeline, then repeats over a list of work items — or runs once in single-shot mode. The `/ll:create-loop` wizard auto-derives the evaluation framework from your project config so you don't write it by hand.

The core idea: running a skill is easy; knowing the output is actually good is hard. A harness solves this by passing each result through up to five evaluation phases before advancing.

### The Evaluation Pipeline

Each harness applies phases in sequence, cheapest first:

| Phase | What it checks | Evaluator | Approx. latency |
|-------|----------------|-----------|-----------------|
| `check_concrete` | Exit code from test/lint/type command — objective, fast | `exit_code` | < 1s |
| `check_mcp` | MCP server tool call — deterministic external state | `mcp_result` | ~500ms |
| `check_skill` | Full agentic user simulation — did it work as a real user would? | `llm_structured` | 30–300s |
| `check_semantic` | LLM judges output quality — semantic correctness | `llm_structured` | 3–10s |
| `check_invariants` | Diff line count — catches runaway changes | `output_numeric` | < 1s |

All phases are optional; the wizard pre-selects based on your project config and what tools are registered. Running cheapest first means expensive LLM calls only happen when objective gates already pass.

### Creating a Harness

Run `/ll:create-loop` and select **"Harness a skill or prompt"**. The 4-step wizard asks:

1. **Target** — pick a discovered skill or enter a custom prompt (plus a "done looks like" criterion for the LLM judge)
2. **Work items** — single-shot, active issues list, file glob, or manual list
3. **Evaluation phases** — which of the five phases to include (pre-selected from config)
4. **Iteration budget** — retries per item and total `max_iterations`

### FSM Structure

**Single-shot** (no discovery): starts directly at `execute`, runs the evaluation chain once, reaches `done`.

**Multi-item** (issues list / glob / manual): adds `discover` and `advance` states around the evaluation chain:

```
discover ──→ execute ──→ check_concrete ──→ check_semantic ──→ check_invariants ──→ advance ──→ discover
               ↑              │ on_no              │ on_no              │ on_no
               └──────────────┴────────────────────┘
no items remaining ──→ done
```

The critical safeguard in multi-item loops is `max_retries` + `on_retry_exhausted: advance` on the `execute` state — without it, one item that never passes evaluation consumes the entire `max_iterations` budget:

```yaml
execute:
  action: /ll:refine-issue ${captured.current_item.output} --auto
  action_type: prompt
  max_retries: 3
  on_retry_exhausted: advance
  next: check_concrete
```

### Stall Detection

For prompt-based skills that may produce no-ops ("already done"), add a `check_stall` state using the `diff_stall` evaluator between `execute` and the first check state. Without it, idempotent skills silently exhaust `max_iterations` without progress:

```yaml
check_stall:
  action: "echo 'checking stall'"
  action_type: shell
  evaluate:
    type: diff_stall
    max_stall: 2
  on_yes: check_concrete    # progress detected — continue evaluation
  on_no: advance            # stalled — skip this item
```

### When to Use a Harness vs. Hand-Authored Loop

| Approach | Effort | Best for |
|----------|--------|----------|
| Harness wizard | ~2 min | Wrapping a skill in quality gates; batch processing with standard evaluation |
| Hand-authored YAML | 30–60 min | Multi-branch routing, complex captured-variable logic, non-standard evaluation |

For full details on evaluation phases, MCP gates, skill-as-judge, stall detection, and worked examples, see the **[Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md)**.

---

## CLI Quick Reference

### Subcommands

| Command | Description |
|---------|-------------|
| `ll-loop run <name>` | Run a loop (also: `ll-loop <name>`) |
| `ll-loop validate <name>` | Check YAML for schema errors and unreachable states |
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram (`--json` for raw FSM config) |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions |
| `ll-loop list` | List available loops (`--running` for active only, `--builtin` for built-ins only) |
| `ll-loop status <name>` | Show current state and iteration count (`--json` for machine-readable output) |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show history; pass `run_id` to view a specific archived run |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |

### History Flags

| Flag | Effect |
|------|--------|
| `--verbose` / `-v` | Show action output preview and LLM call details (model, latency, prompt, response) |
| `--full` | Show untruncated prompts and output (implies --verbose) |
| `--json` | Output events as JSON array |

### Run Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Show execution plan without running actions |
| `--no-llm` | Disable LLM-based evaluation (use deterministic evaluators only) |
| `--llm-model <model>` | Override the LLM model for evaluation |
| `-n <N>` | Override `max_iterations` |
| `--queue` | Wait for conflicting scoped loops instead of erroring |
| `-q` / `--quiet` | Suppress progress output |
| `-v` / `--verbose` | Show full prompt text and more output lines |
| `-b` / `--background` | Run as a background daemon |
| `--show-diagrams` | Display FSM box diagram with active state highlighted after each step |
| `--clear` | Clear terminal before each iteration; combine with `--show-diagrams` for a live in-place dashboard |
| `--delay <SECONDS>` | Sleep N seconds between iterations; overrides `backoff:` from YAML |
| `--context KEY=VALUE` | Override a context variable at runtime (repeatable) |

### Simulate Scenarios

The `simulate` command accepts `--scenario` to auto-select verdicts instead of prompting:

| Scenario | Behavior |
|----------|----------|
| `all-pass` | Every evaluation returns success/target |
| `all-fail` | Every evaluation returns failure/stall |
| `all-error` | Every evaluation returns error |
| `first-fail` | First evaluation fails, rest succeed |
| `alternating` | Alternates between success and failure |

## Pattern: Using `--check` with Exit Code Evaluators

Issue prep skills (`format-issue`, `verify-issues`, `ready-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`, `normalize-issues`, `prioritize-issues`) support a `--check` flag that runs analysis without side effects and exits non-zero when work remains. This makes them usable as FSM loop evaluators with `evaluate: type: exit_code`.

**Important**: Since `/ll:` commands are auto-detected as prompt actions by the executor, states using `--check` must explicitly set `evaluate: type: exit_code` to bypass LLM-structured evaluation.

### Example: Prep-Sprint Invariants Loop

```yaml
name: prep-sprint
description: |
  Ensure all active issues pass prep gates before sprint planning.
  Checks format compliance, verification, sizing, dependencies, and readiness.
initial: check-format
states:
  check-format:
    action: "/ll:format-issue --all --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: check-verify
    on_no: fix-format
  fix-format:
    action: "/ll:format-issue --all --auto"
    action_type: slash_command
    next: check-format
  check-verify:
    action: "/ll:verify-issues --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: check-size
    on_no: fix-verify
  fix-verify:
    action: "Run /ll:verify-issues --auto to fix verification issues."
    action_type: prompt
    next: check-verify
  check-size:
    action: "/ll:issue-size-review --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: check-deps
    on_no: fix-size
  fix-size:
    action: "Run /ll:issue-size-review --auto to decompose oversized issues."
    action_type: prompt
    next: check-size
  check-deps:
    action: "/ll:map-dependencies --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix-deps
  fix-deps:
    action: "/ll:map-dependencies --auto"
    action_type: slash_command
    next: check-deps
  done:
    terminal: true
max_iterations: 20
timeout: 3600
```

Each `check-*` state uses `evaluate: type: exit_code` to route on the skill's exit code (0=success, 1=failure). The corresponding `fix-*` states run the skill in auto mode to remediate, then loop back to re-check.

## Tips

- **Start with low `max_iterations`** (5-10) while developing a loop. Increase once the logic is proven.
- **Use `backoff:`** to add delay between iterations — useful for rate-limited APIs or CI systems.
- **State is persisted to disk** after every transition. If a loop is interrupted, `ll-loop resume` picks up where it left off.
- **Convergence loops** use `direction:` to control whether the metric should go down (`minimize`, default) or up (`maximize`).
- **Loop run state and event logs are automatically archived** to `.loops/.history/<loop-name>/<timestamp>/` when a new run starts. Use `ll-loop history <name>` without a `run_id` to list archived runs, or `ll-loop history <name> <run_id>` to inspect a specific one.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Loop stuck in a cycle | Fix action isn't changing the result the evaluator sees | Check `ll-loop history` — if the same verdict repeats, adjust the fix action |
| Scope conflict error | Another loop holds a lock on overlapping paths | Find it with `ll-loop list --running` and stop it, or use `--queue` to wait |
| LLM evaluator errors | Claude CLI auth or network issue | Ensure `claude` CLI is authenticated (`claude auth`), or use `--no-llm` to fall back to deterministic evaluators |
| "No state found" on resume | Loop already completed or was never started | Check `ll-loop status` — completed loops have no resumable state |

## Further Reading

- [FSM Loop System Design](../generalized-fsm-loop.md) — FSM schema, evaluators, variable interpolation, and full YAML reference
- [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) — Harness evaluation pipeline deep-dive, MCP gates, skill-as-judge, stall detection, and worked examples
- [Configuration Reference](../reference/CONFIGURATION.md) — Project-wide settings (test commands, paths, etc.) used by loop actions
- `/ll:create-loop` — Interactive loop creation wizard (includes harness mode)
- `/ll:review-loop` — Audit an existing loop for quality, correctness, and best practices
- `ll-loop --help` — Full CLI reference for all loop subcommands
