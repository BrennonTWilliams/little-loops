---
description: Create a new FSM loop configuration interactively. Guides users through paradigm selection, parameter gathering, YAML generation, and validation.
allowed-tools:
  - Bash(mkdir:*, test:*, ll-loop:*)
---

# Create Loop

Interactive command for creating new automation loop configurations. This command guides you through:
1. Choosing a paradigm (type of automation)
2. Gathering paradigm-specific parameters
3. Naming the loop
4. Generating and previewing YAML
5. Saving and validating
6. Optional test iteration to verify the loop works

## Allowed Tools

Use these tools during the workflow:
- `AskUserQuestion` - For interactive prompts
- `Write` - To save the loop configuration
- `Bash` - To run validation and create directories
- `Read` - To check for existing loops

## Workflow

### Step 0: Creation Mode

Use AskUserQuestion to determine whether to use a template or build from scratch:

```yaml
questions:
  - question: "How would you like to create your loop?"
    header: "Creation mode"
    multiSelect: false
    options:
      - label: "Start from template (Recommended)"
        description: "Choose a pre-built loop for common tasks"
      - label: "Build from paradigm"
        description: "Configure a new loop from scratch"
```

**If "Start from template"**: Continue to Step 0.1 (Template Selection)
**If "Build from paradigm"**: Skip to Step 1 (Paradigm Selection) - existing flow

---

### Step 0.1: Template Selection

If "Start from template" was selected:

```yaml
questions:
  - question: "Which template would you like to use?"
    header: "Template"
    multiSelect: false
    options:
      - label: "Python quality (lint + types + format)"
        description: "ruff check/fix + mypy + ruff format until clean"
      - label: "JavaScript quality (lint + types)"
        description: "eslint + tsc until clean"
      - label: "Run tests until passing"
        description: "pytest/jest with auto-fix until green"
      - label: "Full quality gate (tests + types + lint)"
        description: "All checks must pass before completing"
```

---

#### Template Definitions

##### Template: python-quality

```yaml
paradigm: invariants
name: "python-quality"
constraints:
  - name: "lint"
    check: "ruff check {{src_dir}}"
    fix: "ruff check --fix {{src_dir}}"
  - name: "types"
    check: "mypy {{src_dir}}"
    fix: "echo 'Fix type errors manually or use /ll:manage_issue bug fix'"
  - name: "format"
    check: "ruff format --check {{src_dir}}"
    fix: "ruff format {{src_dir}}"
maintain: false
max_iterations: {{max_iterations}}
```

##### Template: javascript-quality

```yaml
paradigm: invariants
name: "javascript-quality"
constraints:
  - name: "lint"
    check: "npx eslint {{src_dir}}"
    fix: "npx eslint --fix {{src_dir}}"
  - name: "types"
    check: "npx tsc --noEmit"
    fix: "echo 'Fix type errors manually'"
maintain: false
max_iterations: {{max_iterations}}
```

##### Template: tests-until-passing

```yaml
paradigm: goal
name: "tests-until-passing"
goal: "All tests pass"
tools:
  - "{{test_cmd}}"
  - "/ll:manage_issue bug fix"
max_iterations: {{max_iterations}}
```

**Test command by template context:**
- Python projects: `pytest`
- JavaScript projects: `npm test`
- Custom: Ask user for test command

##### Template: full-quality-gate

```yaml
paradigm: invariants
name: "full-quality-gate"
constraints:
  - name: "tests"
    check: "{{test_cmd}}"
    fix: "/ll:manage_issue bug fix"
  - name: "types"
    check: "{{type_cmd}}"
    fix: "/ll:manage_issue bug fix"
  - name: "lint"
    check: "{{lint_cmd}}"
    fix: "{{lint_fix_cmd}}"
maintain: false
max_iterations: {{max_iterations}}
```

**Command defaults for full-quality-gate:**

| Language | test_cmd | type_cmd | lint_cmd | lint_fix_cmd |
|----------|----------|----------|----------|--------------|
| Python | `pytest` | `mypy {{src_dir}}` | `ruff check {{src_dir}}` | `ruff check --fix {{src_dir}}` |
| JavaScript | `npm test` | `npx tsc --noEmit` | `npx eslint {{src_dir}}` | `npx eslint --fix {{src_dir}}` |

