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

## Tips

- **Start with low `max_iterations`** while developing a loop (5-10). Increase once it works.
- **Use `ll-loop test <name>`** for single-iteration verification — runs one cycle and stops.
- **Use `ll-loop simulate <name>`** for interactive dry-run — traces execution without running actions.
- **Set `on_handoff: spawn`** for long-running loops that might exhaust Claude's context window.
- **Use `action_type: prompt`** when your fix action is a natural-language instruction rather than a CLI command.
- **Use `backoff: <seconds>`** in imperative loops to add delay between iterations.

## Further Reading

- [FSM Loop System Design](generalized-fsm-loop.md) — Internal FSM architecture, schema, evaluators, variable interpolation, and compiler details
- [Configuration Reference](CONFIGURATION.md) — The `loops` section covers loop-related config options
- `/ll:create-loop` — Interactive loop creation wizard
- `ll-loop --help` — Full CLI reference for all loop subcommands
