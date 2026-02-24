# Loops Guide

## What Is a Loop?

A loop is a YAML-defined automation workflow that runs commands, evaluates results, and decides what to do next — without you prompting each step. Under the hood, each loop is a **Finite State Machine (FSM)**: a set of states connected by transitions, with a clear start and end.

Why does this matter? LLMs are stateless — they don't remember what happened two prompts ago. The FSM gives them persistent memory of what was tried, what worked, and when to stop.

```
You write:    paradigm YAML (5-10 lines)
System makes: FSM states + transitions (compiled automatically)
You run:      ll-loop run <name>
```

## How Loops Work

Loops live in `.loops/` as YAML files. Each loop has:

- **States** — units of work (run a check, apply a fix, etc.)
- **Transitions** — edges between states (on success go here, on failure go there)
- **A paradigm** — a high-level pattern that compiles to states and transitions automatically

When a loop runs, the engine:

1. Enters the **initial state** and runs its action
2. Evaluates the result (exit code, output pattern, metric, etc.)
3. Follows the matching **transition** to the next state
4. Repeats until reaching a **terminal state** or hitting `max_iterations`

You don't write FSM states by hand (unless you want to). Instead, pick a **paradigm** — a mental model that matches your problem — and let the compiler generate the FSM.

## The 4 Paradigms

### Goal — "Fix until clean"

Use when you have a single condition to check and a single action to fix it.

**Example** — fix type errors until `mypy` passes:

```yaml
paradigm: goal
name: fix-types
goal: "No type errors"
tools:
  - "mypy src/"
  - "/ll:check-code fix"
max_iterations: 10
```

This compiles to three states: `evaluate` runs the check, `fix` runs the fix action, and `done` is the terminal state. If the check passes, the loop is done. If it fails, the fix runs and the check repeats.

```
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──▶│ done │
  └──────────┘             └──────┘
       │ ▲
  fail │ │ next
       ▼ │
     ┌─────┐
     │ fix │
     └─────┘
```

### Convergence — "Drive a metric toward a target"

Use when you have a measurable value to optimize — an error count to reduce, a coverage percentage to increase.

**Example** — reduce lint errors to zero:

```yaml
paradigm: convergence
name: reduce-lint-errors
check: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
toward: 0
using: "/ll:check-code fix"
tolerance: 0
max_iterations: 50
```

This compiles to three states: `measure` runs the metric command, `apply` runs the fix action, and `done` is the terminal. The evaluator produces one of three verdicts: **target** (metric reached the goal), **progress** (metric improved, keep going), or **stall** (no improvement, stop).

```
  ┌─────────┐              ┌──────┐
  │ measure │───target────▶│ done │
  └─────────┘              └──────┘
       │ ▲
progress │ next
       ▼ │
    ┌───────┐
    │ apply │
    └───────┘
       stall ─────────────▶ done
```

### Invariants — "Maintain multiple quality gates"

Use when multiple independent conditions must all be true — lint, types, formatting, tests.

**Example** — the built-in `quality-gate` loop:

```yaml
paradigm: invariants
name: quality-gate
constraints:
  - name: "lint"
    check: "/ll:check-code lint"
    fix: "Auto-fix lint issues"
  - name: "types"
    check: "/ll:check-code types"
    fix: "Fix type errors"
  - name: "format"
    check: "/ll:check-code format"
    fix: "Auto-format code"
  - name: "tests"
    check: "/ll:run-tests"
    fix: "Fix failing tests"
maintain: false
max_iterations: 15
```

This compiles to a chain of check/fix pairs followed by a terminal `all_valid` state. Each constraint is checked in order. If a check fails, its fix runs and the check repeats. When it passes, the next constraint is checked.

```
  ┌────────────┐             ┌─────────────┐             ┌──────────────┐             ┌─────────────┐             ┌───────────┐
  │ check_lint │───success──▶│ check_types │───success──▶│ check_format │───success──▶│ check_tests │───success──▶│ all_valid │
  └────────────┘             └─────────────┘             └──────────────┘             └─────────────┘             └───────────┘
        │ ▲                        │ ▲                          │ ▲                          │ ▲
   fail │ │ next              fail │ │ next                fail │ │ next                fail │ │ next
        ▼ │                        ▼ │                          ▼ │                          ▼ │
   ┌──────────┐               ┌───────────┐               ┌────────────┐               ┌───────────┐
   │ fix_lint │               │ fix_types │               │ fix_format │               │ fix_tests │
   └──────────┘               └───────────┘               └────────────┘               └───────────┘
```

