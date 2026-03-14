# Loop Type Questions (Step 2)

Based on the selected loop type, ask follow-up questions.

---

## Fix Until Clean Questions

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

> **Note**: The runtime default is 50 for all loop types. These options are suggested starting points to explicitly specify in your YAML based on your use case.
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

**Generate Fix Until Clean FSM YAML:**

```yaml
name: "<loop-name>"
initial: evaluate
max_iterations: <selected-max>
# scope: ["src/"]          # Optional: declare paths for ll-parallel concurrency control
states:
  evaluate:
    action: "<check-command>"
    on_success: done
    on_failure: fix
    on_error: fix
    # Include evaluate block only if not using default (exit_code):
    # evaluate:             # Optional - omit for exit_code default
    #   type: "<output_contains|output_numeric|llm_structured>"
    #   pattern: "<pattern>"     # For output_contains only
    #   operator: "<eq|lt|gt>"   # For output_numeric only
    #   target: <number>         # For output_numeric only
  fix:
    action: "<fix-command>"
    # action_type: prompt   # Add if fix action is natural language (no leading /)
    next: evaluate
  done:
    terminal: true
```

**Example for "Type errors + Lint errors":**

```yaml
name: "fix-types-and-lint"
initial: evaluate
max_iterations: 10
states:
  evaluate:
    action: "mypy src/ && ruff check src/"
    on_success: done
    on_failure: fix
    on_error: fix
  fix:
    action: "/ll:check-code fix"
    next: evaluate
  done:
    terminal: true
```

---

## Maintain Constraints Questions

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

Use the Tool Evaluator Defaults table (from Fix Until Clean section) to customize the evaluator question based on each constraint's check command. For example, if the constraint uses `pytest`, show "Exit code (Recommended for pytest)" with the rationale "Well-behaved: 0=all pass, 1=failures, 2+=errors".

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

Follow the same conditional flow as Fix Until Clean for pattern/numeric follow-ups.

**Generate Maintain Constraints FSM YAML:**

For each constraint `{name}` in order, generate a check/fix pair of states. The terminal state is `all_valid`. If `maintain: true`, the `all_valid` state loops back to the first check state instead of terminating.

```yaml
name: "<loop-name>"
initial: check_<name1>
max_iterations: 50
# scope: ["src/"]            # Optional: declare paths for ll-parallel concurrency control
states:
  check_<name1>:
    action: "<check-1-command>"
    on_success: check_<name2>  # or all_valid if last constraint
    on_failure: fix_<name1>
    # evaluate:               # Optional per-constraint
    #   type: "<output_contains|output_numeric|llm_structured>"
  fix_<name1>:
    action: "<fix-1-command>"
    next: check_<name1>
  check_<name2>:
    action: "<check-2-command>"
    on_success: all_valid      # or next constraint
    on_failure: fix_<name2>
  fix_<name2>:
    action: "<fix-2-command>"
    next: check_<name2>
  all_valid:
    terminal: true             # or next: check_<name1> if maintain: true
```

**Example for "Tests + Types + Lint":**

```yaml
name: "code-quality-guardian"
initial: check_tests
max_iterations: 50
states:
  check_tests:
    action: "pytest"
    on_success: check_types
    on_failure: fix_tests
  fix_tests:
    action: "/ll:manage-issue bug fix"
    next: check_tests
  check_types:
    action: "mypy src/"
    on_success: check_lint
    on_failure: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  check_lint:
    action: "ruff check src/"
    on_success: all_valid
    on_failure: fix_lint
  fix_lint:
    action: "ruff check --fix src/"
    next: check_lint
  all_valid:
    terminal: true
```

---

## Drive a Metric Questions

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

**Generate Drive a Metric FSM YAML:**

```yaml
name: "<loop-name>"
initial: measure
max_iterations: 50
# scope: ["src/"]  # Optional: declare paths for ll-parallel concurrency control
states:
  measure:
    action: "<metric-command>"
    evaluate:
      type: convergence
      toward: <target-value>
      tolerance: 0
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "<fix-action>"
    next: measure
  done:
    terminal: true
```

**Example for "Reduce lint errors to 0":**

```yaml
name: "eliminate-lint-errors"
initial: measure
max_iterations: 50
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    evaluate:
      type: convergence
      toward: 0
      tolerance: 0
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "/ll:check-code fix"
    next: measure
  done:
    terminal: true
```

---

## Run a Sequence Questions

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

Use the Tool Evaluator Defaults table (from Fix Until Clean section) to customize the evaluator question based on the exit condition check command. For compound commands (e.g., "mypy && ruff && pytest"), show "Exit code (Recommended)" since multiple tools are being combined.

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