---

### Step 0.2: Template Customization

After template selection, ask for customization:

```yaml
questions:
  - question: "What source directory should the loop check?"
    header: "Source dir"
    multiSelect: false
    options:
      - label: "src/ (Recommended)"
        description: "Standard source directory"
      - label: "."
        description: "Project root"
      - label: "lib/"
        description: "Library directory"
      - label: "Custom path"
        description: "Specify your own directory"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick fixes only"
      - label: "50"
        description: "For complex issues"
```

**If "Custom path" selected for source dir**: Ask for path via Other option.

**Apply substitutions to selected template:**
- Replace `{{src_dir}}` with selected source directory
- Replace `{{max_iterations}}` with selected max iterations
- Replace `{{test_cmd}}`, `{{type_cmd}}`, `{{lint_cmd}}`, `{{lint_fix_cmd}}` with language-appropriate defaults

**Flow after template customization:**
- The generated YAML and auto-suggested loop name are ready
- Continue directly to Step 4 (Preview and Confirm) with the template-populated configuration
- Skip Step 1 (Paradigm Selection), Step 2 (Paradigm-Specific Questions), and Step 3 (Loop Name) since template provides all configuration

---

### Step 1: Paradigm Selection (Custom Mode Only)

If user selected "Build from paradigm" in Step 0, use this flow.

Use AskUserQuestion with a single-select to determine the loop type:

```yaml
questions:
  - question: "What kind of automation loop do you want to create?"
    header: "Loop type"
    multiSelect: false
    options:
      - label: "Fix errors until clean (Recommended)"
        description: "Run checks and fix issues until all pass. Best for: type errors, lint issues, test failures"
      - label: "Maintain code quality continuously"
        description: "Keep multiple constraints true, restart after all pass. Best for: CI-like quality gates"
      - label: "Drive a metric toward a target"
        description: "Measure a value and apply fixes until it reaches goal. Best for: reducing error counts, coverage"
      - label: "Run a sequence of steps"
        description: "Execute steps in order, repeat until condition met. Best for: multi-stage builds"
```

**Paradigm Mapping:**
- "Fix errors until clean" → `goal` paradigm
- "Maintain code quality continuously" → `invariants` paradigm
- "Drive a metric toward a target" → `convergence` paradigm
- "Run a sequence of steps" → `imperative` paradigm

### Step 2: Paradigm-Specific Questions

Based on the selected paradigm, ask follow-up questions.

---

#### Goal Paradigm Questions

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
```

**If "Custom check" was selected**, ask for the commands:
- "What command checks for errors?" (free text via Other)
- "What command fixes the errors?" (free text via Other)

**Tool Evaluator Defaults:**

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

**Detection Instructions:**
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
  - "/ll:check_code fix"
max_iterations: 10
```

---

#### Invariants Paradigm Questions

If user selected "Maintain code quality continuously":

**Question Set 1:**

```yaml
questions:
  - question: "What constraints should always be true?"
    header: "Constraints"
    multiSelect: true
    options:
      - label: "Tests pass (pytest)"
        description: "Check: pytest, Fix: /ll:manage_issue bug fix"
      - label: "Types valid (mypy)"
        description: "Check: mypy src/, Fix: /ll:manage_issue bug fix"
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
| Tests pass | `pytest` | `/ll:manage_issue bug fix` |
| Types valid | `mypy src/` | `/ll:manage_issue bug fix` |
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
    fix: "/ll:manage_issue bug fix"
  - name: "types-valid"
    check: "mypy src/"
    fix: "/ll:manage_issue bug fix"
  - name: "lint-clean"
    check: "ruff check src/"
    fix: "ruff check --fix src/"
maintain: false
max_iterations: 50
```

---

#### Convergence Paradigm Questions

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
      - label: "/ll:check_code fix (Recommended)"
        description: "Auto-fix code issues"
      - label: "/ll:manage_issue bug fix"
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
using: "/ll:check_code fix"
tolerance: 0
max_iterations: 50
```

---

#### Imperative Paradigm Questions

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
max_iterations: 20
backoff: 2
```

**Example for "Fix → Test → Check until clean":**

