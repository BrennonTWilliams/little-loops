# Paradigm-Specific Questions (Step 2)

Based on the selected paradigm, ask follow-up questions.

---

## Goal Paradigm Questions

If user selected "Fix errors until clean":

**Question Set 1** (single AskUserQuestion call):

```yaml
questions:
  - question: "What should the loop check and fix?"
    header: "Check target"
    multiSelect: true
    options:
      - label: "Type errors (mypy)"
        description: "Check: mypy src/, Fix: auto-fix type issues"
      - label: "Lint errors (ruff)"
        description: "Check: ruff check src/, Fix: ruff check --fix"
      - label: "Test failures (pytest)"
        description: "Check: pytest, Fix: fix failing tests"
      - label: "Custom check"
        description: "Specify your own check and fix commands"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "10 (Recommended)"
        description: "Good for most fixes"
      - label: "20"
        description: "For more complex issues"
      - label: "50"
        description: "For large codebases"

> **Note**: The runtime default is 50 for all paradigms. These options are suggested starting points to explicitly specify in your YAML based on your use case.
```

**If "Custom check" was selected**, ask for the commands:
- "What command checks for errors?" (free text via Other)
- "What command fixes the errors?" (free text via Other)

**Tool Evaluator Defaults:**

> **Note**: This table provides guidance for the AI during the interactive wizard flow. There is no separate code-based automatic tool detection - the AI uses this table to customize question wording based on the check command you provide. You should select the appropriate evaluator type for your specific tools.

When a check command is determined (from presets or custom input), use this table to recommend the appropriate evaluator:

| Tool Pattern | Recommended Evaluator | Rationale |
|--------------|----------------------|-----------|
| `pytest` | exit_code | Well-behaved: 0=all pass, 1=failures, 2+=errors |
| `mypy` | exit_code | Well-behaved: 0=no errors, 1=type errors |
| `ruff check` | exit_code | Well-behaved: 0=clean, 1=violations |
| `ruff format --check` | exit_code | Well-behaved: 0=formatted, 1=needs formatting |
| `npm test` | exit_code | Standard npm behavior |
| `npx tsc` | exit_code | Well-behaved: 0=no errors |
| `npx eslint` | exit_code | Well-behaved: 0=clean, 1=violations |
| `cargo test` | exit_code | Well-behaved: 0=all pass |
| `go test` | exit_code | Well-behaved: 0=all pass |

**Detection Instructions:** (for the AI executing this wizard)

> These instructions guide the AI's behavior during the wizard flow to customize questions based on the detected tool pattern.

1. After the check command is determined, match against the tool patterns above (case-insensitive, partial match)
2. If a match is found, customize the evaluator question to show the matched tool's recommendation
3. Modify the first option label: "Exit code (Recommended for {tool})" where {tool} is the matched pattern
4. Update the description to include the rationale from the table
5. For custom commands with no pattern match, use the generic "Exit code (Recommended)"

**Evaluator Selection** (ask after check command is determined):

Use the Tool Evaluator Defaults table to customize this question based on the detected tool.

```yaml
# Example with mypy detected:
questions:
  - question: "How should success be determined for the mypy check?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for mypy)"
        description: "Well-behaved: 0=no errors, 1=type errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"

# Generic template (no tool match):
questions:
  - question: "How should success be determined for the check command?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended)"
        description: "Success if command exits with code 0"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

**If "Output contains pattern" was selected**, ask:
```yaml
questions:
  - question: "What pattern indicates success?"
    header: "Pattern"
    multiSelect: false
    options:
      - label: "Success"
        description: "Match the word 'Success' in output"
      - label: "0 errors"
        description: "Match '0 errors' in output"
      - label: "no issues found"
        description: "Match 'no issues found' in output"
      - label: "Custom pattern"
        description: "Specify your own pattern (via Other)"
```

**If "Output is numeric" was selected**, ask:
```yaml
questions:
  - question: "What numeric condition indicates success?"
    header: "Condition"
    multiSelect: false
    options:
      - label: "Equals 0"
        description: "Success if output equals 0"
      - label: "Less than threshold"
        description: "Success if output is below a value"
      - label: "Greater than threshold"
        description: "Success if output is above a value"