Follow the same conditional flow as Fix Until Clean for pattern/numeric follow-ups.

**Generate Run a Sequence FSM YAML:**

```yaml
name: "<loop-name>"
initial: step_0
max_iterations: 50
backoff: 2
# scope: ["src/"]            # Optional: declare paths for ll-parallel concurrency control
states:
  step_0:
    action: "<step-1>"
    next: step_1
  step_1:
    action: "<step-2>"
    next: step_2
  step_2:
    action: "<step-3>"
    next: check_done
  check_done:
    action: "<exit-condition-command>"
    on_success: done
    on_failure: step_0
    # evaluate:               # Optional for exit condition
    #   type: "<output_contains|output_numeric|llm_structured>"
    #   pattern: "<pattern>"  # For output_contains only
    #   operator: "<eq|lt|gt>" # For output_numeric only
    #   target: <number>      # For output_numeric only
  done:
    terminal: true
```

**Example for "Fix -> Test -> Check until clean":**

```yaml
name: "fix-test-check"
initial: step_0
max_iterations: 50
backoff: 2
states:
  step_0:
    action: "/ll:check-code fix"
    next: step_1
  step_1:
    action: "pytest"
    next: step_2
  step_2:
    action: "mypy src/"
    next: check_done
  check_done:
    action: "mypy src/ && ruff check src/ && pytest"
    on_success: done
    on_failure: step_0
  done:
    terminal: true
```

---

## Harness Questions

If user selected "Harness a skill or prompt":

### Step H1: Discover Available Skills

Before asking questions, scan the skills directory:

```bash
ls skills/*/SKILL.md 2>/dev/null | sed 's|skills/||' | sed 's|/SKILL.md||'
```

For each skill found, read its `SKILL.md` to extract the first line of the `description:` frontmatter field.

**Question H1** (single AskUserQuestion call):

```yaml
questions:
  - question: "What do you want to harness?"
    header: "Target"
    multiSelect: false
    options:
      - label: "<skill-name>"
        description: "<skill description from SKILL.md frontmatter>"
      # ... one entry per discovered skill ...
      - label: "Custom prompt"
        description: "Enter a free-form natural language prompt to repeat"
```

**If "Custom prompt"**: Ask via Other input for the prompt text. Also ask: "What does 'done' look like?" (free text via Other) to derive the LLM-as-judge evaluation prompt.

---

### Step H2: Work Item Discovery

```yaml
questions:
  - question: "How are work items discovered?"
    header: "Work items"
    multiSelect: false
    options:
      - label: "Single-shot (no item iteration)"
        description: "Run the skill/prompt once; no discover state needed"
      - label: "Active issues list (Recommended for issue skills)"
        description: "Discover via: ll-issues list --json"
      - label: "File glob pattern"
        description: "Find files matching a pattern (e.g. .issues/**/*.md)"
      - label: "Manual list"
        description: "Hard-code a list of items in the loop"
```

**If "File glob pattern"**: Ask for the pattern via Other.

**If "Manual list"**: Ask for comma-separated items via Other.

---

### Step H3: Evaluation Phases

Read `.claude/ll-config.json` to detect configured tool commands (`test_cmd`, `lint_cmd`, `type_cmd`). Present only phases that are relevant:

```yaml
questions:
  - question: "Which evaluation phases should be included?"
    header: "Evaluation phases"
    multiSelect: true
    options:
      - label: "Tool-based gates (Recommended)"
        description: "Shell checks using configured test/lint/type commands"
        # Show only if at least one of test_cmd, lint_cmd, type_cmd is configured
      - label: "LLM-as-judge"
        description: "Claude assesses output quality against skill description"
      - label: "Diff invariants"
        description: "Check git diff --stat to catch runaway or off-scope changes"
```

**Default selection**: All available phases are pre-selected (Recommended).

---

### Step H4: Iteration Budget

```yaml
questions:
  - question: "How many retries per item before giving up?"
    header: "Per-item retries"
    multiSelect: false
    options:
      - label: "3 retries (Recommended)"
        description: "Good balance for most skills"
      - label: "5 retries"
        description: "For complex or slow-converging skills"
      - label: "1 retry (strict)"
        description: "Fail fast; skip items that don't resolve immediately"

  - question: "What is the total iteration budget?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "50 (Recommended)"
        description: "For up to ~15 items with 3 retries each"
      - label: "100"
        description: "For larger item sets"
      - label: "200"
        description: "For long-running batch operations"
```

**Auto-calculate total if omitted**: `max_iterations = estimated_items * per_item_retries * evaluation_states + buffer`

---

### Generate Harness FSM YAML

Use the answers from Steps H1–H4 to generate the YAML. Two structural variants:

#### Variant A: Single-Shot (no item discovery)

