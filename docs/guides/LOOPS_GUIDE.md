# Loops Guide

## Contents

- [What Is a Loop?](#what-is-a-loop)
- [Quick Start](#quick-start)
- [How Loops Work](#how-loops-work)
- [Common Loop Patterns](#common-loop-patterns)
- [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop)
- [Built-in Loops](#built-in-loops)
- [Beyond the Basics](#beyond-the-basics)
- [Prompt Optimization Loops (APO)](#prompt-optimization-loops-apo)
- [Harness Loops](#harness-loops)
- [CLI Quick Reference](#cli-quick-reference)
- [Pattern: Using --check with Exit Code Evaluators](#pattern-using---check-with-exit-code-evaluators)
- [Tips](#tips)
- [Composable Sub-Loops](#composable-sub-loops)
- [Loop Discovery: category and labels](#loop-discovery-category-and-labels)
- [Reusable State Fragments](#reusable-state-fragments)
- [Troubleshooting](#troubleshooting)
- [Further Reading](#further-reading)

---

## What Is a Loop?

A loop is a YAML-defined automation workflow that runs commands, evaluates results, and decides what to do next — without you prompting each step. Under the hood, each loop is a **Finite State Machine (FSM)**: a set of states connected by transitions, with a clear start and end.

Why does this matter? LLMs are stateless — they don't remember what happened two prompts ago. The FSM gives them persistent memory of what was tried, what worked, and when to stop.

```
You write:    FSM YAML (or use /ll:create-loop)
You run:      ll-loop run <name>
```

## Quick Start

The fastest way to create and run a loop:

1. **Create**: `/ll:create-loop` — answer the wizard prompts
2. **Validate**: `ll-loop validate <name>` — check your YAML for errors
3. **Run**: `ll-loop run <name>` — start the loop

For a walkthrough of a real example, see [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop) below.

### When NOT to Use a Loop

Loops add overhead — a YAML file, state management, and retry logic. For a one-off task,
just run the command directly. Use a loop when you need: automatic retry on failure,
repeated execution on a schedule, or quality gates that must pass before moving forward.

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
├─ Fix a specific problem ──────────→ Fix until clean
│   "Run check, if fails run fix, repeat"
│
├─ Maintain multiple standards ─────→ Maintain constraints
│   "Check A, fix A, check B, fix B, ..."
│
├─ Reduce/increase a metric ────────→ Drive a metric
│   "Measure, if not at target, fix, measure again"
│
├─ Run ordered steps ───────────────→ Run a sequence
│   "Do step 1, do step 2, check if done, repeat"
│
├─ Apply a skill to many items ─────→ Harness a skill
│   "Discover items, run skill, pass evaluation pipeline, advance"
│
└─ Chain existing loops together ───→ Composable sub-loops
    "Run loop A, then loop B, using the same context"
```

| Loop type | States | Branching | Best for |
|-----------|--------|-----------|----------|
| Fix until clean | evaluate, fix, done | Binary (pass/fail) | Single check + fix |
| Drive a metric | measure, apply, done | Three-way (target/progress/stall) | Metric optimization |
| Maintain constraints | 2 per constraint + 1 | Binary per constraint | Multi-gate quality |
| Run a sequence | 1 per step + 2 | Binary exit check | Ordered workflows |
| Harness a skill | discover, execute, check_*, advance, done | Multi-phase evaluation (exit code → MCP → skill → LLM → diff) | Batch processing with layered quality gates |
| Composable sub-loops | 1 per child loop + done | Binary (success/failure) per child | Multi-stage pipelines from existing loops |

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

### 3. Test (Dry Run)

Run a single iteration to verify the loop configuration without a full execution:

```bash
ll-loop test fix-tests
```

This executes one iteration from the initial state, prints the action, result, and routing decision, then stops. Use it to confirm the YAML is wired correctly before committing to a full run.

### 4. Simulate

Step through the loop interactively without running any actions — useful for tracing paths through complex FSMs:

```bash
ll-loop simulate fix-tests
```

The simulator prompts you to choose a verdict at each state, then follows the transition and shows you the next state. Use `--scenario all-pass` or `--scenario all-fail` to auto-select verdicts and trace a path without interactive prompts:

```bash
ll-loop simulate fix-tests --scenario all-pass
```

### 5. Inspect

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
  │ evaluate │───success──→│ done │
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

### 6. Run

```bash
ll-loop run fix-tests
```

The engine enters `evaluate`, runs `pytest tests/`, checks the exit code, and follows the transition. If tests fail, it enters `fix`, sends the fix prompt to Claude, then returns to `evaluate`. This continues until tests pass or `max_iterations` is reached.

### 7. Monitor

```bash
ll-loop status fix-tests     # Current state and iteration count
ll-loop history fix-tests    # Full execution history
```

## Built-in Loops

These loops ship with little-loops and cover common workflows. Install one to `.loops/` to customize it:

```bash
ll-loop install <name>       # Copies to .loops/ for editing
```

**General-Purpose**

| Loop | Description |
|------|-------------|
| `dataset-curation` | Scan raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish a curated dataset |
| `general-task` | Definition-of-done driven task loop — define verifiable criteria first, then execute and verify until all criteria pass |
| `greenfield-builder` | End-to-end greenfield project builder: spec analysis → tech research → design artifacts → eval harness → issue decomposition → refinement → eval-driven improvement cycle |
| `eval-driven-development` | Reusable eval-driven development cycle: implement issues, run eval harness, capture issues from failures, refine, and iterate until the harness passes |
| `refine-to-ready-issue` | Single-issue refinement pipeline — format → refine → confidence-check → ready-issue until the issue reaches ready status |

The `general-task` loop requires the `input` context variable — a natural-language description of the task to complete:

```bash
ll-loop run general-task --context input="Refactor the auth module to use dependency injection"
```

The loop follows a structured cycle:

1. **Define Done** — writes verifiable acceptance criteria to `.loops/tmp/general-task-dod.md`
2. **Plan** — decomposes the task into discrete steps in `.loops/tmp/general-task-plan.md`
3. **Execute** — completes the first unchecked step and marks it done in the plan
4. **Verify** — checks each DoD criterion against actual filesystem/command output (uses `llm_structured` evaluation)
5. **Continue** — if any criteria remain unchecked, loops back to execute the next step

The loop runs up to 100 iterations and uses `on_handoff: spawn` to continue across session boundaries. Each execution step is deliberately scoped to a single plan item to keep changes small and verifiable.

The `refine-to-ready-issue` loop uses configurable confidence thresholds (default: readiness > 90, outcome confidence > 75). Override per-run:

```bash
ll-loop run refine-to-ready-issue --context readiness_threshold=85 --context outcome_threshold=70
```

To apply project-wide defaults, set `commands.confidence_gate.readiness_threshold` / `outcome_threshold` in `ll-config.json`, then install the loop locally (`ll-loop install refine-to-ready-issue`) and update its `context:` block defaults.

**Timeout recovery**: If `confidence_check` encounters an unexpected Python error, the loop falls back to `check_scores_from_file` — a deterministic recovery state that reads `confidence_score` and `outcome_confidence` directly from the issue's frontmatter via `ll-issues show --json`. If both scores meet the thresholds, the loop routes to `done`; otherwise it routes to `failed`.

**Refine limit guard**: The loop enforces a **lifetime cap** on total `/ll:refine-issue` calls per issue across all loop runs. Before each refinement, the `check_lifetime_limit` state reads the issue's cumulative `refine_count` from `ll-issues refine-status --json` and compares it against `commands.max_refine_count` in `ll-config.json` (default: **5**, range: 1–20). If the cap is reached, the loop routes to `breakdown_issue` (invoking `/ll:issue-size-review`) rather than failing — a persistent readiness gap after multiple refinement passes signals a scope problem, not a content problem. To raise the limit, set `commands.max_refine_count` in your `ll-config.json`.

**Issue Management**

| Loop | Description |
|------|-------------|
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `evaluation-quality` | Multi-dimensional quality health check across issue quality, code quality, and backlog health; routes to remediation loops when thresholds are breached |
| `issue-discovery-triage` | Automated issue discovery and triage cycle |
| `issue-refinement` | Progressively refine all active issues — delegates per-issue refinement to the `refine-to-ready-issue` sub-loop with commit cadence |
| `issue-size-split` | Review issues for sizing and split oversized ones |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder in your prompt to inject each issue's ID |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `sprint-build-and-validate` | Create a sprint from the backlog and validate all included issues |

**Code Quality**

| Loop | Description |
|------|-------------|
| `context-health-monitor` | Monitor context health via scratch file accumulation and session log size; compacts scratch files and archives stale outputs when pressure is detected |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass |
| `docs-sync` | Verify documentation matches the codebase and check for broken links |
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `incremental-refactor` | Decompose a refactoring goal into safe atomic steps, execute each with test-gated commits, rollback and re-plan on failure |
| `test-coverage-improvement` | Measure test coverage, identify uncovered code paths, write tests for highest-risk gaps, and converge when coverage target is met |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches |

**Evaluation**

| Loop | Description |
|------|-------------|
| `outer-loop-eval` | Analyze a target loop by loading its YAML definition, executing it as a sub-loop, and producing a structured improvement report covering state coverage, missing routes, evaluator types, context variable hygiene, and cycle risks |

**Reinforcement Learning (RL)**

| Loop | Description |
|------|-------------|
| `agent-eval-improve` | Evaluate an AI agent on a task suite, score outputs, identify failure patterns, and iteratively refine agent config/prompts until quality target is reached. Exits `done` on convergence or no actionable patterns; exits `failed` when any state exhausts its `max_retries` |
| `rl-bandit` | Epsilon-greedy bandit loop — explore vs exploit rounds routing on reward convergence |
| `rl-coding-agent` | Policy+RLHF composite loop for agentic coding — outer policy loop adapts coding strategy while inner RLHF loop polishes each artifact to a quality threshold |
| `rl-policy` | Policy iteration loop — act, observe reward, improve policy toward a target |
| `rl-rlhf` | RLHF-style loop — generate candidate output, score quality, refine until target met |

**Automatic Prompt Optimization (APO)**

| Loop | Description |
|------|-------------|
| `apo-beam` | Beam search prompt optimization — generate N variants, score all, advance the winner |
| `apo-contrastive` | Contrastive APO — generate N variants → score comparatively → select best → repeat |
| `apo-feedback-refinement` | Feedback-driven APO — generate → evaluate → refine until convergence |
| `apo-opro` | OPRO-style prompt optimization — history-guided proposal until convergence |
| `apo-textgrad` | TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement |
| `examples-miner` | Co-evolutionary corpus mining — harvest completed issue sessions, quality-gate, calibrate difficulty band, synthesize adversarial examples; runs `apo-textgrad` as a child loop |
| `prompt-regression-test` | CI for prompts — run a prompt suite, score against baseline, flag regressions, and trigger APO repair when quality drops |

**Harness Examples**

| Loop | Description |
|------|-------------|
| `harness-single-shot` | Annotated single-shot harness example — all evaluation phases with commented-out optional gates |
| `harness-multi-item` | Annotated multi-item harness example — all five evaluation phases active over a discovered item list |

## Beyond the Basics

The sections below cover features you'll encounter as you move past simple loops: evaluators, variable interpolation, capture, routing, action types, retry and timing fields, handoff behavior, and scope-based concurrency. For full technical details — schema definitions, compiler internals, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md).

### Evaluators

Evaluators interpret action output and produce a **verdict** string used for routing. Every state gets a default evaluator based on its action type.

| Evaluator | Verdicts | Default for | When to use |
|-----------|----------|-------------|-------------|
| `exit_code` | `yes` / `no` / `error` | shell commands | CLI tools that report pass/fail via exit code |
| `output_numeric` | `yes` / `no` / `error` | — | Compare parsed numeric output to a target |
| `output_json` | `yes` / `no` / `error` | — | Extract a JSON path value and compare |
| `output_contains` | `yes` / `no` | — | Regex or substring match on stdout |
| `convergence` | `target` / `progress` / `stall` | metric-tracking states | Track a metric toward a goal value |
| `diff_stall` | `yes` / `no` / `error` | — | Detect when consecutive iterations produce no git diff changes (see [Stall Detection](#stall-detection)) |
| `llm_structured` | `yes` / `no` / `blocked` / `partial` | slash commands | Natural-language judgment via LLM |
| `mcp_result` | `success` / `tool_error` / `not_found` / `timeout` | `mcp_tool` actions | Evaluate MCP server tool call results; see [MCP Tool Actions](#mcp-tool-actions) for verdict details |

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

### Retry and Timing Fields

These optional fields can be added to any state:

| Field | Type | Description |
|-------|------|-------------|
| `backoff:` | number (seconds) | Delay before executing this state's action. Useful for rate-limited APIs or CI systems. Overridden at runtime by `--delay <SECONDS>`. |
| `max_retries:` | integer | Maximum number of times the engine re-enters this state before triggering `on_retry_exhausted`. |
| `on_retry_exhausted:` | state name | Target state when `max_retries` is reached. Common pattern in harness loops: `on_retry_exhausted: advance` to skip a stuck item and continue processing. |

Example — skip an item after 3 failed attempts:

```yaml
execute:
  action: /ll:refine-issue ${captured.current_item.output} --auto
  action_type: prompt
  max_retries: 3
  on_retry_exhausted: advance
  next: check_concrete
```

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

### Per-Loop Config Overrides

Loop YAML files support an optional top-level `config:` block that embeds per-loop overrides for `ll-config` values. When `ll-loop run <loop-name>` is invoked, the `config:` block overrides the global `ll-config.json` for the session.

```yaml
name: exploratory-refactor
initial: analyze
on_handoff: spawn
config:
  handoff_threshold: 60            # overrides LL_HANDOFF_THRESHOLD
  commands:
    confidence_gate:
      readiness_threshold: 70
      outcome_threshold: 55
  automation:
    max_continuations: 5

states:
  analyze:
    # ...
```

**Precedence** (highest to lowest):
1. CLI flags (`--handoff-threshold`)
2. Loop YAML `config:` block
3. Global `ll-config.json`
4. Schema defaults

**Supported override keys:**

| Key | Description |
|-----|-------------|
| `handoff_threshold` | Override auto-handoff context threshold (1-100) |
| `commands.confidence_gate.readiness_threshold` | Override readiness gate threshold (1-100) |
| `commands.confidence_gate.outcome_threshold` | Override outcome confidence threshold (1-100) |
| `automation.max_continuations` | Override max continuation count (≥1) |
| `continuation.max_continuations` | Alias for `automation.max_continuations` — either key is accepted |

Config overrides apply equally to `ll-loop run` and `ll-loop resume`. CLI flags always take highest precedence and override both the YAML config block and global settings.

Use `ll-loop show <loop-name>` to verify which overrides are active — the header line displays any non-default config values.

### Scope-Based Concurrency

The `scope:` field declares which paths a loop operates on. The engine uses file-based locking to prevent two loops from modifying the same files simultaneously.

```yaml
scope:
  - "src/"
  - "tests/"
```

If a conflicting loop is already running, `ll-loop run` will error. Use `--queue` to wait for the conflict to resolve instead.

## Prompt Optimization Loops (APO)

> **Advanced** — APO loops tune prompts automatically. Most users won't need these.
> Start with standard loops and return here when you have a specific prompt quality problem.

Automatic Prompt Optimization (APO) loops apply iterative improvement techniques to refine prompts using LLM-driven evaluation. They are a practical alternative to manual prompt engineering: instead of tweaking prompts by hand, you describe your criteria and let the loop drive convergence.

Seven built-in APO loops ship with little-loops:

---

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
generate_candidate ──→ evaluate_candidate ──→ route_convergence
                                               ├─ CONVERGED ──→ apply_candidate ──→ done
                                               └─ NEEDS_REFINE ──→ refine ──→ generate_candidate
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
generate_variants ──→ score_and_select ──→ route_convergence
                                           ├─ CONVERGED ──→ done
                                           └─ CONTINUE ──→ generate_variants
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
init_history ──→ propose_candidate ──→ evaluate_candidate ──→ update_history ──→ route_convergence
                       ↑                                                                  │
                       └────────────────────── CONTINUE ───────────────────────────────────┘
                                                                                           │
                                                                          CONVERGED ──→ done
```

---

### `apo-beam` — Beam Search Optimization

**Technique**: Generate N variants in parallel → score all → advance the highest-scoring winner → repeat until convergence.

**When to use**: You have already tried linear refinement (`apo-feedback-refinement` or `apo-contrastive`) and hit a plateau. Beam search explores `beam_width` directions simultaneously each iteration rather than following a single candidate forward. This makes it less likely to stay trapped in a local optimum and more likely to find a qualitatively different high-scoring prompt region.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria used to score each variant |
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
generate_variants ──→ score_variants ──→ select_best ──→ route_convergence
                                                          ├─ CONVERGED ──→ done
                                                          └─ CONTINUE ──→ generate_variants
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
test_on_examples ──→ compute_gradient ──→ route_convergence
                                          ├─ CONVERGED ──→ done
                                          └─ CONTINUE ──→ apply_gradient ──→ test_on_examples
```

---

### `examples-miner` — Co-evolutionary Corpus Mining

**Technique**: Harvest skill invocations from completed issue session logs → quality-gate via a three-layer judge (code persistence, revision distance, oracle scoring) → calibrate to the 40–80% difficulty band → run `apo-textgrad` as a child loop to obtain a gradient signal → synthesize adversarial examples targeting the failure pattern → enforce diversity → publish a fresh `examples.json`.

**When to use**: After `apo-textgrad` has plateaued on hand-crafted examples, or after skill conventions have evolved and the static corpus is stale. The miner automatically harvests the project's own completed issues (800+ issues = implicit human approvals) and synthesizes adversarial examples from the current gradient's failure pattern.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `examples_file` | `examples.json` | Path where the fresh corpus is published |
| `prompt_file` | `system.md` | Prompt file passed to the inner apo-textgrad loop |
| `skill_name` | `capture-issue` | Skill to mine (e.g., `capture-issue`, `refine-issue`) |
| `corpus_state_file` | `corpus.json` | Optional: persisted calibration state for freshness decay |
| `target_pass_rate` | `0.6` | Center of the 40–80% difficulty band (fraction, 0–1) |

**Invocation**:

```bash
# Run with defaults (mines capture-issue sessions, publishes to examples.json)
ll-loop run examples-miner

# Mine a different skill with a custom examples file
ll-loop run examples-miner \
  --context skill_name=refine-issue \
  --context examples_file=tests/refine-examples.json \
  --context prompt_file=skills/refine-issue/SKILL.md

# Install to project for customization (hardcode oracle path for v2 sub-loop promotion)
ll-loop install examples-miner
```

**FSM flow**:
```
harvest ──→ judge ──→ calibrate ──→ write_examples ──→ run_optimizer (sub-loop: apo-textgrad)
                                                         ├─ SUCCESS ──→ synthesize ──→ screen_adversarial ──→ score_adversarial ──→ merge ──→ diversify ──→ publish ──→ done
                                                         └─ FAILURE ──→ diversify ──→ publish ──→ done
```

**Three-layer quality judge**:

| Layer | Mechanism | What it checks |
|-------|-----------|----------------|
| 1. Code persistence | `git log --follow` via Bash | `files_modified` still present in HEAD; persistence age (commit count without revert) |
| 2. Revision distance | Session log entry count | Low session count → output accepted quickly (low distance); many refinement sessions → high distance |
| 3. Oracle rubric | Inline LLM scoring | Tool selection quality, file path relevance, completion status (0–100 pts per candidate) |

Only candidates that survive all three layers and fall in the 40–80% pass-rate band enter the active calibrated set.

**Adversarial synthesis perturbation taxonomy** (gradient `FAILURE_PATTERN` selects type):

| Type | What it does |
|------|-------------|
| `complexity_injection` | Adds a second symptom that may or may not belong in the same issue — tests scope boundary judgment |
| `ambiguity_injection` | Strips specific file/function names, forcing discovery rather than copying references |
| `domain_shift` | Reproduces the same failure pattern in a different subsystem — tests generalization |
| `priority_boundary` | Edge case sitting between two adjacent priority levels |
| `type_confusion` | Description that looks like FEAT but is BUG (or vice versa) |

**Adversarial cap**: `source: adversarial` examples are capped at ≤ 30% of the final corpus at all times.

**Sentinel-based incremental harvest**: The `publish` state writes `corpus.last_harvested` with the current UTC timestamp. On the next run, `harvest` passes `--since <timestamp>` to `ll-messages` so only new sessions are re-processed. On the first run the sentinel file is absent and all sessions are harvested.

**Pairing with apo-textgrad** (recommended workflow):

```bash
# Step 1: Build a fresh corpus from project history
ll-loop run examples-miner --context skill_name=capture-issue

# Step 2: Run apo-textgrad against the mined corpus
ll-loop run apo-textgrad \
  --context prompt_file=skills/capture-issue/SKILL.md \
  --context examples_file=examples.json

# Or: run examples-miner once — it calls apo-textgrad internally as run_optimizer
ll-loop run examples-miner \
  --context skill_name=capture-issue \
  --context prompt_file=skills/capture-issue/SKILL.md
```

**Oracle sub-loop (v2)**: The `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` file provides a two-phase oracle (mechanical checks + semantic LLM scoring) that can be promoted to a sub-loop in a customized `examples-miner.yaml` via `loop: oracles/oracle-capture-issue` + `context_passthrough: true` on the `judge` state. The built-in `examples-miner.yaml` uses inline oracle scoring (v1 approach) — install and customize to enable sub-loop promotion.

---

### `prompt-regression-test` — Prompt CI / Regression Detection

**Technique**: Run a prompt suite against an LLM endpoint, score outputs against expected results, compare scores to a stored baseline, flag regressions, and optionally trigger an `apo-textgrad` sub-loop to repair the regressed prompt before updating the baseline.

**When to use**: Continuous integration for prompts — detect quality regressions when you change the model, system configuration, or surrounding code that a prompt depends on. Unlike other APO loops that optimize a prompt toward a target, `prompt-regression-test` defends a known-good baseline and only triggers optimization when a regression is detected.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_suite` | `prompts/` | Directory containing prompt files to test |
| `baseline_file` | `.loops/tmp/prompt-baseline.json` | Stored baseline scores (created on first run) |
| `pass_threshold` | `90` | Pass rate (0–100) at which the loop considers the suite healthy |

**Invocation**:

```bash
# Run with defaults (tests all prompts in prompts/ directory)
ll-loop run prompt-regression-test

# Point at a specific prompt directory and threshold
ll-loop run prompt-regression-test \
  --context prompt_suite=tests/prompts/ \
  --context pass_threshold=85

# Install to project for customization
ll-loop install prompt-regression-test
```

**FSM flow**:
```
run_suite ──→ score_outputs ──→ compare_baseline ──→ route_regression
                                                       ├─ NO_REGRESSION ──→ report ──→ done
                                                       └─ REGRESSION ──→ trigger_apo (sub-loop: apo-textgrad)
                                                                              ├─ SUCCESS ──→ update_baseline ──→ done
                                                                              └─ FAILURE/ERROR ──→ report ──→ done
```

**First run baseline**: On the first run `baseline_file` does not exist — the loop creates it from the initial suite results and exits with a clean report. Subsequent runs compare against this stored baseline. To reset: delete `baseline_file` before the next run.

**Pairing with `examples-miner`** (recommended workflow for persistent regressions):

```bash
# Step 1: Mine a fresh example corpus for the regressed prompt
ll-loop run examples-miner --context skill_name=my-prompt

# Step 2: Run regression test — triggers apo-textgrad automatically on failure
ll-loop run prompt-regression-test \
  --context prompt_suite=prompts/ \
  --context pass_threshold=90
```

---

### Choosing Between APO Loops

| Trigger | Recommended loop |
|---------|-----------------|
| Output quality varies run-to-run | `apo-feedback-refinement` |
| Need to compare two prompt versions | `apo-contrastive` |
| Optimizing a prompt against a fixed metric | `apo-opro` |
| Want to explore multiple prompt candidates | `apo-beam` |
| Have gradient-like feedback signals | `apo-textgrad` |
| Building a training example corpus | `examples-miner` |
| Prompt quality has regressed vs. baseline | `prompt-regression-test` |

| | `apo-feedback-refinement` | `apo-contrastive` | `apo-opro` | `apo-beam` | `apo-textgrad` | `prompt-regression-test` |
|---|---|---|---|---|---|---|
| Exploration per iteration | Low (single candidate) | Medium (N candidates, comparative) | Low (history-guided single candidate) | High (N parallel candidates, independent) | Low (single targeted refinement) | Low (one repair pass via apo-textgrad) |
| Convergence speed | Fastest when feedback is precise | Moderate | Moderate | Slowest (most LLM calls) | Fast when examples have clear correct answers | Fast when regression has concrete failing examples |
| Local optima risk | High | Moderate | Moderate | Low | Low (example failures provide precise signal) | Low (triggered only by concrete regressions) |
| Best for | Targeted improvement with clear criteria | Broad style exploration | Long runs where history improves proposals | Escaping plateaus, high-variance search spaces | Prompts with measurable pass/fail examples (classification, extraction) | CI integration; defending a known-good quality baseline |

### Tips for APO Loops

- **Start with a concrete `eval_criteria`**: vague criteria produce vague scores. Instead of `"good"`, try `"responds only with valid JSON, handles edge cases, and explains its reasoning"`.
- **Set `quality_threshold` conservatively**: start at 80 and raise once the loop reaches it. Overly strict thresholds burn iterations without improvement.
- **Check the prompt file after each run**: the loop writes back to the file in-place. Use `git diff` to review the evolution across iterations.
- **Install to customize**: run `ll-loop install apo-feedback-refinement` to copy the YAML to `.loops/` and edit state actions or add custom evaluation logic.

## Evaluation Loops

Loops in this category analyze other loops — auditing their YAML definitions, running them as sub-loops, and producing structured improvement reports.

### `outer-loop-eval` — Loop Structure & Execution Auditor

**Technique**: Load a target loop's YAML definition, execute it as a sub-loop against an optional input, then combine a static definition analysis with a live execution trace to produce a structured improvement report covering five dimensions: Structural Issues, Logic Issues, Flow Issues, Component Improvements, and Suggested YAML Changes.

**When to use**: After writing or significantly modifying a loop — or before sharing it. `outer-loop-eval` catches missing `on_error` routes, cycle risks, uninitialized context variables, evaluator type mismatches, and redundant state hops that manual review often misses.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `loop_name` | _(required)_ | Target loop name — built-in (`outer-loop-eval`) or project-level (`.loops/my-loop`) |
| `input` | `""` | Optional input value passed to the sub-loop when it runs |

**Invocation**:

```bash
# Audit a built-in loop
ll-loop run outer-loop-eval --context loop_name=issue-refinement

# Audit a project-level loop with an input
ll-loop run outer-loop-eval \
  --context loop_name=my-custom-loop \
  --context input="some context value"

# Install to project for customization
ll-loop install outer-loop-eval
```

**FSM flow**:
```
analyze_definition → run_sub_loop → analyze_execution → generate_report
                                                             ├─ YES (has findings) → done
                                                             └─ NO (all "None identified.") → refine_analysis → generate_report
```

**Execution failure handling**: If the target loop fails to start (not found, crashes on launch), `outer-loop-eval` captures the error output and feeds it to `analyze_execution` as-is. The final report will still include structural findings derived from the definition analysis — making the audit useful even when the sub-loop cannot run.

**Report sections**: The improvement report always includes these exact headings:
- **Structural Issues** — unreachable states, undefined routes, orphaned states
- **Logic Issues** — incorrect evaluator types, wrong routing, context variable misuse
- **Flow Issues** — redundant hops, timeout risks, missing `on_error` routes
- **Component Improvements** — state-level suggestions: better prompts, tighter evaluators, clearer capture keys
- **Suggested YAML Changes** — concrete diff-style or annotated edits ready to copy into the YAML file

---

## Harness Loops

> **Advanced** — See [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) for the
> full harness guide. This section is a brief overview.

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

_(simplified — omits optional `check_mcp` and `check_skill` phases)_

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
| `ll-loop run <name>` | Run a loop (also: `ll-loop <name>`); use `--worktree` for isolated branch execution |
| `ll-loop validate <name>` | Check YAML for schema errors and unreachable states |
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram (`--json` for raw FSM config) |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions |
| `ll-loop list` | List available loops; `--running` for active only, `--builtin` for built-ins, `--category <cat>` / `--label <tag>` to filter by category or label |
| `ll-loop status <name>` | Show current state and iteration count (`--json` for machine-readable output) |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show history; pass `run_id` to view a specific archived run |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |

### History Flags

| Flag | Effect |
|------|--------|
| `--tail` / `-n` | Limit output to last N events (default: 50) |
| `--event` / `-e` | Filter by event type (e.g. `evaluate`, `route`, `state_enter`) |
| `--state` / `-s` | Filter by state name (matches `state`, `from`, or `to` fields) |
| `--since` | Filter to events within a time window (e.g. `1h`, `30m`, `2d`) |
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
- **Use `backoff:`** to add a delay before a state's action executes — useful for rate-limited APIs or CI systems.
- **State is persisted to disk** after every transition. If a loop is interrupted, `ll-loop resume` picks up where it left off.
- **Convergence loops** use `direction:` to control whether the metric should go down (`minimize`, default) or up (`maximize`).
- **Loop run state and event logs are automatically archived** to `.loops/.history/<timestamp>-<loop-name>/` when a new run starts. Use `ll-loop history <name>` without a `run_id` to list archived runs, or `ll-loop history <name> <run_id>` to inspect a specific one.

## Composable Sub-Loops

Any loop can invoke another loop as a **child FSM** using the `loop:` field on a state. The child runs to completion; its result (`success` or `failure`) drives the parent's transition. This lets you build multi-stage pipelines from loops that already exist — without duplicating logic.

### Minimal Example

```yaml
name: "quality-then-ship"
initial: "run_quality"
max_iterations: 3
states:
  run_quality:
    loop: "fix-quality-and-tests"   # runs the built-in loop as a child
    on_success: "run_git"
    on_failure: "done"
  run_git:
    loop: "issue-refinement-git"
    on_success: "done"
    on_failure: "done"
  done:
    terminal: true
```

### Sharing Context Between Parent and Child

Add `context_passthrough: true` to share the parent's `context` and `captured` variables with the child loop, and merge the child's captures back into the parent when it completes:

```yaml
states:
  run_quality:
    loop: "fix-quality-and-tests"
    context_passthrough: true       # child sees parent context; parent gets child captures
    on_success: "run_git"
    on_failure: "done"
```

Without `context_passthrough`, the child runs with its own isolated context and its captured values are discarded after it exits.

### Routing Aliases

`on_success` and `on_failure` are accepted as aliases for `on_yes` and `on_no` in all states (not just sub-loop states). Use whichever reads more clearly for your use case.

### When to Use Sub-Loops vs. Inline States

| Approach | Best for |
|----------|----------|
| Sub-loop (`loop:`) | Reusing an existing, well-tested loop as a pipeline stage |
| Inline states | Custom logic that doesn't map cleanly to any existing loop |

For full sub-loop schema details — `context_passthrough`, verdict handling, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md#6-sub-loop-composition) and [`skills/create-loop/reference.md`](../../skills/create-loop/reference.md).

### Visualizing Sub-Loop Execution

When `--show-diagrams` is active and a state invokes a child loop, both FSM diagrams are rendered after each child step:

```
== loop: my-loop ====...
[parent diagram — parent state highlighted]
── sub-loop: fix-quality-and-tests ──
[child diagram — current child state highlighted]
```

The parent state remains highlighted throughout child execution so you can track where you are in the outer pipeline. Sub-loop diagram display supports arbitrary nesting depth — each active sub-loop is shown below its parent with a separator, from depth-1 children down to depth-N grandchildren.

---

## Loop Discovery: category and labels

Every loop YAML can declare a `category` string and a `labels` list for filtering with `ll-loop list`:

```yaml
name: fix-quality-and-tests
category: code-quality
labels: [quality, lint, tests]
```

`ll-loop list` groups output by `category`. Loops without a category appear under `uncategorized`. Filter at the command line with:

```bash
ll-loop list --category code-quality          # loops in the code-quality category
ll-loop list --label tests                    # loops carrying the "tests" label
ll-loop list --builtin --category evaluation  # built-in evaluation loops only
```

`--label` can be repeated for an OR match: `--label tests --label lint` returns loops with either tag.

| Field | Type | Description |
|-------|------|-------------|
| `category` | `string` | Grouping label shown as a header in `ll-loop list` output |
| `labels` | `array[string]` | Arbitrary tags for finer-grained filtering |

Both fields are optional and have no effect on loop execution.

---

## Reusable State Fragments

A **fragment** is a named partial state definition stored in a library file. Any loop can import a library and reference a fragment by name — the fragment's fields are merged into the state at parse time, with state-level fields taking precedence. Fragments eliminate copy-pasted state structure (the same `action_type` + `evaluate` combination duplicated across states) without the overhead of a separate execution context.

### Defining a Fragment Library

Create a YAML file with a top-level `fragments:` dict. Each key is a fragment name; the value is a partial state dict:

```yaml
# .loops/lib/common.yaml
fragments:
  shell_exit:
    action_type: shell
    evaluate:
      type: exit_code
```

### Importing and Using Fragments

Add `import:` at the loop root with the library path (relative to the loop file's directory), then reference a fragment with `fragment: <name>` in any state:

```yaml
import:
  - lib/common.yaml

states:
  check_tests:
    fragment: shell_exit    # inherits action_type: shell + evaluate.type: exit_code
    action: "pytest"
    timeout: 600
    on_yes: done
    on_no: fix_tests
```

State-level fields override fragment fields at every nesting level, including nested objects. To change only one sub-field of `evaluate`, supply just that sub-field — the rest carry over from the fragment:

```yaml
states:
  check_count:
    fragment: retry_counter       # provides action_type, action script, evaluate.type/operator
    evaluate:
      target: 5                   # override only the target; type/operator from fragment
    on_yes: keep_going
    on_no: give_up
```

### Inline Fragments

Define fragments directly in the loop file without an `import:` line:

```yaml
fragments:
  my_gate:
    action_type: shell
    evaluate:
      type: exit_code

states:
  lint:
    fragment: my_gate
    action: "ruff check ."
    on_yes: done
    on_no: fix
```

Local `fragments:` definitions override any imported fragment with the same name.

### Built-in Libraries

Two libraries ship with little-loops, both in `scripts/little_loops/loops/lib/`:

#### `lib/common.yaml` — type-pattern fragments

Generic structure fragments (action_type + evaluate combinator) used by all built-in loops:

| Fragment | Provides | Caller must supply |
|----------|----------|--------------------|
| `shell_exit` | `action_type: shell` + `evaluate.type: exit_code` | `action`, routing (`on_yes`, `on_no`) |
| `retry_counter` | Shell counter script + `output_numeric` evaluator against `${context.max_retries}` | `context.counter_key`, `context.max_retries`, routing |
| `llm_gate` | `action_type: prompt` + `evaluate.type: llm_structured` | `action`, `evaluate.prompt`, routing (`on_yes`, `on_no`) |
| `numeric_gate` | `action_type: shell` + `evaluate.type: output_numeric` | `action`, `evaluate.operator`, `evaluate.target`, routing (`on_yes`, `on_no`) |

#### `lib/cli.yaml` — ll- CLI tool fragments

Tool-specific fragments with pre-filled `action` fields for every major ll- CLI tool. Import with `lib/cli.yaml`; override `action` to add flags:

```yaml
import:
  - lib/cli.yaml

states:
  check_links:
    fragment: ll_check_links     # provides action_type, action, evaluate
    capture: link_results
    on_yes: done
    on_no: fix_links

  run_auto:
    fragment: ll_auto
    action: "ll-auto --priority P1,P2 --quiet"   # override action to add flags
    on_yes: done
    on_no: retry
```

| Fragment | Default `action` | Notes |
|----------|-----------------|-------|
| `ll_auto` | `ll-auto` | Override `action` to add `--priority`, `--quiet`, etc. |
| `ll_issues_list` | `ll-issues list --json` | |
| `ll_issues_next` | `ll-issues next-action` | Override `action` to add `--skip "..."` |
| `ll_issues_next_issue` | `ll-issues next-issue` | |
| `ll_history_summary` | `ll-history summary` | Override `action` to add `2>/dev/null` fallback |
| `ll_check_links` | `ll-check-links 2>&1` | |
| `ll_messages` | `ll-messages --stdout` | Override `action` to add `--skill`, `--examples-format`, etc. |
| `ll_deps` | `ll-deps check` | |
| `ll_sprint_list` | `ll-sprint list` | |
| `ll_parallel` | `ll-parallel` | |
| `ll_workflows` | `ll-workflows` | |
| `ll_loop_run` | `ll-loop run ${context.loop_name}` | Requires `context.loop_name` |

All `lib/cli.yaml` fragments use `action_type: shell` + `evaluate.type: exit_code`.

Built-in loops import the libraries as `import: ["lib/common.yaml"]` or `import: ["lib/cli.yaml"]`. User loops in `.loops/` can do the same if they copy or symlink the library, or define their own.

### When to Use Fragments vs. Sub-Loops

| Approach | Best for |
|----------|----------|
| Fragment (`fragment:`) | Sharing a state *structure* (action_type + evaluate) across many states in one or more loops |
| Sub-loop (`loop:`) | Reusing a complete, well-tested loop as a pipeline stage with its own execution context |
| Inline states | Custom logic that doesn't map to any reuse pattern |

Fragment resolution is parse-time only — the engine never sees `fragment:` keys and there is no runtime overhead.

---

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
- `/ll:rename-loop` — Rename a loop (built-in or project-level) and update all references in other YAMLs, tests, and docs
- `ll-loop --help` — Full CLI reference for all loop subcommands