```yaml
paradigm: imperative
name: "fix-test-check"
steps:
  - "/ll:check_code fix"
  - "pytest"
  - "mypy src/"
until:
  check: "mypy src/ && ruff check src/ && pytest"
max_iterations: 20
backoff: 2
```

---

## FSM Compilation Reference

Each paradigm compiles to a specific FSM structure. Use this reference when generating the FSM preview in Step 4.

### Goal Paradigm → FSM
```
States: evaluate, fix, done
Initial: evaluate

Transitions:
  evaluate:
    - on_success → done
    - on_failure → fix
    - on_error → fix
  fix:
    - next → evaluate
  done: [terminal]
```

### Convergence Paradigm → FSM
```
States: measure, apply, done
Initial: measure

Transitions:
  measure:
    - route[target] → done
    - route[progress] → apply
    - route[stall] → done
  apply:
    - next → measure
  done: [terminal]
```

### Invariants Paradigm → FSM
For each constraint `{name}` in order:
```
States: check_{name1}, fix_{name1}, check_{name2}, fix_{name2}, ..., all_valid
Initial: check_{first_constraint}

Transitions:
  check_{name}:
    - on_success → check_{next} (or all_valid if last)
    - on_failure → fix_{name}
  fix_{name}:
    - next → check_{name}
  all_valid: [terminal]
    - on_maintain → check_{first} (if maintain: true)
```

### Imperative Paradigm → FSM
For each step in order:
```
States: step_0, step_1, ..., step_N, check_done, done
Initial: step_0

Transitions:
  step_N:
    - next → step_{N+1} (or check_done if last)
  check_done:
    - on_success → done
    - on_failure → step_0
  done: [terminal]
```

---

### Step 3: Loop Name

After gathering paradigm-specific parameters, ask for the loop name:

```yaml
questions:
  - question: "What should this loop be called?"
    header: "Loop name"
    multiSelect: false
    options:
      - label: "<auto-suggested-name>"
        description: "Based on your selections"
      - label: "Custom name"
        description: "Enter your own name"
```

**Auto-suggest names based on paradigm:**
- Goal: `fix-<targets>` (e.g., `fix-types-and-lint`)
- Invariants: `<constraint-names>-guardian` (e.g., `tests-types-lint-guardian`)
- Convergence: `reduce-<metric>` or `increase-<metric>` (e.g., `reduce-lint-errors`)
- Imperative: `<step-summary>-loop` (e.g., `fix-test-check-loop`)

### Step 4: Preview and Confirm

Generate and display both the paradigm YAML and the compiled FSM preview.

**Generate FSM Preview:**

Using the FSM Compilation Reference above, generate a preview showing:
1. States in execution order (use → between states)
2. Transitions for each non-terminal state
3. Terminal states marked with `[terminal]`
4. Initial state and max_iterations from the configuration

**Display format:**

```
Here's your loop configuration:

## Paradigm YAML
```yaml
<generated-yaml>
```

## Compiled FSM Preview
States: <state1> → <state2> → ... → <terminal>
Transitions:
  <state1>: <verdict>→<target>, <verdict>→<target>
  <state2>: next→<target>
  ...
  <terminal>: [terminal]
Initial: <initial-state>
Max iterations: <max_iterations>
Evaluator: <type> [<details>]  # Only shown if non-default evaluator configured

This will create: .loops/<name>.yaml
```

**Example previews by paradigm:**

Goal paradigm (with output_contains evaluator):
```
## Compiled FSM Preview
States: evaluate → fix → done
Transitions:
  evaluate: success→done, failure→fix, error→fix
  fix: next→evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: output_contains [pattern: "0 errors"]
```

Goal paradigm (default exit_code):
```
## Compiled FSM Preview
States: evaluate → fix → done
Transitions:
  evaluate: success→done, failure→fix, error→fix
  fix: next→evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: exit_code (default)
```

Convergence paradigm:
```
## Compiled FSM Preview
States: measure → apply → done
Transitions:
  measure: target→done, progress→apply, stall→done
  apply: next→measure
  done: [terminal]
Initial: measure
Max iterations: 50
Evaluator: convergence [toward: 0, tolerance: 0]
```