For "Single-shot" work item mode:

```yaml
name: "<loop-name>"
initial: execute
max_iterations: <per-item-retries>
states:
  execute:
    action: "<skill-or-prompt>"
    action_type: prompt
    next: check_concrete         # omit if no tool gates selected
  check_concrete:                # include if tool-based gates selected
    action: "<highest-priority configured cmd: test_cmd > lint_cmd > type_cmd>"
    action_type: shell
    evaluate:
      type: exit_code
    on_success: check_semantic   # or check_invariants or done if later phases omitted
    on_failure: execute
  check_semantic:                # include if LLM-as-judge selected
    action: "echo 'Evaluating output quality'"
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: "<auto-derived: 'Did the previous action successfully complete: <skill-description>? Answer YES or NO with brief rationale.'>"
    on_success: check_invariants # or done if diff invariants omitted
    on_failure: execute
  check_invariants:              # include if diff invariants selected
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_success: done
    on_failure: execute
  done:
    terminal: true
```

#### Variant B: Multi-Item (discover → iterate)

For "Active issues list", "File glob pattern", or "Manual list" work item modes:

```yaml
name: "<loop-name>"
initial: discover
max_iterations: <max-iterations>
states:
  discover:
    action: "<discovery-command>"   # see Discovery Commands table below
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_success: execute
    on_failure: done
  execute:
    action: "<skill-or-prompt> ${captured.current_item.output}"
    action_type: prompt
    next: check_concrete         # or check_semantic / check_invariants / advance
  check_concrete:                # include if tool-based gates selected
    action: "<highest-priority configured cmd>"
    action_type: shell
    evaluate:
      type: exit_code
    on_success: check_semantic   # or check_invariants or advance
    on_failure: execute
  check_semantic:                # include if LLM-as-judge selected
    action: "echo 'Evaluating output quality'"
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: "<auto-derived: 'Did the previous action successfully complete: <skill-description>? Answer YES or NO with brief rationale.'>"
    on_success: check_invariants # or advance
    on_failure: execute
  check_invariants:              # include if diff invariants selected
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_success: advance
    on_failure: execute
  advance:
    action: "echo 'Item complete'"
    action_type: shell
    next: discover
  done:
    terminal: true
```

**Discovery Commands by work item mode:**

| Mode | Discovery Command |
|------|------------------|
| Active issues list | `ll-issues list --json \| python3 -c "import json,sys; issues=[i for i in json.load(sys.stdin) if i.get('status')=='open']; print(issues[0]['id']) if issues else sys.exit(1)"` |
| File glob pattern | `find . -name '<pattern>' -not -path './.git/*' \| sort \| head -1` |
| Manual list | `python3 -c "items='<item1>,<item2>,...'.split(','); [open('/tmp/harness-items.txt','w').write('\n'.join(items))]; print(items[0])"` (first-run seeding) |

**Tool-gate command priority** (use highest-priority configured command):
1. `test_cmd` (most comprehensive)
2. `lint_cmd` (fast feedback)
3. `type_cmd` (type safety)
4. If none configured: omit `check_concrete` state entirely

**Convergence defaults by action type:**

| Skill category | Suggested max_iterations | Per-item retries |
|----------------|--------------------------|------------------|
| Issue refinement/analysis | 200 | 3 |
| Code quality / fix | 50 | 5 |
| Documentation | 100 | 3 |
| Custom prompt | 50 | 3 |

---

**Example: Harness `refine-issue` over all active issues**

```yaml
name: "harness-refine-issue"
initial: discover
max_iterations: 200
timeout: 14400
states:
  discover:
    action: |
      ll-issues list --json | python3 -c "
      import json, sys
      issues = json.load(sys.stdin)
      open_issues = [i for i in issues if i.get('status') == 'open']
      if not open_issues:
          sys.exit(1)
      print(open_issues[0]['id'])
      "
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_success: execute
    on_failure: done
  execute:
    action: /ll:refine-issue ${captured.current_item.output} --auto
    action_type: prompt
    next: check_concrete
  check_concrete:
    action: python -m pytest scripts/tests/ -q --tb=no
    action_type: shell
    evaluate:
      type: exit_code
    on_success: check_semantic
    on_failure: execute
  check_semantic:
    action: echo 'Evaluating refinement quality'
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: >
        Did the previous /ll:refine-issue action successfully refine the issue?
        Check that: the issue file was updated with new content, confidence scores
        were added or improved, and no errors occurred. Answer YES or NO.
    on_success: check_invariants
    on_failure: execute
  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_success: advance
    on_failure: execute
  advance:
    action: echo 'Issue refined'
    action_type: shell
    next: discover
  done:
    terminal: true
```