```

If "Less than threshold" or "Greater than threshold" selected, ask for target value via Other.

**Evaluator type mapping:**
- "Exit code" → `type: exit_code` (or omit, as this is the default)
- "Output contains pattern" → `type: output_contains, pattern: "<pattern>"`
- "Output is numeric" + "Equals 0" → `type: output_numeric, operator: eq, target: 0`
- "Output is numeric" + "Less than threshold" → `type: output_numeric, operator: lt, target: <value>`
- "Output is numeric" + "Greater than threshold" → `type: output_numeric, operator: gt, target: <value>`
- "AI interpretation" → `type: llm_structured`

**Generate Goal YAML:**

```yaml
paradigm: goal
name: "<loop-name>"
goal: "<description of what passes>"
tools:
  - "<check-command>"      # First tool is the check
  - "<fix-command>"        # Second tool is the fix
max_iterations: <selected-max>
# Include evaluator only if not using default (exit_code):
evaluator:                 # Optional - omit for exit_code default
  type: "<output_contains|output_numeric|llm_structured>"
  pattern: "<pattern>"     # For output_contains only
  operator: "<eq|lt|gt>"   # For output_numeric only
  target: <number>         # For output_numeric only
# Include action_type only if not using default heuristic:
action_type: "prompt|slash_command|shell"  # Optional - defaults to heuristic (/ = slash_command)
```

**Example for "Type errors + Lint errors":**

```yaml
paradigm: goal
name: "fix-types-and-lint"
goal: "Type and lint checks pass"
tools:
  - "mypy src/ && ruff check src/"
  - "/ll:check-code fix"
max_iterations: 10
```

---

## Invariants Paradigm Questions

If user selected "Maintain code quality continuously":

**Question Set 1:**

```yaml
questions:
  - question: "What constraints should always be true?"
    header: "Constraints"
    multiSelect: true
    options:
      - label: "Tests pass (pytest)"
        description: "Check: pytest, Fix: /ll:manage-issue bug fix"
      - label: "Types valid (mypy)"
        description: "Check: mypy src/, Fix: /ll:manage-issue bug fix"
      - label: "Lint clean (ruff)"
        description: "Check: ruff check src/, Fix: ruff check --fix src/"
      - label: "Build succeeds"
        description: "Check: npm run build (or equivalent)"
      - label: "Custom constraint"
        description: "Define your own check/fix pair"

  - question: "Should the loop restart after all constraints pass?"
    header: "Maintain mode"
    multiSelect: false
    options:
      - label: "No - stop when all pass"
        description: "Loop terminates when all constraints are satisfied"
      - label: "Yes - continuously maintain"
        description: "Restart from first constraint after all pass (daemon mode)"
```

**For each selected constraint, gather check/fix if custom. Otherwise use defaults:**

| Constraint | Check | Fix |
|------------|-------|-----|
| Tests pass | `pytest` | `/ll:manage-issue bug fix` |
| Types valid | `mypy src/` | `/ll:manage-issue bug fix` |
| Lint clean | `ruff check src/` | `ruff check --fix src/` |
| Build succeeds | Ask for build command | Ask for fix command |

**Evaluator Selection** (ask for each constraint if user wants custom evaluation):

Use the Tool Evaluator Defaults table (from Goal paradigm section) to customize the evaluator question based on each constraint's check command. For example, if the constraint uses `pytest`, show "Exit code (Recommended for pytest)" with the rationale "Well-behaved: 0=all pass, 1=failures, 2+=errors".

```yaml
# Example with pytest constraint:
questions:
  - question: "How should success be determined for 'tests-pass' check?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for pytest)"
        description: "Well-behaved: 0=all pass, 1=failures, 2+=errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

Follow the same conditional flow as Goal paradigm for pattern/numeric follow-ups.

**Generate Invariants YAML:**

```yaml
paradigm: invariants
name: "<loop-name>"
constraints:
  - name: "<constraint-1-name>"
    check: "<check-command>"
    fix: "<fix-command>"
    # Include evaluator only if not using default (exit_code):
    evaluator:               # Optional per-constraint
      type: "<output_contains|output_numeric|llm_structured>"
      pattern: "<pattern>"   # For output_contains only
      operator: "<eq|lt|gt>" # For output_numeric only
      target: <number>       # For output_numeric only
    # Include action_type only if not using default heuristic:
    action_type: "prompt|slash_command|shell"  # Optional per-constraint
  - name: "<constraint-2-name>"
    check: "<check-command>"
    fix: "<fix-command>"
maintain: <true|false>
max_iterations: 50
```

**Example for "Tests + Types + Lint":**

```yaml
paradigm: invariants
name: "code-quality-guardian"
constraints:
  - name: "tests-pass"
    check: "pytest"
    fix: "/ll:manage-issue bug fix"
  - name: "types-valid"
    check: "mypy src/"
    fix: "/ll:manage-issue bug fix"
  - name: "lint-clean"
    check: "ruff check src/"
    fix: "ruff check --fix src/"
maintain: false
max_iterations: 50
```