Set `maintain: true` to restart from the first constraint after all pass (daemon mode).

### Imperative — "Run ordered steps, repeat until done"

Use when you have a specific sequence of steps plus an exit condition.

**Example** — the built-in `codebase-scan` loop:

```yaml
paradigm: imperative
name: codebase-scan
steps:
  - "/ll:scan-codebase"
  - "/ll:verify-issues"
  - "/ll:prioritize-issues"
until:
  check: "git status --porcelain"
  condition: "output_empty"
max_iterations: 5
```

This compiles to a linear chain of step states, a `check_done` state that evaluates the exit condition, and a `done` terminal. If the exit condition fails, execution loops back to `step_0`.

```
  ┌────────┐          ┌────────┐          ┌────────┐          ┌────────────┐             ┌──────┐
  │ step_0 │───next──▶│ step_1 │───next──▶│ step_2 │───next──▶│ check_done │───success──▶│ done │
  └────────┘          └────────┘          └────────┘          └────────────┘             └──────┘
       ▲                                                             │
       └─────────────────────────── fail ────────────────────────────┘
```

## Choosing a Paradigm

```
What are you trying to do?
│
├─ Fix a specific problem ──────────▶ Goal
│   "Run check, if fails run fix, repeat"
│
├─ Maintain multiple standards ─────▶ Invariants
│   "Check A, fix A, check B, fix B, ..."
│
├─ Reduce/increase a metric ────────▶ Convergence
│   "Measure, if not at target, fix, measure again"
│
└─ Run ordered steps ───────────────▶ Imperative
    "Do step 1, do step 2, check if done, repeat"
```

| Paradigm | States | Branching | Best for |
|-----------|--------|-----------|----------|
| Goal | 3 (evaluate, fix, done) | Binary (pass/fail) | Single check + fix |
| Convergence | 3 (measure, apply, done) | Three-way (target/progress/stall) | Metric optimization |
| Invariants | 2 per constraint + 1 | Binary per constraint | Multi-gate quality |
| Imperative | 1 per step + 2 | Binary exit check | Ordered workflows |

## Walkthrough: Creating and Running a Loop

Here's a complete example: creating a goal-paradigm loop to fix test failures.

### 1. Create

Run `/ll:create-loop`. The interactive wizard asks you to choose a paradigm, configure the check and fix commands, and set parameters. Or write the YAML directly:

```yaml
paradigm: goal
name: fix-tests
goal: "All tests pass"
tools:
  - "pytest tests/"
  - "Fix failing tests based on the pytest output"
max_iterations: 10
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
Paradigm: goal
Description: All tests pass
Max iterations: 10
Source: .loops/fix-tests.yaml

States:
  [evaluate] [INITIAL]
    action: pytest tests/
    on_success ──→ done
    on_failure ──→ fix
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

| Loop | Paradigm | Description |
|------|----------|-------------|
| `quality-gate` | invariants | Lint, types, format, and tests must all pass |
| `pre-pr-checks` | invariants | Code quality + tests before PR creation |
| `issue-verification` | invariants | Verify and normalize issue files |
| `history-reporting` | invariants | Generate issue history analysis reports |
| `codebase-scan` | imperative | Scan, verify, and prioritize issues |
| `issue-readiness-cycle` | imperative | Validate and process issues through readiness |
| `sprint-execution` | imperative | Execute a sprint with resume support |
| `workflow-analysis` | imperative | Extract and analyze workflow patterns |

## Beyond the Basics

The sections below cover features you'll encounter as you move past simple loops. For full technical details — schema definitions, compiler internals, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md).

### Evaluators

Evaluators interpret action output and produce a **verdict** string used for routing. Every state gets a default evaluator based on its action type.

| Evaluator | Verdicts | Default for | When to use |
|-----------|----------|-------------|-------------|
| `exit_code` | `success` / `failure` / `error` | shell commands | CLI tools that report pass/fail via exit code |
| `output_numeric` | `success` / `failure` / `error` | — | Compare parsed numeric output to a target |
| `output_json` | `success` / `failure` / `error` | — | Extract a JSON path value and compare |
| `output_contains` | `success` / `failure` | — | Regex or substring match on stdout |
| `convergence` | `target` / `progress` / `stall` | convergence paradigm | Track a metric toward a goal value |
| `llm_structured` | `success` / `failure` / `blocked` / `partial` | slash commands | Natural-language judgment via LLM |

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

The captured value is accessible as `${captured.lint_count.output}`, `${captured.lint_count.exit_code}`, and `${captured.lint_count.duration_ms}`.

### Routing

States use **shorthand** (`on_success`, `on_failure`) or a **route table** for verdict-to-state mapping:

```yaml
route:
  success: done
  failure: fix
  _: retry        # default for unmatched verdicts
  _error: error   # fallback for evaluation errors
