# FSM Compilation Reference & Quick Reference

## FSM Compilation Reference

Each paradigm compiles to a specific FSM structure. Use this reference when generating the FSM preview in Step 4.

> **Notation Legend:**
> - `->` (arrow) means "transitions to" (conceptual representation)
> - `on_success -> done` is equivalent to YAML: `on_success: done`
> - `route[target] -> done` represents a routing table entry: `route: { target: done }`
> - `[terminal]` marks a state that ends the loop
>
> **Two YAML syntaxes for routing:**
> 1. **Shorthand** (for standard success/failure/error verdicts):
>    ```yaml
>    on_success: "done"
>    on_failure: "fix"
>    ```
> 2. **Full routing table** (for custom verdicts):
>    ```yaml
>    route:
>      target: "done"
>      progress: "apply"
>      _: "done"  # default
>    ```

### Goal Paradigm -> FSM
```
States: evaluate, fix, done
Initial: evaluate

Transitions:
  evaluate:
    - on_success -> done
    - on_failure -> fix
    - on_error -> fix
  fix:
    - next -> evaluate
  done: [terminal]
```

### Convergence Paradigm -> FSM
```
States: measure, apply, done
Initial: measure

Transitions:
  measure:
    - route[target] -> done
    - route[progress] -> apply
    - route[stall] -> done
  apply:
    - next -> measure
  done: [terminal]
```

### Invariants Paradigm -> FSM
For each constraint `{name}` in order:
```
States: check_{name1}, fix_{name1}, check_{name2}, fix_{name2}, ..., all_valid
Initial: check_{first_constraint}

Transitions:
  check_{name}:
    - on_success -> check_{next} (or all_valid if last)
    - on_failure -> fix_{name}
  fix_{name}:
    - next -> check_{name}
  all_valid: [terminal]
    - on_maintain -> check_{first} (if maintain: true)
```

### Imperative Paradigm -> FSM
For each step in order:
```
States: step_0, step_1, ..., step_N, check_done, done
Initial: step_0

Transitions:
  step_N:
    - next -> step_{N+1} (or check_done if last)
  check_done:
    - on_success -> done
    - on_failure -> step_0
  done: [terminal]
```

---

## FSM Preview Examples

**Example previews by paradigm:**

Goal paradigm (with output_contains evaluator):
```
## Compiled FSM Preview
States: evaluate -> fix -> done
Transitions:
  evaluate: success->done, failure->fix, error->fix
  fix: next->evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: output_contains [pattern: "0 errors"]
```

Goal paradigm (default exit_code):
```
## Compiled FSM Preview
States: evaluate -> fix -> done
Transitions:
  evaluate: success->done, failure->fix, error->fix
  fix: next->evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: exit_code (default)
```

Convergence paradigm:
```
## Compiled FSM Preview
States: measure -> apply -> done
Transitions:
  measure: target->done, progress->apply, stall->done
  apply: next->measure
  done: [terminal]
Initial: measure
Max iterations: 50
Evaluator: convergence [toward: 0, tolerance: 0]
```

Invariants paradigm (with per-constraint evaluators):
```
## Compiled FSM Preview
States: check_tests -> fix_tests -> check_types -> fix_types -> check_lint -> fix_lint -> all_valid
Transitions:
  check_tests: success->check_types, failure->fix_tests
  fix_tests: next->check_tests
  check_types: success->check_lint, failure->fix_types
  fix_types: next->check_types
  check_lint: success->all_valid, failure->fix_lint
  fix_lint: next->check_lint
  all_valid: [terminal]
Initial: check_tests
Max iterations: 50
Evaluators:
  check_tests: exit_code (default)
  check_types: output_contains [pattern: "Success"]
  check_lint: exit_code (default)
```

Imperative paradigm (with 3 steps):
```
## Compiled FSM Preview
States: step_0 -> step_1 -> step_2 -> check_done -> done
Transitions:
  step_0: next->step_1
  step_1: next->step_2
  step_2: next->check_done
  check_done: success->done, failure->step_0
  done: [terminal]
Initial: step_0
Max iterations: 20
Evaluator: output_numeric [operator: eq, target: 0]
```

---

## Quick Reference

### Template Quick Reference

| Template | Paradigm | Best For |
|----------|----------|----------|
| Python quality | invariants | Python projects with ruff + mypy |
| JavaScript quality | invariants | JS/TS projects with eslint + tsc |
| Tests until passing | goal | Any project with test suite |
| Full quality gate | invariants | CI-like multi-check validation |

**When to use templates:**
- You want a working loop quickly
- Your use case matches a common pattern
- You're new to loop creation