Invariants paradigm (with per-constraint evaluators):
```
## Compiled FSM Preview
States: check_tests → fix_tests → check_types → fix_types → check_lint → fix_lint → all_valid
Transitions:
  check_tests: success→check_types, failure→fix_tests
  fix_tests: next→check_tests
  check_types: success→check_lint, failure→fix_types
  fix_types: next→check_types
  check_lint: success→all_valid, failure→fix_lint
  fix_lint: next→check_lint
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
States: step_0 → step_1 → step_2 → check_done → done
Transitions:
  step_0: next→step_1
  step_1: next→step_2
  step_2: next→check_done
  check_done: success→done, failure→step_0
  done: [terminal]
Initial: step_0
Max iterations: 20
Evaluator: output_numeric [operator: eq, target: 0]
```

Use AskUserQuestion:
```yaml
questions:
  - question: "Save this loop configuration?"
    header: "Confirm"
    multiSelect: false
    options:
      - label: "Yes, save and validate"
        description: "Save to .loops/<name>.yaml and run validation"
      - label: "No, start over"
        description: "Discard and restart the wizard"
```

### Step 5: Save and Validate

If confirmed:

1. **Create directory if needed:**
   ```bash
   mkdir -p .loops
   ```

2. **Check for existing file:**
   ```bash
   test -f .loops/<name>.yaml && echo "EXISTS" || echo "OK"
   ```

   If exists, ask:
   ```yaml
   questions:
     - question: "A loop with this name already exists. Overwrite?"
       header: "Overwrite"
       multiSelect: false
       options:
         - label: "Yes, overwrite"
           description: "Replace the existing loop configuration"
         - label: "No, choose different name"
           description: "Go back and pick a new name"
   ```

3. **Write the file** using the Write tool:
   - Path: `.loops/<name>.yaml`
   - Content: The generated YAML

4. **Validate** using ll-loop CLI:
   ```bash
   ll-loop validate <name>
   ```

5. **Offer test iteration** (after validation succeeds):

   Use AskUserQuestion:
   ```yaml
   questions:
     - question: "Would you like to run a test iteration to verify the loop works?"
       header: "Test run"
       multiSelect: false
       options:
         - label: "Yes, run one iteration (Recommended)"
           description: "Execute check command and verify evaluation works"
         - label: "No, I'll test manually"
           description: "Skip test iteration"
   ```

   If "Yes, run one iteration":
   ```bash
   ll-loop test <name>
   ```

   Display the test output directly. The test command provides:
   - Check command and exit code
   - Output preview
   - Evaluator type and verdict
   - Would-transition target
   - Success indicator or warning with specific issues

   Continue to the success report regardless of test result.

6. **Report results:**

   On success (no test issues):
   ```
   Loop created successfully!

   File: .loops/<name>.yaml
   States: <list-of-states>
   Initial: <initial-state>
   Max iterations: <max>

   Run now with: ll-loop <name>
   ```

   On success with test issues (test ran but found problems):
   ```
   Loop created successfully!

   File: .loops/<name>.yaml
   States: <list-of-states>
   Initial: <initial-state>
   Max iterations: <max>

   Note: Test iteration found issues - see output above.
   You may want to review the configuration before running.

   Run now with: ll-loop <name>
   ```

   On validation failure:
   ```
   Loop saved but validation failed:
   <error-message>

   Please fix the configuration at .loops/<name>.yaml
   ```

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
│
├─ Fix a specific problem → Goal paradigm
│   "Run check, if fails run fix, repeat until passes"
│
├─ Maintain multiple standards → Invariants paradigm
│   "Check A, fix A if needed, check B, fix B if needed, ..."
│
├─ Reduce/increase a metric → Convergence paradigm
│   "Measure value, if not at target, apply fix, measure again"
│
└─ Run ordered steps → Imperative paradigm
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

---

## Examples

```bash
# Start the interactive wizard
/ll:create-loop

# The command will guide you through:
# 1. Selecting a paradigm (goal, invariants, convergence, imperative)
# 2. Configuring paradigm-specific options
# 3. Naming the loop
# 4. Previewing and saving the YAML
```

---

## Integration

This command creates FSM loop configurations that can be executed with the `ll-loop` CLI.

Works well with:
- `ll-loop <name>` - Execute the created loop
- `ll-loop validate <name>` - Validate loop configuration
- `/ll:check_code` - Often used as a fix action in loops
- `/ll:manage_issue` - Used for complex bug fixes in loops