```

Use `$current` as a target to retry the current state. Use `_` for a default route when no other verdict matches.

### Action Types

Each state's action is executed in one of three modes:

| Type | Syntax hint | Behavior |
|------|-------------|----------|
| `shell` | No `/` prefix | Run as shell command, capture stdout/stderr/exit code |
| `slash_command` | Starts with `/` | Execute a Claude Code slash command |
| `prompt` | Natural language | Send text to Claude as a prompt |

The engine auto-detects type: `/` prefix → `slash_command`, otherwise → `shell`. Set `action_type: prompt` explicitly for natural-language fix instructions.

### Handoff Behavior

When a loop detects that Claude's context window is approaching its limit, it triggers a **handoff**:

| Mode | `on_handoff:` value | Behavior |
|------|---------------------|----------|
| Pause | `pause` (default) | Save state to disk, resume later with `ll-loop resume` |
| Spawn | `spawn` | Save state and launch a fresh Claude session to continue |
| Terminate | `terminate` | Stop the loop immediately (state is not saved) |

### Scope-Based Concurrency

The `scope:` field declares which paths a loop operates on. The engine uses file-based locking to prevent two loops from modifying the same files simultaneously.

```yaml
scope:
  - "src/"
  - "tests/"
```

If a conflicting loop is already running, `ll-loop run` will error. Use `--queue` to wait for the conflict to resolve instead.

## CLI Quick Reference

### Subcommands

| Command | Description |
|---------|-------------|
| `ll-loop run <name>` | Run a loop (also: `ll-loop <name>`) |
| `ll-loop validate <name>` | Check YAML for schema errors and unreachable states |
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram |
| `ll-loop compile <file>` | Compile paradigm YAML to FSM YAML |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions |
| `ll-loop list` | List available loops (`--running` for active only) |
| `ll-loop status <name>` | Show current state and iteration count |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show execution history (`-n` for last N events) |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |

### Run Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Show execution plan without running actions |
| `--no-llm` | Disable LLM-based evaluation (use deterministic evaluators only) |
| `--llm-model <model>` | Override the LLM model for evaluation |
| `-n <N>` | Override `max_iterations` |
| `--queue` | Wait for conflicting scoped loops instead of erroring |
| `-q` / `--quiet` | Suppress progress output |

### Simulate Scenarios

The `simulate` command accepts `--scenario` to auto-select verdicts instead of prompting:

| Scenario | Behavior |
|----------|----------|
| `all-pass` | Every evaluation returns success/target |
| `all-fail` | Every evaluation returns failure/stall |
| `first-fail` | First evaluation fails, rest succeed |
| `alternating` | Alternates between success and failure |

## Tips

- **Start with low `max_iterations`** (5-10) while developing a loop. Increase once the logic is proven.
- **Use `backoff:`** to add delay between iterations — useful for rate-limited APIs or CI systems.
- **State is persisted to disk** after every transition. If a loop is interrupted, `ll-loop resume` picks up where it left off.
- **Convergence loops** use `direction:` to control whether the metric should go down (`minimize`, default) or up (`maximize`).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Loop stuck in a cycle | Fix action isn't changing the result the evaluator sees | Check `ll-loop history` — if the same verdict repeats, adjust the fix action |
| Scope conflict error | Another loop holds a lock on overlapping paths | Find it with `ll-loop list --running` and stop it, or use `--queue` to wait |
| LLM evaluator errors | Missing API key or network issue | Set `ANTHROPIC_API_KEY`, or use `--no-llm` to fall back to deterministic evaluators |
| "No state found" on resume | Loop already completed or was never started | Check `ll-loop status` — completed loops have no resumable state |

## Further Reading

- [FSM Loop System Design](../generalized-fsm-loop.md) — Internal FSM architecture, schema, evaluators, variable interpolation, and compiler details
- [Configuration Reference](../reference/CONFIGURATION.md) — Project-wide settings (test commands, paths, etc.) used by loop actions
- `/ll:create-loop` — Interactive loop creation wizard
- `ll-loop --help` — Full CLI reference for all loop subcommands