---

## Convergence Paradigm Questions

If user selected "Drive a metric toward a target":

**Question Set 1:**

```yaml
questions:
  - question: "What type of metric do you want to track?"
    header: "Metric type"
    multiSelect: false
    options:
      - label: "Error count"
        description: "Count errors from a command (reduce toward 0)"
      - label: "Test coverage"
        description: "Coverage percentage (increase toward target)"
      - label: "Custom metric"
        description: "Any command that outputs a number"
```

**Based on metric type, gather details:**

For "Error count":
```yaml
questions:
  - question: "What errors should be counted?"
    header: "Error source"
    multiSelect: false
    options:
      - label: "Lint errors (ruff)"
        description: "Count: ruff check src/ --output-format=json | jq '.length'"
      - label: "Type errors (mypy)"
        description: "Count: mypy src/ --output-format=json | jq '.error_count'"
      - label: "Custom command"
        description: "Specify command that outputs a number"
```

**Question for fix action:**
```yaml
questions:
  - question: "What action should reduce the metric?"
    header: "Fix action"
    multiSelect: false
    options:
      - label: "/ll:check-code fix (Recommended)"
        description: "Auto-fix code issues"
      - label: "/ll:manage-issue bug fix"
        description: "Use issue management to fix bugs"
      - label: "Custom command"
        description: "Specify your own fix command"
```

**Generate Convergence YAML:**

```yaml
paradigm: convergence
name: "<loop-name>"
check: "<metric-command>"
toward: <target-value>
using: "<fix-action>"
tolerance: 0
# Include action_type only if not using default heuristic:
action_type: "prompt|slash_command|shell"  # Optional - for the using: action
max_iterations: 50
```

**Example for "Reduce lint errors to 0":**

```yaml
paradigm: convergence
name: "eliminate-lint-errors"
check: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
toward: 0
using: "/ll:check-code fix"
tolerance: 0
max_iterations: 50
```

---

## Imperative Paradigm Questions

If user selected "Run a sequence of steps":

**Question Set 1:**

```yaml
questions:
  - question: "What steps should run in sequence?"
    header: "Steps"
    multiSelect: true
    options:
      - label: "Check types (mypy)"
        description: "Run type checking"
      - label: "Check lint (ruff)"
        description: "Run linting"
      - label: "Run tests (pytest)"
        description: "Execute test suite"
      - label: "Fix issues"
        description: "Apply automatic fixes"
      - label: "Custom step"
        description: "Add your own command"

  - question: "When should the loop stop?"
    header: "Exit condition"
    multiSelect: false
    options:
      - label: "All checks pass"
        description: "Stop when mypy && ruff && pytest all succeed"
      - label: "Tests pass"
        description: "Stop when pytest succeeds"
      - label: "Custom condition"
        description: "Specify your own exit check"
```

**Evaluator Selection** (ask for the exit condition check):

Use the Tool Evaluator Defaults table (from Goal paradigm section) to customize the evaluator question based on the exit condition check command. For compound commands (e.g., "mypy && ruff && pytest"), show "Exit code (Recommended)" since multiple tools are being combined.

```yaml
# Example with "Tests pass" exit condition (pytest):
questions:
  - question: "How should success be determined for the exit condition?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for pytest)"
        description: "Well-behaved: 0=all pass, 1=failures, 2+=errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

Follow the same conditional flow as Goal paradigm for pattern/numeric follow-ups.

**Generate Imperative YAML:**

```yaml
paradigm: imperative
name: "<loop-name>"
steps:
  - "<step-1>"
  - "<step-2>"
  - "<step-3>"
until:
  check: "<exit-condition-command>"
  # Include evaluator only if not using default (exit_code):
  evaluator:                 # Optional for exit condition
    type: "<output_contains|output_numeric|llm_structured>"
    pattern: "<pattern>"     # For output_contains only
    operator: "<eq|lt|gt>"   # For output_numeric only
    target: <number>         # For output_numeric only
  # Include action_type only if not using default heuristic:
  action_type: "prompt|slash_command|shell"  # Optional for the until: check
max_iterations: 50  # Default if omitted
backoff: 2
```

**Example for "Fix -> Test -> Check until clean":**

```yaml
paradigm: imperative
name: "fix-test-check"
steps:
  - "/ll:check-code fix"
  - "pytest"
  - "mypy src/"
until:
  check: "mypy src/ && ruff check src/ && pytest"
max_iterations: 50  # Default if omitted
backoff: 2
```