**When to build custom:**
- You have unique check/fix commands
- You need convergence (metric-based) loops
- You need imperative (step sequence) loops

### Paradigm Decision Tree

```
What are you trying to do?
|
|- Fix a specific problem -> Goal paradigm
|   "Run check, if fails run fix, repeat until passes"
|
|- Maintain multiple standards -> Invariants paradigm
|   "Check A, fix A if needed, check B, fix B if needed, ..."
|
|- Reduce/increase a metric -> Convergence paradigm
|   "Measure value, if not at target, apply fix, measure again"
|
'- Run ordered steps -> Imperative paradigm
    "Do step 1, do step 2, check if done, repeat if not"
```

### Common Configurations

**Quick lint fix:**
```yaml
paradigm: goal
name: "quick-lint-fix"
goal: "Lint passes"
tools:
  - "ruff check src/"
  - "ruff check --fix src/"
max_iterations: 5
```

**Full quality gate:**
```yaml
paradigm: invariants
name: "full-quality-gate"
constraints:
  - name: "types"
    check: "mypy src/"
    fix: "/ll:manage_issue bug fix"
  - name: "lint"
    check: "ruff check src/"
    fix: "ruff check --fix src/"
  - name: "tests"
    check: "pytest"
    fix: "/ll:manage_issue bug fix"
maintain: false
max_iterations: 30
```

**Coverage improvement:**
```yaml
paradigm: convergence
name: "improve-coverage"
check: "pytest --cov=src --cov-report=term | grep TOTAL | awk '{print $4}' | tr -d '%'"
toward: 80
using: "/ll:manage_issue feature implement"
tolerance: 1
max_iterations: 20
```

### Advanced State Configuration

#### action_type (Optional)

The `action_type` field explicitly controls how an action is executed. In most cases, you can omit this field and the default heuristic works correctly.

**Values:**
- `prompt` - Execute action as a Claude prompt via Claude CLI
- `slash_command` - Execute action as a Claude slash command via Claude CLI
- `shell` - Execute action as a bash shell command
- (omit) - Uses heuristic: actions starting with `/` are slash commands, others are shell commands

**When to use:**
- **Plain prompts**: You want to send a plain prompt to Claude (not a slash command) that doesn't start with `/`
- **Explicit shell commands**: You have a command starting with `/` that should run in shell (not via Claude CLI)
- **Clarity**: You want to explicitly document the execution type in the YAML

**Example - Plain prompt (no leading `/`):**
```yaml
paradigm: goal
name: "fix-with-plain-prompt"
goal: "Code is clean"
tools:
  - "ruff check src/"
  - "Please fix all lint errors in the src/ directory"
action_type: "prompt"  # Explicitly mark as prompt since it doesn't start with /
max_iterations: 10
```

**Example - Shell command starting with `/`:**
```yaml
paradigm: goal
name: "run-specific-script"
goal: "Script succeeds"
tools:
  - "/usr/local/bin/check.sh"
  - "/usr/local/bin/fix.sh"
action_type: "shell"  # Run via shell, not Claude CLI, despite leading /
max_iterations: 5
```

**Most users can omit this field** - the default heuristic covers the common case where slash commands start with `/` and shell commands don't.

#### on_handoff (Optional)

The `on_handoff` field configures loop behavior when context handoff signals are detected during execution. Context handoff occurs when a slash command needs more context than available in the current session.

**Values:**
- `pause` (default) - Pause loop execution when handoff detected, requiring manual resume
- `spawn` - Automatically spawn a new continuation session to continue loop execution
- `terminate` - Terminate the loop when handoff detected

**When to use:**
- **pause** (default): For loops where you want manual control before continuing after a context handoff
- **spawn**: For automated loops that should continue seamlessly across context boundaries (e.g., long-running quality gates)
- **terminate**: For loops where context handoff indicates an unrecoverable state

**Example - Spawn continuation sessions:**
```yaml
paradigm: goal
name: "automated-quality-fix"
goal: "All quality checks pass"
tools:
  - "pytest && mypy src/ && ruff check src/"
  - "/ll:manage_issue bug fix"
max_iterations: 20
on_handoff: "spawn"  # Automatically continue in new session if context runs out
```

**Example - Terminate on handoff:**
```yaml
paradigm: invariants
name: "quick-check-guardian"
constraints:
  - name: "types"
    check: "mypy src/"
    fix: "/ll:manage_issue bug fix"
maintain: false
max_iterations: 10
on_handoff: "terminate"  # Stop if we run out of context
```

**Most users can omit this field** - the default `pause` behavior is appropriate for most interactive use cases.
